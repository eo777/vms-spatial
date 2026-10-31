"""Pages outside the study's token set.

The study transcription (``manuscript/tokens.json``) holds the paragraph text of 207 pages on the 50 Path 1 bifolia.
The ZL transliteration has 227 pages: the other 20 are the circular and astronomical pages (f57v, f65r, f67v1,
f68r3, f68v1, f69v, f70r1, f70v1, f70v2, f71r, f71v, f72r1-3, f72v1-3, f73r, f73v, f116v), which the Voynichese
Project did record, and the Rosettes foldout (fRos), which it did not. ``Manuscript.load(extra=True)`` appends these
pages: their lines come from the same lattice reading as the study tokens (uncertain-reading tokens omitted), their
physical records from ``physical_map.csv`` where present and from the ZL page variables otherwise, and each page joins
the node of its bifolium (an existing Path 1 node, or a new node at the end of the order with group '—'). The same
call adds every other page's non-paragraph loci (labels, circular and radial text), so that ``extra=True`` means
everything the Voynichese Project recorded plus the Rosettes: all 227 pages and all loci, each line with its locus
type (``locus_types``) and, in a bundle, its orientation record (``vmsspatial.orientation``). ``extra='all'`` is the
same thing (an older spelling).

Geometry for the extra pages comes from the alignment review for the recorded pages and from the Rosettes supplement
(``manuscript/supplement_fRos.json``, geometry_kind 'detected', see vmsspatial.rosettes) for fRos; see
bundle.extend_bundle. Scores on circular text are not comparable with scores on paragraph text: the line order of a
ring is one line, the "lines above" are other rings, and the detected boxes carry a confidence. Keep the extra pages
out of a statistic unless the question is about them.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from . import paths
from .manuscript import SECTION_NAMES

ROSETTES = 'fRos'
# the ZL page variables: $Q quire, $P page in quire, $I illustration type, $L Currier language, $H hand
QUIRE_NUM = {q: i + 1 for i, q in enumerate('ABCDEFGHIJKLMNOPQRST')}


def zl_pages(raw=None) -> Dict[str, dict]:
    """page -> ZL page variables, in file order."""
    from .audit._zl.source_lattice import SourceLattice
    lat = SourceLattice(raw or paths.resolve('raw/ZL_ivtff_raw.txt'))
    out: Dict[str, dict] = {}
    for L in lat.loci:
        if L.page not in out:
            out[L.page] = dict(L.page_vars)
    return out


_LOCUS_TYPES = {}


def locus_types(raw=None) -> Dict[str, Dict[str, str]]:
    """page -> {locus: ZL locus type (P0, P1, Pb, L0, Lz, Cc, Ca, Ri, Ro, ...)} for every locus of the transliteration.
    Read from the shipped resource ``locus_types.json`` (built by ``build_locus_types``); the lattice is parsed only
    when the resource is absent."""
    key = str(raw) if raw else ''
    if key not in _LOCUS_TYPES:
        res = paths.resource('locus_types.json')
        if not raw and res.is_file():
            import json
            _LOCUS_TYPES[key] = json.loads(res.read_text(encoding='utf-8'))['pages']
        else:
            from .audit._zl.source_lattice import SourceLattice
            lat = SourceLattice(raw or paths.resolve('raw/ZL_ivtff_raw.txt'))
            out: Dict[str, Dict[str, str]] = {}
            for L in lat.loci:
                out.setdefault(L.page, {})[str(L.num)] = L.locus_type
            _LOCUS_TYPES[key] = out
    return _LOCUS_TYPES[key]


def build_locus_types(out=None) -> dict:
    """Write resources/locus_types.json from the lattice: {source, note, loci, counts, pages: {page: {locus: type}}}."""
    import json
    from collections import Counter
    from .audit._zl.source_lattice import SourceLattice, SOURCE_VERSION
    lat = SourceLattice(paths.resolve('raw/ZL_ivtff_raw.txt'))
    pages: Dict[str, Dict[str, str]] = {}
    for L in lat.loci:
        pages.setdefault(L.page, {})[str(L.num)] = L.locus_type
    counts = Counter(t for p in pages.values() for t in p.values())
    rec = dict(source=SOURCE_VERSION, note='ZL locus type of every locus (page, locus number); built from the transliteration by vmsspatial.extra.build_locus_types',
               loci=sum(counts.values()), counts=dict(sorted(counts.items())), pages=pages)
    path = out or paths.resource('locus_types.json')
    path.write_text(json.dumps(rec, separators=(',', ':'), sort_keys=True) + '\n', encoding='utf-8')
    _LOCUS_TYPES.clear()
    return rec


def locus_category(locus_type) -> str:
    """'P' paragraph, 'L' label, 'C' circular, 'R' radial, '?' unknown: the first letter of the ZL locus type."""
    return locus_type[0] if locus_type else '?'


def leaf_of(folio: str) -> int:
    if folio == ROSETTES:
        return 85
    m = re.match(r'f(\d+)', folio)
    return int(m.group(1)) if m else 0


def extra_page_names(known: set, raw=None) -> List[str]:
    """ZL pages that are not in `known`, in leaf order."""
    names = [p for p in zl_pages(raw) if p not in known]
    return sorted(names, key=lambda p: (leaf_of(p), p))


_EXTRA_LINES = {}


def all_lines(raw=None) -> List[dict]:
    """Every locus of the transliteration outside the study transcription (tokens.json), in the study's token
    convention: {folio, locus, words, first, locus_type}; tokens containing '?' are omitted (as in tokens.json),
    empty loci dropped; `first` marks a locus that opens a unit ('@' locator). Read from the shipped resource
    ``zl_extra_lines.json`` (``build_zl_lines``) when present, else parsed from the lattice (every locus then)."""
    key = str(raw) if raw else ''
    if key not in _EXTRA_LINES:
        res = paths.resource('zl_extra_lines.json')
        if not raw and res.is_file():
            import json
            _EXTRA_LINES[key] = json.loads(res.read_text(encoding='utf-8'))['lines']
        else:
            from .audit._zl.source_lattice import SourceLattice
            lat = SourceLattice(raw or paths.resolve('raw/ZL_ivtff_raw.txt'))
            out = []
            for lt in lat.stream():
                L = lt.locus
                words = [t.text for t in lt.tokens if '?' not in t.text]
                if not words:
                    continue
                out.append(dict(folio=L.page, locus=str(L.num), words=words, first=L.locator == '@', locus_type=L.locus_type))
            _EXTRA_LINES[key] = out
    return _EXTRA_LINES[key]


def build_zl_lines(out=None) -> dict:
    """Write resources/zl_extra_lines.json: every readable locus of the ZL transliteration that tokens.json does not
    hold (the labels, circular and radial text, the 20 pages outside the study), with words and locus type."""
    import json
    from .audit._zl.source_lattice import SOURCE_VERSION
    from .manuscript import load_tokens
    _EXTRA_LINES.clear()
    res = paths.resource('zl_extra_lines.json')
    if res.is_file():
        res.unlink()
    study = {(L['folio'], str(L['locus'])) for L in load_tokens()['lines']}
    lines = [L for L in all_lines() if (L['folio'], L['locus']) not in study]
    rec = dict(source=SOURCE_VERSION, note='Every readable locus of the ZL transliteration outside the study transcription tokens.json (uncertain-reading tokens omitted, '
                                           'empty loci dropped) with its words, paragraph-start flag and locus type; built by vmsspatial.extra.build_zl_lines. Manuscript.load reads the labels, '
                                           'circular and radial loci and the 20 non-study pages from it.',
               n_lines=len(lines), tokens=sum(len(L['words']) for L in lines), lines=lines)
    path = out or res
    path.write_text(json.dumps(rec, separators=(',', ':')) + '\n', encoding='utf-8')
    _EXTRA_LINES.clear()
    return rec


def extra_lines(pages: List[str], raw=None) -> List[dict]:
    """The lines of the given pages (``all_lines`` filtered)."""
    wanted = set(pages)
    return [dict(L) for L in all_lines(raw) if L['folio'] in wanted]


def extra_physical(pages: List[str], physical: Dict[str, dict], raw=None) -> Dict[str, dict]:
    """Physical records for the extra pages: the physical map's row when it has one, otherwise a record built from the
    ZL page variables (and the sibling side's row when there is one)."""
    vars_ = zl_pages(raw)
    out = {}
    for p in pages:
        if p in physical:
            out[p] = dict(physical[p])
            continue
        v = vars_.get(p, {})
        leaf = leaf_of(p)
        sibling = None
        for q, row in physical.items():
            if row['leaf'] == leaf and q != p:
                sibling = row
                break
        quire = v.get('Q', sibling['quire'] if sibling else '?')
        section = v.get('I', sibling['section'] if sibling else 'T')
        currier = v.get('L', sibling['currier'] if sibling else '')
        hand = v.get('H', sibling['hand'] if sibling else '')
        if p == ROSETTES:
            rec = dict(leaf=85, side='v', panel='Ros', quire='N', quire_num=14, bifolium='N:85-86', bif_pos=1, partner=86, A=85, B=86, face='inner',
                       section='C', currier=currier or 'B', hand=hand)
        else:
            side = 'v' if p.endswith('v') or re.search(r'v\d$', p) else 'r'
            if sibling:
                rec = dict(sibling, side=side, panel=re.sub(r'^f\d+[rv]', '', p))
                rec['face'] = 'inner' if (rec['leaf'] == rec['A'] and side == 'v') or (rec['leaf'] == rec['B'] and side == 'r') else 'outer'
            else:
                rec = dict(leaf=leaf, side=side, panel='', quire=quire, quire_num=QUIRE_NUM.get(quire, 0), bifolium='%s:%d' % (quire, leaf), bif_pos=1,
                           partner=leaf, A=leaf, B=leaf, face='outer', section=section, currier=currier, hand=hand)
        rec['section_name'] = SECTION_NAMES.get(rec['section'], rec['section']) + (' ' + rec['currier'] if rec['section'] in ('H', 'S') and rec['currier'] in ('A', 'B') else '')
        out[p] = rec
    return out
