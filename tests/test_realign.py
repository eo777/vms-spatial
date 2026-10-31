"""The alignment of the ZL tokens to the rectangles: f49v, where the XML lists the letter column before the paragraph, and
the rules on a small page with no XML file behind it."""
import math

import pytest

from conftest import needs_data

from vmsspatial import realign as R
from vmsspatial.audit.flags import HARD, UNLOCATED_REASONS, along_line, group_flags, line_flags, resolve_compound
from vmsspatial.audit.checks import check_review


@pytest.fixture(scope='module')
def f49v(review):
    toks = [t for t in review['tokens'] if t['page'] == 'f49v']
    return {t['id']: t for t in toks}, toks, {k: g for k, g in review['groups'].items() if g['page'] == 'f49v'}


def _words_of(review, toks, locus):
    return [(t['text'], review['groups'][t['group']]['xml_indices'], review['groups'][t['group']]['xml_words']) for t in toks if t['locus'] == locus]


@needs_data
def test_f49v_lines_stand_on_their_real_boxes(review, f49v):
    _, toks, _ = f49v
    assert _words_of(review, toks, '2') == [('kshor', [20], ['kshor']), ('shol', [21], ['shol']), ('cphokchol', [22], ['cphokchol']), ('ch{cfhh}y', [23], ['chcfhhy'])]
    assert _words_of(review, toks, '4') == [('qokchy', [24], ['qokchy']), ('qokchod', [25], ['qokchod']), ('sho', [26], ['sho']), ('ckhy', [27], ['cthy'])]
    assert all(t['sensitivity'] for t in toks if t['locus'] in ('2', '4'))


@needs_data
def test_f49v_letter_column_runs_in_order_on_boxes_of_its_own(review, f49v):
    _, toks, _ = f49v
    letters = [t for t in toks if t['locus_type'][0] == 'L']
    assert len(letters) == 26
    located = [t for t in letters if t['sensitivity']]
    assert len(located) == 20
    tops = [review['groups'][t['group']]['box'][1] for t in located]
    assert tops == sorted(tops)
    assert all(max(review['groups'][t['group']]['box'][0], 0) < 380 for t in located)     # the column left of the paragraph
    r = next(t for t in letters if t['text'] == 'r')
    g = review['groups'][r['group']]
    assert g['xml_words'] == ['r'] and len(g['tokens']) == 1 and r['strict']              # r is not on paragraph words
    rare = [t for t in letters if not t['sensitivity']]
    assert all(t['text'].startswith('@') and 'no_xml_word' in t['flags'] for t in rare) and len(rare) == 6


@needs_data
def test_no_rectangle_is_held_twice_and_none_is_shared_silently(review):
    assert R.check_groups(review) == []
    rep = check_review(review)
    assert all(v.get('ok') for v in rep.values()), rep


@needs_data
def test_every_unlocated_token_has_a_reason(review):
    no_box = [t for t in review['tokens'] if not t['sensitivity'] and t['page'] in review['pages']]
    for t in no_box:
        assert set(t['flags']) & (set(UNLOCATED_REASONS) | HARD), t
    assert not any('page_quarantine' in t['flags'] for t in review['tokens'])
    assert sum(not t['sensitivity'] for t in review['tokens'] if t['page'] in review['pages']) == 159


def test_distance_reads_the_transcriptions_conventions():
    assert R.distance('kshor', 'kshor') == 0
    assert R.distance('{cto}', 'cto') == 0
    assert R.distance('???cheeo', 'cheeo') == 0                  # '?' matches a unit or nothing
    assert 0 < R.distance('@170;', 'r') < 1                      # a rare glyph another reader spelled with a common letter
    assert R.distance('kshor', 'daiin') > R.LOOSE


def _token(page, locus, k, text, kind):
    return dict(id='%s.%d@%d' % (page, locus, k), page=page, locus=str(locus), text=text, locus_type=kind, group=None, after='.', boundary='certain', flags=[], strict=False, sensitivity=False)


def _page():
    """Ten letters in a column beside ten lines of four words, which repeat. The XML lists the letters first, as f49v's
    does; nothing is assigned."""
    letters = 'orykespdlf'
    words = ['daiin', 'chol', 'qokeedy', 'shedy']
    tokens, xml = [], []
    for k, c in enumerate(letters):
        tokens.append(_token('x', 2 * k + 1, 0, c, 'L0'))
        xml.append(dict(index=len(xml), box=[20, 100 + 40 * k, 34, 124 + 40 * k], text=c))
    for k, c in enumerate(letters):
        line = [words[(k + j) % 4] + c for j in range(4)]
        for j, w in enumerate(line):
            tokens.append(_token('x', 2 * k + 2, j, w, 'P0'))
            xml.append(dict(index=len(xml), box=[50 + 120 * j, 100 + 40 * k, 150 + 120 * j, 130 + 40 * k], text=w))
    tokens.sort(key=lambda t: (int(t['locus']), t['id']))
    review = dict(pages=dict(x=dict(width=800, height=800, median_width=100, median_height=30, xml='x.xml')), tokens=tokens, groups={})
    return review, xml


def test_streams_keep_a_page_listed_out_of_reading_order():
    review, xml = _page()
    res = R.realign_page('x', review, xml)
    assert not res['unlocated'] and len(res['placements']) == len(xml)
    by_text = {w['text']: w['index'] for w in xml}
    by_id = {t['id']: t for t in review['tokens']}
    for p in res['placements']:
        assert p['xml'] == [by_text[by_id[p['tokens'][0]]['text']]]


def test_a_repeated_short_word_goes_by_position():
    """Two lines both hold `ol`: spelling cannot tell the boxes apart, and a kept group on the wrong line is released."""
    tokens = []
    xml = []
    for locus, y in ((1, 100), (2, 150)):
        for j, w in enumerate(['qokaiin%d' % locus, 'chedy%d' % locus, 'ol', 'shedy%d' % locus, 'lkaiin%d' % locus]):
            tokens.append(_token('x', locus, j, w, 'P0'))
            xml.append(dict(index=len(xml), box=[50 + 120 * j, y, 150 + 120 * j, y + 30], text=w))
    review = dict(pages=dict(x=dict(width=800, height=800, median_width=100, median_height=30, xml='x.xml')), tokens=tokens, groups={})
    for idx, t in enumerate(tokens):
        review['groups'][t['id']] = dict(id=t['id'], page='x', tokens=[t['id']], xml_indices=[idx], xml_words=[t['text']], parts=[xml[idx]['box']], box=list(xml[idx]['box']), status='exact', flags=[], display_parts=[])
        t['group'] = t['id']
    ol = [t for t in tokens if t['text'] == 'ol']                  # both tokens were given the first `ol` and the second's box: swap them
    a, b = review['groups'][ol[0]['id']], review['groups'][ol[1]['id']]
    a['xml_indices'], b['xml_indices'], a['parts'], b['parts'], a['box'], b['box'] = b['xml_indices'], a['xml_indices'], b['parts'], a['parts'], b['box'], a['box']
    res = R.realign_page('x', review, xml)
    place = {p['tokens'][0]: p['xml'][0] for p in res['placements']}
    assert xml[place[ol[0]['id']]]['box'][1] == 100 and xml[place[ol[1]['id']]]['box'][1] == 150


def test_the_flag_rules_read_along_the_line():
    page = dict(width=1000, height=1000, median_width=60, median_height=30)
    tokens = [dict(locus='1', text='chol', boundary='certain')]
    down = dict(tokens=['t'], parts=[[100, 100, 130, 160], [100, 160, 130, 200]], box=[100, 100, 130, 200], xml_words=['ch', 'ol'], xml_indices=[3, 4], flags=[])
    assert 'disconnected_parts' in group_flags(down, tokens, page, {}, 0.0)               # left to right they do not join
    down['flags'] = sorted(group_flags(down, tokens, page, {}, 0.0, 90.0))                 # read down the page they do
    assert 'disconnected_parts' not in down['flags'] and 'multiple_boxes' in down['flags']
    resolve_compound(down, 'chol', page, 90.0)
    assert down['resolved'][0]['method'] == 'exact_compound_union'
    assert along_line([0, 0, 10, 20], 0.0) == [0, 0, 10, 20]
    assert along_line([0, 0, 10, 20], 90.0) == pytest.approx([0, -10, 20, 0])
    line = [dict(id=str(k), box=[50 * k, 0, 50 * k + 40, 30], flags=[]) for k in range(3)]
    line[1], line[2] = line[2], line[1]
    line_flags(line, {}, page)
    assert 'order_reversal' in line[0]['flags'] + line[1]['flags'] + line[2]['flags']


def test_ring_and_bowed_line_read_their_level_locally():
    pts = [(500 + 300 * math.cos(a / 10), 500 + 300 * math.sin(a / 10)) for a in range(0, 50)]
    ring = R.fit_ring(pts + [(100.0, 100.0)], 30.0)
    assert ring.kind == 'ring' and abs(ring.r - 300) < 2 and ring.sense == 1.0              # the stray point does not move it
    assert abs(ring.coord((500 + 330, 500))[1] - 30) < 3
    bowed = [(x, 0.0001 * (x - 500) ** 2) for x in range(0, 1001, 50)]
    line = R.fit_straight(bowed, 8.0)
    assert line.n >= 16                                                                     # words past the straight fit rejoin it by their neighbours' level
