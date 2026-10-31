import numpy as np
import pytest

from conftest import needs_data, needs_controls

from vmsspatial.stats import quintile_contrast, contrast_strata, three_contrasts, lobo_linear, paired_contrast, shuffle_rank, interior_mask, pool_size_tertiles


def synthetic(n=4000, bifolia=20, effect=0.1, seed=1):
    rng = np.random.default_rng(seed)
    bif = np.repeat(np.arange(bifolia), n // bifolia).astype(object)
    metric = rng.normal(size=n)
    outcome = (rng.random(n) < 0.3 - effect * (metric > 0)).astype(float)
    return metric, outcome, bif


def test_quintile_contrast_sign_and_interval():
    metric, outcome, bif = synthetic()
    r = quintile_contrast(metric, outcome, bif, np.ones(len(bif), bool), reps=500)
    assert r['bifolia'] == 20 and r['diff'] > 0.05 and r['ci'][0] > 0
    null = quintile_contrast(metric, np.random.default_rng(2).random(len(bif)), bif, np.ones(len(bif), bool), reps=500)
    assert null['ci'][0] < 0 < null['ci'][1]


def test_strata_and_lobo():
    metric, outcome, bif = synthetic()
    strata = np.random.default_rng(3).integers(0, 3, len(bif))
    r = contrast_strata(metric, outcome, bif, strata, np.ones(len(bif), bool), reps=200)
    assert r['diff'] > 0.05 and r['covered'] > 3000
    words = ['x' * int(k) for k in np.random.default_rng(4).integers(2, 9, len(bif))]
    t = three_contrasts(metric, outcome, bif, words, np.random.default_rng(5).integers(5, 60, len(bif)), np.ones(len(bif), bool))
    assert set(t) == {'raw', 'length', 'length_pool'}
    assert lobo_linear(metric, outcome, bif, np.ones(len(bif), bool)) > 0
    p = paired_contrast(metric, np.random.default_rng(6).normal(size=len(bif)), outcome, bif, np.ones(len(bif), bool), reps=200)
    assert p['a'] > p['b'] and p['diff'] == pytest.approx(p['a'] - p['b'])
    assert shuffle_rank([0.1, 0.2, 0.3], 0.25)['rank'] == 2
    assert set(np.unique(pool_size_tertiles(np.arange(100), np.ones(100, bool)))) <= {0, 1, 2}


def test_interior_mask():
    lines = [['a', 'b', 'c'], ['d'], ['e', 'f', 'g', 'h']]
    m = interior_mask(lines, np.full(8, 20))
    assert m.tolist() == [False, True, False, False, False, True, True, False]


@needs_data
@pytest.mark.slow
def test_layout_shuffles_keep_the_layout(ms_study, sensitivity_study):
    ms, sensitivity = ms_study, sensitivity_study                 # the study's published layout numbers
    from vmsspatial.geometry import line_frames
    from vmsspatial.shuffles import variants, VARIANT_NAMES, repeated, words_in_units
    from vmsspatial.layout_check import overlaps, width_error
    frames = line_frames(sensitivity, ms)
    V = variants(ms, frames, names=[VARIANT_NAMES[1], VARIANT_NAMES[9]])
    v = V[VARIANT_NAMES[1]]
    assert v['carried'] == 797 and overlaps(v['geometry'], v['lines'], ms) == 1391        # the 48 rotated lines have no frame and are not typeset
    assert width_error(ms, frames, v['lines'], v['geometry'])['off_1p5'] < 0.002
    assert abs(v['moved'] / ms.n_tokens - 0.785) < 0.01
    perm, _ = words_in_units(ms, ms.paragraph_of_line(), np.random.default_rng(7))
    assert [len(' '.join(a)) for a in perm] == [L['chars'] for L in ms.lines]              # size-matched: character counts kept before typesetting
    assert sorted(w for ws in perm for w in ws) == sorted(ms.words())
    lf = V[VARIANT_NAMES[9]]
    assert lf['carried'] == 0 and lf['cw_ratio'] is not None and np.median(np.abs(np.log(lf['cw_ratio']))) < 0.05
    two = list(repeated(ms, frames, k=2))
    assert len(two) == 2 and two[0][0] != two[1][0]


@needs_data
@needs_controls
def test_controls(ms_study, sensitivity_study):
    ms, sensitivity = ms_study, sensitivity_study                 # controls are typeset into the study text's recorded line frames
    from vmsspatial.controls import markov_text, fill_by_chars, laid_in, native_lines, ref_words, read_stream, stream_seeds, STREAMS
    rng = np.random.default_rng(1)
    mk = markov_text(ms, 'section', rng)
    assert [len(ws) for ws in mk] != [len(L['words']) for L in ms.lines]                 # filled to the character budget, not the word count
    assert all(len(' '.join(ws)) <= max(L['chars'], len(ws[0])) for ws, L in zip(mk, ms.lines))
    assert set(w for ws in mk for w in ws) <= set(ms.words())
    assert [len(ws) for ws in markov_text(ms, 'section', rng, fill='words')] == [len(L['words']) for L in ms.lines]
    words = ref_words('de_gart_augsburg1487')
    assert len(words) > 50000
    box, start = laid_in(ms, words, rng)
    assert [len(ws) for ws in box] == [len(L['words']) for L in ms.lines]
    again, start2 = laid_in(ms, words, None, start=start)
    assert again == box and start2 == start                                   # a passage is reproducible from its start
    line, lstart = fill_by_chars(ms, words, rng)
    assert all(len(' '.join(ws)) <= max(L['chars'], len(ws[0])) for ws, L in zip(line, ms.lines))
    from vmsspatial.controls import build_control
    from vmsspatial.geometry import line_frames
    frames = line_frames(sensitivity, ms)
    with pytest.warns(UserWarning):                                                      # the one-word-per-box diagnostic announces itself
        lw, geom, comp, info = build_control(ms, sensitivity, 'prose_box', 'de_gart_augsburg1487', start=1000, frames=frames)
    assert info['geometry_kind'] == 'recorded' and info['start'] == 1000 and comp == 'letters' and 'caveat' in info
    for kind, name in (('markov', 'whole'), ('prose', 'de_gart_augsburg1487'), ('prose_native', 'de_gart_augsburg1487')):
        lw, geom, comp, info = build_control(ms, sensitivity, kind, name, frames=frames)   # every control is typeset and checked
        assert info['geometry_kind'] == 'synthetic' and info['typesetting']['ok'] and info['typesetting']['off_1p5'] < 0.01, (kind, info['typesetting'])
        assert sum(1 for g in geom if g) > 0.95 * sum(len(ws) for ws in lw)
    nl = native_lines('de_gart_augsburg1487')
    fragments = sum(1 for ws in nl if len(ws) == 1 and len(ws[0]) <= 2)
    assert fragments < 0.02 * len(nl) and 4 < np.mean([len(ws) for ws in nl]) < 7           # OCR fragments dropped; wraps may leave a few
    timm = read_stream(STREAMS['timm'][1][0])
    assert len(timm) == 4130 and sum(len(l) for l in timm) > 30000
    seeds = stream_seeds('noinnov_spatial', 2)
    assert len(seeds) == 2 and len(seeds[1]) == 4130
