"""Comparing the layout of two pages (or two faces of two bifolia) on their recorded word rectangles.

The question the module answers is descriptive: when the text block of page A is laid over the text block of page B,
with ONE translation and nothing else (no rotation, no scaling, no line fitting), how much of the occupied area is
shared, and how alike is the wording where the rectangles overlap or stand close? It is the comparison workspace of
the October 2026 bifolium study, ported from its JavaScript so that every number can be recomputed from the shipped
bundle (docs/COMPARE.md has the formulas, a worked example and what the scores do not mean).

Selection. A page's units are its located rectangles once each (a shared rectangle counts once), ordered left to
right on horizontal lines and in stream order elsewhere, each with a baseline anchor (the toolkit's baseline point
of the word; non-horizontal loci, which carry no baseline, use a declared box-centre anchor). Its blocks are the
page opening (the first five paragraph lines), the whole page, each canonical paragraph (the paragraph structure of
the transcription) and each non-paragraph locus. ``select`` chooses a block, a line cutoff (the top 1..5 lines or all),
a coordinate variant (recorded, or flat with the stored page warp and the anchors transported by each box's own
shift), an alignment ('starts': translate the block so its first box's anchor is the origin; 'page': translate the
whole page by its opening anchor, so a later paragraph keeps its position within the page) and a scale (pixels, or
body height: 30 / the page's median body box height).

Metrics (``measure``, ``details``, ``per_line``). Occupied-area Dice on the exact rectangle unions; direct-overlap
EVA similarity (each box against the joined atoms of the boxes that overlap it by at least a fifth of the smaller
area, both directions, weighted by intersection area); nearby EVA similarity (the best single match within half a
body word width and half a body box height, both directions, target reuse allowed); the per-line table (line i
against line i without realignment); word-segment correspondences (direct one-to-many neighbourhoods, transitive
connected groups, nearby best matches) with the edit distance on the lossless EVA atoms (``vmsspatial.units``). The
first box is scored like any other: a page's opening word is often a hapax, so comparing it directly is the point, and
its forced overlap under 'starts' alignment lifts Dice only slightly. ``first_line_scan`` and ``rank_pairs`` add the position-constrained EVA similarity,
the horizontal-occupancy Dice and the Jensen-Shannon distance of the lines' unit-pair distributions, and rank every
eligible page pair, or bifolium face pair, by the worse of the Dice rank and the JS rank.

Bifolia (``sheet_rows``, ``joint``): the inner face of a flat bifolium is A verso beside B recto, the outer face B
verso beside A recto; corresponding slots are compared page by page and the joint value is the equal-page mean and
the weaker-page minimum, withheld unless every slot is complete.

From code, ``Comparison`` wraps all of this: ``c = Comparison(); pair = c.pages('f20v', 'f21r', cutoff=3);
pair.scores(); pair.segments(); pair.lines(); pair.plot(); c.bifolia(...); c.composite([...]); c.rank(...).to_csv(...)``.
``page_drift`` gives a page's pre-correction drift indicator (the median signed baseline chord angle of its
paragraph lines, in either warp state) and ``split_lines`` the inline line split of the overlay (display only).

Every selection carries the frame and warp tags of its coordinates. A translation-only overlay score describes
resemblance; it does not test copying (docs/PITFALLS.md 25).
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from .bundle import digest
from .units import atom_strings, zattera

COORDINATES = ('flat', 'recorded')
ALIGNMENTS = ('starts', 'page')
SCALES = ('pixels', 'body_height')
CUTOFFS = (1, 2, 3, 4, 5, 'all')
FACES = {'inner': ['Av', 'Br'], 'outer': ['Bv', 'Ar'], 'both': ['Av', 'Br', 'Bv', 'Ar']}     # a face's slots in display order: inner face first
INTRUSION = ('intrusion_aligned', 'intrusion_misaligned')
EDGE_SHARE = 0.2              # a direct correspondence needs this share of the smaller rectangle in the intersection
NEAR_W, NEAR_H = 0.5, 0.5     # the nearby search: half a body word width, half a body box height
SPATIAL_GATE = 0.2            # the position-constrained edit: parent x intervals overlap by this share of the shorter
BODY_HEIGHT_PX = 30.0         # the body-height scale maps the page's median body box height to 30 px
SCAN_FIELDS = ('spatial', 'x_dice', 'dice_current', 'dice_recorded', 'spatial_body', 'edit_all', 'js_word', 'js_joined')
VERSION = '2026.10.31.1'

_CACHE: Dict[int, dict] = {}


# ----------------------------------------------------------------------------- exact geometry and text primitives
def intersection(a, b):
    """The intersection rectangle of two [x0, y0, x1, y1] rectangles, or None when it has no area."""
    r = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return r if r[2] > r[0] and r[3] > r[1] else None


def area(r) -> float:
    return (r[2] - r[0]) * (r[3] - r[1]) if r else 0.0


def union_area(rects) -> float:
    """The exact area of the union of axis-aligned rectangles (a vertical sweep over the distinct x edges, the
    y intervals merged inside every strip).

    Args:
        rects: sequence of [x0, y0, x1, y1].

    Returns:
        the union area (two adjoining rectangles count their shared edge once; nested ones count once).

    Example:
        >>> union_area([[0, 0, 10, 10], [5, 0, 15, 10]])
        150.0
    """
    xs = sorted({float(r[0]) for r in rects} | {float(r[2]) for r in rects})
    total = 0.0
    for k in range(1, len(xs)):
        x = (xs[k - 1] + xs[k]) / 2
        spans = sorted(((r[1], r[3]) for r in rects if r[0] < x and r[2] > x), key=lambda s: s[0])
        lo = hi = None
        length = 0.0
        for a, b in spans:
            if lo is None:
                lo, hi = a, b
            elif a <= hi:
                hi = max(hi, b)
            else:
                length += hi - lo
                lo, hi = a, b
        if lo is not None:
            length += hi - lo
        total += (xs[k] - xs[k - 1]) * length
    return float(total)


def edit(a: Sequence[str], b: Sequence[str]) -> int:
    """Levenshtein distance between two atom sequences (insertion, deletion, substitution cost 1).

    Example:
        >>> edit(['ch', 'o', 'l'], ['sh', 'o', 'l'])
        1
    """
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a):
        row = [i + 1]
        for j, y in enumerate(b):
            row.append(min(row[j] + 1, prev[j + 1] + 1, prev[j] + (0 if x == y else 1)))
        prev = row
    return prev[len(b)]


def similarity(a: Sequence[str], b: Sequence[str]) -> float:
    """1 - edit distance / the longer length (1 for two empty sequences).

    Example:
        >>> round(similarity(['d', 'a', 'ii', 'n'], ['d', 'a', 'i', 'n']), 2)
        0.75
    """
    return 1.0 - edit(a, b) / max(len(a), len(b), 1)


def atoms(text: str) -> List[str]:
    """The lossless EVA atoms of a word or a joined unit text (spaces removed): benches and pedestalled gallows,
    ligatures and extended atoms whole, every other character on its own."""
    return list(atom_strings(text.replace(' ', '')))


# ----------------------------------------------------------------------------- the page table
def _median(values, default):
    return float(np.median(values)) if len(values) else default


def prepare(app, ms=None, baseline: str = 'auto', table=False, log=None) -> dict:
    """The comparison data of a bundle: every page's units, lines, blocks, body size and baseline anchors in both
    warp states.

    Args:
        app: the manuscript bundle (any policy; the recorded or the flat warp state; the other state is derived with
            the shipped page warp). The sensitivity policy is the most complete reviewed geometry (shared boxes once).
        ms: the Manuscript the bundle follows (default ``bundle.manuscript_of(app)``).
        baseline: the anchor method, ``baselines.word_baselines``: 'auto' (ink where the page has clean ink records,
            glyph elsewhere), 'glyph', 'ink', 'centre', 'bottom'. The October 2026 workspace used 'glyph'.
        table: the stored baselines table (the product, True, or False to derive the points; derived by default so
            that the anchors carry no rounding).
        log: a print-like callable or None.

    Returns:
        {pages: {folio: page record}, folios: [...], frame tags of the recorded and flat geometry, baseline,
        provenance (digests), warp_version, ms}. A page record: folio, node, section, hand, group, side, leaf,
        panel, face, slot, quire_num, H, W, warp (``warp.page_status``), geometry_kind, lines [{index, locus, first,
        category, orientation, units, text, token_count}], units [{id, first, last, line, text, atoms, rect, flat,
        base, flat_base, anchor_kind, boundary, flags, clean, token_count}], blocks [{key, label, lines}].

    Example:
        >>> from vmsspatial import Manuscript, load_bundle                   # doctest: +SKIP
        >>> data = prepare(load_bundle('sensitivity', warp='recorded'), Manuscript.load())   # doctest: +SKIP
        >>> data['pages']['f75r']['H']                                        # doctest: +SKIP
        24.0
    """
    from . import warp as W
    from .baselines import word_baselines
    from .bundle import manuscript_of
    from .frames import tags
    from .geometry import line_units
    from .orientation import attach
    key = id(app)
    cached = _CACHE.get(key)
    if cached and cached['baseline'] == baseline and cached['_table'] == (table if isinstance(table, bool) else id(table)):
        return cached
    if ms is None:
        ms = manuscript_of(app)
    attach(app, ms)
    t = tags(app)
    if t['warp'] == 'recorded':
        rec_app = app
        flat_app = W.flatten_bundle(app)
    else:
        flat_app = app
        rec_app = W.transform(app, 'recorded')
        attach(rec_app, ms, force=True)
    rec_geom, flat_geom = rec_app['geometry'], flat_app['geometry']
    pts, info = word_baselines(rec_app, ms, baseline, table=table, details=True)
    choice = (info.get('auto') or {}).get('choice') or {}
    units = line_units(rec_app, ms, orientations=None)
    review = app.get('spatialReview')
    tokens = review['tokens'] if review else None
    detected = set(t['detected_pages'])
    pages_ms = ms.pages if hasattr(ms, 'pages') else ms['pages']
    lines_ms = ms.lines if hasattr(ms, 'lines') else ms['lines']
    prod = W.load_warp()
    pages = {}
    for p in pages_ms:
        folio = p['folio']
        lines, words = [], []
        for lid in range(p['start_line'], p['end_line']):
            L, B = lines_ms[lid], app['lines'][lid]
            li = len(lines)
            us = units[lid]
            kind = B['orientation']['kind']
            if kind == 'horizontal':
                us = sorted(us, key=lambda u: (u['box'][0] + u['box'][2]) / 2)
            ids = []
            for u in us:
                i, j = u['first'], u['last']
                rec, flat = rec_geom[i], flat_geom[i]
                point = pts[i]
                base = [float(point[0]), float(point[1])] if point is not None else [(rec[0] + rec[2]) / 2, (rec[1] + rec[3]) / 2]
                moved = rec[3] - flat[3]
                text = ' '.join(app['words'][i:j + 1])
                toks = tokens[i:j + 1] if tokens else []
                flags = sorted({f for tk in toks for f in tk.get('flags', [])})
                method = choice.get(folio, baseline) if baseline == 'auto' else baseline
                words.append(dict(id=len(words), first=i, last=j, line=li, text=text, atoms=atoms(text),
                                  rect=[float(v) for v in rec], flat=[float(v) for v in flat], base=base, flat_base=[base[0], base[1] - moved],
                                  anchor_kind=method if point is not None else 'box centre', boundary=toks[-1].get('boundary') if toks else None,
                                  flags=flags, clean=bool(i == j and not flags and (toks[0].get('strict', True) if toks else True)), token_count=j - i + 1))
                ids.append(words[-1]['id'])
            lines.append(dict(index=li, locus=str(L['locus']), first=bool(L['first']), category=(L.get('locus_type') or B.get('locus_type') or '?')[0],
                              orientation=kind, units=ids, text=' '.join(L['words']), token_count=len(L['words'])))
        pages[folio] = dict(folio=folio, node=p['node'], section=p.get('section_name'), hand=p.get('hand'), group=p.get('group'), side=p.get('side'), leaf=p.get('leaf'),
                            panel=p.get('panel', ''), face=p.get('face'), slot=('A' if p.get('leaf') == p.get('A') else 'B') + str(p.get('side')), quire_num=p.get('quire_num'),
                            lines=lines, units=words, blocks=page_blocks(lines), warp=W.page_status(folio, prod),
                            geometry_kind='detected' if folio in detected else 'recorded', frame='detected' if folio in detected else 'recorded')
        body = [w for w in words if lines[w['line']]['category'] == 'P'] or words
        pages[folio]['H'] = _median([w['rect'][3] - w['rect'][1] for w in body], 30.0)
        pages[folio]['W'] = _median([w['rect'][2] - w['rect'][0] for w in body], 60.0)
        pages[folio]['orientations'] = dict(Counter(l['orientation'] for l in lines))
    data = dict(pages=pages, folios=[p['folio'] for p in pages_ms], recorded_tags=tags(rec_app), flat_tags=tags(flat_app), baseline=baseline,
                baseline_pages=dict(Counter(choice.values())) if choice else {baseline: len(pages)}, _table=(table if isinstance(table, bool) else id(table)),
                provenance=dict(words_sha256=digest(app['words']), geometry_sha256=digest(rec_geom), flat_geometry_sha256=digest(flat_geom), policy=app.get('policy'),
                                pages=app.get('pages'), order=app.get('order'), page_warp_version=prod.get('version'), baseline=baseline, version=VERSION),
                ms=ms, app=app, version=VERSION)
    if len(_CACHE) > 4:
        _CACHE.clear()
    _CACHE[key] = data
    if log:
        log('compare data: %d pages, %d units, anchors %s' % (len(pages), sum(len(p['units']) for p in pages.values()), data['baseline_pages']))
    return data


def page_blocks(lines: Sequence[dict]) -> List[dict]:
    """The blocks of a page from its line records: 'opening' (the first five paragraph lines, or the first five lines
    when the page has no paragraph line), 'page' (every line), 'p1', 'p2', ... (the canonical paragraphs: runs of
    paragraph lines broken at `first`) and 'l<index>' (each non-paragraph locus on its own)."""
    para = [l['index'] for l in lines if l['category'] == 'P']
    groups, current = [], []
    for li in para:
        if lines[li]['first'] and current:
            groups.append(current)
            current = []
        current.append(li)
    if current:
        groups.append(current)
    first = para[:5] or list(range(min(5, len(lines))))
    blocks = [dict(key='opening', label='Page opening', lines=first), dict(key='page', label='Whole page, all loci', lines=[l['index'] for l in lines])]
    blocks += [dict(key='p%d' % (i + 1), label='Paragraph %d, loci %s-%s' % (i + 1, lines[g[0]]['locus'], lines[g[-1]]['locus']), lines=g) for i, g in enumerate(groups)]
    blocks += [dict(key='l%d' % l['index'], label='%s locus %s' % (l['orientation'].capitalize(), l['locus']), lines=[l['index']]) for l in lines if l['category'] != 'P']
    return blocks


def load(policy: str = 'sensitivity', warp: str = 'recorded', baseline: str = 'auto', order: str = 'folio', pages: str = 'all', log=None) -> dict:
    """``prepare`` on a freshly loaded bundle and manuscript.

    Args:
        policy: 'sensitivity' (default here: the most complete reviewed geometry, shared boxes drawn once) or 'strict'.
        warp: the state the bundle is loaded in ('recorded' is the natural input; the flat state is derived exactly).
        baseline: the anchor method (see ``prepare``).
        order, pages: the manuscript shape (defaults: by bifolium, every page and locus).

    Returns:
        the comparison data.

    Example:
        >>> data = load()                                                     # doctest: +SKIP
        >>> measure(select(data, 'f20v'), select(data, 'f21r'))['dice']       # doctest: +SKIP
    """
    from .bundle import load_bundle
    from .manuscript import Manuscript
    ms = Manuscript.load(order, pages=pages)
    app = load_bundle(policy, pages=pages, order=order, warp=warp)
    return prepare(app, ms, baseline=baseline, log=log)


def catalog(data: dict) -> List[dict]:
    """One row per page (folio, node, section, hand, group, slot, face, H, W, lines, units, warp fitted, blocks)."""
    return [dict(folio=p['folio'], node=p['node'], section=p['section'], hand=p['hand'], group=p['group'], slot=p['slot'], face=p['face'], leaf=p['leaf'], side=p['side'],
                 panel=p['panel'], H=p['H'], W=p['W'], lines=len(p['lines']), units=len(p['units']), warp_fitted=bool(p['warp']['fitted']), geometry_kind=p['geometry_kind'],
                 blocks=[b['key'] for b in p['blocks']]) for p in data['pages'].values()]


# ----------------------------------------------------------------------------- selection
def block_of(page: dict, key: str) -> dict:
    for b in page['blocks']:
        if b['key'] == key:
            return b
    return page['blocks'][0]


def select(data: dict, folio: str, block: str = 'opening', cutoff='all', coordinates: str = 'flat', alignment: str = 'starts', scale: str = 'pixels',
           extent: Optional[str] = None) -> dict:
    """The units of one block of a page, translated to its anchor, ready for ``measure``.

    Args:
        data: ``prepare`` / ``load``.
        folio: the page.
        block: 'opening' | 'page' | 'p1'.. | 'l<index>' (``page_blocks``).
        cutoff: the top 1..5 lines of the block, or 'all'.
        coordinates: 'flat' (the stored page warp applied, anchors transported by each box's shift) or 'recorded'.
        alignment: 'starts' (the block's first box's anchor becomes the origin) or
            'page' (the page's opening anchor becomes the origin, so later paragraphs keep their page positions).
        scale: 'pixels' or 'body_height' (x and y multiplied by 30 / the page's median body box height).
        extent: a convenience: 'whole' = block 'page' with cutoff 'all'; 'top' = block 'opening'; None keeps `block`.

    Returns:
        a selection: {page (the page record), block, all [units with rect (translated, scaled), baseline, line
        (index within the block), line_abs, anchor, selected], chosen (the selected units), line_info, W, H (scaled),
        origin, anchor_kind, available (False when the block's first line has no box: then nothing is scored and
        fallback_line names the located line that sets the origin), complete, expected, located, total_lines, nonhorizontal, coordinates,
        alignment, scale, frame, warp}.

    Example:
        >>> s = select(data, 'f20v', cutoff=3)                     # doctest: +SKIP
        >>> len(s['chosen']), s['complete']                          # doctest: +SKIP
    """
    if coordinates not in COORDINATES:
        raise ValueError('coordinates must be one of %r' % (COORDINATES,))
    if alignment not in ALIGNMENTS:
        raise ValueError('alignment must be one of %r' % (ALIGNMENTS,))
    if scale not in SCALES:
        raise ValueError('scale must be one of %r' % (SCALES,))
    if cutoff not in CUTOFFS:
        raise ValueError('cutoff must be 1..5 or "all"')
    page = data['pages'][folio]
    if extent == 'whole':
        block, cutoff = 'page', 'all'
    elif extent == 'top':
        block = 'opening'
    b = block_of(page, block)
    order = {li: i for i, li in enumerate(b['lines'])}
    H, W = page['H'] or 30.0, page['W'] or 60.0
    factor = BODY_HEIGHT_PX / H if scale == 'body_height' else 1.0
    rect_of = (lambda u: u['rect']) if coordinates == 'recorded' else (lambda u: u['flat'])
    base_of = (lambda u: u['base']) if coordinates == 'recorded' else (lambda u: u['flat_base'])
    source = page['units']
    us = [u for u in source if u['line'] in order]
    page_start = page['blocks'][0]['lines'][0] if page['blocks'][0]['lines'] else None
    if alignment == 'page':
        anchor = next((u for u in source if u['line'] == page_start), source[0] if source else None)
    else:
        anchor = next((u for u in us if u['line'] == b['lines'][0]), None) if b['lines'] else None
    # no box on the block's first line: nothing is scored (available stays False), but the block is still drawn and
    # its lines still read, from its first located box
    fallback = None if anchor or not us else min(us, key=lambda u: order[u['line']])
    origin = base_of(anchor) if anchor else base_of(fallback) if fallback else [0.0, 0.0]
    take = len(b['lines']) if cutoff == 'all' else int(cutoff)
    all_units = []
    for u in us:
        r = rect_of(u)
        all_units.append(dict(u, line_abs=u['line'], line=order[u['line']], rect=[(r[0] - origin[0]) * factor, (r[1] - origin[1]) * factor, (r[2] - origin[0]) * factor, (r[3] - origin[1]) * factor],
                              baseline=(base_of(u)[1] - origin[1]) * factor, anchor=u is anchor, selected=order[u['line']] < take))
    chosen = [u for u in all_units if u['selected']]
    located = {u['line'] for u in chosen}
    expected = len(b['lines']) if cutoff == 'all' else int(cutoff)
    tags = data['recorded_tags'] if coordinates == 'recorded' else data['flat_tags']
    return dict(page=page, folio=folio, block=b, all=all_units, chosen=chosen,
                line_info=[dict(index=i, line_abs=li, locus=page['lines'][li]['locus'], text=page['lines'][li]['text'], orientation=page['lines'][li]['orientation']) for i, li in enumerate(b['lines'])],
                W=W * factor, H=H * factor, origin=list(origin), anchor_kind=anchor['anchor_kind'] if anchor else None, available=anchor is not None,
                fallback_line=order[fallback['line']] if fallback else None,
                complete=len(located) == expected and len(b['lines']) >= expected, expected=expected, located=len(located), total_lines=len(b['lines']),
                nonhorizontal=sorted({page['lines'][u['line_abs']]['orientation'] for u in chosen} - {'horizontal'}),
                coordinates=coordinates, alignment=alignment, scale=scale, cutoff=cutoff, frame=page['frame'], warp=tags['warp'])


# ----------------------------------------------------------------------------- metrics
def _empty(A, B):
    return dict(dice=None, local_segment_similarity=None, nearby_similarity=None, units_a=len(A), units_b=len(B))


def measure_units(raw_a: Sequence[dict], raw_b: Sequence[dict], W: float, H: float, same_row: bool = False) -> dict:
    """The three overlay scores on two unit lists already in one frame (each unit: rect, atoms, line, anchor).

    Anchors are dropped. Dice = 2 x shared area / (area A + area B) on the exact rectangle unions (per line when
    `same_row`); direct-overlap EVA similarity = the intersection-area-weighted mean, over every box in either
    direction, of the similarity between its atoms and the joined atoms of the boxes overlapping it by at least
    EDGE_SHARE of the smaller area; nearby similarity = the mean over both directions of each box's best single
    match within NEAR_W x W horizontally and NEAR_H x H vertically.

    Returns:
        {dice, local_segment_similarity, nearby_similarity, units_a, units_b} (None where undefined).
    """
    A, B = list(raw_a), list(raw_b)
    out = _empty(A, B)
    if not A or not B:
        return out
    inter = [[None if (same_row and a['line'] != b['line']) else intersection(a['rect'], b['rect']) for b in B] for a in A]
    if same_row:
        shared = total = 0.0
        for line in {u['line'] for u in A + B}:
            shared += union_area([r for i, row in enumerate(inter) if A[i]['line'] == line for r in row if r])
            total += union_area([u['rect'] for u in A if u['line'] == line]) + union_area([u['rect'] for u in B if u['line'] == line])
    else:
        shared = union_area([r for row in inter for r in row if r])
        total = union_area([u['rect'] for u in A]) + union_area([u['rect'] for u in B])
    adj = [[bool(r) and area(r) / min(area(A[i]['rect']), area(B[j]['rect'])) >= EDGE_SHARE for j, r in enumerate(row)] for i, row in enumerate(inter)]
    weighted = weight = 0.0
    for i in range(len(A)):
        js = [j for j in range(len(B)) if adj[i][j]]
        if not js:
            continue
        w = union_area([inter[i][j] for j in js])
        weighted += w * similarity(A[i]['atoms'], [x for j in js for x in B[j]['atoms']])
        weight += w
    for j in range(len(B)):
        ix = [i for i in range(len(A)) if adj[i][j]]
        if not ix:
            continue
        w = union_area([inter[i][j] for i in ix])
        weighted += w * similarity([x for i in ix for x in A[i]['atoms']], B[j]['atoms'])
        weight += w
    best_a, best_b = [None] * len(A), [None] * len(B)
    for i, a in enumerate(A):
        ra = a['rect']
        for j, b in enumerate(B):
            if same_row and a['line'] != b['line']:
                continue
            rb = b['rect']
            if max(0.0, ra[0] - rb[2], rb[0] - ra[2]) <= NEAR_W * W and max(0.0, ra[1] - rb[3], rb[1] - ra[3]) <= NEAR_H * H:
                s = similarity(a['atoms'], b['atoms'])
                best_a[i] = max(best_a[i] or 0.0, s)
                best_b[j] = max(best_b[j] or 0.0, s)
    near = [v for v in best_a + best_b if v is not None]
    out.update(dice=2 * shared / total if total else None, local_segment_similarity=weighted / weight if weight else None,
               nearby_similarity=sum(near) / len(near) if near else None)
    return out


def measure(a: dict, b: dict, same_row: bool = False) -> dict:
    """The overlay scores of two selections (``select``): occupied-area Dice, direct-overlap EVA similarity, nearby
    EVA similarity, and the scored unit counts. W and H are the means of the two pages' body sizes. Both selections
    must be in the same coordinates (frame and warp).

    Args:
        a, b: selections.
        same_row: restrict overlaps and matches to units with the same line index within their blocks.

    Returns:
        {dice, local_segment_similarity, nearby_similarity, units_a, units_b}; all None when a selection has no anchor.

    Example:
        >>> measure(select(data, 'f20v', cutoff=3), select(data, 'f21r', cutoff=3))   # doctest: +SKIP
        {'dice': 0.84..., 'local_segment_similarity': ..., 'nearby_similarity': ..., 'units_a': ..., 'units_b': ...}
    """
    from .frames import require_same
    require_same(dict(frame=a['frame'], warp=a['warp'], source='voynichese'), dict(frame=b['frame'], warp=b['warp'], source='voynichese'), 'the two selections')
    if not a['available'] or not b['available']:
        return dict(dice=None, local_segment_similarity=None, nearby_similarity=None, units_a=0, units_b=0)
    return measure_units(a['chosen'], b['chosen'], (a['W'] + b['W']) / 2, (a['H'] + b['H']) / 2, same_row)


def _record(A, B, ix, js):
    aa, bb = [A[i] for i in ix], [B[j] for j in js]
    xa, xb = [x for u in aa for x in u['atoms']], [x for u in bb for x in u['atoms']]
    return dict(a=[u['id'] for u in aa], b=[u['id'] for u in bb], text_a=' | '.join(u['text'] for u in aa), text_b=' | '.join(u['text'] for u in bb),
                similarity=similarity(xa, xb), edits=edit(xa, xb), lines_a=sorted({u['line'] + 1 for u in aa}), lines_b=sorted({u['line'] + 1 for u in bb}),
                clean=all(u['clean'] for u in aa + bb), flags=sorted({f for u in aa + bb for f in (u.get('flags') or [])}))


def details(a: dict, b: dict, same_row: bool = False) -> dict:
    """The word-segment correspondences behind the scores of two selections.

    Returns:
        {direct: one-to-many neighbourhoods (each box of A with the boxes of B that overlap it by EDGE_SHARE, and the
        reverse), connected: the transitive connected groups of that overlap graph, nearby: each box of A with its
        best single match within the nearby window}; every record has the unit ids, the joined texts, the similarity,
        the edit distance, the line numbers (1-based within the blocks), clean (no flagged or shared unit) and flags.

    Example:
        >>> details(select(data, 'f47r', cutoff=5), select(data, 'f56r', cutoff=5))['connected'][0]   # doctest: +SKIP
    """
    A, B = list(a['chosen']), list(b['chosen'])
    edges = [[] for _ in A]
    reverse = [[] for _ in B]
    for i, u in enumerate(A):
        for j, v in enumerate(B):
            if same_row and u['line'] != v['line']:
                continue
            r = intersection(u['rect'], v['rect'])
            if r and area(r) / min(area(u['rect']), area(v['rect'])) >= EDGE_SHARE:
                edges[i].append(j)
                reverse[j].append(i)
    direct = [_record(A, B, [i], js) for i, js in enumerate(edges) if js] + [_record(A, B, ix, [j]) for j, ix in enumerate(reverse) if ix]
    connected, seen_a, seen_b = [], set(), set()
    for i in range(len(A)):
        if i in seen_a or not edges[i]:
            continue
        todo, ix, js = [('a', i)], [], []
        while todo:
            side, k = todo.pop()
            seen = seen_a if side == 'a' else seen_b
            if k in seen:
                continue
            seen.add(k)
            if side == 'a':
                ix.append(k)
                todo += [('b', j) for j in edges[k]]
            else:
                js.append(k)
                todo += [('a', j) for j in reverse[k]]
        connected.append(_record(A, B, sorted(ix), sorted(js)))
    W, H = (a['W'] + b['W']) / 2, (a['H'] + b['H']) / 2
    nearby = []
    for i, u in enumerate(A):
        best = None
        for j, v in enumerate(B):
            if same_row and u['line'] != v['line']:
                continue
            r, s = u['rect'], v['rect']
            if max(0.0, r[0] - s[2], s[0] - r[2]) > NEAR_W * W or max(0.0, r[1] - s[3], s[1] - r[3]) > NEAR_H * H:
                continue
            score = similarity(u['atoms'], v['atoms'])
            if best is None or score > best[1]:
                best = (j, score)
        if best:
            nearby.append(_record(A, B, [i], [best[0]]))
    return dict(direct=direct, connected=connected, nearby=nearby)


def per_line(a: dict, b: dict) -> List[dict]:
    """Line i of selection a against line i of selection b, WITHOUT realigning the lines: the blocks stay translated
    by their anchors and only the units of the same line index are scored. The cumulative scores of a cutoff are not
    averages of these rows.

    Returns:
        [{line (1-based), dice, local_segment_similarity, nearby_similarity, units_a, units_b}] over the lines of the
        selections' cutoff.

    Example:
        >>> per_line(select(data, 'f47r', cutoff=5), select(data, 'f56r', cutoff=5))[0]['line']   # doctest: +SKIP
        1
    """
    n = max(a['expected'], b['expected'])
    W, H = (a['W'] + b['W']) / 2, (a['H'] + b['H']) / 2
    rows = []
    for line in range(n):
        A = [u for u in a['chosen'] if u['line'] == line]
        B = [u for u in b['chosen'] if u['line'] == line]
        rows.append(dict(line=line + 1, **measure_units(A, B, W, H)))
    return rows


def start_words(a: dict, b: dict, line: int = 0, count: int = 2) -> List[dict]:
    """The first `count` units of one line of both selections side by side with their atom similarity (the anchor
    included, marked), for the opening-word readout."""
    A = [u for u in a['all'] if u['line'] == line][:count]
    B = [u for u in b['all'] if u['line'] == line][:count]
    out = []
    for i in range(max(len(A), len(B))):
        ua, ub = A[i] if i < len(A) else None, B[i] if i < len(B) else None
        out.append(dict(position=i + 1, a=ua['text'] if ua else None, b=ub['text'] if ub else None,
                        similarity=similarity(ua['atoms'], ub['atoms']) if ua and ub else None, anchor=bool((ua and ua['anchor']) or (ub and ub['anchor']))))
    return out


def reading_lines(selection: dict, limit='all') -> List[dict]:
    """The lines of a selection as reading rows: the line info with its units and the median baseline (the reader's
    initial partner is chosen by baseline, ``nearest_reading_line``), and whether the line is scored."""
    rows = []
    for l in selection['line_info']:
        if limit != 'all' and l['index'] >= 5:
            continue
        units = [u for u in selection['all'] if u['line'] == l['index']]
        ys = sorted(u['baseline'] for u in units)
        rows.append(dict(l, units=units, baseline=ys[len(ys) // 2] if ys else None, scored=any(u['selected'] for u in units)))
    return rows


def nearest_reading_line(lines: Sequence[dict], baseline: Optional[float], fallback: int = 0) -> Optional[dict]:
    """The reading row whose baseline is nearest to `baseline` (the row `fallback` when none has one)."""
    located = [l for l in lines if l['baseline'] is not None]
    if baseline is None or not located:
        return next((l for l in lines if l['index'] == fallback), lines[0] if lines else None)
    return min(located, key=lambda l: abs(l['baseline'] - baseline))


# ----------------------------------------------------------------------------- bifolia
def face_slots(face: str, columns: str = 'both') -> List[str]:
    """The page slots of a bifolium face: inner = ['Av', 'Br'], outer = ['Bv', 'Ar'], both = all four; `columns`
    'A' or 'B' keeps one leaf.

    Example:
        >>> face_slots('inner', 'A')
        ['Av']
    """
    slots = FACES.get(face)
    if slots is None:
        raise ValueError("face must be 'inner', 'outer' or 'both'")
    return [s for s in slots if columns == 'both' or s[0] == columns]


def sheet_rows(data: dict, node_a: str, node_b: str, face: str = 'inner', choices: Optional[dict] = None, columns: str = 'both') -> List[dict]:
    """The corresponding pages of two bifolia, slot by slot. A slot with several panels (a foldout) resolves only by
    an explicit choice (`choices[slot] = {a: folio, b: folio, blockA, blockB}`); otherwise it stays None.

    Returns:
        [{slot, options_a, options_b, page_a, page_b (folios or None), block_a, block_b}].

    Example:
        >>> [(r['page_a'], r['page_b']) for r in sheet_rows(data, 'C:20-21', 'B:10-15', 'inner')]   # doctest: +SKIP
        [('f20v', 'f10v'), ('f21r', 'f15r')]
    """
    choices = choices or {}
    rows = []
    for slot in face_slots(face, columns):
        oa = [p['folio'] for p in data['pages'].values() if p['node'] == node_a and p['slot'] == slot]
        ob = [p['folio'] for p in data['pages'].values() if p['node'] == node_b and p['slot'] == slot]
        c = choices.get(slot, {})

        def resolve(options, key):
            if key in options:
                return key
            return options[0] if len(options) == 1 else None
        rows.append(dict(slot=slot, options_a=oa, options_b=ob, page_a=resolve(oa, c.get('a')), page_b=resolve(ob, c.get('b')),
                         block_a=c.get('blockA', 'opening'), block_b=c.get('blockB', 'opening')))
    return rows


def compare_sheets(data: dict, node_a: str, node_b: str, face: str = 'inner', cutoff=3, coordinates: str = 'flat', alignment: str = 'starts', scale: str = 'pixels',
                   choices: Optional[dict] = None, columns: str = 'both') -> dict:
    """``sheet_rows`` scored slot by slot and joined.

    Returns:
        {rows: [{slot, pages, a, b (selections), result}], joint: ``joint``}.

    Example:
        >>> compare_sheets(data, 'C:20-21', 'B:10-15', 'inner', cutoff=3)['joint']['mean']['dice']   # doctest: +SKIP
    """
    rows = []
    for r in sheet_rows(data, node_a, node_b, face, choices, columns):
        if not r['page_a'] or not r['page_b']:
            rows.append(dict(slot=r['slot'], pages=[r['page_a'], r['page_b']], a=None, b=None, result=None))
            continue
        a = select(data, r['page_a'], r['block_a'], cutoff, coordinates, alignment, scale)
        b = select(data, r['page_b'], r['block_b'], cutoff, coordinates, alignment, scale)
        rows.append(dict(slot=r['slot'], pages=[r['page_a'], r['page_b']], a=a, b=b, result=measure(a, b)))
    return dict(rows=rows, joint=joint(rows))


def joint(rows: Sequence[dict]) -> dict:
    """The joint value of slot rows: the equal-page mean and the weaker-page minimum of each score, withheld (None)
    unless every slot has two available, complete selections and a finite score.

    Example:
        >>> joint([])['complete']
        False
    """
    complete = bool(rows) and all(r.get('a') and r.get('b') and r['a']['available'] and r['b']['available'] and r['a']['complete'] and r['b']['complete'] for r in rows)
    mean, minimum = {}, {}
    for key in ('dice', 'local_segment_similarity', 'nearby_similarity'):
        values = [(r.get('result') or {}).get(key) for r in rows]
        valid = complete and all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
        mean[key] = sum(values) / len(values) if valid else None
        minimum[key] = min(values) if valid else None
    return dict(complete=complete, mean=mean, minimum=minimum, required_pairs=len(rows), available_pairs=sum(1 for r in rows if r.get('a') and r.get('b') and r['a']['available'] and r['b']['available']))


# ----------------------------------------------------------------------------- the first-line scan and the rankings
def line_features(text: str) -> dict:
    """The unit-pair histograms of a line's transcript for the Jensen-Shannon distances: `toolkit` (within-word
    Zattera pairs, every word weighted equally, as ``measures.Features``), `within` (within-word pairs by count),
    `joined` (the words joined into one sequence, pairs across word boundaries allowed, unit segmentation kept),
    `boundaries` (a boundary unit between the words); `plain` and `spaced` are the atom sequences for the edit
    similarities."""
    words = text.split()
    aa = [atoms(w) for w in words]
    zz = [zattera(w) for w in words]

    def hist(groups, weighted=False):
        h = Counter()
        for seq in groups:
            den = max(1, len(seq) - 1) if weighted else 1
            for i in range(1, len(seq)):
                h[(seq[i - 1], seq[i])] += 1.0 / den
        return h
    spaced = []
    for i, a in enumerate(aa):
        if i:
            spaced.append('<boundary>')
        spaced += a
    flat = [u for z in zz for u in z]
    bounded = []
    for i, z in enumerate(zz):
        if i:
            bounded.append('<boundary>')
        bounded += z
    return dict(words=words, plain=[x for a in aa for x in a], spaced=spaced, toolkit=hist(zz, True), within=hist(zz), joined=hist([flat]), boundaries=hist([bounded]))


def js_distance(a: Counter, b: Counter) -> Optional[float]:
    """The square root of the base-2 Jensen-Shannon divergence between two histograms (None when one is empty).

    Example:
        >>> js_distance(Counter({('a', 'b'): 1}), Counter({('c', 'd'): 1}))
        1.0
    """
    sa, sb = sum(a.values()), sum(b.values())
    if not sa or not sb:
        return None
    d = 0.0
    for k in set(a) | set(b):
        p, q = a.get(k, 0.0) / sa, b.get(k, 0.0) / sb
        m = (p + q) / 2
        if p:
            d += p * math.log2(p / m) / 2
        if q:
            d += q * math.log2(q / m) / 2
    return math.sqrt(max(0.0, d))


def x_overlap_gate(a, b, threshold: float = SPATIAL_GATE) -> bool:
    n = max(0.0, min(a['rect'][2], b['rect'][2]) - max(a['rect'][0], b['rect'][0]))
    return n > 0 and n / min(a['rect'][2] - a['rect'][0], b['rect'][2] - b['rect'][0]) >= threshold


def spatial_similarity(A: Sequence[dict], B: Sequence[dict], threshold: float = SPATIAL_GATE) -> dict:
    """The position-constrained EVA similarity of two unit lists: a Levenshtein alignment of the atom sequences in
    reading order where a match or substitution between two atoms is allowed at cost 0 / 1 only when their parent
    boxes' x intervals overlap by at least `threshold` of the shorter interval, and costs 2 otherwise; insertions
    and deletions cost 1. similarity = max(0, 1 - cost / the longer sequence).

    Returns:
        {similarity, edits, atoms_a, atoms_b} (similarity None when a list is empty).

    Example:
        >>> u = lambda t, lo, hi: dict(atoms=atoms(t), rect=[lo, 0, hi, 10])
        >>> spatial_similarity([u('cho', 0, 10), u('dy', 10, 20)], [u('chody', 0, 20)])['similarity']
        1.0
    """
    a = [(t, k) for k, u in enumerate(A) for t in u['atoms']]
    b = [(t, k) for k, u in enumerate(B) for t in u['atoms']]
    if not a or not b:
        return dict(similarity=None, edits=None, atoms_a=len(a), atoms_b=len(b))
    gate = [[x_overlap_gate(u, v, threshold) for v in B] for u in A]
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        ta, ka = a[i - 1]
        g = gate[ka]
        row = [i]
        for j in range(1, len(b) + 1):
            tb, kb = b[j - 1]
            sub = (0 if ta == tb else 1) if g[kb] else 2
            row.append(min(row[j - 1] + 1, prev[j] + 1, prev[j - 1] + sub))
        prev = row
    edits = prev[len(b)]
    return dict(similarity=max(0.0, 1.0 - edits / max(len(a), len(b))), edits=edits, atoms_a=len(a), atoms_b=len(b))


def _union_length(intervals) -> float:
    total, end = 0.0, -math.inf
    for lo, hi in sorted(intervals):
        total += max(0.0, hi - max(lo, end))
        end = max(end, hi)
    return total


def x_dice(A: Sequence[dict], B: Sequence[dict]) -> Optional[float]:
    """Horizontal-occupancy Dice: 2 x the length of the x intervals shared by A and B over the sum of their union
    lengths (None when both are empty)."""
    a = [(u['rect'][0], u['rect'][2]) for u in A]
    b = [(u['rect'][0], u['rect'][2]) for u in B]
    inter = [(max(x[0], y[0]), min(x[1], y[1])) for x in a for y in b if min(x[1], y[1]) > max(x[0], y[0])]
    den = _union_length(a) + _union_length(b)
    return 2 * _union_length(inter) / den if den else None


def dice2d(A: Sequence[dict], B: Sequence[dict]) -> Optional[float]:
    """Occupied-area Dice of two unit lists (no anchors dropped here; drop them before calling)."""
    den = union_area([u['rect'] for u in A]) + union_area([u['rect'] for u in B])
    if not den:
        return None
    return 2 * union_area([r for u in A for v in B for r in [intersection(u['rect'], v['rect'])] if r]) / den


def _line_selection(data, page, line_index, coordinates='flat', scale='pixels', cutoff=1):
    """A selection anchored on a given line of the page (the scan's per-line anchor): the block holds the lines from
    `line_index` on, `cutoff` of them selected."""
    folio = page['folio']
    saved = page['blocks']
    lines = [l['index'] for l in page['lines'][line_index:]]
    page['blocks'] = [dict(key='scan', label='Scan', lines=lines)] + saved
    try:
        return select(data, folio, 'scan', cutoff, coordinates, 'starts', scale)
    finally:
        page['blocks'] = saved


def first_line_scan(data: dict, cutoff: int = 1, log=None) -> dict:
    """Every page's opening lines against every other page's: the retrieval scan behind ``rank_pairs``.

    A page enters when its opening block's first line is a paragraph line, horizontal, with located rectangles; the
    first `cutoff` lines of the opening are selected with the usual first-box translation (flat coordinates). A page is complete when every token of those lines is located; a pair is eligible when both
    pages are complete and each has at least two scored boxes.

    Returns:
        {cutoff, pages: [meta per scanned page], pairs: [{a, b (indices into pages), spatial, x_dice, edit,
        edit_all, edit_boundaries, js_word, js_pooled, js_joined, js_boundaries, dice_current, dice_recorded,
        spatial_body, eligible}], excluded: [{folio, locus, reasons}], eligible_pairs}.

    Example:
        >>> scan = first_line_scan(data)                      # doctest: +SKIP
        >>> len(scan['pages']), scan['eligible_pairs']        # doctest: +SKIP
        (205, 20100)
    """
    key = ('scan', cutoff)
    if key in data:
        return data[key]
    E, excluded = [], []
    for folio in data['folios']:
        page = data['pages'][folio]
        opening = page['blocks'][0]['lines']
        line = page['lines'][opening[0]] if opening else None
        reasons = []
        if line is None or line['category'] != 'P':
            reasons.append('no paragraph opening')
        if line is None or line['orientation'] != 'horizontal':
            reasons.append('opening not horizontal')
        if line is None or not line['units']:
            reasons.append('first opening has no boxes')
        if reasons:
            excluded.append(dict(folio=folio, locus=line['locus'] if line else None, reasons=reasons))
            continue
        cur = select(data, folio, 'opening', cutoff, 'flat', 'starts', 'pixels')
        rec = select(data, folio, 'opening', cutoff, 'recorded', 'starts', 'pixels')
        body = select(data, folio, 'opening', cutoff, 'flat', 'starts', 'body_height')
        chosen = cur['chosen']
        us = list(chosen)
        text = ' '.join(page['lines'][li]['text'] for li in opening[:cutoff])
        represented = sum(u['token_count'] for u in chosen)
        transcript = sum(page['lines'][li]['token_count'] for li in opening[:cutoff])
        f = line_features(text)
        E.append(dict(meta=dict(folio=folio, locus=line['locus'], line_index=opening[0], section=page['section'], hand=page['hand'], node=page['node'], face=page['face'],
                                slot=page['slot'], text=text, unit_count=len(chosen), scored_units=len(us), atoms=sum(len(u['atoms']) for u in us), full_atoms=len(f['plain']),
                                span=(max(u['rect'][2] for u in chosen) - min(u['rect'][0] for u in chosen)) if chosen else 0.0, located_tokens=represented,
                                transcript_tokens=transcript, complete=represented == transcript and cur['complete'], flagged_units=sum(1 for u in chosen if u['flags']),
                                grouped_units=sum(1 for u in chosen if u['token_count'] > 1), warp_fitted=bool(page['warp']['fitted'])),
                      us=us, rec=list(rec['chosen']), body=list(body['chosen']), features=f))
    pairs = []
    for i in range(len(E)):
        a = E[i]
        for j in range(i + 1, len(E)):
            b = E[j]
            A, B, f, g = a['us'], b['us'], a['features'], b['features']
            pairs.append(dict(a=i, b=j, spatial=spatial_similarity(A, B)['similarity'], x_dice=x_dice(A, B),
                              edit=similarity([x for u in A for x in u['atoms']], [x for u in B for x in u['atoms']]), edit_all=similarity(f['plain'], g['plain']),
                              edit_boundaries=similarity(f['spaced'], g['spaced']), js_word=js_distance(f['toolkit'], g['toolkit']), js_pooled=js_distance(f['within'], g['within']),
                              js_joined=js_distance(f['joined'], g['joined']), js_boundaries=js_distance(f['boundaries'], g['boundaries']),
                              dice_current=dice2d(A, B), dice_recorded=dice2d(a['rec'], b['rec']), spatial_body=spatial_similarity(a['body'], b['body'])['similarity'],
                              eligible=bool(a['meta']['complete'] and b['meta']['complete'] and len(A) >= 2 and len(B) >= 2)))
        if log and i % 40 == 0:
            log('scanned %d / %d pages, %d pairs' % (i + 1, len(E), len(pairs)))
    scan = dict(cutoff=cutoff, pages=[e['meta'] for e in E], pairs=pairs, excluded=excluded, eligible_pairs=sum(1 for r in pairs if r['eligible']),
                policy=dict(selection='the opening block\'s first line must be a paragraph line, horizontal, with located rectangles; no later replacement',
                            coordinates='flat (stored page warp, anchors transported) with the first-box translation; x is unchanged by the warp',
                            primary='position-constrained EVA Levenshtein similarity (spatial): order kept, match or substitution only where the parent x intervals overlap by 20%% of the shorter; insertion, deletion, substitution 1; no spatial match 2',
                            js='sqrt of the base-2 Jensen-Shannon divergence: js_word equal-word within-word Zattera pairs, js_pooled by count, js_joined pairs across boundaries with the segmentation kept, js_boundaries with a boundary unit',
                            eligibility='both pages complete (every token of the selected lines located) and at least two scored boxes each'))
    data[key] = scan
    return scan


def _pair_key(a, b):
    return (a, b) if a <= b else (b, a)


def pair_rows(scan: dict, data: dict, scope: str = 'pages') -> dict:
    """The rows of a scope from a scan: page pairs, or bifolium face pairs (inner, outer, both) whose required slots
    each hold exactly one complete scanned page; a face row averages its page pairs' scores equally and keeps the
    weakest overlap.

    Returns:
        {rows, sheets (bifolia count for a face scope), slots}.
    """
    pages = scan['pages']
    eligible = [r for r in scan['pairs'] if r['eligible']]
    if scope == 'pages':
        rows = [dict(id='p:%s:%s' % (pages[r['a']]['folio'], pages[r['b']]['folio']), unit='pages', a=pages[r['a']]['folio'], b=pages[r['b']]['folio'], pages_a=[pages[r['a']]], pages_b=[pages[r['b']]],
                     parts=[r], **{k: r[k] for k in SCAN_FIELDS}) for r in eligible]
        return dict(rows=rows, sheets=None, slots=None)
    required = FACES.get(scope)
    if required is None:
        raise ValueError("scope must be 'pages', 'inner', 'outer' or 'both'")
    lookup = {_pair_key(r['a'], r['b']): r for r in eligible}
    sheets: Dict[str, Dict[str, List[int]]] = {}
    for i, p in enumerate(pages):
        if not p['complete'] or p['scored_units'] < 2:
            continue
        sheets.setdefault(p['node'], {}).setdefault(p['slot'], []).append(i)
    ok = sorted(((n, s) for n, s in sheets.items() if all(len(s.get(k, [])) == 1 for k in required)), key=lambda ns: _natural(ns[0]))
    rows = []
    for x in range(len(ok)):
        for y in range(x + 1, len(ok)):
            (a, A), (b, B) = ok[x], ok[y]
            parts = [lookup.get(_pair_key(A[s][0], B[s][0])) for s in required]
            if any(r is None for r in parts):
                continue
            row = dict(id='b:%s:%s|%s' % (scope, a, b), unit='bifolia', face=scope, a=a, b=b, pages_a=[pages[A[s][0]] for s in required], pages_b=[pages[B[s][0]] for s in required], parts=parts)
            for k in SCAN_FIELDS:
                vals = [r[k] for r in parts]
                row[k] = sum(vals) / len(vals) if all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals) else None
            row['weakest_overlap'] = min(r['dice_current'] for r in parts) if all(r['dice_current'] is not None for r in parts) else None
            rows.append(row)
    return dict(rows=rows, sheets=len(ok), slots=required)


def _natural(s: str):
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def filter_rows(rows: Sequence[dict], pool: str = 'all', containing: Optional[str] = None) -> List[dict]:
    """Restrict ranking rows to a pool: 'all'; 'herbal_a' (every page Herbal A); 'same' (same section and hand slot
    by slot); 'different' (a slot whose sections differ); 'sheet' (page pairs of one bifolium); `containing` keeps rows
    naming that page or bifolium."""
    out = []
    for r in rows:
        if containing and r['a'] != containing and r['b'] != containing:
            continue
        if pool == 'herbal_a' and not all(p['section'] == 'Herbal A' for p in r['pages_a'] + r['pages_b']):
            continue
        if pool == 'same' and not all(p['section'] == q['section'] and p['hand'] == q['hand'] for p, q in zip(r['pages_a'], r['pages_b'])):
            continue
        if pool == 'different' and not any(p['section'] != q['section'] for p, q in zip(r['pages_a'], r['pages_b'])):
            continue
        if pool == 'sheet' and not (r['unit'] == 'pages' and r['pages_a'][0]['node'] == r['pages_b'][0]['node']):
            continue
        out.append(r)
    return out


def _ranks(rows, key, descending):
    srt = sorted(rows, key=lambda r: ((-r[key] if descending else r[key]), r['id']))
    out, rank, previous = {}, 1, None
    for i, r in enumerate(srt):
        if i and abs(r[key] - previous) > 1e-12:
            rank = i + 1
        out[r['id']] = rank
        previous = r[key]
    return out


def rank_rows(rows: Sequence[dict], metric: str = 'both', js: str = 'js_joined') -> List[dict]:
    """Rank rows by one metric, or by 'both': the worse of the Dice rank (dice_current, descending) and the JS rank
    (`js`, ascending), ties broken by the rank sum, then the id. Ranks are competition ranks (equal values share a
    rank) and are computed within the rows given, so a filtered pool re-ranks.

    Returns:
        the rows with overlap_rank, js_rank, metric_rank, both_worst, both_sum, sorted.
    """
    key = js if metric == 'js' else metric
    needed = ['dice_current', js] if metric == 'both' else [key]
    rows = [r for r in rows if all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) for k in needed)]
    overlap = _ranks(rows, 'dice_current', True)
    jsr = _ranks(rows, js, False)
    metric_ranks = None if metric == 'both' else _ranks(rows, key, not key.startswith('js_'))
    out = []
    for r in rows:
        q = dict(r, overlap_rank=overlap[r['id']], js_rank=jsr[r['id']], metric_rank=metric_ranks[r['id']] if metric_ranks else None)
        q['both_worst'] = max(q['overlap_rank'], q['js_rank'])
        q['both_sum'] = q['overlap_rank'] + q['js_rank']
        out.append(q)
    if metric == 'both':
        out.sort(key=lambda r: (r['both_worst'], r['both_sum'], r['id']))
    else:
        out.sort(key=lambda r: (r['metric_rank'], r['id']))
    return out


def rank_pairs(data: dict, pool: str = 'all', cutoff: int = 1, scope: str = 'pages', metric: str = 'both', containing: Optional[str] = None, log=None) -> dict:
    """The ranked list of page pairs or bifolium face pairs by first-line resemblance.

    Args:
        data: ``prepare`` / ``load``.
        pool: 'all' | 'herbal_a' | 'same' | 'different' | 'sheet' (``filter_rows``).
        cutoff: the top lines of the opening compared (1 reproduces the October 2026 scan).
        scope: 'pages' | 'inner' | 'outer' | 'both' (bifolium faces; 'both' = all four slots).
        metric: 'both' (the combined rank), 'dice_current', 'spatial', 'js' (js_joined), or any field of SCAN_FIELDS.
        containing: keep only pairs that name this page or bifolium.

    Returns:
        a ``Records`` list of the ranked rows (each with the folios, the scores, overlap_rank, js_rank, both_worst,
        both_sum) whose `meta` holds n_rows, pages_scanned, eligible_pages, eligible_pairs, sheets, slots, pool, scope,
        metric, cutoff and a note; ``records.to_csv(path)`` writes it; `records['sheets']` reads the meta. The bifolium scores are
        equal means of the page-pair scores (their JS is not a pooled distance), the joint value of ``joint`` is the
        counterpart for a chosen pair, and the order is a descriptive retrieval order, not a probability.

    Example:
        >>> r = rank_pairs(data)                                   # doctest: +SKIP
        >>> r['n_rows'], r['rows'][0]['a'], r['rows'][0]['b']      # doctest: +SKIP
        (20100, ...)
    """
    scan = first_line_scan(data, cutoff, log)
    built = pair_rows(scan, data, scope)
    rows = rank_rows(filter_rows(built['rows'], pool, containing), metric)
    return Records(rows, dict(n_rows=len(rows), pages_scanned=len(scan['pages']), eligible_pages=sum(1 for p in scan['pages'] if p['complete'] and p['scored_units'] >= 2),
                              eligible_pairs=scan['eligible_pairs'], sheets=built['sheets'], slots=built['slots'], pool=pool, scope=scope, metric=metric, cutoff=cutoff, containing=containing,
                              note='Descriptive retrieval order. The combined rank minimises the worse of the occupied-area Dice rank (flat coordinates) and the joined-line JS rank, '
                                   'then their sum. Bifolium rows average their page pairs equally. Translation-only alignment scores describe resemblance, not copying.'))


def compact_rows(rows: Sequence[dict], top: int = 50) -> List[dict]:
    """The first `top` ranked rows reduced to folios and numbers (for the viewer's lists)."""
    out = []
    for r in rows[:top]:
        c = dict(a=r['a'], b=r['b'], unit=r['unit'], pages_a=[p['folio'] for p in r['pages_a']], pages_b=[p['folio'] for p in r['pages_b']],
                 overlap_rank=r.get('overlap_rank'), js_rank=r.get('js_rank'))
        if r.get('face'):
            c['face'] = r['face']
        for k in SCAN_FIELDS:
            c[k] = None if r[k] is None else round(r[k], 6)
        if 'weakest_overlap' in r:
            c['weakest_overlap'] = None if r['weakest_overlap'] is None else round(r['weakest_overlap'], 6)
        out.append(c)
    return out


# ----------------------------------------------------------------------------- page layout: breaks, paragraph ends, polygons
def paragraph_polygons(rows: Sequence[dict], pitch: float) -> List[dict]:
    """Stepped outer envelopes of runs of consecutive complete horizontal rows: consecutive rows are joined halfway
    across their vertical gap, overlapping row extents are combined into horizontal bands, and a run splits at a
    missing row, a reversed step or a step above 2.5 x `pitch`. The envelope contains the located text with its
    interior gaps; it is not an ink contour.

    Args:
        rows: [{line, locus, position (within the paragraph), rect (the row's bounding rectangle), cy}].
        pitch: the paragraph's median row step.

    Returns:
        [{index, lines, loci, points (the polygon, clockwise from the top left)}].
    """
    runs: List[List[dict]] = []
    for row in rows:
        run = runs[-1] if runs else None
        last = run[-1] if run else None
        dy = row['cy'] - last['cy'] if last else 0.0
        if last and row['position'] == last['position'] + 1 and dy > 0 and dy <= 2.5 * pitch:
            run.append(row)
        else:
            runs.append([row])
    out = []
    for index, run in enumerate(runs):
        boxes = [list(r['rect']) for r in run]
        for i in range(1, len(boxes)):
            if boxes[i][1] > boxes[i - 1][3]:
                join = (boxes[i][1] + boxes[i - 1][3]) / 2
                boxes[i - 1][3] = join
                boxes[i][1] = join
        ys = sorted({v for b in boxes for v in (b[1], b[3])})
        bands = []
        for i in range(1, len(ys)):
            lo, hi = ys[i - 1], ys[i]
            active = [b for b in boxes if b[1] < hi and b[3] > lo]
            if active:
                bands.append([min(b[0] for b in active), lo, max(b[2] for b in active), hi])
        points = [p for b in bands for p in ([b[0], b[1]], [b[0], b[3]])] + [p for b in reversed(bands) for p in ([b[2], b[3]], [b[2], b[1]])]
        if len(points) >= 4:
            out.append(dict(index=index, lines=[r['line'] for r in run], loci=[r['locus'] for r in run], points=points))
    return out


def line_break_markers(data: dict, folio: str) -> List[dict]:
    """The transcript intrusion breaks of a page from ``geometry.line_breaks`` (ZL <-> and <~> between located
    words of a horizontal line, adjacent in the left-to-right order), as unit pairs: [{line (page line index), locus,
    left (unit id), right (unit id), kind ('transcript' | 'geometric' | 'both'), gap (recorded x)}]. Breaks whose
    right word does not lie to the right of the left word are counted under `unlocated`."""
    from .geometry import line_breaks
    page = data['pages'][folio]
    app, ms = data['app'], data['ms']
    key = ('breaks',)
    if key not in data:
        data[key] = line_breaks(app, ms, orientations='horizontal')
    breaks = data[key]
    pages_ms = ms.pages if hasattr(ms, 'pages') else ms['pages']
    p = next(q for q in pages_ms if q['folio'] == folio)
    unit_of = {}
    for u in page['units']:
        for i in range(u['first'], u['last'] + 1):
            unit_of[i] = u['id']
    out = []
    for lid in range(p['start_line'], p['end_line']):
        li = lid - p['start_line']
        for br in breaks[lid]:
            if br['left'] is None or br['right'] is None or not br['transcript']:
                continue
            u, v = page['units'][unit_of[br['left']]], page['units'][unit_of[br['right']]]
            out.append(dict(line=li, locus=page['lines'][li]['locus'], left=u['id'], right=v['id'], kind='both' if br['geometric'] else 'transcript',
                            gap=[u['rect'][2], v['rect'][0]], located=v['rect'][0] > u['rect'][2], adjacent=br['adjacent']))
    return out


def layout(data: dict, folio: str, coordinates: str = 'flat', paragraph_alignment: str = 'page', scale: str = 'pixels') -> dict:
    """A page's paragraph layout features in one frame: the whole page translated by its opening anchor (or every
    paragraph by its own first-word anchor when `paragraph_alignment` is 'starts'), with the intrusion break markers,
    the paragraph start and end spans and the paragraph envelopes (``paragraph_polygons``).

    Returns:
        {folio, available, origin, anchor_kind, features: [{type: 'break' | 'start' | 'end', paragraph, line, locus,
        x1, y1, x2, y2}], boxes: [{rect, line, locus, baseline, paragraph}], paragraphs: [{key, lines, available,
        anchor, shift, polygons, complete_rows, omitted_rows}], stats}.

    Example:
        >>> lay = layout(data, 'f75r'); lay['stats']['paragraphs'], len(lay['features'])   # doctest: +SKIP
    """
    page = data['pages'][folio]
    sel = select(data, folio, 'page', 'all', coordinates, 'page', scale)
    factor = BODY_HEIGHT_PX / (page['H'] or 30.0) if scale == 'body_height' else 1.0
    paragraphs_blocks = [b for b in page['blocks'] if b['key'].startswith('p') and b['key'] != 'page']
    stats = dict(paragraphs=len(paragraphs_blocks), missing_starts=0, missing_ends=0, annotated_breaks=0, unlocated_breaks=0,
                 nonhorizontal_lines=sum(1 for l in page['lines'] if l['orientation'] != 'horizontal'))
    opening = page['blocks'][0]['lines'][0] if page['blocks'][0]['lines'] else None
    anchor = next((u for u in sel['all'] if u['anchor']), None)
    available = sel['available'] and anchor is not None and anchor['line_abs'] == opening
    result = dict(folio=folio, section=page['section'], group=page['group'], available=available, paragraph_alignment=paragraph_alignment, opening_line=opening,
                  warp=page['warp'], origin=sel['origin'], anchor_kind=sel['anchor_kind'], features=[], boxes=[], paragraphs=[], stats=stats, coordinates=coordinates, frame=sel['frame'], warp_state=sel['warp'])
    if not available and paragraph_alignment != 'starts':
        return result
    by_line = defaultdict(list)
    for u in sel['all']:
        by_line[u['line_abs']].append(u)
    para_of = {}
    for b in paragraphs_blocks:
        for li in b['lines']:
            para_of[li] = b['key']
    for marker in line_break_markers(data, folio):
        stats['annotated_breaks'] += 1
        if not marker['located']:
            stats['unlocated_breaks'] += 1
            continue
        u = next(x for x in sel['all'] if x['id'] == marker['left'])
        v = next(x for x in sel['all'] if x['id'] == marker['right'])
        result['features'].append(dict(type='break', paragraph=para_of.get(marker['line']), line=marker['line'], locus=marker['locus'], x1=u['rect'][2], y1=u['baseline'], x2=v['rect'][0], y2=v['baseline'], kind=marker['kind']))
    for line in page['lines']:
        if line['orientation'] != 'horizontal':
            continue
        units = sorted(by_line.get(line['index'], []), key=lambda u: u['first'])
        result['boxes'] += [dict(rect=u['rect'], line=line['index'], locus=line['locus'], baseline=u['baseline'], paragraph=para_of.get(line['index']), id=u['id']) for u in units]
    for b in paragraphs_blocks:
        for kind in ('start', 'end'):
            li = b['lines'][0] if kind == 'start' else b['lines'][-1]
            line = page['lines'][li]
            units = by_line.get(li, [])
            complete = bool(units) and sum(u['token_count'] for u in units) == line['token_count']
            if line['orientation'] != 'horizontal' or not complete:
                stats['missing_starts' if kind == 'start' else 'missing_ends'] += 1
                continue
            left = min(units, key=lambda u: u['rect'][0])
            right = max(units, key=lambda u: u['rect'][2])
            result['features'].append(dict(type=kind, paragraph=b['key'], line=li, locus=line['locus'], x1=left['rect'][0], y1=left['baseline'], x2=right['rect'][2], y2=right['baseline']))
    aligned = paragraph_alignment == 'starts'
    for b in paragraphs_blocks:
        start = next((f for f in result['features'] if f['type'] == 'start' and f['paragraph'] == b['key']), None)
        first = sorted(by_line.get(b['lines'][0], []), key=lambda u: u['first'])
        raw_base = (first[0]['base'] if coordinates == 'recorded' else first[0]['flat_base']) if first else None
        usable = start is not None and raw_base is not None
        shift = [(raw_base[k] - sel['origin'][k]) * factor for k in (0, 1)] if aligned and usable else [0.0, 0.0]
        para = dict(id='%s/%s' % (folio, b['key']), key=b['key'], first_line=b['lines'][0], lines=b['lines'], available=usable if aligned else available, anchor=raw_base if usable else None,
                    shift=shift, polygons=[], complete_rows=0, omitted_rows=0)
        if aligned and not usable:
            para['omitted_rows'] = len(b['lines'])
            result['paragraphs'].append(para)
            continue
        feats = [f for f in result['features'] if f['paragraph'] == b['key']]
        boxes = [x for x in result['boxes'] if x['paragraph'] == b['key']]
        if aligned:
            for f in feats:
                f['x1'] -= shift[0]; f['x2'] -= shift[0]; f['y1'] -= shift[1]; f['y2'] -= shift[1]
            for x in boxes:
                x['rect'] = [x['rect'][0] - shift[0], x['rect'][1] - shift[1], x['rect'][2] - shift[0], x['rect'][3] - shift[1]]
                x['baseline'] -= shift[1]
        rows = []
        for position, li in enumerate(b['lines']):
            line = page['lines'][li]
            units = by_line.get(li, [])
            bs = [x for x in boxes if x['line'] == li]
            if line['orientation'] != 'horizontal' or not bs or sum(u['token_count'] for u in units) != line['token_count']:
                para['omitted_rows'] += 1
                continue
            rect = [min(x['rect'][0] for x in bs), min(x['rect'][1] for x in bs), max(x['rect'][2] for x in bs), max(x['rect'][3] for x in bs)]
            rows.append(dict(line=li, locus=line['locus'], position=position, rect=rect, cy=(rect[1] + rect[3]) / 2))
        steps = [r['cy'] - rows[i]['cy'] for i, r in enumerate(rows[1:]) if r['position'] == rows[i]['position'] + 1 and r['cy'] > rows[i]['cy']]
        pitch = _median(steps, 0.0) or _median([r['rect'][3] - r['rect'][1] for r in rows], 0.0) * 1.5 or BODY_HEIGHT_PX * factor
        para['complete_rows'] = len(rows)
        para['polygons'] = [dict(poly, id='%s/area%d' % (para['id'], i + 1)) for i, poly in enumerate(paragraph_polygons(rows, pitch))]
        result['paragraphs'].append(para)
    if aligned:
        usable = {p['key'] for p in result['paragraphs'] if p['available']}
        result['features'] = [f for f in result['features'] if f['paragraph'] in usable]
        result['boxes'] = [x for x in result['boxes'] if x['paragraph'] in usable]
        result['available'] = bool(usable)
    return result


# ----------------------------------------------------------------------------- the viewer's compact records
def pages_from_viewer(compact: dict, words: Sequence[str]) -> dict:
    """Comparison data rebuilt from the atlas's compact records (viewer/data/compare/pages.json.gz written by
    ``viewer_data.compare_data``) and the atlas bundle's words: the same selections and scores as ``prepare`` gives,
    with the rounding of the file (0.01 px). What the browser computes with viewer/js/compare_math.js is computed here
    on the same numbers.

    Example:
        >>> from vmsspatial.bundle import read_json                                     # doctest: +SKIP
        >>> d = pages_from_viewer(read_json('viewer/data/compare/pages.json.gz'), read_json('viewer/data/manuscript/words.json.gz')['words'])   # doctest: +SKIP
    """
    pages = {}
    for folio, p in compact['pages'].items():
        lines = [dict(index=i, locus=l[0], first=bool(l[1]), category=l[2], orientation=l[3], units=[], text=None, token_count=None) for i, l in enumerate(p['lines'])]
        units = []
        for u in p['units']:
            first, last, line, x0, y0, x1, y1, dy, bx, by, flags = u
            text = ' '.join(words[first:last + 1])
            units.append(dict(id=len(units), first=first, last=last, line=line, text=text, atoms=atoms(text), rect=[x0, y0, x1, y1], flat=[x0, y0 - dy, x1, y1 - dy], base=[bx, by], flat_base=[bx, by - dy],
                              anchor_kind='box centre' if flags & 4 else compact.get('baseline', 'auto'), boundary='intrusion_aligned' if flags & 1 else None, flags=[], clean=bool(flags & 2), token_count=last - first + 1))
            lines[line]['units'].append(units[-1]['id'])
        for l in lines:
            l['text'] = ' '.join(words[units[i]['first']:units[i]['last'] + 1] and units[i]['text'] for i in l['units'])
            l['token_count'] = sum(units[i]['token_count'] for i in l['units'])
        pages[folio] = dict(folio=folio, node=p['node'], section=p['section'], hand=p['hand'], group=p['group'], side=p['side'], leaf=p['leaf'], panel=p['panel'], face=p['face'], slot=p['slot'],
                            quire_num=p['quire_num'], H=p['H'], W=p['W'], lines=lines, units=units, blocks=[dict(key=k, label=k, lines=ls) for k, ls in p['blocks']],
                            warp=dict(fitted=p['warp_fitted']), geometry_kind=p['geometry_kind'], frame=p.get('frame', 'recorded'))
    return dict(pages=pages, folios=list(compact['pages']), recorded_tags=dict(frame='recorded', warp='recorded', source=compact.get('source', 'voynichese'), detected_pages=()),
                flat_tags=dict(frame='recorded', warp='flat', source=compact.get('source', 'voynichese'), detected_pages=()), baseline=compact.get('baseline'), version=compact.get('version'), from_viewer=True)


# ----------------------------------------------------------------------------- orders
def orders(ms) -> Dict[str, dict]:
    """The toolkit's page orders over the manuscript's pages: 'bifolia' (the sheets by first leaf, each sheet's pages
    together, the default), 'folio' (the page sequence: leaf, side, panel), 'path1' (the positional model's working
    order of the bifolia; not an established chronology). Each: {id, label, pages, note}.

    Example:
        >>> orders(ms)['folio']['pages'][:2]           # doctest: +SKIP
        ['f1r', 'f1v']
    """
    from .manuscript import Manuscript, page_key
    pages_ms = ms.pages if hasattr(ms, 'pages') else ms['pages']
    folio = [p['folio'] for p in sorted(pages_ms, key=lambda p: page_key(p['folio'], p))]
    out = {'folio': dict(id='folio', label='Manuscript page order', pages=folio, note='The page sequence, panels included. Not a copying chronology.')}
    for name, label, note in (('bifolia', 'Manuscript by bifolium', "The sheets by first leaf, each sheet's pages together."), ('path1', 'Path 1 (positional model, proposed)', 'A proposed glyph-statistical ordering, not an established chronology.')):
        try:
            m = Manuscript.load(name, pages=getattr(ms, 'page_set', 'all'))
            out[name] = dict(id=name, label=label, pages=[p['folio'] for p in m.pages], note=note)
        except Exception as err:            # a toy manuscript without the resources
            out[name] = dict(id=name, label=label, pages=list(folio), note=note + ' (unavailable: %s)' % err)
    return out


def load_order(path, ms=None, data: Optional[dict] = None) -> dict:
    """An external page order from a JSON file: either a list of folios or {id, label, pages, ties?, note?}. Pages the
    file does not name are appended in folio order (and listed under `appended`); names the manuscript lacks are
    listed under `unknown` and dropped. The study's pooled-stability orders are such files and are not shipped.

    Example:
        >>> load_order('my_order.json', ms)['pages'][:3]     # doctest: +SKIP
    """
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    rec = dict(id=Path(path).stem, label=Path(path).stem, pages=raw) if isinstance(raw, list) else dict(raw)
    if ms is None and data is not None:
        ms = data['ms']
    known = orders(ms)['folio']['pages'] if ms is not None else list(rec['pages'])
    seen = set()
    pages, unknown = [], []
    for f in rec['pages']:
        if f in seen:
            continue
        seen.add(f)
        (pages if f in known else unknown).append(f)
    appended = [f for f in known if f not in seen]
    rec.update(pages=pages + appended, appended=appended, unknown=unknown, external=True)
    rec.setdefault('note', 'An external order; the order inside ties, when the file names them, is a navigation choice, not a claim.')
    return rec


# ----------------------------------------------------------------------------- drift indicator and the inline line split
DRIFT_MIN_UNITS = 4          # a line needs this many located boxes
DRIFT_MIN_SPAN_W = 3.0       # ... spanning this many page median word widths (first to last anchor)
DRIFT_METHOD = ('Whole-page median signed first-to-last baseline chord angle; horizontal paragraph lines with at least 4 located boxes spanning at least '
                '3 median word widths, both endpoints baseline anchors (no box-centre fallback); positive falls to the right; the quarantined pages whose '
                'paragraph lines are not all horizontal are unavailable. No minimum page-line count.')


def _quarantine(data):
    key = ('quarantine',)
    if key not in data:
        try:
            from .orientation import nonhorizontal_pages
            data[key] = set(nonhorizontal_pages(data['app'], data['ms'])) if data.get('app') is not None else set(data.get('quarantine', ()))
        except Exception:
            data[key] = set(data.get('quarantine', ()))
    return data[key]


def page_drift(data: dict, folio: str, coordinates: str = 'recorded') -> dict:
    """The drift indicator of a page: the signed angle of each qualifying horizontal paragraph line (the chord from its
    first to its last baseline anchor) and the page's median, in the recorded state (the pre-correction angle the
    workspace shows as a guide) or the flat state (the same chords after the stored page warp).

    A line qualifies with at least DRIFT_MIN_UNITS located boxes whose anchors span at least DRIFT_MIN_SPAN_W page
    median word widths, both endpoints baseline anchors (a box-centre fallback never contributes). Pages whose
    paragraph lines are not all horizontal (the study's quarantine) are unavailable. Positive angles fall to the right.

    Args:
        data: ``prepare`` / ``load`` (or ``pages_from_viewer``).
        folio: the page.
        coordinates: 'recorded' (pre-correction, the workspace's indicator) or 'flat'.

    Returns:
        {folio, coordinates, angle (median degrees or None), slope, n, lines: [{index, locus, angle, units, span,
        qualifies}] (every horizontal paragraph line with two baseline-anchored boxes; the median uses the qualifying
        ones), dropped: {short, narrow, baseline}, median_word_width, source, method, unavailable (reason or None)}.

    Example:
        >>> page_drift(data, 'f21v')['angle'] < 0          # doctest: +SKIP
        True
    """
    if coordinates not in COORDINATES:
        raise ValueError('coordinates must be one of %r' % (COORDINATES,))
    page = data['pages'][folio]
    base_of = (lambda u: u['base']) if coordinates == 'recorded' else (lambda u: u['flat_base'])
    eligible = [l for l in page['lines'] if l['category'] == 'P' and l['orientation'] == 'horizontal']
    ids = {l['index'] for l in eligible}
    words = [u for u in page['units'] if u['line'] in ids]
    widths = [u['rect'][2] - u['rect'][0] for u in words if u['rect'][2] - u['rect'][0] > 0]
    width = _median(widths, 0.0) if widths else None
    lines, dropped = [], dict(short=0, narrow=0, baseline=0)
    quarantined = folio in _quarantine(data)
    if not quarantined:
        for line in eligible:
            us = sorted((u for u in words if u['line'] == line['index']), key=lambda u: base_of(u)[0])
            anchored = [u for u in us if u['anchor_kind'] != 'box centre']
            rec = dict(index=line['index'], locus=line['locus'], units=len(us), qualifies=False)
            if len(us) < DRIFT_MIN_UNITS:
                dropped['short'] += 1
            first, last = (us[0], us[-1]) if us else (None, None)
            if first is not None and last is not None and len(us) >= 2:
                dx = base_of(last)[0] - base_of(first)[0]
                rec['span'] = dx
                if first['anchor_kind'] != 'box centre' and last['anchor_kind'] != 'box centre' and dx > 0:
                    rec['angle'] = math.degrees(math.atan2(base_of(last)[1] - base_of(first)[1], dx))
            if len(us) >= DRIFT_MIN_UNITS:
                if not (width and rec.get('span', 0) >= DRIFT_MIN_SPAN_W * width):
                    dropped['narrow'] += 1
                elif first['anchor_kind'] == 'box centre' or last['anchor_kind'] == 'box centre' or 'angle' not in rec:
                    dropped['baseline'] += 1
                else:
                    rec['qualifies'] = True
            if 'angle' in rec or len(anchored) >= 2:
                lines.append(rec)
    qualifying = [l['angle'] for l in lines if l['qualifies']]
    angle = _median(qualifying, None) if qualifying else None
    return dict(folio=folio, coordinates=coordinates, angle=angle, slope=None if angle is None else math.tan(math.radians(angle)), n=len(qualifying), lines=lines, dropped=dropped,
                median_word_width=width, source='%s baseline anchors (%s), %s state' % (data.get('baseline', 'auto'), page.get('anchor_methods') or data.get('baseline', 'auto'), coordinates),
                method=DRIFT_METHOD, unavailable='quarantined page (paragraph lines not all horizontal)' if quarantined else (None if qualifying else ('no located rectangles' if not words else 'no qualifying horizontal paragraph lines')))


def drift_guide(drift: dict, gain: float = 1.0, x0: float = 0.0, x1: float = 1000.0):
    """The two endpoints of a page's drift guide through the comparison origin: [[x0, slope*gain*x0], [x1, slope*gain*x1]],
    or None when the page has no angle. `gain` multiplies the vertical slope for display only; the angle itself is
    never amplified. The intercept is illustrative (the guide passes through the origin), not a fitted line."""
    if drift is None or drift.get('angle') is None:
        return None
    s = drift['slope'] * gain
    return [[x0, s * x0], [x1, s * x1]]


def split_lines(a: dict, b: dict, indices: Sequence[int], scale: float = 1.0, limit='all', heading_px: float = 25.0, gap_px: float = 27.0, padding_px: float = 12.0) -> Optional[dict]:
    """Display-only vertical translations that pull one line of selection a and one line of selection b apart into a
    band (a above b), with the earlier and later context moved above and below the band by shared offsets. Box
    sizes, horizontal positions, spacing and within-line slopes are kept; only the vertical translation changes;
    the scores of the original selections are untouched (the result is tagged frame 'display').

    Args:
        a, b: selections in one frame (``select``).
        indices: [line of a, line of b] (indices within the blocks). ``nearest_reading_line`` chooses a partner.
        scale: display pixels per page pixel (the heading, gap and padding are given in display pixels).
        limit: 'all' or the top 5 lines, as the overlay shows them.

    Returns:
        {frame: 'display', selections: [a', b'] (copies with moved rect and baseline), indices, start, end (the band's
        top and bottom in the common frame), row_tops, up, down (the context offsets), ymin, ymax} or None when a line has
        no units or the arguments do not describe two selections.

    Example:
        >>> s = split_lines(a, b, [0, 0]); s['selections'][0]['all'][0]['rect'][0] == a['all'][0]['rect'][0]   # doctest: +SKIP
        True
    """
    if indices is None or len(indices) != 2 or scale <= 0:
        return None
    sels = [a, b]
    shown = lambda s: [u for u in s['all'] if limit == 'all' or u['line'] < 5]
    rows = [[u for u in shown(s) if u['line'] == idx] for s, idx in zip(sels, indices)]
    if any(not r for r in rows):
        return None
    bounds = [(min(u['rect'][1] for u in r), max(u['rect'][3] for u in r)) for r in rows]
    top, bottom = min(bb[0] for bb in bounds), max(bb[1] for bb in bounds)
    heading, gap, padding = heading_px / scale, gap_px / scale, padding_px / scale
    height = (bounds[0][1] - bounds[0][0]) + (bounds[1][1] - bounds[1][0]) + heading + gap + padding
    extra = max(0.0, height - (bottom - top))
    start = top - extra / 2
    row_tops = [start + heading, start + heading + (bounds[0][1] - bounds[0][0]) + gap]
    end = row_tops[1] + (bounds[1][1] - bounds[1][0]) + padding
    above = [u for s, idx in zip(sels, indices) for u in shown(s) if u['line'] < idx]
    below = [u for s, idx in zip(sels, indices) for u in shown(s) if u['line'] > idx]
    up = min(-extra / 2, (start - padding - max(u['rect'][3] for u in above)) if above else 0.0)
    down = max(extra / 2, (end + padding - min(u['rect'][1] for u in below)) if below else 0.0)
    displayed = []
    for k, (s, idx) in enumerate(zip(sels, indices)):
        moved = []
        for u in s['all']:
            dy = (row_tops[k] - bounds[k][0]) if u['line'] == idx else (up if u['line'] < idx else down)
            moved.append(dict(u, rect=[u['rect'][0], u['rect'][1] + dy, u['rect'][2], u['rect'][3] + dy], baseline=u['baseline'] + dy))
        chosen_ids = {u['id'] for u in s['chosen']}
        displayed.append(dict(s, all=moved, chosen=[u for u in moved if u['id'] in chosen_ids], frame=DISPLAY_FRAME, display_of=s['frame']))
    visible = [u for s in displayed for u in shown(s)]
    return dict(frame=DISPLAY_FRAME, warp=a['warp'], selections=displayed, indices=list(indices), start=start, end=end, row_tops=row_tops, up=up, down=down,
                ymin=min(start - padding, min(u['rect'][1] - padding for u in visible)), ymax=max(end + padding, max(u['rect'][3] + padding for u in visible)),
                note='Display-only vertical translations; the measured selections and their scores are unchanged.')


DISPLAY_FRAME = 'display'


# ----------------------------------------------------------------------------- the object API
def describe(obj) -> str:
    """One line saying what a selection, a drift record, a layout or a records list is in (frame, warp state,
    cutoff, alignment, coordinates, data version)."""
    if hasattr(obj, 'describe'):
        return obj.describe()
    if isinstance(obj, dict):
        if 'chosen' in obj and 'block' in obj:
            return ('%s %s: %d of %d lines, cutoff %s, align %s, %s coordinates, %s scale, %s frame, %s warp, anchor %s%s' %
                    (obj['folio'], obj['block']['key'], obj['located'], obj['total_lines'], obj['cutoff'], obj['alignment'], obj['coordinates'], obj['scale'], obj['frame'], obj['warp'],
                     obj['anchor_kind'], '' if obj['complete'] else ' (incomplete)'))
        if 'slope' in obj and 'lines' in obj:
            return '%s drift, %s state: %s over %d qualifying lines (%s)' % (obj['folio'], obj['coordinates'], ('%+.2f deg' % obj['angle']) if obj['angle'] is not None else 'unavailable', obj['n'], obj.get('unavailable') or obj['source'])
        if obj.get('frame') == DISPLAY_FRAME:
            return 'display frame (translations for display, not measured geometry), %s warp' % obj.get('warp')
        if 'pages' in obj and 'folios' in obj:
            return 'comparison data: %d pages, %d units, anchors %s, policy %s, data %s' % (len(obj['pages']), sum(len(p['units']) for p in obj['pages'].values()), obj.get('baseline'), (obj.get('provenance') or {}).get('policy'), _data_version())
    return repr(type(obj))


def _data_version() -> str:
    try:
        from . import paths
        return str(paths.manifest().get('version'))
    except Exception:
        return '?'


class Records(list):
    """A plain list of record dicts with its metadata and small helpers: `meta`, ``to_csv(path)``, ``to_json(path)``,
    ``compact(top)``, ``describe()``. `records['sheets']` reads the metadata, `records['rows']` the list itself, so older
    callers keep working. A ranking has one row per pair (`meta`: n_rows, pool, scope, metric, cutoff, pages_scanned,
    eligible_pages, eligible_pairs, sheets, slots, note). Any other table names its columns in `meta['columns']`
    (``line_stats.line_table``, ``line_stats.word_table``): the rows are then written as they are."""

    def __init__(self, rows=(), meta: Optional[dict] = None):
        super().__init__(rows)
        self.meta = dict(meta or {})

    def __getitem__(self, key):
        if isinstance(key, str):
            return list(self) if key == 'rows' else self.meta[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        return self.meta.get(key, default)

    def compact(self, top: int = 50) -> List[dict]:
        return list(self)[:top] if self.meta.get('columns') else compact_rows(self, top)

    def to_csv(self, path, top: Optional[int] = None):
        """Write the rows (the first `top` when given) as CSV: the table's `columns`, or for a ranking a, b, the pages,
        every score, the ranks."""
        import csv
        columns = self.meta.get('columns')
        rows = self.compact(top if top else len(self))
        keys = list(columns) if columns else ['a', 'b', 'unit', 'face', 'pages_a', 'pages_b'] + list(SCAN_FIELDS) + ['weakest_overlap', 'overlap_rank', 'js_rank']
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            w.writeheader()
            for r in rows:
                w.writerow({k: (' '.join(v) if isinstance(v, list) else v) for k, v in r.items()})
        return path

    def to_json(self, path=None, top: Optional[int] = None):
        out = dict(self.meta, rows=self.compact(top if top else len(self)))
        if path is None:
            return out
        Path(path).write_text(json.dumps(out, indent=1, default=float), encoding='utf-8')
        return path

    def describe(self) -> str:
        m = self.meta
        if m.get('columns'):
            return '%d rows: %s; data %s. %s' % (len(self), m.get('title', 'a table'), _data_version(), m.get('note', ''))
        return ('%d %s pairs ranked by %s in pool %s (cutoff %s lines%s; %d pages scanned, %d eligible pairs; data %s). %s' %
                (len(self), m.get('scope', 'pages'), m.get('metric'), m.get('pool'), m.get('cutoff'), ', %d sheets' % m['sheets'] if m.get('sheets') else '', m.get('pages_scanned', 0), m.get('eligible_pairs', 0), _data_version(), m.get('note', '')))


class PairComparison:
    """Two selections in one frame with their scores: ``Comparison.pages`` returns one.

    Attributes: a, b (the selections), same_row.
    Methods: scores(), segments(kind), lines(), start_words(), overlay_geometry(), split(line_a, line_b=None), drift(),
    plot(ax=None, mode='overlay', labels=True), to_json(path=None), describe()."""

    def __init__(self, data: dict, a: dict, b: dict, same_row: bool = False):
        self.data, self.a, self.b, self.same_row = data, a, b, same_row
        self._scores = None

    def scores(self) -> dict:
        """{dice, local_segment_similarity, nearby_similarity, units_a, units_b} (``measure``)."""
        if self._scores is None:
            self._scores = measure(self.a, self.b, self.same_row)
        return dict(self._scores)

    def segments(self, kind: str = 'connected') -> List[dict]:
        """The word correspondences (``details``): kind 'connected' (default), 'direct', 'nearby' or 'all' (a dict)."""
        d = details(self.a, self.b, self.same_row)
        return d if kind == 'all' else d[kind]

    def lines(self) -> List[dict]:
        """Line i against line i without realignment (``per_line``)."""
        return per_line(self.a, self.b)

    def start_words(self, line: int = 0, count: int = 2) -> List[dict]:
        return start_words(self.a, self.b, line, count)

    def overlay_geometry(self) -> dict:
        """Both pages' boxes in the common frame: {frame, warp, coordinates, alignment, scale, cutoff, origin_a, origin_b,
        a: [{id, text, line, rect, baseline, anchor, selected, first, last}], b: [...]}; tagged like the selections."""
        def rows(s):
            return [dict(id=u['id'], text=u['text'], line=u['line'], line_abs=u['line_abs'], rect=list(u['rect']), baseline=u['baseline'], anchor=u['anchor'], selected=u['selected'], first=u['first'], last=u['last']) for u in s['all']]
        return dict(frame=self.a['frame'], warp=self.a['warp'], source='voynichese', coordinates=self.a['coordinates'], alignment=self.a['alignment'], scale=self.a['scale'], cutoff=self.a['cutoff'],
                    folio_a=self.a['folio'], folio_b=self.b['folio'], block_a=self.a['block']['key'], block_b=self.b['block']['key'], origin_a=self.a['origin'], origin_b=self.b['origin'],
                    W=(self.a['W'] + self.b['W']) / 2, H=(self.a['H'] + self.b['H']) / 2, a=rows(self.a), b=rows(self.b))

    def split(self, line_a: int, line_b: Optional[int] = None, scale: float = 1.0) -> Optional[dict]:
        """The inline line split (``split_lines``): line `line_a` of A against `line_b` of B, the partner chosen by the
        nearest median baseline when None."""
        if line_b is None:
            ra = next((l for l in reading_lines(self.a) if l['index'] == line_a), None)
            partner = nearest_reading_line(reading_lines(self.b), ra['baseline'] if ra else None, line_a)
            line_b = partner['index'] if partner else line_a
        return split_lines(self.a, self.b, [line_a, line_b], scale, self.a['cutoff'] if self.a['cutoff'] != 'all' else 'all')

    def drift(self) -> dict:
        """Both pages' drift indicators in the selections' coordinates (``page_drift``)."""
        return dict(a=page_drift(self.data, self.a['folio'], self.a['coordinates']), b=page_drift(self.data, self.b['folio'], self.b['coordinates']))

    def plot(self, ax=None, mode: str = 'overlay', labels: bool = True, shade: bool = True):
        """The matplotlib overlay (``plot.plot_comparison`` on these selections)."""
        from .plot import plot_pair
        return plot_pair(self, ax=ax, mode=mode, labels=labels, shade=shade)

    def to_json(self, path=None):
        """Settings, scores, per-line table, segments and the overlay geometry as one JSON-ready dict (written to `path`
        when given)."""
        out = dict(settings=dict(a=self.a['folio'], b=self.b['folio'], block_a=self.a['block']['key'], block_b=self.b['block']['key'], cutoff=self.a['cutoff'], coordinates=self.a['coordinates'],
                                 alignment=self.a['alignment'], scale=self.a['scale'], same_row=self.same_row, baseline=self.data.get('baseline'), frame=self.a['frame'], warp=self.a['warp'], data_version=_data_version()),
                   scores=self.scores(), lines=self.lines(), segments=self.segments('all'), geometry=self.overlay_geometry(), drift=self.drift(), description=self.describe())
        if path is None:
            return out
        Path(path).write_text(json.dumps(out, indent=1, default=float), encoding='utf-8')
        return path

    def describe(self) -> str:
        s = self.scores()
        return ('%s %s vs %s %s: cutoff %s, align %s, %s coordinates (%s frame, %s warp), %s scale, anchors %s, %s; Dice %s, direct-overlap EVA %s, nearby EVA %s on %d / %d scored boxes; data %s' %
                (self.a['folio'], self.a['block']['key'], self.b['folio'], self.b['block']['key'], self.a['cutoff'], self.a['alignment'], self.a['coordinates'], self.a['frame'], self.a['warp'], self.a['scale'],
                 self.data.get('baseline'), 'same-row' if self.same_row else 'free overlap', _f(s['dice']), _f(s['local_segment_similarity']), _f(s['nearby_similarity']), s['units_a'], s['units_b'], _data_version()))

    def __repr__(self):
        return 'PairComparison(%s)' % self.describe()


def _f(v):
    return '-' if v is None else '%.3f' % v


class Composite:
    """Several selections drawn in one frame, each translated to its own anchor (``Comparison.composite``)."""

    def __init__(self, data: dict, selections: List[dict]):
        self.data, self.selections = data, selections

    def overlay_geometry(self) -> dict:
        return dict(frame=self.selections[0]['frame'], warp=self.selections[0]['warp'], alignment=self.selections[0]['alignment'], coordinates=self.selections[0]['coordinates'],
                    pages=[dict(folio=s['folio'], block=s['block']['key'], origin=s['origin'], boxes=[dict(id=u['id'], text=u['text'], line=u['line'], rect=list(u['rect']), baseline=u['baseline'], anchor=u['anchor'], selected=u['selected']) for u in s['all']]) for s in self.selections])

    def pairwise(self) -> List[dict]:
        """Every pair's scores."""
        out = []
        for i in range(len(self.selections)):
            for j in range(i + 1, len(self.selections)):
                out.append(dict(a=self.selections[i]['folio'], b=self.selections[j]['folio'], **measure(self.selections[i], self.selections[j])))
        return out

    def plot(self, ax=None, labels: bool = False):
        from .plot import plot_composite
        return plot_composite(self, ax=ax, labels=labels)

    def to_json(self, path=None):
        out = dict(description=self.describe(), geometry=self.overlay_geometry(), pairwise=self.pairwise())
        if path is None:
            return out
        Path(path).write_text(json.dumps(out, indent=1, default=float), encoding='utf-8')
        return path

    def describe(self) -> str:
        s = self.selections[0]
        return 'composite of %d blocks (%s): cutoff %s, align %s, %s coordinates (%s frame, %s warp), anchors %s; data %s' % (
            len(self.selections), ', '.join('%s %s' % (x['folio'], x['block']['key']) for x in self.selections), s['cutoff'], s['alignment'], s['coordinates'], s['frame'], s['warp'], self.data.get('baseline'), _data_version())


class SheetComparison:
    """Two bifolia compared slot by slot on one face (``Comparison.bifolia``): `rows` (slot, pages, pair), `joint`."""

    def __init__(self, data: dict, node_a: str, node_b: str, face: str, rows: List[dict]):
        self.data, self.node_a, self.node_b, self.face = data, node_a, node_b, face
        self.rows = rows
        self.joint = joint(rows)

    def pairs(self) -> List[Optional[PairComparison]]:
        return [PairComparison(self.data, r['a'], r['b']) if r.get('a') and r.get('b') else None for r in self.rows]

    def to_json(self, path=None):
        out = dict(description=self.describe(), rows=[dict(slot=r['slot'], pages=r['pages'], result=r['result']) for r in self.rows], joint=self.joint)
        if path is None:
            return out
        Path(path).write_text(json.dumps(out, indent=1, default=float), encoding='utf-8')
        return path

    def describe(self) -> str:
        j = self.joint
        first = next((r['a'] for r in self.rows if r.get('a')), None)
        return '%s vs %s, %s face (%s): %s; equal-page mean Dice %s, direct-overlap %s, nearby %s; weaker page Dice %s; %s' % (
            self.node_a, self.node_b, self.face, ', '.join('%s %s/%s' % (r['slot'], r['pages'][0], r['pages'][1]) for r in self.rows), describe(first) if first else 'no selection',
            _f(j['mean']['dice']), _f(j['mean']['local_segment_similarity']), _f(j['mean']['nearby_similarity']), _f(j['minimum']['dice']), 'complete' if j['complete'] else 'incomplete: joint withheld')


class Comparison:
    """The comparison toolkit from code, in a few lines:

        c = Comparison()                                    # the manuscript, the sensitivity bundle, 'auto' anchors (~10 s)
        pair = c.pages('f20v', 'f21r', cutoff=3)            # two openings, align 'starts', flat coordinates
        pair.scores(); pair.segments(); pair.lines(); pair.overlay_geometry(); pair.plot(); pair.to_json('pair.json')
        c.bifolia('C:20-21', 'B:10-15', face='inner', cutoff=3).joint
        c.composite(['f30r', 'f37r', 'f16r'], align='page').plot()
        ranked = c.rank(pool='herbal_a'); ranked.to_csv('herbal_a.csv')
        c.drift('f21v'); c.layout('f75r'); c.wheels('fRos')

    Every method takes keyword arguments with the defaults of ``select``; every result has ``describe()``.

    Args:
        ms: a Manuscript (default ``Manuscript.load()``: every page, by bifolium).
        app: a bundle (default ``load_bundle(policy, warp='recorded')``; a flat bundle is accepted).
        baseline: the anchor method ('auto' default; 'glyph' reproduces the October 2026 workspace).
        policy: 'sensitivity' (default) or 'strict' when `app` is None.
        data: prepared comparison data instead (``prepare``).
    """

    def __init__(self, ms=None, app=None, baseline: str = 'auto', policy: str = 'sensitivity', data: Optional[dict] = None, log=None):
        if data is None:
            if app is None:
                from .bundle import load_bundle
                from .manuscript import Manuscript
                ms = ms or Manuscript.load()
                app = load_bundle(policy, pages=ms.page_set, order=ms.order, warp='recorded')
            data = prepare(app, ms, baseline=baseline, log=log)
        self.data = data
        self.ms = data['ms']

    @property
    def folios(self) -> List[str]:
        return list(self.data['folios'])

    def page(self, folio: str) -> dict:
        """The page record (units, lines, blocks, H, W, slot, warp status)."""
        return self.data['pages'][folio]

    def blocks(self, folio: str) -> List[dict]:
        """The blocks of a page: opening, page, p1.., l<i>."""
        return [dict(b) for b in self.data['pages'][folio]['blocks']]

    def select(self, folio: str, block: str = 'opening', cutoff='all', coordinates: str = 'flat', alignment: str = 'starts', scale: str = 'pixels') -> dict:
        return select(self.data, folio, block, cutoff, coordinates, alignment, scale)

    def pages(self, a: str, b: str, cutoff='all', align: str = 'starts', coordinates: str = 'flat', block_a: str = 'opening', block_b: str = 'opening', scale: str = 'pixels',
              same_row: bool = False) -> PairComparison:
        """Two pages' blocks overlaid: ``PairComparison``.

        Args:
            a, b: the pages.
            cutoff: top 1..5 lines of the blocks or 'all'.
            align: 'starts' (block anchors) or 'page' (page opening anchors, later paragraphs keep their positions).
            coordinates: 'flat' or 'recorded'.
            block_a, block_b: 'opening' | 'page' | 'p1'.. | 'l<i>'.
            scale: 'pixels' or 'body_height'.
            same_row: score only units with the same line index.
        """
        return PairComparison(self.data, select(self.data, a, block_a, cutoff, coordinates, align, scale), select(self.data, b, block_b, cutoff, coordinates, align, scale), same_row)

    def paragraphs(self, a: str, pa: int, b: str, pb: int, cutoff='all', align: str = 'starts', coordinates: str = 'flat', scale: str = 'pixels') -> PairComparison:
        """Paragraph `pa` of page a against paragraph `pb` of page b (1-based)."""
        return self.pages(a, b, cutoff, align, coordinates, 'p%d' % pa, 'p%d' % pb, scale)

    def bifolia(self, node_a: str, node_b: str, face: str = 'inner', cutoff=3, align: str = 'starts', coordinates: str = 'flat', scale: str = 'pixels', choices: Optional[dict] = None,
                columns: str = 'both') -> SheetComparison:
        """Two bifolia slot by slot on a face (inner = Av, Br; outer = Bv, Ar; both = all four) with the joint value."""
        res = compare_sheets(self.data, node_a, node_b, face, cutoff, coordinates, align, scale, choices, columns)
        return SheetComparison(self.data, node_a, node_b, face, res['rows'])

    def composite(self, pages: Sequence, align: str = 'page', cutoff='all', coordinates: str = 'flat', scale: str = 'pixels') -> Composite:
        """Several pages (folios, or (folio, block) pairs) in one frame, each translated to its own anchor."""
        sels = []
        for p in pages:
            folio, block = (p, 'page' if align == 'page' else 'opening') if isinstance(p, str) else (p[0], p[1])
            sels.append(select(self.data, folio, block, cutoff, coordinates, align, scale))
        return Composite(self.data, sels)

    def rank(self, pool: str = 'all', cutoff: int = 1, scope: str = 'pages', metric: str = 'both', containing: Optional[str] = None, log=None) -> Records:
        """The ranked pairs (``rank_pairs``): a ``Records`` list with ``to_csv``."""
        return rank_pairs(self.data, pool, cutoff, scope, metric, containing, log)

    def drift(self, folio: str, coordinates: str = 'recorded') -> dict:
        """The page's drift indicator (``page_drift``)."""
        return page_drift(self.data, folio, coordinates)

    def layout(self, folio: str, coordinates: str = 'flat', paragraph_alignment: str = 'page', scale: str = 'pixels') -> dict:
        return layout(self.data, folio, coordinates, paragraph_alignment, scale)

    def wheels(self, pages, labels: bool = False) -> dict:
        """The centred wheels of a page or several pages (``wheels.centered_layout``; frame 'display')."""
        from .wheels import centered_layout
        return centered_layout(self.data['app'], self.ms, pages=[pages] if isinstance(pages, str) else list(pages), labels=labels)

    def catalog(self) -> List[dict]:
        return catalog(self.data)

    def orders(self) -> Dict[str, dict]:
        return orders(self.ms)

    def describe(self) -> str:
        return describe(self.data)

    def __repr__(self):
        return 'Comparison(%s)' % self.describe()
