"""Word baselines from the recorded rectangles: the box bottom is a biased baseline.

A rectangle's vertical extent depends on the glyphs in the word. Gallows (k, t, p, f and the pedestalled cth, ckh,
cph, cfh) raise the top; descenders (q, y, g, m and others) push the bottom below the writing line. A word with a
descender therefore gets a bottom that is too low by the descender depth and a word without one does not, which is a
per-word error of the size of the drift being measured. Two further box effects: a word written on a slope has an
axis-aligned box whose bottom is attained at the down-slope end and whose top at the up-slope end (the box is taller
by |slope| x width, and its bottom is below the baseline at the box centre by half of that), and some boxes are drawn
slightly off the text's own angle, which the boxes alone cannot tell.

``glyph_effects`` measures the glyph effects on the manuscript itself: every line's bottoms and tops are fitted with
their own straight line, the residuals (in the page's median box height H) are regressed on indicators "unit g occurs
in the word" for every unit the toolkit's Zattera splitter produces (``vmsspatial.units``), effects below 0.03 H are
set to zero, and words made only of zero-effect units are the reference level (offset 0). ``word_baselines`` turns a
bundle into one baseline point per word: ``bottom`` (box centre x, box bottom), ``centre`` (box centre x, box vertical
centre), or ``glyph``: two estimates, the bottom minus the word's descender offset and the top minus the word's
ascender offset plus the line's x-height (the median corrected-bottom-to-corrected-top distance of the line), each
moved from the box edge where a sloped word's box attains it to the box centre along the line's fitted slope (two
passes), combined with inverse-variance weights from the pooled residual variances of plain and marked words.
``baseline_rms`` compares the methods by the within-line residual from each line's own straight fit.

The glyph table is itself a result (which units push the box down or up, and by how much); ``baseline_rms`` says
whether the correction helps on the data at hand. What the boxes cannot give, a box drawn off the text's own angle
and the ink's actual baseline, comes from the page images: method ``ink`` reads the data product of
``vmsspatial.ink`` (the baseline of each word's x-height band measured on the Beinecke scan, in the recorded frame)
and falls back to the glyph baseline where a word's ink record is missing or flagged.

The four methods are also a shipped data product, ``data/manuscript/baselines.json.gz`` (``build_table``: per token
the box centre x and, per method, the baseline y and weight, in the recorded warp state, with the words' and
geometry's digests); ``word_baselines`` reads it when the bundle's words and geometry match and derives otherwise.
Lines whose orientation is not horizontal (``vmsspatial.orientation``) carry no baseline points (``orientations``);
the glyph effects are pooled over the pages whose paragraph lines are all horizontal.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import paths
from .bundle import digest, read_json, write_json
from .frames import check_same, require_warp, tag, tags
from .geometry import _lines, _pages, line_units
from .units import zattera

METHODS = ('bottom', 'centre', 'glyph', 'ink', 'auto')
DEFAULT_METHOD = 'auto'      # ink where the page has clean ink records, glyph otherwise; never the box bottom
TABLE_KEY = 'manuscript/baselines.json.gz'
TABLE_VERSION = '2026.10.30.1'
_TABLE = {}
MIN_EFFECT_H = 0.03          # smaller effects are set to zero
MIN_GLYPH_COUNT = 20         # a unit needs this many words to get an effect
MIN_LINE_UNITS = 3           # a line needs this many located rectangles for its own straight fit
PASSES = 2                   # slope-aware passes of word_baselines


def _line_fit(x, y, line, n_lines):
    """Unweighted least squares of y on [1, x] within every line at once. Returns (intercepts, slopes)."""
    S0 = np.bincount(line, None, n_lines).astype(float)
    S1 = np.bincount(line, x, n_lines)
    S2 = np.bincount(line, x * x, n_lines)
    T0 = np.bincount(line, y, n_lines)
    T1 = np.bincount(line, x * y, n_lines)
    det = S0 * S2 - S1 * S1
    ok = det > 1e-9 * np.maximum(S2, 1.0)
    slope = np.where(ok, (S0 * T1 - S1 * T0) / np.where(ok, det, 1.0), 0.0)
    has = S0 > 0
    icpt = np.where(has, (T0 - slope * S1) / np.where(has, S0, 1.0), 0.0)
    return icpt, slope


def page_heights(app, ms, orientations='horizontal') -> Tuple[Dict[int, float], list]:
    """(per page index the median height of its located, non-oversized rectangles on the lines of `orientations`, the
    study's H, one per rectangle; the ``line_units`` it read). ``ink.page_heights`` returns the dict alone."""
    units = line_units(app, ms, orientations=orientations)
    lines = _lines(ms)
    out = {}
    for p in _pages(ms):
        hs = [u['box'][3] - u['box'][1] for l in range(p['start_line'], p['end_line']) for u in units[l]]
        out[p['index']] = float(np.median(hs)) if hs else float('nan')
    return out, units


def _unit_rows(app, ms, units, exclude_quarantine):
    """One row per located rectangle: line, page, folio, token range, box, the Zattera units of its word(s). With
    `exclude_quarantine` the pages whose paragraph lines are not all horizontal are left out (the pooled effects)."""
    lines, pages = _lines(ms), _pages(ms)
    folio_of = {p['index']: p.get('folio') for p in pages}
    skip = set()
    if exclude_quarantine:
        from .orientation import nonhorizontal_pages
        skip = nonhorizontal_pages(app, ms)
    cache = {}
    rows = []
    for l, us in enumerate(units):
        page = lines[l]['page']
        folio = folio_of.get(page)
        if folio in skip or app['lines'][l]['page'] in skip:
            continue
        for u in us:
            glyphs = set()
            for t in app['words'][u['first']:u['last'] + 1]:
                if t not in cache:
                    cache[t] = frozenset(zattera(t))
                glyphs |= cache[t]
            rows.append(dict(line=l, page=page, first=u['first'], last=u['last'], box=u['box'], glyphs=glyphs))
    return rows


def _usable(rows, min_line_units):
    count = Counter(r['line'] for r in rows)
    return [r for r in rows if count[r['line']] >= min_line_units]


def _residuals(rows, H_of, which):
    """Residuals (in H) of the rectangles' bottoms (which=3) or tops (which=1) from their line's own straight fit on x."""
    lines = sorted({r['line'] for r in rows})
    lid = {l: k for k, l in enumerate(lines)}
    line = np.array([lid[r['line']] for r in rows])
    x = np.array([(r['box'][0] + r['box'][2]) / 2 for r in rows])
    y = np.array([r['box'][which] for r in rows])
    H = np.array([H_of[r['page']] for r in rows])
    a, b = _line_fit(x, y, line, len(lines))
    return (y - (a[line] + b[line] * x)) / H, len(lines)


def glyph_effects(app, ms, min_count: int = MIN_GLYPH_COUNT, min_effect_H: float = MIN_EFFECT_H, min_line_units: int = MIN_LINE_UNITS) -> dict:
    """The effect of every Zattera unit on a word's box bottom and box top, in H (positive = lower on the page).

    Pooled over the located, non-oversized rectangles of the paragraph text outside the pages with rotated paragraphs, on lines
    with `min_line_units` or more of them: residuals of bottoms and tops from each line's own straight fit, regressed
    on indicators of the units present in the word with the same per-line projection applied to the indicators
    (a within-line regression); units in fewer than `min_count` words get no
    effect; effects below `min_effect_H` in size are set to zero; the reference level is a word made only of
    zero-effect units (offset 0). Returns effects {unit: {n, bottom_H, top_H, bottom_raw_H, top_raw_H}}, the
    reference units, the pooled residual variances of plain and marked words after correction (the weights of
    ``word_baselines``), the RMS before and after, the median line x-height in H, and the counts."""
    H_of, units = page_heights(app, ms)
    rows = _usable(_unit_rows(app, ms, units, True), min_line_units)
    r_b, n_lines = _residuals(rows, H_of, 3)
    r_t, _ = _residuals(rows, H_of, 1)
    count = Counter(g for r in rows for g in r['glyphs'])
    inventory = sorted(g for g, c in count.items() if c >= min_count)
    col = {g: j for j, g in enumerate(inventory)}
    X = np.zeros((len(rows), len(inventory)))
    for i, r in enumerate(rows):
        for g in r['glyphs']:
            if g in col:
                X[i, col[g]] = 1.0
    # the residuals had each line's own [1, x] projected out; the indicators get the same projection (Frisch-Waugh),
    # otherwise a unit that is common on a line is attenuated by its own share of the line's level
    line_ids = sorted({r['line'] for r in rows})
    lid = {l: k for k, l in enumerate(line_ids)}
    line = np.array([lid[r['line']] for r in rows])
    x = np.array([(r['box'][0] + r['box'][2]) / 2 for r in rows])
    Xt = np.empty_like(X)
    for j in range(X.shape[1]):
        a, b = _line_fit(x, X[:, j], line, len(line_ids))
        Xt[:, j] = X[:, j] - (a[line] + b[line] * x)
    beta_b, *_ = np.linalg.lstsq(Xt, r_b, rcond=None)
    beta_t, *_ = np.linalg.lstsq(Xt, r_t, rcond=None)
    effects = {}
    for g in inventory:
        b, t = float(beta_b[col[g]]), float(beta_t[col[g]])
        effects[g] = dict(n=int(count[g]), bottom_H=b if abs(b) >= min_effect_H else 0.0, top_H=t if abs(t) >= min_effect_H else 0.0, bottom_raw_H=b, top_raw_H=t)
    for g, c in count.items():
        if g not in effects:
            effects[g] = dict(n=int(c), bottom_H=0.0, top_H=0.0, bottom_raw_H=float('nan'), top_raw_H=float('nan'))
    reference = sorted(g for g in inventory if effects[g]['bottom_H'] == 0.0 and effects[g]['top_H'] == 0.0)
    # residual variances after the correction, from refitted lines, for plain and marked words separately
    desc = np.array([sum(effects[g]['bottom_H'] for g in r['glyphs']) for r in rows])
    asc = np.array([sum(effects[g]['top_H'] for g in r['glyphs']) for r in rows])
    H = np.array([H_of[r['page']] for r in rows])
    corrected_b = [dict(r, box=[r['box'][0], r['box'][1], r['box'][2], r['box'][3] - d * h]) for r, d, h in zip(rows, desc, H)]
    corrected_t = [dict(r, box=[r['box'][0], r['box'][1] - a * h, r['box'][2], r['box'][3]]) for r, a, h in zip(rows, asc, H)]
    rb2, _ = _residuals(corrected_b, H_of, 3)
    rt2, _ = _residuals(corrected_t, H_of, 1)
    marked_b, marked_t = desc != 0, asc != 0

    def var(v, mask):
        return float(np.mean(v[mask] ** 2)) if mask.sum() >= min_count else float(np.mean(v ** 2))
    variance = dict(bottom_plain=var(rb2, ~marked_b), bottom_marked=var(rb2, marked_b), top_plain=var(rt2, ~marked_t), top_marked=var(rt2, marked_t),
                    n_bottom_marked=int(marked_b.sum()), n_top_marked=int(marked_t.sum()))
    xh = (np.array([r['box'][3] for r in rows]) - desc * H - (np.array([r['box'][1] for r in rows]) - asc * H)) / H
    return dict(effects=effects, inventory=inventory, reference=reference, n_words=len(rows), n_lines=n_lines, min_count=min_count, min_effect_H=min_effect_H,
                variance=variance, rms_before=dict(bottom=float(np.sqrt(np.mean(r_b ** 2))), top=float(np.sqrt(np.mean(r_t ** 2)))),
                rms_after=dict(bottom=float(np.sqrt(np.mean(rb2 ** 2))), top=float(np.sqrt(np.mean(rt2 ** 2)))),
                x_height_H=float(np.median(xh)), unit='page median rectangle height H')


def effects_table(effects: dict) -> List[dict]:
    """The effects as rows sorted by the size of the bottom effect, then the top effect (for a CSV)."""
    rows = [dict(unit=g, n_words=e['n'], bottom_H=e['bottom_H'], top_H=e['top_H'], bottom_raw_H=e['bottom_raw_H'], top_raw_H=e['top_raw_H'],
                 reference=g in effects['reference']) for g, e in effects['effects'].items()]
    rows.sort(key=lambda r: (-abs(r['bottom_H']), -abs(r['top_H']), -r['n_words']))
    return rows


def word_baselines(app, ms, method: str = DEFAULT_METHOD, effects: Optional[dict] = None, slopes: Optional[Dict[int, float]] = None,
                   passes: int = PASSES, details: bool = False, ink: Optional[dict] = None, orientations='horizontal', table=None):
    """Per token: (x anchor, baseline y, weight) or None; tokens of a shared rectangle get the rectangle's point.
    The default method 'auto' is the ink baseline on the pages whose ink records are clean (``warp.ink_pages``) and
    the glyph baseline on the others (and everywhere when no ink product fits the bundle); the box bottom is never
    a default. Read from the shipped table (``build_table``) when it was built on this bundle's words and geometry
    (`table`: the product, or False to derive), else derived here. Lines outside `orientations` get None.
    method 'bottom' / 'centre' / 'glyph' (module docstring) or 'ink': the baseline measured on the page images
    (``vmsspatial.ink``, the data product ``ink_measures.json.gz`` or `ink`), evaluated at the box centre and moved
    with the box bottom onto the bundle's geometry (recorded or flattened), with the glyph baseline standing in for
    every rectangle whose ink record is missing or flagged; `effects` from ``glyph_effects`` (computed here when
    None); `slopes` {line index: slope} start the slope-aware passes (else the first pass is flat). The weight is the
    estimate's precision in 1/H^2 (1 for bottom and centre; the ink points' pooled residual variance for ink). With
    details=True returns (points, {'x_height_H': {line: x-height in H}, 'slopes': {line: slope}, 'effects': effects,
    'ink': {'used', 'fallback', 'records'} for method 'ink'})."""
    if method not in METHODS:
        raise ValueError('method must be one of %r' % (METHODS,))
    if table is not False and effects is None and slopes is None and orientations == 'horizontal':
        stored = table_points(app, method, table)
        if stored is not None:
            if not details:
                return stored
            if method != 'glyph':
                return stored, dict(x_height_H={}, slopes={}, effects=None, from_table=True)
    if method == 'auto':
        return _auto_baselines(app, ms, effects, slopes, passes, details, ink, orientations, table)
    if method == 'ink':
        from .ink import load_ink, baseline_points, ink_matches, for_bundle
        ink = ink or load_ink()
        ink = for_bundle(ink, app)
        if not ink_matches(ink, app):
            raise ValueError('the ink product was measured on other words than this bundle (words_sha256 differs)')
        check_same(app, ink, 'the bundle and the ink product')
        pts, info = word_baselines(app, ms, 'glyph', effects=effects, slopes=slopes, passes=passes, details=True, orientations=orientations, table=table)
        H_of, units = page_heights(app, ms, orientations)
        ink_pts = baseline_points(ink, app)
        used = fallback = 0
        out = list(pts)
        for us in units:
            for u in us:
                q = ink_pts.get(u['first'])
                if q is None:
                    fallback += 1
                    continue
                used += 1
                for i in range(u['first'], u['last'] + 1):
                    out[i] = q
        info['ink'] = dict(used=used, fallback=fallback, records=len(ink_pts), residual_var_H2=ink.get('residual_var_H2'), version=ink.get('version'), source=ink.get('source'))
        return (out, info) if details else out
    H_of, units = page_heights(app, ms, orientations)
    rows = _unit_rows(app, ms, units, False)
    n = len(app['words'])
    out = [None] * n
    info = dict(x_height_H={}, slopes={}, effects=None)
    if method in ('bottom', 'centre'):
        for r in rows:
            b = r['box']
            pt = ((b[0] + b[2]) / 2, b[3] if method == 'bottom' else (b[1] + b[3]) / 2, 1.0)
            for i in range(r['first'], r['last'] + 1):
                out[i] = pt
        return (out, info) if details else out
    effects = effects or glyph_effects(app, ms)
    info['effects'] = effects
    eff, var = effects['effects'], effects['variance']
    zero = dict(n=0, bottom_H=0.0, top_H=0.0)
    H = np.array([H_of[r['page']] for r in rows])
    x0 = np.array([r['box'][0] for r in rows]); x1 = np.array([r['box'][2] for r in rows])
    y0 = np.array([r['box'][1] for r in rows]); y1 = np.array([r['box'][3] for r in rows])
    xc = (x0 + x1) / 2
    desc = np.array([sum(eff.get(g, zero)['bottom_H'] for g in r['glyphs']) for r in rows])
    asc = np.array([sum(eff.get(g, zero)['top_H'] for g in r['glyphs']) for r in rows])
    yb = y1 - desc * H                       # corrected bottom
    yt = y0 - asc * H                        # corrected top
    wb = np.where(desc != 0, 1.0 / var['bottom_marked'], 1.0 / var['bottom_plain'])
    wt = np.where(asc != 0, 1.0 / var['top_marked'], 1.0 / var['top_plain'])
    line_ids = sorted({r['line'] for r in rows})
    lid = {l: k for k, l in enumerate(line_ids)}
    line = np.array([lid[r['line']] for r in rows])
    page = np.array([r['page'] for r in rows])
    count = np.bincount(line, None, len(line_ids))
    s = np.zeros(len(line_ids))
    if slopes:
        for l, v in slopes.items():
            if l in lid:
                s[lid[l]] = v
    y = None
    for it in range(passes + 1):
        sl = s[line]
        xb = np.where(sl > 0, x1, np.where(sl < 0, x0, xc))      # where a sloped word's box attains its bottom
        xt = np.where(sl > 0, x0, np.where(sl < 0, x1, xc))      # and its top
        yb_c = yb - sl * (xb - xc)
        yt_c = yt - sl * (xt - xc)
        # the line's x-height: median corrected-bottom-to-corrected-top distance (lines with enough rectangles, else the page's median, else the global)
        xh_line = np.full(len(line_ids), np.nan)
        d = (yb_c - yt_c) / H
        for k in range(len(line_ids)):
            m = line == k
            if count[k] >= MIN_LINE_UNITS:
                xh_line[k] = np.median(d[m])
        page_xh = {}
        for p in np.unique(page):
            v = xh_line[np.unique(line[page == p])]
            v = v[np.isfinite(v)]
            page_xh[p] = float(np.median(v)) if len(v) else effects['x_height_H']
        xh = np.where(np.isfinite(xh_line[line]), xh_line[line], np.array([page_xh[p] for p in page]))
        yt_base = yt_c + xh * H
        y = (wb * yb_c + wt * yt_base) / (wb + wt)
        if it == passes:
            break
        a, b = _line_fit(xc, y, line, len(line_ids))
        s = np.where(count >= MIN_LINE_UNITS, b, 0.0)
    w = wb + wt
    for i, r in enumerate(rows):
        pt = (float(xc[i]), float(y[i]), float(w[i]))
        for j in range(r['first'], r['last'] + 1):
            out[j] = pt
    info['x_height_H'] = {line_ids[k]: (float(xh_line[k]) if np.isfinite(xh_line[k]) else None) for k in range(len(line_ids))}
    info['slopes'] = {line_ids[k]: float(s[k]) for k in range(len(line_ids))}
    return (out, info) if details else out


def _ink_for(app, ink):
    """The ink product aligned with the bundle, or None when none applies."""
    from . import paths as _paths
    try:
        from .ink import load_ink, for_bundle, ink_matches
        ink = ink or load_ink()
        ink = for_bundle(ink, app)
        return ink if ink_matches(ink, app) else None
    except (_paths.DataMissing, ValueError, KeyError):
        return None


def auto_pages(app, ms, ink: Optional[dict] = None) -> Dict[str, str]:
    """Per folio of the bundle, the method 'auto' stands for: 'ink' where the page has clean ink records, 'glyph'
    otherwise (``warp.ink_pages``)."""
    from .warp import ink_pages
    ink = _ink_for(app, ink)
    good = ink_pages(ink) if ink is not None else set()
    pages = _pages(ms)
    return {p['folio']: ('ink' if p['folio'] in good else 'glyph') for p in pages}


def _auto_baselines(app, ms, effects, slopes, passes, details, ink, orientations, table):
    ink = _ink_for(app, ink)
    choice = auto_pages(app, ms, ink)
    glyph, info = word_baselines(app, ms, 'glyph', effects=effects, slopes=slopes, passes=passes, details=True, orientations=orientations, table=table)
    out = list(glyph)
    used = 0
    if ink is not None and any(v == 'ink' for v in choice.values()):
        ink_pts = word_baselines(app, ms, 'ink', effects=effects or info.get('effects'), slopes=slopes, passes=passes, ink=ink, orientations=orientations, table=table)
        folio_of_line = {}
        for p in _pages(ms):
            for l in range(p['start_line'], p['end_line']):
                folio_of_line[l] = p['folio']
        for l, L in enumerate(app['lines']):
            if choice.get(folio_of_line.get(l, L['page'])) == 'ink':
                for i in range(L['start'], L['end']):
                    if ink_pts[i] is not None:
                        out[i] = ink_pts[i]
                        used += 1
    info = dict(info, auto=dict(rule='ink where the page has clean ink records, glyph otherwise', pages=dict(Counter(choice.values())), ink_points=used, choice=choice))
    return (out, info) if details else out


def line_xheights(app, ms, effects: Optional[dict] = None) -> Dict[int, Optional[float]]:
    """Per line index: the line's x-height in H (median corrected-bottom-to-corrected-top distance of its rectangles
    under the glyph baseline), None for lines with fewer than 3 located rectangles. A by-product of ``word_baselines``."""
    return word_baselines(app, ms, 'glyph', effects=effects, details=True)[1]['x_height_H']


def baseline_rms(app, ms, methods=None, effects: Optional[dict] = None, min_units: int = 4, ink: Optional[dict] = None, orientations='horizontal') -> dict:
    """For each method, the pooled RMS (in H) of the within-line residuals from each line's own straight fit, over the
    same words: lines outside the pages with rotated paragraphs with `min_units` or more located rectangles. Also the median of
    the per-line RMS. The glyph effects are estimated on the same data, so its gain is in-sample (a few dozen
    parameters against tens of thousands of words). `methods` defaults to bottom, centre, glyph, and ink when the
    ink product is present and was measured on this bundle's words (`skipped` says when it was not)."""
    skipped = []
    if methods is None:
        methods = ['auto', 'bottom', 'centre', 'glyph']
        try:
            from .ink import load_ink, ink_matches, for_bundle
            ink = ink or load_ink()
            ink = for_bundle(ink, app)
            if ink_matches(ink, app):
                methods.append('ink')
            else:
                skipped.append('ink (measured on other words)')
        except Exception as err:                                   # the product is optional here
            skipped.append('ink (%s)' % err)
    H_of, units = page_heights(app, ms, orientations)
    rows = _unit_rows(app, ms, units, True)
    count = Counter(r['line'] for r in rows)
    rows = [r for r in rows if count[r['line']] >= min_units]
    line_ids = sorted({r['line'] for r in rows})
    lid = {l: k for k, l in enumerate(line_ids)}
    line = np.array([lid[r['line']] for r in rows])
    H = np.array([H_of[r['page']] for r in rows])
    if effects is None and 'glyph' in methods:
        effects = glyph_effects(app, ms)
    out = dict(n_words=len(rows), n_lines=len(line_ids), methods={}, skipped=skipped)
    for method in methods:
        pts = word_baselines(app, ms, method, effects=effects, ink=ink, orientations=orientations)
        x = np.array([pts[r['first']][0] for r in rows])
        y = np.array([pts[r['first']][1] for r in rows])
        a, b = _line_fit(x, y, line, len(line_ids))
        res = (y - (a[line] + b[line] * x)) / H
        per_line = np.sqrt(np.bincount(line, res ** 2, len(line_ids)) / np.bincount(line, None, len(line_ids)))
        out['methods'][method] = dict(rms_pooled_H=float(np.sqrt(np.mean(res ** 2))), rms_line_median_H=float(np.median(per_line)),
                                      abs_residual_median_H=float(np.median(np.abs(res))))
    concrete = [m for m in out['methods'] if m != 'auto'] or list(out['methods'])        # 'auto' is a per-page choice among the others
    best = min(concrete, key=lambda m: out['methods'][m]['rms_pooled_H'])
    out['lowest'] = best
    return out


# ----------------------------------------------------------------------------- the stored table
def load_table(path=None, reload: bool = False) -> Optional[dict]:
    """The shipped baselines table (``TABLE_KEY``), read once; None when absent."""
    key = str(path) if path else ''
    if reload or key not in _TABLE:
        p = path or paths.resolve(TABLE_KEY, required=False)
        _TABLE[key] = read_json(p) if p and Path(p).is_file() else None
    return _TABLE[key]


def table_matches(table: Optional[dict], app) -> bool:
    """True when the table was built on this bundle's words and geometry, in the bundle's warp state (a table moved
    to the flat state by ``warp.transform`` matches the flat bundle derived from the same recorded geometry)."""
    if not table or table.get('words_sha256') != digest(app['words']):
        return False
    ta, tb = tags(table), tags(app)
    if ta['warp'] != tb['warp'] or ta['frame'] != tb['frame']:
        return False
    if ta['warp'] == 'flat':
        parent = (app.get('geometry_provenance') or {}).get('parent_geometry_sha256')
        return bool(parent) and table.get('geometry_sha256') == parent and table.get('warp_version') == (app.get('geometry_provenance') or {}).get('page_warp_version')
    return table.get('geometry_sha256') == digest(app['geometry'])


def table_for(table: Optional[dict], app) -> Optional[dict]:
    """The table on this bundle's stream: the table itself when it matches, the same records re-sequenced by (page,
    locus) when the bundle holds the same lines in another shape (other pages, another order) with the same box
    bottoms, None otherwise."""
    if table_matches(table, app):
        return table
    if not table or tags(table)['warp'] != tags(app)['warp'] or tags(table)['frame'] != tags(app)['frame']:
        return None
    where = {(L['page'], str(L['locus'])): L for L in table['lines']}
    index = []
    for L in app['lines']:
        T = where.get((L['page'], str(L['locus'])))
        if T is None or T['end'] - T['start'] != L['end'] - L['start']:
            return None
        index.extend(range(T['start'], T['end']))
    bottom = table['bottom']
    for i, b in zip(index, app['geometry']):
        if (b is None) != (bottom[i] is None) or (b is not None and abs(bottom[i] - b[3]) > 0.006):
            return None
    return dict(table, x=[table['x'][i] for i in index], bottom=[bottom[i] for i in index], lines=[dict(page=L['page'], locus=L['locus'], start=L['start'], end=L['end']) for L in app['lines']],
                methods={m: dict(v, y=[v['y'][i] for i in index], weight=[v['weight'][i] for i in index]) for m, v in table['methods'].items()},
                words_sha256=digest(app['words']), geometry_sha256=digest(app['geometry']), pages=app.get('pages'), order=app.get('order'))


def table_points(app, method: str, table=None):
    """Per token (x, y, weight) or None from the stored table, or None when no matching table is at hand."""
    t = table_for(table if isinstance(table, dict) else load_table(), app)
    if t is None or method not in t['methods']:
        return None
    x, m = t['x'], t['methods'][method]
    return [None if (m['y'][i] is None or x[i] is None) else (float(x[i]), float(m['y'][i]), float(m['weight'][i])) for i in range(len(x))]


def build_table(app, ms, ink: Optional[dict] = None, out=None, effects: Optional[dict] = None, log=print, round_px: int = 2) -> dict:
    """Derive the four baseline methods on the bundle (its recorded warp state) and write the table: {version, frame,
    warp, source, policy, words_sha256, geometry_sha256, lines, x (box centre per token), bottom (box bottom per
    token: where the warp is read), methods: {bottom, centre, glyph, ink: {y, weight, note}}, effects, ink_info}. y is
    rounded to `round_px` decimals (0.01 px), weights to five significant digits."""
    require_warp(app, 'recorded', 'the bundle the baselines are derived on')
    effects = effects or glyph_effects(app, ms)
    methods = {}
    x = [None] * len(app['words'])
    bottom = [None if not b else round(float(b[3]), round_px) for b in app['geometry']]
    notes = {'bottom': 'box centre x, box bottom', 'centre': 'box centre x, box vertical centre',
             'glyph': 'box bottom and top corrected for the word\'s descenders and gallows and the line\'s slope, combined with precision weights (glyph_effects)',
             'ink': 'the ink baseline measured on the Beinecke scan (vmsspatial.ink), evaluated at the box centre; the glyph baseline where the record is missing or flagged',
             'auto': 'the default: ink on the pages whose ink records are clean, glyph on the others'}
    ink_info = None
    ink = _ink_for(app, ink)
    auto_info = None
    for m in METHODS:
        if m == 'ink':
            if ink is None:
                if log:
                    log('baselines table: no ink product fits this bundle; method ink left out')
                continue
            pts, info = word_baselines(app, ms, 'ink', effects=effects, ink=ink, details=True, table=False)
            ink_info = info['ink']
        elif m == 'auto':
            pts, info = word_baselines(app, ms, 'auto', effects=effects, ink=ink, details=True, table=False)
            auto_info = info.get('auto')
        else:
            pts = word_baselines(app, ms, m, effects=effects, table=False)
        ys, ws = [None] * len(pts), [None] * len(pts)
        for i, p in enumerate(pts):
            if p is None:
                continue
            x[i] = round(float(p[0]), round_px)
            ys[i] = round(float(p[1]), round_px)
            ws[i] = float('%.5g' % p[2])
        methods[m] = dict(y=ys, weight=ws, note=notes[m], located=sum(1 for p in pts if p is not None))
    table = dict(version=TABLE_VERSION, frame='recorded', warp='recorded', source='voynichese', policy=app.get('policy'),
                 words_sha256=digest(app['words']), geometry_sha256=digest(app['geometry']), review_version=(app.get('geometry_provenance') or {}).get('review_version'),
                 note='Per token the box centre x and, per baseline method, the baseline y (px, recorded frame and warp state) and its weight (precision in 1/H^2); '
                      'tokens of a shared rectangle repeat its point; lines that are not horizontal carry none. Move it with vmsspatial.warp.transform.',
                 lines=[dict(page=L['page'], locus=L['locus'], start=L['start'], end=L['end']) for L in app['lines']], x=x, bottom=bottom, methods=methods,
                 effects=dict(effects=effects['effects'], reference=effects['reference'], variance=effects['variance'], x_height_H=effects['x_height_H'], n_words=effects['n_words'], n_lines=effects['n_lines']),
                 ink_info=ink_info, auto=auto_info, pages=app.get('pages'), order=app.get('order'))
    out = out or (paths.data_dir() / TABLE_KEY)
    write_json(table, out)
    _TABLE.clear()
    if log:
        log('wrote %s (%.2f MB): %s' % (out, Path(out).stat().st_size / 2 ** 20, ', '.join('%s %d' % (m, v['located']) for m, v in methods.items())))
    return table
