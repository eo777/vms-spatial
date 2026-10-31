"""Flattening: remove the photographic warp that a page's text lines share.

The method is a robust, leave-one-line-out polynomial warp model with per-line fixed effects: a description, not an
established name. docs/DEWARPING.md gives the model, its named parts, its parameters and its limits.

The word rectangles were drawn on photographs of a bound book. A curvature shared across a page bows every line the
same way at the same horizontal position, and the
camera adds a page-wide tilt and a little keystone (the slope changing from the top of the page to the bottom). In the
recorded coordinates the scribe's drift and the photograph's warp are mixed. ``flatten`` estimates the warp of each
page from its text lines and removes it, so that a line statistic measured afterwards reads the writing rather than
the photograph.

Model per page, on the baseline points (``baseline``, by default 'auto': the ink baseline where the page has clean ink
records, the glyph-corrected box baseline otherwise) of the located, non-oversized
rectangles (``geometry.line_units``: a shared rectangle counts once) of the lines with at least ``min_words`` of them;
u and v are the position inside the page's text block, -1..1 from its extent:

    y = a_l + b_l u + W(u, v_l),        W(u, v) = sum over k = 2..degree of (w_k0 + w_k1 v) u^k

one intercept and one slope per line l, and one smooth field W shared by every line of the page. The per-line terms
absorb everything linear within a line, so W carries only the curvature that lines at the same horizontal position
share. The fit is linear least squares after projecting the per-line [1, u] out of y and of every basis column
(Frisch-Waugh), reweighted with Huber weights (scale 1.4826 x MAD, 5 iterations) when ``robust``. With fewer than 8
usable lines the v-dependent terms are dropped (of the field and of the tilt line below). With fewer than ``min_lines``
usable lines the page is left as recorded (``fitted = False``).

Tilt and keystone: a robust straight line s(v) = c0 + c1 v through the fitted per-line slopes, weighted by the lines'
point counts; s(v_l) is the slope the page's lines share at the height of line l. Every located rectangle on the page
is then moved vertically by -(W(u, v_l) + s(v_l) u), referenced so that the mean shift over the page's points is zero
(the page does not move as a whole); top and bottom move together, so widths and heights are unchanged. With ``loo``
the field W for a line comes from a fit that leaves that line out, so a line that genuinely bows is not flattened by
its own data (the tilt line uses every line). A line's leave-one-out field is read at the edge of the horizontal range
the other lines cover, never extrapolated beyond it (a line that alone reaches into the margin keeps its own shape
there); outside the text block the field is read at its edge value. The report gives the field's amplitude across the
whole text block and across its core (the range at least half of the fitted lines reach).

Identifiability. A page-wide constant slant written by the scribe cannot be told from the camera's rotation, and a
curvature shared by every line of a page cannot be told from binding: flattening removes both. What survives is each
line's deviation from the page's shared slope and, thanks to leave-one-out, each line's own bowing. Whether the shared
curvature IS binding is a separate, physical check: on fitted pages with a clear amplitude its stronger side would be
the gutter side of the folio (``gutter_side`` against ``expected_gutter``). It is not: that holds on about half of the
pages. Say when a number comes from flattened
geometry (``geometry_kind = 'flattened'``, PITFALLS 16).

    flat, report = flatten(load_bundle('sensitivity'), ms)
    report['summary'], report['pages']['f75r']       # the same report travels in flat['flatten']

``flatten`` is the FITTER. Consumers take the stored fit instead: ``vmsspatial.warp.flatten_bundle(app)`` or
``load_bundle(policy, warp='flat')`` apply the shipped page warp product (data/manuscript/page_warp.json.gz, built by
``warp.build`` with this function), so that every study removes the same warp once (docs/DATA_MODEL.md). Lines whose
orientation is not horizontal (``vmsspatial.orientation``) do not enter a page's fit (``orientations``) and are not
moved by it either: a warp fitted on a page's horizontal text cannot be checked on its rings or rotated blocks, so
those rectangles keep their recorded positions in the flat state and the report lists them (``line_kinds``).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np

from .baselines import METHODS as BASELINE_METHODS, word_baselines
from .bundle import digest
from .frames import require_warp, tag
from .geometry import _lines, _pages, line_units

HUBER_C = 1.345
MAD_SCALE = 1.4826
IRLS_ITERATIONS = 5
FEW_LINES = 8                 # below this many usable lines the v-dependent terms are dropped
AMPLITUDE_H = 0.1             # a page's shared curvature counts as clear above this peak-to-peak amplitude (in H)
SMALL = 20                    # no share on fewer pages
PARAMETERS = ('degree', 'min_lines', 'min_words', 'robust', 'loo')


# ----------------------------------------------------------------------------- numerics
def _basis(u, v, degree, v_terms):
    """Columns [u^2, v u^2, u^3, v u^3, ...] (or without the v columns) for k = 2..degree."""
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    cols = []
    for k in range(2, degree + 1):
        cols.append(u ** k)
        if v_terms:
            cols.append(v * u ** k)
    return np.column_stack(cols) if cols else np.zeros((len(u), 0))


def basis_terms(degree, v_terms) -> List[str]:
    out = []
    for k in range(2, degree + 1):
        out.append('u^%d' % k)
        if v_terms:
            out.append('v u^%d' % k)
    return out


def _line_params(u, z, w, line, n_lines):
    """Weighted least squares of z on [1, u] within every line at once (group sums). Returns (intercepts, slopes)."""
    S0 = np.bincount(line, w, n_lines)
    S1 = np.bincount(line, w * u, n_lines)
    S2 = np.bincount(line, w * u * u, n_lines)
    T0 = np.bincount(line, w * z, n_lines)
    T1 = np.bincount(line, w * u * z, n_lines)
    det = S0 * S2 - S1 * S1
    ok = det > 1e-12 * max(1.0, float(S2.max()) if len(S2) else 1.0)
    slope = np.where(ok, (S0 * T1 - S1 * T0) / np.where(ok, det, 1.0), 0.0)
    has = S0 > 0
    icpt = np.where(has, (T0 - slope * S1) / np.where(has, S0, 1.0), 0.0)
    return icpt, slope


def _project_out(u, Z, w, line, n_lines):
    """Residuals of every column of Z after the weighted fit of the per-line [1, u] (the Frisch-Waugh step)."""
    out = np.empty_like(Z)
    for j in range(Z.shape[1]):
        a, b = _line_params(u, Z[:, j], w, line, n_lines)
        out[:, j] = Z[:, j] - (a[line] + b[line] * u)
    return out


def _robust_scale(r):
    med = np.median(r)
    return MAD_SCALE * float(np.median(np.abs(r - med)))


def _huber(r, scale):
    return np.minimum(1.0, HUBER_C * scale / np.maximum(np.abs(r), 1e-12))


def _fit_page(u, y, B, line, n_lines, robust, w0=None):
    """Joint fit of the shared field and the per-line lines, with base weights w0 (the baseline points' precisions)
    times Huber weights. Returns (field coefficients, intercepts, slopes, weights, per-line normal-equation parts for
    leave-one-out)."""
    n, m = B.shape
    w0 = np.ones(n) if w0 is None else np.asarray(w0, float) / np.mean(w0)
    w = w0.copy()
    coef = np.zeros(m)
    for it in range(IRLS_ITERATIONS + 1):
        yt = _project_out(u, y[:, None], w, line, n_lines)[:, 0]
        Bt = _project_out(u, B, w, line, n_lines)
        if m:
            sw = np.sqrt(w)
            coef, *_ = np.linalg.lstsq(Bt * sw[:, None], yt * sw, rcond=None)
        a, b = _line_params(u, y - B @ coef, w, line, n_lines)
        r = y - (a[line] + b[line] * u + B @ coef)
        if not robust or it == IRLS_ITERATIONS:
            break
        scale = _robust_scale(r * np.sqrt(w0))
        if scale <= 1e-9:
            break
        w = w0 * _huber(r * np.sqrt(w0), scale)
    # per-line parts of the normal equations G w = h (the projections are per line, so dropping a line drops its rows)
    G = np.zeros((n_lines, m, m))
    h = np.zeros((n_lines, m))
    for j in range(m):
        h[:, j] = np.bincount(line, w * Bt[:, j] * yt, n_lines)
        for k in range(j, m):
            G[:, j, k] = G[:, k, j] = np.bincount(line, w * Bt[:, j] * Bt[:, k], n_lines)
    return coef, a, b, w, G, h


def _loo_coefficients(coef, G, h):
    """Field coefficients with each line left out, from the full normal equations minus the line's part."""
    n_lines, m = h.shape
    if m == 0:
        return np.zeros((n_lines, 0))
    Gt, ht = G.sum(0), h.sum(0)
    out = np.empty((n_lines, m))
    for l in range(n_lines):
        out[l], *_ = np.linalg.lstsq(Gt - G[l], ht - h[l], rcond=None)
    return out


def _robust_line(x, y, w0, robust):
    """c0 + c1 x through (x, y) with base weights w0, Huber-reweighted when robust. Returns (c0, c1)."""
    x, y, w0 = np.asarray(x, float), np.asarray(y, float), np.asarray(w0, float)
    w = w0.copy()
    c = np.zeros(2)
    for it in range(IRLS_ITERATIONS + 1):
        sw = np.sqrt(w)
        A = np.column_stack([np.ones(len(x)), x]) * sw[:, None]
        c, *_ = np.linalg.lstsq(A, y * sw, rcond=None)
        r = y - (c[0] + c[1] * x)
        if not robust or it == IRLS_ITERATIONS:
            break
        scale = _robust_scale(r)
        if scale <= 1e-12:
            break
        w = w0 * _huber(r, scale)
    return float(c[0]), float(c[1])


def _weighted_mean(x, w):
    w = np.asarray(w, float)
    return float(np.sum(w * np.asarray(x, float)) / np.sum(w)) if np.sum(w) > 0 else float(np.mean(x))


def expected_gutter(folio: str, side: Optional[str] = None) -> Optional[str]:
    """'left' for a recto, 'right' for a verso (the side field of the physical map, or the folio name)."""
    s = (side or '').lower()
    if not s:
        m = re.match(r'^f\d+([rv])', str(folio or ''))
        s = m.group(1) if m else ''
    return {'r': 'left', 'v': 'right'}.get(s)


# ----------------------------------------------------------------------------- the page model
class _PageModel:
    """The fitted warp of one page, able to shift any rectangle on the page."""

    def __init__(self, x_mid, half_w, y_mid, half_h, degree, v_terms, coef, coef_loo, v_line, c0, c1, cover_loo=None):
        """Lines are keyed as the caller keys them (bundle line indices in ``flatten``, loci in ``vmsspatial.warp``)."""
        self.x_mid, self.half_w, self.y_mid, self.half_h = x_mid, half_w, y_mid, half_h
        self.degree, self.v_terms = degree, v_terms
        self.coef = np.asarray(coef, float)
        self.coef_loo = {l: np.asarray(c, float) for l, c in coef_loo.items()}      # line -> field without that line
        self.v_line = {l: float(v) for l, v in v_line.items()}                    # line -> its v
        self.cover_loo = {l: (float(c[0]), float(c[1])) for l, c in (cover_loo or {}).items()}   # line -> u range the other lines cover
        self.c0, self.c1 = float(c0), float(c1)
        self.ref = 0.0

    def u(self, x):
        return (np.asarray(x, float) - self.x_mid) / self.half_w

    def v_of(self, lines, y):
        y = np.asarray(y, float)
        return np.array([self.v_line.get(l, (yy - self.y_mid) / self.half_h) for l, yy in zip(lines, y)], float)

    def field(self, u, v, lines):
        """W(u, v) at each point, with the leave-one-out coefficients of the point's line where there are any, read at
        the edge of the range the fitting lines cover (never extrapolated beyond the data that shaped it)."""
        u = np.asarray(u, float)
        lo = np.array([self.cover_loo.get(l, (-1.0, 1.0))[0] for l in lines], float)
        hi = np.array([self.cover_loo.get(l, (-1.0, 1.0))[1] for l in lines], float)
        B = _basis(np.clip(u, lo, hi), v, self.degree, self.v_terms)
        if B.shape[1] == 0:
            return np.zeros(len(B))
        C = np.array([self.coef_loo.get(l, self.coef) for l in lines], float)
        return np.einsum('ij,ij->i', B, C)

    def slope(self, v):
        return self.c0 + self.c1 * np.asarray(v, float)

    def shift(self, x, y, lines):
        """Vertical shift (pixels, positive = the rectangle moves up) to remove from rectangles at (x centre, y bottom)."""
        u = self.u(x)
        v = self.v_of(lines, y)
        return self.field(u, v, lines) + self.slope(v) * self.half_w * u - self.ref

    def curve(self, xs, line, a, b):
        """(warped, straight) baseline y at xs for one line: a + b u + W(u, v_l) and a + b u, recorded coordinates."""
        u = self.u(xs)
        v = np.full(len(u), self.v_line.get(line, 0.0))
        straight = a + b * u
        return straight + self.field(u, v, [line] * len(u)), straight


def baseline_curves(page_report: dict, line: int, xs) -> Tuple[np.ndarray, np.ndarray]:
    """From a fitted page's report: (warped, straight) baseline y at xs for line `line` (a bundle line index), in the
    recorded coordinate frame; the straight baseline is the one the line was flattened to (before the page's shared
    tilt is taken out, which a straight line cannot show in recorded coordinates)."""
    c = page_report['coefficients']
    L = c['lines'][str(int(line))]
    m = _PageModel(page_report['x_mid'], page_report['half_width_px'], page_report['y_mid'], page_report['half_height_px'], page_report['degree_used'],
                   page_report['v_terms'], c['field'], {int(k): v['field_loo'] for k, v in c['lines'].items()}, {int(k): v['v'] for k, v in c['lines'].items()},
                   c['tilt'][0], c['tilt'][1], {int(k): v['cover_loo'] for k, v in c['lines'].items()})
    return m.curve(np.asarray(xs, float), int(line), L['intercept_px'], L['slope_px_per_u'])


# ----------------------------------------------------------------------------- flatten
def flatten(app: dict, ms=None, degree: int = 3, min_lines: int = 4, min_words: int = 3, robust: bool = True, loo: bool = True,
            baseline='auto', effects: Optional[dict] = None, ink: Optional[dict] = None, orientations='horizontal') -> Tuple[dict, dict]:
    """Remove each page's shared warp from a bundle's rectangles (module docstring). Returns (flat_app, report).
    This refits the warp from the bundle; consumers should apply the stored fit (``warp.flatten_bundle``).

    `baseline` names the baseline point of each rectangle (``baselines.word_baselines``: 'auto', the default, is the
    ink baseline on the pages whose ink records are clean and the glyph baseline elsewhere; 'glyph' corrects
    the box bottom for the word's descenders and gallows and the line's slope and weights the points by their
    precision; 'bottom' and 'centre' are the plain box bottom and box centre; 'ink' is the baseline measured on the
    page images, ``vmsspatial.ink``, with the glyph baseline standing in for flagged words), or a dict {folio: method}
    choosing per page (``warp.baseline_choice``); `effects` is a ``glyph_effects`` table to reuse (else it is
    estimated on `app`); `ink` the ink product for method 'ink'. The shift applied to a rectangle is the same
    whatever the baseline. Lines outside `orientations` (default: the horizontal ones; ``vmsspatial.orientation``)
    do not enter the fit, and the report counts them under ``skipped``.

    `app` is any bundle from ``load_bundle`` (or any dict with words, lines and geometry on the manuscript's lines); it
    is not modified. `flat_app` is a shallow copy with a new ``geometry`` (every located rectangle shifted vertically,
    top and bottom alike), ``geometry_kind = 'flattened'``, ``geometry_provenance`` extended with the derivation, the
    parent geometry's sha256, the parameters and the new geometry's sha256, and ``flatten`` = the report. A reviewed
    bundle's ``spatialReview`` is copied with its ``geometry`` and ``sensitivityGeometry`` shifted the same way, so the
    sensitivity policy of ``SpatialContext`` reads flattened boxes too (the review's group records keep the recorded
    rectangles). The report has ``pages`` (per folio: fitted, reason, n_lines, n_points, degree_used, v_terms, tilt_deg
    (c0 as an angle in pixel space), keystone_deg_per_H (change of the shared slope per median box height of vertical
    travel) and keystone_deg_text_height (top to bottom of the text block), curvature_pp_H / curvature_pp_px (peak to
    peak of the nonlinear part of the field across the text block at mid height), gutter_side ('left' / 'right': where
    the field's |second derivative| is larger, 'none' when equal), expected_gutter, rms_before_H / rms_after_H (RMS of
    the points' residuals from their own line's straight fit, before and after), H_px and the coefficients), ``summary``
    and ``parameters``."""
    if degree < 2:
        raise ValueError('degree must be at least 2 (the field starts at u^2)')
    if ms is None:
        from .bundle import manuscript_of
        ms = manuscript_of(app)
    require_warp(app, 'recorded', 'the bundle to flatten')
    lines_ms, pages = _lines(ms), _pages(ms)
    if baseline == 'auto':
        from .baselines import auto_pages
        baseline = auto_pages(app, ms, ink)
    per_page = dict(baseline) if isinstance(baseline, dict) else {p.get('folio', str(p['index'])): baseline for p in pages}
    methods = sorted(set(per_page.values()))
    bad = [m for m in methods if m not in BASELINE_METHODS]
    if bad:
        raise ValueError('baseline must be one of %r (got %r)' % (BASELINE_METHODS, bad))
    params = dict(degree=int(degree), min_lines=int(min_lines), min_words=int(min_words), robust=bool(robust), loo=bool(loo),
                  baseline=baseline if isinstance(baseline, str) else 'per page (auto: ink where clean, glyph otherwise)', orientations=orientations if isinstance(orientations, str) else list(orientations or []))
    units = line_units(app, ms, orientations=orientations)
    from .geometry import orientation_mask
    keep, _ = orientation_mask(app, ms, orientations)
    from .orientation import records as orientation_records
    kinds = [r.get('kind') for r in orientation_records(app, ms)] if orientations not in (None, 'all') else [L.get('orientation', {}).get('kind') for L in app['lines']]
    if effects is None and any(m in ('glyph', 'ink') for m in methods):
        from .baselines import glyph_effects
        effects = glyph_effects(app, ms)
    points_by = {m: word_baselines(app, ms, m, effects=effects, ink=ink, orientations=orientations) for m in methods}   # per token (x anchor, baseline y, precision)
    geometry = app['geometry']
    review = app.get('spatialReview')
    extra_lists = [review['geometry'], review['sensitivityGeometry']] if review else []
    new_lists = [list(geometry)] + [list(g) for g in extra_lists]
    reports: Dict[str, dict] = {}
    for p in pages:
        folio = p.get('folio', str(p['index']))
        slots = list(range(p['start_line'], p['end_line']))
        points = points_by[per_page.get(folio, methods[0])]
        rep = dict(folio=folio, index=p['index'], fitted=False, reason='', n_lines=0, n_points=0, degree_used=int(degree), v_terms=False,
                   expected_gutter=expected_gutter(folio, p.get('side')), baseline=per_page.get(folio, methods[0]),
                   line_kinds={str(app['lines'][l].get('locus', l)): (kinds[l] or ('horizontal' if keep[l] else 'other'))
                               for l in slots if any(geometry[i] for i in range(app['lines'][l]['start'], app['lines'][l]['end']))})
        reports[folio] = rep
        # the page's points: one per located rectangle, on lines with enough of them (lines of another orientation have no units)
        boxes = [(l, u['box']) for l in slots for u in units[l] if points[u['first']] is not None]
        if not boxes:
            all_boxes = [b for l in slots for i in range(app['lines'][l]['start'], app['lines'][l]['end']) for b in [geometry[i]] if b]
            rep['reason'] = 'no located rectangles' if not all_boxes else 'no horizontal lines with located rectangles'
            if all_boxes:
                rep['H_px'] = float(np.median([b[3] - b[1] for b in all_boxes]))
            continue
        H = float(np.median([b[3] - b[1] for _, b in boxes]))
        rep['H_px'] = H
        count = Counter(l for l, _ in boxes)
        usable = sorted(l for l, c in count.items() if c >= min_words)
        rep['n_lines'] = len(usable)
        rep['n_points'] = int(sum(count[l] for l in usable))
        if len(usable) < min_lines:
            rep['reason'] = 'fewer than %d lines with %d or more located rectangles (%d)' % (min_lines, min_words, len(usable))
            continue
        pts = [(l, points[u['first']]) for l in slots for u in units[l] if count[l] >= min_words and points[u['first']] is not None]
        x = np.array([p[0] for _, p in pts], float)
        y = np.array([p[1] for _, p in pts], float)
        w0 = np.array([p[2] for _, p in pts], float)
        lid = {l: k for k, l in enumerate(usable)}
        line = np.array([lid[l] for l, _ in pts])
        n_lines = len(usable)
        x_mid, y_mid = (x.min() + x.max()) / 2, (y.min() + y.max()) / 2
        half_w, half_h = (x.max() - x.min()) / 2, (y.max() - y.min()) / 2
        if half_w <= 0 or half_h <= 0:
            rep['reason'] = 'degenerate text block extent'
            continue
        u = (x - x_mid) / half_w
        v = (y - y_mid) / half_h
        v_line = np.bincount(line, v, n_lines) / np.bincount(line, None, n_lines)
        v_terms = n_lines >= FEW_LINES
        B = _basis(u, v_line[line], degree, v_terms)
        coef, a_full, b_full, w, G, h = _fit_page(u, y, B, line, n_lines, robust, w0)
        coef_loo = _loo_coefficients(coef, G, h) if loo else np.tile(coef, (n_lines, 1))
        # the u range each line's points cover, and the range the OTHER lines cover (where its leave-one-out field is read)
        umin, umax = np.full(n_lines, np.inf), np.full(n_lines, -np.inf)
        np.minimum.at(umin, line, u)
        np.maximum.at(umax, line, u)
        cover = {}
        for k in range(n_lines):
            others = [j for j in range(n_lines) if j != k]
            cover[usable[k]] = (float(umin[others].min()), float(umax[others].max())) if (loo and others) else (-1.0, 1.0)
        lo = np.array([cover[usable[k]][0] for k in line]); hi = np.array([cover[usable[k]][1] for k in line])
        B_loo = _basis(np.clip(u, lo, hi), v_line[line], degree, v_terms)
        W_loo = np.einsum('ij,ij->i', B_loo, coef_loo[line]) if B.shape[1] else np.zeros(len(u))
        a, b = _line_params(u, y - W_loo, w, line, n_lines)                      # the lines' own straight parts, given the field
        npts = np.bincount(line, None, n_lines).astype(float)
        beta = b / half_w                                                       # per-line slopes in pixel space
        if v_terms:
            c0, c1 = _robust_line(v_line, beta, npts, robust)
        else:
            c0, c1 = _weighted_mean(beta, npts), 0.0
        model = _PageModel(x_mid, half_w, y_mid, half_h, degree, v_terms, coef, {usable[k]: coef_loo[k] for k in range(n_lines)},
                           {usable[k]: v_line[k] for k in range(n_lines)}, c0, c1, cover)
        raw = model.shift(x, y, [usable[k] for k in line])
        model.ref = float(np.mean(raw))
        shift = raw - model.ref
        # before / after: residuals from each line's own unweighted straight fit
        ones = np.ones(len(u))
        a0, b0 = _line_params(u, y, ones, line, n_lines)
        a1, b1 = _line_params(u, y - shift, ones, line, n_lines)
        rms_before = float(np.sqrt(np.mean((y - (a0[line] + b0[line] * u)) ** 2))) / H
        rms_after = float(np.sqrt(np.mean((y - shift - (a1[line] + b1[line] * u)) ** 2))) / H
        # amplitude and side of the shared curvature at mid height
        grid = np.linspace(-1, 1, 201)
        Wmid = _basis(grid, np.zeros_like(grid), degree, v_terms) @ coef if B.shape[1] else np.zeros_like(grid)
        trend = np.polyval(np.polyfit(grid, Wmid, 1), grid)
        nonlinear = Wmid - trend
        pp_px = float(nonlinear.max() - nonlinear.min())
        # the same over the core of the text block: the u range at least half of the usable lines reach
        coverage = sum(((grid >= umin[k]) & (grid <= umax[k])).astype(int) for k in range(n_lines))
        core = grid[coverage >= int(np.ceil(n_lines / 2.0))]
        if len(core) >= 3:
            Wcore = _basis(core, np.zeros_like(core), degree, v_terms) @ coef if B.shape[1] else np.zeros_like(core)
            nl_core = Wcore - np.polyval(np.polyfit(core, Wcore, 1), core)
            pp_core_px, core_range = float(nl_core.max() - nl_core.min()), [float(core.min()), float(core.max())]
        else:
            pp_core_px, core_range = float('nan'), None
        terms = basis_terms(degree, v_terms)
        w_k0 = {k: float(coef[terms.index('u^%d' % k)]) for k in range(2, degree + 1)}
        second = sum(k * (k - 1) * w_k0[k] * grid ** (k - 2) for k in range(2, degree + 1))
        left_curv, right_curv = float(np.mean(np.abs(second[grid < 0]))), float(np.mean(np.abs(second[grid > 0])))
        if left_curv > right_curv * (1 + 1e-9):
            side = 'left'
        elif right_curv > left_curv * (1 + 1e-9):
            side = 'right'
        else:
            side = 'none'
        rep.update(fitted=True, reason='', v_terms=bool(v_terms), tilt_deg=float(np.degrees(np.arctan(c0))),
                   keystone_deg_per_H=float(np.degrees(np.arctan(c0 + c1 * H / half_h)) - np.degrees(np.arctan(c0))),
                   keystone_deg_text_height=float(np.degrees(np.arctan(c0 + c1)) - np.degrees(np.arctan(c0 - c1))),
                   curvature_pp_px=pp_px, curvature_pp_H=pp_px / H, curvature_pp_core_px=pp_core_px, curvature_pp_core_H=pp_core_px / H, core_u_range=core_range,
                   gutter_side=side, curvature_left=left_curv, curvature_right=right_curv,
                   rms_before_H=rms_before, rms_after_H=rms_after, x_mid=float(x_mid), y_mid=float(y_mid), half_width_px=float(half_w), half_height_px=float(half_h),
                   reference_px=model.ref, robust_weight_mean=float(np.mean(w)),
                   coefficients=dict(field=[float(c) for c in coef], field_terms=terms, tilt=[c0, c1],
                                     lines={str(usable[k]): dict(n=int(npts[k]), v=float(v_line[k]), intercept_px=float(a[k]), slope_px_per_u=float(b[k]),
                                                                 slope_deg=float(np.degrees(np.arctan(beta[k]))), field_loo=[float(c) for c in coef_loo[k]],
                                                                 u_range=[float(umin[k]), float(umax[k])], cover_loo=list(cover[usable[k]]),
                                                                 locus=str(app['lines'][usable[k]].get('locus', usable[k])))
                                            for k in range(n_lines)}))
        # shift every located rectangle of the page's horizontal lines, in every geometry list, by the model
        for src, dst in zip([geometry] + extra_lists, new_lists):
            idx, xs, ys, ls = [], [], [], []
            for l in slots:
                if not keep[l]:
                    continue
                L = app['lines'][l]
                for i in range(L['start'], L['end']):
                    bx = src[i]
                    if bx:
                        idx.append(i)
                        xs.append((bx[0] + bx[2]) / 2)
                        ys.append(bx[3])
                        ls.append(l)
            if not idx:
                continue
            sh = model.shift(np.array(xs), np.array(ys), ls)
            for i, s in zip(idx, sh):
                bx = src[i]
                dst[i] = [float(bx[0]), float(bx[1] - s), float(bx[2]), float(bx[3] - s)]
    report = dict(parameters=params, pages=reports, summary=summarize(reports), skipped=getattr(units, 'skipped', None))
    new_geometry = new_lists[0]
    prov = dict(app.get('geometry_provenance') or {})
    prov.update(derived='flattened', parent_geometry_kind=app.get('geometry_kind'), parent_geometry_sha256=digest(geometry), flatten_parameters=params,
                geometry_sha256=digest(new_geometry))
    flat = dict(app, geometry=new_geometry, geometry_kind='flattened', geometry_provenance=prov, flatten=report)
    if review:
        flat['spatialReview'] = dict(review, geometry=new_lists[1], sensitivityGeometry=new_lists[2])
    tag(flat, warp='flat')
    flat['lines'] = [dict(L) for L in app['lines']]
    return flat, report


def summarize(pages: Dict[str, dict]) -> dict:
    """Counts over the per-page reports; shares only beside their counts and only on 20 pages or more."""
    reps = list(pages.values())
    fitted = [r for r in reps if r['fitted']]
    reasons = Counter(r['reason'] for r in reps if not r['fitted'])
    def gutter_test(key):
        clear = [r for r in fitted if r[key] > AMPLITUDE_H]
        judged = [r for r in clear if r['expected_gutter'] and r['gutter_side'] in ('left', 'right')]
        match = sum(1 for r in judged if r['gutter_side'] == r['expected_gutter'])
        return dict(n=len(clear), judged=len(judged), gutter_matches=match, gutter_mismatches=len(judged) - match,
                    share_match=(match / len(judged)) if len(judged) >= SMALL else None,
                    recto=sum(1 for r in clear if r['expected_gutter'] == 'left'), verso=sum(1 for r in clear if r['expected_gutter'] == 'right'))
    med = lambda key, rs: float(np.nanmedian([r[key] for r in rs])) if rs else None
    return dict(pages=len(reps), fitted=len(fitted), not_fitted=dict(reasons), quarantined=reasons.get('no horizontal lines with located rectangles', 0),
                median_curvature_pp_H=med('curvature_pp_H', fitted), median_curvature_pp_px=med('curvature_pp_px', fitted),
                median_curvature_pp_core_H=med('curvature_pp_core_H', fitted),
                median_abs_tilt_deg=float(np.median([abs(r['tilt_deg']) for r in fitted])) if fitted else None,
                median_rms_before_H=med('rms_before_H', fitted), median_rms_after_H=med('rms_after_H', fitted),
                amplitude_threshold_H=AMPLITUDE_H,
                above_threshold=gutter_test('curvature_pp_H'),                 # amplitude across the whole text block
                above_threshold_core=gutter_test('curvature_pp_core_H'))       # amplitude across the core the lines share


def page_table(report: dict) -> List[dict]:
    """The per-page report as flat rows (for a CSV): no coefficients."""
    keys = ('folio', 'index', 'fitted', 'reason', 'baseline', 'n_lines', 'n_points', 'degree_used', 'v_terms', 'H_px', 'tilt_deg', 'keystone_deg_per_H', 'keystone_deg_text_height',
            'curvature_pp_H', 'curvature_pp_px', 'curvature_pp_core_H', 'core_u_range', 'gutter_side', 'expected_gutter', 'rms_before_H', 'rms_after_H', 'reference_px', 'robust_weight_mean')
    return [{k: r.get(k) for k in keys} for r in report['pages'].values()]
