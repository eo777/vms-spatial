"""Glyph-aware baselines: known descender and ascender offsets are recovered on a synthetic page; on the manuscript
the gallows raise the top, q and y lower the bottom, and the glyph baseline has the smallest within-line residual."""
import numpy as np
import pytest

from conftest import needs_data

from vmsspatial.baselines import glyph_effects, word_baselines, baseline_rms, effects_table, line_xheights

DESC = {'q': 0.30, 'y': 0.25}                 # bottom pushed down, in H
ASC = {'k': -0.40, 't': -0.35}                # top pushed up, in H
VOCAB = ['daiin', 'ol', 'chol', 'qokedy', 'otal', 'shedy', 'chor', 'qol', 'dar', 'okal', 'ytar', 'cheol', 'sal', 'qotedy', 'oldar', 'chedy', 'aiin', 'kar', 'ar', 'ory']


def _page(n_lines=16, words=14, seed=5, noise=0.03):
    """Straight sloped lines of EVA words; box bottom = baseline + descender offset, box top = baseline - 1 H + ascender offset."""
    rng = np.random.default_rng(seed)
    H = 30.0
    tokens, lines, geometry, truth = [], [], [], []
    ms_lines = []
    for l in range(n_lines):
        slope = rng.uniform(-0.03, 0.03)
        base0 = 200 + 70 * l
        x = 150 + np.cumsum(rng.uniform(55, 75, words))
        start = len(tokens)
        for k in range(words):
            w = VOCAB[rng.integers(len(VOCAB))]
            width = 8 * len(w) + 10
            xc = x[k]
            base = base0 + slope * (xc - 500)
            desc = sum(DESC.get(c, 0.0) for c in set(w)) * H
            asc = sum(ASC.get(c, 0.0) for c in set(w)) * H
            # the box of a sloped word reaches the baseline at its down-slope end and the x-height line at its up-slope end
            x_lo, x_hi = xc - width / 2, xc + width / 2
            bottom = base0 + slope * ((x_hi if slope > 0 else x_lo) - 500) + desc + rng.normal(0, noise * H)
            top = base0 + slope * ((x_lo if slope > 0 else x_hi) - 500) - H + asc + rng.normal(0, noise * H)
            tokens.append(w)
            geometry.append([float(x_lo), float(top), float(x_hi), float(bottom)])
            truth.append(float(base))
        lines.append(dict(page='f1r', locus=str(l + 1), start=start, end=len(tokens)))
        ms_lines.append(dict(page=0, chars=words * 5, folio='f1r', locus=str(l + 1)))
    ms = dict(lines=ms_lines, pages=[dict(index=0, folio='f1r', side='r', start_line=0, end_line=n_lines)])
    app = dict(words=tokens, lines=lines, geometry=geometry, components={w: [w] for w in tokens}, component_mode='raw', geometry_kind='recorded')
    return ms, app, np.array(truth)


def test_synthetic_effects_and_baselines():
    ms, app, truth = _page()
    eff = glyph_effects(app, ms, min_count=10)
    e = eff['effects']
    # the effects are measured in the page's median BOX height, which the descenders and gallows make larger than the 30 px x-height
    scale = 30.0 / float(np.median([g[3] - g[1] for g in app['geometry']]))
    assert 0.7 < scale < 0.9
    for g, v in DESC.items():
        assert abs(e[g]['bottom_H'] - v * scale) < 0.03, (g, e[g], v * scale)
    for g, v in ASC.items():
        assert abs(e[g]['top_H'] - v * scale) < 0.03, (g, e[g], v * scale)
    for g in ('o', 'a', 'l', 'ch', 'sh', 'd', 'r'):
        assert e[g]['bottom_H'] == 0.0 and e[g]['top_H'] == 0.0, (g, e[g])
    assert 'o' in eff['reference'] and 'q' not in eff['reference'] and 'k' not in eff['reference']
    pts = {m: word_baselines(app, ms, m, effects=eff) for m in ('bottom', 'centre', 'glyph')}
    err = {m: np.array([p[1] for p in pts[m]]) - truth for m in pts}
    err = {m: v - np.median(v) for m, v in err.items()}                  # a constant level is not an error here
    rms = {m: float(np.sqrt(np.mean(v ** 2))) for m, v in err.items()}
    assert rms['glyph'] < 0.06 * 30 and rms['glyph'] < 0.5 * rms['bottom'], rms
    assert all(p[2] > 1 for p in pts['glyph']) and all(p[2] == 1.0 for p in pts['bottom'])
    pts_d, info = word_baselines(app, ms, 'glyph', effects=eff, details=True)
    assert abs(np.median([v for v in info['x_height_H'].values() if v is not None]) - scale) < 0.05     # the x-height is 30 px = `scale` box heights
    assert line_xheights(app, ms, effects=eff) == info['x_height_H'] and len(info['x_height_H']) == 16
    cmp = baseline_rms(app, ms, effects=eff)
    assert cmp['lowest'] == 'glyph' and cmp['n_lines'] == 16
    assert effects_table(eff)[0]['unit'] in DESC


@needs_data
def test_manuscript_effects_and_rms(ms, sensitivity_recorded):
    sensitivity = sensitivity_recorded
    eff = glyph_effects(sensitivity, ms)
    e = eff['effects']
    assert eff['n_lines'] >= 3600 and eff['n_words'] >= 30000
    for g in ('k', 't', 'p', 'f', 'cth', 'ckh'):
        assert e[g]['top_H'] < -MIN or e[g]['top_raw_H'] < 0, (g, e[g])
    for g in ('q', 'y'):
        assert e[g]['bottom_H'] > 0, (g, e[g])
    assert eff['rms_after']['bottom'] < eff['rms_before']['bottom'] and eff['rms_after']['top'] < eff['rms_before']['top']
    cmp = baseline_rms(sensitivity, ms, effects=eff)
    assert cmp['n_lines'] == 3801                  # lines with 4 or more rectangles off the pages with rotated paragraphs
    assert list(cmp['methods'])[0] == 'auto' and cmp['lowest'] in ('auto', 'ink')
    assert cmp['methods']['glyph']['rms_pooled_H'] <= cmp['methods']['bottom']['rms_pooled_H'], cmp
    assert cmp['methods']['auto']['rms_pooled_H'] <= cmp['methods']['glyph']['rms_pooled_H']
    pts = word_baselines(sensitivity, ms, effects=eff)              # the default: auto
    assert sum(p is not None for p in pts) == 34625                 # the located tokens of the horizontal lines
    pts_d, info = word_baselines(sensitivity, ms, 'auto', effects=eff, details=True)
    assert info['auto']['pages'] == {'ink': 193, 'glyph': 34} and info['auto']['ink_points'] > 20000
    assert sum(p is not None for p in word_baselines(sensitivity, ms, 'glyph', effects=eff, orientations=None)) == 38605


@needs_data
def test_study_shape_baselines(ms_study, sensitivity_study):
    eff = glyph_effects(sensitivity_study, ms_study)
    cmp = baseline_rms(sensitivity_study, ms_study, effects=eff, methods=['bottom', 'centre', 'glyph'])
    assert cmp['n_lines'] == 3801 and cmp['lowest'] == 'glyph'
    assert abs(cmp['methods']['glyph']['rms_pooled_H'] - 0.1289) < 0.002 and abs(cmp['methods']['bottom']['rms_pooled_H'] - 0.1691) < 0.002
    pts = word_baselines(sensitivity_study, ms_study, 'glyph', effects=eff)
    assert sum(p is not None for p in pts) == 34625
    assert sum(p is not None for p in word_baselines(sensitivity_study, ms_study, 'glyph', effects=eff, orientations=None)) == 34876


MIN = 0.03
