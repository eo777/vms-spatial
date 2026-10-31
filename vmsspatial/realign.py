"""Alignment of the ZL tokens to the recorded rectangles, word by word.

The Voynichese Project's XML lists a page's words in its own order, which is not always ZL's reading order: f49v's XML
lists the column of letters first and the paragraph after it, while ZL interleaves letter, line, letter, line, so one
order-preserving stream over a page matches paragraph words to letters. A located count proves nothing here: repeated
and one-letter words match anywhere. This module aligns a page in streams and lets geometry decide what spelling cannot.

1. Keep. Every assignment group of the review that is sound stays (no hard flag, a clean spelling, or reviewed on the
   native image). The XML words of the other groups and the words no group holds are free. A kept word that stands off
   its own line is released with them; it returns at the end when nothing better took its place, and until then only an
   equal or better spelling may take its rectangle.
2. Streams. ZL is split by locus category (paragraph, label, circular, radial), each stream in reading order, and each
   is aligned order-preservingly with the XML words in file order, either way round, by a local alignment on spelling:
   the edit distance on the toolkit's Zattera units over the longer word, one token on up to three rectangles or up to
   three tokens on one rectangle (never across a locus or a drawing intrusion). Other streams' words are skipped at
   small cost and a ring may start anywhere. Runs of at least ``RUN_PAIRS`` pairs are taken best first, each XML word
   once. A run overrides a kept group only over a stretch of ``OVERRIDE`` pairs or with a better spelling.
3. Geometry. Every locus gets a line from its located words: a robust straight line with the direction of its reading,
   or a ring; a long line bows and a drawn ring is no true circle, so both read their level from the nearest located
   words. The rays of the circular pages curl and have no line. A placement must lie on its own line, closer to it than
   to the neighbouring lines, and in reading order along the line's direction; a word of a locus with no line must stand
   beside its located neighbours, and a one- or two-glyph word between the neighbouring located loci of its stream.
   Spelling cannot place repeated and short words: position does. Only a spelling that this token and this rectangle
   alone have on the page is excused the finer tests. Placements that fail are undone.
4. Filling. The free tokens of a line take the free rectangles that pass the geometry, in line order, by spelling,
   then, where the counts agree and the length fits, by position (the transcriptions differ there). The words no line
   reaches are placed when each is the other's only close spelling.
5. Accepting. Placement is decided word by word. Group status, flags and the strict and sensitivity eligibility
   follow the review's own rules (``audit.flags``). A token left without a rectangle gets a reason: ``no_xml_word``,
   ``transcriptions_differ`` or ``position_failed``.

``realign_pages`` returns the new review; ``realign_page`` runs one page; ``check_groups`` lists rectangles held twice.
The XML is an optional input (``raw/positional-data``); the review is the shipped product of this module.
"""
from __future__ import annotations

import collections
import json
import math
import multiprocessing
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import paths
from .audit.flags import (HARD, HIGH_COST, NO_XML_WORD, POSITION_FAILED, PROSE_LOCI, STRICT, TOKEN_FLAGS, TRANSCRIPTIONS_DIFFER, group_flags, line_flags, resolve_compound)
from .orientation import chord, circle_fit
from .units import zattera

VERSION = '2026-10-31'
CLEAN = HIGH_COST             # a spelling distance at or below this is a clean match
LOOSE = 0.6                   # above this a pair is no match at all, even inside a run
STRONG = 0.2                  # a run must start and end on pairs at least this close
SKIP_TOKEN, SKIP_XML = 0.5, 0.25
RUN_SCORE, RUN_PAIRS = 3.0, 3
OVERRIDE = 4                  # pairs in a stretch of a run that may displace kept groups outright
GAP_TOKEN, GAP_XML = 2, 3     # a larger gap ends a run
LINE_TOL = 0.62               # a word's largest distance across its line, in page median heights
ADJACENT = 1.5                # the gap between neighbouring words of a locus without a line, in page size units per token
MIN_RADIUS_H, MIN_ARC_DEG = 2.0, 60.0
TALL = 1.3                    # a box this much taller than wide stands on a line up or down the page
WIDTH_RANGE = (0.4, 2.5)      # a placement without a clean spelling: rectangle length over the word's expected length
GROUPS = ((1, 2, .1), (2, 1, .1), (2, 2, .2), (1, 3, .2), (3, 1, .2))     # tokens, rectangles, penalty
KEPT = ('clean', 'sure')
WORD_RE = re.compile(r'<word index="(\d+)" x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)">([^<]*)</word>')
_UNITS: Dict[str, tuple] = {}
_DIST: Dict[tuple, float] = {}


# ----------------------------------------------------------------------------- inputs
def xml_words(folio: str, path=None, review: Optional[dict] = None) -> List[dict]:
    """The Voynichese XML words of a page: [{index, box [x0, y0, x1, y1], text}] (optional file: the workspace's
    positional-data folder, or the manifest's raw/positional-data entry). `review` names the page's file (f101r is
    f101r1.xml)."""
    stem = Path(review['pages'][folio]['xml']).stem if review and folio in review.get('pages', {}) else folio
    p = Path(path) if path else None
    if p is None:
        p = paths.resolve('raw/positional-data/%s.xml' % stem, required=False)
    if p is None:
        ws = paths.workspace_dir()
        cand = (ws / 'positional-data' / ('%s.xml' % stem)) if ws else None
        p = cand if cand and cand.is_file() else None
    if p is None or not Path(p).is_file():
        raise paths.DataMissing('the Voynichese XML of %s is not available (positional-data/%s.xml)' % (folio, stem))
    out = []
    for m in WORD_RE.finditer(Path(p).read_text(encoding='utf-8')):
        i, x, y, w, h, t = m.groups()
        out.append(dict(index=int(i), box=[int(x), int(y), int(x) + int(w), int(y) + int(h)], text=t))
    return out


def units(text: str) -> tuple:
    """A word's Zattera units with the ligature marks dropped (`{cto}` spells c, t, o)."""
    u = _UNITS.get(text)
    if u is None:
        bare = text.replace('{', '').replace('}', '').replace("'", '')
        try:
            u = tuple(zattera(bare))
        except Exception:
            u = tuple(bare)
        _UNITS[text] = u
    return u


def distance(a: str, b: str) -> float:
    """Edit distance on Zattera units over the longer word. '?' matches any unit, or none, for nothing; a rare glyph
    (`@170;`) that another reader spelled with a common letter costs half a unit."""
    key = (a, b)
    v = _DIST.get(key)
    if v is not None:
        return v
    ua, ub = units(a), units(b)
    n, m = len(ua), len(ub)
    if not n and not m:
        return 0.0
    drop_a = [0.0 if u == '?' else 1.0 for u in ua]
    drop_b = [0.0 if u == '?' else 1.0 for u in ub]
    prev = [0.0] * (m + 1)
    for j in range(1, m + 1):
        prev[j] = prev[j - 1] + drop_b[j - 1]
    for i in range(1, n + 1):
        cur = [prev[0] + drop_a[i - 1]] + [0.0] * m
        ca = ua[i - 1]
        for j in range(1, m + 1):
            cb = ub[j - 1]
            sub = 0.0 if ca == cb or ca == '?' or cb == '?' else 0.5 if ca[0] == '@' or cb[0] == '@' else 1.0
            cur[j] = min(prev[j] + drop_a[i - 1], cur[j - 1] + drop_b[j - 1], prev[j - 1] + sub)
        prev = cur
    v = prev[m] / max(n, m, 1)
    if len(_DIST) < 400000:
        _DIST[key] = v
    return v


def _gain(a: str, b: str, bonus: float = 0.0) -> Tuple[float, float]:
    """The score of pairing two spellings, and their distance."""
    na, nb = len(units(a)), len(units(b))
    n = max(na, nb)
    if abs(na - nb) > LOOSE * n:
        return -0.8, 1.0
    d = distance(a, b)
    if d <= CLEAN:
        return 0.4 * min(n, 5) * (1 - 1.5 * d) + bonus, d
    if d <= LOOSE:
        return -0.2 + bonus, d
    return -0.8, d


# ----------------------------------------------------------------------------- the order-preserving local alignment
def chain(tokens: Sequence[str], words: Sequence[str], join: Sequence[bool], prefer: Optional[set] = None) -> List[dict]:
    """Best local alignment of the tokens with the XML words (Smith-Waterman, the group moves of ``GROUPS``). `join[i]`
    says tokens i and i+1 may share a rectangle; `prefer` holds pairs (i, j) the review already makes. Returns the steps
    [{g, d, t: [token positions], x: [word positions]}] in order."""
    n, m = len(tokens), len(words)
    if not n or not m:
        return []
    S = np.zeros((n + 1, m + 1))
    back = {}
    best = (0.0, 0, 0)
    for i in range(1, n + 1):
        Si, Sp = S[i], S[i - 1]
        ti = tokens[i - 1]
        for j in range(1, m + 1):
            b, how = 0.0, None
            c = Sp[j] - SKIP_TOKEN
            if c > b:
                b, how = c, (1, 0, 0.0, 1.0)
            c = Si[j - 1] - SKIP_XML
            if c > b:
                b, how = c, (0, 1, 0.0, 1.0)
            g, d = _gain(ti, words[j - 1], 0.05 if prefer and (i - 1, j - 1) in prefer else 0.0)
            c = Sp[j - 1] + g
            if c > b:
                b, how = c, (1, 1, g, d)
            for a, e, pen in GROUPS:
                if i >= a and j >= e:
                    if a > 1 and not all(join[i - a + k] for k in range(a - 1)):
                        continue
                    ga = ''.join(tokens[i - a:i]) if a > 1 else ti
                    gb = ''.join(words[j - e:j]) if e > 1 else words[j - 1]
                    ua, ub = len(units(ga)), len(units(gb))
                    if abs(ua - ub) > CLEAN * max(ua, ub):
                        continue
                    g2, d2 = _gain(ga, gb)
                    if d2 <= CLEAN:
                        c = S[i - a, j - e] + g2 - pen
                        if c > b:
                            b, how = c, (a, e, g2 - pen, d2)
            Si[j] = b
            if how:
                back[(i, j)] = how
            if b > best[0]:
                best = (b, i, j)
    steps = []
    _, i, j = best
    while (i, j) in back and S[i, j] > 0:
        a, e, g, d = back[(i, j)]
        if a and e:
            steps.append(dict(g=g, d=d, t=list(range(i - a, i)), x=list(range(j - e, j))))
        i -= a
        j -= e
    steps.reverse()
    return steps


def _segments(steps: List[dict]) -> List[List[dict]]:
    out: List[List[dict]] = []
    for s in steps:
        if out and (s['t'][0] - out[-1][-1]['t'][-1] - 1 > GAP_TOKEN or s['x'][0] - out[-1][-1]['x'][-1] - 1 > GAP_XML):
            out.append([s])
        elif out:
            out[-1].append(s)
        else:
            out.append([s])
    return out


def _trim(seg: List[dict]) -> List[dict]:
    """A run starts and ends on a close pair beside its neighbour."""
    def tight(a, b):
        return b['t'][0] - a['t'][-1] <= 2 and b['x'][0] - a['x'][-1] <= 2
    while len(seg) >= 2 and not (seg[0]['d'] <= STRONG and tight(seg[0], seg[1])):
        seg = seg[1:]
    while len(seg) >= 2 and not (seg[-1]['d'] <= STRONG and tight(seg[-2], seg[-1])):
        seg = seg[:-1]
    return seg


# ----------------------------------------------------------------------------- line models
def _centre(b) -> Tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _union(parts) -> list:
    return [min(p[0] for p in parts), min(p[1] for p in parts), max(p[2] for p in parts), max(p[3] for p in parts)]


def _edge_gap(a, b) -> float:
    return math.hypot(max(a[0] - b[2], b[0] - a[2], 0), max(a[1] - b[3], b[1] - a[3], 0))


class Line:
    """A locus's line: 'straight' (mean m, unit direction u of reading, angle, n inliers, span) or 'ring' (centre c,
    radius r, sense of reading +1 or -1, th0, tol)."""

    along = None
    level = None

    def __init__(self, kind: str, **kw):
        self.kind = kind
        self.__dict__.update(kw)

    def coord(self, c) -> Tuple[float, float]:
        """(along, across) of a point; along grows in reading order, on a ring from the start of the fit."""
        if self.kind == 'straight':
            dx, dy = c[0] - self.m[0], c[1] - self.m[1]
            s, q = dx * self.u[0] + dy * self.u[1], -dx * self.u[1] + dy * self.u[0]
            return s, q - self.level_at(s)
        th = math.atan2(c[1] - self.c[1], c[0] - self.c[0])
        return ((self.sense * (th - self.th0)) % (2 * math.pi)) * self.r, math.hypot(c[0] - self.c[0], c[1] - self.c[1]) - self.radius_at(th)

    def level_at(self, s: float) -> float:
        """A long line bows with the page: its level at a point is the median over the nearest located words."""
        if self.along is None or len(self.along) < 6:
            return 0.0
        step = np.abs(self.along - s)
        near = [k for k in np.argsort(step)[:5] if step[k] > 1e-9][:4]
        return float(np.median(self.level[near]))

    def radius_at(self, th: float) -> float:
        """A drawn ring is no true circle: its radius at an angle is the median over the nearest located words."""
        step = np.abs((self.angles - th + math.pi) % (2 * math.pi) - math.pi)
        near = [k for k in np.argsort(step)[:5] if step[k] > 1e-9][:4]
        return float(np.median(self.rhos[near])) if len(near) >= 2 else self.r

    def angle_at(self, c) -> float:
        """The text direction at a point, degrees clockwise from left to right."""
        if self.kind == 'straight':
            return self.angle
        th = math.degrees(math.atan2(c[1] - self.c[1], c[0] - self.c[0]))
        return th + 90.0 * self.sense


def fit_straight(pts, tol: float) -> Optional[Line]:
    """The line through the most points within `tol`, its direction from the first towards the last."""
    P = np.asarray(pts, float)
    best = None
    for a in range(len(P)):
        for b in range(a + 1, len(P)):
            v = P[b] - P[a]
            L = float(np.hypot(*v))
            if L < 1e-6:
                continue
            u = v / L
            inliers = np.abs((P[:, 0] - P[a, 0]) * -u[1] + (P[:, 1] - P[a, 1]) * u[0]) <= tol
            score = (int(inliers.sum()), L)
            if best is None or score > best[0]:
                best = (score, inliers)
    if best is None:
        return None
    Q = P[best[1]]
    ch = chord(Q, Q[-1] - Q[0])
    if ch is None:
        return None
    u = np.array(ch['direction'])
    if (np.diff(Q, axis=0) @ u).sum() < 0:
        u = -u
    L = Line('straight', m=Q.mean(0), u=u, n=int(best[1].sum()), span=float(ch['span']), angle=math.degrees(math.atan2(u[1], u[0])), own=True)
    if len(P) >= 6:
        # the words a bowed line left outside the straight fit rejoin it by their neighbours' level
        A = P - L.m
        along, across = A @ u, -A[:, 0] * u[1] + A[:, 1] * u[0]
        keep = best[1].copy()
        for _ in range(2):
            L.along, L.level = along[keep], across[keep]
            grown = np.array([abs(across[k] - L.level_at(along[k])) <= tol for k in range(len(P))])
            if (grown == keep).all():
                break
            keep = grown
        L.along, L.level = along[keep], across[keep]
        L.n = int(keep.sum())
    return L


def _circle3(p, q, r) -> Optional[Tuple[float, float, float]]:
    d = 2.0 * (p[0] * (q[1] - r[1]) + q[0] * (r[1] - p[1]) + r[0] * (p[1] - q[1]))
    if abs(d) < 1e-9:
        return None
    a, b, c = p @ p, q @ q, r @ r
    x = (a * (q[1] - r[1]) + b * (r[1] - p[1]) + c * (p[1] - q[1])) / d
    y = (a * (r[0] - q[0]) + b * (p[0] - r[0]) + c * (q[0] - p[0])) / d
    return x, y, math.hypot(p[0] - x, p[1] - y)


def fit_ring(pts, H: float) -> Optional[Line]:
    """A circle through most of the points: the best of many triples first, so that a word placed on another ring cannot
    move it, then least squares on the points it holds. `tol` is the ring's scatter about its local radius, at least
    one height. The sense of reading comes from the median step between consecutive points."""
    P = np.asarray(pts, float)
    n = len(P)
    if n < 4:
        return None
    rng = np.random.default_rng(n)
    triples = np.array([rng.choice(n, 3, replace=False) for _ in range(min(200, 10 * n))])
    best, keep = 0, None
    for a, b, c in triples:
        circ = _circle3(P[a], P[b], P[c])
        if circ is None or not MIN_RADIUS_H * H <= circ[2] <= 2000:
            continue
        inliers = np.abs(np.hypot(P[:, 0] - circ[0], P[:, 1] - circ[1]) - circ[2]) <= max(H, 0.12 * circ[2])
        if int(inliers.sum()) > best:
            best, keep = int(inliers.sum()), inliers
    if keep is None or best < 4:
        return None
    circ = None
    for _ in range(3):
        circ = circle_fit(P[keep])
        if circ is None:
            return None
        new = np.abs(np.hypot(P[:, 0] - circ['cx'], P[:, 1] - circ['cy']) - circ['r']) <= max(H, 0.12 * circ['r'])
        if (new == keep).all() or new.sum() < 4:
            break
        keep = new
    if circ['r'] < MIN_RADIUS_H * H or circ['arc_deg'] < MIN_ARC_DEG:
        return None
    A = P[keep]
    th = np.arctan2(A[:, 1] - circ['cy'], A[:, 0] - circ['cx'])
    step = (np.diff(th) + math.pi) % (2 * math.pi) - math.pi
    sense = 1.0 if np.median(step) >= 0 else -1.0
    ring = Line('ring', c=(circ['cx'], circ['cy']), r=circ['r'], sense=sense, th0=float(th[0]) - sense * 0.5, residual=circ['residual'], tol=H, n=int(keep.sum()), own=True,
                angles=th, rhos=np.hypot(A[:, 0] - circ['cx'], A[:, 1] - circ['cy']))
    ring.tol = max(H, 3.0 * float(np.median([abs(ring.coord(p)[1]) for p in A])))
    return ring


# ----------------------------------------------------------------------------- one page
class Page:
    """The alignment of one page (module docstring). `placed` maps token ids to placements {tokens, xml, how, old};
    `held` maps XML indices to the same records; `how` is clean or sure (a kept group), seed, run, gap, fill, bag or
    position."""

    def __init__(self, folio: str, review: dict, xml: Optional[List[dict]] = None):
        self.folio = folio
        self.info = review['pages'][folio]
        self.tokens = [t for t in review['tokens'] if t['page'] == folio]
        self.by_id = {t['id']: t for t in self.tokens}
        self.xml = xml if xml is not None else xml_words(folio, review=review)
        self.words = {w['index']: w for w in self.xml}
        self.H = float(self.info['median_height'])
        self.W = float(self.info['median_width'])
        self.U = max(self.H, self.W)
        widths = [max(g['box'][2] - g['box'][0], g['box'][3] - g['box'][1]) / max(len(units(g['xml_words'][0])), 1) for g in review['groups'].values()
                  if g['page'] == folio and g['status'] == 'exact' and len(g['parts']) == 1 and g['tokens'] and 'invalid_box' not in g['flags']]
        self.char_w = float(np.median(widths)) if len(widths) >= 8 else max(self.W / 5.0, 1.0)
        self.loci: Dict[str, List[dict]] = collections.OrderedDict()
        for t in self.tokens:
            self.loci.setdefault(t['locus'], []).append(t)
        self.pos = {t['id']: (loc, k) for loc, ts in self.loci.items() for k, t in enumerate(ts)}
        self.locus_order = list(self.loci)
        self.locus_at = {loc: i for i, loc in enumerate(self.locus_order)}
        self.old = {g['id']: g for g in review['groups'].values() if g['page'] == folio}
        self.placed: Dict[str, dict] = {}
        self.held: Dict[int, dict] = {}
        self.sure = set()
        self.released: List[dict] = []
        self.reserved: Dict[int, float] = {}
        self.models: Dict[str, Optional[Line]] = {}
        self._fits: Dict[tuple, Optional[Line]] = {}
        self.run_list: List[dict] = []

    # ---- bookkeeping
    def add(self, ids, xml, how, old=None) -> dict:
        p = dict(tokens=list(ids), xml=list(xml), how=how, old=old)
        for i in ids:
            assert i not in self.placed, i
            self.placed[i] = p
        for x in xml:
            assert x not in self.held, x
            self.held[x] = p
        return p

    def remove(self, p: dict):
        for i in p['tokens']:
            del self.placed[i]
        for x in p['xml']:
            del self.held[x]

    def spelling(self, p: dict) -> float:
        return distance(''.join(self.by_id[i]['text'] for i in p['tokens']), ''.join(self.words[x]['text'] for x in p['xml']))

    def box(self, p: dict) -> list:
        return _union([self.words[x]['box'] for x in p['xml']])

    def cat(self, loc: str) -> str:
        return self.loci[loc][0]['locus_type'][0]

    def located(self, loc: str) -> List[Tuple[int, dict]]:
        out, seen = [], set()
        for k, t in enumerate(self.loci[loc]):
            p = self.placed.get(t['id'])
            if p and id(p) not in seen:
                seen.add(id(p))
                out.append((k, p))
        return out

    def free_tokens(self) -> List[dict]:
        return [t for t in self.tokens if t['id'] not in self.placed]

    def free_words(self) -> List[dict]:
        return [w for w in self.xml if w['index'] not in self.held]

    # ---- step 1: what stays
    def classify(self):
        for g in self.old.values():
            if not g['tokens'] or not g['xml_indices']:
                continue
            f = set(g['flags'])
            if 'alignment_reviewed' in f or g.get('resolved'):
                self.sure |= set(g['tokens']) | set(g['xml_indices'])
                self.add(g['tokens'], g['xml_indices'], 'sure', g['id'])
            elif not (f & HARD) and 'high_alignment_cost' not in f:
                self.add(g['tokens'], g['xml_indices'], 'clean', g['id'])

    def release(self):
        """A kept word off its own line, or far from its located neighbours where there is no line, goes back to the
        pool; ``restore`` returns it if nothing better took its place."""
        self.fit_all()
        released = []
        for loc in self.locus_order:
            for _, p in self.located(loc):
                if p['how'] != 'clean':
                    continue
                if self.stands(loc, p['tokens'], self.box(p)) is False:
                    released.append(p)
        for p in released:
            d = self.spelling(p)
            for x in p['xml']:
                self.reserved[x] = d
            self.remove(p)
        self.released += released

    def restore(self):
        for p in self.released:
            if not any(i in self.placed for i in p['tokens']) and not any(x in self.held for x in p['xml']):
                self.add(p['tokens'], p['xml'], p['how'], p['old'])

    # ---- step 2: unique spellings, then the streams
    def seeds(self):
        free_t, free_x = self.free_tokens(), self.free_words()
        ct = collections.Counter(t['text'] for t in free_t)
        cx = collections.Counter(w['text'] for w in free_x)
        where = {w['text']: w for w in free_x}
        self.fit_all()
        for t in free_t:
            s = t['text']
            if ct[s] == 1 and cx.get(s) == 1 and len(units(s)) >= 3:
                w = where[s]
                if self.stands(t['locus'], [t['id']], w['box'], w['text']) is not False:
                    self.add([t['id']], [w['index']], 'seed')

    def can_join(self, a: dict, b: dict) -> bool:
        return a['locus'] == b['locus'] and not str(a.get('boundary') or '').startswith('intrusion')

    def runs(self):
        streams: Dict[str, List[dict]] = collections.OrderedDict()
        for t in self.tokens:
            if t['id'] not in self.sure:
                streams.setdefault(t['locus_type'][0], []).append(t)
        pool = [w for w in self.xml if w['index'] not in self.sure]
        used_t, used_x, accepted = set(), set(), []
        while True:
            best = None
            for cat, ts in streams.items():
                seq_t = [t for t in ts if t['id'] not in used_t]
                if not seq_t:
                    continue
                join = [self.can_join(a, b) for a, b in zip(seq_t, seq_t[1:])] + [False]
                for rev in (False, True):
                    seq_x = [w for w in pool if w['index'] not in used_x]
                    if not seq_x:
                        continue
                    if rev:
                        seq_x = seq_x[::-1]
                    where = {w['index']: j for j, w in enumerate(seq_x)}
                    prefer = set()
                    for i, t in enumerate(seq_t):
                        p = self.placed.get(t['id'])
                        if p and len(p['tokens']) == 1 and len(p['xml']) == 1 and p['xml'][0] in where:
                            prefer.add((i, where[p['xml'][0]]))
                    steps = chain([t['text'] for t in seq_t], [w['text'] for w in seq_x], join, prefer)
                    for seg in _segments(steps):
                        seg = _trim(seg)
                        score = sum(s['g'] for s in seg)
                        if len(seg) >= RUN_PAIRS and score >= RUN_SCORE and (best is None or score > best[0]):
                            best = (score, cat, rev, seg, seq_t, seq_x)
            if best is None:
                break
            score, cat, rev, seg, seq_t, seq_x = best
            pairs = [q for s in seg for q in self.unpair([seq_t[i]['id'] for i in s['t']], [seq_x[j]['index'] for j in s['x']], s['d'])]
            gaps = []
            for s0, s1 in zip(seg, seg[1:]):
                a, b = seq_t[s0['t'][-1] + 1:s1['t'][0]], seq_x[s0['x'][-1] + 1:s1['x'][0]]
                if len(a) == len(b) and a:
                    gaps.append(([t['id'] for t in a], [w['index'] for w in b]))
            accepted.append(dict(score=score, stream=cat, reversed=rev, pairs=pairs, gaps=gaps))
            for a, b, _ in pairs:
                used_t |= set(a)
                used_x |= set(b)
        self.run_list = accepted
        for run in accepted:
            self.apply_run(run)

    def unpair(self, ids: List[str], xml: List[int], d: float) -> List[tuple]:
        """Two tokens on two rectangles part into two pairs when one of the pairs spells clean."""
        if len(ids) == len(xml) == 2:
            ds = [distance(self.by_id[i]['text'], self.words[x]['text']) for i, x in zip(ids, xml)]
            if min(ds) <= CLEAN:
                return [([i], [x], v) for i, x, v in zip(ids, xml, ds)]
        return [(ids, xml, d)]

    def apply_run(self, run: dict):
        def flush(stretch):
            if not stretch:
                return
            touched = {}
            for a, b, _ in stretch:
                for p in [self.placed[i] for i in a if i in self.placed] + [self.held[x] for x in b if x in self.held]:
                    touched[id(p)] = p
            if touched and len(stretch) < OVERRIDE:
                keep = []
                for a, b, d in stretch:
                    ps = {id(p): p for p in [self.placed[i] for i in a if i in self.placed] + [self.held[x] for x in b if x in self.held]}
                    if not ps:
                        keep.append((a, b, d))
                    elif d + 0.05 < min(self.spelling(p) for p in ps.values()):
                        for p in ps.values():
                            self.remove(p)
                        keep.append((a, b, d))
                stretch = keep
            else:
                for p in touched.values():
                    self.remove(p)
            for a, b, d in stretch:
                if d <= CLEAN or self.width_ok(a, [self.words[x]['box'] for x in b]):
                    self.add(a, b, 'run')
        stretch = []
        for a, b, d in run['pairs']:
            p = self.placed.get(a[0])
            if p and sorted(p['tokens']) == sorted(a) and sorted(p['xml']) == sorted(b):
                flush(stretch)
                stretch = []
            else:
                stretch.append((a, b, d))
        flush(stretch)
        for a, b in run['gaps']:
            if not any(i in self.placed for i in a) and not any(x in self.held for x in b):
                for i, x in zip(a, b):
                    if self.width_ok([i], [self.words[x]['box']]):
                        self.add([i], [x], 'gap')

    # ---- step 3: lines
    def fit(self, loc: str) -> Optional[Line]:
        """A locus's line from its located words. A radial locus has none (the rays of the circular pages curl, so
        adjacency decides there), a circular one a ring or none, a paragraph line a straight line or, rarely, a ring."""
        cat = self.cat(loc)
        items = self.located(loc)
        pts = [_centre(self.box(p)) for _, p in items]
        if len(pts) < 2 or cat == 'R':
            return None
        key = (loc, tuple(pts))
        if key not in self._fits:
            if cat == 'C':
                L = fit_ring(pts, self.H)
            else:
                L = fit_straight(pts, LINE_TOL * self.H)
                if cat == 'P' and len(pts) >= 6:
                    ring = fit_ring(pts, self.H)
                    if ring is not None and L is not None:
                        perp = float(np.std((np.asarray(pts, float) - L.m) @ np.array([-L.u[1], L.u[0]])))
                        if ring.residual < 0.35 * (perp + 1e-9):
                            L = ring
            self._fits[key] = L
        return self._fits[key]

    def fit_all(self):
        self.models = {loc: self.fit(loc) for loc in self.locus_order}
        # a short paragraph line takes the direction of its neighbours through its own located words
        for i, loc in enumerate(self.locus_order):
            if self.cat(loc) != 'P':
                continue
            L = self.models[loc]
            items = self.located(loc)
            if not items or (L is not None and (L.kind != 'straight' or (L.n >= 3 and L.span >= 2 * self.W))):
                continue
            u = self.near_direction(i)
            if u is None or not self.agrees(u, items):
                self.models[loc] = L if L is not None and L.n >= 3 else None      # another block's direction: adjacency decides
                continue
            m = np.mean([_centre(self.box(p)) for _, p in items], axis=0)
            self.models[loc] = Line('straight', m=m, u=u, n=len(items), span=L.span if L is not None else 0.0, angle=math.degrees(math.atan2(u[1], u[0])), own=False)

    def agrees(self, u, items) -> bool:
        """A direction taken from a neighbouring line must suit the located boxes: tall boxes stand on a line up or down
        the page, wide ones on a line across it."""
        boxes = [self.box(p) for _, p in items]
        aspect = float(np.median([(b[3] - b[1]) / max(b[2] - b[0], 1) for b in boxes]))
        return not (aspect > TALL and abs(u[1]) < 0.7) and not (aspect < 1 / TALL and abs(u[1]) > 0.7)

    def near_direction(self, i: int):
        for d in range(1, len(self.locus_order)):
            for j in (i - d, i + d):
                if 0 <= j < len(self.locus_order):
                    L = self.models.get(self.locus_order[j])
                    if L is not None and L.kind == 'straight' and L.own and L.n >= 3 and self.cat(self.locus_order[j]) == 'P':
                        return L.u
        return None

    def on_line(self, loc: str, box) -> Optional[bool]:
        """The rectangle against the locus's line: True, False, or None when there is no line to test against."""
        L = self.models.get(loc)
        cat = self.cat(loc)
        if L is None or (cat == 'L' and L.n < 4):
            return None                                  # a short label need not be straight: adjacency decides
        c = _centre(box)
        q = L.coord(c)[1]
        if L.kind == 'ring':
            if abs(q) > L.tol:
                return False
            for other_loc, other in self.models.items():
                if other is not None and other is not L and other.kind == 'ring' and self.cat(other_loc) == 'C' and math.hypot(other.c[0] - L.c[0], other.c[1] - L.c[1]) <= 2 * self.U:
                    if abs(other.coord(c)[1]) + 0.1 * self.H < abs(q):
                        return False
            return True
        if abs(q) > LINE_TOL * self.H:
            return False
        if cat == 'P':
            i = self.locus_at[loc]
            for j in range(max(0, i - 3), min(len(self.locus_order), i + 4)):
                other = self.models.get(self.locus_order[j])
                if j == i or other is None or other.kind != 'straight' or self.cat(self.locus_order[j]) != 'P' or abs(((other.angle - L.angle + 180) % 360) - 180) > 20:
                    continue
                if abs(other.coord(c)[1]) + 0.1 * self.H < abs(q):
                    return False
        return True

    def one_to_one(self, ids: Sequence[str], text: str) -> bool:
        """A spelling only this token and this rectangle have on the page: nothing can confuse them."""
        word = ''.join(self.by_id[i]['text'] for i in ids)
        if len(units(word)) < 3 or distance(word, text) > STRONG:
            return False
        return sum(distance(word, w['text']) <= STRONG for w in self.xml) == 1 and sum(distance(t['text'], text) <= STRONG for t in self.tokens) == len(ids)

    def stands(self, loc: str, ids: Sequence[str], box, text: Optional[str] = None) -> Optional[bool]:
        """The rectangle's place for these tokens: on their line, or beside their neighbours where there is no line (None:
        nothing to test against). A one-to-one spelling (`text`) needs only to be near its line or beside a neighbour."""
        r = self.on_line(loc, box)
        if r is None:
            r = self.adjacent(loc, ids, box)
        if r is False and text is not None and self.one_to_one(ids, text):
            L = self.models.get(loc)
            near = L is not None and abs(L.coord(_centre(box))[1]) <= 2.5 * LINE_TOL * self.H
            r = near or bool(self.adjacent(loc, ids, box))
        return r

    def order_ok(self, loc: str, ids: Sequence[str], box) -> bool:
        """The rectangle stands in reading order among the located words of its line."""
        L = self.models.get(loc)
        if L is None:
            return True
        ka, kb = self.pos[ids[0]][1], self.pos[ids[-1]][1]
        s = L.coord(_centre(box))[0]
        if L.kind == 'ring':
            before = after = None
            for _, p in self.located(loc):
                if p['tokens'][0] in ids:
                    continue
                k = self.pos[p['tokens'][0]][1]
                sp = L.coord(_centre(self.box(p)))[0]
                if k < ka:
                    before = sp
                elif k > kb and after is None:
                    after = sp
            if before is None or after is None:
                return True
            turn = 2 * math.pi * L.r
            return (s - before) % turn <= (after - before) % turn + 0.25 * self.W
        slack = 0.25 * self.W
        for _, p in self.located(loc):
            if p['tokens'][0] in ids:
                continue
            sp = L.coord(_centre(self.box(p)))[0]
            if self.pos[p['tokens'][-1]][1] < ka and s < sp - slack:
                return False
            if self.pos[p['tokens'][0]][1] > kb and s > sp + slack:
                return False
        return True

    def neighbours(self, loc: str, k0: int, k1: int) -> Tuple[Optional[dict], Optional[dict]]:
        left = right = None
        for _, p in self.located(loc):
            if self.pos[p['tokens'][-1]][1] < k0:
                left = p
            elif self.pos[p['tokens'][0]][1] > k1 and right is None:
                right = p
        return left, right

    def adjacent(self, loc: str, ids: Sequence[str], box) -> Optional[bool]:
        """A word of a locus without a line stands beside its located neighbours (None: it has none)."""
        k0, k1 = self.pos[ids[0]][1], self.pos[ids[-1]][1]
        left, right = self.neighbours(loc, k0, k1)
        ok = None
        for p, n in ((left, None if left is None else k0 - self.pos[left['tokens'][-1]][1]), (right, None if right is None else self.pos[right['tokens'][0]][1] - k1)):
            if p is not None:
                ok = (ok is not False) and _edge_gap(self.box(p), box) <= ADJACENT * self.U * n
        return ok

    def between(self, t: dict, box) -> bool:
        """Within the rectangle spanned by the neighbouring located loci of the same stream."""
        i, cat = self.locus_at[t['locus']], t['locus_type'][0]
        spans = []
        for rng in (range(i - 1, -1, -1), range(i + 1, len(self.locus_order))):
            for j in rng:
                loc = self.locus_order[j]
                if self.cat(loc) == cat and self.located(loc):
                    spans.append(_union([self.box(p) for _, p in self.located(loc)]))
                    break
        if not spans:
            return False
        b = _union(spans)
        m = 1.5 * self.U
        c = _centre(box)
        return b[0] - m <= c[0] <= b[2] + m and b[1] - m <= c[1] <= b[3] + m

    def prune(self):
        """Every new placement against its line."""
        for _ in range(2):
            self.fit_all()
            bad = []
            for loc in self.locus_order:
                for _, p in self.located(loc):
                    if p['how'] in KEPT:
                        continue
                    box = self.box(p)
                    r = self.stands(loc, p['tokens'], box, ''.join(self.words[x]['text'] for x in p['xml']))
                    if r is None and len(p['tokens']) == 1 and len(units(self.by_id[p['tokens'][0]]['text'])) <= 2:
                        r = self.between(self.by_id[p['tokens'][0]], box)
                    if r is False or not self.order_ok(loc, p['tokens'], box):
                        bad.append(p)
            for p in bad:
                self.remove(p)

    # ---- step 4: filling the gaps
    def stretches(self, loc: str) -> List[List[int]]:
        out, cur = [], []
        for k, t in enumerate(self.loci[loc]):
            if t['id'] in self.placed:
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(k)
        if cur:
            out.append(cur)
        return out

    def candidates(self, loc: str, ids: Sequence[str]) -> List[dict]:
        """The free rectangles that pass the geometry for a stretch of tokens, in line order."""
        L = self.models.get(loc)
        out = []
        for w in self.free_words():
            if (self.stands(loc, ids, w['box']) or any(self.stands(loc, [i], w['box'], w['text']) for i in ids)) and self.order_ok(loc, ids, w['box']):
                out.append(w)
        if L is not None:
            out.sort(key=lambda w: L.coord(_centre(w['box']))[0])
        else:
            left, right = self.neighbours(loc, self.pos[ids[0]][1], self.pos[ids[-1]][1])
            if left is not None:
                out.sort(key=lambda w: _edge_gap(self.box(left), w['box']))
            elif right is not None:
                out.sort(key=lambda w: -_edge_gap(self.box(right), w['box']))
        return out

    def width_ok(self, ids: Sequence[str], parts) -> bool:
        n = sum(len(units(self.by_id[i]['text'])) for i in ids)
        along = sum(max(b[2] - b[0], b[3] - b[1]) for b in parts)
        return WIDTH_RANGE[0] <= along / ((n + 0.5) * self.char_w) <= WIDTH_RANGE[1]

    def local(self, ts: List[dict], ws: List[dict]) -> List[Tuple[List[int], List[int]]]:
        """Global alignment of a stretch of tokens with the candidate rectangles in line order; rectangles are skipped
        at no cost, a token left over costs 0.8."""
        T = [t['text'] for t in ts]
        X = [w['text'] for w in ws]
        join = [self.can_join(a, b) for a, b in zip(ts, ts[1:])] + [False]
        n, m = len(T), len(X)
        inf = 1e9
        D = np.full((n + 1, m + 1), inf)
        D[0, :] = 0
        back = {}
        for i in range(n + 1):
            for j in range(m + 1):
                b = D[i, j]
                if b >= inf:
                    continue
                if i < n and b + 0.8 < D[i + 1, j]:
                    D[i + 1, j] = b + 0.8
                    back[(i + 1, j)] = (1, 0)
                if j < m and b < D[i, j + 1]:
                    D[i, j + 1] = b
                    back[(i, j + 1)] = (0, 1)
                if i < n and j < m:
                    for a, e in ((1, 1), (1, 2), (2, 1), (2, 2), (1, 3), (3, 1)):
                        if i + a > n or j + e > m or (a > 1 and not all(join[i + q] for q in range(a - 1))):
                            continue
                        d = distance(''.join(T[i:i + a]), ''.join(X[j:j + e]))
                        c = b + d * max(a, e) + 0.05 * (a + e - 2)
                        if d <= CLEAN and c < D[i + a, j + e]:
                            D[i + a, j + e] = c
                            back[(i + a, j + e)] = (a, e)
        j = int(np.argmin(D[n]))
        i = n
        steps = []
        while (i, j) in back:
            a, e = back[(i, j)]
            if a and e:
                steps.append((list(range(i - a, i)), list(range(j - e, j))))
            i -= a
            j -= e
        steps.reverse()
        return steps

    def takes(self, ids: Sequence[str], xml: Sequence[int]) -> bool:
        """A released word's rectangle goes only to a spelling at least as good as the one it held."""
        d = distance(''.join(self.by_id[i]['text'] for i in ids), ''.join(self.words[x]['text'] for x in xml))
        return all(d <= self.reserved.get(x, 1.0) for x in xml)

    def fill(self, position: bool = False) -> int:
        changed = 0
        self.fit_all()
        for loc in self.locus_order:
            for stretch in self.stretches(loc):
                ts = [self.loci[loc][k] for k in stretch]
                ids = [t['id'] for t in ts]
                if self.models.get(loc) is None and not self.located(loc):
                    continue
                ws = self.candidates(loc, ids)
                if not ws:
                    continue
                done = set()
                for a, e in self.local(ts, ws):
                    for tid, xml, _ in self.unpair([ts[i]['id'] for i in a], [ws[j]['index'] for j in e], 0.0):
                        if self.takes(tid, xml):
                            self.add(tid, xml, 'fill')
                            done |= {k for k, t in enumerate(ts) if t['id'] in tid}
                            changed += 1
                if done:
                    self.fit_all()
                if position:
                    rest = [t for i, t in enumerate(ts) if i not in done]
                    wrest = [w for w in ws if w['index'] not in self.held and w['index'] not in self.reserved]
                    if rest and len(rest) == len(wrest):
                        for t, w in zip(rest, wrest):
                            if self.width_ok([t['id']], [w['box']]):
                                self.add([t['id']], [w['index']], 'position')
                                changed += 1
                    elif len(rest) == 1 and 2 <= len(wrest) <= 3 and self.width_ok([rest[0]['id']], [w['box'] for w in wrest]):
                        self.add([rest[0]['id']], [w['index'] for w in wrest], 'position')
                        changed += 1
        return changed

    def bag(self, limit: float = CLEAN) -> int:
        """The words no line reaches: a free token of a locus without a line takes a free word when each is the other's
        only close spelling; a short word must also stand between the neighbouring loci of its stream, and a word
        beyond a clean spelling too."""
        changed = 0
        for _ in range(4):
            self.fit_all()
            free_x = self.free_words()
            pairs: Dict[str, list] = {}
            for t in self.free_tokens():
                if self.models.get(t['locus']) is None:
                    for w in free_x:
                        d = distance(t['text'], w['text'])
                        if d <= limit:
                            pairs.setdefault(t['id'], []).append((d, w['index']))
            of_word: Dict[int, list] = {}
            for tid, c in pairs.items():
                c.sort()
                for d, x in c:
                    of_word.setdefault(x, []).append((d, tid))
            n = 0
            for tid, c in pairs.items():
                t = self.by_id[tid]
                d, x = c[0]
                other = sorted(of_word[x])
                if (len(c) > 1 and c[1][0] <= d + 0.1) or (len(other) > 1 and other[1][0] <= d + 0.1) or other[0][1] != tid or x in self.held:
                    continue
                short = len(units(t['text'])) <= 2 or d > CLEAN
                if (short and not self.between(t, self.words[x]['box'])) or (d > CLEAN and not self.width_ok([tid], [self.words[x]['box']])):
                    continue
                self.add([tid], [x], 'bag')
                n += 1
            changed += n
            if not n:
                break
        return changed

    def run_all(self) -> 'Page':
        self.classify()
        self.release()
        self.seeds()
        self.runs()
        self.prune()
        self.fill()
        self.bag()
        self.release()
        self.fill()
        self.fill(position=True)
        self.bag(LOOSE)
        self.restore()
        self.fill(position=True)
        self.fit_all()
        return self

    # ---- step 5: why a token has no rectangle, and the result
    def reason(self, t: dict) -> str:
        free = self.free_words()
        if any(distance(t['text'], w['text']) <= CLEAN for w in free):
            return POSITION_FAILED
        L = self.models.get(t['locus'])
        for w in free:
            r = self.on_line(t['locus'], w['box'])
            if r or (L is None and self.between(t, w['box'])):
                return TRANSCRIPTIONS_DIFFER
        return NO_XML_WORD

    def angle_of(self, p: dict) -> float:
        """The reading direction at a placement, degrees clockwise from left to right: its line's, or where the locus
        has no line the direction of its own pieces."""
        L = self.models.get(self.by_id[p['tokens'][0]]['locus'])
        if L is not None:
            return round(L.angle_at(_centre(self.box(p))), 1)
        if len(p['xml']) > 1:
            a, b = _centre(self.words[p['xml'][0]]['box']), _centre(self.words[p['xml'][-1]]['box'])
            return round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), 1)
        return 0.0

    def result(self) -> dict:
        seen, placements = set(), []
        same = {(tuple(sorted(g['tokens'])), tuple(sorted(g['xml_indices']))): g['id'] for g in self.old.values() if 'disconnected_parts' not in g['flags']}
        for p in self.placed.values():
            if id(p) not in seen:
                seen.add(id(p))
                how, old = p['how'], p['old']
                key = (tuple(sorted(p['tokens'])), tuple(sorted(p['xml'])))
                if how not in KEPT and key in same:          # placed anew where the review already had it
                    how, old = 'clean', same[key]
                placements.append(dict(tokens=p['tokens'], xml=p['xml'], how=how, old=old, angle=self.angle_of(p), distance=round(self.spelling(p), 3)))
        return dict(folio=self.folio, placements=placements, unlocated={t['id']: self.reason(t) for t in self.free_tokens()})


def realign_page(folio: str, review: dict, xml: Optional[List[dict]] = None) -> dict:
    """One page's placements: {folio, placements: [{tokens, xml, how, old, angle, distance}], unlocated: {token: reason}}."""
    return Page(folio, review, xml).run_all().result()


# ----------------------------------------------------------------------------- writing it into the review
def apply_page(review: dict, result: dict) -> dict:
    """The page's groups and tokens replaced by the result's, in place: kept groups keep their id and record, new groups
    follow the review's rules (``audit.flags``), every XML word stays held by exactly one group. Returns the review."""
    folio = result['folio']
    info = review['pages'][folio]
    old = {k: g for k, g in review['groups'].items() if g['page'] == folio}
    source = {}
    for g in old.values():
        for k, i in enumerate(g['xml_indices']):
            source[i] = (g['parts'][k], g['display_parts'][k] if g.get('display_parts') else None, g['xml_words'][k])
    tokens = [t for t in review['tokens'] if t['page'] == folio]
    by_id = {t['id']: t for t in tokens}
    counts = collections.Counter(tuple(v[0]) for v in source.values())
    new_groups: Dict[str, dict] = {}
    token_group: Dict[str, str] = {}
    angles: Dict[str, float] = {}
    n = 0
    for p in result['placements']:
        ids = p['tokens']
        if p['how'] in KEPT and p['old'] in old:
            g = old[p['old']]
            key = g['id']
            new_groups[key] = g
        else:
            n += 1
            key = 'r-%s-%d' % (folio, n)
            parts = [source[i][0] for i in p['xml']]
            texts = [source[i][2] for i in p['xml']]
            g = dict(id=key, page=folio, tokens=list(ids), xml_indices=list(p['xml']), xml_words=texts, parts=parts, box=_union(parts),
                     status='', flags=[], display_parts=[source[i][1] for i in p['xml']] if all(source[i][1] for i in p['xml']) else [])
            g['flags'] = sorted(group_flags(g, [by_id[i] for i in ids], info, counts, p['distance'], p['angle']) | {'alignment_corrected'})
            g['status'] = ('many_to_many' if len(ids) > 1 and len(p['xml']) > 1 else 'xml_merged' if len(ids) > 1 else 'xml_split' if len(p['xml']) > 1 else
                           'exact' if by_id[ids[0]]['text'] == texts[0] else 'variant' if p['distance'] <= HIGH_COST else 'substitution')
            resolve_compound(g, by_id[ids[0]]['text'], info, p['angle'])
            new_groups[key] = g
        angles[key] = p['angle']
        for i in ids:
            token_group[i] = key
    for t in tokens:
        if t['id'] not in token_group:
            n += 1
            key = 'r-%s-%d' % (folio, n)
            new_groups[key] = dict(id=key, page=folio, tokens=[t['id']], xml_indices=[], xml_words=[], parts=[], box=None, status='canonical_unmatched', flags=['missing_box'], display_parts=[])
            token_group[t['id']] = key
    held = {i for g in new_groups.values() for i in g['xml_indices']}
    for i in sorted(set(source) - held):
        n += 1
        key = 'r-%s-%d' % (folio, n)
        new_groups[key] = dict(id=key, page=folio, tokens=[], xml_indices=[i], xml_words=[source[i][2]], parts=[source[i][0]], box=list(source[i][0]), status='xml_unmatched',
                               flags=['xml_only'], display_parts=[source[i][1]] if source[i][1] else [])
    for k in old:
        del review['groups'][k]
    review['groups'].update(new_groups)
    # the line diagnostics of every group of the page, along each line's direction
    located = [g for g in new_groups.values() if g['tokens'] and g['box']]
    for g in located:
        g['flags'] = sorted(set(g['flags']) - {'line_outlier', 'order_reversal'})
    place = {t['id']: k for k, t in enumerate(tokens)}
    lines: Dict[str, List[dict]] = collections.defaultdict(list)
    for g in located:
        first = by_id[g['tokens'][0]]
        if len({by_id[i]['locus'] for i in g['tokens']}) == 1 and first['locus_type'] in PROSE_LOCI and not set(g['flags']) & {'invalid_box', 'disconnected_parts'}:
            lines[first['locus']].append(g)
    for line in lines.values():
        line.sort(key=lambda g: place[g['tokens'][0]])
        line_flags(line, angles, info)
    # the tokens
    for t in tokens:
        key = token_group[t['id']]
        g = new_groups[key]
        res = next((r for r in g.get('resolved', []) if r['token'] == t['id']), None)
        keep = [f for f in t['flags'] if f in TOKEN_FLAGS and not (f in ('exact_compound_union', 'image_reviewed_boundary') and res is None)]
        if key != t['group']:
            for f in ('resolved_box', 'display_box', 'resolution_method'):
                t.pop(f, None)
            if res is not None:
                t.update(resolved_box=res['box'], display_box=res['display_box'], resolution_method=res['method'])
                keep.append(res['method'])
        t['group'] = key
        reason = result['unlocated'].get(t['id'])
        t['flags'] = sorted(set(g['flags']) | set(keep) | ({reason} if reason else set()))
        flags = set(t['flags'])
        t['strict'] = bool(g['box']) and (res is not None or not flags & STRICT)
        t['sensitivity'] = bool(g['box']) and (res is not None or not flags & HARD)
    return review


def recompute_metrics(review: dict) -> dict:
    tokens = review['tokens']
    groups = review['groups']
    tf = collections.Counter(f for t in tokens for f in t['flags'])
    gf = collections.Counter(f for g in groups.values() for f in g['flags'])
    m = dict(review.get('metrics') or {})
    m.update(canonical_tokens=len(tokens), canonical_pages=len({t['page'] for t in tokens}), coordinate_pages=len({g['page'] for g in groups.values()}),
             alignment_groups=len(groups), strict_eligible=sum(1 for t in tokens if t['strict']), sensitivity_eligible=sum(1 for t in tokens if t['sensitivity']),
             tokens_with_flags=dict(tf), groups_with_flags=dict(gf), statuses=dict(collections.Counter(g['status'] for g in groups.values())))
    review['metrics'] = m
    return m


def check_groups(review: dict) -> List[str]:
    """Rectangles held twice: every XML word of a page belongs to one group, and tokens share a rectangle only inside a
    group flagged `shared_box`. Returns the offences."""
    out = []
    seen: Dict[tuple, str] = {}
    for g in review['groups'].values():
        for i in g['xml_indices']:
            k = (g['page'], i)
            if k in seen:
                out.append('%s: XML word %d held by %s and %s' % (g['page'], i, seen[k], g['id']))
            seen[k] = g['id']
        if len(g['tokens']) > 1 and 'shared_box' not in g['flags']:
            out.append('%s: group %s shares a box without the flag' % (g['page'], g['id']))
    return out


# ----------------------------------------------------------------------------- all pages
_WORKER_REVIEW: Optional[dict] = None


def _init_worker(review_path):
    global _WORKER_REVIEW
    from .audit.review import load_review
    _WORKER_REVIEW = load_review(review_path)


def _work(args) -> Tuple[str, Optional[dict]]:
    folio, checkpoint = args
    res = realign_page(folio, _WORKER_REVIEW)
    if checkpoint:
        tmp = Path(checkpoint) / (folio + '.tmp')
        tmp.write_text(json.dumps(res), encoding='utf-8')
        tmp.replace(Path(checkpoint) / (folio + '.json'))
    return folio, res


def realign_pages(folios: Optional[Sequence[str]] = None, review_path=None, workers: int = 1, checkpoint=None, log=print) -> Tuple[dict, Dict[str, dict]]:
    """Align the given pages (default every page with rectangles) and write them into a copy of the review (new version,
    metrics). `workers` processes share the pages; with `checkpoint` (a folder) every page's result is saved as it
    finishes and a rerun skips the pages already there, so a crash costs one page. Returns (new review, {folio: result})."""
    from .audit.review import load_review
    review = load_review(review_path)
    folios = list(folios or review['pages'])
    results: Dict[str, dict] = {}
    if checkpoint:
        Path(checkpoint).mkdir(parents=True, exist_ok=True)
        for f in folios:
            p = Path(checkpoint) / (f + '.json')
            if p.is_file():
                results[f] = json.loads(p.read_text(encoding='utf-8'))
    todo = [f for f in folios if f not in results]
    if workers > 1 and todo:
        with multiprocessing.Pool(workers, initializer=_init_worker, initargs=(review_path,)) as pool:
            for k, (f, res) in enumerate(pool.imap_unordered(_work, [(f, checkpoint) for f in todo], chunksize=1)):
                results[f] = res
                if log and k % 25 == 24:
                    log('%d of %d pages' % (k + 1, len(todo)))
    else:
        global _WORKER_REVIEW
        _WORKER_REVIEW = review
        for f in todo:
            results[f] = _work((f, checkpoint))[1]
    for f in folios:
        apply_page(review, results[f])
    review['version'] = VERSION
    review['policies'] = dict(strict_exclusions=sorted(STRICT), sensitivity_exclusions=sorted(HARD))
    review.pop('realignment', None)
    recompute_metrics(review)
    return review, results
