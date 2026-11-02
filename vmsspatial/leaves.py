"""The leaves on the parchment: where each page's fold and top edge lie in the recorded frame, and its scale in mm.

The Beinecke scans (``vmsspatial.images``) photograph each page in its binding on a black ground, at one resolution.
The leaf's top and bottom edges, and the line where it meets the binding, show as long straight edges. For each
page this module finds on the scan

* the fold: walking out from the text toward the binding, the first long straight edge of at least 30% of the
  band's strongest, then the strongest within the next 8 mm (the leaf often curves into the gutter as a soft band
  before its edge). The edge where the visible leaf meets the binding stands for the fold: the strip of leaf hidden
  in the binding, if any, is not measured;
* the top and bottom edges: the long straight edge nearest the text above it and below it.

An edge's score is a low percentile (the 35th) of the gradient across it, along the whole span of the text, at the
best angle within 1.5 degrees of the axis, so a drawing that crosses the band does not make one. The scale is set
once for all scans: the median height of the ordinary leaves (no foldout) is the catalogue's 225 mm (Beinecke Rare
Book and Manuscript Library, MS 408: 225 x 160 mm), so a leaf that is taller or shorter than that keeps its own
size. The edges are mapped into the recorded frame through the stored registration (``images.Mapping``).

A value that is missing or implausible is estimated, and says so (``fold_method``, ``top_method``, ``scale_method``):
the fold from the median inner margin of the measured leaves, the top from the bottom edge and the median leaf
height, or from the median top margin; the scale of a page without a registration from the median of the others.
Foldout panels away from the binding are placed by their text. The data product is
``data/manuscript/leaves.json.gz`` (numbers only); the Page stream draws pages on the parchment scale with it
(``scale=paper``). Nothing here writes an image.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import paths

PRODUCT_KEY = 'manuscript/leaves.json.gz'
PRODUCT_VERSION = '2026.11.02.1'
CATALOGUE_MM = dict(height=225.0, width=160.0, source='Beinecke Rare Book and Manuscript Library, catalogue record of MS 408 (225 x 160 mm)')
DOWN = 4                                     # the scan is searched at a quarter of its size
ANGLES = np.deg2rad(np.arange(-1.5, 1.5001, 0.05))
PERCENTILE = 35                              # of the gradient along a candidate edge
FIRST_SHARE = 0.3                            # the first fold candidate out from the text: at least this share of the band's peak
NEAREST_SHARE = 0.45                         # top, bottom, outer edge: the candidate nearest the text of at least this share
MIN_SCORE = 3.0
GAP_MM = 1.5                                 # the band starts this far from the text
REACH_MM = 8.0                               # how far past the first candidate the fold may lie
WIDE_SCAN_PX = 3300                          # a scan wider than this shows a foldout
HEIGHT_TOLERANCE = 0.04                      # a leaf height this far from the median: the top edge is not taken as measured
FOLD_MARGIN_MM = (0.5, 60.0)                 # a measured fold must leave an inner margin in this range
MIN_FOLD_SCORE = 4.0


def _recto(folio: str, side: Optional[str] = None) -> bool:
    if side in ('r', 'v'):
        return side == 'r'
    from .images import FOLIO_RE
    m = FOLIO_RE.match(folio)
    return bool(m and m.group(2) == 'r')


def _smooth_rows(a: np.ndarray, k: int = 3) -> np.ndarray:
    ker = np.ones(k) / k
    return np.apply_along_axis(lambda v: np.convolve(v, ker, mode='same'), 0, a)


def edge_scores(G: np.ndarray, lo: int, hi: int, span0: int, span1: int):
    """G: the gradient magnitude across an edge that runs along axis 0. For each offset lo..hi-1 (axis 1), the best score
    over ANGLES of the PERCENTILE of G along the line through it over rows span0..span1, and that line's slope
    (offset change per row, about the span's centre)."""
    rows = np.arange(span0, span1)
    centre = (span0 + span1) / 2
    cols = np.arange(lo, hi)
    best = np.full(hi - lo, -1.0)
    slope = np.zeros(hi - lo)
    for t in ANGLES:
        X = cols[None, :] + np.round((rows - centre) * math.tan(t)).astype(int)[:, None]
        inside = (X >= 0) & (X < G.shape[1])
        vals = np.where(inside, G[rows[:, None], np.clip(X, 0, G.shape[1] - 1)], 0)
        s = np.percentile(vals, PERCENTILE, axis=0)
        better = s > best
        best[better] = s[better]
        slope[better] = math.tan(t)
    return best, slope


def _maxima(s: np.ndarray) -> List[int]:
    return [i for i in range(1, len(s) - 1) if s[i] >= MIN_SCORE and s[i] >= s[i - 1] and s[i] >= s[i + 1]]


def pick_nearest(score: np.ndarray, text_last: bool) -> Optional[int]:
    """The local maximum nearest the text of at least NEAREST_SHARE of the band's peak (text at the end of `score` when
    text_last)."""
    s = score if text_last else score[::-1]
    if s.max() <= 0:
        return None
    cand = [i for i in _maxima(s) if s[i] >= NEAREST_SHARE * s.max()]
    if not cand:
        return None
    i = max(cand)
    return i if text_last else len(s) - 1 - i


def pick_fold(score: np.ndarray, text_last: bool, reach: int) -> Optional[int]:
    """Out from the text, the first local maximum of at least FIRST_SHARE of the band's peak, then the strongest local
    maximum within `reach` samples beyond it."""
    s = score if text_last else score[::-1]
    if s.max() <= 0:
        return None
    cand = _maxima(s)
    first = [i for i in cand if s[i] >= FIRST_SHARE * s.max()]
    if not first:
        return None
    f = max(first)
    i = max((j for j in cand if f - reach <= j <= f), key=lambda j: s[j])
    return i if text_last else len(s) - 1 - i


def measure_scan(gray: np.ndarray, text, recto: bool, px_per_mm: float = 15.8) -> dict:
    """Edges of one leaf on a scan at a quarter of its size (`gray`, float). `text` = [x0, y0, x1, y1] of the text in
    the same pixels. Returns {fold, outer, top, bottom}: each None or {at (the offset at the text's centre), slope,
    score, peak}, in the given pixels. `px_per_mm` is for the scan at full size."""
    H, W = gray.shape
    tx0, ty0, tx1, ty1 = [int(round(v)) for v in text]
    q = px_per_mm / DOWN
    gap, reach = max(2, int(round(GAP_MM * q))), max(1, int(round(REACH_MM * q)))
    Gx = np.abs(np.diff(_smooth_rows(gray), axis=1, prepend=gray[:, :1]))
    Gy = np.abs(np.diff(_smooth_rows(gray.T).T, axis=0, prepend=gray[:1, :])).T
    sy0, sy1, sx0, sx1 = max(0, ty0), min(H, ty1), max(0, tx0), min(W, tx1)
    out = {}
    for name, G, lo, hi, span, text_last, fold in (
            ('left', Gx, 2, tx0 - gap, (sy0, sy1), True, recto), ('right', Gx, tx1 + gap, W - 2, (sy0, sy1), False, not recto),
            ('top', Gy, 2, ty0 - gap, (sx0, sx1), True, False), ('bottom', Gy, ty1 + gap, H - 2, (sx0, sx1), False, False)):
        lo, hi = max(2, lo), min(G.shape[1] - 2, hi)
        if hi - lo < 3 or span[1] - span[0] < 10:
            out[name] = None
            continue
        sc, sl = edge_scores(G, lo, hi, *span)
        i = pick_fold(sc, text_last, reach) if fold else pick_nearest(sc, text_last)
        out[name] = None if i is None else dict(at=float(lo + i), slope=float(sl[i]), score=float(sc[i]), peak=float(sc.max()), centre=(span[0] + span[1]) / 2)
    return dict(fold=out['left'] if recto else out['right'], outer=out['right'] if recto else out['left'], top=out['top'], bottom=out['bottom'])


def _page_boxes(app, ms) -> Dict[str, List[list]]:
    """{folio: [recorded boxes]}: every located rectangle of every line, whatever its orientation."""
    from .geometry import line_units, _pages
    units = line_units(app, ms, orientations='all')
    out = {}
    for p in _pages(ms):
        out[p['folio']] = [u['box'] for l in range(p['start_line'], p['end_line']) for u in units[l]]
    return out


def _scan_edges(folio: str, boxes, rec: dict, recto: bool) -> Optional[dict]:
    from PIL import Image
    from . import images
    m = images.Mapping(rec)
    B = np.asarray(boxes, float)
    corners = np.concatenate([B[:, [0, 1]], B[:, [2, 1]], B[:, [0, 3]], B[:, [2, 3]]])
    P = m.to_image(corners)
    text = [np.percentile(P[:, 0], 0.5), np.percentile(P[:, 1], 0.5), np.percentile(P[:, 0], 99.5), np.percentile(P[:, 1], 99.5)]
    img = Image.open(images.image_path(folio, 'beinecke', rec.get('image_id'))).convert('L')
    size = img.size
    gray = np.asarray(img.reduce(DOWN), float)
    e = measure_scan(gray, [v / DOWN for v in text], recto)
    full = {}
    for k, v in e.items():
        full[k] = None if v is None else dict(at=v['at'] * DOWN, slope=v['slope'], score=round(v['score'], 2), peak=round(v['peak'], 2), centre=v['centre'] * DOWN)
    return dict(edges=full, text_px=[float(v) for v in text], image_id=rec.get('image_id'), image_size=list(size), mapping=m)


def _r(v, nd=1):
    return None if v is None else round(float(v), nd)


def build(app=None, ms=None, out=None, log=print) -> dict:
    """Measure every page with a registered Beinecke scan in the image cache and write the data product. Returns it."""
    from . import images
    from .bundle import load_bundle, write_json
    from .manuscript import Manuscript
    if ms is None:
        ms = Manuscript.load()
    if app is None:
        app = load_bundle('sensitivity', pages=ms.page_set, order=ms.order, warp='recorded')
    boxes = _page_boxes(app, ms)
    info = {p['folio']: p for p in ms.pages}
    frames = {f: 'detected' for f in (app.get('geometry_provenance') or {}).get('detected_pages') or []}
    raw = {}
    for folio, bs in boxes.items():
        if not bs:
            raw[folio] = dict(reason='no located box')
            continue
        rec = images.registration(folio, 'beinecke')
        if not rec.get('ok'):
            raw[folio] = dict(reason='no registration')
            continue
        try:
            raw[folio] = _scan_edges(folio, bs, rec, _recto(folio, info.get(folio, {}).get('side')))
        except FileNotFoundError:
            raw[folio] = dict(reason='scan not in the image cache')
    # one scale for every scan: the median ordinary leaf height is the catalogue's
    def ordinary(f):
        r = raw[f]
        return 'edges' in r and not info.get(f, {}).get('panel') and r['image_size'][0] < WIDE_SCAN_PX
    heights = [raw[f]['edges']['bottom']['at'] - raw[f]['edges']['top']['at'] for f in raw if ordinary(f) and raw[f]['edges']['top'] and raw[f]['edges']['bottom']]
    median_h = float(np.median(heights))
    ppm = median_h / CATALOGUE_MM['height']
    pages = {}
    for f, r in raw.items():
        side = info.get(f, {}).get('side')
        recto = _recto(f, side)
        B = np.asarray(boxes[f], float) if boxes[f] else None
        tbox = None if B is None else [float(B[:, 0].min()), float(B[:, 1].min()), float(B[:, 2].max()), float(B[:, 3].max())]
        p = dict(side='r' if recto else 'v', panel=info.get(f, {}).get('panel') or '', text=[_r(v) for v in tbox] if tbox else None)
        if 'edges' in r:
            m, e = r['mapping'], r['edges']
            t = r['text_px']
            xc, yc = (t[0] + t[2]) / 2, (t[1] + t[3]) / 2
            rec_c = m.to_frame([[xc, yc]])[0]
            p.update(mm=_r(ppm / m.scale(rec_c[0], rec_c[1]), 4), scale_method='measured', image_id=r['image_id'])

            def at_y(edge, y):                   # a fold or outer edge's x at scan height y
                return edge['at'] + (y - edge['centre']) * edge['slope']

            def at_x(edge, x):
                return edge['at'] + (x - edge['centre']) * edge['slope']
            if e['fold']:
                p['fold'] = _r(m.to_frame([[at_y(e['fold'], yc), yc]])[0][0])
                p['fold_score'] = e['fold']['score']
                p['fold_slope'] = _r(e['fold']['slope'], 5)
            for k in ('top', 'bottom'):
                if e[k]:
                    p[k] = _r(m.to_frame([[xc, at_x(e[k], xc)]])[0][1])
            if e['top'] and e['bottom']:
                p['leaf_height_mm'] = _r((at_x(e['bottom'], xc) - at_x(e['top'], xc)) / ppm)
            if e['fold'] and e['outer']:
                p['visible_width_mm'] = _r(abs(at_y(e['outer'], yc) - at_y(e['fold'], yc)) / ppm)
            p['scan'] = dict(text_px=[_r(v) for v in t], **{k: None if v is None else dict(at=_r(v['at']), slope=_r(v['slope'], 5), score=v['score']) for k, v in e.items()})
        else:
            p['reason'] = r.get('reason')
        pages[f] = p
    # plausibility, and the medians the estimates use
    def margin(p):
        if p.get('fold') is None or not p.get('text'):
            return None
        return ((p['text'][0] - p['fold']) if p['side'] == 'r' else (p['fold'] - p['text'][2])) / p['mm']
    for f, p in pages.items():
        mg = margin(p)
        p['fold_margin_mm'] = _r(mg)
        p['fold_method'] = 'measured' if (mg is not None and FOLD_MARGIN_MM[0] <= mg <= FOLD_MARGIN_MM[1] and (p.get('fold_score') or 0) >= MIN_FOLD_SCORE
                                          and p['panel'] in ('', '1')) else 'estimated'
        h = p.get('leaf_height_mm')
        p['top_method'] = 'measured' if p.get('top') is not None and h is not None and abs(h - CATALOGUE_MM['height']) <= HEIGHT_TOLERANCE * CATALOGUE_MM['height'] else None
    good = [p for f, p in pages.items() if ordinary(f) and p['fold_method'] == 'measured']
    inner = float(np.median([p['fold_margin_mm'] for p in good]))
    tops = [(p['text'][1] - p['top']) / p['mm'] for p in pages.values() if p['top_method'] == 'measured' and p.get('text')]
    top_margin = float(np.median(tops))
    lo_t, hi_t = np.percentile(tops, [2, 98])
    scale = float(np.median([p['mm'] for p in pages.values() if p.get('scale_method') == 'measured']))
    for f, p in pages.items():
        if p.get('mm') is None:                  # a detected frame is the quarter-size scan itself (docs/DATA_MODEL.md)
            p['mm'], p['scale_method'] = _r(ppm / 4 if frames.get(f) == 'detected' else scale, 4), 'estimated'
        if not p.get('text'):
            p['fold_method'] = p['top_method'] = 'none'
            continue
        if p['fold_method'] == 'estimated':
            p['fold'] = _r(p['text'][0] - inner * p['mm'] if p['side'] == 'r' else p['text'][2] + inner * p['mm'])
        if p['top_method'] is None:
            tm = (p['text'][1] - p['top']) / p['mm'] if p.get('top') is not None else None
            if tm is not None and lo_t <= tm <= hi_t:
                p['top_method'] = 'measured'
            elif p.get('bottom') is not None and lo_t <= (p['text'][1] - (p['bottom'] - CATALOGUE_MM['height'] * p['mm'])) / p['mm'] <= hi_t:
                p['top'], p['top_method'] = _r(p['bottom'] - CATALOGUE_MM['height'] * p['mm']), 'bottom'
            else:
                p['top'], p['top_method'] = _r(p['text'][1] - top_margin * p['mm']), 'estimated'
    counts = {k: {m: sum(1 for p in pages.values() if p.get(k) == m) for m in sorted({p.get(k) for p in pages.values()} - {None})} for k in ('fold_method', 'top_method', 'scale_method')}
    prod = dict(version=PRODUCT_VERSION, built=date.today().isoformat(), frame='recorded', source='beinecke', catalogue=CATALOGUE_MM,
                calibration=dict(scan_px_per_mm=round(ppm, 4), median_leaf_height_px=round(median_h, 1), leaves=len(heights)),
                medians=dict(inner_margin_mm=round(inner, 2), top_margin_mm=round(top_margin, 2), recorded_px_per_mm=round(scale, 4)),
                counts=counts, credit=images.CREDIT,
                fields=dict(mm='recorded px per mm on the parchment, at the text centre', fold='recorded x of the fold (the edge where the leaf meets the binding) at the text centre height',
                            top='recorded y of the leaf top edge at the text centre', bottom='recorded y of the leaf bottom edge', text='recorded bounds of the located boxes',
                            fold_method='measured | estimated (median inner margin) | none', top_method='measured | bottom (bottom edge less 225 mm) | estimated (median top margin) | none',
                            scale_method='measured (registration and the scan scale) | estimated (median)', scan='the edges on the scan, full-size px: at = offset at the text centre, slope per px along the edge'),
                note='Estimated from the Beinecke scans: the visible edge where a leaf meets the binding stands for the fold, and the scale is set by the catalogue leaf height (docs/STREAM.md).',
                pages=pages)
    out = Path(out) if out else paths.data_dir() / PRODUCT_KEY
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(prod, out)
    _PRODUCT.clear()
    if log:
        log('wrote %s: %d pages; scan %.2f px/mm; folds %s; tops %s; median inner margin %.1f mm' % (out, len(pages), ppm, counts['fold_method'], counts['top_method'], inner))
    return prod


_PRODUCT = {}


def load_leaves(path=None) -> Optional[dict]:
    """The shipped product (PRODUCT_KEY), read once; None when it is absent."""
    key = str(path) if path else ''
    if key not in _PRODUCT:
        p = Path(path) if path else paths.resolve(PRODUCT_KEY, required=False)
        if p is None or not Path(p).is_file():
            _PRODUCT[key] = None
        else:
            from .bundle import read_json
            _PRODUCT[key] = read_json(p)
    return _PRODUCT[key]


def for_viewer(prod: Optional[dict], folio: str) -> Optional[dict]:
    """The few numbers the Page stream needs for one page: {mm, fold, top, fold_method, top_method, scale_method}."""
    p = (prod or {}).get('pages', {}).get(folio)
    if not p or p.get('fold') is None or p.get('top') is None:
        return None
    return dict(mm=p['mm'], fold=p['fold'], top=p['top'], fold_method=p['fold_method'], top_method=p['top_method'], scale_method=p['scale_method'])
