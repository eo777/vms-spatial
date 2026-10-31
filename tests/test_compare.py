"""The comparison model: exact primitives on toy rectangles, the selection and alignment rules, the bifolium slots and
the joint value, the documented example and the first-line scan."""
import json
from collections import Counter

import pytest

from conftest import needs_data

from vmsspatial import compare as C
from vmsspatial.frames import FrameError


def _unit(text, rect, line=0, anchor=False, uid=0):
    return dict(id=uid, text=text, atoms=C.atoms(text), rect=list(rect), line=line, anchor=anchor, clean=True, flags=[])


def test_primitives():
    assert C.union_area([[0, 0, 10, 10], [5, 0, 15, 10]]) == 150.0
    assert C.union_area([[0, 0, 10, 10], [0, 0, 4, 4]]) == 100.0 and C.union_area([]) == 0.0
    assert C.union_area([[0, 0, 40, 20], [40, 0, 100, 20]]) == C.union_area([[0, 0, 100, 20]])        # one box and two adjoining boxes occupy the same area
    assert C.intersection([0, 0, 10, 10], [10, 0, 20, 10]) is None and C.intersection([0, 0, 10, 10], [5, 5, 20, 20]) == [5, 5, 10, 10]
    assert C.edit(['ch', 'o', 'l'], ['sh', 'o', 'l']) == 1 and C.similarity([], []) == 1.0 and C.similarity(['a'], []) == 0.0
    assert C.atoms('cheol dy') == ['ch', 'e', 'o', 'l', 'd', 'y'] and C.atoms('{c@123;h}y') == ['{c@123;h}', 'y']
    s = C.spatial_similarity([_unit('cho', [0, 0, 10, 10]), _unit('dy', [10, 0, 20, 10])], [_unit('chody', [0, 0, 20, 10])])
    assert s['similarity'] == 1.0 and s['edits'] == 0
    assert C.spatial_similarity([_unit('cho', [0, 0, 10, 10]), _unit('dy', [10, 0, 20, 10])], [_unit('chody', [100, 0, 120, 10])])['similarity'] == 0.0
    assert C.spatial_similarity([], [_unit('a', [0, 0, 1, 1])])['similarity'] is None
    assert C.x_dice([_unit('cho', [0, 0, 10, 10]), _unit('dy', [10, 0, 20, 10])], [_unit('chody', [0, 0, 20, 10])]) == 1.0
    assert C.js_distance(Counter({('a', 'b'): 1}), Counter({('c', 'd'): 1})) == 1.0 and C.js_distance(Counter({('a', 'b'): 1}), Counter({('a', 'b'): 2})) == 0.0
    assert C.js_distance(Counter(), Counter({('a', 'b'): 1})) is None
    f = C.line_features('daiin ol chedy')
    assert f['plain'] == ['d', 'a', 'i', 'i', 'n', 'o', 'l', 'ch', 'e', 'd', 'y'] and f['toolkit'][('d', 'a')] == pytest.approx(1 / 3) and f['joined'][('n', 'o')] == 1.0 and f['boundaries'][('n', '<boundary>')] == 1.0


def test_measure_units_and_details():
    A = [_unit('a', [0, 0, 10, 10], 0, anchor=True, uid=0), _unit('chol', [20, 0, 40, 10], 0, uid=1), _unit('daiin', [0, 20, 30, 30], 1, uid=2)]
    B = [_unit('a', [0, 0, 10, 10], 0, anchor=True, uid=0), _unit('chor', [25, 0, 45, 10], 0, uid=1), _unit('dain', [0, 20, 30, 30], 1, uid=2)]
    m = C.measure_units(A, B, 40.0, 20.0)
    assert m['units_a'] == m['units_b'] == 3                                                       # the first box is scored like any other
    shared = 10 * 10 + 15 * 10 + 30 * 10
    assert m['dice'] == pytest.approx(2 * shared / (100 + 200 + 300 + 100 + 200 + 300))
    # atoms are lossless EVA atoms: chol/chor = 1 - 1/3, daiin/dain = 1 - 1/5 ('ii' stays two atoms); both directions, weighted by the intersection areas
    assert m['local_segment_similarity'] == pytest.approx((100 * 2 + 150 * (2 / 3) * 2 + 300 * 0.8 * 2) / 1100)
    assert m['nearby_similarity'] == pytest.approx((1 + 2 / 3 + 0.8) / 3)
    same = C.measure_units(A, B, 40.0, 20.0, same_row=True)
    assert same['dice'] == pytest.approx(m['dice'])                                                 # every overlap here is within one row
    assert C.measure_units(A, [], 40.0, 20.0)['dice'] is None
    sel = lambda units: dict(chosen=units, all=units, W=40.0, H=20.0, available=True, frame='recorded', warp='recorded', expected=2)
    d = C.details(sel(A), sel(B))
    assert len(d['direct']) == 6 and len(d['connected']) == 3 and len(d['nearby']) == 3 and d['connected'][1]['text_a'] == 'chol' and d['connected'][1]['edits'] == 1
    rows = C.per_line(sel(A), sel(B))
    assert [r['line'] for r in rows] == [1, 2] and rows[1]['dice'] == 1.0
    with pytest.raises(FrameError):
        C.measure(dict(sel(A), warp='flat'), sel(B))


def test_polygons_and_ranking():
    rows = [dict(line=0, locus='1', position=0, rect=[0, 0, 100, 20], cy=10), dict(line=1, locus='2', position=1, rect=[0, 30, 80, 50], cy=40), dict(line=3, locus='4', position=3, rect=[0, 90, 80, 110], cy=100)]
    polys = C.paragraph_polygons(rows, 30.0)
    assert len(polys) == 2 and polys[0]['lines'] == [0, 1] and polys[1]['lines'] == [3]
    assert polys[0]['points'][0] == [0, 0] and [100, 25] in polys[0]['points']                        # the join lies halfway between 20 and 30
    rows = [dict(id='p:%d' % k, dice_current=v[0], js_joined=v[1]) for k, v in enumerate([(0.8, 0.5), (0.7, 0.4), (0.8, 0.6), (0.6, 0.4), (0.9, 0.9)])]
    r = C.rank_rows(rows)
    # Dice ranks (descending, ties share): p4 1, p0 2, p2 2, p1 4, p3 5; JS ranks (ascending): p1 1, p3 1, p0 3, p2 4, p4 5
    assert [x['id'] for x in r] == ['p:0', 'p:1', 'p:2', 'p:3', 'p:4']
    assert [x['both_worst'] for x in r] == [3, 4, 4, 5, 5] and [x['both_sum'] for x in r] == [5, 5, 6, 6, 6]
    assert {x['id']: x['overlap_rank'] for x in r} == {'p:4': 1, 'p:0': 2, 'p:2': 2, 'p:1': 4, 'p:3': 5}
    assert [x['id'] for x in C.rank_rows(rows, 'js')][:2] == ['p:1', 'p:3']
    assert [x['id'] for x in C.rank_rows(rows, 'dice_current')][0] == 'p:4'
    assert C.face_slots('inner', 'A') == ['Av'] and C.face_slots('both', 'B') == ['Br', 'Bv']
    with pytest.raises(ValueError):
        C.face_slots('top')
    assert C.joint([])['complete'] is False


@needs_data
def test_selection_rules(ms, sensitivity_recorded):
    data = C.prepare(sensitivity_recorded, ms, baseline='glyph')
    assert len(data['pages']) == 227 and sum(len(p['units']) for p in data['pages'].values()) == 37478
    assert sum(1 for p in data['pages'].values() for b in p['blocks'] if b['key'][0] == 'p' and b['key'] != 'page') == 740          # the canonical paragraphs
    assert data['pages']['f75r']['H'] == 24.0 and data['pages']['f75r']['W'] == 57.0
    assert data['pages']['f20v']['slot'] == 'Av' and data['pages']['f21r']['slot'] == 'Br' and data['pages']['f21v']['slot'] == 'Bv'
    f7r = data['pages']['f7r']
    start = C.select(data, 'f7r', 'p2', 'all', 'flat', 'starts')
    position = C.select(data, 'f7r', 'p2', 'all', 'flat', 'page')
    assert len(start['chosen']) == len(position['chosen']) and sum(u['anchor'] for u in start['chosen']) == 1 and sum(u['anchor'] for u in position['chosen']) == 0
    delta = [a - b for a, b in zip(start['chosen'][0]['rect'], position['chosen'][0]['rect'])]
    for u, v in zip(start['chosen'], position['chosen']):
        assert all(abs(a - b - d) < 1e-9 for a, b, d in zip(u['rect'], v['rect'], delta))        # paragraph-position mode changes only the common translation
    a = C.select(data, 'f20v', 'opening', 3, 'flat', 'starts', 'pixels')
    b = C.select(data, 'f20v', 'opening', 3, 'flat', 'starts', 'body_height')
    factor = 30.0 / data['pages']['f20v']['H']
    assert b['H'] == 30.0 and all(abs(x * factor - y) < 1e-9 for x, y in zip(a['chosen'][0]['rect'], b['chosen'][0]['rect']))
    assert all(u['line'] < 3 for u in a['chosen']) and a['complete']
    whole = C.select(data, 'f20v', 'p1', 3, extent='whole')
    assert whole['block']['key'] == 'page' and len(whole['chosen']) == len(data['pages']['f20v']['units'])
    assert C.select(data, 'f116v', 'page')['available'] is False                                      # two tokens, no rectangles: no anchor, no score
    assert data['pages']['fRos']['geometry_kind'] == 'detected' and C.select(data, 'fRos', 'page')['frame'] == 'detected'
    rec, flat = C.select(data, 'f20v', 'opening', 1, 'recorded'), C.select(data, 'f20v', 'opening', 1, 'flat')
    assert [u['rect'][0] for u in rec['chosen']] == pytest.approx([u['rect'][0] for u in flat['chosen']])      # x is unchanged by the warp
    assert rec['warp'] == 'recorded' and flat['warp'] == 'flat'
    with pytest.raises(FrameError):
        C.measure(rec, flat)
    rows = C.sheet_rows(data, 'C:20-21', 'B:10-15', 'inner')
    assert [(r['page_a'], r['page_b']) for r in rows] == [('f20v', 'f10v'), ('f21r', 'f15r')]
    assert [(r['page_a'], r['page_b']) for r in C.sheet_rows(data, 'C:20-21', 'B:10-15', 'outer')] == [('f21v', 'f15v'), ('f20r', 'f10r')]
    panels = C.sheet_rows(data, 'N:85-86', 'B:10-15', 'outer')
    assert panels[0]['page_a'] is None and panels[1]['page_a'] is None                                   # foldout panels need an explicit choice
    assert C.sheet_rows(data, 'N:85-86', 'B:10-15', 'outer', {'Bv': dict(a='f86v3')})[0]['page_a'] == 'f86v3'
    res = C.compare_sheets(data, 'C:20-21', 'B:10-15', 'inner', 3)
    j = res['joint']
    assert j['complete'] and j['mean']['dice'] == pytest.approx((res['rows'][0]['result']['dice'] + res['rows'][1]['result']['dice']) / 2)
    assert j['minimum']['dice'] == pytest.approx(min(r['result']['dice'] for r in res['rows']))
    assert C.joint([res['rows'][0], dict(slot='Br')])['mean']['dice'] is None
    rl = C.reading_lines(C.select(data, 'f20v', 'page', extent='whole'))
    assert len(rl) == len(data['pages']['f20v']['lines']) and rl[0]['units'][0]['text'] == 'faiis' and rl[0]['units'][0]['anchor']
    lay = C.layout(data, 'f75r')
    assert lay['available'] and lay['stats']['paragraphs'] == 4 and any(f['type'] == 'break' for f in lay['features']) and all(p['polygons'] for p in lay['paragraphs'])
    o = C.orders(ms)
    assert o['folio']['pages'][:2] == ['f1r', 'f1v'] and len(o['path1']['pages']) == 227 and o['bifolia']['pages'][:3] == ['f1r', 'f1v', 'f8r'] and 'quire' not in o


@needs_data
def test_block_without_a_first_line_box_is_drawn_but_not_scored(ms, sensitivity_recorded):
    data = C.prepare(sensitivity_recorded, ms, baseline='glyph', table=False)
    page = data['pages']['f20v']
    blanked = dict(data, pages=dict(data['pages'], f20v=dict(page, units=[u for u in page['units'] if u['line'] != 0])))
    s = C.select(blanked, 'f20v', block='opening', cutoff=3)
    assert s['available'] is False and s['fallback_line'] == 1
    assert max(abs(v) for v in s['origin']) > 100                        # not the page's own corner
    assert abs(next(u for u in s['all'] if u['line'] == 1)['baseline']) < 40
    fine = C.select(data, 'f20v', block='opening', cutoff=3)
    assert fine['available'] is True and fine['fallback_line'] is None
    assert C.measure(s, fine)['dice'] is None                            # still not scored


@needs_data
@pytest.mark.slow
def test_documented_example(ms, sensitivity_recorded, tmp_path):
    """The worked example of docs/COMPARE.md and the README quickstart, line by line: the documented path is the
    tested path."""
    c = C.Comparison(ms, sensitivity_recorded, baseline='glyph')          # the docs call Comparison() with the defaults; the fixtures stand in for the load
    assert '227 pages' in c.describe() and 'anchors glyph' in c.describe()
    pair = c.pages('f20v', 'f21r', cutoff=3, align='starts')
    scores = pair.scores()
    assert set(scores) == {'dice', 'local_segment_similarity', 'nearby_similarity', 'units_a', 'units_b'}
    assert scores['dice'] == pytest.approx(0.7112958720104641) and scores['units_a'] == 29 and scores['units_b'] == 25
    segments = pair.segments()
    assert segments and {'text_a', 'text_b', 'similarity', 'edits', 'lines_a', 'lines_b', 'clean'} <= set(segments[0])
    assert len(pair.segments('direct')) >= len(segments) and set(pair.segments('all')) == {'direct', 'connected', 'nearby'}
    lines = pair.lines()
    assert [r['line'] for r in lines] == [1, 2, 3] and all('dice' in r for r in lines)
    geo = pair.overlay_geometry()
    assert geo['frame'] == 'recorded' and geo['warp'] == 'flat' and len(geo['a']) == 43 and len(geo['b']) == 39 and geo['a'][0]['anchor']
    d = pair.describe()
    assert 'cutoff 3' in d and 'align starts' in d and 'flat warp' in d and 'Dice 0.711' in d and 'data' in d
    out = pair.to_json(tmp_path / 'pair.json')
    saved = json.loads((tmp_path / 'pair.json').read_text(encoding='utf-8'))
    assert saved['scores']['dice'] == pytest.approx(scores['dice']) and saved['settings']['cutoff'] == 3 and saved['geometry']['warp'] == 'flat'
    sheet = c.bifolia('C:20-21', 'B:10-15', face='inner', cutoff=3)
    assert sheet.joint['complete'] and sheet.joint['mean']['dice'] == pytest.approx(0.630, abs=5e-4)
    assert sheet.joint['mean']['local_segment_similarity'] == pytest.approx(0.247, abs=5e-4) and sheet.joint['minimum']['dice'] == pytest.approx(0.587, abs=5e-4)
    assert 'inner face' in sheet.describe() and all(p is not None for p in sheet.pairs())
    comp = c.composite(['f30r', 'f37r', 'f16r'], align='page')
    assert len(comp.selections) == 3 and len(comp.pairwise()) == 3 and 'align page' in comp.describe() and comp.overlay_geometry()['pages'][0]['folio'] == 'f30r'
    drift = c.drift('f21v')
    assert drift['n'] == 7 and drift['angle'] < 0 and drift['coordinates'] == 'recorded'                   # the workstream's check: seven qualifying lines, falling left
    assert c.drift('f112v')['angle'] > 0 and c.drift('f86v3')['unavailable'].startswith('quarantined') and c.drift('f116v')['angle'] is None
    flat = c.drift('f21v', 'flat')
    assert flat['n'] == 7 and flat['angle'] != drift['angle'] and 'drift' in C.describe(flat)
    assert C.drift_guide(drift, 10, 0, 100)[1][1] == pytest.approx(drift['slope'] * 1000) and C.drift_guide(dict(angle=None), 1) is None
    split = pair.split(0)
    assert split['frame'] == 'display' and split['indices'][0] == 0 and split['start'] < split['row_tops'][0] < split['row_tops'][1] < split['end']
    moved = split['selections'][0]['all'][0]
    assert moved['rect'][0] == pair.a['all'][0]['rect'][0] and moved['rect'][2] == pair.a['all'][0]['rect'][2]             # x unchanged, only a vertical translation
    assert pair.scores() == scores                                                                            # the split changed nothing measured
    try:
        import matplotlib
        matplotlib.use('Agg')
        ax = pair.plot()
        assert 'Dice' in ax.get_title(loc='left') and len(ax.patches) > 20
        ax = comp.plot()
        assert '3 blocks' in ax.get_title(loc='left')
        matplotlib.pyplot.close('all')
    except ImportError:
        pass


@needs_data
@pytest.mark.slow
def test_first_line_scan_counts(ms, sensitivity_recorded):
    data = C.prepare(sensitivity_recorded, ms, baseline='glyph')
    scan = C.first_line_scan(data, 1)
    assert len(scan['pages']) == 205 and len(scan['pairs']) == 20910 and scan['eligible_pairs'] == 20100
    for scope, (sheets, n) in (('pages', (None, 20100)), ('inner', (38, 703)), ('outer', (39, 741)), ('both', (35, 595))):
        r = C.rank_pairs(data, 'all', 1, scope)
        assert isinstance(r, C.Records) and (r.meta['sheets'], len(r)) == (sheets, n), scope
        assert r['sheets'] == sheets and r['rows'] == list(r)                                       # the older dict-style reads
        assert all(r[i]['both_worst'] <= r[i + 1]['both_worst'] for i in range(len(r) - 1))
    sp = C.rank_pairs(data, 'all', 1, 'pages', 'spatial')[0]
    assert {sp['a'], sp['b']} == {'f7v', 'f22r'}
    js = C.rank_pairs(data, 'all', 1, 'pages', 'js')[0]
    assert {js['a'], js['b']} == {'f78v', 'f80v'}
    within = C.rank_pairs(data, 'sheet', 1)
    assert within and all(r['pages_a'][0]['node'] == r['pages_b'][0]['node'] for r in within)
    herbal = C.Comparison(data=data).rank(pool='herbal_a', containing='f20v')
    assert herbal and all('f20v' in (r['a'], r['b']) for r in herbal) and 'herbal_a' in herbal.describe()
    compact = herbal.compact(5)
    assert len(compact) == 5 and set(compact[0]) >= {'a', 'b', 'dice_current', 'js_joined', 'overlap_rank', 'js_rank'}
    import tempfile, csv, os
    path = os.path.join(tempfile.mkdtemp(), 'herbal.csv')
    herbal.to_csv(path, top=10)
    with open(path, encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10 and rows[0]['a'] and float(rows[0]['dice_current']) >= 0
