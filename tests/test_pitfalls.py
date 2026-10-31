"""The controls that the 28 October 2026 reviews required, as functions (docs/PITFALLS.md)."""
import warnings

import numpy as np
import pytest

from conftest import needs_data, needs_controls

from vmsspatial.selector import PoolSpec, SpatialContext, STUDY_SELECTOR, WIDTH_NEUTRAL_SELECTOR, CURSOR_SELECTOR, LINES_ABOVE_ONLY
from vmsspatial.measures import Features, score, measure
from vmsspatial.outcomes import outcomes, token_meta, repeat_outside_pool
from vmsspatial.stats import standard_contrasts, format_contrasts, baseline_summary, shuffle_rank, cohort_masks
from vmsspatial.shuffles import size_matched, baseline, check_typesetting, shuffled_in_boxes, LayoutError
from vmsspatial.bundle import make_bundle
from vmsspatial.jsref import node_available, js_score


def two_targets():
    """A short and a long target with the same left neighbour on one line."""
    f = dict(words=['abcd', 'xy', 'abcd', 'longword', 'u', 'v'], components={w: list(w) for w in ['abcd', 'xy', 'longword', 'u', 'v']},
             geometry=[[0, 0, 40, 10], [50, 0, 70, 10], [0, 20, 40, 30], [50, 20, 130, 30], [0, 40, 10, 50], [20, 40, 30, 50]],
             lines=[dict(page='p', locus='1', bifolium='b', start=0, end=2), dict(page='p', locus='2', bifolium='b', start=2, end=4), dict(page='p', locus='3', bifolium='b', start=4, end=6)])
    return f


def test_width_neutral_distance_does_not_read_the_target_length():
    c = SpatialContext(two_targets())
    c.pages['p']['word_width'] = 20
    short = c.pool(1, PoolSpec(left=5, depth=0))
    long_ = c.pool(3, PoolSpec(left=5, depth=0))
    assert short.weights[0] > long_.weights[0]                          # centre metric: the short target's neighbour is nearer
    es, el = c.pool(1, PoolSpec(left=5, depth=0, metric='edge')), c.pool(3, PoolSpec(left=5, depth=0, metric='edge'))
    assert es.weights[0] == pytest.approx(el.weights[0])                # edge metric: the same gap gives the same weight
    assert es.weights[0] == pytest.approx(1 / (1 + 1.5) ** 2)            # gap 10 = half a word width, plus one


def test_cursor_target_fixes_the_window_before_the_width_is_known():
    c = SpatialContext(two_targets())
    c.pages['p']['word_width'] = 20
    assert list(c.target_box(3, CURSOR_SELECTOR)) == [50, 20, 70, 30]
    cs, cl = c.pool(1, PoolSpec(left=5, depth=0, target='cursor')), c.pool(3, PoolSpec(left=5, depth=0, target='cursor'))
    assert cs.weights[0] == pytest.approx(cl.weights[0])
    assert list(c.target_box(3, STUDY_SELECTOR)) == [50, 20, 130, 30]
    assert list(c.target_box(3, STUDY_SELECTOR.mirror().cursor())) == [110, 20, 130, 30]


def test_repeat_outside_pool():
    words = ['a', 'b', 'a', 'c', 'a']
    pools = {0: [], 1: [0], 2: [0, 1], 3: [2], 4: [2, 3]}
    r = repeat_outside_pool(words, lambda i: np.array(pools[i]), w=99)
    assert r.tolist() == [1, 0, 1, 0, 1]                                 # token 2: its twin at 0 is in the pool, the one at 4 is not
    r2 = repeat_outside_pool(words, lambda i: np.array(pools[i]), w=1)
    assert r2.tolist() == [0, 0, 0, 0, 0]


def test_shuffle_rank_reports_excess_and_permutation_p():
    r = shuffle_rank([0.01, 0.02, 0.03, 0.04], 0.035)
    assert r['rank'] == 3 and r['of'] == 4 and r['p_one_sided'] == pytest.approx(2 / 5) and r['excess'] == pytest.approx(0.01)


def test_old_recorded_box_shuffle_warns(ms):
    with pytest.warns(DeprecationWarning):
        shuffled_in_boxes(ms, np.zeros(ms.n_tokens, int), np.random.default_rng(1))


@needs_data
def test_recorded_baseline_keeps_the_geometry_and_warns_without_kind(ms_study, strict_study):
    ms, strict = ms_study, strict_study
    lines = [strict['words'][L['start']:L['end']] for L in strict['lines']]
    gen = baseline(ms, lines, strict['geometry'], 'recorded', k=2)
    sl, sg = next(gen)
    assert sg == strict['geometry'] and sl != lines
    assert [len(' '.join(a)) for a in sl] == [len(' '.join(b)) for b in lines]
    with pytest.raises(ValueError):
        next(baseline(ms, lines, strict['geometry'], 'synthetic', k=1))
    with pytest.warns(UserWarning):
        make_bundle(ms, lines, strict['geometry'], 'zattera')
    b = make_bundle(ms, lines, strict['geometry'], 'zattera', geometry_kind='recorded')
    assert b['geometry_kind'] == 'recorded' and SpatialContext(b).describe()['geometry_kind'] == 'recorded'


@needs_data
def test_typesetting_guard(ms_study, sensitivity_study):
    ms, sensitivity = ms_study, sensitivity_study
    from vmsspatial.geometry import line_frames
    from vmsspatial.manuscript import tokenize
    frames = line_frames(sensitivity, ms)
    tok = tokenize(ms)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        old = shuffled_in_boxes(ms, np.cumsum(tok['since_par'] == 0), np.random.default_rng(1))
    with pytest.raises(LayoutError):
        check_typesetting(ms, frames, old, sensitivity['geometry'])
    ok = check_typesetting(ms, frames, ms.line_words(), sensitivity['geometry'], max_off_share=0.1)
    assert ok['ok']


@needs_data
@pytest.mark.slow
def test_standard_contrasts_report_every_measure_control_and_cohort(ms_study, strict_study):
    ms, strict = ms_study, strict_study                           # the published controls of the 2026 study, by explicit option
    ctx = SpatialContext(strict)
    feat = Features(strict)
    tab = score(ctx, STUDY_SELECTOR, feat)
    above = score(ctx, LINES_ABOVE_ONLY, feat)
    lines = ms.line_words()
    node, group, bstart, bend = token_meta(ms, lines)
    out = outcomes(strict['words'], bstart, bend)
    res = standard_contrasts(tab, out, node, strict['words'], out['full'], line_words=lines, above_table=above, reps=0)
    assert set(res) == {'all', 'interior-A', 'interior-B'}
    for c in res.values():
        assert set(c) >= {'n', 'mean_pool', 'components', 'h2', 'worddiv'}
        for m in ('components', 'h2', 'worddiv'):
            assert set(c[m]) == {'raw', 'length', 'length_pool'} and np.isfinite(c[m]['length_pool']['diff'])
    assert res['interior-A']['n'] < res['all']['n']
    text = format_contrasts(res, 'test')
    assert 'inside length x pool' in text
    # the joint control keeps a positive residual on the manuscript
    assert res['all']['components']['length_pool']['diff'] > 0 and res['all']['h2']['length_pool']['diff'] > 0.02
    summary = baseline_summary(res, [res, res])
    assert summary['all']['h2']['length_pool']['rank'] == 0 and summary['all']['h2']['length_pool']['excess'] == pytest.approx(0)


@needs_data
@pytest.mark.slow
@pytest.mark.skipif(not node_available(), reason='node not on the PATH')
def test_width_neutral_and_cursor_match_the_js(strict):
    ctx = SpatialContext(strict)
    feat = Features(strict)
    specs = [WIDTH_NEUTRAL_SELECTOR, CURSOR_SELECTOR, PoolSpec(metric='edge', target='cursor', name='both')]
    js = js_score(strict, 'strict', configs=[s.as_dict() for s in specs])
    idx = np.arange(0, ctx.n, 7)
    for s in specs:
        t = score(ctx, s, feat, indices=idx)
        ref = js[s.label()]
        for key in ('components', 'h2', 'worddiv'):
            a, b = t[key][idx], ref[key][idx]
            assert (np.isfinite(a) == np.isfinite(b)).all(), (s.label(), key)
            m = np.isfinite(a)
            assert np.max(np.abs(a[m] - b[m])) < 1e-9, (s.label(), key)
        assert np.array_equal(t['n'][idx], ref['n'][idx].astype(int)), s.label()
    # the viewer's own sourcePool with the same options (the default path of the reference scorer)
    plain = js_score(strict, 'strict')
    mine = score(ctx, STUDY_SELECTOR, feat, indices=idx)
    m = np.isfinite(mine['components'][idx])
    assert np.max(np.abs(mine['components'][idx][m] - plain['components'][idx][m])) < 1e-9
