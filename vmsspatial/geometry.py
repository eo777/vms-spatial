"""Page geometry: line frames from the recorded rectangles, and typesetting of any text into them.

One implementation shared by every synthetic layout in the toolkit (it is the ``page_geometry.py`` of the governed
self-citation study, 27 October 2026, with the study's ``fill_slots``):

* ``oversized_flags``: recorded rectangles wider than 6 or taller than 2.5 times the page's median box are defects of the
  source geometry (unless the bundle carries the alignment review, whose strict mask already excludes them);
* ``vertical_gaps``: drawing gaps that run down the page (a plant stem, a column of a diagram), found as inter-word gaps
  wider than half the page's median word width that overlap on lines at most two apart;
* ``line_frames``: per manuscript line the horizontal extent and the median vertical extent of its rectangles, split into
  text segments at isolated gaps wider than twice the page's median word width and at the vertical gaps;
* ``place_in_slot`` / ``fill_slots`` / ``synthetic_geometry``: words laid left to right at the line's letter size inside
  its segments, following the recorded line's drift and height; words that do not fit carry over to the next slot of the
  page; words left at the end of a page go below the page's lowest line in its widest line's segments;
* ``PageGeometry`` + ``Layout``: the same placement done incrementally, word by word, for a generator that needs to
  know what is in view while it writes (``Layout.pool``).

A *bundle* here is any dict with ``words``, ``lines`` ([{start, end, page, ...}]) and ``geometry`` ([x0, y0, x1, y1] or
None per token); ``ms`` is a ``Manuscript`` (lines with ``chars`` and ``page``, pages with ``start_line``/``end_line``).

Orientation. ``line_frames``, ``line_units`` and ``line_breaks`` take ``orientations='horizontal'`` (a kind, a list of
kinds, or None for every line; ``vmsspatial.orientation``): a line of another orientation (rotated, circular, radial,
label) gets no frame, no units and no breaks, and the returned list carries the count under ``.skipped``
(``Frames``, a list with that attribute). The typesetters therefore leave the words of a rotated line without a box
instead of laying them into a frame that assumes horizontal text.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

import numpy as np

DEFAULTS = dict(left=3.0, depth=8.0, angle=45.0, weight='distance', cap=100)


def _lines(ms):
    return ms.lines if hasattr(ms, 'lines') else ms['lines']


def _pages(ms):
    return ms.pages if hasattr(ms, 'pages') else ms['pages']


class Frames(list):
    """A per-line list that also says which lines were skipped for their orientation (``skipped``: {skipped_lines,
    by_kind}) and which frame / warp state its bundle was in (``frame_tags``, ``vmsspatial.frames.tags``)."""
    skipped = None
    frame_tags = None


def orientation_mask(app, ms, orientations):
    """Per line True when the line may enter a line statistic (``orientation.line_mask``); every line when
    `orientations` is None or 'all'. A bundle without lines (a toy) is all True."""
    if orientations is None or orientations == 'all':
        return [True] * len(app['lines']), None
    from .orientation import line_mask, skipped
    m = line_mask(app, orientations, ms)
    return m, skipped(app, m)


def oversized_flags(app, ms, width_factor=6.0, height_factor=2.5) -> List[bool]:
    """Per token: True when the recorded rectangle is wider than width_factor or taller than height_factor times the
    median box of its page. A reviewed (schema 3) bundle uses its strict mask instead: a tall gallows box is not a defect."""
    if app.get('spatialReview'):
        return [not t['strict'] for t in app['spatialReview']['tokens']]
    flags = [False] * len(app['geometry'])
    for p in _pages(ms):
        idx = [i for l in range(p['start_line'], p['end_line']) for i in range(app['lines'][l]['start'], app['lines'][l]['end']) if app['geometry'][i]]
        if not idx:
            continue
        w = np.median([app['geometry'][i][2] - app['geometry'][i][0] for i in idx])
        h = np.median([app['geometry'][i][3] - app['geometry'][i][1] for i in idx])
        for i in idx:
            g = app['geometry'][i]
            if g[2] - g[0] > width_factor * w or g[3] - g[1] > height_factor * h:
                flags[i] = True
    return flags


def vertical_gaps(app, ms, flags, min_share=0.5, overlap_share=0.3, near=2):
    """{line index: [(x_left, x_right), ...]} of the vertical drawing gaps to split lines at."""
    out = {}
    for p in _pages(ms):
        slots = list(range(p['start_line'], p['end_line']))
        idx = [i for l in slots for i in range(app['lines'][l]['start'], app['lines'][l]['end']) if app['geometry'][i] and not flags[i]]
        if not idx:
            continue
        W = float(np.median([app['geometry'][i][2] - app['geometry'][i][0] for i in idx]))
        cands = []
        for k, l in enumerate(slots):
            boxes = sorted([app['geometry'][i] for i in range(app['lines'][l]['start'], app['lines'][l]['end']) if app['geometry'][i] and not flags[i]], key=lambda b: b[0])
            for a, b in zip(boxes, boxes[1:]):
                if b[0] - a[2] > min_share * W:
                    cands.append((k, float(a[2]), float(b[0])))
        if len(cands) < 2:
            continue
        parent = list(range(len(cands)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                if cands[i][0] == cands[j][0]:
                    continue
                if min(cands[i][2], cands[j][2]) - max(cands[i][1], cands[j][1]) >= overlap_share * W:
                    parent[find(i)] = find(j)
        groups = {}
        for i in range(len(cands)):
            groups.setdefault(find(i), []).append(i)
        for members in groups.values():
            ks = sorted({cands[i][0] for i in members})
            if len(ks) < 2 or min(b - a for a, b in zip(ks, ks[1:])) > near:
                continue
            for i in members:
                k, x0, x1 = cands[i]
                out.setdefault(slots[k], []).append((x0, x1))
    return out


def line_frames(app, ms, orientations='horizontal'):
    """Per line: (x_min, y_top_median, x_max, y_bottom_median, segments [(x0, x1)], centres, tops, bottoms) or None
    (no usable rectangle, or an orientation outside `orientations`; the count is in the result's ``skipped``)."""
    flags = oversized_flags(app, ms)
    keep, skipped = orientation_mask(app, ms, orientations)
    lines, pages = _lines(ms), _pages(ms)
    gap_rule = {}
    for p in pages:
        idx = [i for l in range(p['start_line'], p['end_line']) for i in range(app['lines'][l]['start'], app['lines'][l]['end']) if app['geometry'][i] and not flags[i]]
        gap_rule[p['index']] = 2 * float(np.median([app['geometry'][i][2] - app['geometry'][i][0] for i in idx])) if idx else 120.0
    vgaps = vertical_gaps(app, ms, flags)
    frames = Frames()
    frames.skipped = skipped
    from .frames import tags as _tags
    frames.frame_tags = _tags(app)
    for l, L in enumerate(app['lines']):
        boxes = sorted([app['geometry'][i] for i in range(L['start'], L['end']) if app['geometry'][i] and not flags[i]], key=lambda b: b[0]) if keep[l] else []
        if not boxes:
            frames.append(None)
            continue
        rule = gap_rule[lines[l]['page']]
        cuts = vgaps.get(l, [])
        segments = [[boxes[0][0], boxes[0][2]]]
        for b in boxes[1:]:
            gap = (segments[-1][1], b[0])
            if b[0] - segments[-1][1] > rule or any(abs(gap[0] - x0) < 1e-6 and abs(gap[1] - x1) < 1e-6 for x0, x1 in cuts):
                segments.append([b[0], b[2]])
            else:
                segments[-1][1] = max(segments[-1][1], b[2])
        frames.append((min(b[0] for b in boxes), float(np.median([b[1] for b in boxes])), max(b[2] for b in boxes), float(np.median([b[3] for b in boxes])),
                       [(float(a), float(b)) for a, b in segments],
                       np.array([(b[0] + b[2]) / 2 for b in boxes], float), np.array([b[1] for b in boxes], float), np.array([b[3] for b in boxes], float)))
    return frames


INTRUSION_BOUNDARIES = ('intrusion_aligned', 'intrusion_misaligned')   # the review's `boundary` after a token: <-> and <~>


def line_units(app, ms, flags=None, orientations='horizontal'):
    """Per line, the located rectangles once each, in stream order: [{first, last, box}], where first..last are the
    stream indices of the tokens the rectangle stands for (one token, or the several tokens of a shared box, which the
    bundle repeats for each of them). Tokens without a usable rectangle (``oversized_flags``, the frame's exclusions)
    are left out, and a line outside `orientations` has no units (``skipped`` on the result). A reviewed bundle
    groups by the review's assignment group; a plain one by identical rectangles."""
    flags = oversized_flags(app, ms) if flags is None else flags
    keep, skipped = orientation_mask(app, ms, orientations)
    review = app.get('spatialReview')
    groups = [t.get('group') for t in review['tokens']] if review else None
    out = Frames()
    out.skipped = skipped
    for l, L in enumerate(app['lines']):
        units = []
        for i in (range(L['start'], L['end']) if keep[l] else ()):
            b = app['geometry'][i]
            if not b or flags[i]:
                continue
            key = groups[i] if groups and groups[i] else tuple(b)
            if units and units[-1]['key'] == key:
                units[-1]['last'] = i
            else:
                units.append(dict(key=key, first=i, last=i, box=[float(v) for v in b]))
        out.append([dict(first=u['first'], last=u['last'], box=u['box']) for u in units])
    return out


def line_breaks(app, ms, frames=None, boundaries=None, orientations='horizontal'):
    """Per line, the breaks between its located words: [{left, right, transcript, geometric, gap, adjacent}].

    `left` / `right` are the stream indices of the located words on either side of the break (the last token of a shared
    rectangle on the left, the first on the right; None when no located word stands on that side). `transcript`: the ZL
    boundary after a token between them is a drawing intrusion (<-> or <~>: the review's `boundary` field, or one label
    per token passed as `boundaries`; a bundle without either reports no transcript breaks). `geometric`: the two words
    fall in different text segments of the line's frame (``line_frames``: an isolated gap wider than twice the page's
    median word width, or a vertical gap shared with neighbouring lines). `gap` = (right edge of the left word, left edge
    of the right word) in the page's pixel frame. `adjacent`: the two words are neighbours in the left-to-right order of
    the line's rectangles (False for a transcript break between words recorded out of order, or with a side missing).
    Words without a usable rectangle are passed over: a marker after such a word is attributed to the located words
    around it. Only breaks that are transcript or geometric (or both) are returned, in left-to-right order. Lines
    outside `orientations` report no breaks (``skipped`` on the result)."""
    if frames is None:
        frames = line_frames(app, ms, orientations)
    elif getattr(frames, 'frame_tags', None):
        from .frames import check_same
        check_same(frames.frame_tags, app, 'the line frames and the bundle')      # segments are horizontal extents: a warp mismatch is said, not refused
    units_per_line = line_units(app, ms, orientations=orientations)
    if boundaries is None:
        review = app.get('spatialReview')
        boundaries = [t.get('boundary') for t in review['tokens']] if review else None
    out = Frames()
    out.skipped = getattr(units_per_line, 'skipped', None)
    for l, (L, units) in enumerate(zip(app['lines'], units_per_line)):
        fr = frames[l]
        recs = {}
        if fr is not None and len(units) > 1:
            segs = fr[4]

            def seg_of(b):
                inside = [s for s, (a, c) in enumerate(segs) if a - 1e-6 <= b[0] <= c + 1e-6]
                return inside[0] if inside else min(range(len(segs)), key=lambda s: abs(segs[s][0] - b[0]))
            order = sorted(range(len(units)), key=lambda k: units[k]['box'][0])
            for u, v in zip(order, order[1:]):
                U, V = units[u], units[v]
                recs[(u, v)] = dict(left=U['last'], right=V['first'], transcript=False, geometric=seg_of(U['box']) != seg_of(V['box']),
                                    gap=(U['box'][2], V['box'][0]), adjacent=True)
        if boundaries is not None and units:
            for i in range(L['start'], L['end']):
                if boundaries[i] not in INTRUSION_BOUNDARIES:
                    continue
                lefts = [k for k, U in enumerate(units) if U['last'] <= i]
                rights = [k for k, U in enumerate(units) if U['first'] > i]
                u = lefts[-1] if lefts else None
                v = rights[0] if rights else None
                key = (u, v) if (u, v) in recs else ((v, u) if (v, u) in recs else None)
                if key is not None:
                    recs[key]['transcript'] = True
                else:
                    recs[('t', i)] = dict(left=units[u]['last'] if u is not None else None, right=units[v]['first'] if v is not None else None,
                                          transcript=True, geometric=False,
                                          gap=(units[u]['box'][2], units[v]['box'][0]) if u is not None and v is not None else None, adjacent=False)
        found = [r for r in recs.values() if r['transcript'] or r['geometric']]
        found.sort(key=lambda r: (r['gap'][0] if r['gap'] else float('inf'), r['left'] if r['left'] is not None else -1))
        out.append(found)
    return out


def line_profile(fr):
    xs, tops, bottoms = fr[5], fr[6], fr[7]
    return lambda xc: (float(np.interp(xc, xs, tops)), float(np.interp(xc, xs, bottoms)))


def place_in_slot(ws, fr, cw, yshift=0.0, gap=1.0):
    """Place as many of ws as fit, left to right, inside the line's text segments at character width cw. Returns
    (number placed, boxes). A word longer than every segment is forced into the widest one only when nothing else has
    been placed in the slot."""
    segments = fr[4]
    yfun = line_profile(fr)
    out = []
    idx = 0
    for x0, x1 in segments:
        cap = (x1 - x0) / cw
        pos = 0.0
        while idx < len(ws) and pos + len(ws[idx]) <= cap + 1e-9:
            a = x0 + pos * cw
            b = a + len(ws[idx]) * cw
            top, bottom = yfun((a + b) / 2)
            out.append([a, top + yshift, b, bottom + yshift])
            pos += len(ws[idx]) + gap
            idx += 1
        if idx >= len(ws):
            break
    if idx == 0 and ws:
        x0, x1 = max(segments, key=lambda s: s[1] - s[0])
        a = x0
        b = a + len(ws[0]) * cw
        top, bottom = yfun((a + b) / 2)
        out.append([a, top + yshift, b, bottom + yshift])
        idx = 1
    return idx, out


def fill_slots(ms, frames, slot_words, mode='fixed', cw_page=None, skip=None):
    """Lay words into the manuscript's line slots page by page, within the recorded text segments, with carry-over.
      mode 'fixed': slot_words[l] are the words that belong to slot l; character width = the slot's recorded text width
                    over the manuscript line's characters (the manuscript's letter size on that line).
      mode 'lines': slot_words is a sequence of printed lines; a slot takes the carry if there is one, otherwise the
                    next printed line; character width = the slot's letter size, or cw_page[page index] when given.
    skip: per-slot flags of slots that take nothing (label-like slots); the carry passes over them.
    Returns (words per slot, geometry in that order)."""
    lines, pages = _lines(ms), _pages(ms)
    n = len(lines)
    out_words = [[] for _ in range(n)]
    out_geom = [[] for _ in range(n)]
    supply = iter(slot_words) if mode == 'lines' else None
    for p in pages:
        slots = list(range(p['start_line'], p['end_line']))
        centres = [(frames[l][1] + frames[l][3]) / 2 for l in slots if frames[l] is not None]
        gaps = [b - a for a, b in zip(centres, centres[1:]) if b - a > 0]
        pitch = float(np.median(gaps)) if gaps else 30.0
        carry = []
        last_framed = None
        widest = None
        lowest = None
        for l in slots:
            if skip is not None and skip[l]:
                continue
            fr = frames[l]
            if mode == 'lines':
                words = carry if carry else list(next(supply, []))
            else:
                words = carry + list(slot_words[l])
            carry = []
            if fr is None or not words:
                out_words[l] = words
                out_geom[l] = [None] * len(words)
                continue
            cw = cw_page[p['index']] if mode == 'lines' and cw_page else sum(b - a for a, b in fr[4]) / max(lines[l]['chars'], 1)
            placed, boxes = place_in_slot(words, fr, cw)
            out_words[l] = words[:placed]
            out_geom[l] = boxes
            carry = words[placed:]
            last_framed = l
            width = sum(b - a for a, b in fr[4])
            if widest is None or width > widest[1]:
                widest = (l, width, cw)
            if lowest is None or fr[3] > frames[lowest][3]:
                lowest = l
        k = 0
        while carry and last_framed is not None:
            k += 1
            wl, _, wcw = widest
            shift = frames[lowest][3] - frames[wl][3] + k * pitch
            placed, boxes = place_in_slot(carry, frames[wl], wcw, yshift=shift)
            out_words[last_framed] += carry[:placed]
            out_geom[last_framed] += boxes
            carry = carry[placed:]
        if carry:
            l = slots[-1]
            out_words[l] += carry
            out_geom[l] += [None] * len(carry)
    return out_words, [g for gs in out_geom for g in gs]


def synthetic_geometry(line_words, frames, ms):
    """Boxes for a text given line by line. The per-slot word lists in `line_words` are updated IN PLACE to the
    carried-over assignment, so the caller's line structure matches the geometry."""
    new_words, geom = fill_slots(ms, frames, line_words, 'fixed')
    for l in range(len(line_words)):
        line_words[l][:] = new_words[l]
    return geom


def source_pool(target, cand, word_width, pitch, left=3.0, depth=8.0, angle=45.0, weight='distance', cap=100):
    """The study selector on one target (kept for the incremental Layout; see selector.py for the general form).
    target: (box, line index); cand: dict of arrays x0, y0, x1, y1, line. Returns (indices into cand, weights, available)."""
    (tx0, ty0, tx1, ty1), tline = target
    tx, ty = (tx0 + tx1) / 2, (ty0 + ty1) / 2
    x0, y0, x1, y1, line = cand['x0'], cand['y0'], cand['x1'], cand['y1'], cand['line']
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = cx - tx, ty - cy
    same = line == tline
    ok_same = same & (dx < 0) & (-dx <= left * word_width)
    dist_same = -dx / word_width
    near = np.maximum(0.0, ty - y1)
    far = np.minimum(depth * pitch, ty - y0)
    horizontal = np.maximum(np.maximum(x0 - tx, tx - x1), 0.0)
    tan = np.tan(np.radians(angle))
    ok_other = (~same) & (dy > 0) & (far > 0) & (near <= far) & (horizontal <= far * tan + 1e-8)
    with np.errstate(divide='ignore', invalid='ignore'):
        dist_other = np.hypot(dx, dy) / pitch
        align_other = dy * dy / (dx * dx + dy * dy)
    ok = ok_same | ok_other
    idx = np.flatnonzero(ok)
    if not len(idx):
        return idx, np.zeros(0), 0
    distance = np.where(same[idx], dist_same[idx], dist_other[idx])
    alignment = np.where(same[idx], 1.0, align_other[idx])
    w = np.ones(len(idx)) if weight == 'uniform' else alignment / (1.0 + distance) ** 2
    order = np.lexsort((-idx, distance, -w))
    keep = order[:cap]
    return idx[keep], w[keep], int(len(idx))


class PageGeometry:
    """Frames of every manuscript line, the per-line letter size and the per-page word width and pitch."""

    def __init__(self, ms, app):
        self.ms = ms
        self.app = app
        lines = _lines(ms)
        assert app['words'] == [w for L in lines for w in L['words']], 'the bundle and the transcription disagree'
        assert len(app['lines']) == len(lines)
        self.frames = line_frames(app, ms)
        flags = oversized_flags(app, ms)
        self.cw = [None if fr is None else sum(b - a for a, b in fr[4]) / max(L['chars'], 1) for fr, L in zip(self.frames, lines)]
        self.page_of = [L['page'] for L in lines]
        self.pitch, self.word_width, self.slots = {}, {}, {}
        for p in _pages(ms):
            slots = list(range(p['start_line'], p['end_line']))
            self.slots[p['index']] = slots
            centres = [(self.frames[l][1] + self.frames[l][3]) / 2 for l in slots if self.frames[l] is not None]
            gaps = [b - a for a, b in zip(centres, centres[1:]) if b - a > 0]
            self.pitch[p['index']] = float(np.median(gaps)) if gaps else 30.0
            widths = [app['geometry'][i][2] - app['geometry'][i][0] for l in slots for i in range(app['lines'][l]['start'], app['lines'][l]['end'])
                      if app['geometry'][i] and not flags[i]]
            self.word_width[p['index']] = float(np.median(widths)) if widths else 1.0

    @property
    def n_lines(self):
        return len(self.frames)

    def line_chars(self, line):
        return _lines(self.ms)[line]['chars']


class Layout:
    """Incremental fill_slots: words arrive one at a time with their text line index; every word on a page that has a
    box so far is a candidate source for the next word."""

    def __init__(self, geo: PageGeometry):
        self.g = geo
        self.boxes = {}
        self.words = {}
        self.line_of = {}
        self.page_tokens = defaultdict(list)
        self.cur_line = None
        self.cur_page = None
        self.slot_words, self.slot_pos = [], []
        self.carry_words, self.carry_pos = [], []
        self.last_framed = None
        self.widest = None
        self.lowest = None
        self.last_reason = ''

    def _assign(self, pos, box):
        self.boxes[pos] = box
        if box is not None and self.cur_page is not None:
            self.page_tokens[self.cur_page].append(pos)

    def _place_slot(self):
        fr = self.g.frames[self.cur_line] if self.cur_line < self.g.n_lines else None
        if fr is None:
            for p in self.slot_pos:
                self.boxes[p] = None
            return len(self.slot_pos)
        placed, boxes = place_in_slot(self.slot_words, fr, self.g.cw[self.cur_line])
        for j, p in enumerate(self.slot_pos):
            if j < placed:
                if self.boxes.get(p, None) is None:
                    self._assign(p, boxes[j])
            else:
                self.boxes[p] = None
        return placed

    def _close_slot(self):
        if self.cur_line is None:
            return
        fr = self.g.frames[self.cur_line] if self.cur_line < self.g.n_lines else None
        if fr is None or not self.slot_words:
            self.carry_words, self.carry_pos = [], []
            return
        placed = self._place_slot()
        self.carry_words, self.carry_pos = self.slot_words[placed:], self.slot_pos[placed:]
        self.last_framed = self.cur_line
        width = sum(b - a for a, b in fr[4])
        if self.widest is None or width > self.widest[1]:
            self.widest = (self.cur_line, width, self.g.cw[self.cur_line])
        if self.lowest is None or fr[3] > self.g.frames[self.lowest][3]:
            self.lowest = self.cur_line

    def _close_page(self):
        if self.cur_page is None:
            return
        pitch = self.g.pitch[self.cur_page]
        k = 0
        while self.carry_words and self.last_framed is not None:
            k += 1
            wl, _, wcw = self.widest
            shift = self.g.frames[self.lowest][3] - self.g.frames[wl][3] + k * pitch
            placed, boxes = place_in_slot(self.carry_words, self.g.frames[wl], wcw, yshift=shift)
            for j in range(placed):
                self._assign(self.carry_pos[j], boxes[j])
            self.carry_words, self.carry_pos = self.carry_words[placed:], self.carry_pos[placed:]
        for p in self.carry_pos:
            self.boxes[p] = None
        self.carry_words, self.carry_pos = [], []
        self.last_framed = self.widest = self.lowest = None

    def start_line(self, line):
        self._close_slot()
        page = self.g.page_of[line] if line < self.g.n_lines else None
        if page != self.cur_page:
            self._close_page()
            self.cur_page = page
        self.cur_line = line
        self.slot_words, self.slot_pos = list(self.carry_words), list(self.carry_pos)
        self.carry_words, self.carry_pos = [], []
        if self.slot_words:
            self._place_slot()

    def add(self, pos, word, line):
        if line != self.cur_line:
            self.start_line(line)
        self.words[pos] = word
        self.line_of[pos] = line
        self.slot_words.append(word)
        self.slot_pos.append(pos)
        self._place_slot()

    def finish(self):
        self._close_slot()
        self._close_page()
        self.cur_line = None

    def line_chars_used(self, line):
        return sum(len(w) + 1 for p, w in zip(self.slot_pos, self.slot_words) if self.line_of[p] == line)

    def target_box(self, line, proxy_len):
        """The provisional box of the next word of `line` and the slot it lands in, or None when the page is full."""
        if line != self.cur_line:
            self.start_line(line)
        fr = self.g.frames[line] if line < self.g.n_lines else None
        if fr is None:
            self.last_reason = 'no_frame'
            return None
        words = self.slot_words + ['x' * proxy_len]
        placed, boxes = place_in_slot(words, fr, self.g.cw[line])
        if placed == len(words):
            return boxes[-1], line
        overflow = words[placed:]
        page = self.g.page_of[line]
        for nxt in range(line + 1, self.g.n_lines):
            if self.g.page_of[nxt] != page:
                break
            fr2 = self.g.frames[nxt]
            if fr2 is None:
                continue
            p2, b2 = place_in_slot(overflow, fr2, self.g.cw[nxt])
            if p2 == len(overflow):
                return b2[-1], nxt
            overflow = overflow[p2:]
        self.last_reason = 'page_full'
        return None

    def candidates(self, page):
        pos = self.page_tokens.get(page, [])
        if not pos:
            return None, pos
        b = np.array([self.boxes[p] for p in pos], float)
        return dict(x0=b[:, 0], y0=b[:, 1], x1=b[:, 2], y1=b[:, 3], line=np.array([self.line_of[p] for p in pos])), pos

    def pool(self, line, options=None):
        """Sources in view for the next word of text line `line`: (positions, weights, available, target box)."""
        o = dict(DEFAULTS, **(options or {}))
        self.last_reason = ''
        if line >= self.g.n_lines:
            self.last_reason = 'beyond_manuscript'
            return None
        page = self.g.page_of[line]
        W, pitch = self.g.word_width[page], self.g.pitch[page]
        cw = self.g.cw[line]
        if cw is None:
            self.last_reason = 'no_frame'
            return None
        budget = self.g.line_chars(line) - self.line_chars_used(line)
        proxy = max(1, min(int(round(W / cw)), budget if budget > 0 else 1))
        t = self.target_box(line, proxy)
        if t is None:
            return None
        target, tline = t
        cand, pos = self.candidates(page)
        if cand is None:
            return [], np.zeros(0), 0, target
        idx, w, available = source_pool((target, tline), cand, W, pitch, o['left'], o['depth'], o['angle'], o['weight'], o['cap'])
        return [pos[i] for i in idx], w, available, target

    def geometry_in_order(self, n):
        return [self.boxes.get(i) for i in range(n)]


def label_like_slot(L, max_words=2, max_chars=12):
    """A manuscript line of at most two words and twelve characters: the single words written beside drawings that
    the transcription carries as paragraph text."""
    return len(L['words']) <= max_words and L['chars'] <= max_chars


def page_block(ms, frames, p):
    """Left margin, first line centre, pitch, box height and character width of a page from its line frames."""
    lines = _lines(ms)
    fr = [frames[l] for l in range(p['start_line'], p['end_line']) if frames[l] is not None]
    chars = [lines[l]['chars'] for l in range(p['start_line'], p['end_line']) if frames[l] is not None]
    if not fr:
        return None
    left = float(np.percentile([f[0] for f in fr], 10))
    centres = sorted((f[1] + f[3]) / 2 for f in fr)
    gaps = [b - a for a, b in zip(centres, centres[1:]) if b - a > 0]
    height = float(np.median([f[3] - f[1] for f in fr]))
    pitch = float(np.median(gaps)) if gaps else height * 1.6
    cw = float(np.median([(f[2] - f[0]) / c for f, c in zip(fr, chars) if c > 0]))
    return dict(left=left, top=centres[0], pitch=pitch, height=height, cw=cw)
