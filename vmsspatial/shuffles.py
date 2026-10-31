"""Rearrangements of a text that keep the page layout, and shuffle baselines scored in the observation's own geometry.

TWO RULES THAT THE 28 OCTOBER 2026 REVIEWS ENFORCED, built in here:

1. A shuffle must keep the layout. Dropping a word into another word's recorded rectangle gives it the wrong width
   (41.6 percent of words off by more than 1.5x in the old recorded-box shuffles; the selector weights by distance and
   reads box geometry, so the control was distorted, and a claim built on it was withdrawn). Every variant is therefore
   either SIZE-MATCHED (words exchanged only with words of the same character length, so every line keeps its
   character count and, with the recorded rectangles, every word keeps a box of its own width) or RE-TYPESET into the
   manuscript's line frames at the line's letter size (``geometry.synthetic_geometry``); line permutations are
   length-banded with the letter size fitted to the slot. ``check_typesetting`` is the guard.

2. A shuffle baseline must be scored in the SAME geometry as the observation (``baseline``): a statistic measured on
   the recorded rectangles is compared with size-matched shuffles that keep the recorded rectangles; a statistic on
   synthetic rectangles with shuffles re-typeset the same way. Mixing them (recorded observed against synthetic
   shuffles) produced p-values that tested nothing and were withdrawn. Every text, the copiers included, gets its own
   baseline; the quantity to compare across texts is the EXCESS over the baseline, not the raw value. One realization
   is never enough: use K of 19 to 30 and report mean, range, rank and the one-sided permutation probability
   (``stats.shuffle_rank``).

Variants:
    words_in_units(unit)   words permuted inside each unit (paragraph, page, bifolium, whole text) among words of the
                           same character length
    words_any_length       words of any length permuted inside the unit (line lengths change; typeset_fit)
    words_in_lines         the words of each line permuted inside that line
    reversed_lines         each line's words in reverse order
    rotated_lines          line k rotated by k words (what stood in one column runs diagonally)
    lines_in_units(unit)   whole lines permuted inside each unit among lines of comparable length (typeset_fit)
    shuffled_in_boxes      SUPERSEDED and deprecated: words of any length permuted but kept in the recorded rectangles
                           of the slots they land in; emits a DeprecationWarning; for comparison with the old method only
"""
from __future__ import annotations

import warnings
from collections import defaultdict
from typing import Dict, Iterator, List, Optional

import numpy as np

from .geometry import place_in_slot, synthetic_geometry


class LayoutError(ValueError):
    pass


def unit_labels(ms, unit: str) -> np.ndarray:
    """Per-line unit labels: 'paragraph' | 'page' | 'bifolium' | 'all'."""
    return {'paragraph': ms.paragraph_of_line(), 'page': ms.page_of_line(), 'bifolium': ms.node_of_line(), 'all': np.zeros(len(ms.lines), int)}[unit]


def size_matched(lines: List[List[str]], unit, rng):
    """Words permuted inside each unit among words of the SAME character length, for any line-aligned text.
    Returns (lines, moved). Every line keeps its character count, so recorded rectangles stay valid."""
    groups = defaultdict(list)
    for l, ws in enumerate(lines):
        for k, w in enumerate(ws):
            groups[(unit[l], len(w))].append((l, k))
    out = [list(ws) for ws in lines]
    moved = 0
    for slots in groups.values():
        words = [lines[l][k] for l, k in slots]
        perm = rng.permutation(len(slots))
        for (l, k), j in zip(slots, perm):
            out[l][k] = words[j]
            moved += words[j] != lines[l][k]
    return out, moved


def words_in_units(ms, unit, rng):
    """The manuscript's words, size-matched inside `unit` (a per-line label array). Returns (line_words, moved)."""
    return size_matched([list(L['words']) for L in ms.lines], unit, rng)


def words_any_length(ms, unit, rng, lines=None):
    """Words of any length permuted inside the unit: line lengths change, so typeset with the fitted letter size."""
    src = lines or [list(L['words']) for L in ms.lines]
    par = np.repeat(unit, [len(ws) for ws in src])
    words = np.array([w for ws in src for w in ws], dtype=object)
    for u in np.unique(par):
        m = np.where(par == u)[0]
        words[m] = words[rng.permutation(m)]
    at, out = 0, []
    for ws in src:
        out.append(list(words[at:at + len(ws)]))
        at += len(ws)
    return out


def words_in_lines(ms, rng, lines=None):
    src = lines or [list(L['words']) for L in ms.lines]
    return [[ws[k] for k in rng.permutation(len(ws))] for ws in src]


def reversed_lines(ms, lines=None):
    src = lines or [list(L['words']) for L in ms.lines]
    return [list(reversed(ws)) for ws in src]


def rotated_lines(ms, lines=None):
    src = lines or [list(L['words']) for L in ms.lines]
    out = []
    for k, ws in enumerate(src):
        ws = list(ws)
        s = k % len(ws) if ws else 0
        out.append(ws[s:] + ws[:s])
    return out


def lines_in_units(ms, unit, rng, band=0.5, lines=None):
    """Lines permuted inside each unit among lines of comparable length (character count within a factor 1 + band of
    the slot's own; the nearest unassigned line when none does). Returns (line_words, moved). Typeset with typeset_fit."""
    src = lines or [list(L['words']) for L in ms.lines]
    chars = np.array([len(' '.join(ws)) for ws in src], float)
    out = [None] * len(src)
    moved = 0
    for u in np.unique(unit):
        idx = np.where(unit == u)[0]
        free = list(idx.tolist())
        for slot in idx[rng.permutation(len(idx))]:
            lo, hi = chars[slot] / (1 + band), chars[slot] * (1 + band)
            fits = [l for l in free if lo - 1e-9 <= chars[l] <= hi + 1e-9]
            pick = fits[rng.integers(len(fits))] if fits else min(free, key=lambda l: abs(chars[l] - chars[slot]))
            free.remove(pick)
            out[slot] = src[pick]
            moved += pick != slot
    return out, moved


def shuffled_in_boxes(ms, unit, rng):
    """SUPERSEDED: words of any length permuted within each unit (per-TOKEN unit labels), line word counts kept, the
    recorded rectangles reused as they stand. 41.6 percent of the words land in a box more than 1.5x too wide or too
    narrow. Kept only to compare the old control with the correct ones; never use it for a result."""
    warnings.warn('shuffled_in_boxes puts words into other words\' rectangles; use size_matched/words_in_units (recorded geometry kept) or a re-typeset variant', DeprecationWarning, stacklevel=2)
    words = np.array([w for L in ms.lines for w in L['words']], dtype=object)
    for u in np.unique(unit):
        m = np.where(unit == u)[0]
        words[m] = words[rng.permutation(m)]
    out, at = [], 0
    for L in ms.lines:
        n = len(L['words'])
        out.append(list(words[at:at + n]))
        at += n
    return out


def typeset(ms, frames, line_words):
    """Lay the variant into the manuscript's frames; returns (lines as placed, geometry, carried)."""
    before = [len(ws) for ws in line_words]
    lines = [list(ws) for ws in line_words]
    geometry = synthetic_geometry(lines, frames, ms)
    carried = sum(max(0, a - len(ws)) for a, ws in zip(before, lines))
    return lines, geometry, carried


def typeset_fit(ms, frames, line_words):
    """Each slot's words at the letter size that fills the slot. Returns (lines, geometry, no_box, cw_ratio)."""
    geometry, ratios, no_box = [], [], 0
    for l, ws in enumerate(line_words):
        fr = frames[l]
        if fr is None or not ws:
            geometry += [None] * len(ws)
            continue
        width = sum(b - a for a, b in fr[4])
        cw0 = width / max(ms.lines[l]['chars'], 1)
        cw = width / max(len(' '.join(ws)), 1)
        placed, boxes = place_in_slot(ws, fr, cw)
        tries = 0
        while placed < len(ws) and tries < 8:
            cw *= 0.94
            placed, boxes = place_in_slot(ws, fr, cw)
            tries += 1
        geometry += boxes + [None] * (len(ws) - placed)
        no_box += len(ws) - placed
        ratios.append(cw / cw0)
    return [list(ws) for ws in line_words], geometry, no_box, np.array(ratios)


def check_typesetting(ms, frames, line_words, geometry, max_off_share=0.01, raise_on_fail=True) -> dict:
    """Guard: the share of boxed words whose box width is off by more than 1.5x from the word's width at the line's
    letter size must stay below `max_off_share` (0.1 percent for a re-typeset text; 41.6 percent is the old mistake).
    Returns the layout_check report; raises LayoutError when the guard fails."""
    from .layout_check import check
    report = check(ms, frames, line_words, geometry)
    report['ok'] = report['width']['off_1p5'] <= max_off_share
    if raise_on_fail and not report['ok']:
        raise LayoutError('%.1f%% of the words sit in a box off by more than 1.5x: this text was not typeset into the frames' % (100 * report['width']['off_1p5']))
    return report


VARIANT_NAMES = ['manuscript (synthetic boxes)', 'words shuffled in paragraphs (size-matched)', 'words shuffled in pages (size-matched)',
                 'words shuffled in bifolia (size-matched)', 'words shuffled in whole manuscript (size-matched)',
                 'words shuffled in paragraphs (any length, fitted letter size)', 'words shuffled in lines', 'lines reversed',
                 'lines rotated (diagonal)', 'lines shuffled in paragraphs (fitted letter size)', 'lines shuffled in pages (fitted letter size)']


def variants(ms, frames, seed=1028, names=None) -> Dict[str, dict]:
    """Every standard variant typeset, in a fixed order: name -> dict(lines, geometry, carried, moved, cw_ratio)."""
    rng = np.random.default_rng(seed)
    par, page = ms.paragraph_of_line(), ms.page_of_line()
    node = ms.node_of_line()
    out = {}
    wanted = set(names) if names else None

    def add(name, lines, moved=None, fit=False):
        if wanted is not None and name not in wanted:
            return
        if fit:
            placed, geom, carried, ratio = typeset_fit(ms, frames, lines)
        else:
            placed, geom, carried = typeset(ms, frames, lines)
            ratio = None
        out[name] = dict(lines=placed, geometry=geom, carried=carried, moved=moved, cw_ratio=ratio)

    add(VARIANT_NAMES[0], [list(L['words']) for L in ms.lines])
    lines, moved = words_in_units(ms, par, rng)
    add(VARIANT_NAMES[1], lines, moved)
    lines, moved = words_in_units(ms, page, rng)
    add(VARIANT_NAMES[2], lines, moved)
    lines, moved = words_in_units(ms, node, rng)
    add(VARIANT_NAMES[3], lines, moved)
    lines, moved = words_in_units(ms, np.zeros(len(ms.lines), int), rng)
    add(VARIANT_NAMES[4], lines, moved)
    add(VARIANT_NAMES[5], words_any_length(ms, par, rng), None, fit=True)
    add(VARIANT_NAMES[6], words_in_lines(ms, rng))
    add(VARIANT_NAMES[7], reversed_lines(ms))
    add(VARIANT_NAMES[8], rotated_lines(ms))
    lines, moved = lines_in_units(ms, par, rng)
    add(VARIANT_NAMES[9], lines, moved, fit=True)
    lines, moved = lines_in_units(ms, page, rng)
    add(VARIANT_NAMES[10], lines, moved, fit=True)
    return out


def repeated(ms, frames, k=19, unit='paragraph', seed=1028) -> Iterator[tuple]:
    """K size-matched word shuffles of the MANUSCRIPT inside `unit`, re-typeset: yields (lines, geometry) per
    realization (synthetic geometry). For a baseline matched to any text and geometry use `baseline`."""
    rng = np.random.default_rng(seed)
    u = unit_labels(ms, unit)
    for _ in range(k):
        lines, _ = words_in_units(ms, u, rng)
        placed, geom, _ = typeset(ms, frames, lines)
        yield placed, geom


def baseline(ms, line_words, geometry, geometry_kind, frames=None, k=30, unit='paragraph', seed=1028) -> Iterator[tuple]:
    """K size-matched shuffles of ANY line-aligned text, scored in the observation's own geometry:
      geometry_kind 'recorded'   the words are exchanged among same-length words, so each slot's recorded box fits the
                                 word that lands in it: the geometry is returned unchanged ('flattened', the recorded
                                 boxes with the page warp removed, is treated the same way)
      geometry_kind 'synthetic'  the shuffle is re-typeset into the frames (needs `frames`)
    Yields (lines, geometry). Use the same k, unit and seed for every text you compare, and compare excesses."""
    rng = np.random.default_rng(seed)
    u = unit_labels(ms, unit)
    if geometry_kind not in ('recorded', 'flattened', 'synthetic'):
        raise ValueError("geometry_kind must be 'recorded', 'flattened' or 'synthetic' (say which geometry the observation was scored on)")
    if geometry_kind == 'synthetic' and frames is None:
        raise ValueError('a synthetic-geometry baseline needs the line frames')
    for _ in range(k):
        lines, _ = size_matched(line_words, u, rng)
        if geometry_kind in ('recorded', 'flattened'):
            yield lines, list(geometry)
        else:
            placed, geom, _ = typeset(ms, frames, lines)
            yield placed, geom
