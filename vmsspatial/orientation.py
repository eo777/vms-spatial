"""Text orientation of every line: horizontal, rotated, circular, radial, label, unknown.

Every bundle line gets an ``orientation`` record and every token inherits its line's (``attach``):

    kind         'horizontal' | 'rotated' | 'circular' | 'radial' | 'label' | 'unknown'
    angle_deg    the text direction in the recorded frame: 0 = left to right, positive = clockwise on the page (the
                 text falls to the right; y grows downward). None for circular text, whose direction turns.
    centre       [x, y] and radius: the fitted circle of a circular line, or the page's circle for a radial line
    word_angles  circular and radial lines only: per token the tangent (circular) or radial (radial) angle, None
                 where the token has no rectangle
    confidence   0..1, from the cues' agreement and the number of rectangles
    basis        the cues that decided: the ZL locus type, the chord of the rectangle centres (angle, span, residual),
                 the rectangles' aspect, the circle fit, the ink writing angle when the optional ink pass ran

Cues. The ZL locus type (P paragraph, L label, C circular, R radial; vmsspatial.extra.locus_types). The arrangement of
the line's rectangle centres: a straight chord (principal axis; its angle, its span in page median word widths and
the perpendicular residual in page median heights) against a circle fit (algebraic least squares; radial residual and
the arc the points cover). The rectangles' aspect: a word written along the horizontal has a wide box (median
height / width about 0.45 on the manuscript); a word written up or down the page has a tall one. For pages with ink
records the optional pass ``ink_pass`` measures the writing angle of rotated lines on the scan around the box chord
(the standard search is within 6 degrees of the horizontal) and records it in the basis.

Paragraph lines are horizontal unless the boxes say otherwise: a chord steeper than ``ROTATED_DEG`` over at least one
word width, or tall boxes, make the line rotated; a circle that fits far better than the chord over a wide arc makes
it circular. A chord near 180 degrees (the words' boxes run right to left) is read as a horizontal line whose boxes
were recorded in reversed order ('reversed box order' in the basis): the boxes cannot tell that from text written
upside down (the lower paragraphs of f86v3 are such text), which the ink pass or the re-alignment's direction can. Label and circular and radial loci keep their type's kind, with the chord angle (labels) or the fitted
circle (circular, radial) as geometry. Lines without a rectangle are unknown.

Centres (``vmsspatial.wheels``). The centre of a circular line is the centre of the WHEEL its ring belongs to: the
ring's own circle fit must pass the wheel screens (at least 5 distinct boxes, 180 degrees of arc, a radius of two
body box heights, a radial residual within one box height and 12 percent of the radius), and accepted rings whose
centres coincide within max(H, 8 percent of the smaller radius) share one wheel whose centre is the median of
theirs. A circular line whose ring is rejected keeps its kind and its own fit diagnostics but gets NO centre and no
word angles ('circle rejected: <reason>' in the basis). A radial line takes the centre of the nearest accepted wheel
of its page; on a page without an accepted wheel (f67r2, f67v1: radial labels only) no centre is inferred. The
acceptance thresholds use the page's body box height (its paragraph lines' rectangles), as the wheels product does.

``line_mask(app, 'horizontal')`` selects the lines a line statistic may use; the line statistics of the toolkit take
``orientations='horizontal'`` by default and report how many lines they skipped. ``nonhorizontal_pages`` is the set
of pages whose paragraph lines are not all horizontal (``audit.flags.QUARANTINE`` names them).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from .extra import locus_category, locus_types

LABEL_TURNED_DEG = 30.0        # a label whose chord is this steep is written along its direction (word_labels.js: TURNED)
KINDS = ('horizontal', 'rotated', 'circular', 'radial', 'label', 'unknown')
ROTATED_DEG = 25.0            # a paragraph chord steeper than this (over a word width or more) is rotated text
TALL_ASPECT = 1.3             # median box height / width above this says the words stand up or down the page
MIN_SPAN_W = 1.0              # the chord needs this many median word widths to carry an angle
CIRCLE_MIN_POINTS = 5
CIRCLE_GAIN = 0.35            # the circle's radial residual must be below this share of the chord's residual
CIRCLE_MIN_ARC_DEG = 60.0
CIRCLE_MIN_RADIUS_H = 2.0
VERSION = '2026.10.31.1'      # centres from the accepted wheels (vmsspatial.wheels); rejected rings and radial lines without a wheel get none


# ----------------------------------------------------------------------------- geometry of one line
def _dedupe(boxes: Sequence[Optional[Sequence[float]]], groups: Optional[Sequence] = None):
    """The located rectangles of a line once each (a shared rectangle appears under several tokens), with the token
    positions they stand for."""
    units = []
    seen = {}
    for k, b in enumerate(boxes):
        if not b:
            continue
        key = groups[k] if groups is not None and groups[k] else tuple(float(v) for v in b)
        if key in seen:
            units[seen[key]]['tokens'].append(k)
            continue
        seen[key] = len(units)
        units.append(dict(box=[float(v) for v in b], tokens=[k]))
    return units


def chord(centres: np.ndarray, first_to_last: Optional[np.ndarray] = None):
    """Principal axis of N x 2 centres: (angle_deg, span, perpendicular rms residual, unit direction). The direction
    points from the first towards the last word (`first_to_last`, default: the first and last centre)."""
    c = np.asarray(centres, float)
    if len(c) < 2:
        return None
    d = c - c.mean(0)
    _, s, vt = np.linalg.svd(d, full_matrices=False)
    u = vt[0]
    ref = first_to_last if first_to_last is not None else c[-1] - c[0]
    if float(np.dot(u, ref)) < 0:
        u = -u
    proj = d @ u
    perp = d @ np.array([-u[1], u[0]])
    return dict(angle_deg=float(math.degrees(math.atan2(u[1], u[0]))), span=float(proj.max() - proj.min()),
                residual=float(np.sqrt(np.mean(perp ** 2))), direction=[float(u[0]), float(u[1])])


def circle_fit(centres: np.ndarray):
    """Algebraic least-squares circle through N x 2 points: (cx, cy, r, radial rms residual, arc covered in degrees)
    or None (fewer than 3 points or a degenerate fit)."""
    c = np.asarray(centres, float)
    if len(c) < 3:
        return None
    A = np.column_stack([2 * c[:, 0], 2 * c[:, 1], np.ones(len(c))])
    b = (c ** 2).sum(1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = sol[0], sol[1]
    r2 = sol[2] + cx * cx + cy * cy
    if not np.isfinite(r2) or r2 <= 0:
        return None
    r = math.sqrt(r2)
    dist = np.hypot(c[:, 0] - cx, c[:, 1] - cy)
    res = float(np.sqrt(np.mean((dist - r) ** 2)))
    ang = np.degrees(np.arctan2(c[:, 1] - cy, c[:, 0] - cx))
    arc = _arc_span(ang)
    return dict(cx=float(cx), cy=float(cy), r=float(r), residual=res, arc_deg=float(arc))


def _arc_span(angles_deg: np.ndarray) -> float:
    """The arc (degrees, up to 360) that a set of polar angles covers: 360 minus the largest gap between them."""
    a = np.sort(np.mod(np.asarray(angles_deg, float), 360.0))
    if len(a) < 2:
        return 0.0
    gaps = np.diff(np.concatenate([a, [a[0] + 360.0]]))
    return float(360.0 - gaps.max())


def _page_stats(app, by_page: Dict[str, List[int]]):
    """Per page: median box width and height over its located rectangles."""
    out = {}
    for page, idx in by_page.items():
        boxes = [app['geometry'][i] for i in idx if app['geometry'][i]]
        if boxes:
            out[page] = (float(np.median([b[2] - b[0] for b in boxes])) or 1.0, float(np.median([b[3] - b[1] for b in boxes])) or 1.0)
        else:
            out[page] = (1.0, 1.0)
    return out


def line_record(boxes: Sequence[Optional[Sequence[float]]], locus_type: Optional[str], W: float, H: float, groups: Optional[Sequence] = None,
                page_centre: Optional[Sequence[float]] = None, wheel: Optional[dict] = None, rejected: Optional[str] = None,
                body_H: Optional[float] = None) -> dict:
    """The orientation record of one line from its tokens' rectangles (None where a token has none), its ZL locus
    type and the page's median word width W and height H.

    `page_centre` ([x, y, r]) is the accepted wheel a radial line belongs to (the nearest on its page; None when the
    page has no accepted wheel: no centre is inferred). For a circular line, `wheel` ({id, centre, radius}) is the
    accepted wheel its ring was grouped into and `rejected` the reason its ring failed the wheel screens
    (``vmsspatial.wheels``); when neither is given (a line on its own) the line's own circle fit is screened with
    ``wheels.acceptance`` against `body_H` (default H)."""
    cat = locus_category(locus_type)
    units = _dedupe(boxes, groups)
    n = len(units)
    basis = ['locus_type:%s' % (locus_type or '?')]
    rec = dict(kind='unknown', angle_deg=None, confidence=0.0, basis=basis, n_boxes=n, locus_type=locus_type, centre=None, radius=None)
    if n == 0:
        basis.append('no rectangles')
        return rec
    B = np.array([u['box'] for u in units], float)
    centres = np.column_stack([(B[:, 0] + B[:, 2]) / 2, (B[:, 1] + B[:, 3]) / 2])
    aspect = float(np.median((B[:, 3] - B[:, 1]) / np.maximum(B[:, 2] - B[:, 0], 1e-9)))
    rec['aspect'] = round(aspect, 3)
    ch = chord(centres) if n >= 2 else None
    if ch:
        rec['chord'] = dict(angle_deg=round(ch['angle_deg'], 2), span_W=round(ch['span'] / W, 2), residual_H=round(ch['residual'] / H, 3))
        basis.append('chord:%.1fdeg over %.1fW' % (ch['angle_deg'], ch['span'] / W))
    basis.append('aspect:%.2f' % aspect)
    circ = circle_fit(centres) if n >= CIRCLE_MIN_POINTS or cat == 'C' else None
    circ_ok = bool(circ and ch and circ['r'] >= CIRCLE_MIN_RADIUS_H * H and circ['residual'] < CIRCLE_GAIN * max(ch['residual'], 1e-9) and circ['arc_deg'] >= CIRCLE_MIN_ARC_DEG)
    tall = aspect > TALL_ASPECT
    reversed_order = bool(ch and ch['span'] >= MIN_SPAN_W * W and abs(ch['angle_deg']) > 180.0 - ROTATED_DEG and cat in ('P', 'L'))
    if reversed_order:
        # the words run right to left along a near-horizontal chord: an order reversal of the recorded boxes (the
        # review's `order_reversal` flag), not rotated text; the tilt is the chord's angle about 180
        ch = dict(ch, angle_deg=_wrap(ch['angle_deg'] - 180.0))
        rec['chord']['angle_deg'] = round(ch['angle_deg'], 2)
        basis.append('reversed box order')
    steep = bool(ch and ch['span'] >= MIN_SPAN_W * W and abs(ch['angle_deg']) > ROTATED_DEG)
    if cat == 'C' or (cat == 'P' and circ_ok and n >= CIRCLE_MIN_POINTS):
        rec['kind'] = 'circular'
        from .wheels import fit_circle as wheel_fit, acceptance
        own = wheel_fit(centres) if n >= 3 else None            # the ring's own fit (centred algebraic least squares)
        if own:
            rec['circle'] = dict(residual_H=round(own['residual'] / H, 3), arc_deg=round(own['arc_deg'], 1), radius=round(own['radius'], 1), n_boxes=n)
        if wheel is None and rejected is None:
            reason = acceptance(own, body_H if body_H else H)
            if reason:
                rejected = reason
            else:
                wheel = dict(id='own', centre=own['centre'], radius=own['radius'])
        if wheel is not None:
            cx, cy = wheel['centre']
            rec['centre'] = [round(cx, 1), round(cy, 1)]
            rec['radius'] = round(own['radius'], 1) if own else round(wheel['radius'], 1)
            rec['wheel'] = wheel['id']
            basis.append('circle:r=%.0f arc=%.0fdeg' % (own['radius'] if own else wheel['radius'], own['arc_deg'] if own else 0.0))
            if wheel['id'] != 'own':
                basis.append('wheel:%s' % wheel['id'])
            clockwise = (locus_type or 'Cc') != 'Ca'
            if cat == 'P':
                clockwise = _turns_clockwise(centres, dict(cx=cx, cy=cy))
            rec['clockwise'] = clockwise
            angles = []
            for b in boxes:
                if not b:
                    angles.append(None)
                    continue
                th = math.degrees(math.atan2((b[1] + b[3]) / 2 - cy, (b[0] + b[2]) / 2 - cx))
                angles.append(round(_wrap(th + (90.0 if clockwise else -90.0)), 1))
            rec['word_angles'] = angles
            quality = max(0.0, 1.0 - (own['residual'] if own else 0.0) / H)
            rec['confidence'] = round(min(1.0, quality * min(1.0, n / 8.0) * (1.0 if (own['arc_deg'] if own else 0.0) >= CIRCLE_MIN_ARC_DEG else 0.5)), 2)
        else:
            rec['centre'] = None
            rec['radius'] = None
            rec['rejected'] = rejected
            basis.append('circle rejected: %s' % rejected)
            rec['confidence'] = 0.2
        return rec
    if cat == 'R':
        rec['kind'] = 'radial'
        if ch and ch['span'] >= 0.5 * W:
            rec['angle_deg'] = round(ch['angle_deg'], 1)
        if page_centre:
            rec['centre'] = [round(page_centre[0], 1), round(page_centre[1], 1)]
            rec['radius'] = round(page_centre[2], 1) if len(page_centre) > 2 and page_centre[2] else None
            basis.append('circle:wheel')
            rec['word_angles'] = [None if not b else round(math.degrees(math.atan2((b[1] + b[3]) / 2 - page_centre[1], (b[0] + b[2]) / 2 - page_centre[0])), 1) for b in boxes]
            # a radial line runs along a ray from the centre: its chord should point along the ray
            if ch and rec['word_angles']:
                ray = [a for a in rec['word_angles'] if a is not None]
                along = abs(_wrap(ch['angle_deg'] - float(np.median(ray))))
                rec['confidence'] = round(max(0.2, 1.0 - min(along, 180 - along) / 90.0) * min(1.0, n / 3.0), 2)
            else:
                rec['confidence'] = 0.3
        else:
            basis.append('circle:none (no accepted wheel on the page)')
            rec['confidence'] = round(0.3 * min(1.0, n / 3.0), 2)
        return rec
    if cat == 'L':
        rec['kind'] = 'label'
        if ch and ch['span'] >= MIN_SPAN_W * W:
            rec['angle_deg'] = round(ch['angle_deg'], 1)
        elif tall:
            rec['angle_deg'] = 90.0
            basis.append('tall boxes')
        else:
            rec['angle_deg'] = 0.0
        rec['confidence'] = round(0.6 + 0.4 * min(1.0, n / 3.0), 2) if ch else 0.6
        return rec
    # paragraph text (and any other type): horizontal unless the boxes say otherwise
    if steep or (tall and (n == 1 or not ch or ch['span'] < MIN_SPAN_W * W)):
        rec['kind'] = 'rotated'
        if steep:
            rec['angle_deg'] = round(ch['angle_deg'], 1)
            rec['confidence'] = round(min(1.0, (abs(ch['angle_deg']) - ROTATED_DEG) / 30.0 + 0.5) * min(1.0, 0.5 + n / 6.0), 2)
            if tall:
                basis.append('tall boxes')
        else:
            rec['angle_deg'] = 90.0
            basis.append('tall boxes; direction unknown')
            rec['confidence'] = 0.4
        return rec
    rec['kind'] = 'horizontal'
    if ch and ch['span'] >= MIN_SPAN_W * W:
        rec['angle_deg'] = round(ch['angle_deg'], 1)
        agree = 1.0 - min(1.0, abs(ch['angle_deg']) / ROTATED_DEG)
        rec['confidence'] = round(min(1.0, 0.5 * agree + 0.5 * min(1.0, ch['span'] / (3 * W))) * (0.7 if tall else 1.0), 2)
    else:
        rec['angle_deg'] = 0.0
        rec['confidence'] = 0.5 if not tall else 0.3
        basis.append('single rectangle' if n == 1 else 'short chord')
    return rec


def _turns_clockwise(centres: np.ndarray, circ: dict) -> bool:
    th = np.unwrap(np.arctan2(centres[:, 1] - circ['cy'], centres[:, 0] - circ['cx']))
    return bool(np.sum(np.diff(th)) >= 0)


def _wrap(deg: float) -> float:
    return ((deg + 180.0) % 360.0) - 180.0


def upright(angle: float) -> float:
    """The same line of writing, turned half way round where it would read upside down: (-90, 90]."""
    d = _wrap(angle)
    if d > 90.0:
        d -= 180.0
    elif d <= -90.0:
        d += 180.0
    return d


def label_angle(record: Optional[dict], j: int) -> Optional[float]:
    """The direction a word label runs in: the same rule as ``angleOf`` in viewer/js/word_labels.js, which the atlas and
    the comparison page use.

    Degrees clockwise on the page, 0 = left to right, the sense of SVG's rotate(); matplotlib turns the other way. On a
    ring written clockwise a word's bottom faces the wheel's centre: 0 at 12 o'clock, 90 at 3, 180 at 6, -90 at 9.

    Args:
        record: the line's orientation record (None or empty reads as level text).
        j: the token's place in its line.

    Returns:
        circular: the token's `word_angles` entry, None when it has none (a ring that failed the wheel screens).
        radial: `angle_deg`, the chord where the line has one, else the ray of `word_angles` turned upright (the boxes
        cannot say which way a single word runs), None without either. rotated: `angle_deg`, None without one. label:
        `angle_deg` when the chord is 30 degrees or steeper. Anything else: 0.

    Example:
        >>> label_angle(dict(kind='circular', word_angles=[0.0, 90.0, 180.0, -90.0]), 1)
        90.0
        >>> label_angle(dict(kind='horizontal', angle_deg=1.5), 0)
        0.0
    """
    if not record:
        return 0.0
    angles = record.get('word_angles')
    a = angles[j] if angles and 0 <= j < len(angles) else None
    kind, chord = record.get('kind'), record.get('angle_deg')
    if kind == 'circular':
        return a
    if kind == 'radial':
        return chord if chord is not None else (None if a is None else upright(a))
    if kind == 'rotated':
        return chord
    if kind == 'label' and abs(chord or 0.0) >= LABEL_TURNED_DEG:
        return chord
    return 0.0


# ----------------------------------------------------------------------------- a whole bundle
def _line_types(app, ms=None) -> List[Optional[str]]:
    """The ZL locus type of every bundle line: from the manuscript's lines when given, else the shipped resource."""
    if ms is not None:
        ms_lines = ms.lines if hasattr(ms, 'lines') else ms['lines']
        if len(ms_lines) == len(app['lines']) and all('locus_type' in L for L in ms_lines[:3]):
            return [L.get('locus_type') for L in ms_lines]
    types = locus_types()
    return [types.get(L['page'], {}).get(str(L['locus'])) for L in app['lines']]


def page_circles(app, ms=None, types: Optional[List[Optional[str]]] = None) -> Dict[str, list]:
    """Per page with an accepted wheel: [cx, cy, r] of its largest wheel (``vmsspatial.wheels``). Before 2026-10-31
    this was the median of every circular line's own fit, rejected rings included; the wheels product replaced it."""
    out = {}
    for L, r in zip(app['lines'], records(app, ms)):
        if r['kind'] == 'circular' and r.get('centre') and r.get('radius'):
            cur = out.get(L['page'])
            if cur is None or r['radius'] > cur[2]:
                out[L['page']] = [float(r['centre'][0]), float(r['centre'][1]), float(r['radius'])]
    return out


def _nearest_wheel(boxes, wheels):
    """The accepted wheel of the page nearest to the centroid of a line's rectangles: [cx, cy, r] or None."""
    pts = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes if b]
    if not pts or not wheels:
        return None
    cx, cy = float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts]))
    w = min(wheels, key=lambda w: math.hypot(w['centre'][0] - cx, w['centre'][1] - cy))
    return [w['centre'][0], w['centre'][1], w['radius']]


def _geometry_for_orientation(app):
    """The rectangles the orientation is read from: the review's sensitivity geometry when the bundle carries the
    review (the most complete recorded set, the same under every policy), else the bundle's own geometry."""
    review = app.get('spatialReview')
    if review and review.get('sensitivityGeometry') and len(review['sensitivityGeometry']) == len(app['geometry']):
        return review['sensitivityGeometry']
    return app['geometry']


def line_orientations(app, ms=None) -> List[dict]:
    """One orientation record per bundle line (``line_record`` on each), read from the most complete recorded
    rectangles the bundle carries (``_geometry_for_orientation``), so the record does not depend on the policy."""
    types = _line_types(app, ms)
    geometry = _geometry_for_orientation(app)
    view = dict(app, geometry=geometry)
    by_page = defaultdict(list)
    for L in app['lines']:
        by_page[L['page']].extend(range(L['start'], L['end']))
    stats = _page_stats(view, by_page)
    review = app.get('spatialReview')
    groups = [t.get('group') for t in review['tokens']] if review else None
    # first pass: the kinds (a circular line's own fit is screened on its own here; the wheels decide the centres)
    out = []
    for L, t in zip(app['lines'], types):
        W, H = stats[L['page']]
        g = groups[L['start']:L['end']] if groups else None
        out.append(line_record(geometry[L['start']:L['end']], t, W, H, g))
    # the wheels of every page from the circular lines, then the centres of circular and radial lines from them
    from .wheels import fit_pages
    fits = fit_pages(view, geometry, [r['kind'] for r in out], [locus_category(L.get('locus_type') or t) for L, t in zip(app['lines'], types)], labels=False)
    wheel_of_line, rejected_of_line = {}, {}
    for page, rec in fits.items():
        for w in rec['wheels']:
            for r in w['rings']:
                wheel_of_line[r['line']] = dict(id=w['id'], centre=w['centre'], radius=w['radius'])
        for r in rec['rejected']:
            rejected_of_line[r['line']] = r['reason']
    for l, (L, t) in enumerate(zip(app['lines'], types)):
        kind = out[l]['kind']
        if kind not in ('circular', 'radial'):
            continue
        W, H = stats[L['page']]
        g = groups[L['start']:L['end']] if groups else None
        boxes = geometry[L['start']:L['end']]
        page_fit = fits.get(L['page']) or {}
        if kind == 'circular':
            out[l] = line_record(boxes, t, W, H, g, wheel=wheel_of_line.get(l), rejected=rejected_of_line.get(l, 'not a circular line of the wheel fit'), body_H=page_fit.get('H'))
        else:
            out[l] = line_record(boxes, t, W, H, g, page_centre=_nearest_wheel(boxes, page_fit.get('wheels') or []))
    return out


def attach(app: dict, ms=None, force: bool = False) -> dict:
    """Store the orientation record on every line of the bundle (``lines[i]['orientation']``), in place, and the
    locus type beside it; returns the bundle. Already attached records are kept unless `force`."""
    if not force and app['lines'] and all('orientation' in L for L in app['lines']):
        return app
    recs = line_orientations(app, ms)
    types = _line_types(app, ms)
    for L, r, t in zip(app['lines'], recs, types):
        L['orientation'] = r
        if t and not L.get('locus_type'):
            L['locus_type'] = t
    app['orientation_version'] = VERSION
    return app


def token_orientations(app) -> List[Optional[dict]]:
    """Per token, its line's orientation record (``attach`` first)."""
    attach(app)
    out = [None] * len(app['words'])
    for L in app['lines']:
        for i in range(L['start'], L['end']):
            out[i] = L['orientation']
    return out


_MEMO = {}


def records(app, ms=None) -> List[dict]:
    """The orientation records of a bundle's lines without modifying it: the attached ones when the bundle carries
    them (``attach``), else computed and memoized on the bundle's identity (a statistic may ask many times)."""
    if app['lines'] and all('orientation' in L for L in app['lines']):
        return [L['orientation'] for L in app['lines']]
    key = (id(app), id(app['lines']), id(app['geometry']), len(app['words']))
    if key not in _MEMO:
        if len(_MEMO) > 64:
            _MEMO.clear()
        _MEMO[key] = line_orientations(app, ms)
    return _MEMO[key]


def _kinds(orientations) -> Optional[frozenset]:
    if orientations is None or orientations == 'all':
        return None
    if isinstance(orientations, str):
        orientations = [orientations]
    bad = [k for k in orientations if k not in KINDS]
    if bad:
        raise ValueError('unknown orientation kind(s) %r; one of %s' % (bad, ', '.join(KINDS)))
    return frozenset(orientations)


def line_mask(app, orientations='horizontal', ms=None) -> List[bool]:
    """Per bundle line: True when its orientation kind is among `orientations` (a kind, a list of kinds, or None /
    'all' for every line). Attaches the records when the bundle lacks them."""
    kinds = _kinds(orientations)
    if kinds is None:
        return [True] * len(app['lines'])
    return [r['kind'] in kinds for r in records(app, ms)]


def skipped(app, mask: Sequence[bool]) -> dict:
    """What a line statistic left out: counts of the skipped lines by kind, for its report."""
    recs = records(app)
    c = Counter(r['kind'] for r, m in zip(recs, mask) if not m)
    return dict(skipped_lines=int(sum(1 for m in mask if not m)), by_kind=dict(c))


def summary(app, ms=None) -> dict:
    """Lines by kind, pages by the kinds they hold, paragraph lines by kind, and the pages whose paragraph lines are
    not all horizontal."""
    attach(app, ms)
    lines = Counter(L['orientation']['kind'] for L in app['lines'])
    pages = defaultdict(Counter)
    par = Counter()
    for L in app['lines']:
        pages[L['page']][L['orientation']['kind']] += 1
        if locus_category(L.get('locus_type')) == 'P':
            par[L['orientation']['kind']] += 1
    page_kinds = Counter()
    for p, c in pages.items():
        page_kinds['+'.join(sorted(k for k in c if c[k]))] += 1
    return dict(version=VERSION, lines_by_kind=dict(lines), paragraph_lines_by_kind=dict(par), pages=len(pages), pages_by_kinds=dict(page_kinds),
                pages_with_kind={k: sum(1 for c in pages.values() if c.get(k)) for k in KINDS}, nonhorizontal_pages=sorted(nonhorizontal_pages(app)))


def nonhorizontal_pages(app, ms=None) -> set:
    """Pages with a paragraph line (ZL type P*) whose orientation is rotated or circular (lines without rectangles do
    not count). Does not modify the bundle."""
    recs = records(app, ms)
    types = _line_types(app, ms)
    out = set()
    for L, r, t in zip(app['lines'], recs, types):
        if locus_category(L.get('locus_type') or t) == 'P' and r['kind'] in ('rotated', 'circular'):
            out.add(L['page'])
    return out


def describe(rec: Optional[dict]) -> str:
    """One line of text for a record (the viewer's tooltip uses the same fields)."""
    if not rec:
        return 'orientation unknown'
    s = rec['kind']
    if rec.get('angle_deg') is not None:
        s += ' %+.1f deg' % rec['angle_deg']
    if rec.get('centre'):
        s += ' about (%.0f, %.0f)' % tuple(rec['centre'])
        if rec.get('radius'):
            s += ' r %.0f' % rec['radius']
    return s + ' (confidence %.2f; %s)' % (rec.get('confidence', 0.0), '; '.join(rec.get('basis', [])))


# ----------------------------------------------------------------------------- the optional ink pass
def ink_pass(app, ms, lines: Optional[Iterable[int]] = None, source: str = 'beinecke', search_deg: float = 12.0, log=None) -> Dict[int, dict]:
    """Measure the writing angle of rotated lines on the page scan around the box chord: the region of each rectangle
    is rotated by the chord angle (so the standard shear search, within `search_deg`, reads the text as if horizontal)
    and the measured angle is returned to the page frame. Only the lines given (default: every rotated line of the
    bundle) are touched; nothing is re-measured elsewhere and nothing is written. Returns {line index: {angle_deg
    (median over the line's words, page frame), n, chord_deg}} and records it in each line's basis."""
    from .images import registration, page_image, Mapping
    from .ink import binarize, measure_word, DEFAULTS
    import cv2
    attach(app, ms)
    if lines is None:
        lines = [k for k, L in enumerate(app['lines']) if L['orientation']['kind'] == 'rotated']
    pages_ms = ms.pages if hasattr(ms, 'pages') else ms['pages']
    folio_of_line = {}
    for p in pages_ms:
        for l in range(p['start_line'], p['end_line']):
            folio_of_line[l] = p['folio']
    out = {}
    cache = {}
    for l in lines:
        L = app['lines'][l]
        rec = L['orientation']
        if rec.get('angle_deg') is None:
            continue
        folio = folio_of_line.get(l, L['page'])
        if folio not in cache:
            reg = registration(folio, source, app, ms)
            cache[folio] = (reg, page_image(folio, source, reg.get('image_id')) if reg.get('ok') else None)
        reg, img = cache[folio]
        if img is None:
            continue
        m = Mapping(reg, L['locus'])
        units = _dedupe(app['geometry'][L['start']:L['end']])
        boxes = [u['box'] for u in units]
        steep = abs(rec['angle_deg']) >= 45
        # the extent of a box across the text direction (its width for text written up or down the page)
        H = float(np.median([(b[2] - b[0]) if steep else (b[3] - b[1]) for b in boxes]))
        angles = []
        for b in boxes:
            bi = m.box_to_image(b)
            cx, cy = (bi[0] + bi[2]) / 2, (bi[1] + bi[3]) / 2
            half = max(bi[2] - bi[0], bi[3] - bi[1]) / 2 + 0.6 * H * m.scale(cx, cy)
            X0, Y0, X1, Y1 = int(max(0, cx - half)), int(max(0, cy - half)), int(min(img.shape[1], cx + half)), int(min(img.shape[0], cy + half))
            if X1 - X0 < 8 or Y1 - Y0 < 8:
                continue
            reg_img = np.ascontiguousarray(img[Y0:Y1, X0:X1])
            theta = rec['angle_deg'] + m.rotation_deg(cx, cy)
            R = cv2.getRotationMatrix2D(((X1 - X0) / 2.0, (Y1 - Y0) / 2.0), theta, 1.0)       # rotate the text back to the horizontal
            rot = cv2.warpAffine(reg_img, R, (X1 - X0, Y1 - Y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            H_img = H * m.scale(cx, cy)
            ink, paint = binarize(rot, H_img)
            # the rotated box: its extent along the text direction and across it
            w_t = ((b[3] - b[1]) if steep else (b[2] - b[0])) * m.scale(cx, cy)
            h_t = ((b[2] - b[0]) if steep else (b[3] - b[1])) * m.scale(cx, cy)
            box_r = [(X1 - X0) / 2.0 - w_t / 2, (Y1 - Y0) / 2.0 - h_t / 2, (X1 - X0) / 2.0 + w_t / 2, (Y1 - Y0) / 2.0 + h_t / 2]
            p = dict(DEFAULTS, angle_range_deg=search_deg)
            mw = measure_word(ink, paint, box_r, H_img, p)
            if mw.get('angle_deg') is not None and not (mw['flags'] & 32):
                angles.append(theta + mw['angle_deg'] - m.rotation_deg(cx, cy))
        if angles:
            a = float(np.median(angles))
            out[l] = dict(angle_deg=round(a, 1), n=len(angles), chord_deg=rec['angle_deg'])
            rec['basis'] = [x for x in rec['basis'] if not x.startswith('ink:')] + ['ink:%.1fdeg (%d words)' % (a, len(angles))]
            rec['ink_angle_deg'] = round(a, 1)
            if log:
                log('%s line %s: chord %.1f deg, ink %.1f deg over %d words' % (folio, L['locus'], rec['angle_deg'], a, len(angles)))
    return out
