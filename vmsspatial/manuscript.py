"""The manuscript text and its physical structure.

Text: by default (``Manuscript.load()``) every page and every locus of the ZL transliteration that the toolkit can
place: the 227 pages, paragraph text, labels, circular and radial text, 5,365 lines and 38,876 tokens (uncertain
readings omitted), each line with its ZL locus type, read in the manuscript by bifolium. ``pages='paragraph'``
restricts the text to the study transcription (``manuscript/tokens.json``: the paragraph text of 207 pages, 4,130
lines, 34,977 tokens), and ``order='path1'`` reads the bifolia in the Path 1 order of the positional composition
model (``resources/path1_order.json``); ``Manuscript.load(pages='paragraph', order='path1')`` is what the October
2026 studies used. Physical structure: ``manuscript/physical_map.csv``
(quire, leaf, side, bifolium, partner leaf, section letter, Currier language, hand). No EVA parsing happens here: words
are the transcription's token strings.

Orders. The stream is a list of pages. ``order='bifolia'`` (the default) is the manuscript by sheet: the sheets by
their first leaf, each sheet's pages together (f1r, f1v, f8r, f8v, f2r, ...). ``order='folio'`` is the true page
sequence, panels included (f1r, f1v, f2r, f2v, ...), so a sheet's pages lie apart. ``order='path1'`` keeps sheets
together in the study's working order (not an established chronology). The token stream, and with it every window
measure, follows the chosen order. A bifolium (a node) is a label on pages and lines, not a stretch of the stream:
``bifolium_ranges`` gives a sheet's token ranges in any order, and sheet statistics gather its words by label.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from . import paths

# Golf 2.1 group -> the traditional section its pages belong to (share of the group's tokens).
GROUP_SECTION = {'1a': 'Herbal A', '1b': 'Herbal A', '1.5a': 'Herbal A', '2a': 'Pharma, Astro', '5a': 'Cosmo', '6': 'Stars',
                 '3b': 'Herbal B', '3a': 'Herbal B', '3c': 'Stars', '4c': 'Stars', '4a': 'Bio'}
GROUP_ORDER = ['1a', '1b', '1.5a', '2a', '5a', '6', '3b', '3a', '3c', '4c', '4a']
SECTION_NAMES = {'H': 'Herbal', 'S': 'Stars', 'P': 'Pharma', 'B': 'Bio', 'C': 'Cosmological', 'A': 'Astronomical', 'Z': 'Zodiac', 'T': 'Text'}
ORDERS = ('bifolia', 'folio', 'path1')
PAGE_SETS = ('all', 'paragraph')
DEFAULT_ORDER = 'bifolia'
DEFAULT_PAGES = 'all'
STUDY = dict(pages='paragraph', order='path1')      # the shape of the October 2026 studies: Manuscript.load(**STUDY)


def page_set(pages=DEFAULT_PAGES, extra=None) -> str:
    """Normalise the `pages` argument ('all' | 'paragraph'). `extra` is the deprecated older spelling (True = 'all',
    False = 'paragraph') and overrides `pages` when given."""
    if extra is not None:
        import warnings
        warnings.warn("extra= is deprecated; use pages='all' (extra=True) or pages='paragraph' (extra=False)", DeprecationWarning, stacklevel=3)
        pages = 'all' if extra else 'paragraph'
    if pages is None:
        pages = DEFAULT_PAGES
    if pages not in PAGE_SETS:
        raise ValueError('pages must be one of %r' % (PAGE_SETS,))
    return pages


def group_label(g, sep='\n'):
    """'3c' -> '3c\\nStars': the Golf code with the traditional section name of its pages."""
    return g + sep + GROUP_SECTION[g] if g in GROUP_SECTION else g


def group_labels(groups, sep='\n'):
    """Tick labels: the code on every tick, the section name under the first group of each stretch of one section."""
    out, prev = [], None
    for g in groups:
        name = GROUP_SECTION.get(g)
        out.append(g + sep + name.replace(', ', sep) if name and name != prev else g)
        prev = name
    return out


def load_tokens(path=None) -> dict:
    p = path or paths.resolve('manuscript/tokens.json')
    return json.loads(p.read_text(encoding='utf-8'))


def load_physical(path=None) -> Dict[str, dict]:
    """folio -> physical record; a flat bifolium's inner face = A verso | B recto, outer face = B verso | A recto."""
    p = path or paths.resolve('manuscript/physical_map.csv')
    rows = {}
    with open(p, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            leaf, partner = int(r['leaf']), int(r['partner_leaf'])
            a, b = min(leaf, partner), max(leaf, partner)
            side = r['side']
            face = 'inner' if (leaf == a and side == 'v') or (leaf == b and side == 'r') else 'outer'
            rows[r['folio']] = dict(leaf=leaf, side=side, panel=r['panel'], quire=r['quire'], quire_num=int(r['quire_num']),
                                    bifolium=r['bifolium'], bif_pos=int(r['bif_pos']), partner=partner, A=a, B=b, face=face,
                                    section=r['section'], currier=r['currier'], hand=r['hand'],
                                    section_name=SECTION_NAMES.get(r['section'], r['section']) + (' ' + r['currier'] if r['section'] in ('H', 'S') and r['currier'] in ('A', 'B') else ''))
    return rows


def load_order(name='path1') -> List[dict]:
    """The 50 bifolia as nodes [{id, group, N, pages}]: in Path 1 order, or by first leaf (`bifolia`, `folio`)."""
    base = json.loads(paths.resource('path1_order.json').read_text(encoding='utf-8'))['nodes']
    if name == 'path1':
        return [dict(n) for n in base]
    if name not in ORDERS:
        raise ValueError('order must be one of %r' % (ORDERS,))
    phys = load_physical()
    return [dict(n) for n in sorted(base, key=lambda n: _sheet_key(n, phys))]


def _sheet_key(n, phys):
    return (min(phys[q]['leaf'] for q in n['pages']), phys[n['pages'][0]]['quire_num'])


def page_key(folio: str, phys: dict) -> tuple:
    """A page's place in the true page sequence: leaf, side, panel (the Rosettes foldout after f85)."""
    return (phys['leaf'] if folio != 'fRos' else 85.5, phys['side'], phys.get('panel', ''))


@dataclass
class Manuscript:
    """pages: [{index, folio, node, group, order_in_node, start_line, end_line, + physical}]; lines: [{folio, locus, words,
    first (paragraph start), final (last line of its page), chars, node, group, page, locus_type (the ZL locus type:
    P0, P1, Pb ... paragraph text, L* labels, Cc / Ca circular, Ri / Ro radial)}]; nodes: the bifolia in order;
    page_set: 'all' | 'paragraph'."""
    nodes: List[dict]
    pages: List[dict]
    lines: List[dict]
    order: str = DEFAULT_ORDER
    physical: Dict[str, dict] = field(default_factory=dict, repr=False)
    extra: bool = True          # True when page_set is 'all' (older name)
    page_set: str = DEFAULT_PAGES

    @classmethod
    def load(cls, order=DEFAULT_ORDER, tokens=None, physical=None, pages='all', extra=None) -> 'Manuscript':
        """The default is the whole recorded manuscript: all 227 pages and all loci (paragraph text, labels,
        circular and radial text; the 20 circular and astronomical pages and the Rosettes join the node of their
        bifolium or a new node, group '—'), by bifolium, every line with its ZL locus type. `order='folio'` is the page
        sequence, `order='path1'` the study's order (``STUDY``); `pages='paragraph'` gives the study transcription only
        (207 pages). `extra` is the deprecated older spelling of `pages` (True = 'all', False = 'paragraph')."""
        if order is None:
            order = DEFAULT_ORDER
        pages_kind = page_set(pages, extra)
        extra = pages_kind == 'all'
        tok = tokens or load_tokens()
        phys = dict(physical or load_physical())
        by = defaultdict(list)
        for line in tok['lines']:
            by[line['folio']].append(line)
        nodes = load_order(order)
        if extra:
            # extra=True (or 'all', the older spelling): the pages absent from the study set, and every page's
            # non-paragraph loci (labels, circular and radial text), the Rosettes' included: everything the Voynichese
            # Project recorded, plus fRos
            from .extra import extra_page_names, extra_lines, extra_physical
            names = extra_page_names(set(by))
            phys.update(extra_physical(names, phys))
            targets = set(names) | set(by)
            for line in extra_lines(sorted(targets)):
                if line['locus'] not in {L['locus'] for L in by[line['folio']]}:
                    by[line['folio']].append(line)
            for p in targets:
                by[p].sort(key=lambda L: int(L['locus']) if str(L['locus']).isdigit() else 10 ** 6)
            for n in nodes:
                n['N'] = sum(len(L['words']) for p in n['pages'] for L in by[p])
            by_id = {n['id']: n for n in nodes}
            for p in names:
                bif = phys[p]['bifolium']
                if bif not in by_id:
                    by_id[bif] = dict(id=bif, group='—', N=0, pages=[])
                    nodes.append(by_id[bif])
                node = by_id[bif]
                # after the last page of the same or an earlier leaf (recto before verso), else at the end
                key = (phys[p]['leaf'], phys[p]['side'])
                at = max([k + 1 for k, f in enumerate(node['pages']) if (phys[f]['leaf'], phys[f]['side']) <= key] or [len(node['pages'])])
                node['pages'].insert(at, p)
                node['N'] += sum(len(L['words']) for L in by[p])
            if order != 'path1':
                nodes.sort(key=lambda n: _sheet_key(n, phys))
        from .extra import locus_types
        types = locus_types()
        sequence = [(p, node, k) for node in nodes for k, p in enumerate(node['pages'])]
        if order == 'folio':
            sequence.sort(key=lambda s: page_key(s[0], phys[s[0]]))
        pages, lines = [], []
        for p, node, k in sequence:
            start_line = len(lines)
            for i, line in enumerate(by[p]):
                lines.append(dict(folio=p, locus=str(line['locus']), words=list(line['words']), first=bool(line['first']),
                                  final=i == len(by[p]) - 1, chars=len(' '.join(line['words'])), node=node['id'],
                                  group=node['group'], page=len(pages),
                                  locus_type=line.get('locus_type') or types.get(p, {}).get(str(line['locus']))))
            pages.append(dict(index=len(pages), folio=p, node=node['id'], group=node['group'], order_in_node=k,
                              start_line=start_line, end_line=len(lines), **phys[p]))
        ms = cls(nodes=nodes, pages=pages, lines=lines, order=order, physical=phys, extra=bool(extra), page_set=pages_kind)
        assert sum(len(L['words']) for L in ms.lines) == sum(n['N'] for n in nodes), 'token count differs from the order resource'
        return ms

    # ---- lookups
    @property
    def n_tokens(self) -> int:
        return sum(len(L['words']) for L in self.lines)

    def line_words(self) -> List[List[str]]:
        return [list(L['words']) for L in self.lines]

    def words(self) -> List[str]:
        return [w for L in self.lines for w in L['words']]

    def page(self, folio: str) -> dict:
        for p in self.pages:
            if p['folio'] == folio:
                return p
        raise KeyError(folio)

    def node(self, node_id: str) -> dict:
        for n in self.nodes:
            if n['id'] == node_id:
                return n
        raise KeyError(node_id)

    def page_sizes(self) -> List[int]:
        return [sum(len(self.lines[l]['words']) for l in range(p['start_line'], p['end_line'])) for p in self.pages]

    def page_of_line(self) -> np.ndarray:
        return np.array([L['page'] for L in self.lines])

    def paragraph_of_line(self) -> np.ndarray:
        return np.cumsum([bool(L['first']) for L in self.lines])

    def node_of_line(self) -> np.ndarray:
        return np.array([L['node'] for L in self.lines], dtype=object)

    def section_of_page(self, index: int) -> str:
        return self.pages[index]['section_name']

    def lines_of_page(self, index: int) -> range:
        p = self.pages[index]
        return range(p['start_line'], p['end_line'])

    def bifolium_ranges(self, line_words=None) -> Dict[str, List[tuple]]:
        """node id -> the sheet's token ranges [(first, end), ...] in the stream of `line_words` (default: the
        manuscript's): one range in a sheet order, several when its pages lie apart."""
        lw = line_words or [L['words'] for L in self.lines]
        out: Dict[str, List[tuple]] = {}
        at = 0
        for L, ws in zip(self.lines, lw):
            ranges = out.setdefault(L['node'], [])
            if ranges and ranges[-1][1] == at:
                ranges[-1] = (ranges[-1][0], at + len(ws))
            else:
                ranges.append((at, at + len(ws)))
            at += len(ws)
        return out

    def summary(self) -> dict:
        return dict(order=self.order, page_set=self.page_set, bifolia=len(self.nodes), pages=len(self.pages), lines=len(self.lines), tokens=self.n_tokens,
                    groups=dict(Counter(n['group'] for n in self.nodes)), extra=self.extra)


def tokenize(ms: Manuscript, stream_lines=None) -> dict:
    """Flatten a line-aligned text (the manuscript's own when stream_lines is None) into per-token arrays: words, page,
    line, pos (in line), linelen, first_line, since_page, since_par, chars_before, line_chars, node, group."""
    lines = ms.lines
    words, page, line_ix, pos, linelen, first_line, since_page, since_par, chars_before, line_chars, node, group = ([] for _ in range(12))
    sp = spar = 0
    last_page = -1
    for li, L in enumerate(lines):
        ws = stream_lines[li] if stream_lines is not None else L['words']
        if L['page'] != last_page:
            sp, last_page = 0, L['page']
        if L['first']:
            spar = 0
        cb = 0
        lc = len(' '.join(ws))
        for k, w in enumerate(ws):
            words.append(w); page.append(L['page']); line_ix.append(li); pos.append(k); linelen.append(len(ws))
            first_line.append(L['first']); since_page.append(sp); since_par.append(spar)
            chars_before.append(cb); line_chars.append(lc); node.append(L['node']); group.append(L['group'])
            cb += len(w) + 1; sp += 1; spar += 1
    arr = np.asarray
    return dict(words=words, page=arr(page), line=arr(line_ix), pos=arr(pos), linelen=arr(linelen), first_line=arr(first_line),
                since_page=arr(since_page), since_par=arr(since_par), chars_before=arr(chars_before), line_chars=arr(line_chars),
                node=np.array(node, dtype=object), group=np.array(group, dtype=object))


def transitions(ms: Manuscript) -> List[dict]:
    """Consecutive page pairs in the manuscript's order with their physical relation (same-face, flip, cross-sheet)."""
    out = []
    P = ms.pages
    for k in range(1, len(P)):
        a, b = P[k - 1], P[k]
        cls = 'cross-sheet' if a['bifolium'] != b['bifolium'] else ('same-face' if a['face'] == b['face'] else 'flip')
        out.append(dict(index=k, prev=a['folio'], cur=b['folio'], cls=cls, group=b['group'], node=b['node'],
                        direction='%s>%s' % (a['side'], b['side']), same_leaf=a['leaf'] == b['leaf'], prev_face=a['face'], cur_face=b['face']))
    return out
