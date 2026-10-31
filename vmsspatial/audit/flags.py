"""Review flags of the alignment audit and the two eligibility policies.

A flag describes an ASSIGNMENT (which ZL token goes with which recorded rectangle), never a defect of the manuscript or
of the original rectangles. Flags overlap and must not be summed.

``group_flags``, ``line_flags`` and ``resolve_compound`` are the rules that derive a group's flags. They read a group
along its line's direction, so a rotated block or a ring is judged as level text is.
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Sequence

from ..units import parse_eva

# (scope, meaning). scope 'group' = a property of the token's assignment group; 'token' = of the token itself.
FLAGS = {
    'shared_box': ('group', 'Several ZL tokens share one physical group of rectangles; their individual positions are unresolved.'),
    'multiple_boxes': ('group', 'The assignment spans more than one original rectangle.'),
    'cross_locus': ('group', 'The assignment joins tokens of different ZL loci (lines).'),
    'cross_intrusion': ('group', 'The assignment joins tokens separated by a drawing intrusion (<-> or <~>).'),
    'disconnected_parts': ('group', 'The original pieces of the assignment do not form one run along the line.'),
    'invalid_box': ('group', 'An original rectangle lies outside the page or has no area.'),
    'duplicate_box': ('group', 'The same rectangle is recorded twice on the page.'),
    'high_alignment_cost': ('group', 'The distance between the ZL spelling and the coordinate spelling exceeds 0.34 and no reviewer confirmed the assignment; line and reading order placed the word.'),
    'spelling_difference': ('group', 'The two transcriptions spell the word differently (an ordinary reading difference; not a rejection).'),
    'short_wide': ('group', 'A one- or two-glyph word assigned a rectangle wider than expected for its length.'),
    'line_outlier': ('group', 'The rectangle sits far from the level of its prose line.'),
    'order_reversal': ('group', 'Consecutive words of a prose line whose rectangles run against the reading direction.'),
    'large_recorded_box': ('group', 'The rectangle is wider than 6 or taller than 2.5 times the page median (an inspection flag only; tall gallows are legitimate).'),
    'missing_box': ('group', 'The token is on a coordinate page but no rectangle is assigned to it.'),
    'xml_only': ('group', 'A coordinate word with no ZL token (a label or a marginal word outside the canonical text).'),
    'box_corrected': ('group', 'A rectangle itself was corrected from source review (none in the current release).'),
    'alignment_corrected': ('group', 'The assignment was changed from the automatic alignment after review.'),
    'alignment_reviewed': ('group', 'A reviewer inspected the assignment on the native image.'),
    'exact_compound_union': ('token', 'One ZL word equals consecutive adjacent coordinate words; their union is its geometry.'),
    'image_reviewed_boundary': ('token', 'The word boundary inside a shared rectangle was cut on the native image.'),
    'uncertain_boundary': ('token', 'The ZL space after the token is uncertain (a comma).'),
    'alternative_reading': ('token', 'The ZL token has an alternative reading ([a:b]); the preferred reading is used.'),
    'no_coordinate_page': ('token', 'No coordinate page exists for the token (fRos, f116v).'),
    'no_xml_word': ('token', 'The Voynichese XML has no word where this token belongs (a rare glyph, or text it did not record).'),
    'transcriptions_differ': ('token', 'A free rectangle stands where the token belongs, but the two transcriptions are too different and their word counts disagree there.'),
    'position_failed': ('token', 'A free rectangle has this spelling, but it stands off the token\'s line or out of reading order.'),
}

HARD = frozenset({'invalid_box', 'cross_locus', 'cross_intrusion', 'disconnected_parts'})
STRICT = HARD | frozenset({'shared_box', 'multiple_boxes', 'high_alignment_cost', 'short_wide', 'line_outlier', 'order_reversal', 'duplicate_box'})
POLICIES = {'strict': STRICT, 'sensitivity': HARD}
# The pages whose paragraph lines are not all horizontal, the computed set ``vmsspatial.orientation.nonhorizontal_pages(
# load_bundle('sensitivity'))`` (tests assert the two agree). The line statistics skip non-horizontal LINES
# (``orientations='horizontal'``), not pages.
QUARANTINE = frozenset({'f67r2', 'f67v2', 'f85r2', 'f86v3'})
PROSE_LOCI = frozenset({'P0', 'P1', 'Pb', 'Pc', 'Pr', 'Pt'})
HIGH_COST = 0.34
NO_XML_WORD, TRANSCRIPTIONS_DIFFER, POSITION_FAILED = 'no_xml_word', 'transcriptions_differ', 'position_failed'
UNLOCATED_REASONS = (NO_XML_WORD, TRANSCRIPTIONS_DIFFER, POSITION_FAILED)
TOKEN_FLAGS = frozenset(k for k, v in FLAGS.items() if v[0] == 'token')


def describe(flag: str) -> str:
    return FLAGS.get(flag, ('?', flag))[1]


def along_line(box: Sequence[float], angle: float) -> List[float]:
    """A rectangle in the frame of a line read `angle` degrees clockwise from left to right: [start, top, end, bottom]
    along and across the line."""
    if not angle:
        return list(box)
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    xs, ys = (box[0], box[2]), (box[1], box[3])
    along = [x * c + y * s for x in xs for y in ys]
    across = [y * c - x * s for x in xs for y in ys]
    return [min(along), min(across), max(along), max(across)]


def group_flags(group: dict, tokens: Sequence[dict], page: dict, box_counts: Dict[tuple, int], cost: float, angle: float = 0.0) -> set:
    """The flags of an assignment group: `tokens` are its token records, `page` the review's page record, `box_counts`
    counts each rectangle of the page, `cost` is the spelling distance, `angle` the line's direction."""
    flags = set()
    parts, ids = group['parts'], group['tokens']
    mw, mh = page['median_width'], page['median_height']
    if not parts:
        flags.add('missing_box')
    if len(ids) > 1:
        flags.add('shared_box')
    if len(parts) > 1:
        flags.add('multiple_boxes')
    if len({t['locus'] for t in tokens}) > 1:
        flags.add('cross_locus')
    if any(str(t.get('boundary') or '').startswith('intrusion') for t in tokens[:-1]):
        flags.add('cross_intrusion')
    if cost > HIGH_COST and 'alignment_reviewed' not in group['flags']:
        flags.add('high_alignment_cost')
    if ids and ''.join(t['text'] for t in tokens) != ''.join(group['xml_words']):
        flags.add('spelling_difference')
    for b in parts:
        if b[0] < 0 or b[1] < 0 or b[2] <= b[0] or b[3] <= b[1] or b[2] > page['width'] or b[3] > page['height']:
            flags.add('invalid_box')
        if b[2] - b[0] > 6 * mw or b[3] - b[1] > 2.5 * mh:
            flags.add('large_recorded_box')      # tall gallows and wide words are legitimate: an inspection flag, never a defect
        if box_counts.get(tuple(b), 0) > 1:
            flags.add('duplicate_box')
    level = [along_line(b, angle) for b in parts]
    for a, b in zip(level, level[1:]):
        if min(a[3], b[3]) - max(a[1], b[1]) <= 0 or b[0] < a[0] or b[0] - a[2] > mw:
            flags.add('disconnected_parts')
    if len(tokens) == 1 and group['box']:
        atoms = parse_eva(tokens[0]['text'])
        box = along_line(group['box'], angle)
        if all(a.kind == 'glyph' for a in atoms) and len(atoms) <= 2 and box[2] - box[0] > max(.8 * mw, 2.5 * len(atoms) * mw / 5):
            flags.add('short_wide')
    return flags


def line_flags(line: List[dict], angles: Dict[str, float], page: dict) -> None:
    """The physical-line diagnostics of one prose line, in place: `line` holds its groups in reading order, `angles`
    their directions (the line takes its middle word's)."""
    mw, mh = page['median_width'], page['median_height']
    angle = angles.get(line[len(line) // 2]['id'], 0.0)
    boxes = [along_line(g['box'], angle) for g in line]
    extra = {g['id']: set() for g in line}
    if len(line) >= 4:
        ys = [(b[1] + b[3]) / 2 for b in boxes]
        med = statistics.median(ys)
        mad = statistics.median(abs(y - med) for y in ys)
        for g, y in zip(line, ys):
            if abs(y - med) > max(1.5 * mh, 4 * mad):
                extra[g['id']].add('line_outlier')
    for a, b, ba, bb in zip(line, line[1:], boxes, boxes[1:]):
        if bb[0] < ba[0] - .5 * mw:
            extra[a['id']].add('order_reversal')
            extra[b['id']].add('order_reversal')
    for g in line:
        if extra[g['id']]:
            g['flags'] = sorted(set(g['flags']) | extra[g['id']])


def resolve_compound(group: dict, text: str, page: dict, angle: float = 0.0) -> None:
    """One ZL word that equals consecutive, adjacent XML words on one physical row takes their union as its geometry
    (group['resolved'], method `exact_compound_union`), in place."""
    parts, idx = group['parts'], group['xml_indices']
    if (len(group['tokens']) != 1 or len(parts) < 2 or set(group['flags']) & (STRICT - {'multiple_boxes'}) or text != ''.join(group['xml_words'])
            or sorted(idx) != list(range(min(idx), max(idx) + 1))):
        return
    level = [along_line(b, angle) for b in parts]
    if min(b[3] for b in level) <= max(b[1] for b in level) or any(b[0] < a[0] or b[0] - a[2] > .5 * page['median_width'] for a, b in zip(level, level[1:])):
        return
    d = group.get('display_parts')
    group['resolved'] = [dict(token=group['tokens'][0], box=list(group['box']),
                              display_box=[min(p[0] for p in d), min(p[1] for p in d), max(p[2] for p in d), max(p[3] for p in d)] if d else None,
                              method='exact_compound_union', xml_indices=list(idx), reason='One ZL word exactly equals consecutive, adjacent XML words on one physical row.')]
