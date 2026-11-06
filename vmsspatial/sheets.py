"""The odd-shaped sheets: foldout leaves, the Rosettes sheet and the bifolia that lack a leaf.

``resources/sheets.json`` records, for each foldout leaf, how many panels it has, which page lies on which (counted out from
the binding fold), and the vertical lines placed on each Beinecke photograph of it: the fold, the creases, any further fold
inside a panel and the outer edge, in scan px (docs/SHEETS.md). From those lines this module gives

* ``panel_widths(node)``: each panel's width in mm on each photograph, and the width taken, read on the face the resource
  names for that panel (``use``: the photograph where it lies flat with both of its lines clear); ``spread`` flags a panel
  whose two faces differ by more than SPREAD_MM; ``faces`` gives each face's widths where a panel is read on each face's own
  photograph (``own``: the binding hides a different strip of it on each face);
* ``page_lines(folio, scan)``: the page's fold-side line and outer line on a photograph of it, for ``vmsspatial.leaves``;
* ``for_viewer()``: the widths, the pages' panels and the further folds, and the Rosettes grid, for the Light table.

Scan px become mm at the scan's scale: the one shared by every scan, or a scan's own where ``vmsspatial.leaves`` gives it
one (``calibration.scans_own_scale``).

    >>> from vmsspatial import sheets
    >>> sheets.panel_widths('S:100-101')['101']['width']          # doctest: +SKIP
    [138.1, 139.6]
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from . import paths

SPREAD_MM = 5.0
DEFAULT_PX_PER_MM = 15.84


@lru_cache(maxsize=1)
def load() -> dict:
    """The resource, read once."""
    return json.loads((paths.RESOURCES / 'sheets.json').read_text(encoding='utf-8'))


def _scales() -> Tuple[float, Dict[str, float]]:
    from .leaves import load_leaves
    cal = (load_leaves() or {}).get('calibration') or {}
    return float(cal.get('scan_px_per_mm') or DEFAULT_PX_PER_MM), {k: float(v) for k, v in (cal.get('scans_own_scale') or {}).items()}


def scale_of(scan: str) -> float:
    """Scan px per mm for one scan."""
    common, own = _scales()
    return own.get(scan, common)


def _inner(k: int) -> str:
    return 'fold' if k == 1 else '%d|%d' % (k - 1, k)


def _outer(k: int, n: int) -> str:
    return 'edge' if k == n else '%d|%d' % (k, k + 1)


def panel_widths(node: str) -> Dict[str, dict]:
    """{leaf: {readings: [{scan, side, widths: [mm or None per panel], folds: {panel: mm from its inner line}}], width: [mm],
    folds: {panel: mm}, spread: [panels whose readings differ by more than SPREAD_MM]}} for the foldout leaves of one sheet."""
    out = {}
    for leaf, spec in (load()['sheets'].get(node, {}).get('leaves') or {}).items():
        n, readings = spec['panels'], []
        for ph in spec['photos']:
            s, ln = scale_of(ph['scan']), ph['lines']
            widths = [abs(ln[_outer(k, n)] - ln[_inner(k)]) / s if _inner(k) in ln and _outer(k, n) in ln else None for k in range(1, n + 1)]
            folds = {k: abs(ln['%d fold' % k] - ln[_inner(k)]) / s for k in range(1, n + 1) if '%d fold' % k in ln and _inner(k) in ln}
            readings.append(dict(scan=ph['scan'], side=ph['side'], widths=[None if w is None else round(w, 1) for w in widths], folds={k: round(v, 1) for k, v in folds.items()}))
        width, spread, folds, use = [], [], {}, spec.get('use') or ['r'] * n
        for k in range(n):
            ws = [r['widths'][k] for r in readings if r['widths'][k] is not None]
            chosen = [r['widths'][k] for r in readings if r['widths'][k] is not None and r['side'] == use[k]]
            width.append(chosen[0] if chosen else (ws[0] if ws else None))
            if ws and max(ws) - min(ws) > SPREAD_MM:
                spread.append(k + 1)
        for k in range(1, n + 1):
            fs = [r['folds'][k] for r in readings if k in r['folds']]
            if fs:
                folds[k] = round(sum(fs) / len(fs), 1)
        out[leaf] = dict(readings=readings, width=width, folds=folds, spread=spread)
        if spec.get('own'):                      # a panel read on each face's own photograph, from that face's fold
            out[leaf]['faces'] = {side: [next((r['widths'][k] for r in readings if r['side'] == side and r['widths'][k] is not None), width[k])
                                         if k + 1 in spec['own'] else width[k] for k in range(n)] for side in ('r', 'v')}
    return out


def _leaf_of(folio: str) -> Optional[Tuple[str, str, dict]]:
    for node, sh in load()['sheets'].items():
        for leaf, spec in (sh.get('leaves') or {}).items():
            if folio in spec['pages']:
                return node, leaf, spec
    return None


def page_lines(folio: str, scan: str) -> Optional[dict]:
    """{fold, outer, panels} for a foldout page on one photograph of its side: the scan x of the line on its fold side (the
    binding for panel 1, else the crease toward the fold) and of the line on its outer side, either None when that
    photograph does not show it; None when the page is no foldout page or the photograph is not of its side."""
    found = _leaf_of(folio)
    if not found:
        return None
    node, leaf, spec = found
    side = 'v' if folio[len('f%s' % leaf):][:1] == 'v' else 'r'
    span, n = spec['pages'][folio], spec['panels']
    for ph in spec['photos']:
        if ph['scan'] == scan and ph['side'] == side:
            return dict(fold=ph['lines'].get(_inner(span[0])), outer=ph['lines'].get(_outer(span[-1], n)), panels=span, node=node, leaf=leaf)
    return None


def for_viewer() -> dict:
    """{node: {A|B: {widths: [mm], pages: {folio: [panel index from 0]}, creases: [[panel index, mm from its inner edge]],
    faces (where a panel is read on each face): {r|v: [mm]}}} or
    {grid: ...}} for every foldout sheet, the leaf letter as in the bifolium (A the lower folio number)."""
    out = {}
    for node, sh in load()['sheets'].items():
        if 'grid' in sh:
            out[node] = dict(grid=sh['grid'])
            continue
        if not sh.get('leaves'):
            continue
        leaves = sorted(int(x) for x in node.split(':')[1].split('-'))
        rec = {}
        for leaf, w in panel_widths(node).items():
            spec = sh['leaves'][leaf]
            if spec['panels'] < 2:
                continue
            rec['A' if int(leaf) == leaves[0] else 'B'] = dict(widths=w['width'], pages={f: [k - 1 for k in span] for f, span in spec['pages'].items()},
                                                             creases=[[k - 1, mm] for k, mm in sorted(w['folds'].items())], spread=w['spread'],
                                                             **({'faces': w['faces']} if 'faces' in w else {}))
        if rec:
            out[node] = rec
    return out


def check(physical: Optional[dict] = None) -> List[str]:
    """Problems in the resource against the physical map: a panel page of the map missing from it or listed under another
    leaf, a page listed that the map lacks, a photograph missing a fold or edge line it should show. [] when none."""
    if physical is None:
        from .manuscript import load_physical
        physical = load_physical()
    problems = []
    listed = {}
    for node, sh in load()['sheets'].items():
        for leaf, spec in (sh.get('leaves') or {}).items():
            for f, span in spec['pages'].items():
                listed[f] = (node, leaf)
                if f not in physical:
                    problems.append('%s: not in the physical map' % f)
                elif physical[f]['bifolium'] != node or str(physical[f]['leaf']) != leaf:
                    problems.append('%s: the map has %s leaf %s, the sheets %s leaf %s' % (f, physical[f]['bifolium'], physical[f]['leaf'], node, leaf))
                if not span or min(span) < 1 or max(span) > spec['panels']:
                    problems.append('%s: panels %s outside 1..%d' % (f, span, spec['panels']))
            for ph in spec['photos']:
                xs = [ph['lines'][k] for k in ph['lines']]
                order = sorted(ph['lines'], key=lambda k: ph['lines'][k])
                if xs != sorted(xs) and xs != sorted(xs, reverse=True):
                    problems.append('%s %s: lines out of order %s' % (leaf, ph['scan'], order))
        for f, p in physical.items():
            if p['bifolium'] == node and p.get('panel') and p['panel'] != 'Ros' and f not in listed and 'grid' not in sh:
                problems.append('%s: a panel page of %s the sheets do not list' % (f, node))
    for f, p in physical.items():
        if p.get('panel') and p['panel'] != 'Ros' and f not in listed and 'grid' not in load()['sheets'].get(p['bifolium'], {}):
            problems.append('%s: a panel page with no sheet entry' % f)
    return sorted(set(problems))
