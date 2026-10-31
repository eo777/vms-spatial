"""The page warp as a data product, and the one entry point for moving coordinates between the two warp states.

``vmsspatial.flatten`` FITS a page's shared photographic warp (binding curvature, camera tilt, keystone) from its
text lines. Until now every consumer refitted it, with whichever baseline it chose, so "flattened" was not one
thing and nothing stopped a study from removing the warp twice or keeping it by mistake. This module stores ONE fit
per page as the shipped data product ``data/manuscript/page_warp.json.gz`` and applies it:

    warp.apply(folio, x, y, line, to='flat' | 'recorded')     move y coordinates of one page (line = the ZL locus)
    warp.transform(table, to='flat')                          move a whole tagged table and flip its `warp` tag:
                                                              a bundle, a baselines table, the ink product
    warp.flatten_bundle(app)                                  the bundle in the flat warp state (what consumers call;
                                                              load_bundle(policy, warp='flat') does the same)
    warp.build(app, ms, ink)                                  refit every page and write the product (the fitter is
                                                              flatten.flatten; this chooses the baseline per page)

The product holds, per page: the field basis and its normalisation (x_mid, half_w, y_mid, half_h, degree, v_terms),
the full-fit coefficients, the per-line leave-one-out coefficients and coverage interval (by locus), the tilt line,
the reference shift, the baseline the page was fitted on ('ink' where the page has clean ink records in the ink
product, 'glyph' otherwise; recorded in `baseline`), and the quality (fitted, n_lines, n_points, curvature
amplitude, tilt, keystone, rms before and after). Pages that could not be fitted are listed with the reason and are
left as recorded. The shift of a rectangle is read at its centre x and bottom y with its line's leave-one-out field;
a line the fit did not use (too few rectangles, or not horizontal) takes the full-fit field at its own height. That is
exactly what ``flatten.flatten`` does, so ``flatten_bundle(load_bundle('sensitivity'))`` reproduces
``flatten(app, ms, baseline=<the product's per-page choice>)`` to floating-point rounding (tests/test_warp.py).

Tags (``vmsspatial.frames``): the product applies to tables in the recorded frame and the recorded warp state and
produces the flat state; ``transform`` refuses a table that is already in the target state.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from . import paths
from .bundle import digest, read_json, write_json
from .frames import FrameError, tags, tag

PRODUCT_KEY = 'manuscript/page_warp.json.gz'
VERSION = '2026.10.30.1'
CLEAN_SHARE = 0.5           # a page uses the ink baseline when at least this share of its measured rectangles is clean
MIN_CLEAN = 40              # ... and it has at least this many clean records
INVERSE_STEPS = 8           # fixed-point steps of the flat -> recorded inverse for lines the fit did not use

_PRODUCT = {}


# ----------------------------------------------------------------------------- the product
def load_warp(path=None, reload: bool = False) -> dict:
    """The page warp product (``PRODUCT_KEY``), read once."""
    key = str(path) if path else ''
    if reload or key not in _PRODUCT:
        _PRODUCT[key] = read_json(path or paths.resolve(PRODUCT_KEY))
    return _PRODUCT[key]


def ink_pages(ink: dict, share: float = CLEAN_SHARE, min_clean: int = MIN_CLEAN) -> set:
    """The pages whose ink records are clean enough to fit the warp on the ink baseline."""
    out = set()
    for folio, s in (ink.get('pages') or {}).items():
        if s.get('ok') and (s.get('n_clean') or 0) >= min_clean and (s.get('n_clean') or 0) >= share * max(1, s.get('n_units') or 0):
            out.add(folio)
    return out


def baseline_choice(app, ms, ink: Optional[dict]) -> Dict[str, str]:
    """Per folio: 'ink' where the ink product was measured on this bundle's words and the page has clean records,
    'glyph' otherwise."""
    pages = ms.pages if hasattr(ms, 'pages') else ms['pages']
    good = set()
    if ink is not None:
        from .ink import ink_matches, for_bundle
        ink = for_bundle(ink, app)
        if ink_matches(ink, app):
            good = ink_pages(ink)
    return {p['folio']: ('ink' if p['folio'] in good else 'glyph') for p in pages}


def page_status(folio: str, product: Optional[dict] = None) -> dict:
    """What the stored warp does on a page: {folio, fitted, reason, baseline, n_lines, moved ('horizontal lines' |
    'nothing'), line_kinds, quality}. A page the product does not know reports fitted False with the reason
    'not in the page warp product'."""
    prod = product or load_warp()
    rec = prod['pages'].get(folio)
    if rec is None:
        return dict(folio=folio, fitted=False, reason='not in the page warp product', baseline=None, n_lines=0, moved='nothing', line_kinds={}, quality={})
    return dict(folio=folio, fitted=bool(rec.get('fitted')), reason=rec.get('reason', ''), baseline=rec.get('baseline'), n_lines=rec.get('n_lines', 0),
                moved='horizontal lines' if rec.get('fitted') else 'nothing', line_kinds=rec.get('line_kinds') or {}, quality=rec.get('quality') or {})


def _page_record(rep: dict, lines: Sequence[dict]) -> dict:
    """The product's page record from a flatten page report (coefficients keyed by locus)."""
    out = dict(fitted=bool(rep.get('fitted')), reason=rep.get('reason', ''), baseline=rep.get('baseline'), n_lines=rep.get('n_lines', 0), n_points=rep.get('n_points', 0),
               H_px=rep.get('H_px'), expected_gutter=rep.get('expected_gutter'), line_kinds=rep.get('line_kinds') or {})
    if not rep.get('fitted'):
        return out
    c = rep['coefficients']
    out.update(degree=rep['degree_used'], v_terms=bool(rep['v_terms']), x_mid=rep['x_mid'], half_w=rep['half_width_px'], y_mid=rep['y_mid'], half_h=rep['half_height_px'],
               coef=list(c['field']), terms=list(c['field_terms']), tilt=list(c['tilt']), reference_px=rep['reference_px'],
               lines={(L.get('locus') or lines[int(k)]['locus']): dict(v=L['v'], field_loo=list(L['field_loo']), cover_loo=list(L['cover_loo']), intercept_px=L['intercept_px'],
                                                                     slope_px_per_u=L['slope_px_per_u'], slope_deg=L['slope_deg'], n=L['n']) for k, L in c['lines'].items()},
               quality={k: rep.get(k) for k in ('tilt_deg', 'keystone_deg_per_H', 'keystone_deg_text_height', 'curvature_pp_H', 'curvature_pp_px', 'curvature_pp_core_H', 'core_u_range',
                                                 'gutter_side', 'rms_before_H', 'rms_after_H', 'robust_weight_mean')})
    return out


def build(app, ms=None, ink: Optional[dict] = None, out=None, degree: int = 3, min_lines: int = 4, min_words: int = 3, robust: bool = True, loo: bool = True,
          effects: Optional[dict] = None, log=print) -> dict:
    """Fit every page of the bundle (the sensitivity bundle in the recorded warp state, every page and locus) with
    ``flatten.flatten`` on the per-page baseline of ``baseline_choice`` and write the product. Returns the product."""
    from .flatten import flatten
    from .frames import require_warp
    if ms is None:
        from .bundle import manuscript_of
        ms = manuscript_of(app)
    require_warp(app, 'recorded', 'the bundle the page warp is fitted on')
    if ink is None:
        try:
            from .ink import load_ink
            ink = load_ink()
        except paths.DataMissing:
            ink = None
    if ink is not None:
        from .ink import for_bundle
        ink = for_bundle(ink, app)
    choice = baseline_choice(app, ms, ink)
    flat, report = flatten(app, ms, degree=degree, min_lines=min_lines, min_words=min_words, robust=robust, loo=loo, baseline=choice, effects=effects, ink=ink)
    pages = {folio: _page_record(rep, app['lines']) for folio, rep in report['pages'].items()}
    prod = dict(version=VERSION, built=date.today().isoformat(), frame='recorded', warp='recorded', source='voynichese', produces='flat',
                policy=app.get('policy'), words_sha256=digest(app['words']), geometry_sha256=digest(app['geometry']),
                parameters=dict(report['parameters'], baseline='per page: ink where the page has clean ink records, else glyph'),
                baseline_rule='ink where the ink product (version %s) was measured on these words and the page has at least %d clean records and %.0f%% of its records clean; glyph otherwise'
                              % (ink.get('version') if ink else None, MIN_CLEAN, 100 * CLEAN_SHARE),
                baseline_counts=dict(Counter(p['baseline'] for p in pages.values() if p['fitted'])),
                note='One shared polynomial warp field per page (vmsspatial.flatten: per-line intercept and slope projected out, Huber weights, leave-one-line-out), '
                     'fitted on the horizontal lines; apply with vmsspatial.warp (y_flat = y - shift(x, y, locus)). A page-wide slant written by the scribe cannot be told from the camera rotation.',
                skipped_lines=report.get('skipped'), pages=pages, summary=report['summary'])
    out = out or (paths.data_dir() / PRODUCT_KEY)
    write_json(prod, out)
    _PRODUCT.clear()
    if log:
        s = report['summary']
        log('wrote %s (%.2f MB): %d pages, %d fitted (%s), median curvature %.3f H, median |tilt| %.2f deg'
            % (out, out.stat().st_size / 2 ** 20 if hasattr(out, 'stat') else 0.0, s['pages'], s['fitted'], ', '.join('%s %d' % kv for kv in sorted(prod['baseline_counts'].items())),
               s['median_curvature_pp_H'] or float('nan'), s['median_abs_tilt_deg'] or float('nan')))
    return prod


# ----------------------------------------------------------------------------- applying it
class PageWarp:
    """The stored warp of one page: ``shift(x, y, loci)`` in pixels (positive = the rectangle moves up when flattened)."""

    def __init__(self, folio: str, rec: dict):
        from .flatten import _PageModel
        self.folio = folio
        self.rec = rec
        self.fitted = bool(rec.get('fitted'))
        self.model = None
        if self.fitted:
            L = rec['lines']
            self.model = _PageModel(rec['x_mid'], rec['half_w'], rec['y_mid'], rec['half_h'], rec['degree'], rec['v_terms'], rec['coef'],
                                    {k: v['field_loo'] for k, v in L.items()}, {k: v['v'] for k, v in L.items()}, rec['tilt'][0], rec['tilt'][1],
                                    {k: v['cover_loo'] for k, v in L.items()})
            self.model.ref = float(rec['reference_px'])

    def shift(self, x, y, loci) -> np.ndarray:
        x = np.asarray(x, float).ravel()
        y = np.asarray(y, float).ravel()
        if isinstance(loci, (str, int)):
            loci = [str(loci)] * len(x)
        loci = [str(l) for l in loci]
        if not self.fitted or not len(x):
            return np.zeros(len(x))
        return self.model.shift(x, y, loci)


def page_warp(folio: str, product: Optional[dict] = None) -> PageWarp:
    prod = product or load_warp()
    rec = prod['pages'].get(folio)
    if rec is None:
        raise KeyError('%s is not in the page warp product' % folio)
    return PageWarp(folio, rec)


def apply(folio: str, x, y, line, to: str = 'flat', product: Optional[dict] = None, iterations: int = INVERSE_STEPS):
    """Move y coordinates of points (x, y) on `folio` (line = the ZL locus of each point, one value or a sequence)
    from the recorded to the flat warp state (`to='flat'`: y - shift) or back (`to='recorded'`: y + shift, the shift
    re-read at the recovered recorded y for lines the fit did not use, a few fixed-point steps). Returns an array
    (a float for a single point)."""
    if to not in ('flat', 'recorded'):
        raise ValueError("to must be 'flat' or 'recorded'")
    pw = page_warp(folio, product)
    xs = np.asarray(x, float).ravel()
    ys = np.asarray(y, float).ravel()
    scalar = np.ndim(y) == 0
    if to == 'flat':
        out = ys - pw.shift(xs, ys, line)
    else:
        rec = ys.copy()
        for _ in range(max(1, iterations)):
            rec = ys + pw.shift(xs, rec, line)
        out = rec
    return float(out[0]) if scalar else out


def _kind(table) -> str:
    if 'words' in table and 'lines' in table and 'geometry' in table:
        return 'bundle'
    if 'methods' in table and 'x' in table and 'lines' in table:
        return 'baselines'
    if 'units' in table and 'lines' in table and isinstance(table.get('units'), dict) and 'base' in table['units']:
        return 'ink'
    raise FrameError('warp.transform does not know this table (a bundle, a baselines table or the ink product)')


def transform(table: dict, to: str = 'flat', product: Optional[dict] = None, ms=None, app=None) -> dict:
    """A copy of a tagged table with every vertical coordinate moved to the other warp state and its `warp` tag
    flipped: a bundle (geometry and the review's geometry lists), a baselines table (every method's y) or the ink
    product (base, mean, ascender, descender and box bottom of every record; the line fits redone). The table must be
    in the recorded frame and not already in the target state."""
    if to not in ('flat', 'recorded'):
        raise ValueError("to must be 'flat' or 'recorded'")
    t = tags(table)
    if t['frame'] != 'recorded':
        raise FrameError('warp.transform works in the recorded frame; this table is in the %s frame' % t['frame'])
    if t['warp'] == to:
        raise FrameError('this table is already in the %s warp state (frame %s, source %s); nothing to transform' % (to, t['frame'], t['source']))
    prod = product or load_warp()
    kind = _kind(table)
    if kind == 'bundle':
        return _transform_bundle(table, to, prod)
    if kind == 'baselines':
        return _transform_baselines(table, to, prod)
    return _transform_ink(table, to, prod, ms, app)


def _moves(rec: dict, locus) -> bool:
    """Whether the stored warp moves the rectangles of a line: only the page's horizontal lines (the fit cannot be
    checked on rotated, circular or radial text, which keeps its recorded position in the flat state)."""
    kinds = rec.get('line_kinds') or {}
    return kinds.get(str(locus), 'horizontal') == 'horizontal'


def _shift_boxes(geometry, lines, to, prod):
    """New geometry list: every located rectangle of a horizontal line moved by its page's warp (top and bottom alike)."""
    out = list(geometry)
    by_page = {}
    for L in lines:
        by_page.setdefault(L['page'], []).append(L)
    for folio, Ls in by_page.items():
        rec = prod['pages'].get(folio)
        if not rec or not rec.get('fitted'):
            continue
        pw = PageWarp(folio, rec)
        idx, xs, ys, loci = [], [], [], []
        for L in Ls:
            if not _moves(rec, L['locus']):
                continue
            for i in range(L['start'], L['end']):
                b = geometry[i]
                if b:
                    idx.append(i)
                    xs.append((b[0] + b[2]) / 2)
                    ys.append(b[3])
                    loci.append(str(L['locus']))
        if not idx:
            continue
        xs, ys = np.array(xs), np.array(ys)
        if to == 'flat':
            sh = pw.shift(xs, ys, loci)
        else:
            rec_y = ys.copy()
            for _ in range(INVERSE_STEPS):
                rec_y = ys + pw.shift(xs, rec_y, loci)
            sh = -(rec_y - ys)
        for i, s in zip(idx, sh):
            b = geometry[i]
            out[i] = [float(b[0]), float(b[1] - s), float(b[2]), float(b[3] - s)]
    return out


def _transform_bundle(app: dict, to: str, prod: dict) -> dict:
    new_geometry = _shift_boxes(app['geometry'], app['lines'], to, prod)
    out = dict(app, geometry=new_geometry)
    review = app.get('spatialReview')
    if review:
        out['spatialReview'] = dict(review, geometry=_shift_boxes(review['geometry'], app['lines'], to, prod),
                                    sensitivityGeometry=_shift_boxes(review['sensitivityGeometry'], app['lines'], to, prod))
    prov = dict(app.get('geometry_provenance') or {})
    prov.update(derived='flattened' if to == 'flat' else 'unflattened', parent_geometry_kind=app.get('geometry_kind'), parent_geometry_sha256=digest(app['geometry']),
                page_warp_version=prod.get('version'), page_warp_sha256=prod.get('geometry_sha256'), flatten_parameters=prod.get('parameters'), geometry_sha256=digest(new_geometry))
    out['geometry_provenance'] = prov
    out['geometry_kind'] = 'flattened' if to == 'flat' else 'recorded'
    tag(out, warp=to)
    out['lines'] = [dict(L) for L in app['lines']]
    return out


def _transform_baselines(table: dict, to: str, prod: dict) -> dict:
    """Every method's y moves by the shift of the token's rectangle, read at the box centre and bottom (the table's
    `bottom`; the baseline y itself when a table lacks it), as the bundle's rectangles move."""
    out = dict(table, methods={m: dict(v) for m, v in table['methods'].items()})
    x = table['x']
    bottom = table.get('bottom')
    new_bottom = list(bottom) if bottom else None
    for L in table['lines']:
        rec = prod['pages'].get(L['page'])
        if not rec or not rec.get('fitted') or not _moves(rec, L['locus']):
            continue
        pw = PageWarp(L['page'], rec)
        idx = [i for i in range(L['start'], L['end']) if x[i] is not None and (bottom[i] is not None if bottom else any(v['y'][i] is not None for v in out['methods'].values()))]
        if not idx:
            continue
        xs = np.array([x[i] for i in idx], float)
        ref = np.array([bottom[i] if bottom else next(v['y'][i] for v in out['methods'].values() if v['y'][i] is not None) for i in idx], float)
        if to == 'flat':
            sh = pw.shift(xs, ref, str(L['locus']))
        else:
            rec_y = ref.copy()
            for _ in range(INVERSE_STEPS):
                rec_y = ref + pw.shift(xs, rec_y, str(L['locus']))
            sh = -(rec_y - ref)
        for m, v in out['methods'].items():
            new_y = list(v['y'])
            for i, s in zip(idx, sh):
                if new_y[i] is not None:
                    new_y[i] = float(new_y[i] - s)
            v['y'] = new_y
        if new_bottom:
            for i, s in zip(idx, sh):
                new_bottom[i] = float(new_bottom[i] - s)
    if new_bottom:
        out['bottom'] = new_bottom
    tag(out, warp=to)
    out['warp_version'] = prod.get('version')
    return out


def _transform_ink(ink: dict, to: str, prod: dict, ms=None, app=None) -> dict:
    """Every vertical value of every record moved by the shift of its rectangle (read at the rectangle's centre and
    bottom, with its line's locus), the line fits redone on the moved clean baselines."""
    from .ink import refit_lines, for_bundle
    if app is None:
        from .bundle import load_bundle
        app = load_bundle(ink.get('policy') or 'sensitivity', pages=ink['bundle_pages'], order=ink['bundle_order'], warp='recorded', orientation=False)
    if ms is None:
        from .bundle import manuscript_of
        ms = manuscript_of(app)
    ink = for_bundle(ink, app)
    if digest(app['words']) != ink.get('words_sha256'):
        raise FrameError('the ink product was measured on other words than this bundle')
    lines_ms = ms.lines if hasattr(ms, 'lines') else ms['lines']
    out = dict(ink, units={k: list(v) for k, v in ink['units'].items()})
    U = out['units']
    n = len(U['first'])
    by_page = {}
    for i in range(n):
        L = lines_ms[U['line'][i]]
        by_page.setdefault(L['folio'], []).append(i)
    moved = 0
    for folio, idx in by_page.items():
        rec = prod['pages'].get(folio)
        if not rec or not rec.get('fitted'):
            continue
        idx = [i for i in idx if _moves(rec, lines_ms[U['line'][i]]['locus'])]
        if not idx:
            continue
        pw = PageWarp(folio, rec)
        xs = np.array([(app['geometry'][U['first'][i]][0] + app['geometry'][U['first'][i]][2]) / 2 if app['geometry'][U['first'][i]] else U['xc'][i] or 0.0 for i in idx], float)
        ys = np.array([U['box_bottom'][i] for i in idx], float)
        loci = [str(lines_ms[U['line'][i]]['locus']) for i in idx]
        if to == 'flat':
            sh = pw.shift(xs, ys, loci)
        else:
            rec_y = ys.copy()
            for _ in range(INVERSE_STEPS):
                rec_y = ys + pw.shift(xs, rec_y, loci)
            sh = -(rec_y - ys)
        for i, s in zip(idx, sh):
            if s:
                moved += 1
            for f in ('base', 'mean', 'asc_y', 'desc_y', 'box_bottom'):
                if U[f][i] is not None:
                    U[f][i] = round(float(U[f][i] - s), 2)
    out['lines'] = refit_lines(out)
    out['frame_note'] = 'vertical values moved to the %s warp state by vmsspatial.warp (%d of %d records on fitted pages)' % (to, moved, n)
    tag(out, warp=to)
    out['warp_version'] = prod.get('version')
    return out


def flatten_bundle(app: dict, product: Optional[dict] = None) -> dict:
    """The bundle in the flat warp state through the stored page warp (``transform(app, 'flat')``), carrying the
    product's per-page quality under ``flatten`` as the refitting ``flatten.flatten`` did (parameters, summary,
    pages: fitted, reason, baseline, quality)."""
    prod = product or load_warp()
    out = transform(app, 'flat', prod)
    out['flatten'] = dict(parameters=prod['parameters'], summary=prod['summary'], version=prod['version'],
                          pages={f: dict(folio=f, fitted=p['fitted'], reason=p['reason'], baseline=p.get('baseline'), n_lines=p['n_lines'], n_points=p['n_points'],
                                         H_px=p.get('H_px'), expected_gutter=p.get('expected_gutter'), **(p.get('quality') or {})) for f, p in prod['pages'].items()})
    # per page of THIS bundle: whether its rectangles were moved
    out['warp_pages'] = {}
    for page in sorted({L['page'] for L in app['lines']}):
        st = page_status(page, prod)
        out['warp_pages'][page] = 'flat' if st['fitted'] else 'recorded (%s)' % st['reason']
    return out


def page_table(product: Optional[dict] = None) -> List[dict]:
    """The product's pages as flat rows (for a CSV)."""
    prod = product or load_warp()
    rows = []
    for f, p in prod['pages'].items():
        r = dict(folio=f, fitted=p['fitted'], reason=p['reason'], baseline=p.get('baseline'), n_lines=p['n_lines'], n_points=p['n_points'], H_px=p.get('H_px'))
        r.update(p.get('quality') or {})
        rows.append(r)
    return rows
