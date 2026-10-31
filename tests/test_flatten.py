"""Flattening: a synthetic warped page is straightened, a thin page is left alone, the manuscript bundle stays valid."""
import copy

import numpy as np

import pytest

from conftest import needs_data

from vmsspatial.bundle import validate_bundle
from vmsspatial.flatten import flatten, baseline_curves, expected_gutter, page_table
from vmsspatial.geometry import line_units
from vmsspatial.selector import SpatialContext

# the injected warp of the synthetic page (pixels; u, v in -1..1 over the text block)
W20, W21, W30, W31 = -6.0, 1.5, 4.0, -1.0        # (w20 + w21 v) u^2 + (w30 + w31 v) u^3: |W''| is larger on the left
C0, C1 = 0.02, 0.006                              # shared slope c0 + c1 v (1.15 deg of tilt, a little keystone)
SLOPE = 0.012                                     # the lines' own slopes, +-SLOPE in a pattern with zero mean and no trend in v
PATTERN = [1, -1, -1, 1, 1, -1, -1, 1, 1, -1, -1, 1]
NOISE = 0.5


def _page(n_lines=12, words=12, folio='f1r', seed=3):
    """A toy manuscript and bundle: one page of straight lines with a warp, a tilt and a keystone written into the boxes."""
    rng = np.random.default_rng(seed)
    xs0 = np.linspace(150, 850, words)
    x_mid, half_w = 500.0, 350.0
    ys0 = 200 + 80 * np.arange(n_lines)
    y_mid, half_h = float(ys0.mean()), float((ys0[-1] - ys0[0]) / 2) if n_lines > 1 else 1.0
    words_all, lines, geometry, truth, own = [], [], [], [], []
    ms_lines = []
    for l in range(n_lines):
        x = xs0 + rng.uniform(-8, 8, words)
        x[0], x[-1] = xs0[0], xs0[-1]                       # the extent stays what the model will measure
        u = (x - x_mid) / half_w
        v = (ys0[l] - y_mid) / half_h
        b = SLOPE * PATTERN[l % len(PATTERN)]
        straight = ys0[l] + b * (x - x_mid)
        warp = (W20 + W21 * v) * u ** 2 + (W30 + W31 * v) * u ** 3 + (C0 + C1 * v) * (x - x_mid)
        y = straight + warp + rng.normal(0, NOISE, words)
        start = len(words_all)
        for k in range(words):
            words_all.append('w%d_%d' % (l, k))
            geometry.append([float(x[k] - 20), float(y[k] - 24), float(x[k] + 20), float(y[k])])
            truth.append(float(straight[k]))
        lines.append(dict(page=folio, locus=str(l + 1), start=start, end=len(words_all)))
        ms_lines.append(dict(page=0, chars=words * 5, folio=folio, locus=str(l + 1)))
        own.append(b)
    ms = dict(lines=ms_lines, pages=[dict(index=0, folio=folio, side=folio[-1], start_line=0, end_line=n_lines)])
    app = dict(words=words_all, lines=lines, geometry=geometry, components={w: [w] for w in words_all}, component_mode='raw', geometry_kind='recorded',
               geometry_provenance=dict(policy='toy'))
    return ms, app, np.array(truth), own


def test_synthetic_page_is_straightened():
    ms, app, truth, own = _page()
    before = copy.deepcopy(app)
    flat, report = flatten(app, ms, baseline='bottom')                 # toy words carry no EVA glyphs: the plain box bottom
    assert app == before                                               # the input bundle is untouched
    p = report['pages']['f1r']
    assert p['fitted'] and p['n_lines'] == 12 and p['n_points'] == 144 and p['v_terms'] and p['degree_used'] == 3
    g0, g1 = np.array(app['geometry'], float), np.array(flat['geometry'], float)
    assert np.allclose(g1[:, 2] - g1[:, 0], g0[:, 2] - g0[:, 0]) and np.allclose(g1[:, 3] - g1[:, 1], g0[:, 3] - g0[:, 1])
    assert np.allclose(g1[:, 0], g0[:, 0]) and np.allclose(g1[:, 1] - g0[:, 1], g1[:, 3] - g0[:, 3])
    # the flattened bottoms are the true straight lines up to one page constant (the zero-mean reference) and the noise
    dev = g1[:, 3] - truth
    dev -= dev.mean()
    assert np.abs(dev).max() < 2.0 and dev.std() < 0.7, (np.abs(dev).max(), dev.std())
    # the warp was recognised: amplitude, its stronger side, the tilt and the keystone
    assert p['gutter_side'] == 'left' and p['expected_gutter'] == 'left'
    assert abs(p['tilt_deg'] - np.degrees(np.arctan(C0))) < 0.1
    assert p['curvature_pp_px'] > 3.0 and p['rms_after_H'] < 0.3 * p['rms_before_H']
    assert abs(p['keystone_deg_text_height'] - (np.degrees(np.arctan(C0 + C1)) - np.degrees(np.arctan(C0 - C1)))) < 0.15
    # the per-line slopes that survive are the lines' own slopes
    for l in range(12):
        L = p['coefficients']['lines'][str(l)]
        assert abs(np.tan(np.radians(L['slope_deg'])) - (own[l] + C0 + C1 * L['v'])) < 0.004
    warped, straight = baseline_curves(p, 3, np.linspace(150, 850, 5))
    assert warped.shape == (5,) and np.abs(warped - straight).max() > 1.0
    assert flat['geometry_kind'] == 'flattened' and flat['geometry_provenance']['derived'] == 'flattened'
    assert flat['geometry_provenance']['parent_geometry_kind'] == 'recorded' and flat['flatten'] is report
    assert page_table(report)[0]['folio'] == 'f1r'
    assert report['summary']['fitted'] == 1 and report['summary']['above_threshold']['share_match'] is None    # one page: no share


def test_thin_page_is_left_as_recorded():
    ms, app, _, _ = _page(n_lines=3)
    flat, report = flatten(app, ms, baseline='bottom')
    p = report['pages']['f1r']
    assert not p['fitted'] and 'fewer than 4 lines' in p['reason'] and p['n_lines'] == 3
    assert flat['geometry'] == app['geometry'] and flat['geometry'] is not app['geometry']
    assert flat['geometry_kind'] == 'flattened' and report['summary']['fitted'] == 0 and report['summary']['not_fitted'] == {p['reason']: 1}
    assert expected_gutter('f86v3') == 'right' and expected_gutter('f1r') == 'left' and expected_gutter('fRos') is None


def _median_abs_chord_angle(app, ms):
    from vmsspatial.audit.flags import QUARANTINE
    units = line_units(app, ms)
    angles = []
    for p in ms.pages:
        if p['folio'] in QUARANTINE:
            continue
        boxes = [u['box'] for l in range(p['start_line'], p['end_line']) for u in units[l]]
        if not boxes:
            continue
        W = np.median([b[2] - b[0] for b in boxes])
        for l in range(p['start_line'], p['end_line']):
            us = sorted(units[l], key=lambda u: u['box'][0] + u['box'][2])
            if len(us) < 4:
                continue
            x0, x1 = (us[0]['box'][0] + us[0]['box'][2]) / 2, (us[-1]['box'][0] + us[-1]['box'][2]) / 2
            if x1 - x0 < 3 * W:
                continue
            angles.append(abs(np.degrees(np.arctan((us[-1]['box'][3] - us[0]['box'][3]) / (x1 - x0)))))
    return float(np.median(angles)), len(angles)


@needs_data
def test_manuscript_bundle_flattens(ms, sensitivity_recorded, sensitivity):
    from vmsspatial.frames import FrameError
    with pytest.raises(FrameError):
        flatten(sensitivity, ms)                                 # the default bundle is flat already
    rec = sensitivity_recorded
    flat, report = flatten(rec, ms)                              # the default baseline: auto (ink where clean, glyph otherwise)
    counts = validate_bundle(flat)
    assert counts['boxed'] == 38605 and counts['pages'] == 227
    s = report['summary']
    assert s['pages'] == 227 and s['fitted'] == 205 and s['fitted'] + sum(s['not_fitted'].values()) == 227
    assert report['skipped']['by_kind'] == {'unknown': 102, 'label': 921, 'circular': 83, 'radial': 141, 'rotated': 48}
    assert report['pages']['f86v3']['fitted'] and report['pages']['f86v3']['baseline'] == 'ink' and report['pages']['f75r']['baseline'] == 'ink'
    assert report['parameters']['baseline'].startswith('per page (auto')
    for folio in ('f67r2', 'f86v3', 'f57v'):
        p = ms.page(folio)
        for l in range(p['start_line'], p['end_line']):
            if rec['lines'][l]['orientation']['kind'] != 'horizontal':
                L = rec['lines'][l]
                assert all(flat['geometry'][i] == rec['geometry'][i] for i in range(L['start'], L['end']))   # rotated, circular, radial lines untouched
    assert flat['warp'] == 'flat' and rec['warp'] == 'recorded'
    ctx = SpatialContext(flat, 'sensitivity')
    assert int(ctx.has_box.sum()) == 38605 and ctx.describe()['geometry_kind'] == 'flattened'
    assert flat['spatialReview']['sensitivityGeometry'] == flat['geometry']             # the policy's review list follows
    before, n0 = _median_abs_chord_angle(rec, ms)
    after, n1 = _median_abs_chord_angle(flat, ms)
    assert n0 == n1 and n0 >= 3750 and after <= before, (before, after)
    prov = flat['geometry_provenance']
    assert prov['derived'] == 'flattened' and prov['parent_geometry_sha256'] == rec['geometry_provenance']['geometry_sha256']
    assert prov['geometry_sha256'] != prov['parent_geometry_sha256'] and prov['flatten_parameters']['degree'] == 3 and prov['policy'] == 'sensitivity'
    assert rec['geometry_kind'] == 'recorded' and 'flatten' not in rec
    # the stored product equals this refit, so the default bundle IS this flattening
    for a, b in zip(flat['geometry'], sensitivity['geometry']):
        assert (a is None) == (b is None) and (a is None or max(abs(x - y) for x, y in zip(a, b)) < 1e-9)


@needs_data
def test_study_shape_flattens_with_the_glyph_baseline(ms_study, sensitivity_study):
    sensitivity, ms = sensitivity_study, ms_study
    flat, report = flatten(sensitivity, ms, baseline='glyph')
    assert validate_bundle(flat)['boxed'] == 34876 and report['summary']['pages'] == 207 and report['summary']['fitted'] == 205
    assert report['skipped'] == {'skipped_lines': 60, 'by_kind': {'unknown': 12, 'rotated': 48}}
    assert report['pages']['f86v3']['fitted'] and report['pages']['f86v3']['baseline'] == 'glyph'
    before, n0 = _median_abs_chord_angle(sensitivity, ms)
    after, n1 = _median_abs_chord_angle(flat, ms)
    assert n0 == n1 == 3773 and after <= before, (before, after)
    assert flat['geometry_provenance']['flatten_parameters']['baseline'] == 'glyph' and report['parameters']['baseline'] == 'glyph'
    flat_b, report_b = flatten(sensitivity, ms, baseline='bottom')
    assert report_b['summary']['fitted'] == report['summary']['fitted'] and flat_b['geometry'] != flat['geometry']
