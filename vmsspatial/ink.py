"""Ink measurements of the words on the page images: the writing's own baseline, x-height band, angle and extents.

The recorded rectangles say where a word is, not where its ink is: the box bottom follows the lowest descender,
the box top the tallest gallows, and a box may be drawn off the text's own angle (``baselines``). This module reads
the ink inside each mapped rectangle on a page image (``images``: the Beinecke scan by default, the Voynichese
display image as a check) and returns numbers only, in the recorded frame.

Binarization. Per text line, the image region around the line's mapped rectangles is thresholded locally (Sauvola,
window 1.5 H in image px, k 0.2) on a channel in which ink is dark (``channel``: luminance 'lum', the red/blue
chromaticity 'rb', or inverted HSV saturation 'sat'; ``compare_channels`` scores them by Otsu's class separation
inside the boxes, and the default is the one that won on the test pages). Saturated paint (green, blue, saturated
red that is not dark) is removed first. Inside a word's padded box, connected components are kept when at least
half of their pixels lie inside the box (a drawing line or a neighbour's descender passing through is dropped and
flagged); a component with less than half inside but a large share of the box's ink is a merge with a neighbour
(flagged touch, kept only inside the box); specks below 0.004 H^2 are dropped.

Per word (one record per located rectangle, shared rectangles once): the ink's horizontal extent; the writing
angle, found by shearing the ink by angles within +-6 degrees and maximising the sharpness of the vertical profile
(short words take the line's angle); the x-height band from the sheared profile (the baseline is the strongest drop of the
profile near the box bottom, where every glyph ends; the mean line the lowest sufficiently strong rise 0.45 to 1.05 H
above it that is followed by dense rows; both sub-pixel); the ascender top
and descender bottom (the extreme ink beyond the band by more than 0.08 H, with its x); ink coverage; flags. All
coordinates come back in the recorded frame (and in H = the page's median rectangle height) through the inverse of
the page's registration. Per line: a robust straight fit through the word baselines (angle, offset, residuals), the
median x-height and its spread, the box-derived angles for comparison, and the box-to-ink cross-correlation shift
(a diagnostic of the boxes against the ink; the registration itself comes from the two images, see ``images``).

``measure_pages`` writes the data product ``data/manuscript/ink_measures.json.gz`` (lists per record, 0.1 px),
``load_ink`` reads it, ``baseline_points`` turns it into baseline points for ``baselines.word_baselines(method='ink')``
(on any geometry of the same rectangles: the baseline travels with the box bottom), ``intrusions`` lists the words
whose descenders reach into the line below or whose ascenders reach into the line above, and ``gap_table`` gives
every word's gap to the previous line. Tests render synthetic words (``measure_region`` on an array).

Images: Beinecke Rare Book and Manuscript Library, Yale University (MS 408), via Yale University Library's digital
collections; Voynichese Project display images from voynichese.com. No crop is saved anywhere.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import paths
from .bundle import digest, read_json, write_json
from .frames import check_same, tag
from .geometry import _lines, _pages, line_units

VERSION = '2026.10.30.2'
PRODUCT_KEY = 'manuscript/ink_measures.json.gz'
CHANNELS = ('lum', 'rb', 'sat')
DEFAULTS = dict(channel='lum', sauvola_window_H=1.5, sauvola_k=0.2, paint_sat=0.42, pad_H=(0.25, 0.35), angle_range_deg=6.0, angle_step_deg=0.5,
                angle_fine_deg=0.1, base_window_H=(0.7, 0.15), band_min_H=0.28, band_max_H=0.8, sparsity_share=0.3, plateau_share=0.2, plateau_H=0.2, mass_share=0.7, mass_share_min=0.4, min_width_H=2.0, inside_frac=0.5, merge_share=0.15, neighbour_share=0.03, paint_share=0.03,
                speck_area_H2=0.004, min_ink_H2=0.05, asc_margin_H=0.08, touch_H=0.08, shift_search_H=0.6)

# flags of a word record (bit values)
LITTLE_INK, PAINT, NEIGHBOUR, REGISTRATION, NO_BAND, ANGLE_FALLBACK, TOUCH_ABOVE, TOUCH_BELOW, CLIPPED, SHORT = 1, 2, 4, 8, 16, 32, 64, 128, 256, 512
FLAG_NAMES = {LITTLE_INK: 'little_ink', PAINT: 'paint', NEIGHBOUR: 'neighbour_ink', REGISTRATION: 'registration_poor', NO_BAND: 'band_not_found',
              ANGLE_FALLBACK: 'angle_from_line', TOUCH_ABOVE: 'touch_above', TOUCH_BELOW: 'touch_below', CLIPPED: 'region_clipped', SHORT: 'short_word'}
UNCLEAN = LITTLE_INK | PAINT | REGISTRATION | NO_BAND                    # a record with any of these is not a clean baseline (touch and neighbour flags are informational)
UNIT_FIELDS = ('first', 'last', 'line', 'box_bottom', 'x0', 'x1', 'xc', 'base', 'mean', 'asc_y', 'asc_x', 'desc_y', 'desc_x', 'angle', 'xheight', 'coverage', 'n_ink', 'flags')
LINE_FIELDS = ('line', 'n_units', 'n_clean', 'angle', 'intercept', 'x_mid', 'resid_rms', 'xheight_med', 'xheight_mad', 'box_ls_angle', 'box_chord_angle',
               'shift_dx', 'shift_dy', 'shift_n', 'ink_dx', 'ink_dy', 'ink_z')


def flag_names(flags: int) -> List[str]:
    return [n for b, n in FLAG_NAMES.items() if flags & b]


# ----------------------------------------------------------------------------- binarization
def channel(rgb: np.ndarray, name: str) -> np.ndarray:
    """A float32 image in which ink is dark: 'lum' luminance; 'rb' 255 x (1 - (R - B) / (R + B)), the red/blue
    chromaticity (brown ink is redder than vellum); 'sat' 255 - HSV saturation (ink is more saturated than vellum)."""
    r, g, b = (rgb[..., 0].astype(np.float32), rgb[..., 1].astype(np.float32), rgb[..., 2].astype(np.float32))
    if name == 'lum':
        return 0.299 * r + 0.587 * g + 0.114 * b
    if name == 'rb':
        return 255.0 * (1.0 - np.clip((r - b) / (r + b + 1.0), 0.0, 1.0))
    if name == 'sat':
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        return 255.0 * (1.0 - (mx - mn) / (mx + 1.0))
    raise ValueError('channel must be one of %r' % (CHANNELS,))


def paint_mask(rgb: np.ndarray, sat_threshold: float = 0.42) -> np.ndarray:
    """Saturated paint: green, cyan and blue hues above the saturation threshold, and saturated red that is not
    dark (brown ink is dark and orange-brown; the test keeps it)."""
    import cv2
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.float32) / 255.0, hsv[..., 2].astype(np.float32) / 255.0
    sat = s > sat_threshold
    cool = (h >= 30) & (h <= 135)                                  # OpenCV hue 0..180: 60..270 degrees
    red = ((h < 5) | (h > 165)) & (v > 0.45)
    return sat & (cool | red)


def binarize(rgb: np.ndarray, H_img: float, params: Optional[dict] = None) -> Tuple[np.ndarray, np.ndarray]:
    """(ink, paint) boolean masks of an image region: a Sauvola threshold on the chosen channel, window 1.5 H (odd,
    at least 15 px), paint removed."""
    from skimage.filters import threshold_sauvola
    p = dict(DEFAULTS, **(params or {}))
    chan = channel(rgb, p['channel'])
    win = int(round(p['sauvola_window_H'] * H_img))
    win = max(15, win | 1)
    thr = threshold_sauvola(chan, window_size=win, k=p['sauvola_k'], r=128.0)       # r: half the 0..255 range (the float default is 1)
    paint = paint_mask(rgb, p['paint_sat'])
    ink = (chan < thr) & ~paint
    return ink, paint


def otsu_separation(values: np.ndarray) -> float:
    """Otsu's effectiveness: between-class variance over total variance at the best threshold (0..1)."""
    v = np.asarray(values, float).ravel()
    if len(v) < 16 or v.std() < 1e-9:
        return 0.0
    hist, edges = np.histogram(v, bins=64)
    centres = (edges[:-1] + edges[1:]) / 2
    w = hist.astype(float) / hist.sum()
    cw = np.cumsum(w)
    cm = np.cumsum(w * centres)
    mean = cm[-1]
    with np.errstate(divide='ignore', invalid='ignore'):
        between = (mean * cw - cm) ** 2 / (cw * (1 - cw))
    between = np.nan_to_num(between, nan=0.0, posinf=0.0, neginf=0.0)
    return float(between.max() / (v.var() + 1e-12))


def compare_channels(folio: str, app, ms, source: str = 'beinecke', max_boxes: int = 150, rec: Optional[dict] = None) -> dict:
    """Mean Otsu separation of each channel inside the page's mapped rectangles (paint pixels excluded): the channel
    that separates ink from vellum best scores highest."""
    from .images import registration, page_image, Mapping
    rec = rec or registration(folio, source, app, ms)
    if not rec.get('ok'):
        return dict(folio=folio, ok=False)
    img = page_image(folio, source, rec.get('image_id'))
    units = line_units(app, ms)
    pages = _pages(ms)
    p = next(p for p in pages if p.get('folio') == folio)
    boxes = [(l, u['box']) for l in range(p['start_line'], p['end_line']) for u in units[l]]
    step = max(1, len(boxes) // max_boxes)
    scores = {c: [] for c in CHANNELS}
    for l, box in boxes[::step]:
        m = Mapping(rec, l)
        b = m.box_to_image(box)
        X0, Y0, X1, Y1 = int(b[0]), int(b[1]), int(math.ceil(b[2])), int(math.ceil(b[3]))
        reg = img[max(0, Y0):Y1, max(0, X0):X1]
        if reg.size == 0:
            continue
        keep = ~paint_mask(reg)
        for c in CHANNELS:
            scores[c].append(otsu_separation(channel(reg, c)[keep]))
    out = dict(folio=folio, ok=True, n_boxes=len(scores['lum']), separation={c: float(np.mean(s)) if s else None for c, s in scores.items()})
    out['best'] = max(out['separation'], key=lambda c: out['separation'][c] or 0.0)
    return out


# ----------------------------------------------------------------------------- one word
def _sheared_profile(ys: np.ndarray, xs: np.ndarray, xc: float, tan_t: float, n_rows: int) -> np.ndarray:
    """Vertical ink profile after shearing rows by tan_t x (x - xc), with linear weights into 1 px bins."""
    y = ys - tan_t * (xs - xc)
    f = np.floor(y)
    w = y - f
    i = f.astype(int)
    out = np.bincount(np.clip(i, 0, n_rows - 1), 1.0 - w, n_rows) + np.bincount(np.clip(i + 1, 0, n_rows - 1), w, n_rows)
    return out


def _sharpness(profile: np.ndarray) -> float:
    """The profile's energy (sum of squares): largest when the ink's rows line up, the standard skew criterion."""
    return float(np.sum(profile * profile))


def _best_angle(ys, xs, xc, n_rows, rng_deg, step_deg, fine_deg) -> float:
    grid = np.arange(-rng_deg, rng_deg + 1e-9, step_deg)
    best = max(grid, key=lambda t: _sharpness(_sheared_profile(ys, xs, xc, math.tan(math.radians(t)), n_rows)))
    fine = np.arange(best - step_deg, best + step_deg + 1e-9, fine_deg)
    fine = fine[(fine >= -rng_deg - 1e-9) & (fine <= rng_deg + 1e-9)]
    return float(max(fine, key=lambda t: _sharpness(_sheared_profile(ys, xs, xc, math.tan(math.radians(t)), n_rows))))


def _smooth(P: np.ndarray) -> np.ndarray:
    return np.convolve(P, [0.25, 0.5, 0.25], mode='same') if len(P) >= 3 else P.copy()


def _extremum(D: np.ndarray, lo: int, hi: int, sign: float):
    """Position (row boundary, sub-pixel) and size of the strongest rise (sign +1) or drop (-1) of the profile whose
    forward difference is D, among boundaries lo..hi (D[i] is the boundary at the start of row i + 1)."""
    lo, hi = max(0, lo), min(len(D) - 1, hi)
    if hi < lo:
        return None, 0.0
    seg = sign * D[lo:hi + 1]
    j = int(np.argmax(seg)) + lo
    size = float(sign * D[j])
    pos = j + 1.0
    if 0 < j < len(D) - 1:
        a, b, c = sign * D[j - 1], sign * D[j], sign * D[j + 1]
        den = a - 2 * b + c
        if den < 0:
            pos += float((a - c) / (2 * den))
    return pos, size


def _band(profile: np.ndarray, H_img: float, box_bottom: float, p: dict):
    """(top, bottom) of the x-height band from the sheared profile, in rows.

    Baseline candidates: the drops of the (lightly smoothed) profile within [box bottom - base_window_H[0] x H, box
    bottom + base_window_H[1] x H] (every glyph ends on the baseline; the box bottom is the drawn lowest ink),
    strongest first, each followed by sparse rows (mean below sparsity_share x peak over 0.15 H: the mid-band dip of
    c/e-shaped glyphs is followed by the dense bottom arcs and fails, the baseline is followed by tails only). Mean
    line candidates: the rises between base - band_max_H x H and base - band_min_H x H, lowest first, followed by
    dense rows (plateau_share x peak over plateau_H x H); the band must hold mass_share of the profile's mass (so
    the rise into the dense bottom arcs alone is too thin and the next rise up is taken). Edges are sub-pixel
    (parabolic). None when nothing qualifies."""
    P = _smooth(profile)
    peak = P.max()
    total = P.sum()
    if peak <= 0 or len(P) < 4:
        return None
    D = np.diff(P)
    lo = max(0, int(math.floor(box_bottom - p['base_window_H'][0] * H_img)) - 1)
    hi = min(len(D) - 1, int(math.ceil(box_bottom + p['base_window_H'][1] * H_img)) - 1)
    if hi < lo:
        return None
    drops = [i for i in range(lo, hi + 1) if D[i] < -0.05 * peak and (i == 0 or D[i] <= D[i - 1]) and (i == len(D) - 1 or D[i] <= D[i + 1])]
    drops.sort(key=lambda i: D[i])
    k_sparse = max(2, int(round(0.15 * H_img)))
    plateau = max(2, int(round(p['plateau_H'] * H_img)))
    for i in drops:
        after = P[i + 1:i + 1 + k_sparse]
        if len(after) and after.mean() > p['sparsity_share'] * peak:
            continue
        base, _ = _extremum(D, i, i, -1.0)
        lo2 = max(0, int(math.floor(base - p['band_max_H'] * H_img)) - 1)
        hi2 = min(len(D) - 1, int(math.ceil(base - p['band_min_H'] * H_img)) - 1)
        if hi2 < lo2:
            continue
        rises = [j for j in range(lo2, hi2 + 1) if D[j] > 0.03 * peak and (j == 0 or D[j] >= D[j - 1]) and (j == len(D) - 1 or D[j] >= D[j + 1])]
        fallback = None
        for j in sorted(rises, reverse=True):                           # lowest candidate first
            rows = P[j + 1:min(len(P), j + 1 + plateau)]
            if not len(rows) or rows.mean() < p['plateau_share'] * peak:
                continue
            top, _ = _extremum(D, j, j, +1.0)
            if top is None or base - top < p['band_min_H'] * H_img:
                continue
            mass = P[int(round(top)):int(round(base)) + 1].sum() / max(total, 1e-9)
            if mass >= p['mass_share']:
                return float(top), float(base)
            if fallback is None or mass > fallback[0]:
                fallback = (mass, top)
        if fallback is not None and fallback[0] >= p['mass_share_min']:
            return float(fallback[1]), float(base)
    return None


def _filter_components(ink: np.ndarray, box: Sequence[float], H_img: float, p: dict):
    """Keep the word's own components inside a padded-box region. Returns (kept mask, flags, neighbour share)."""
    import cv2
    h, w = ink.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros_like(ink), 0, 0.0
    bx0, by0 = int(max(0, math.floor(box[0]))), int(max(0, math.floor(box[1])))
    bx1, by1 = int(min(w, math.ceil(box[2]))), int(min(h, math.ceil(box[3])))
    inside = np.bincount(labels[by0:by1, bx0:bx1].ravel(), minlength=n).astype(float)
    area = stats[:, cv2.CC_STAT_AREA].astype(float)
    speck = area < p['speck_area_H2'] * H_img * H_img
    valid = ~speck
    valid[0] = False
    inside_total = inside[valid].sum()
    frac = inside / np.maximum(area, 1)
    keep_whole = valid & (frac >= p['inside_frac'])
    partial = valid & ~keep_whole & (inside > 0)
    merge = partial & (inside >= p['merge_share'] * max(inside_total, 1.0))
    neighbour = partial & ~merge
    flags = 0
    kept = np.isin(labels, np.nonzero(keep_whole)[0])
    if merge.any():
        inside_mask = np.zeros_like(ink)
        inside_mask[by0:by1, bx0:bx1] = True
        kept |= np.isin(labels, np.nonzero(merge)[0]) & inside_mask
    tol = p['touch_H'] * H_img
    for k in np.nonzero(keep_whole | merge)[0]:
        top, bottom = stats[k, cv2.CC_STAT_TOP], stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT]
        if merge[k] or top <= 0 or bottom >= h:
            if top < box[1] - tol:
                flags |= TOUCH_ABOVE
            if bottom > box[3] + tol:
                flags |= TOUCH_BELOW
    nshare = float(inside[neighbour].sum() / max(inside_total, 1.0))
    if nshare > p['neighbour_share']:
        flags |= NEIGHBOUR
    return kept, flags, nshare


def measure_word(ink: np.ndarray, paint: Optional[np.ndarray], box: Sequence[float], H_img: float, params: Optional[dict] = None,
                 angle_deg: Optional[float] = None, line_angle_deg: Optional[float] = None) -> dict:
    """Measure one word in a binarized region (module docstring). `box` is the mapped rectangle in region px; the
    region should be the box padded by about (0.25 H, 0.35 H). `angle_deg` forces the shear angle; otherwise the
    word's own angle is searched, unless its ink is narrower than min_width_H x H, when `line_angle_deg` (or 0) is
    used and the record is flagged. Returns region-pixel values: x0, x1, xc, base, mean, asc (y, x) or None,
    desc (y, x) or None, angle_deg, xheight, coverage, n_ink, flags, neighbour_share, paint_share."""
    p = dict(DEFAULTS, **(params or {}))
    h, w = ink.shape
    out = dict(x0=None, x1=None, xc=None, base=None, mean=None, asc=None, desc=None, angle_deg=None, xheight=None, coverage=None, n_ink=0, flags=0,
               neighbour_share=0.0, paint_share=0.0)
    bx0, by0 = int(max(0, math.floor(box[0]))), int(max(0, math.floor(box[1])))
    bx1, by1 = int(min(w, math.ceil(box[2]))), int(min(h, math.ceil(box[3])))
    box_area = max(1, (bx1 - bx0) * (by1 - by0))
    if paint is not None:
        out['paint_share'] = float(paint[by0:by1, bx0:bx1].sum() / box_area)
        if out['paint_share'] > p['paint_share']:
            out['flags'] |= PAINT
    kept, cflags, nshare = _filter_components(ink, box, H_img, p)
    out['flags'] |= cflags
    out['neighbour_share'] = nshare
    ys, xs = np.nonzero(kept)
    out['n_ink'] = int(len(ys))
    out['kept'] = kept
    if len(ys) < p['min_ink_H2'] * H_img * H_img:
        out['flags'] |= LITTLE_INK
        return out
    ys = ys.astype(float) + 0.5
    xs = xs.astype(float) + 0.5
    x0, x1 = float(xs.min() - 0.5), float(xs.max() + 0.5)
    xc = (x0 + x1) / 2
    out.update(x0=x0, x1=x1, xc=xc)
    if x1 - x0 < p['min_width_H'] * H_img:
        out['flags'] |= SHORT
    if angle_deg is None:
        if out['flags'] & SHORT:
            angle_deg = line_angle_deg if line_angle_deg is not None else 0.0
            out['flags'] |= ANGLE_FALLBACK
        else:
            angle_deg = _best_angle(ys, xs, xc, h, p['angle_range_deg'], p['angle_step_deg'], p['angle_fine_deg'])
    out['angle_deg'] = float(angle_deg)
    tan_t = math.tan(math.radians(angle_deg))
    prof = _sheared_profile(ys, xs, xc, tan_t, h)
    band = _band(prof, H_img, box[3], p)
    if band is None:
        out['flags'] |= NO_BAND
        return out
    top, bottom = band
    xh = bottom - top
    out.update(mean=top, base=bottom, xheight=float(xh), coverage=float(len(ys) / max(1.0, (x1 - x0) * xh)))
    ysh = ys - tan_t * (xs - xc)                     # sheared ink rows: y' at x = xc
    k_top, k_bot = int(np.argmin(ysh)), int(np.argmax(ysh))
    if top - ysh[k_top] > p['asc_margin_H'] * H_img:
        out['asc'] = (float(ys[k_top]), float(xs[k_top]))
    if ysh[k_bot] - bottom > p['asc_margin_H'] * H_img:
        out['desc'] = (float(ys[k_bot]), float(xs[k_bot]))
    return out


def measure_region(rgb: np.ndarray, box: Sequence[float], H_img: float, params: Optional[dict] = None, angle_deg: Optional[float] = None) -> dict:
    """Binarize an RGB region and measure the word in `box` (region px): for tests and ad-hoc use."""
    ink, paint = binarize(rgb, H_img, params)
    return measure_word(ink, paint, box, H_img, params, angle_deg=angle_deg)


# ----------------------------------------------------------------------------- one line
def _robust_line(x, y):
    """(intercept, slope) of a Huber-reweighted least-squares line (the chord for two points)."""
    from .flatten import _robust_line as rl
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2:
        return None
    if len(x) == 2:
        s = (y[1] - y[0]) / (x[1] - x[0]) if x[1] != x[0] else 0.0
        return float(y[0] - s * x[0]), float(s)
    c0, c1 = rl(x, y, np.ones(len(x)), True)
    return c0, c1


def box_ink_shift(ink: np.ndarray, boxes: Sequence[Sequence[float]], H_img: float, search_H: float = 0.6):
    """Cross-correlation of the boxes' inner bands (rows 0.2..0.8, columns 0.1..0.9 of each box) with the zero-mean
    ink of a line region: the shift (dx, dy, in region px) that puts the boxes on the ink, and the peak's z-score.
    A diagnostic of the boxes against the ink (the registration is not changed by it)."""
    from scipy.signal import correlate
    h, w = ink.shape
    T = np.zeros((h, w), np.float32)
    for b in boxes:
        bw, bh = b[2] - b[0], b[3] - b[1]
        x0, x1 = int(max(0, b[0] + 0.1 * bw)), int(min(w, b[2] - 0.1 * bw))
        y0, y1 = int(max(0, b[1] + 0.2 * bh)), int(min(h, b[3] - 0.2 * bh))
        if x1 > x0 and y1 > y0:
            T[y0:y1, x0:x1] = 1.0
    if T.sum() == 0 or ink.sum() == 0:
        return None
    I = ink.astype(np.float32)
    I -= I.mean()
    C = correlate(I, T, mode='same', method='fft')
    R = int(max(2, round(search_H * H_img)))
    cy, cx = h // 2, w // 2
    win = C[max(0, cy - R):cy + R + 1, max(0, cx - R):cx + R + 1]
    if win.size < 9:
        return None
    k = np.unravel_index(int(np.argmax(win)), win.shape)
    dy, dx = k[0] - (cy - max(0, cy - R)), k[1] - (cx - max(0, cx - R))
    # parabolic refinement
    def refine(a, i):
        if 0 < i < len(a) - 1 and (a[i - 1] - 2 * a[i] + a[i + 1]) < 0:
            return float((a[i - 1] - a[i + 1]) / (2 * (a[i - 1] - 2 * a[i] + a[i + 1])))
        return 0.0
    fdy = refine(win[:, k[1]], k[0])
    fdx = refine(win[k[0], :], k[1])
    z = float((win.max() - win.mean()) / (win.std() + 1e-9))
    at_edge = k[0] in (0, win.shape[0] - 1) or k[1] in (0, win.shape[1] - 1)
    return dict(dx=float(dx + fdx), dy=float(dy + fdy), z=z, at_edge=bool(at_edge))


def measure_line(img: np.ndarray, mapping, units: Sequence[dict], H_frame: float, params: Optional[dict] = None, reg_poor: bool = False) -> Tuple[List[dict], dict]:
    """Measure every unit of one line on a page image. Returns (word records in the RECORDED frame, line record).

    Word record: first, last, box (recorded), x0, x1, xc, base, mean, asc_y, asc_x, desc_y, desc_x (frame px or
    None), angle_deg (frame; positive = falls to the right), xheight (frame px), coverage, n_ink, flags, and the
    box-derived comparisons dx0, dx1 (ink extent minus box edge), dtop, dbottom (ink top / bottom minus box top /
    bottom, frame px, None when no ink beyond the band)."""
    p = dict(DEFAULTS, **(params or {}))
    if not units:
        return [], {}
    boxes_img = [mapping.box_to_image(u['box']) for u in units]
    xs_c = [(u['box'][0] + u['box'][2]) / 2 for u in units]
    ys_c = [(u['box'][1] + u['box'][3]) / 2 for u in units]
    xm, ym = float(np.mean(xs_c)), float(np.mean(ys_c))
    s = mapping.scale(xm, ym)
    rot = mapping.rotation_deg(xm, ym)
    H_img = H_frame * s
    pad_x, pad_y = p['pad_H'][0] * H_img, p['pad_H'][1] * H_img
    win = max(15, int(round(p['sauvola_window_H'] * H_img)) | 1)
    B = np.array(boxes_img)
    X0 = int(math.floor(B[:, 0].min() - pad_x - win))
    Y0 = int(math.floor(B[:, 1].min() - pad_y - win))
    X1 = int(math.ceil(B[:, 2].max() + pad_x + win))
    Y1 = int(math.ceil(B[:, 3].max() + pad_y + win))
    X0c, Y0c, X1c, Y1c = max(0, X0), max(0, Y0), min(img.shape[1], X1), min(img.shape[0], Y1)
    if X1c - X0c < 4 or Y1c - Y0c < 4:
        return [dict(first=u['first'], last=u['last'], box=u['box'], flags=CLIPPED | LITTLE_INK) for u in units], {}
    region = img[Y0c:Y1c, X0c:X1c]
    ink, paint = binarize(region, H_img, p)
    origin = np.array([X0c, Y0c], float)

    def one(k, angle=None, line_angle=None):
        b = boxes_img[k] - np.array([X0c, Y0c, X0c, Y0c])
        rx0, ry0 = int(max(0, math.floor(b[0] - pad_x))), int(max(0, math.floor(b[1] - pad_y)))
        rx1, ry1 = int(min(ink.shape[1], math.ceil(b[2] + pad_x))), int(min(ink.shape[0], math.ceil(b[3] + pad_y)))
        sub_ink = ink[ry0:ry1, rx0:rx1]
        sub_paint = paint[ry0:ry1, rx0:rx1]
        sub_box = [b[0] - rx0, b[1] - ry0, b[2] - rx0, b[3] - ry0]
        m = measure_word(sub_ink, sub_paint, sub_box, H_img, p, angle_deg=angle, line_angle_deg=line_angle)
        clipped = (rx0 == 0 and X0c == 0) or (ry0 == 0 and Y0c == 0) or (rx1 == ink.shape[1] and X1c == img.shape[1]) or (ry1 == ink.shape[0] and Y1c == img.shape[0])
        if clipped:
            m['flags'] |= CLIPPED
        if reg_poor:
            m['flags'] |= REGISTRATION
        m['_off'] = np.array([rx0, ry0], float)
        return m
    raw = [one(k) for k in range(len(units))]
    limit = p['angle_range_deg'] - 0.05
    at_limit = [m['angle_deg'] is not None and abs(m['angle_deg']) >= limit and not (m['flags'] & ANGLE_FALLBACK) for m in raw]
    own = [m['angle_deg'] - rot for m, lim in zip(raw, at_limit) if m['angle_deg'] is not None and not lim and not (m['flags'] & (ANGLE_FALLBACK | UNCLEAN))]
    line_angle_frame = float(np.median(own)) if len(own) >= 2 else None
    if line_angle_frame is not None:
        for k, m in enumerate(raw):
            if m['flags'] & ANGLE_FALLBACK or at_limit[k]:
                # short words, and words whose own search ran to the limit of the range, take the line's angle
                raw[k] = one(k, angle=line_angle_frame + rot)
                raw[k]['flags'] |= ANGLE_FALLBACK
    records = []
    for u, m, bimg in zip(units, raw, boxes_img):
        rec = dict(first=u['first'], last=u['last'], box=u['box'], flags=m['flags'], n_ink=m['n_ink'], coverage=m.get('coverage'),
                   x0=None, x1=None, xc=None, base=None, mean=None, asc_y=None, asc_x=None, desc_y=None, desc_x=None, angle_deg=None, xheight=None,
                   dx0=None, dx1=None, dtop=None, dbottom=None, neighbour_share=m['neighbour_share'], paint_share=m['paint_share'])
        if m['x0'] is not None:
            off = m['_off'] + origin
            yc_img = (bimg[1] + bimg[3]) / 2 - origin[1] - m['_off'][1]
            ext = mapping.to_frame(np.array([[m['x0'], yc_img], [m['x1'], yc_img]]) + off)
            rec['x0'], rec['x1'] = float(ext[0, 0]), float(ext[1, 0])
            rec['dx0'], rec['dx1'] = rec['x0'] - u['box'][0], rec['x1'] - u['box'][2]
            if m['base'] is not None:
                pts = mapping.to_frame(np.array([[m['xc'], m['base']], [m['xc'], m['mean']]]) + off)
                rec['xc'], rec['base'], rec['mean'] = float(pts[0, 0]), float(pts[0, 1]), float(pts[1, 1])
                rec['xheight'] = float(rec['base'] - rec['mean'])
                rec['angle_deg'] = float(m['angle_deg'] - rot)
                if m['asc'] is not None:
                    a = mapping.to_frame(np.array([[m['asc'][1], m['asc'][0]]]) + off)[0]
                    rec['asc_y'], rec['asc_x'] = float(a[1]), float(a[0])
                    rec['dtop'] = rec['asc_y'] - u['box'][1]
                if m['desc'] is not None:
                    d = mapping.to_frame(np.array([[m['desc'][1], m['desc'][0]]]) + off)[0]
                    rec['desc_y'], rec['desc_x'] = float(d[1]), float(d[0])
                    rec['dbottom'] = rec['desc_y'] - u['box'][3]
        records.append(rec)
    # the line: robust fit through the clean baselines, x-heights, the box angles, the box-to-ink shift
    clean = [r for r in records if r['base'] is not None and not (r['flags'] & UNCLEAN)]
    line = dict(n_units=len(units), n_clean=len(clean), angle=None, intercept=None, x_mid=None, resid_rms=None, xheight_med=None, xheight_mad=None,
                box_ls_angle=None, box_chord_angle=None, ink_dx=None, ink_dy=None, ink_z=None, scale=s, rotation_deg=rot, H_img=H_img)
    xb = np.array([(u['box'][0] + u['box'][2]) / 2 for u in units])
    yb = np.array([u['box'][3] for u in units])
    order = np.argsort(xb)
    if len(units) >= 2:
        fit = _robust_line(xb, yb)
        if fit:
            line['box_ls_angle'] = math.degrees(math.atan(fit[1]))
        i0, i1 = order[0], order[-1]
        if xb[i1] > xb[i0]:
            line['box_chord_angle'] = math.degrees(math.atan((yb[i1] - yb[i0]) / (xb[i1] - xb[i0])))
    if len(clean) >= 2:
        x = np.array([r['xc'] for r in clean])
        y = np.array([r['base'] for r in clean])
        fit = _robust_line(x, y)
        if fit:
            c0, c1 = fit
            line['x_mid'] = float(np.mean(x))
            line['intercept'] = float(c0 + c1 * line['x_mid'])
            line['angle'] = math.degrees(math.atan(c1))
            res = y - (c0 + c1 * x)
            line['resid_rms'] = float(np.sqrt(np.mean(res ** 2)))
            for r in clean:
                r['resid'] = float(r['base'] - (c0 + c1 * r['xc']))
        xh = np.array([r['xheight'] for r in clean])
        line['xheight_med'] = float(np.median(xh))
        line['xheight_mad'] = float(np.median(np.abs(xh - np.median(xh))))
    sh = box_ink_shift(ink, [b - np.array([X0c, Y0c, X0c, Y0c]) for b in boxes_img], H_img, p['shift_search_H'])
    if sh:
        # image-pixel shift -> recorded-frame px through the local Jacobian (rotation small: divide by the scale)
        line['ink_dx'], line['ink_dy'], line['ink_z'] = sh['dx'] / s, sh['dy'] / s, sh['z']
        line['ink_at_edge'] = sh['at_edge']
    return records, line


# ----------------------------------------------------------------------------- all pages
def _round(v, nd=1):
    return None if v is None else round(float(v), nd)


def page_heights(app, ms, orientations='horizontal') -> Dict[int, float]:
    units = line_units(app, ms, orientations=orientations)
    out = {}
    for p in _pages(ms):
        hs = [u['box'][3] - u['box'][1] for l in range(p['start_line'], p['end_line']) for u in units[l]]
        out[p['index']] = float(np.median(hs)) if hs else float('nan')
    return out


def measure_pages(app, ms, folios: Optional[Sequence[str]] = None, source: str = 'beinecke', out=None, params: Optional[dict] = None, log=print,
                  review: Optional[dict] = None, orientations='horizontal') -> dict:
    """Register and measure every page (or `folios`) of a bundle on the page images; write the product to `out`
    (default: the data folder's manuscript/ink_measures.json.gz; False: do not write). Pages whose registration
    fails are recorded under `pages` with ok=False and no records. The bundle should be the sensitivity one (the
    most complete reviewed geometry) in the recorded warp state; the product records its words' and geometry's
    digests and the frame tags. Lines outside `orientations` are not measured (counted under `skipped`)."""
    from .images import registration, page_image, Mapping, CREDIT
    from .audit.review import load_review
    from .frames import require_warp
    require_warp(app, 'recorded', 'the bundle to measure')
    p = dict(DEFAULTS, **(params or {}))
    review = review or load_review()
    pages = _pages(ms)
    lines_ms = _lines(ms)
    units = line_units(app, ms, orientations=orientations)
    H_of = page_heights(app, ms, orientations)
    want = set(folios) if folios else None
    product = dict(version=VERSION, source=source, params=dict(p, pad_H=list(p['pad_H'])), date=date.today().isoformat(), policy=app.get('policy'),
                   bundle_pages=app.get('pages'), bundle_order=app.get('order'),
                   words_sha256=digest(app['words']), geometry_sha256=digest(app['geometry']), credit=CREDIT,
                   frame='recorded', warp='recorded',
                   frame_note='recorded (the Voynichese XML pixel frame of each page); H = the page median rectangle height; angles positive = falling to the right',
                   flags={str(b): n for b, n in FLAG_NAMES.items()}, unit_fields=list(UNIT_FIELDS), line_fields=list(LINE_FIELDS),
                   skipped=getattr(units, 'skipped', None), pages={}, units={f: [] for f in UNIT_FIELDS}, lines={f: [] for f in LINE_FIELDS})
    n_done = 0
    t_all = time.time()
    for pg in pages:
        folio = pg['folio']
        if want and folio not in want:
            continue
        slots = [l for l in range(pg['start_line'], pg['end_line']) if units[l]]
        if not slots:
            product['pages'][folio] = dict(ok=False, reason='no located rectangles')
            continue
        t0 = time.time()
        rec = registration(folio, source, app, ms, review=review)
        summary = dict(ok=bool(rec.get('ok')), method=rec.get('method'), n_inliers=rec.get('n_inliers'), residual_px=rec.get('residual_px'), scale=rec.get('scale'),
                       rotation_deg=rec.get('rotation_deg'), shift_range_px=rec.get('shift_range_px'), shift_median_px=rec.get('shift_median_px'),
                       field_amplitude_px=rec.get('field_amplitude_px'), flags=list(rec.get('flags') or []), image_id=rec.get('image_id'),
                       H_px=H_of[pg['index']], n_lines=len(slots), n_units=0, n_clean=0,
                       skipped_lines=sum(1 for l in range(pg['start_line'], pg['end_line']) if not units[l] and any(app['geometry'][i] for i in range(app['lines'][l]['start'], app['lines'][l]['end']))))
        if not rec.get('ok'):
            summary['reason'] = 'registration failed'
            product['pages'][folio] = summary
            if log:
                log('%s: registration failed (%s)' % (folio, rec.get('flags')))
            continue
        img = page_image(folio, source, rec.get('image_id'))
        reg_poor = ('large_residual' in summary['flags']) or ('similarity_fallback' in summary['flags'])     # images.quality_flags: residual above 3 recorded px
        for l in slots:
            locus = str(app['lines'][l]['locus'])
            m = Mapping(rec, locus)
            words, line = measure_line(img, m, units[l], H_of[pg['index']], p, reg_poor=reg_poor)
            for r in words:
                for f in UNIT_FIELDS:
                    if f == 'line':
                        v = l
                    elif f == 'box_bottom':
                        v = _round(r['box'][3])
                    elif f == 'angle':
                        v = _round(r.get('angle_deg'), 2)
                    elif f == 'coverage':
                        v = _round(r.get('coverage'), 3)
                    elif f in ('first', 'last', 'n_ink', 'flags'):
                        v = int(r.get(f, 0))
                    else:
                        v = _round(r.get(f))
                    product['units'][f].append(v)
                summary['n_units'] += 1
                if r.get('base') is not None and not (r['flags'] & UNCLEAN):
                    summary['n_clean'] += 1
            sh = (rec.get('lines') or {}).get(locus) or {}
            sc = rec.get('scale') or 1.0
            L = dict(line=l, n_units=line.get('n_units', len(units[l])), n_clean=line.get('n_clean', 0), angle=_round(line.get('angle'), 2), intercept=_round(line.get('intercept')),
                     x_mid=_round(line.get('x_mid')), resid_rms=_round(line.get('resid_rms'), 2), xheight_med=_round(line.get('xheight_med')), xheight_mad=_round(line.get('xheight_mad'), 2),
                     box_ls_angle=_round(line.get('box_ls_angle'), 2), box_chord_angle=_round(line.get('box_chord_angle'), 2),
                     shift_dx=_round(sh.get('dx', 0.0) / sc, 2), shift_dy=_round(sh.get('dy', 0.0) / sc, 2), shift_n=int(sh.get('n', 0)),
                     ink_dx=_round(line.get('ink_dx'), 2), ink_dy=_round(line.get('ink_dy'), 2), ink_z=_round(line.get('ink_z'), 1))
            for f in LINE_FIELDS:
                product['lines'][f].append(L[f])
        summary['seconds'] = round(time.time() - t0, 1)
        product['pages'][folio] = summary
        n_done += 1
        if log:
            log('%s: %d lines, %d units, %d clean (%.0f%%), registration %s %d inliers %.2f px, %.1f s' % (
                folio, len(slots), summary['n_units'], summary['n_clean'], 100.0 * summary['n_clean'] / max(1, summary['n_units']), summary['method'],
                summary['n_inliers'] or 0, summary['residual_px'] or 0.0, summary['seconds']))
    product['n_pages_measured'] = n_done
    product['seconds'] = round(time.time() - t_all, 1)
    if app.get('spatialReview'):
        add_shape_keys(product, app)
    finalize(product, ms, H_of)
    if out is None:
        out = paths.data_dir() / PRODUCT_KEY
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        write_json(product, out)
        if log:
            log('wrote %s (%.2f MB): %d pages, %d units, pooled clean residual %.3f H' % (out, Path(out).stat().st_size / 2 ** 20, n_done, len(product['units']['first']),
                                                                                       product['residual_rms_H'] or float('nan')))
    return product


def finalize(product: dict, ms, H_of: Optional[Dict[int, float]] = None) -> dict:
    """Recompute the product's pooled within-line residual variance of the clean baselines (the weight of an ink
    baseline point, in H^2) from its records; call after `replace_pages`."""
    lines_ms = _lines(ms)
    if H_of is None:
        from .bundle import load_bundle
        H_of = page_heights(load_bundle(product.get('policy') or 'sensitivity', pages=product['bundle_pages'], order=product['bundle_order'], warp='recorded'), ms)
    res = []
    lines_by = {l: k for k, l in enumerate(product['lines']['line'])}
    U, li = product['units'], product['lines']
    for i in range(len(U['first'])):
        if U['base'][i] is None or U['flags'][i] & UNCLEAN:
            continue
        k = lines_by.get(U['line'][i])
        if k is None or li['angle'][k] is None or li['n_clean'][k] < 3:
            continue
        y_fit = li['intercept'][k] + math.tan(math.radians(li['angle'][k])) * (U['xc'][i] - li['x_mid'][k])
        res.append((U['base'][i] - y_fit) / H_of[lines_ms[U['line'][i]]['page']])
    product['residual_var_H2'] = float(np.mean(np.square(res))) if res else None
    product['residual_rms_H'] = float(math.sqrt(product['residual_var_H2'])) if res else None
    product['n_clean_residuals'] = len(res)
    product['n_pages_measured'] = sum(1 for v in product['pages'].values() if v.get('ok'))
    return product


def replace_pages(product: dict, part: dict) -> dict:
    """The product with the pages of `part` (a run on some folios of the same bundle) replacing its own records of
    those pages. Both carry `line_keys` (page, locus), so nothing here depends on the stream."""
    folios = set(part['pages'])
    out = dict(product)
    out['pages'] = dict(product['pages'])
    out['pages'].update(part['pages'])
    page_of = {l: k[0] for l, k in zip(product['lines']['line'], product['line_keys'])}
    keep_u = [i for i, l in enumerate(product['units']['line']) if page_of.get(l) not in folios]
    keep_l = [i for i, l in enumerate(product['lines']['line']) if page_of[l] not in folios]
    out['units'] = {f: [product['units'][f][i] for i in keep_u] + list(part['units'][f]) for f in UNIT_FIELDS}
    out['lines'] = {f: [product['lines'][f][i] for i in keep_l] + list(part['lines'][f]) for f in LINE_FIELDS}
    out['token_ids'] = [product['token_ids'][i] for i in keep_u] + list(part['token_ids'])
    out['line_keys'] = [product['line_keys'][i] for i in keep_l] + list(part['line_keys'])
    out['n_pages_measured'] = sum(1 for v in out['pages'].values() if v.get('ok'))
    return out


def merge_products(parts: Sequence[dict]) -> dict:
    """One product from several partial runs (different folios)."""
    out = dict(parts[0])
    out['pages'] = {}
    out['units'] = {f: [] for f in UNIT_FIELDS}
    out['lines'] = {f: [] for f in LINE_FIELDS}
    out['token_ids'], out['line_keys'] = [], []
    for p in parts:
        out['pages'].update(p['pages'])
        for f in UNIT_FIELDS:
            out['units'][f] += p['units'][f]
        for f in LINE_FIELDS:
            out['lines'][f] += p['lines'][f]
        out['token_ids'] += p['token_ids']
        out['line_keys'] += p['line_keys']
    out['n_pages_measured'] = sum(1 for v in out['pages'].values() if v.get('ok'))
    return out


def load_ink(path=None) -> dict:
    """The ink data product (``paths.resolve`` finds it in the data folder or the workspace), tagged (an older file
    without tags is recorded / recorded / beinecke)."""
    ink = read_json(path or paths.resolve(PRODUCT_KEY))
    from .frames import FRAMES, tags
    if ink.get('frame') not in FRAMES:
        ink['frame_note'] = ink.get('frame')
        ink['frame'] = 'recorded'
        ink['warp'] = tags(dict(frame=ink['frame_note'] or 'recorded'))['warp']
    tag(ink, frame='recorded', warp=ink.get('warp') or 'recorded', source=ink.get('source') or 'beinecke')
    return ink


def refit_lines(product: dict) -> dict:
    """The product's line table with angle, intercept, x_mid and resid_rms refitted (Huber line through the clean
    baselines of each line, as ``measure_line`` does); the other columns are kept. Used after a warp transform."""
    L = {f: list(v) for f, v in product['lines'].items()}
    U = product['units']
    by_line = defaultdict(list)
    for i in range(len(U['first'])):
        if U['base'][i] is not None and not (U['flags'][i] & UNCLEAN):
            by_line[U['line'][i]].append((U['xc'][i], U['base'][i]))
    for k, l in enumerate(L['line']):
        pts = by_line.get(l, [])
        if len(pts) < 2:
            continue
        x = np.array([p[0] for p in pts], float)
        y = np.array([p[1] for p in pts], float)
        fit = _robust_line(x, y)
        if not fit:
            continue
        c0, c1 = fit
        x_mid = float(np.mean(x))
        L['x_mid'][k] = _round(x_mid)
        L['intercept'][k] = _round(c0 + c1 * x_mid)
        L['angle'][k] = _round(math.degrees(math.atan(c1)), 2)
        L['resid_rms'][k] = _round(float(np.sqrt(np.mean((y - (c0 + c1 * x)) ** 2))), 2)
    return L


def ink_matches(ink: dict, app) -> bool:
    """True when the product was measured on this bundle's words (the geometry may differ: flattened). Another shape
    of the manuscript (other pages, another order) is aligned with ``for_bundle`` first."""
    return ink.get('words_sha256') == digest(app['words'])


_REMAP = {}


def for_bundle(ink: dict, app) -> dict:
    """The product with its token and line indices moved onto `app`'s stream, when the product was measured on
    another shape of the manuscript (other pages or another order): records are matched by the review's token ids
    (`token_ids`), lines by (page, locus) (`line_keys`). Records of tokens the bundle lacks are dropped. Returns `ink`
    itself when the words already match, or when the bundle carries no review block to match by."""
    if ink_matches(ink, app) or not app.get('spatialReview'):
        return ink
    key = (id(ink), id(app), len(app['words']))
    if key in _REMAP:
        return _REMAP[key]
    ids, line_keys = ink['token_ids'], ink['line_keys']
    pos = {t['id']: i for i, t in enumerate(app['spatialReview']['tokens'])}
    line_of = {(L['page'], str(L['locus'])): k for k, L in enumerate(app['lines'])}
    token_line = {}
    for k, L in enumerate(app['lines']):
        for i in range(L['start'], L['end']):
            token_line[i] = k
    out = dict(ink, units={f: [] for f in UNIT_FIELDS}, lines={f: [] for f in LINE_FIELDS})
    U = ink['units']
    keep_ids = []
    for r, tid in enumerate(ids):
        i = pos.get(tid)
        if i is None:
            continue
        span = U['last'][r] - U['first'][r]
        for f in UNIT_FIELDS:
            v = U[f][r]
            if f == 'first':
                v = i
            elif f == 'last':
                v = i + span
            elif f == 'line':
                v = token_line[i]
            out['units'][f].append(v)
        keep_ids.append(tid)
    Lk = ink['lines']
    kept_line_keys = []
    for r, (page, locus) in enumerate(line_keys):
        l = line_of.get((page, str(locus)))
        if l is None:
            continue
        for f in LINE_FIELDS:
            out['lines'][f].append(l if f == 'line' else Lk[f][r])
        kept_line_keys.append([page, locus])
    out['token_ids'] = keep_ids
    out['line_keys'] = kept_line_keys
    out['words_sha256'] = digest(app['words'])
    out['geometry_sha256'] = None
    out['bundle_pages'] = app.get('pages')
    out['bundle_order'] = app.get('order')
    out['remapped_from'] = dict(words_sha256=ink.get('words_sha256'), pages=ink.get('bundle_pages'), order=ink.get('bundle_order'), records=len(ids), kept=len(keep_ids))
    if len(_REMAP) > 8:
        _REMAP.clear()
    _REMAP[key] = out
    return out


def add_shape_keys(ink: dict, app: dict) -> dict:
    """Write `token_ids`, `line_keys`, `pages` and `order` into a product (in place) from the bundle it was measured
    on: the keys that tie its records to the manuscript whatever the stream. Returns the product."""
    if not ink_matches(ink, app):
        raise ValueError('the ink product was not measured on this bundle')
    tok = app['spatialReview']['tokens']
    ink['token_ids'] = [tok[i]['id'] for i in ink['units']['first']]
    ink['line_keys'] = [[app['lines'][l]['page'], app['lines'][l]['locus']] for l in ink['lines']['line']]
    ink['bundle_pages'] = app.get('pages')
    ink['bundle_order'] = app.get('order')
    return ink


def unit_index(ink: dict) -> Dict[int, int]:
    """Token index -> record index, for every token of every measured rectangle."""
    out = {}
    U = ink['units']
    for i, (a, b) in enumerate(zip(U['first'], U['last'])):
        for t in range(a, b + 1):
            out[t] = i
    return out


def unit_rows(ink: dict) -> List[dict]:
    """The records as dicts (one per rectangle)."""
    U = ink['units']
    n = len(U['first'])
    return [{f: U[f][i] for f in UNIT_FIELDS} for i in range(n)]


def line_rows(ink: dict) -> Dict[int, dict]:
    L = ink['lines']
    return {L['line'][i]: {f: L[f][i] for f in LINE_FIELDS} for i in range(len(L['line']))}


def baseline_points(ink: dict, app, H_of: Optional[Dict[int, float]] = None, ms=None) -> Dict[int, Tuple[float, float, float]]:
    """{first token of the rectangle: (x anchor = current box centre, baseline y under the CURRENT geometry, weight)}
    for every clean record whose rectangle is located in `app`. The ink baseline is stored in the recorded frame and
    travels with the box bottom (y = current bottom + (ink baseline - recorded bottom)), evaluated at the box centre
    along the word's own angle; the bundle and the product must share a frame and a warp state (``frames``). The
    weight is 1 / (pooled within-line residual variance in H^2)."""
    ink = for_bundle(ink, app)
    if not ink_matches(ink, app):
        raise ValueError('the ink product was measured on other words (words_sha256 differs)')
    check_same(app, ink, 'the bundle and the ink product')          # the baseline travels with its own box bottom: coherent in either state, but said
    var = ink.get('residual_var_H2') or 0.01
    w = 1.0 / var
    U = ink['units']
    out = {}
    for i in range(len(U['first'])):
        if U['base'][i] is None or U['flags'][i] & UNCLEAN:
            continue
        box = app['geometry'][U['first'][i]]
        if not box:
            continue
        xc_box = (box[0] + box[2]) / 2
        y = U['base'][i] + math.tan(math.radians(U['angle'][i] or 0.0)) * (xc_box - U['xc'][i]) + (box[3] - U['box_bottom'][i])
        out[U['first'][i]] = (float(xc_box), float(y), float(w))
    return out


# ----------------------------------------------------------------------------- intrusions and gaps
def _line_records(ink: dict, app, ms, H_of):
    """Per line: its records (dicts with frame values and H values) sorted by ink centre; the line fit."""
    rows = unit_rows(ink)
    lines = line_rows(ink)
    lines_ms = _lines(ms)
    by_line = defaultdict(list)
    for r in rows:
        if r['x0'] is None:
            continue
        H = H_of[lines_ms[r['line']]['page']]
        r = dict(r, H=H)
        L = lines.get(r['line'])
        if L and L['angle'] is not None and r['base'] is not None:
            r['resid_H'] = (r['base'] - (L['intercept'] + math.tan(math.radians(L['angle'])) * (r['xc'] - L['x_mid']))) / H
            r['xh_rel_H'] = (r['xheight'] - L['xheight_med']) / H if L['xheight_med'] is not None else None
        else:
            r['resid_H'] = None
            r['xh_rel_H'] = None
        by_line[r['line']].append(r)
    for l in by_line:
        by_line[l].sort(key=lambda r: (r['x0'] + r['x1']) / 2)
    return by_line, lines


def _line_ref(line: Optional[dict], key: str, x: float):
    """The line's fitted baseline ('base') or mean line ('mean') at x from the product's line record (the robust fit
    through its clean words' baselines, minus the line's median x-height for the mean line); None without a fit of
    three or more clean words."""
    if not line or line.get('angle') is None or (line.get('n_clean') or 0) < 3:
        return None
    y = line['intercept'] + math.tan(math.radians(line['angle'])) * (x - line['x_mid'])
    if key == 'mean':
        if line.get('xheight_med') is None:
            return None
        y -= line['xheight_med']
    return y


def _word_at(records: Sequence[dict], x: float, H: float):
    """The word whose ink extent (widened by 0.2 H) covers x, else the nearest word by centre; None when no words."""
    cov = [r for r in records if r['x0'] - 0.2 * H <= x <= r['x1'] + 0.2 * H]
    pool = cov or records
    return min(pool, key=lambda r: abs((r['x0'] + r['x1']) / 2 - x)) if pool else None


def intrusions(app, ms, ink: dict, margin_H: float = 0.05, min_overlap_px: float = 0.0, orientations='horizontal') -> List[dict]:
    """Descenders of an upper line reaching below the lower line's mean line (minus `margin_H` x H) and ascenders of
    a lower line reaching above the upper line's baseline (plus the margin), for consecutive lines of a paragraph on
    one page. The reference edges are the LINE's fitted baseline and mean line at that x (the robust fit through the
    line's clean words and its median x-height), never the word's own band, so that a word's own x-height or
    baseline, the outcomes a writing-order test looks at, cannot select it into the event set. Per event: direction
    ('down' = upper descender into the lower line, 'up' = lower ascender into the upper line), the two tokens (first
    token of each rectangle) and words, the horizontal overlap of the two ink extents (px), depth_H (beyond the other
    line's fitted edge; positive = inside), depth_word_H (the same against the other word's own band, for
    information), gap_H (the lower line's mean line minus the upper line's baseline at that x, from the line fits),
    the lower word's x-height minus its line's median (H) and baseline residual from its line's fit (H), touched (a
    merge flag on either word), folio, section, hand, the two line indices. Lines without a fit, and lines outside
    `orientations`, give no events. The bundle's positions are not read (only its words and heights): a warp
    mismatch with the product is a warning, not an error."""
    ink = for_bundle(ink, app)
    check_same(app, ink, 'the bundle and the ink product')
    from .geometry import orientation_mask
    keep, _ = orientation_mask(app, ms, orientations)
    H_of = page_heights(app, ms, orientations)
    by_line, lines = _line_records(ink, app, ms, H_of)
    lines_ms, pages = _lines(ms), _pages(ms)
    words = app['words']
    events = []
    for l in range(len(lines_ms) - 1):
        a, b = lines_ms[l], lines_ms[l + 1]
        if b.get('first') or a['page'] != b['page'] or l not in by_line or (l + 1) not in by_line:
            continue
        pg = pages[a['page']]
        if not (keep[l] and keep[l + 1]):
            continue
        Lu, Ll = lines.get(l), lines.get(l + 1)
        if _line_ref(Lu, 'base', 0.0) is None or _line_ref(Ll, 'mean', 0.0) is None:
            continue
        H = H_of[a['page']]
        up, lo = by_line[l], by_line[l + 1]
        base_info = dict(folio=pg['folio'], section=pg.get('section_name'), hand=pg.get('hand'), upper_line=l, lower_line=l + 1, H_px=H)
        for r in up:
            if r['desc_y'] is None or r['flags'] & (LITTLE_INK | NO_BAND | REGISTRATION):
                continue
            x = r['desc_x']
            mean_lo, base_up = _line_ref(Ll, 'mean', x), _line_ref(Lu, 'base', x)
            depth = (r['desc_y'] - mean_lo) / H
            if depth < -margin_H:
                continue
            under = _word_at(lo, x, H)
            if under is None:
                continue
            ov = min(r['x1'], under['x1']) - max(r['x0'], under['x0'])
            if ov < min_overlap_px:
                continue
            events.append(dict(base_info, direction='down', upper_token=r['first'], lower_token=under['first'], upper_word=words[r['first']], lower_word=words[under['first']],
                               x=x, overlap_px=float(ov), depth_H=float(depth), depth_word_H=float((r['desc_y'] - under['mean']) / H) if under.get('mean') is not None else None,
                               gap_H=float((mean_lo - base_up) / H), lower_xh_rel_H=under.get('xh_rel_H'), lower_resid_H=under.get('resid_H'),
                               upper_desc_depth_H=float((r['desc_y'] - r['base']) / H) if r['base'] is not None else None,
                               touched=bool((r['flags'] & TOUCH_BELOW) or (under['flags'] & TOUCH_ABOVE)), upper_flags=r['flags'], lower_flags=under['flags']))
        for r in lo:
            if r['asc_y'] is None or r['flags'] & (LITTLE_INK | NO_BAND | REGISTRATION):
                continue
            x = r['asc_x']
            base_up, mean_lo = _line_ref(Lu, 'base', x), _line_ref(Ll, 'mean', x)
            depth = (base_up - r['asc_y']) / H
            if depth < -margin_H:
                continue
            over = _word_at(up, x, H)
            if over is None:
                continue
            ov = min(r['x1'], over['x1']) - max(r['x0'], over['x0'])
            if ov < min_overlap_px:
                continue
            events.append(dict(base_info, direction='up', upper_token=over['first'], lower_token=r['first'], upper_word=words[over['first']], lower_word=words[r['first']],
                               x=x, overlap_px=float(ov), depth_H=float(depth), depth_word_H=float((over['base'] - r['asc_y']) / H) if over.get('base') is not None else None,
                               gap_H=float((mean_lo - base_up) / H), lower_xh_rel_H=r.get('xh_rel_H'), lower_resid_H=r.get('resid_H'),
                               lower_asc_height_H=float((r['mean'] - r['asc_y']) / H) if r['mean'] is not None else None,
                               touched=bool((r['flags'] & TOUCH_ABOVE) or (over['flags'] & TOUCH_BELOW)), upper_flags=over['flags'], lower_flags=r['flags']))
    return events


def gap_table(app, ms, ink: dict, events: Optional[List[dict]] = None, orientations='horizontal') -> List[dict]:
    """Per measured word of a line that follows another line of its paragraph: the gap to the previous line at the
    word's centre from the two LINE fits (lower mean line minus upper baseline, H; gap_word_H uses the word's own
    mean line instead), the word's x-height (H) and its deviation from the line's median, its baseline residual from
    the line fit (H), whether an upper-line descender bottom lies within the word's extent (under_descender), the
    deepest 'down' intrusion onto it (intrusion_depth_H, None when none), and the upper line's local descender depth
    above it. Lines without a fit, and lines outside `orientations`, are left out. The bundle's positions are not
    read: a warp mismatch with the product is a warning, not an error."""
    ink = for_bundle(ink, app)
    check_same(app, ink, 'the bundle and the ink product')
    from .geometry import orientation_mask
    keep, _ = orientation_mask(app, ms, orientations)
    H_of = page_heights(app, ms, orientations)
    by_line, lines = _line_records(ink, app, ms, H_of)
    lines_ms, pages = _lines(ms), _pages(ms)
    words = app['words']
    deepest = {}
    for e in events or []:
        if e['direction'] == 'down':
            k = e['lower_token']
            deepest[k] = max(deepest.get(k, -9.0), e['depth_H'])
    rows = []
    for l in range(1, len(lines_ms)):
        a, b = lines_ms[l - 1], lines_ms[l]
        if b.get('first') or a['page'] != b['page'] or l not in by_line or (l - 1) not in by_line:
            continue
        pg = pages[b['page']]
        if not (keep[l] and keep[l - 1]):
            continue
        Lu, Ll = lines.get(l - 1), lines.get(l)
        if _line_ref(Lu, 'base', 0.0) is None or _line_ref(Ll, 'mean', 0.0) is None:
            continue
        H = H_of[b['page']]
        up = by_line[l - 1]
        for r in by_line[l]:
            if r['mean'] is None or r['flags'] & UNCLEAN:
                continue
            x = (r['x0'] + r['x1']) / 2
            base_up, mean_lo = _line_ref(Lu, 'base', x), _line_ref(Ll, 'mean', x)
            desc_over = [q for q in up if q['desc_x'] is not None and r['x0'] <= q['desc_x'] <= r['x1']]
            depths = [(q['desc_y'] - q['base']) / H for q in desc_over if q['base'] is not None]
            rows.append(dict(folio=pg['folio'], section=pg.get('section_name'), hand=pg.get('hand'), line=l, upper_line=l - 1, token=r['first'], word=words[r['first']], x=x,
                             gap_H=float((mean_lo - base_up) / H), gap_word_H=float((r['mean'] - base_up) / H), xheight_H=r['xheight'] / H, xh_rel_H=r.get('xh_rel_H'), resid_H=r.get('resid_H'),
                             under_descender=bool(desc_over), upper_desc_depth_H=max(depths) if depths else None,
                             intrusion_depth_H=deepest.get(r['first']), flags=r['flags'], touched=bool(r['flags'] & TOUCH_ABOVE)))
    return rows


def summary(ink: dict, ms=None) -> dict:
    """Counts over the product: pages measured / failed, units, clean share, flags, per section when `ms` is given."""
    U = ink['units']
    n = len(U['first'])
    flags = Counter()
    for f in U['flags']:
        for nme in flag_names(f):
            flags[nme] += 1
    clean = sum(1 for i in range(n) if U['base'][i] is not None and not (U['flags'][i] & UNCLEAN))
    out = dict(pages_measured=sum(1 for v in ink['pages'].values() if v.get('ok')), pages_failed=sorted(k for k, v in ink['pages'].items() if not v.get('ok')),
               units=n, clean=clean, clean_share=(clean / n) if n >= 20 else None, flags=dict(flags), residual_rms_H=ink.get('residual_rms_H'))
    if ms is not None:
        lines_ms, pages = _lines(ms), _pages(ms)
        by = defaultdict(lambda: [0, 0])
        for i in range(n):
            sec = pages[lines_ms[U['line'][i]]['page']].get('section_name')
            by[sec][0] += 1
            if U['base'][i] is not None and not (U['flags'][i] & UNCLEAN):
                by[sec][1] += 1
        out['by_section'] = {s: dict(units=v[0], clean=v[1], share=(v[1] / v[0]) if v[0] >= 20 else None) for s, v in sorted(by.items())}
    return out
