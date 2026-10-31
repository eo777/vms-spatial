"""Line, baseline and warp statistics: one record per horizontal line and one per located rectangle.

    from vmsspatial import line_stats
    lines = line_stats.line_table()                  # one record per horizontal line of the whole manuscript
    words = line_stats.word_table()                  # one record per located rectangle
    lines.to_csv('lines.csv'); words.to_csv('words.csv')
    line_stats.KEYS['sag']                           # what a column means: label, unit, sign, per word or per line
    plot.plot_page('f75r', color_by='resid_chord')   # any key of KEYS paints a page

The numbers answer how each line lies on the page: its chord and fit, how far every word stands from them, how much of
that the photograph put there (the stored page warp) and where the ink's own baseline runs. The atlas shows the same
numbers (Colors, "Lines, baselines and warp"; ``viewer_measures`` packages them), so a value read on a page can be
recomputed from code.

Inputs. The default is ``load_bundle('sensitivity')`` on every page and locus: the most complete reviewed geometry, a
shared rectangle counted once. Any bundle and Manuscript may be passed (any policy, either warp state: the other state
comes from the stored page warp, never from a refit). Anchors come from ``compare.prepare``: one baseline point per
rectangle by ``baseline`` ('auto': the ink baseline on pages with clean ink records, the glyph-corrected box baseline
elsewhere), moved with each box's own shift between the two warp states.

Which lines. A line record exists for every horizontal line (``orientation``); the other kinds are skipped and counted
in ``meta['skipped']``. No qualification rule is applied: a chord needs two anchors, a least-squares fit three, the
quantities that read a line's shape four, and a smaller line reports None for what it cannot support. To reproduce a
study's rule, filter on `n_anchors` and `span_W` (four located rectangles spanning three median word widths).

Units and signs. H = the page's median box height, W = its median box width; y runs DOWN the page, so a larger y is
lower on it. An angle is positive when the line falls to the right. A residual is positive below the chord or the fit.
`offset` is positive when the line ends lower than it starts. `sag` is positive when the middle lies lower on the page
than the ends: it is the parabola through the anchors at mid-line against its own chord, so with the quadratic term c
of y/H = a + b u + c u^2 (u = 0..1 along the line, column `quad_c`), sag = -c / 4. `warp_shift` is recorded minus flat:
positive where the photograph pushed the box down. `baseline_shift` and `ink_shift` are the ink baseline minus the box
bottom and minus the glyph baseline: negative where the ink lies higher. `step` is positive when the text right of a
break sits lower than the continuation of the text left of it.

States. A column names its state when it matters: `*_recorded` are in the recorded warp state, every other chord, fit,
residual and offset is flat. Ink columns are measured on the Beinecke scan and returned in the recorded frame (the
registration's residual applies, PITFALLS 19). `chord_centred` subtracts the page's median flat chord angle
(``compare.page_drift``). Each table's ``meta`` carries frame, warp and source tags, so ``frames.require_same`` reads
it like any other table. Pages without a fitted field have None warp columns and `page_flattened` 0. Page columns
(`page_*`) repeat the page's value on each line.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Optional, Sequence

import numpy as np

VERSION = '2026.10.31.1'
GROUP = 'Lines, baselines and warp'
MIN_CHORD = 2                 # a chord needs two anchors
MIN_FIT = 3                   # a least-squares line three
MIN_SHAPE = 4                 # a parabola, or a rank correlation along the line, four
BIG_OFFSET_H = 0.5            # the share of the offset reached at mid-line reads lines with at least this |offset|
WARP_SAMPLES = 7              # points along a line's warped baseline


def _key(label, unit, kind, per, digits, description, domain=None, menu=True):
    return dict(label=label, unit=unit, kind=kind, per=per, digits=digits, description=description, domain=domain, menu=menu)


# key -> what it is. `per`: token (a located rectangle, every token of a shared box takes its value), line, or page (one
# value per page, repeated on its lines). `menu`: shown under Colors; the others appear in the atlas's line notes.
KEYS = dict(
    resid_chord=_key('Chord residual', 'H', 'diverging', 'token', 2, "The word's baseline minus its line's chord from first to last anchor, flat state. Positive = below the chord."),
    resid_fit=_key('Fit residual', 'H', 'diverging', 'token', 2, "The word's baseline minus its line's least-squares line, flat state. Positive = below the fit."),
    warp_shift=_key('Warp shift', 'H', 'diverging', 'token', 2, 'Recorded minus flat position of the box: what the stored page warp removed. Positive = the photograph pushed the box down. Empty on pages without a fitted field.'),
    baseline_shift=_key('Ink minus box', 'H', 'diverging', 'token', 2, 'Ink baseline minus box bottom, on the Beinecke scan in the recorded frame. Negative = the writing line lies above the box bottom. Clean ink records only.'),
    ink_shift=_key('Ink minus glyph', 'H', 'diverging', 'token', 2, 'Ink baseline minus the glyph-corrected box baseline, recorded frame. Negative = the ink lies above the box baseline. Clean ink records only.'),
    ink_xheight=_key('Ink x-height', 'H', 'sequential', 'token', 2, "Height of the word's x-height band on the Beinecke scan, recorded frame. Clean ink records only."),
    intrusion_depth=_key('Intrusion depth', 'H', 'sequential', 'token', 2, "The deepest intrusion the word takes part in: a descender below the next line's mean line, or an ascender above the previous line's baseline. Recorded frame, Beinecke scan. A visual audit found about 15 percent of deep events (5 of 36) are touching merges where the upper word has no descender."),
    chord_flat=_key('Chord angle, flat', 'deg', 'diverging', 'line', 2, "Angle of the chord from the line's first to its last baseline anchor, stored page warp removed. Positive falls to the right."),
    chord_recorded=_key('Chord angle, recorded', 'deg', 'diverging', 'line', 2, 'The same chord in the recorded coordinates, camera rotation and page deformation included.'),
    chord_centred=_key('Centred chord angle', 'deg', 'diverging', 'line', 2, "The flat chord angle minus the page's median: the line's own tilt against its page."),
    ls_angle=_key('Fit angle', 'deg', 'diverging', 'line', 2, 'Angle of the least-squares line through the anchors, flat state; three or more anchors.'),
    offset=_key('End offset', 'H', 'diverging', 'line', 2, 'Last anchor minus first anchor, flat state. Positive = the line ends lower.'),
    offset_centred=_key('Centred end offset', 'H', 'diverging', 'line', 2, "The end offset minus the page's median chord angle carried over the line's span."),
    abs_offset=_key('Absolute end offset', 'H', 'sequential', 'line', 2, 'The end offset whichever way the line tilts.'),
    fit_rms=_key('Fit RMS', 'H', 'sequential', 'line', 3, 'Root mean square of the anchors about the least-squares line, flat state: the wobble once the tilt is gone.'),
    sag=_key('Line sag', 'H', 'diverging', 'line', 3, 'The parabola through the anchors at mid-line against its own chord, flat state; four or more anchors. Positive = the middle lies lower on the page than the ends.'),
    jitter=_key('Word jitter', 'H', 'sequential', 'line', 3, 'Median absolute baseline step between neighbouring anchors, flat state.'),
    jump_share=_key('Largest jump share', 'ratio', 'sequential', 'line', 3, "The largest step between neighbouring anchors as a share of the line's summed steps. 1 = one step carries all of it."),
    rho=_key('Accumulation rho', '', 'diverging', 'line', 2, "Spearman correlation of a word's deviation from the first word with its position along the line. Near +1 the line falls steadily, near -1 it rises steadily; four or more anchors.", domain=(-1, 1)),
    max_u=_key('Largest residual position', '', 'sequential', 'line', 2, 'Where the word farthest from the fit stands: 0 = first anchor, 1 = last.', domain=(0, 1)),
    step=_key('Break step', 'H', 'diverging', 'line', 2, "The common-slope step at the line's largest illustration break. Positive = the text after the break sits lower than the continuation of the text before it."),
    n_breaks=_key('Break count', '', 'sequential', 'line', 0, 'Illustration breaks on the line (transcript markers or geometric segment boundaries) with located words on both sides.', domain=(0, 3)),
    ink_vs_box_angle=_key('Ink angle difference', 'deg', 'diverging', 'line', 2, "The robust fit through the line's ink baselines minus the least-squares angle of its box bottoms, recorded frame. Positive = the ink falls to the right more than the boxes."),
    xheight_spread=_key('X-height spread', 'H', 'sequential', 'line', 3, "Median absolute deviation of the line's ink x-heights."),
    line_words=_key('Located words', '', 'sequential', 'line', 0, 'Located rectangles on the line, a shared box once.'),
    line_span=_key('Anchor span', 'H', 'sequential', 'line', 1, 'Horizontal distance from the first to the last anchor.'),
    chord_rms=_key('Chord RMS', 'H', 'sequential', 'line', 3, 'Root mean square of the anchors about the chord, flat state.', menu=False),
    chord_max=_key('Chord largest residual', 'H', 'sequential', 'line', 3, 'Largest absolute residual from the chord, flat state.', menu=False),
    fit_max=_key('Fit largest residual', 'H', 'sequential', 'line', 3, 'Largest absolute residual from the fit, flat state.', menu=False),
    half_diff=_key('Half slope difference', 'H', 'diverging', 'line', 3, "The second half's fitted slope minus the first half's, as offset per line width, flat state.", menu=False),
    mid_share=_key('Offset at mid-line', 'ratio', 'sequential', 'line', 2, 'Share of the end offset reached at mid-line, on lines with an end offset of 0.5 H or more.', menu=False),
    warp_mean=_key('Line warp mean', 'H', 'diverging', 'line', 3, 'Mean shift the warp removed along the line.', menu=False),
    warp_range=_key('Line warp range', 'H', 'sequential', 'line', 3, 'Range of the shift the warp removed along the line.', menu=False),
    xheight=_key('Line x-height', 'H', 'sequential', 'line', 2, "Median ink x-height of the line's clean words.", menu=False),
    ink_rms=_key('Ink fit RMS', 'H', 'sequential', 'line', 3, "Residual of the clean words' ink baselines about the line's robust fit.", menu=False),
    ink_clean=_key('Clean ink words', '', 'sequential', 'line', 0, 'Clean ink records on the line.', menu=False),
    reg_dx=_key('Registration shift x', 'px', 'diverging', 'line', 2, "The line's local registration shift, horizontal, recorded px.", menu=False),
    reg_dy=_key('Registration shift y', 'px', 'diverging', 'line', 2, "The line's local registration shift, vertical, recorded px.", menu=False),
    page_warp_amplitude=_key('Warp amplitude', 'H', 'sequential', 'page', 3, "Peak-to-peak curvature of the stored page warp over the core of the page, the range at least half the page's lines reach."),
    page_tilt=_key('Page tilt', 'deg', 'diverging', 'page', 2, "The page's shared tilt removed by the stored warp. Camera rotation and a slant the scribe wrote cannot be told apart."),
    page_keystone=_key('Page keystone', 'deg/H', 'diverging', 'page', 3, "Change of the page's tilt per box height down the page."),
    page_flattened=_key('Warp fitted', '0/1', 'sequential', 'page', 0, '1 where the page has a fitted warp field, 0 where its boxes stay recorded.', domain=(0, 1)),
)
TOKEN_KEYS = [k for k, v in KEYS.items() if v['per'] == 'token']
LINE_KEYS = [k for k, v in KEYS.items() if v['per'] == 'line']
PAGE_KEYS = [k for k, v in KEYS.items() if v['per'] == 'page']
LINE_COLUMNS = ['line', 'folio', 'locus', 'locus_type', 'section', 'hand', 'group', 'par_pos', 'par_index', 'par_len', 'n_anchors', 'span_W', 'H_px', 'W_px'] + \
               LINE_KEYS + ['offset_recorded', 'ls_offset', 'quad_c', 'step_conc', 'break_kinds', 'page_median_angle', 'page_baseline', 'gutter_side', 'expected_gutter'] + PAGE_KEYS
WORD_COLUMNS = ['first', 'last', 'word', 'folio', 'locus', 'line', 'kind', 'x0', 'y0', 'x1', 'y1', 'x', 'y_recorded', 'y_flat', 'anchor'] + TOKEN_KEYS
_CACHE: Dict[tuple, dict] = {}


# ----------------------------------------------------------------------------- one line
def rank(a) -> np.ndarray:
    """Average ranks (1 = smallest; ties share their mean rank)."""
    a = np.asarray(a, float)
    order = np.argsort(a, kind='mergesort')
    ranks = np.empty(len(a))
    ranks[order] = np.arange(1, len(a) + 1)
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    return (np.bincount(inv, weights=ranks) / counts)[inv]


def spearman(x, y) -> Optional[float]:
    """Spearman correlation, None for fewer than three points or a constant series."""
    if len(x) < 3:
        return None
    rx, ry = rank(x), rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def line_shape(x, y, H: float) -> dict:
    """The quantities of one line from its baseline anchors.

    Args:
        x: the anchors' horizontal positions, ascending (pixels).
        y: their vertical positions (pixels, growing DOWN the page), in one warp state.
        H: the page's median box height (pixels).

    Returns:
        a dict: chord (deg), offset, span_px, resid_chord (per anchor, H), chord_rms, chord_max (from two and three
        anchors), ls_angle, ls_slope, ls_intercept, ls_offset, resid_fit, fit_rms, fit_max, max_u, jitter, jump_share,
        step_conc (from three), quad_c, sag, half_diff, rho, mid_share (from four). What the line cannot support is
        None. Signs: module docstring.

    Example:
        >>> line_shape([0, 100, 200, 300], [10, 12, 14, 16], 20)['chord'] > 0        # falling to the right
        True
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    out = dict.fromkeys(('chord', 'offset', 'span_px', 'resid_chord', 'chord_rms', 'chord_max', 'ls_angle', 'ls_slope', 'ls_intercept', 'ls_offset', 'resid_fit', 'fit_rms', 'fit_max',
                         'max_u', 'jitter', 'jump_share', 'step_conc', 'quad_c', 'sag', 'half_diff', 'rho', 'mid_share'))
    if n < MIN_CHORD or x[-1] <= x[0]:
        return out
    span = float(x[-1] - x[0])
    u = (x - x[0]) / span
    slope = (y[-1] - y[0]) / span
    r_chord = (y - (y[0] + slope * (x - x[0]))) / H
    d = (y - y[0]) / H
    out.update(chord=math.degrees(math.atan(slope)), offset=float(d[-1]), span_px=span, resid_chord=r_chord)
    if n < MIN_FIT:
        return out
    b, a = np.polyfit(x, y, 1)
    r_fit = (y - (a + b * x)) / H
    jumps = np.abs(np.diff(y)) / H
    total = float(jumps.sum())
    out.update(chord_rms=float(np.sqrt(np.mean(r_chord ** 2))), chord_max=float(np.max(np.abs(r_chord))), ls_angle=math.degrees(math.atan(b)), ls_slope=float(b), ls_intercept=float(a),
               ls_offset=float(b * span / H), resid_fit=r_fit, fit_rms=float(np.sqrt(np.mean(r_fit ** 2))), fit_max=float(np.max(np.abs(r_fit))), max_u=float(u[int(np.argmax(np.abs(r_fit)))]),
               jitter=float(np.median(jumps)))
    if total > 0:
        out['jump_share'] = float(jumps.max() / total)
        out['step_conc'] = out['jump_share'] * (n - 1)
    if n < MIN_SHAPE:
        return out
    c = float(np.polyfit(u, y / H, 2)[0])
    out.update(quad_c=c, sag=-c / 4, rho=spearman(u, d))
    first, second = u <= 0.5, u > 0.5
    if first.sum() >= 2 and second.sum() >= 2 and np.ptp(x[first]) > 0 and np.ptp(x[second]) > 0:
        out['half_diff'] = float((np.polyfit(x[second], y[second], 1)[0] - np.polyfit(x[first], y[first], 1)[0]) * span / H)
    if abs(d[-1]) >= BIG_OFFSET_H:
        out['mid_share'] = float(np.interp(0.5, u, d) / d[-1])
    return out


def _fit_or_chord(x, y):
    """(slope, intercept): least squares from three points, the chord through two, None for one."""
    if len(x) >= 3:
        s, a = np.polyfit(x, y, 1)
        return float(s), float(a)
    if len(x) == 2 and x[1] > x[0]:
        s = (y[1] - y[0]) / (x[1] - x[0])
        return float(s), float(y[0] - s * x[0])
    return None


def break_step(xl, yl, xr, yr, H: float) -> dict:
    """The step at a break between a left component (xl, yl) and a right one (xr, yr), x ascending, y down the page.

    Args:
        xl, yl, xr, yr: the anchors on either side.
        H: the page's median box height.

    Returns:
        {step: the common-slope step in H (both sides share one slope, one intercept and a step; None under three
        anchors), step_lr: the right side's first anchor against the left fit extended, step_rl: the right fit extended
        back to the left side's last anchor, fit_left, fit_right: (slope, intercept) of each component or None}.
        Positive = the right side lies lower than the continuation of the left.
    """
    xl, yl, xr, yr = (np.asarray(v, float) for v in (xl, yl, xr, yr))
    fl, fr = _fit_or_chord(xl, yl), _fit_or_chord(xr, yr)
    out = dict(step=None, fit_left=fl, fit_right=fr, step_lr=(float((yr[0] - (fl[1] + fl[0] * xr[0])) / H) if fl else None), step_rl=(float(((fr[1] + fr[0] * xl[-1]) - yl[-1]) / H) if fr else None))
    x, y = np.concatenate([xl, xr]), np.concatenate([yl, yr])
    if len(x) >= 3:
        A = np.column_stack([x, np.ones(len(x)), np.concatenate([np.zeros(len(xl)), np.ones(len(xr))])])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        out['step'] = float(coef[2] / H)
    return out


# ----------------------------------------------------------------------------- the manuscript
def _finite(v):
    return None if v is None or not math.isfinite(v) else float(v)


def _paragraphs(page: dict) -> Dict[int, tuple]:
    """Page line index -> (position in the paragraph: single, first, middle, last; its place, 1-based; the paragraph's
    length), from the page's canonical paragraphs."""
    out = {}
    for b in page['blocks']:
        key = b['key']
        if not (key[0] == 'p' and key[1:].isdigit()):
            continue
        ls = b['lines']
        for k, l in enumerate(ls):
            out[l] = ('single' if len(ls) == 1 else 'first' if k == 0 else 'last' if k == len(ls) - 1 else 'middle', k + 1, len(ls))
    return out


def _page_record(p: dict, H, W, drift_angle, recorded_drift) -> dict:
    st = p['warp']
    q = st.get('quality') or {}
    fitted = bool(st.get('fitted'))
    anchors = Counter(u['anchor_kind'] for u in p['units'] if u['anchor_kind'] != 'box centre')
    return dict(folio=p['folio'], H=H, W=W, fitted=fitted, reason=st.get('reason') or '', page_baseline=st.get('baseline'), page_anchors=anchors.most_common(1)[0][0] if anchors else None, page_warp_amplitude=_finite(q.get('curvature_pp_core_H')) if fitted else None,
                page_tilt=q.get('tilt_deg') if fitted else None, page_keystone=q.get('keystone_deg_per_H') if fitted else None, page_flattened=1 if fitted else 0, gutter_side=q.get('gutter_side') if fitted else None,
                expected_gutter=None, page_median_angle=drift_angle, page_median_recorded=recorded_drift, registration=None)


def compute(app=None, ms=None, baseline: str = 'auto', ink: Optional[dict] = None, log=None) -> dict:
    """Everything the tables and the atlas read, computed once.

    Args:
        app: the bundle (default ``load_bundle('sensitivity')`` on the shape of `ms`, recorded rectangles; either warp
            state works, the other comes from the stored page warp).
        ms: its Manuscript (default ``bundle.manuscript_of(app)``, or the whole manuscript).
        baseline: the anchor method (``baselines.word_baselines``; 'auto' by default).
        ink: the ink product (default ``ink.load_ink``; without one the ink columns are None and `ink_note` says so).
        log: a print-like callable or None.

    Returns:
        {lines: per bundle line a record or None (not horizontal), words: per located rectangle a record, breaks,
        intrusions, ink_fits, warp_curves, pages: {folio: page record}, app, ms, data (``compare.prepare``), rec_tags,
        baseline, baseline_pages, skipped, ink_note, version}.
    """
    from . import compare as C, warp as W
    from .baselines import page_heights, word_baselines
    from .bundle import load_bundle, manuscript_of
    from .frames import require_same, tags
    from .geometry import line_breaks, line_frames
    from .orientation import attach
    key = (id(app), id(ms), baseline, id(ink))
    if key in _CACHE:
        return _CACHE[key]
    if app is None:
        if ms is None:
            from .manuscript import Manuscript
            ms = Manuscript.load()
        given = load_bundle('sensitivity', pages=ms.page_set, order=ms.order, warp='recorded')
    else:
        given = app
        ms = ms or manuscript_of(app)
    rec = given
    if tags(given)['warp'] != 'recorded':
        rec = W.transform(given, 'recorded')
        attach(rec, ms, force=True)
    data = C.prepare(rec, ms, baseline=baseline, log=log)
    attach(rec, ms)
    n_lines = len(rec['lines'])
    pages_ms = ms.pages if hasattr(ms, 'pages') else ms['pages']
    heights, units = page_heights(rec, ms)
    prod = W.load_warp()
    frames = line_frames(rec, ms)
    breaks = line_breaks(rec, ms, frames)
    glyph = word_baselines(rec, ms, 'glyph', table=False)
    lines: List[Optional[dict]] = [None] * n_lines
    words: List[dict] = []
    word_at: Dict[int, dict] = {}
    break_rows, curves = [], []
    pages: Dict[str, dict] = {}
    skipped = Counter()
    for pg in pages_ms:
        folio = pg['folio']
        p = data['pages'][folio]
        H = _finite(heights.get(pg['index']))
        base = pg['start_line']
        widths = [u['box'][2] - u['box'][0] for l in range(pg['start_line'], pg['end_line']) for u in units[l]]
        W_px = float(np.median(widths)) if widths else None
        fl, re_ = C.page_drift(data, folio, 'flat'), C.page_drift(data, folio, 'recorded')
        page = pages[folio] = _page_record(p, H, W_px, fl['angle'], re_['angle'])
        page['expected_gutter'] = (prod['pages'].get(folio) or {}).get('expected_gutter')
        pw = W.page_warp(folio, prod) if page['fitted'] else None
        paragraphs = _paragraphs(p)
        for L in p['lines']:
            l = base + L['index']
            horizontal = L['orientation'] == 'horizontal'
            us = [p['units'][i] for i in L['units']]
            for u in us:
                w = dict(first=u['first'], last=u['last'], word=u['text'], folio=folio, locus=L['locus'], line=l, kind=L['orientation'], x0=u['rect'][0], y0=u['rect'][1], x1=u['rect'][2], y1=u['rect'][3],
                         x=u['base'][0], y_recorded=u['base'][1], y_flat=u['flat_base'][1], anchor=u['anchor_kind'], **dict.fromkeys(TOKEN_KEYS))
                if horizontal and H and page['fitted']:
                    w['warp_shift'] = (u['rect'][3] - u['flat'][3]) / H
                words.append(w)
                word_at[u['first']] = w
            if not horizontal:
                skipped[L['orientation']] += 1
                continue
            r = dict.fromkeys(LINE_COLUMNS)
            r.update(line=l, folio=folio, locus=L['locus'], locus_type=rec['lines'][l].get('locus_type'), section=p.get('section'), hand=p.get('hand'), group=p.get('group'), n_anchors=0, line_words=len(us), H_px=H, W_px=W_px,
                     page_baseline=page['page_baseline'], page_median_angle=page['page_median_angle'], gutter_side=page['gutter_side'], expected_gutter=page['expected_gutter'], n_breaks=0)
            r.update({k: page[k] for k in PAGE_KEYS})
            if L['index'] in paragraphs:
                r['par_pos'], r['par_index'], r['par_len'] = paragraphs[L['index']]
            lines[l] = r
            anch = sorted((u for u in us if u['anchor_kind'] != 'box centre'), key=lambda u: u['base'][0])
            r['n_anchors'] = len(anch)
            if len(anch) < MIN_CHORD or not H:
                continue
            x = np.array([u['base'][0] for u in anch], float)
            yr = np.array([u['base'][1] for u in anch], float)
            yf = np.array([u['flat_base'][1] for u in anch], float)
            sf, sr = line_shape(x, yf, H), line_shape(x, yr, H)
            if sf['chord'] is None:
                continue
            r.update(chord_flat=sf['chord'], chord_recorded=sr['chord'], offset=sf['offset'], abs_offset=abs(sf['offset']), offset_recorded=sr['offset'], line_span=sf['span_px'] / H,
                     span_W=sf['span_px'] / W_px if W_px else None, ls_angle=sf['ls_angle'], ls_offset=sf['ls_offset'], fit_rms=sf['fit_rms'], fit_max=sf['fit_max'], max_u=sf['max_u'],
                     chord_rms=sf['chord_rms'], chord_max=sf['chord_max'], sag=sf['sag'], quad_c=sf['quad_c'], half_diff=sf['half_diff'], rho=sf['rho'], mid_share=sf['mid_share'],
                     jitter=sf['jitter'], jump_share=sf['jump_share'], step_conc=sf['step_conc'])
            if page['page_median_angle'] is not None:
                r['chord_centred'] = sf['chord'] - page['page_median_angle']
                r['offset_centred'] = sf['offset'] - math.tan(math.radians(page['page_median_angle'])) * sf['span_px'] / H
            for k, u in enumerate(anch):
                word_at[u['first']]['resid_chord'] = float(sf['resid_chord'][k])
                if sf['resid_fit'] is not None:
                    word_at[u['first']]['resid_fit'] = float(sf['resid_fit'][k])
            r['_x'], r['_yr'], r['_yf'] = x, yr, yf
            r['_fit_flat'] = (sf['ls_slope'], sf['ls_intercept']) if sf['ls_slope'] is not None else None
            r['_fit_recorded'] = (sr['ls_slope'], sr['ls_intercept']) if sr['ls_slope'] is not None else None
            # breaks: the components between them, in x order
            brs = [b for b in breaks[l] if b['left'] is not None and b['right'] is not None and b['adjacent']]
            r['n_breaks'] = len(brs)
            mids = [(b['gap'][0] + b['gap'][1]) / 2 for b in brs]
            comp = np.array([sum(1 for m in mids if xx >= m) for xx in x])
            steps = []
            kinds = []
            for k, b in enumerate(brs):
                kind = 'both' if b['transcript'] and b['geometric'] else ('transcript' if b['transcript'] else 'geometric')
                kinds.append(kind)
                ml, mr = comp == k, comp == k + 1
                if not ml.any() or not mr.any():
                    continue
                f = break_step(x[ml], yf[ml], x[mr], yf[mr], H)
                g = break_step(x[ml], yr[ml], x[mr], yr[mr], H)
                left_ix, right_ix = int(np.flatnonzero(ml)[-1]), int(np.flatnonzero(mr)[0])
                ul, ur = anch[left_ix], anch[right_ix]
                if f['step'] is not None:
                    steps.append(f['step'])
                break_rows.append(dict(line=l, folio=folio, locus=L['locus'], kind=kind, left_token=b['left'], right_token=b['right'], step=f['step'], gap_W=(b['gap'][1] - b['gap'][0]) / W_px if W_px else None,
                                       left_ix=left_ix, right_ix=right_ix, first_ix=int(np.flatnonzero(ml)[0]), last_ix=int(np.flatnonzero(mr)[-1]), flat=f, recorded=g, tick_x=(ul['rect'][2] + ur['rect'][0]) / 2,
                                       tick_recorded=[min(ul['rect'][1], ur['rect'][1]) - 4, max(ul['rect'][3], ur['rect'][3]) + 4], tick_flat=[min(ul['flat'][1], ur['flat'][1]) - 4, max(ul['flat'][3], ur['flat'][3]) + 4]))
            r['break_kinds'] = ' '.join(kinds) or None
            r['step'] = max(steps, key=abs) if steps else None
            if page['fitted']:
                moved = (yr - yf) / H
                r['warp_mean'], r['warp_range'] = float(np.mean(moved)), float(np.ptp(moved))
                L_warp = pw.rec.get('lines', {}).get(str(L['locus']))
                if L_warp is not None:
                    sx = np.linspace(x[0], x[-1], WARP_SAMPLES)
                    warped, straight = pw.model.curve(sx, str(L['locus']), L_warp['intercept_px'], L_warp['slope_px_per_u'])
                    curves.append(dict(line=l, folio=folio, locus=L['locus'], x=sx, warped=warped, straight=straight, flat=warped - pw.shift(sx, warped, str(L['locus']))))
    stats = dict(lines=lines, words=words, breaks=break_rows, intrusions=[], ink_fits=[], warp_curves=curves, pages=pages, app=given, rec=rec, ms=ms, data=data, baseline=baseline,
                 baseline_pages=data['baseline_pages'], skipped=dict(skipped), n_lines=n_lines, n_tokens=len(rec['words']), rec_tags=tags(rec), version=VERSION, ink_note='no ink product', ink_given=ink)
    _add_ink(stats, word_at, glyph, heights, ink, log, require_same)
    if len(_CACHE) > 3:
        _CACHE.clear()
    _CACHE[key] = stats
    if log:
        log('line stats: %d horizontal lines, %d with a chord, %d with a fit, %d located rectangles, %s' % (
            sum(1 for r in lines if r), sum(1 for r in lines if r and r['chord_flat'] is not None), sum(1 for r in lines if r and r['ls_angle'] is not None), len(words), stats['ink_note']))
    return stats


def _add_ink(stats: dict, word_at: Dict[int, dict], glyph, heights, ink: Optional[dict], log, require_same) -> None:
    """The ink columns of the word and line records, the intrusions and the ink line fits (in both states). The ink
    product is optional data: the box measures stand without it and `ink_note` says why it is missing."""
    from . import paths, warp as W
    from .ink import UNCLEAN, for_bundle, ink_matches, intrusions, line_rows, load_ink, unit_rows
    rec, ms = stats['rec'], stats['ms']
    try:
        product = ink or load_ink()
    except paths.DataMissing as err:
        stats['ink_note'] = 'no ink product (%s)' % err
        return
    ink_b = for_bundle(product, rec)
    if not ink_matches(ink_b, rec):
        stats['ink_note'] = 'the ink product was measured on other words'
        return
    require_same(rec, ink_b, 'the bundle and the ink product')
    lines_ms = ms.lines if hasattr(ms, 'lines') else ms['lines']
    records = unit_rows(ink_b)
    by_first = {r['first']: r for r in records}
    used = 0
    extent: Dict[int, list] = {}
    for r in records:
        w = word_at.get(r['first'])
        if w is None or w['kind'] != 'horizontal' or r['base'] is None or (r['flags'] & UNCLEAN):
            continue
        H = _finite(heights.get(lines_ms[r['line']]['page']))
        if not H:
            continue
        tan_t = math.tan(math.radians(r['angle'] or 0.0))
        xc_box = (w['x0'] + w['x1']) / 2
        at_box = r['base'] + tan_t * (xc_box - r['xc'])                # the ink baseline at the box centre, along the word's own angle
        w['baseline_shift'] = (at_box - w['y1']) / H
        g = glyph[r['first']]
        w['ink_shift'] = (at_box - g[1]) / H if g else None
        w['ink_xheight'] = r['xheight'] / H if r['xheight'] is not None else None
        lo, hi = extent.get(r['line'], (r['x0'], r['x1']))
        extent[r['line']] = (min(lo, r['x0']), max(hi, r['x1']))
        used += 1
    rows = line_rows(ink_b)
    flat_rows = line_rows(W.transform(ink_b, 'flat', app=rec, ms=ms))
    for l, row in rows.items():
        r = stats['lines'][l] if l < len(stats['lines']) else None
        if r is None or row.get('angle') is None or (row.get('n_clean') or 0) < 3:
            continue
        H = r['H_px']
        if not H:
            continue
        r['ink_clean'] = row['n_clean']
        r['reg_dx'], r['reg_dy'] = row.get('shift_dx'), row.get('shift_dy')
        r['xheight'] = row['xheight_med'] / H if row.get('xheight_med') is not None else None
        r['xheight_spread'] = row['xheight_mad'] / H if row.get('xheight_mad') is not None else None
        r['ink_rms'] = row['resid_rms'] / H if row.get('resid_rms') is not None else None
        if row.get('box_ls_angle') is not None:
            r['ink_vs_box_angle'] = row['angle'] - row['box_ls_angle']
        if l in extent:
            x0, x1 = extent[l]
            fr = flat_rows.get(l) or row
            at = lambda q, x: q['intercept'] + math.tan(math.radians(q['angle'])) * (x - q['x_mid'])
            stats['ink_fits'].append(dict(line=l, folio=r['folio'], x=[x0, x1], y=[at(row, x0), at(row, x1)], y_flat=[at(fr, x0), at(fr, x1)]))
    events = []
    depth: Dict[int, float] = {}
    for e in intrusions(rec, ms, ink_b):
        d = float(e['depth_H'])
        if d <= 0:                                                     # near misses (down to -0.05 H) are not intrusions
            continue
        stroke = e['upper_token'] if e['direction'] == 'down' else e['lower_token']
        q = by_first.get(stroke)
        y = (q['desc_y'] if e['direction'] == 'down' else q['asc_y']) if q else None
        if y is None:
            continue
        events.append(dict(e, y=float(y), stroke_token=stroke))
        for t in (e['upper_token'], e['lower_token']):
            depth[t] = max(depth.get(t, 0.0), d)
    for t, d in depth.items():
        if t in word_at:
            word_at[t]['intrusion_depth'] = d
    stats['intrusions'] = events
    for folio, q in (ink_b.get('pages') or {}).items():
        if folio in stats['pages'] and q.get('ok'):
            stats['pages'][folio]['registration'] = dict(method=q.get('method'), n_inliers=q.get('n_inliers'), residual_px=q.get('residual_px'))
    stats['ink_note'] = '%d clean ink records, %d intrusions on %d rectangles' % (used, len(events), len(depth))


# ----------------------------------------------------------------------------- the tables
def _meta(stats: dict, title: str, columns: Sequence[str]) -> dict:
    t = stats['rec_tags']
    return dict(title=title, columns=list(columns), n_rows=None, frame=t['frame'], warp='flat', source=t['source'], recorded_columns='y_recorded, x0, y0, x1, y1, and every column ending in _recorded; ink columns recorded frame, source beinecke',
                baseline=stats['baseline'], baseline_pages=stats['baseline_pages'], policy=stats['rec'].get('policy'), pages=stats['rec'].get('pages'), order=stats['rec'].get('order'), skipped=stats['skipped'],
                ink=stats['ink_note'], version=stats['version'], note='H = page median box height, W = median box width; y grows down the page; signs in vmsspatial.line_stats.')


def line_table(app=None, ms=None, baseline: str = 'auto', ink: Optional[dict] = None, log=None):
    """One record per horizontal line.

    Args:
        app: the bundle (default the sensitivity geometry of the whole manuscript; either warp state).
        ms: its Manuscript (default the bundle's own).
        baseline: the anchor method ('auto' by default, ``baselines.word_baselines``).
        ink: the ink product (default the shipped one).
        log: a print-like callable or None.

    Returns:
        ``compare.Records``: `LINE_COLUMNS` per line (``KEYS`` says what each key means), with ``to_csv(path)``,
        ``to_json(path)``, ``describe()`` and `meta` (frame, warp and source tags, the anchors used, `skipped`: the
        lines of other orientations by kind). None where a line cannot support a value.

    Example:
        >>> lines = line_table()                                                     # doctest: +SKIP
        >>> kept = [r for r in lines if r['n_anchors'] >= 4 and (r['span_W'] or 0) >= 3]   # doctest: +SKIP
        >>> lines.to_csv('lines.csv')                                                # doctest: +SKIP
    """
    from .compare import Records
    st = compute(app, ms, baseline, ink, log)
    rows = [{k: r.get(k) for k in LINE_COLUMNS} for r in st['lines'] if r is not None]
    meta = _meta(st, 'one record per horizontal line', LINE_COLUMNS)
    meta['n_rows'] = len(rows)
    return Records(rows, meta)


def word_table(app=None, ms=None, baseline: str = 'auto', ink: Optional[dict] = None, log=None):
    """One record per located rectangle (a shared box once, its tokens first..last).

    Args:
        app, ms, baseline, ink, log: as for ``line_table``.

    Returns:
        ``compare.Records``: `WORD_COLUMNS` per rectangle: the token range, its word or words, the page, locus, line and
        orientation kind, the recorded rectangle, the anchor in both warp states (`x`, `y_recorded`, `y_flat`, `anchor`:
        the method used, 'box centre' off horizontal lines) and the word measures (``KEYS``), None off horizontal lines.

    Example:
        >>> words = word_table()                                                     # doctest: +SKIP
        >>> below = [w for w in words if (w['resid_chord'] or 0) > 0.2]              # doctest: +SKIP
    """
    from .compare import Records
    st = compute(app, ms, baseline, ink, log)
    meta = _meta(st, 'one record per located rectangle', WORD_COLUMNS)
    meta['n_rows'] = len(st['words'])
    return Records(st['words'], meta)


def token_values(key: str, app=None, ms=None, baseline: str = 'auto', ink: Optional[dict] = None) -> list:
    """The value of a measure on every token of the bundle (None where it has none): a word measure on each token of
    its rectangle, a line measure on each token of its line, a page measure on each token of its page.

    Args:
        key: a key of ``KEYS``.
        app, ms, baseline, ink: as for ``line_table``.

    Returns:
        a list with one number or None per token.

    Example:
        >>> plot.plot_page('f75r', color_by=token_values('sag'))                     # doctest: +SKIP
    """
    if key not in KEYS:
        raise ValueError('unknown measure %r; the keys are in line_stats.KEYS' % (key,))
    return values_of(compute(app, ms, baseline, ink), key)


def values_of(st: dict, key: str) -> list:
    """``token_values`` from a ``compute`` result."""
    out = [None] * st['n_tokens']
    per = KEYS[key]['per']
    if per == 'token':
        for w in st['words']:
            if w[key] is not None:
                for t in range(w['first'], w['last'] + 1):
                    out[t] = w[key]
        return out
    bundle_lines = st['rec']['lines']
    if per == 'line':
        for L, r in zip(bundle_lines, st['lines']):
            if r is not None and r.get(key) is not None:
                for t in range(L['start'], L['end']):
                    out[t] = r[key]
        return out
    for L in bundle_lines:
        v = st['pages'][L['page']][key]
        if v is not None:
            for t in range(L['start'], L['end']):
                out[t] = v
    return out
