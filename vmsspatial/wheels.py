"""Wheels: the circles that the manuscript's circular text is written on, fitted from the recorded rectangles.

A circular locus (ZL type Cc / Ca, or a paragraph locus whose boxes run in a circle) is a ring of words. Its ring
centre is fitted from the centres of its distinct recorded word rectangles by algebraic least squares (the fit of
``vmsspatial.orientation.circle_fit``, solved after centring the points for numerical stability). A ring is
ACCEPTED when it has at least ``MIN_BOXES`` distinct boxes, its boxes cover at least ``MIN_ARC_DEG`` of arc, its radius
is at least ``MIN_RADIUS_H`` page body box heights, and its radial RMS residual is at most one body box height and
at most ``MAX_RESIDUAL_SHARE`` of the radius; a rejected ring keeps its reason. Accepted rings whose centres lie within
max(H, ``GROUP_SHARE`` x the smaller radius) of EVERY member of a group (complete linkage) form one WHEEL, whose
centre is the coordinate-wise median of its rings' centres and whose radius is the largest ring radius. Separate
centres on a page stay separate (f68r2 has two, the Rosettes nine). H is the page's body box height: the median
height of the recorded rectangles on its paragraph lines (all its rectangles when it has no paragraph line).

Products and uses:

    fit_wheels(app, ms)          every page's wheels and rejected rings from a bundle (the fit reads the most complete
                                 recorded rectangles the bundle carries, as the orientation records do)
    build(app, ms)               write the shipped product data/manuscript/wheels.json.gz (``load_wheels`` reads it)
    centered_layout(app, ms, folio)   each wheel of a page translated to a common centre, nothing else changed: a
                                 DISPLAY transform in the frame 'display' (``vmsspatial.frames``), never measured geometry
    orientation records          ``vmsspatial.orientation`` takes the centre, radius and per-word angles of circular and
                                 radial lines from the accepted wheels (a rejected ring gets no centre; a radial line
                                 gets the nearest accepted wheel of its page, or none)

What a wheel is not. A fitted centre is a property of the recorded rectangles, not of the ink; a coincident centre
after ``centered_layout`` is imposed by the display and is no evidence of a shared template (docs/PITFALLS.md 24).
Fit criteria, acceptance and limits: docs/WHEELS.md.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import paths
from .bundle import digest, read_json, write_json

VERSION = '2026.10.30.1'
PRODUCT_KEY = 'manuscript/wheels.json.gz'
MIN_BOXES = 5                 # distinct located boxes a ring needs
MIN_ARC_DEG = 180.0           # the boxes must cover half the circle
MIN_RADIUS_H = 2.0            # in page body box heights
MAX_RESIDUAL_H = 1.0          # radial RMS residual, in body box heights
MAX_RESIDUAL_SHARE = 0.12     # ... and as a share of the radius
GROUP_SHARE = 0.08            # ring centres within max(H, this x the smaller radius) of every member join one wheel
DEFAULT_H, DEFAULT_W = 30.0, 60.0
DISPLAY_FRAME = 'display'
_PRODUCT = {}

REASONS = dict(few='Fewer than 5 distinct located boxes, or degenerate fit', arc='Located arc covers less than 180 degrees',
               radius='Radius below 2 median box heights', residual='Circle residual exceeds the display-fit threshold')


# ----------------------------------------------------------------------------- the fit
def fit_circle(points) -> Optional[dict]:
    """Algebraic least-squares circle through N x 2 points, solved after centring them.

    Args:
        points: sequence of [x, y] (at least 3).

    Returns:
        {centre: [cx, cy], radius, residual (radial RMS), arc_deg (the arc the points cover: 360 minus the largest
        angular gap), n} or None when there are fewer than 3 points or the normal equations are degenerate
        (collinear points).

    Example:
        >>> f = fit_circle([[1, 0], [0, 1], [-1, 0], [0, -1]])
        >>> round(f['radius'], 6), [round(c, 6) for c in f['centre']]
        (1.0, [0.0, 0.0])
    """
    P = np.asarray(points, float).reshape(-1, 2)
    n = len(P)
    if n < 3:
        return None
    m = P.mean(0)
    q = P - m
    xx = float(np.sum(q[:, 0] * q[:, 0]))
    xy = float(np.sum(q[:, 0] * q[:, 1]))
    yy = float(np.sum(q[:, 1] * q[:, 1]))
    z = q[:, 0] ** 2 + q[:, 1] ** 2
    xz = float(np.sum(q[:, 0] * z))
    yz = float(np.sum(q[:, 1] * z))
    det = xx * yy - xy * xy
    if det <= 1e-12 * (xx + yy) ** 2:
        return None
    x = (xz * yy - yz * xy) / (2 * det)
    y = (yz * xx - xz * xy) / (2 * det)
    r = math.sqrt((xx + yy) / n + x * x + y * y)
    if not math.isfinite(r) or r <= 0:
        return None
    c = [float(m[0] + x), float(m[1] + y)]
    d = np.hypot(P[:, 0] - c[0], P[:, 1] - c[1])
    residual = float(math.sqrt(float(np.mean((d - r) ** 2))))
    ang = np.sort(np.mod(np.arctan2(P[:, 1] - c[1], P[:, 0] - c[0]) + 2 * math.pi, 2 * math.pi))
    gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * math.pi]]))
    arc = 360.0 - float(gaps.max()) * 180.0 / math.pi
    return dict(centre=c, radius=float(r), residual=residual, arc_deg=float(arc), n=int(n))


def acceptance(fit: Optional[dict], H: float) -> str:
    """Why a ring fit is rejected for a wheel, or '' when it is accepted.

    Args:
        fit: a ``fit_circle`` result (or None).
        H: the page's body box height in the same pixels.

    Returns:
        '' (accepted) or one of the sentences in ``REASONS``.

    Example:
        >>> acceptance(None, 30.0)
        'Fewer than 5 distinct located boxes, or degenerate fit'
    """
    if not fit or fit['n'] < MIN_BOXES:
        return REASONS['few']
    if fit['arc_deg'] < MIN_ARC_DEG:
        return REASONS['arc']
    if fit['radius'] < MIN_RADIUS_H * H:
        return REASONS['radius']
    if fit['residual'] > MAX_RESIDUAL_H * H or fit['residual'] / fit['radius'] > MAX_RESIDUAL_SHARE:
        return REASONS['residual']
    return ''


def _centre(box):
    return [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]


def _median(values):
    return float(np.median(values)) if len(values) else 0.0


def fit_rings(lines: Sequence[dict], H: float):
    """Fit every circular line of a page and screen it.

    Args:
        lines: [{line, locus, units: [{first, last, box}]}] the page's circular lines with their located rectangles.
        H: the page's body box height.

    Returns:
        (rings, rejected): accepted rings [{line, locus, fit, units (every unit of the line), distinct (boxes used)}]
        and rejected [{line, locus, reason, fit}].

    Example:
        >>> ring = [dict(first=k, last=k, box=[100 * math.cos(k) - 10, 100 * math.sin(k) - 5, 100 * math.cos(k) + 10, 100 * math.sin(k) + 5]) for k in range(12)]
        >>> rings, rejected = fit_rings([dict(line=0, locus='1', units=ring)], 10.0)
        >>> len(rings), len(rejected)
        (1, 0)
    """
    rings, rejected = [], []
    for L in lines:
        seen, distinct = set(), []
        for u in L['units']:
            key = tuple(float(v) for v in u['box'])
            if key in seen:
                continue
            seen.add(key)
            distinct.append(u)
        fit = fit_circle([_centre(u['box']) for u in distinct]) if distinct else None
        reason = acceptance(fit, H)
        if reason:
            rejected.append(dict(line=L['line'], locus=L['locus'], reason=reason, fit=fit))
        else:
            rings.append(dict(line=L['line'], locus=L['locus'], fit=fit, units=list(L['units']), distinct=len(distinct)))
    return rings, rejected


def group_rings(rings: Sequence[dict], H: float) -> List[dict]:
    """Complete-link grouping of accepted rings into wheels.

    Rings are taken from the most to the least populated; a ring joins the first group every member of which has its
    centre within max(H, GROUP_SHARE x the smaller of the two radii). A wheel's centre is the coordinate-wise median
    of its rings' centres, its radius the largest ring radius; wheels are ordered by centre y, then x.

    Args:
        rings: accepted rings from ``fit_rings``.
        H: the page's body box height.

    Returns:
        [{centre, radius, centre_spread, rings}] where centre_spread is the largest distance of a ring centre from
        the wheel centre.

    Example:
        >>> a = dict(line=0, locus='1', fit=dict(centre=[0.0, 0.0], radius=100.0, n=9))
        >>> b = dict(line=1, locus='2', fit=dict(centre=[1.0, 1.0], radius=80.0, n=7))
        >>> len(group_rings([a, b], 10.0))
        1
    """
    groups: List[List[dict]] = []
    for ring in sorted(rings, key=lambda r: -r['fit']['n']):
        c = ring['fit']['centre']
        home = None
        for g in groups:
            if all(math.hypot(c[0] - o['fit']['centre'][0], c[1] - o['fit']['centre'][1]) <= max(H, GROUP_SHARE * min(ring['fit']['radius'], o['fit']['radius'])) for o in g):
                home = g
                break
        if home is None:
            groups.append([ring])
        else:
            home.append(ring)
    wheels = []
    for rs in groups:
        c = [_median([r['fit']['centre'][0] for r in rs]), _median([r['fit']['centre'][1] for r in rs])]
        wheels.append(dict(centre=c, radius=max(r['fit']['radius'] for r in rs), rings=rs,
                           centre_spread=max(math.hypot(r['fit']['centre'][0] - c[0], r['fit']['centre'][1] - c[1]) for r in rs)))
    wheels.sort(key=lambda w: (w['centre'][1], w['centre'][0]))
    return wheels


# ----------------------------------------------------------------------------- a bundle
def _geometry(app):
    from .orientation import _geometry_for_orientation
    return _geometry_for_orientation(app)


def _units_by_line(app, geometry) -> List[List[dict]]:
    """Per bundle line the located rectangles once each ([{first, last, box}]), grouped by the review's assignment
    group where the bundle carries one, else by identical rectangles; nothing is excluded as oversized."""
    from .geometry import line_units
    view = dict(app, geometry=geometry)
    return line_units(view, None, flags=[False] * len(app['words']), orientations=None)


def _categories(app, ms=None) -> List[str]:
    from .orientation import _line_types
    from .extra import locus_category
    types = _line_types(app, ms)
    return [locus_category(L.get('locus_type') or t) for L, t in zip(app['lines'], types)]


def body_size(units: Sequence[Sequence[dict]], cats: Sequence[str]):
    """The page's body box height and width: medians over the rectangles of its paragraph lines (all its rectangles
    when it has no paragraph line; 30 x 60 px when it has none)."""
    body = [u['box'] for us, c in zip(units, cats) if c == 'P' for u in us] or [u['box'] for us in units for u in us]
    if not body:
        return DEFAULT_H, DEFAULT_W
    return float(np.median([b[3] - b[1] for b in body])), float(np.median([b[2] - b[0] for b in body]))


def fit_pages(app, geometry, kinds: Sequence[str], cats: Sequence[str], labels: bool = True) -> Dict[str, dict]:
    """The core fit on plain per-line data (used by ``fit_wheels`` and by the orientation records, which must not call
    back into ``orientation.attach``).

    Args:
        app: a bundle (words, lines, spatialReview optional).
        geometry: the rectangles to fit on (one per token or None).
        kinds: per line the orientation kind; only 'circular' lines are fitted.
        cats: per line the locus category (P, L, C, R, ?).
        labels: also list, per wheel, the nearby non-paragraph, non-circular units (within radius + H of the centre).

    Returns:
        {folio: {H, W, wheels: [...], rejected: [...], circular_lines, n_units}} with per wheel {id, centre, radius,
        centre_spread, rings: [{line, locus, centre, radius, residual, arc_deg, n, tokens}], words (unit count),
        tokens (token count), labels: [[first, last], ...]}.
    """
    units = _units_by_line(app, geometry)
    by_page: Dict[str, List[int]] = defaultdict(list)
    for l, L in enumerate(app['lines']):
        by_page[L['page']].append(l)
    out = {}
    for folio, idx in by_page.items():
        H, W = body_size([units[l] for l in idx], [cats[l] for l in idx])
        circ = [dict(line=l, locus=str(app['lines'][l]['locus']), units=units[l]) for l in idx if kinds[l] == 'circular']
        rings, rejected = fit_rings(circ, H)
        wheels = group_rings(rings, H)
        recs = []
        for k, w in enumerate(wheels):
            ring_lines = {r['line'] for r in w['rings']}
            members = [u for r in w['rings'] for u in r['units']]
            near = []
            if labels:
                for l in idx:
                    if cats[l] == 'P' or kinds[l] == 'circular':
                        continue
                    for u in units[l]:
                        c = _centre(u['box'])
                        d = math.hypot(c[0] - w['centre'][0], c[1] - w['centre'][1]) / (w['radius'] + H)
                        if d <= 1.0:
                            near.append((d, l, u))
            recs.append(dict(id='%s/wheel%d' % (folio, k + 1), centre=[float(v) for v in w['centre']], radius=float(w['radius']), centre_spread=float(w['centre_spread']),
                             rings=[dict(line=r['line'], locus=r['locus'], centre=[float(v) for v in r['fit']['centre']], radius=float(r['fit']['radius']), residual=float(r['fit']['residual']),
                                         arc_deg=float(r['fit']['arc_deg']), n=int(r['fit']['n']), tokens=[[u['first'], u['last']] for u in r['units']]) for r in w['rings']],
                             lines=sorted(ring_lines), words=len(members), tokens=sum(u['last'] - u['first'] + 1 for u in members), labels=[]))
            recs[-1]['_near'] = near
        # a nearby label joins the nearest wheel only (never guessed into two)
        if labels and len(recs) > 1:
            best: Dict[tuple, tuple] = {}
            for k, rec in enumerate(recs):
                for d, l, u in rec['_near']:
                    key = (u['first'], u['last'])
                    if key not in best or d < best[key][0]:
                        best[key] = (d, k)
            for k, rec in enumerate(recs):
                rec['labels'] = sorted([[l, u['first'], u['last']] for d, l, u in rec['_near'] if best[(u['first'], u['last'])][1] == k], key=lambda t: (t[1], t[2]))
        else:
            for rec in recs:
                rec['labels'] = sorted([[l, u['first'], u['last']] for d, l, u in rec['_near']], key=lambda t: (t[1], t[2]))
        for rec in recs:
            del rec['_near']
        out[folio] = dict(H=H, W=W, wheels=recs, rejected=[dict(line=r['line'], locus=r['locus'], reason=r['reason'], fit=r['fit']) for r in rejected],
                          circular_lines=len(circ), n_units=sum(len(units[l]) for l in idx))
    return out


def fit_wheels(app, ms=None, labels: bool = True) -> dict:
    """Fit the wheels of every page of a bundle.

    Reads the most complete recorded rectangles the bundle carries (the review's sensitivity geometry when present,
    as the orientation records do), takes the circular lines from the bundle's orientation records (attached if
    missing) and returns the product structure that ``build`` writes.

    Args:
        app: the manuscript bundle (any policy; the recorded warp state is the natural one, circular lines are not
            moved by the warp in any case).
        ms: the Manuscript the bundle follows (optional; locus types are read from the bundle or the resource).
        labels: list nearby non-paragraph units per wheel.

    Returns:
        {version, frame, warp, source, policy, review_version, words_sha256, geometry_sha256, parameters, pages: {folio:
        {...}}, summary: {pages_with_wheels, wheels, rejected_loci, accepted_boxes, zodiac_pages, ...}}. A ring names its
        locus and its tokens by their places in that line, a label likewise and a rejected ring by its locus, so the
        product holds for any stream; ``place`` gives the line and token indices of a bundle.

    Example:
        >>> from vmsspatial import Manuscript, load_bundle            # doctest: +SKIP
        >>> ms = Manuscript.load(); app = load_bundle('sensitivity', warp='recorded')   # doctest: +SKIP
        >>> prod = fit_wheels(app, ms); prod['summary']['wheels']      # doctest: +SKIP
        34
    """
    from .frames import tags
    from .orientation import attach
    attach(app, ms)
    geometry = _geometry(app)
    kinds = [L['orientation']['kind'] for L in app['lines']]
    cats = _categories(app, ms)
    pages = fit_pages(app, geometry, kinds, cats, labels=labels)
    detected = set(tags(app)['detected_pages'])
    for folio, rec in pages.items():
        rec['frame'] = 'detected' if folio in detected else 'recorded'
    section = {}
    if ms is not None:
        for p in (ms.pages if hasattr(ms, 'pages') else ms['pages']):
            section[p['folio']] = p.get('section_name')
    prod = dict(version=VERSION, built=date.today().isoformat(), frame='recorded', warp='recorded', source=tags(app)['source'], policy=app.get('policy'),
                review_version=(app.get('geometry_provenance') or {}).get('review_version'),
                words_sha256=digest(app['words']), geometry_sha256=digest(geometry), orientation_version=app.get('orientation_version'),
                parameters=dict(min_boxes=MIN_BOXES, min_arc_deg=MIN_ARC_DEG, min_radius_H=MIN_RADIUS_H, max_residual_H=MAX_RESIDUAL_H, max_residual_share=MAX_RESIDUAL_SHARE,
                                group_share=GROUP_SHARE, H='median recorded box height of the page\'s paragraph-line rectangles (all rectangles when none)',
                                fit='algebraic least squares on distinct recorded box centres, solved after centring (orientation.circle_fit)',
                                grouping='complete linkage of accepted ring centres within max(H, group_share x smaller radius); wheel centre = coordinate-wise median, radius = largest ring'),
                note='Wheels are fitted on the recorded rectangles of circular lines; a page in the detected frame (fRos) carries frame "detected" in its record. '
                     'A wheel is a property of the recorded rectangles, not of the ink, and a centred composite (centered_layout) is a display transform, not evidence.',
                pages=_by_locus(pages, app), summary=summarize(pages, section))
    return prod


def _by_locus(pages: Dict[str, dict], app) -> Dict[str, dict]:
    """Line and token indices of the bundle replaced by loci and places within a line."""
    lines = app['lines']
    out = {}
    for folio, rec in pages.items():
        wheels = []
        for w in rec['wheels']:
            rings = []
            for r in w['rings']:
                s = lines[r['line']]['start']
                rings.append(dict({k: v for k, v in r.items() if k != 'line'}, tokens=[[a - s, b - s] for a, b in r['tokens']]))
            labels = [[str(lines[l]['locus']), a - lines[l]['start'], b - lines[l]['start']] for l, a, b in w['labels']]
            wheels.append(dict({k: v for k, v in w.items() if k != 'lines'}, rings=rings, labels=labels))
        out[folio] = dict(rec, wheels=wheels, rejected=[{k: v for k, v in r.items() if k != 'line'} for r in rec['rejected']])
    return out


def place(product: dict, app) -> Optional[dict]:
    """The product with rings, labels and rejected loci carrying the `line` and `tokens` indices of the bundle `app`,
    whatever its order or pages. None when the bundle has other rectangles than the product was fitted on."""
    if product.get('review_version') is None or product['review_version'] != (app.get('geometry_provenance') or {}).get('review_version'):
        return None
    line_of = {(L['page'], str(L['locus'])): l for l, L in enumerate(app['lines'])}
    pages = {}
    for folio, rec in product['pages'].items():
        if any((folio, r['locus']) not in line_of for w in rec['wheels'] for r in w['rings']) or any((folio, r['locus']) not in line_of for r in rec['rejected']):
            continue
        wheels = []
        for w in rec['wheels']:
            rings = []
            for r in w['rings']:
                l = line_of[(folio, r['locus'])]
                s = app['lines'][l]['start']
                rings.append(dict(r, line=l, tokens=[[a + s, b + s] for a, b in r['tokens']]))
            labels = []
            for locus, a, b in w.get('labels', []):
                l = line_of.get((folio, locus))
                if l is not None:
                    labels.append([l, a + app['lines'][l]['start'], b + app['lines'][l]['start']])
            wheels.append(dict(w, rings=rings, labels=labels, lines=sorted(r['line'] for r in rings)))
        pages[folio] = dict(rec, wheels=wheels, rejected=[dict(r, line=line_of[(folio, r['locus'])]) for r in rec['rejected']])
    return dict(product, pages=pages)


def wheels_for(app, ms=None) -> dict:
    """The wheels of a bundle with its own line and token indices: the shipped product when it was fitted on the same
    rectangles, in any order, else a fresh fit."""
    try:
        prod = place(load_wheels(), app)
    except paths.DataMissing:
        prod = None
    return prod if prod is not None else place(fit_wheels(app, ms), app)


def summarize(pages: Dict[str, dict], section: Optional[Dict[str, str]] = None) -> dict:
    """Counts over a product's pages: pages with wheels, wheels, rejected loci, accepted boxes, wheels per page."""
    section = section or {}
    with_wheels = {f: p for f, p in pages.items() if p['wheels']}
    return dict(pages_with_circular_lines=sum(1 for p in pages.values() if p['circular_lines']), pages_with_wheels=len(with_wheels),
                wheels=sum(len(p['wheels']) for p in pages.values()), rejected_loci=sum(len(p['rejected']) for p in pages.values()),
                accepted_boxes=sum(w['words'] for p in pages.values() for w in p['wheels']),
                accepted_tokens=sum(w['tokens'] for p in pages.values() for w in p['wheels']),
                wheels_per_page={f: len(p['wheels']) for f, p in with_wheels.items()},
                by_section=dict(Counter(section.get(f, '?') for f in with_wheels for _ in pages[f]['wheels'])) if section else None,
                rejection_reasons=dict(Counter(r['reason'] for p in pages.values() for r in p['rejected'])))


# ----------------------------------------------------------------------------- the product
def load_wheels(path=None, reload: bool = False) -> dict:
    """The shipped wheels product (``PRODUCT_KEY``), read once.

    Args:
        path: another file (default: data/manuscript/wheels.json.gz through ``paths.resolve``).
        reload: re-read even when cached.

    Returns:
        the product dict written by ``build`` (see ``fit_wheels``).

    Example:
        >>> load_wheels()['summary']['wheels']          # doctest: +SKIP
        34
    """
    key = str(path) if path else ''
    if reload or key not in _PRODUCT:
        _PRODUCT[key] = read_json(path or paths.resolve(PRODUCT_KEY))
    return _PRODUCT[key]


def build(app=None, ms=None, out=None, log=print) -> dict:
    """Fit the wheels on the sensitivity bundle in the recorded warp state (default shape) and write the product.

    Args:
        app: the bundle (default ``load_bundle('sensitivity', warp='recorded')``).
        ms: its Manuscript (default ``Manuscript.load()``).
        out: output path (default the data folder's ``PRODUCT_KEY``).
        log: a print-like callable or None.

    Returns:
        the product.

    Example:
        >>> build()                                     # doctest: +SKIP
    """
    if app is None:
        from .bundle import load_bundle
        app = load_bundle('sensitivity', warp='recorded')
    if ms is None:
        from .bundle import manuscript_of
        ms = manuscript_of(app)
    prod = fit_wheels(app, ms)
    out = out or (paths.data_dir() / PRODUCT_KEY)
    write_json(prod, out)
    _PRODUCT.clear()
    if log:
        s = prod['summary']
        log('wrote %s: %d wheels on %d pages, %d rejected circular loci, %d accepted boxes' % (out, s['wheels'], s['pages_with_wheels'], s['rejected_loci'], s['accepted_boxes']))
    return prod


def page_wheels(folio: str, product: Optional[dict] = None) -> dict:
    """One page's record of the product ({H, W, wheels, rejected, ...}; empty when the page has no circular line)."""
    prod = product or load_wheels()
    return prod['pages'].get(folio) or dict(H=None, W=None, wheels=[], rejected=[], circular_lines=0, n_units=0, frame='recorded')


def wheels_table(product: Optional[dict] = None) -> List[dict]:
    """The product's wheels as flat rows (for a CSV): folio, id, centre, radius, rings, boxes, centre spread."""
    prod = product or load_wheels()
    rows = []
    for folio, p in prod['pages'].items():
        for w in p['wheels']:
            rows.append(dict(folio=folio, id=w['id'], cx=w['centre'][0], cy=w['centre'][1], radius=w['radius'], rings=len(w['rings']), boxes=w['words'],
                             centre_spread=w['centre_spread'], frame=p.get('frame', 'recorded')))
    return rows


# ----------------------------------------------------------------------------- the display transform
def centered_layout(app, ms=None, folio: str = None, wheels: Optional[dict] = None, labels: bool = False, pages: Optional[Sequence[str]] = None) -> dict:
    """Each wheel of a page (or of several pages) translated so that its centre lies at (0, 0): the display transform
    of the comparison workspace. Nothing else changes: no scaling, no rotation, no radius normalisation, no word
    rearrangement. The result is tagged frame 'display' so that ``frames.require_same`` refuses to combine it with
    measured geometry.

    Args:
        app: the bundle whose rectangles are drawn (its warp state is recorded in the result; circular lines are the
            same in both states).
        ms: the Manuscript (optional).
        folio: one page, or `pages` for several.
        wheels: a wheels product (default: the shipped one, refitted from the bundle when it was built on other words).
        labels: include each wheel's nearby non-paragraph units (kind 'nearby label').
        pages: several folios.

    Returns:
        {frame: 'display', warp, source, folios, wheels: [{id, folio, centre (recorded), radius, centre_spread,
        rings: [...], words: [{first, last, line, locus, text, kind, rect (centred)}]}], rejected: [...], note}.

    Example:
        >>> lay = centered_layout(app, ms, 'f68r2')      # doctest: +SKIP
        >>> [w['id'] for w in lay['wheels']]              # doctest: +SKIP
        ['f68r2/wheel1', 'f68r2/wheel2']
    """
    from .frames import tags, tag
    folios = list(pages) if pages else ([folio] if folio else [])
    if not folios:
        raise ValueError('name a folio or pages')
    prod = wheels_for(app, ms) if wheels is None else place(wheels, app)
    t = tags(app)
    out_wheels, rejected = [], []
    for f in folios:
        rec = page_wheels(f, prod)
        for w in rec['wheels']:
            cx, cy = w['centre']
            words = []
            for r in w['rings']:
                for first, last in r['tokens']:
                    b = app['geometry'][first]
                    if not b:
                        continue
                    words.append(dict(first=first, last=last, line=r['line'], locus=r['locus'], text=' '.join(app['words'][first:last + 1]), kind='circular',
                                      rect=[b[0] - cx, b[1] - cy, b[2] - cx, b[3] - cy]))
            if labels:
                for l, first, last in w.get('labels', []):
                    b = app['geometry'][first]
                    if not b:
                        continue
                    words.append(dict(first=first, last=last, line=l, locus=str(app['lines'][l]['locus']), text=' '.join(app['words'][first:last + 1]), kind='nearby label',
                                      rect=[b[0] - cx, b[1] - cy, b[2] - cx, b[3] - cy]))
            out_wheels.append(dict(id=w['id'], folio=f, centre=list(w['centre']), radius=w['radius'], centre_spread=w['centre_spread'], rings=w['rings'], words=words, H=rec['H']))
        rejected += [dict(r, folio=f) for r in rec['rejected']]
    out = dict(folios=folios, wheels=out_wheels, rejected=rejected, source_frame=t['frame'], source_warp=t['warp'],
               note='Display transform: each wheel translated to a common centre, no scaling, rotation, radius normalisation or word rearrangement. '
                    'A coincident centre is imposed by the display and is not evidence of a shared template; the centred coordinates are not measured geometry.')
    tag(out, frame=DISPLAY_FRAME, warp=t['warp'], source=t['source'])
    return out


def extent(layout: dict, margin: float = 30.0, step: float = 50.0) -> float:
    """The half-frame (px) that holds every centred rectangle of a layout, rounded up to a multiple of `step`."""
    r = 0.0
    for w in layout['wheels']:
        for u in w['words']:
            r = max(r, max(abs(v) for v in u['rect']))
    return float(math.ceil((r + margin) / step) * step) if r else 650.0
