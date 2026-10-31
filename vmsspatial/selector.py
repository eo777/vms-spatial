"""Spatial source pools: which earlier (or later) words on the same page are "in view" of a target word.

The study selector (the governor app's ``sourcePool`` in ``js/sources.js``, ported here exactly): a word on an earlier
line is in view when its recorded rectangle intersects the cone of `depth` line spacings above the target with
half-angle `angle`; a word on the same line when its centre lies within `left` median word widths to the left. Weight =
alignment / (1 + distance)^2 (alignment = cos^2 of the angle off the vertical, 1 on the same line; distance in line
spacings above, in word widths on the line), or 1 with weight 'uniform'; the `cap` heaviest are kept. The page's median
word width and line pitch come from the recorded rectangles of that page.

THE WORD-LENGTH TRAP (28 October 2026, RESULTS section 7 item 9). With centre-to-centre same-line distance and
inverse-square weights, the left neighbour's centre lies closer when the target is short, so one word dominates the pool
of a short target and the pool's diversity rises with the target's own length, while repetition falls with it. On the
manuscript the raw contrast (+0.034) is mostly that instrument effect; it disappears inside exact length classes and
reappears, smaller, only under the joint length x pool-size control. Three selector-side remedies are built in, and the
statistics in ``stats.py`` add the length and pool-size strata:
    metric='edge'     width-neutral same-line distance: the gap between the two boxes in word widths, plus one, so an
                      adjacent word has distance 1 whatever the lengths (``WIDTH_NEUTRAL_SELECTOR``)
    target='cursor'   the source window is fixed before the target's width is known: the target is a provisional box one
                      median word wide at its left edge, a writing cursor (``CURSOR_SELECTOR``); the review named this
                      the selector a copying test needs
    weight='uniform'  every eligible word counts once (a control; must still be read at fixed pool size)

``PoolSpec`` also generalizes the shape (the geometry sweep): direction 'down' takes the tokens AFTER the target with
the cone below it and a reach to the right (the mirror used by the direction test); `depth` 0 restricts the pool to the
same line; `offset` displaces the cone's apex sideways.

Beyond pools, ``SpatialContext.candidates(i)`` returns every same-page word with its position relative to the target
(dx, dy in page units and in word widths / line spacings, line offset, rectangle), so any region check can be written
as a boolean mask over it; ``SpatialContext.select(i, mask)`` turns a mask into a pool.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional

import numpy as np

from .bundle import read_json


@dataclass(frozen=True)
class PoolSpec:
    direction: str = 'up'        # 'up': tokens before N, cone above, reach to the left; 'down': the mirror image
    left: float = 3.0            # same-line reach in median word widths (direction up)
    right: float = 0.0           # same-line reach to the right (direction down)
    depth: float = 8.0           # line spacings the cone reaches into the other lines; 0 = same line only
    angle: float = 45.0          # half-angle of the cone in degrees (0 = a vertical ray)
    offset: float = 0.0          # horizontal displacement of the cone's apex in word widths (negative = left)
    weight: str = 'distance'     # 'distance' (alignment / (1 + d)^2) or 'uniform'
    metric: str = 'centre'       # same-line distance: 'centre' (centre to centre) or 'edge' (gap between boxes + 1; width-neutral)
    target: str = 'box'          # 'box': the target's recorded rectangle; 'cursor': a provisional box one median word wide at its leading edge
    cap: int = 100               # the heaviest `cap` candidates are kept
    name: str = ''

    def mirror(self) -> 'PoolSpec':
        """The same shape on the other side of the target: tokens after N, cone below, reach to the right."""
        if self.direction == 'up':
            return replace(self, direction='down', right=self.left, left=0.0, name=(self.name + ' (mirror)').strip())
        return replace(self, direction='up', left=self.right, right=0.0, name=(self.name + ' (mirror)').strip())

    def width_neutral(self) -> 'PoolSpec':
        return replace(self, metric='edge', name=(self.name + ', width-neutral').strip(', '))

    def cursor(self) -> 'PoolSpec':
        return replace(self, target='cursor', name=(self.name + ', cursor target').strip(', '))

    def label(self) -> str:
        if self.name:
            return self.name
        side = ('left %g' % self.left) if self.direction == 'up' else ('right %g' % self.right)
        lines = ('%g lines %s, %g deg' % (self.depth, 'above' if self.direction == 'up' else 'below', self.angle)) if self.depth else 'same line only'
        extra = (' apex %+g words' % self.offset if self.offset else '') + (' uniform' if self.weight == 'uniform' else '') \
            + (' edge distance' if self.metric == 'edge' else '') + (' cursor target' if self.target == 'cursor' else '')
        return '%s + %s%s (cap %d)' % (side, lines, extra, self.cap)

    def as_dict(self) -> dict:
        return dict(name=self.label(), dir=self.direction, left=self.left, right=self.right, depth=self.depth, angle=self.angle,
                    offset=self.offset, weight=self.weight, metric=self.metric, target=self.target, cap=self.cap)


STUDY_SELECTOR = PoolSpec(name='study selector: left 3 + 8 lines above, 45')
WIDTH_NEUTRAL_SELECTOR = PoolSpec(metric='edge', name='study selector, width-neutral (gap distance)')
CURSOR_SELECTOR = PoolSpec(target='cursor', name='study selector, writing-cursor target')
LINES_ABOVE_ONLY = PoolSpec(left=0.0, name='lines above only (8)')
WINDOW_DIRECTIONS = ('backward', 'forward', 'centered')


@dataclass
class Pool:
    indices: np.ndarray          # token indices, ascending
    weights: np.ndarray
    available: int = 0           # eligible candidates before the cap
    missing_target: bool = False
    full: bool = True            # False for a reading-order window clipped at the stream's ends

    @property
    def n(self) -> int:
        return int(len(self.indices))


def _median(a):
    a = np.asarray([v for v in a if np.isfinite(v)], float)
    return float(np.median(a)) if len(a) else float('nan')


class SpatialContext:
    """Per-token centres, per-page word width and pitch, and the eligibility mask, from a bundle (``js/sources.js``
    ``prepare``, ported). policy: 'strict' (the bundle's geometry; a reviewed bundle's nulls are the exclusions) or
    'sensitivity' (the review's sensitivity geometry). A plain schema-2 bundle gets the page-relative size exclusion
    under every policy, as the viewer applies it."""

    def __init__(self, bundle: dict, policy: str = 'strict'):
        """The viewer's rules: the page-relative size exclusion for unreviewed geometry; line pitch from the median top
        and bottom of each line's boxes."""
        self.bundle = bundle
        self.policy = policy
        self.geometry_kind = bundle.get('geometry_kind', 'recorded' if bundle.get('spatialReview') else 'unknown')
        self.words: List[str] = bundle['words']
        self.n = len(self.words)
        self.lines = bundle['lines']
        review = bundle.get('spatialReview')
        reviewed = bool(review)
        if policy == 'sensitivity' and review:
            geometry = list(review['sensitivityGeometry'])
        else:
            geometry = list(bundle['geometry'])
        self.line_of = np.zeros(self.n, dtype=np.int32)
        self.page_id: List[str] = []
        page_lines: Dict[str, List[int]] = {}
        page_tokens: Dict[str, List[int]] = {}
        for k, L in enumerate(self.lines):
            self.line_of[L['start']:L['end']] = k
            page_lines.setdefault(L['page'], []).append(k)
            page_tokens.setdefault(L['page'], []).extend(range(L['start'], L['end']))
        self.page_of_line = [L['page'] for L in self.lines]
        self.excluded = set()
        if reviewed:
            for i, b in enumerate(geometry):
                if not b:
                    self.excluded.add(i)
        else:
            for page, idx in page_tokens.items():
                boxes = [geometry[i] for i in idx if geometry[i]]
                w = _median([b[2] - b[0] for b in boxes])
                h = _median([b[3] - b[1] for b in boxes])
                for i in idx:
                    b = geometry[i]
                    if b and (b[2] - b[0] > 6 * w or b[3] - b[1] > 2.5 * h):
                        self.excluded.add(i)
                        geometry[i] = None
        self.geometry = geometry
        self.box = np.full((self.n, 4), np.nan)
        for i, b in enumerate(geometry):
            if b:
                self.box[i] = b
        self.has_box = ~np.isnan(self.box[:, 0])
        self.cx = (self.box[:, 0] + self.box[:, 2]) / 2
        self.cy = (self.box[:, 1] + self.box[:, 3]) / 2
        self.pages: Dict[str, dict] = {}
        self.page_index_of_token = np.zeros(self.n, dtype=np.int32)
        for pk, (page, idx) in enumerate(page_tokens.items()):
            idx_arr = np.array(idx, dtype=np.int64)
            self.page_index_of_token[idx_arr] = pk
            boxed = idx_arr[self.has_box[idx_arr]]
            widths = self.box[boxed, 2] - self.box[boxed, 0]
            heights = self.box[boxed, 3] - self.box[boxed, 1]
            word_width = _median(widths)
            if not (word_width > 0):
                word_width = 1.0
            ys = []
            for k in page_lines[page]:
                L = self.lines[k]
                lb = np.arange(L['start'], L['end'])
                lb = lb[self.has_box[lb]]
                if not len(lb):
                    ys.append(float('nan'))
                else:
                    ys.append((_median(self.box[lb, 1]) + _median(self.box[lb, 3])) / 2)
            diffs = [b - a for a, b in zip(ys, ys[1:]) if np.isfinite(a) and np.isfinite(b) and b - a > 0]
            pitch = _median(diffs) if diffs else float('nan')
            if not (pitch > 0):
                pitch = _median(heights) * 1.6 if len(heights) else float('nan')
            if not (pitch > 0):
                pitch = 1.0
            self.pages[page] = dict(index=pk, indices=idx_arr, boxed=boxed, word_width=word_width, pitch=pitch, lines=page_lines[page])

    def describe(self) -> dict:
        """What this context measures on: say it in every report (geometry kind, policy, provenance)."""
        return dict(geometry_kind=self.geometry_kind, policy=self.policy, tokens=self.n, located=int(self.has_box.sum()),
                    excluded=len(self.excluded), provenance=self.bundle.get('geometry_provenance') or self.bundle.get('input_geometry_provenance'))

    # ---- geometry of a page
    def page_of(self, i: int) -> dict:
        return self.pages[self.page_of_line[self.line_of[i]]]

    def candidates(self, i: int, which: str = 'before') -> Optional[dict]:
        """Every boxed word on the target's page (before the target, after it, or all but it) with its geometry relative
        to the target: idx, dx, dy (page units; dy > 0 = the candidate lies ABOVE the target), dx_w (dx in word widths),
        dy_p (dy in line spacings), same_line, line_offset (transcription lines; negative = earlier line), distance_p
        (centre distance in line spacings), distance_w (same-line centre distance in word widths), box (n, 4).
        None when the target has no resolved rectangle."""
        if not self.has_box[i]:
            return None
        page = self.page_of(i)
        idx = page['boxed']
        if which == 'before':
            idx = idx[idx < i]
        elif which == 'after':
            idx = idx[idx > i]
        else:
            idx = idx[idx != i]
        tx, ty = self.cx[i], self.cy[i]
        dx = self.cx[idx] - tx
        dy = ty - self.cy[idx]
        W, pitch = page['word_width'], page['pitch']
        return dict(idx=idx, dx=dx, dy=dy, dx_w=dx / W, dy_p=dy / pitch, same_line=self.line_of[idx] == self.line_of[i],
                    line_offset=self.line_of[idx] - self.line_of[i], distance_p=np.hypot(dx, dy) / pitch, distance_w=np.abs(dx) / W,
                    box=self.box[idx], target_box=self.box[i], word_width=W, pitch=pitch)

    def select(self, i: int, mask, weights=None, cap: Optional[int] = None, candidates=None) -> Pool:
        """A pool from a boolean mask over `candidates(i)` (or a function of it); optional weights (array aligned with the
        candidates, or a function) and cap (the heaviest kept)."""
        c = candidates or self.candidates(i, 'all')
        if c is None:
            return Pool(np.zeros(0, dtype=np.int64), np.zeros(0), 0, True)
        m = np.asarray(mask(c) if callable(mask) else mask, bool)
        idx = c['idx'][m]
        w = np.ones(len(idx)) if weights is None else np.asarray(weights(c) if callable(weights) else weights, float)[m]
        available = len(idx)
        if cap is not None and len(idx) > cap:
            order = np.argsort(-w, kind='stable')[:cap]
            idx, w = idx[order], w[order]
        order = np.argsort(idx, kind='stable')
        return Pool(idx[order], w[order], available, False)

    def target_box(self, i: int, spec: PoolSpec) -> np.ndarray:
        """The target's rectangle under the spec: its recorded box, or the writing cursor (one median word wide at the
        leading edge: the left edge for direction up, the right edge for the mirror)."""
        tb = self.box[i]
        if spec.target != 'cursor':
            return tb
        W = self.page_of(i)['word_width']
        if spec.direction == 'up':
            return np.array([tb[0], tb[1], tb[0] + W, tb[3]])
        return np.array([tb[2] - W, tb[1], tb[2], tb[3]])

    # ---- the selector
    def pool(self, i: int, spec: PoolSpec = STUDY_SELECTOR) -> Pool:
        """The words in view of token i under `spec`. Indices ascending; weights aligned."""
        if not self.has_box[i]:
            return Pool(np.zeros(0, dtype=np.int64), np.zeros(0), 0, True)
        up = spec.direction == 'up'
        page = self.page_of(i)
        W, pitch = page['word_width'], page['pitch']
        idx = page['boxed']
        idx = idx[idx < i] if up else idx[idx > i]
        if not len(idx):
            return Pool(idx, np.zeros(0), 0, False)
        tb = self.target_box(i, spec)
        tx, ty = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
        box = self.box[idx]
        cx, cy = self.cx[idx], self.cy[idx]
        same = self.line_of[idx] == self.line_of[i]
        dx = cx - tx
        # same line
        if up:
            reach = spec.left
            ok_same = same & (dx < 0) & (-dx <= reach * W) if reach else np.zeros(len(idx), bool)
            dist_same = -dx / W
            gap = tb[0] - box[:, 2]
        else:
            reach = spec.right
            ok_same = same & (dx > 0) & (dx <= reach * W) if reach else np.zeros(len(idx), bool)
            dist_same = dx / W
            gap = box[:, 0] - tb[2]
        if spec.metric == 'edge':
            dist_same = 1.0 + np.maximum(0.0, gap) / W
        # other lines
        if spec.depth:
            ax = tx + spec.offset * W
            if up:
                dy = ty - cy
                near = np.maximum(0.0, ty - box[:, 3])
                far = np.minimum(spec.depth * pitch, ty - box[:, 1])
            else:
                dy = cy - ty
                near = np.maximum(0.0, box[:, 1] - ty)
                far = np.minimum(spec.depth * pitch, box[:, 3] - ty)
            horizontal = np.maximum(np.maximum(box[:, 0] - ax, ax - box[:, 2]), 0.0)
            tan = np.tan(np.radians(spec.angle))
            ok_other = (~same) & (dy > 0) & (far > 0) & (near <= far) & (horizontal <= far * tan + 1e-8)
            ddx = cx - ax
            with np.errstate(divide='ignore', invalid='ignore'):
                dist_other = np.hypot(ddx, dy) / pitch
                align_other = dy * dy / (ddx * ddx + dy * dy)
        else:
            ok_other = np.zeros(len(idx), bool)
            dist_other = np.zeros(len(idx))
            align_other = np.ones(len(idx))
        ok = ok_same | ok_other
        sel = np.flatnonzero(ok)
        if not len(sel):
            return Pool(np.zeros(0, dtype=np.int64), np.zeros(0), 0, False)
        distance = np.where(same[sel], dist_same[sel], dist_other[sel])
        alignment = np.where(same[sel], 1.0, align_other[sel])
        w = np.ones(len(sel)) if spec.weight == 'uniform' else alignment / (1.0 + distance) ** 2
        cand = idx[sel]
        # heaviest first, then nearest, then (up) the later token first / (down) the earlier token first; as js/sources.js
        tie = -cand if up else cand
        order = np.lexsort((tie, distance, -w))[:spec.cap]
        keep = cand[order]
        kw = w[order]
        back = np.argsort(keep, kind='stable')
        return Pool(keep[back], kw[back], int(len(sel)), False)

    def pools(self, spec: PoolSpec = STUDY_SELECTOR, indices=None):
        for i in (range(self.n) if indices is None else indices):
            yield i, self.pool(i, spec)

    # ---- reading-order windows
    def window_pool(self, i: int, width: int, direction: str = 'backward') -> Pool:
        before = 0 if direction == 'forward' else ((width - 1) // 2 if direction == 'centered' else width - 1)
        start = i - before
        end = start + width
        idx = np.arange(max(0, start), min(self.n, end), dtype=np.int64)
        return Pool(idx, np.ones(len(idx)), int(len(idx)), False, full=start >= 0 and end <= self.n)

    def missing_targets(self) -> np.ndarray:
        return ~self.has_box


def load_context(policy='strict', path=None) -> SpatialContext:
    from .bundle import load_bundle
    return SpatialContext(load_bundle(policy, path), policy=policy)


# ---- region helpers: masks over SpatialContext.candidates(i)
class Region:
    """Boolean masks over a candidates record, for `SpatialContext.select`. Combine with & | ~ on the arrays."""

    @staticmethod
    def same_line(c, left=None, right=None):
        m = c['same_line'].copy()
        if left is not None:
            m &= ~((c['dx_w'] < 0) & (-c['dx_w'] > left))
        if right is not None:
            m &= ~((c['dx_w'] > 0) & (c['dx_w'] > right))
        return m

    @staticmethod
    def lines_above(c, k=1, by='transcription'):
        return (c['line_offset'] < 0) & (c['line_offset'] >= -k) if by == 'transcription' else (c['dy_p'] > 0.5) & (c['dy_p'] <= k + 0.5)

    @staticmethod
    def lines_below(c, k=1, by='transcription'):
        return (c['line_offset'] > 0) & (c['line_offset'] <= k) if by == 'transcription' else (c['dy_p'] < -0.5) & (c['dy_p'] >= -(k + 0.5))

    @staticmethod
    def rect(c, x0, y0, x1, y1):
        """Candidate centres inside a rectangle given relative to the target centre, in word widths (x) and line spacings
        (y; positive = above)."""
        return (c['dx_w'] >= x0) & (c['dx_w'] <= x1) & (c['dy_p'] >= y0) & (c['dy_p'] <= y1)

    @staticmethod
    def radius(c, r):
        """Centre distance at most r line spacings."""
        return c['distance_p'] <= r

    @staticmethod
    def cone(c, depth=8, angle=45, above=True):
        """Rectangle intersects the finite cone of `depth` line spacings above (or below) the target: the selector's rule."""
        tb, box, pitch = c['target_box'], c['box'], c['pitch']
        ty = (tb[1] + tb[3]) / 2
        tx = (tb[0] + tb[2]) / 2
        if above:
            dy = c['dy']
            near = np.maximum(0.0, ty - box[:, 3])
            far = np.minimum(depth * pitch, ty - box[:, 1])
        else:
            dy = -c['dy']
            near = np.maximum(0.0, box[:, 1] - ty)
            far = np.minimum(depth * pitch, box[:, 3] - ty)
        horizontal = np.maximum(np.maximum(box[:, 0] - tx, tx - box[:, 2]), 0.0)
        return (~c['same_line']) & (dy > 0) & (far > 0) & (near <= far) & (horizontal <= far * np.tan(np.radians(angle)) + 1e-8)

    @staticmethod
    def distance_weights(c, metric='centre'):
        """The selector's weights for any mask: 1/(1+d)^2 on the line, cos^2/(1+d)^2 elsewhere; metric 'edge' uses the
        width-neutral same-line distance."""
        with np.errstate(divide='ignore', invalid='ignore'):
            align = np.where(c['same_line'], 1.0, c['dy'] ** 2 / (c['dx'] ** 2 + c['dy'] ** 2))
        d_same = c['distance_w']
        if metric == 'edge':
            tb, box, W = c['target_box'], c['box'], c['word_width']
            gap = np.where(c['dx'] < 0, tb[0] - box[:, 2], box[:, 0] - tb[2])
            d_same = 1.0 + np.maximum(0.0, gap) / W
        d = np.where(c['same_line'], d_same, c['distance_p'])
        return np.nan_to_num(align) / (1.0 + d) ** 2
