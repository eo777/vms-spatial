import numpy as np
import pytest

from conftest import needs_data

from vmsspatial.selector import PoolSpec, SpatialContext, STUDY_SELECTOR, Region
from vmsspatial.measures import Features, measure, score, score_window, mattr, bag_mattr, trailing_distinct, rolling_series, mean_within, window_bounds
from vmsspatial.outcomes import outcomes, word_impact, token_meta
from vmsspatial.jsref import node_available, js_score


def fixture(words, components=None, geometry=None, lines=None):
    return dict(words=words, components=components or {w: list(w) for w in words}, geometry=geometry or [[i * 10, 0, i * 10 + 8, 8] for i in range(len(words))],
                lines=lines or [dict(page='p', locus='1', bifolium='b', start=0, end=len(words))])


def pool_all(n):
    from vmsspatial.selector import Pool
    return Pool(np.arange(n), np.ones(n), n)


def test_spatial_pool_uses_same_page_left_above_geometry_only():
    f = fixture(['outside', 'above', 'angle', 'left', 'target', 'future'])
    f['geometry'] = [[95, 15, 105, 25], [95, 15, 105, 25], [175, 15, 185, 25], [85, 95, 95, 105], [95, 95, 105, 105], [90, 85, 100, 95]]
    f['lines'] = [dict(page='earlier', start=0, end=1), dict(page='p', start=1, end=3), dict(page='p', start=3, end=6)]
    c = SpatialContext(f)
    full = c.pool(4, PoolSpec(angle=45, depth=2, left=3))
    assert list(full.indices) == [1, 2, 3] and full.available == 3
    assert full.weights[1] < full.weights[0]
    assert list(c.pool(4, PoolSpec(angle=0, depth=2, left=3)).indices) == [1, 3]
    assert list(c.pool(4, PoolSpec(angle=0, depth=2, left=0)).indices) == [1]
    assert list(c.pool(4, PoolSpec(angle=0, depth=.5, left=3)).indices) == [3]
    assert list(c.pool(4, PoolSpec(angle=45, depth=2, left=3, weight='uniform', cap=1)).indices) == [3]
    f['geometry'][4] = None
    assert SpatialContext(f).pool(4).missing_target


def test_cone_intersects_rectangles_and_clips_at_depth():
    f = fixture(['left-edge', 'right-edge', 'outside', 'too-high', 'target'])
    f['geometry'] = [[65, 75, 90, 85], [110, 75, 135, 85], [130, 75, 150, 85], [95, 0, 105, 10], [95, 95, 105, 105]]
    f['lines'] = [dict(page='p', start=0, end=4), dict(page='p', start=4, end=5)]
    c = SpatialContext(f)
    c.pages['p']['pitch'] = 20
    assert list(c.pool(4, PoolSpec(depth=2, angle=45)).indices) == [0, 1]
    f['geometry'][0] = [90, 75, 101, 85]
    ray = SpatialContext(f)
    ray.pages['p']['pitch'] = 20
    assert list(ray.pool(4, PoolSpec(depth=2, angle=0)).indices) == [0]


def test_mirror_and_regions():
    f = fixture(['a', 'b', 'c', 'target', 'd', 'e', 'f'])
    f['geometry'] = [[0, 0, 8, 8], [20, 0, 28, 8], [40, 0, 48, 8], [20, 20, 28, 28], [40, 20, 48, 28], [20, 40, 28, 48], [40, 40, 48, 48]]
    f['lines'] = [dict(page='p', start=0, end=3), dict(page='p', start=3, end=5), dict(page='p', start=5, end=7)]
    c = SpatialContext(f)
    c.pages['p']['pitch'] = 20
    c.pages['p']['word_width'] = 8
    up = c.pool(3, PoolSpec(left=3, depth=2, angle=45))
    down = c.pool(3, PoolSpec(left=3, depth=2, angle=45).mirror())
    assert set(up.indices) == {0, 1, 2} and set(down.indices) == {4, 5, 6}
    cand = c.candidates(3, 'all')
    assert set(cand['idx'][Region.lines_above(cand, 1)]) == {0, 1, 2}
    assert set(cand['idx'][Region.lines_below(cand, 1)]) == {5, 6}
    assert set(cand['idx'][Region.same_line(cand)]) == {4}
    sel = c.select(3, lambda cc: Region.cone(cc, depth=2, angle=45, above=False))
    assert set(sel.indices) == {5, 6}


def test_measure_fixtures():
    c = fixture(['ab', 'ab', 'ac', 'ac', 'ab', 'ac'])
    s = measure(Features(c), pool_all(6))
    assert s['h1'] == pytest.approx(1.5) and s['h2'] == pytest.approx(1) and s['components'] == pytest.approx(2)
    assert s['worddiv'] == pytest.approx(.5) and s['js'] == pytest.approx(0) and s['ess'] == pytest.approx(6)
    d = measure(Features(fixture(['ab', 'cd', 'ab', 'cd', 'ab', 'cd'])), pool_all(6))
    assert d['h1'] == pytest.approx(2) and d['h2'] == pytest.approx(0) and d['components'] == pytest.approx(2)
    one = measure(Features(fixture(['aaaa'] * 6)), pool_all(6))
    assert one['h1'] == 0 and one['h2'] == 0 and one['components'] == 1 and one['worddiv'] == 0
    thin = measure(Features(fixture(['a', 'bbbbbb'] * 3)), pool_all(6))
    assert thin['h1'] == pytest.approx(1) and np.isnan(thin['h2'])
    from vmsspatial.selector import Pool
    a = measure(Features(c), Pool(np.arange(6), np.array([1, 2, 1, 2, 1, 2.]), 6))
    b = measure(Features(c), Pool(np.arange(6), np.array([7, 14, 7, 14, 7, 14.]), 6))
    for k in ('h1', 'ess', 'worddiv'):
        assert a[k] == pytest.approx(b[k])


def test_windows_and_impact_small():
    words = ['a', 'a', 'b', 'c', 'd', 'a', 'b', 'b', 'e', 'f', 'f']
    for width in (2, 3, 5, 11):
        for direction in ('backward', 'forward', 'centered'):
            scores, repeated = rolling_series(words, width, direction)
            for i in range(len(words)):
                s, e, full = window_bounds(i, width, direction, len(words))
                expected = words[s:e]
                assert repeated[i] == (1 if expected.count(words[i]) > 1 else 0)
                if full:
                    assert scores[i] == pytest.approx(len(set(expected)) / width)
                else:
                    assert np.isnan(scores[i])
    imp = word_impact(words, 3)
    n = len(words)
    for i in range(n):
        wins = [(s, s + 3) for s in range(max(0, i - 2), min(i, n - 3) + 1)]
        affected = sum(1 for s, e in wins if words[s:e].count(words[i]) > 1)
        assert imp['windows'][i] == len(wins) and imp['affected'][i] == affected
    assert window_bounds(100, 100, 'centered', 500) == (51, 151, True)


@needs_data
def test_strict_pools_hold_strict_tokens_only(strict, strict_study):
    ctx = SpatialContext(strict)                                 # the default bundle: every locus, flat
    sr = strict['spatialReview']['tokens']
    for i in range(0, ctx.n, 97):
        for j in ctx.pool(i).indices:
            assert sr[j]['strict']
    assert ctx.describe()['geometry_kind'] == 'flattened' and ctx.describe()['located'] == 35613
    ctx = SpatialContext(strict_study)                           # the study shape
    assert strict_study['words'][14509] == 'shok' and ctx.pool(14509).missing_target        # shok and or share one coordinate word
    shared = SpatialContext(strict_study, policy='sensitivity').pool(14509)
    assert 14496 in shared.indices and 14497 in shared.indices


@needs_data
def test_bifolium_mattr_is_the_mean_of_the_rolling_series(ms, strict):
    scores, _ = rolling_series(strict['words'], 100, 'backward')
    ranges = ms.bifolium_ranges()
    for node in ms.nodes:
        assert len(ranges[node['id']]) == 1
        s, e = ranges[node['id']][0]
        assert mean_within(scores, ranges[node['id']]) == pytest.approx(mattr(strict['words'][s:e]), abs=1e-12)
    assert np.allclose(np.nan_to_num(trailing_distinct(strict['words']), nan=-1), np.nan_to_num(scores, nan=-1))
    ws = strict['words'][:2000]
    assert 0 < bag_mattr(ws) <= 1 and bag_mattr(ws) >= mattr(ws) - 0.05


@needs_data
@pytest.mark.slow
@pytest.mark.skipif(not node_available(), reason='node not on the PATH')
def test_python_matches_js_reference(strict):
    ctx = SpatialContext(strict)
    mine = score(ctx, STUDY_SELECTOR, Features(strict))
    js = js_score(strict, 'strict')
    for k in ('components', 'h1', 'h2', 'worddiv', 'ess', 'pair_ess'):
        a, b = mine[k].astype(float), js[k]
        assert (np.isfinite(a) == np.isfinite(b)).all(), k
        m = np.isfinite(a)
        assert np.max(np.abs(a[m] - b[m])) < 1e-9, k
    assert np.array_equal(mine['n'], js['n'].astype(int)) and np.array_equal(mine['available'], js['available'].astype(int))
    specs = [PoolSpec(depth=8, left=0, name='above only'), PoolSpec(left=3, depth=8).mirror(), PoolSpec(left=3, depth=8, metric='edge', name='edge'), PoolSpec(left=3, depth=0, name='same line')]
    jsm = js_score(strict, 'strict', configs=[s.as_dict() for s in specs])
    for s in specs:
        t = score(ctx, s, Features(strict), indices=range(0, ctx.n, 5))
        ref = jsm[s.label()]
        idx = np.arange(0, ctx.n, 5)
        for key in ('components', 'worddiv'):
            a, b = t[key][idx], ref[key][idx]
            assert (np.isfinite(a) == np.isfinite(b)).all(), s.label()
            m = np.isfinite(a)
            if m.any():                       # same-line-only pools never reach five pair-bearing words: components stay NaN
                assert np.max(np.abs(a[m] - b[m])) < 1e-9, s.label()
        assert np.array_equal(t['n'][idx], ref['n'][idx].astype(int)), s.label()


@needs_data
def test_sheet_statistics_hold_in_both_orders(ms, strict):
    from vmsspatial.manuscript import Manuscript
    from vmsspatial.measures import group_table
    pages = Manuscript.load('folio')
    a, b = group_table(ms, ms.line_words()), group_table(pages, pages.line_words())
    assert a['groups'].keys() == b['groups'].keys() and a['nodes'].keys() == b['nodes'].keys()
    for g in a['groups']:
        assert a['groups'][g]['tokens'] == b['groups'][g]['tokens']
    same = 0
    for n in ms.nodes:
        assert a['nodes'][n['id']]['tokens'] == b['nodes'][n['id']]['tokens']
        if n['pages'] == [p['folio'] for p in pages.pages if p['node'] == n['id']]:     # the sheet's pages stand in one order in both streams
            assert a['nodes'][n['id']]['mattr'] == pytest.approx(b['nodes'][n['id']]['mattr'], abs=1e-12)
            same += 1
    assert same >= 40
    # a sheet in page order has several stretches; windows stay inside one, as the viewer's row means do
    node, _, bstart, bend = token_meta(pages, pages.line_words())
    ranges = pages.bifolium_ranges()
    assert len(ranges['A:1-8']) == 2 and {(bstart[s], bend[s]) for s, e in ranges['A:1-8']} == set(ranges['A:1-8'])
    assert all(node[s] == 'A:1-8' and node[e - 1] == 'A:1-8' for s, e in ranges['A:1-8'])
    words = pages.words()
    scores, _ = rolling_series(words, 100, 'backward')
    m = mean_within(scores, ranges['A:1-8'])
    assert 0.3 < m < 1
    by_hand = [scores[i] for s, e in ranges['A:1-8'] for i in range(s + 99, e)]
    assert m == pytest.approx(sum(by_hand) / len(by_hand))
