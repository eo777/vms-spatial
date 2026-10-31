"""Word regions on page images that the Voynichese Project did not record (the Rosettes foldout, f116v).

The goal is not optical character recognition: the transcription already says which words stand where (locus types,
Petersen's circle:label numbers, clock positions of the circular texts). These functions find candidate word
rectangles on the image and link the transcribed words to them, in two layers:

* rings: a circular text is unwrapped (`unwrap`) into a straight strip around the rosette's centre, the ink profile
  along the strip is cut at the gaps between words, and the cuts are matched to the transcribed words by their
  glyph counts (`strip_words`): a word's width is close to proportional to its number of glyphs, so the N-word
  segmentation whose widths fit the N glyph counts best is chosen, splitting runs that the gaps did not separate
  and merging runs that a gap inside a word separated. Boxes return to image coordinates through the polar map.
* free text (labels, floating paragraphs): candidate rectangles from a text detector (`craft_candidates`, the CRAFT
  character-region detector in EasyOCR, run in tiles; or `ink_components`, plain connected components of the ink
  mask merged along their reading direction) are assigned to the transcribed labels of a region by an order-
  preserving alignment (`assign_sequence`) under an ordering hypothesis (clockwise around the rosette, or reading
  order), again scored by glyph count against width.

Every assignment carries a `confidence` in [0, 1] and a `method`, and the output is a geometry supplement with its
own provenance (`geometry_kind='detected'`), never mixed silently with the recorded rectangles. Review the result on
the image before using it in a statistic (scripts/rosettes_geometry.py draws the overlay).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None


def _need_cv2():
    if cv2 is None:
        raise ImportError('vmsspatial.segment needs opencv-python (pip install opencv-python-headless)')


# ---------------------------------------------------------------- image basics
def load_gray(path) -> np.ndarray:
    """The page image as an 8-bit grey array (PIL, so very large JPEGs load)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    return np.asarray(Image.open(path).convert('L'))


def ink_mask(gray: np.ndarray, block: int = 61, offset: int = 32, blur: int = 3) -> np.ndarray:
    """Ink = darker than the local background by `offset` grey levels (adaptive threshold on a `block` window,
    after a small median blur against parchment grain). Returns a uint8 mask with 1 on ink."""
    _need_cv2()
    block = block | 1
    g = cv2.medianBlur(gray, blur | 1) if blur else gray
    return cv2.adaptiveThreshold(g, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, offset)


# ---------------------------------------------------------------- rings
@dataclass
class Ring:
    """A circular text: centre, inner and outer radius of the text band (pixels), the angle where the text starts
    (degrees clockwise from 12 o'clock) and its direction."""
    cx: float
    cy: float
    r0: float
    r1: float
    start_deg: float = 0.0
    clockwise: bool = True
    name: str = ''
    r0_end: Optional[float] = None     # a spiral: the band moves linearly from (r0, r1) to (r0_end, r1_end)
    r1_end: Optional[float] = None
    turns: float = 1.0                 # angular extent in turns

    def as_dict(self):
        return asdict(self)


def clock_to_deg(clock: str) -> float:
    """'10:30' -> 315 degrees clockwise from 12 o'clock."""
    h, m = clock.split(':')
    return ((int(h) % 12) * 60 + int(m)) / 720.0 * 360.0


def radial_profile(mask: np.ndarray, cx: float, cy: float, r_max: int, step: int = 2) -> np.ndarray:
    """Mean ink per radius bin around (cx, cy): the text ring and the drawn circles show as peaks."""
    r_max = int(r_max)
    y0, y1 = max(0, int(cy - r_max)), min(mask.shape[0], int(cy + r_max) + 1)
    x0, x1 = max(0, int(cx - r_max)), min(mask.shape[1], int(cx + r_max) + 1)
    sub = mask[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    rr = np.hypot(xx - cx, yy - cy)
    bins = (rr / step).astype(int)
    keep = bins < r_max // step
    sums = np.bincount(bins[keep], weights=sub[keep], minlength=r_max // step)
    counts = np.bincount(bins[keep], minlength=r_max // step)
    return sums / np.maximum(counts, 1)


def refine_centre(mask: np.ndarray, cx: float, cy: float, r: float, search: int = 72, step: int = 8, down: int = 4) -> Tuple[float, float, float]:
    """Move the centre on a grid so that the radial ink profile between 0.7r and 1.3r is sharpest (highest peak
    contrast): a circle drawn around the true centre gives a narrow, tall peak. Works on a `down`-sampled mask,
    then refines at full resolution within one coarse step. Returns (cx, cy, score)."""
    _need_cv2()
    small = cv2.resize(mask, (mask.shape[1] // down, mask.shape[0] // down), interpolation=cv2.INTER_AREA)

    def score_at(m, x, y, rad, step_px):
        prof = radial_profile(m, x, y, int(1.35 * rad), step_px)
        lo, hi = int(0.7 * rad / step_px), int(1.3 * rad / step_px)
        seg = prof[lo:hi]
        return float(seg.max() - np.median(seg)) if len(seg) else -1.0

    best = (cx, cy, -1.0)
    for dy in range(-search, search + 1, step):
        for dx in range(-search, search + 1, step):
            sc = score_at(small, (cx + dx) / down, (cy + dy) / down, r / down, 1)
            if sc > best[2]:
                best = (cx + dx, cy + dy, sc)
    bx, by, _ = best
    fine = (bx, by, -1.0)
    for dy in range(-step, step + 1, 2):
        for dx in range(-step, step + 1, 2):
            sc = score_at(mask, bx + dx, by + dy, r, 2)
            if sc > fine[2]:
                fine = (bx + dx, by + dy, sc)
    return fine


def band_from_candidates(candidates: Sequence[dict], cx: float, cy: float, r_lo: float, r_hi: float, min_count: int = 6) -> Optional[Tuple[float, float]]:
    """The radial band of a text ring from detector candidates: the densest cluster of candidate centres by radius
    between r_lo and r_hi (bins of a median candidate height), padded by half a height. None when too few
    candidates lie in the range."""
    rad, hts = [], []
    for c in candidates:
        b = c['box']
        r = math.hypot((b[0] + b[2]) / 2 - cx, (b[1] + b[3]) / 2 - cy)
        if r_lo <= r <= r_hi:
            rad.append(r)
            hts.append(min(b[2] - b[0], b[3] - b[1]))
    if len(rad) < min_count:
        return None
    h = float(np.median(hts))
    bins = np.arange(r_lo, r_hi + h, max(4.0, h / 2))
    counts, edges = np.histogram(rad, bins)
    k = int(np.argmax(counts))
    lo, hi = edges[k], edges[k + 1]
    # grow while neighbouring bins keep a third of the peak
    while k > 0 and counts[k - 1] >= counts.max() / 3:
        k -= 1
        lo = edges[k]
    k2 = int(np.argmax(counts))
    while k2 + 1 < len(counts) and counts[k2 + 1] >= counts.max() / 3:
        k2 += 1
        hi = edges[k2 + 1]
    sel = [r for r in rad if lo <= r <= hi]
    centre = float(np.median(sel))
    return max(r_lo, centre - 0.9 * h), min(r_hi, centre + 0.9 * h)


def text_band(mask: np.ndarray, cx: float, cy: float, r_lo: float, r_hi: float, step: int = 2, min_height: int = 24) -> Tuple[float, float]:
    """The radial extent [r0, r1] of the text ring between r_lo and r_hi.

    On these diagrams the text ring is the OUTERMOST sharp peak of the radial ink profile: the drawn border
    (scallops, hairs, dots) lies inside it and the parchment outside it is near the background level. The profile
    is smoothed, the background is the median of the outer fifth of the range, and the band is the stretch around
    the outermost peak (at least 0.35 of the way from background to the peak) that stays above background plus a
    quarter of the peak's height, padded by a quarter of the text height."""
    prof = radial_profile(mask, cx, cy, int(r_hi) + 8, step)
    lo, hi = int(r_lo / step), int(r_hi / step)
    seg = prof[lo:hi].copy()
    if len(seg) < 5:
        return r_lo, r_hi
    k = np.ones(3) / 3
    sm = np.convolve(seg, k, mode='same')
    background = float(np.median(sm[int(0.8 * len(sm)):]))
    peak_h = float(sm.max() - background)
    thr = background + 0.35 * peak_h
    peaks = [i for i in range(1, len(sm) - 1) if sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1] and sm[i] >= thr]
    if not peaks:
        return r_lo, r_hi
    p = peaks[-1]
    floor = background + 0.25 * (sm[p] - background)
    a = p
    while a > 0 and sm[a - 1] >= floor:
        a -= 1
    b = p
    while b + 1 < len(sm) and sm[b + 1] >= floor:
        b += 1
    r0, r1 = (lo + a) * step, (lo + b + 1) * step
    if r1 - r0 < min_height:
        c = (r0 + r1) / 2
        r0, r1 = c - min_height / 2, c + min_height / 2
    pad = 0.25 * (r1 - r0)
    return max(r_lo, r0 - pad), min(r_hi, r1 + pad)


def unwrap(image: np.ndarray, ring: Ring, radial_px: Optional[int] = None):
    """Straighten the band r0..r1 around the centre into a strip: columns run along the text in reading direction
    from the start angle, rows run outward (outer edge at the top, so the writing is upright when read from outside
    the circle). Returns (strip, to_image) where to_image(col, row) gives image coordinates."""
    _need_cv2()
    r0, r1 = ring.r0, ring.r1
    r0e, r1e = (ring.r0_end if ring.r0_end is not None else r0), (ring.r1_end if ring.r1_end is not None else r1)
    n_rad = radial_px or int(round(max(r1 - r0, r1e - r0e)))
    mean_r = (r0 + r1 + r0e + r1e) / 4
    n_ang = int(round(2 * math.pi * mean_r * ring.turns))
    # angle of each column: start at start_deg (clockwise from 12 o'clock), advancing in reading direction
    sign = 1.0 if ring.clockwise else -1.0
    cols = np.arange(n_ang)
    frac = cols / n_ang
    theta = np.deg2rad(ring.start_deg) + sign * 2 * math.pi * ring.turns * frac       # clockwise from 12 o'clock
    # image coordinates: clockwise from 12 o'clock means x = cx + r sin(theta), y = cy - r cos(theta)
    rows = np.arange(n_rad)
    inner = r0 + (r0e - r0) * frac                                                    # per column (spiral)
    outer = r1 + (r1e - r1) * frac
    radii = outer[None, :] - (outer - inner)[None, :] * ((rows + 0.5) / n_rad)[:, None]   # outer edge at the top
    sin_t, cos_t = np.sin(theta), np.cos(theta)
    map_x = (ring.cx + radii * sin_t[None, :]).astype(np.float32)
    map_y = (ring.cy - radii * cos_t[None, :]).astype(np.float32)
    strip = cv2.remap(image, map_x, map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def to_image(col: float, row: float) -> Tuple[float, float]:
        fr = col / n_ang
        t = np.deg2rad(ring.start_deg) + sign * 2 * math.pi * ring.turns * fr
        o, i = r1 + (r1e - r1) * fr, r0 + (r0e - r0) * fr
        r = o - (o - i) * row / n_rad
        return ring.cx + r * math.sin(t), ring.cy - r * math.cos(t)

    return strip, to_image


def strip_boxes_to_image(segments: Sequence[Tuple[int, int]], rows: Tuple[int, int], to_image, samples: int = 9) -> List[List[int]]:
    """Axis-aligned image boxes of strip segments [c0, c1) over rows [top, bottom): the bounding box of the
    segment's polygon sampled along its two arcs."""
    out = []
    top, bottom = rows
    for c0, c1 in segments:
        pts = []
        for c in np.linspace(c0, c1, samples):
            pts.append(to_image(c, top))
            pts.append(to_image(c, bottom))
        xs, ys = zip(*pts)
        out.append([int(math.floor(min(xs))), int(math.floor(min(ys))), int(math.ceil(max(xs))), int(math.ceil(max(ys)))])
    return out


# ---------------------------------------------------------------- strips: runs and the glyph-count fit
def ink_runs(mask_strip: np.ndarray, rows: Optional[Tuple[int, int]] = None, min_gap: int = 3, min_run: int = 4) -> List[Tuple[int, int]]:
    """Column runs of ink in a strip (within `rows`), gaps shorter than `min_gap` closed, runs shorter than
    `min_run` dropped. Returns [(c0, c1), ...] half-open."""
    sub = mask_strip if rows is None else mask_strip[rows[0]:rows[1]]
    col = sub.sum(axis=0) > 0
    runs, i, n = [], 0, len(col)
    while i < n:
        if col[i]:
            j = i
            while j < n and col[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a, b) for a, b in merged if b - a >= min_run]


def text_rows(mask_strip: np.ndarray, min_frac: float = 0.25) -> Tuple[int, int]:
    """The row band of the strip that carries the text: rows whose ink share is at least `min_frac` of the
    densest row, the longest such run."""
    prof = mask_strip.sum(axis=1).astype(float)
    if prof.max() <= 0:
        return 0, mask_strip.shape[0]
    above = prof >= min_frac * prof.max()
    best, cur, start = (0, 0, 0), 0, 0
    for i, a in enumerate(above):
        if a:
            if cur == 0:
                start = i
            cur += 1
            if cur > best[0]:
                best = (cur, start, i)
        else:
            cur = 0
    return best[1], best[2] + 1


def fit_widths(runs: Sequence[Tuple[int, int]], glyphs: Sequence[int], gap_cost: float = 0.6) -> Tuple[List[Tuple[int, int]], float]:
    """Cut the ordered ink runs into len(glyphs) consecutive words so that each word's width fits its glyph count.

    Dynamic programme over (run index, word index): a word takes one or more consecutive runs (merging a gap
    inside a word costs `gap_cost` per merged gap, in units of the per-glyph width), and a run may be split
    between two or more words when it is wider than its share (the split falls at the proportional position,
    cost 1 per split). The per-glyph width is estimated from the total ink width over the total glyph count.
    Returns (segments, mean absolute width error in glyph units)."""
    runs = [tuple(r) for r in runs]
    n, m = len(runs), len(glyphs)
    if not n or not m:
        return [], float('inf')
    total_w = sum(b - a for a, b in runs)
    per_glyph = total_w / max(1, sum(glyphs))
    exp = [g * per_glyph for g in glyphs]
    INF = float('inf')
    # state: after assigning words 0..j-1 using runs 0..i-1 (whole runs); plus partial-run states handled by
    # splitting: a run wider than 1.6x its word is split proportionally among consecutive words.
    # To keep it tractable we first expand wide runs into virtual sub-runs by the glyph shares of candidate words
    # at alignment time: approximate by allowing a run to cover k consecutive words (k>=1) with split penalty k-1.
    best = {(0, 0): (0.0, None)}
    for i in range(n):
        for j in range(m):
            if (i, j) not in best:
                continue
            cost0 = best[(i, j)][0]
            # option A: word j takes runs i..i2 (merging)
            w = 0
            for i2 in range(i, min(n, i + 6)):
                w += runs[i2][1] - runs[i2][0]
                if i2 > i:
                    w += runs[i2][0] - runs[i2 - 1][1]
                c = cost0 + abs(w - exp[j]) / per_glyph + gap_cost * (i2 - i)
                key = (i2 + 1, j + 1)
                if c < best.get(key, (INF,))[0]:
                    best[key] = (c, ('merge', i, j, i2))
                if w > exp[j] * 2.5:
                    break
            # option B: run i is split among words j..j2 (k >= 2)
            w = runs[i][1] - runs[i][0]
            share = 0
            for j2 in range(j, min(m, j + 6)):
                share += exp[j2]
                if j2 > j:
                    c = cost0 + abs(w - share) / per_glyph + 1.0 * (j2 - j)
                    key = (i + 1, j2 + 1)
                    if c < best.get(key, (INF,))[0]:
                        best[key] = (c, ('split', i, j, j2))
                if share > w * 2.5:
                    break
    if (n, m) not in best:
        return [], INF
    # back-track
    segs = [None] * m
    key = (n, m)
    while key != (0, 0):
        c, move = best[key]
        if move[0] == 'merge':
            _, i, j, i2 = move
            segs[j] = (runs[i][0], runs[i2][1])
            key = (i, j)
        else:
            _, i, j, j2 = move
            a, b = runs[i]
            shares = exp[j:j2 + 1]
            tot = sum(shares)
            pos = a
            for k, s in enumerate(shares):
                nxt = b if k == len(shares) - 1 else pos + (b - a) * s / tot
                segs[j + k] = (int(round(pos)), int(round(nxt)))
                pos = nxt
            key = (i, j)
    err = np.mean([abs((b - a) - e) / per_glyph for (a, b), e in zip(segs, exp)])
    return segs, float(err)


def strip_words(mask_strip: np.ndarray, glyphs: Sequence[int], rows: Optional[Tuple[int, int]] = None,
                min_gap_range: Sequence[int] = (3, 5, 7, 9, 12, 15)) -> Dict:
    """Word segments of a strip for the transcribed words (glyph counts), trying several gap closings and keeping
    the one whose fit is best; `confidence` is 1/(1+error) scaled by how well the run count matched."""
    rows = rows or text_rows(mask_strip)
    best = None
    for g in min_gap_range:
        runs = ink_runs(mask_strip, rows, min_gap=g)
        if not runs:
            continue
        segs, err = fit_widths(runs, glyphs)
        if not segs:
            continue
        count_pen = abs(len(runs) - len(glyphs)) / max(1, len(glyphs))
        score = err + 0.5 * count_pen
        if best is None or score < best['score']:
            best = dict(segments=segs, error=err, runs=len(runs), min_gap=g, rows=rows, score=score)
    if best is None:
        return dict(segments=[], error=float('inf'), runs=0, rows=rows, confidence=0.0)
    best['confidence'] = float(1.0 / (1.0 + best['error']) * (1.0 - min(0.5, 0.5 * abs(best['runs'] - len(glyphs)) / max(1, len(glyphs)))))
    return best


# ---------------------------------------------------------------- free-text candidates
def craft_candidates(image_path, cache: Optional[Path] = None, tile: int = 2000, overlap: int = 300, gpu: bool = False,
                     params: Optional[dict] = None, log=None) -> List[dict]:
    """Candidate word rectangles from the CRAFT detector (EasyOCR, recognizer off) over the whole image in
    overlapping tiles, cached as JSON. Each candidate: {box: [x0, y0, x1, y1], kind: 'h' | 'f', poly?}."""
    cache = Path(cache) if cache else None
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))['boxes']
    import easyocr  # noqa: optional heavy dependency
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = np.asarray(Image.open(image_path).convert('RGB'))
    H, W = im.shape[:2]
    p = dict(text_threshold=0.45, low_text=0.3, link_threshold=0.35, canvas_size=3000, mag_ratio=1.5, slope_ths=0.2,
             ycenter_ths=0.5, height_ths=0.6, width_ths=0.4, add_margin=0.04)
    p.update(params or {})
    reader = easyocr.Reader(['en'], gpu=gpu, recognizer=False, verbose=False)
    boxes = []
    for y in range(0, max(1, H - overlap), tile - overlap):
        for x in range(0, max(1, W - overlap), tile - overlap):
            crop = im[y:min(H, y + tile), x:min(W, x + tile)]
            h, f = reader.detect(crop, **p)
            for x0, x1, y0, y1 in h[0]:
                boxes.append(dict(kind='h', box=[int(x0) + x, int(y0) + y, int(x1) + x, int(y1) + y]))
            for poly in f[0]:
                pts = np.array(poly, dtype=float).reshape(-1, 2) + [x, y]
                boxes.append(dict(kind='f', poly=pts.round().astype(int).tolist(),
                                  box=[int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())]))
            if log:
                log('tile %d,%d: %d candidates' % (x, y, len(h[0]) + len(f[0])))
    if cache:
        cache.write_text(json.dumps(dict(width=W, height=H, tile=tile, overlap=overlap, params=p, boxes=boxes)), encoding='utf-8')
    return boxes


def dedupe_boxes(boxes: Sequence[dict], iou: float = 0.5) -> List[dict]:
    """Drop near-duplicate candidates from overlapping tiles (keep the larger of two boxes with IoU >= `iou`)."""
    kept: List[dict] = []
    for b in sorted(boxes, key=lambda b: -(b['box'][2] - b['box'][0]) * (b['box'][3] - b['box'][1])):
        x0, y0, x1, y1 = b['box']
        dup = False
        for k in kept:
            a0, b0, a1, b1 = k['box']
            iw, ih = min(x1, a1) - max(x0, a0), min(y1, b1) - max(y0, b0)
            if iw <= 0 or ih <= 0:
                continue
            inter = iw * ih
            union = (x1 - x0) * (y1 - y0) + (a1 - a0) * (b1 - b0) - inter
            if inter / union >= iou or inter >= 0.8 * (x1 - x0) * (y1 - y0):
                dup = True
                break
        if not dup:
            kept.append(b)
    return kept


def ink_components(mask: np.ndarray, min_area: int = 30, max_height: int = 90, join: int = 12) -> List[dict]:
    """Word candidates from connected ink components: components joined when closer than `join` pixels along the
    row direction, dropped when taller than `max_height` (drawings) or smaller than `min_area`."""
    _need_cv2()
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (join, max(1, join // 3)))
    joined = cv2.dilate(mask, kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area or h > max_height:
            continue
        out.append(dict(kind='c', box=[int(x), int(y), int(x + w), int(y + h)]))
    return out


# ---------------------------------------------------------------- assignment of labels to candidates
def box_angle(box: Sequence[float], cx: float, cy: float) -> float:
    """Degrees clockwise from 12 o'clock of a box's centre around (cx, cy)."""
    x, y = (box[0] + box[2]) / 2 - cx, (box[1] + box[3]) / 2 - cy
    return (math.degrees(math.atan2(x, -y)) + 360.0) % 360.0


def assign_sequence(items: Sequence[dict], candidates: Sequence[dict], per_glyph: float, skip_cost: float = 0.45,
                    unmatched_cost: float = 2.0) -> Tuple[List[Optional[int]], float]:
    """Order-preserving alignment of transcribed items ({glyphs, ...}) to ordered candidates ({box}): each item
    takes one candidate, or none (cost `unmatched_cost`); candidates may be skipped (cost `skip_cost`, cheaper
    for small boxes); the match cost is the width error in glyph units. Returns (candidate index per item or
    None, total cost)."""
    n, m = len(items), len(candidates)
    INF = float('inf')
    widths = [c['box'][2] - c['box'][0] for c in candidates]
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c = dp[i][j]
            if c == INF:
                continue
            if j < m:   # skip candidate j
                pen = skip_cost * min(1.0, widths[j] / max(1.0, 3 * per_glyph))
                if c + pen < dp[i][j + 1]:
                    dp[i][j + 1] = c + pen
                    back[i][j + 1] = (i, j, 'skip')
            if i < n:   # item i unmatched
                if c + unmatched_cost < dp[i + 1][j]:
                    dp[i + 1][j] = c + unmatched_cost
                    back[i + 1][j] = (i, j, 'none')
            if i < n and j < m:
                err = abs(widths[j] - items[i]['glyphs'] * per_glyph) / per_glyph
                if c + err < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = c + err
                    back[i + 1][j + 1] = (i, j, 'match')
    out: List[Optional[int]] = [None] * n
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj, move = back[i][j]
        if move == 'match':
            out[pi] = pj
        i, j = pi, pj
    return out, dp[n][m]


def clusters(candidates: Sequence[dict], factor: float = 1.6) -> List[List[dict]]:
    """Groups of candidates whose boxes lie within `factor` median heights of each other (single linkage): a
    column of label lines or a floating paragraph becomes one group."""
    n = len(candidates)
    if not n:
        return []
    h = float(np.median([c['box'][3] - c['box'][1] for c in candidates]))
    reach = factor * max(1.0, h)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        a = candidates[i]['box']
        for j in range(i + 1, n):
            b = candidates[j]['box']
            dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
            dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
            if math.hypot(dx, dy) <= reach:
                parent[find(i)] = find(j)
    groups: Dict[int, List[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(candidates[i])
    return list(groups.values())


def reading_order(candidates: Sequence[dict]) -> List[dict]:
    heights = [c['box'][3] - c['box'][1] for c in candidates] or [20]
    h = float(np.median(heights))
    return sorted(candidates, key=lambda c: (round((c['box'][1] + c['box'][3]) / 2 / max(1.0, h)), c['box'][0]))


def order_candidates(candidates: Sequence[dict], hypothesis: str, cx: float = 0, cy: float = 0, start_deg: float = 0) -> List[dict]:
    """Candidates in the order an ordering hypothesis predicts: 'cw' / 'ccw' around (cx, cy) from start_deg, with
    each cluster of adjacent candidates (a column of lines, a paragraph) kept together in reading order at the
    angle of its centroid; or 'reading' (top to bottom, then left to right, rows grouped by a median height)."""
    if hypothesis in ('cw', 'ccw'):
        def angle_of(box):
            a = (box_angle(box, cx, cy) - start_deg) % 360.0
            return a if hypothesis == 'cw' else (360.0 - a) % 360.0
        out = []
        for group in sorted(clusters(candidates), key=lambda g: angle_of([min(c['box'][0] for c in g), min(c['box'][1] for c in g), max(c['box'][2] for c in g), max(c['box'][3] for c in g)])):
            out.extend(reading_order(group))
        return out
    return reading_order(candidates)


def best_assignment(items: Sequence[dict], candidates: Sequence[dict], per_glyph: float, cx: float, cy: float,
                    hypotheses: Sequence[str] = ('cw', 'ccw', 'reading'), starts: Sequence[float] = (0, 90, 180, 270)) -> dict:
    """Try every ordering hypothesis (and start angle for the circular ones) and keep the cheapest alignment."""
    best = None
    for hyp in hypotheses:
        for s in (starts if hyp in ('cw', 'ccw') else (0,)):
            ordered = order_candidates(candidates, hyp, cx, cy, s)
            assign, cost = assign_sequence(items, ordered, per_glyph)
            matched = sum(1 for a in assign if a is not None)
            if best is None or cost < best['cost']:
                errs = [abs((ordered[a]['box'][2] - ordered[a]['box'][0]) - it['glyphs'] * per_glyph) / per_glyph for it, a in zip(items, assign) if a is not None]
                best = dict(hypothesis=hyp, start=s, cost=cost, matched=matched, width_error=float(np.mean(errs)) if errs else float('inf'),
                            boxes=[ordered[a]['box'] if a is not None else None for a in assign])
    if best:
        n = max(1, len(items))
        # confidence: the matched share, discounted by the mean width error of the matches (in glyph units)
        best['confidence'] = float(best['matched'] / n / (1.0 + (best['width_error'] if math.isfinite(best['width_error']) else 9.0)))
    return best or dict(hypothesis=None, cost=float('inf'), matched=0, boxes=[None] * len(items), confidence=0.0)
