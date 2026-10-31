import pytest

from conftest import needs_data

from vmsspatial.units import zattera, raw_units, letters, parse_eva
from vmsspatial.bundle import load_bundle, make_bundle, validate_bundle, clean_geometry, POLICIES


def test_zattera_units():
    assert zattera('qokeedy') == ['q', 'o', 'k', 'ee', 'd', 'y']
    assert zattera('cheol') == ['ch', 'e', 'o', 'l']
    assert zattera('ckhaiin') == ['ckh', 'a', 'ii', 'n']
    assert zattera('@130;tol') == ['@130;', 't', 'o', 'l']
    assert zattera("{c'hkh}y") == ["{c'hkh}", 'y']
    for w in ('qokeedy', 'daiin', 'ol{c@133;h}eol', 'shxam', 'eeee'):
        assert ''.join(zattera(w)) == w
    assert raw_units('chol') == ['c', 'h', 'o', 'l']
    assert letters('herba') == list('herba')
    assert [a.kind for a in parse_eva('cth{ab}@1;x')] == ['composite', 'ligature', 'extended', 'glyph']


@needs_data
def test_default_bundle_is_every_locus_flat(strict, sensitivity):
    assert strict['schema'] == 3 and len(strict['words']) == 38876 and len(strict['lines']) == 5365
    assert strict['pages'] == 'all' and strict['order'] == 'bifolia' and strict['warp'] == 'flat' and strict['geometry_kind'] == 'flattened'
    assert sum(1 for b in strict['geometry'] if b) == 35613
    assert sum(1 for b in sensitivity['geometry'] if b) == 38605
    assert strict['lines'][0]['page'] == 'f1r' and strict['words'][:3] == ['fachys', 'ykal', 'ar']
    assert strict['spatialReview']['version'] == '2026-10-31' and strict['geometry_provenance']['policy'] == 'strict'
    assert strict['geometry_provenance']['page_warp_version'] and strict['detected_pages'] == ['fRos']
    assert sum(1 for v in strict['warp_pages'].values() if v == 'flat') == 205 and len(strict['warp_pages']) == 227
    assert all(t['strict'] == (b is not None) for t, b in zip(sensitivity['spatialReview']['tokens'], sensitivity['geometry']))
    for policy in POLICIES:
        assert len(load_bundle(policy, orientation=False)['geometry']) == 38876
    with pytest.raises(ValueError):
        load_bundle('legacy')
    with pytest.raises(ValueError):
        load_bundle('strict', warp='bent')
    assert validate_bundle(strict)['tokens'] == 38876


@needs_data
def test_study_shape_bundles(strict_study, sensitivity_study):
    """The study shape by explicit option: paragraph text, Path 1 order, recorded rectangles."""
    assert len(strict_study['words']) == 34977 and strict_study['pages'] == 'paragraph' and strict_study['order'] == 'path1' and strict_study['warp'] == 'recorded'
    assert sum(1 for b in strict_study['geometry'] if b) == 32319
    assert sum(1 for b in sensitivity_study['geometry'] if b) == 34876
    assert 'legacyGeometry' not in strict_study and strict_study['geometry_kind'] == 'recorded'
    assert strict_study['lines'][0]['page'] == 'f27r'
    from vmsspatial.bundle import manuscript_of
    assert manuscript_of(strict_study).summary()['tokens'] == 34977
    assert validate_bundle(strict_study)['tokens'] == 34977


@needs_data
def test_make_bundle_roundtrip(ms_study, sensitivity_study, ms, sensitivity_recorded):
    from vmsspatial.geometry import line_frames, synthetic_geometry
    frames = line_frames(sensitivity_study, ms_study)
    lines = ms_study.line_words()
    geom = synthetic_geometry(lines, frames, ms_study)
    b = make_bundle(ms_study, lines, geom, 'zattera', provenance=sensitivity_study['geometry_provenance'], geometry_kind='synthetic')
    v = validate_bundle(b)
    assert v['tokens'] == 34977 and v['lines'] == 4130 and v['boxed'] == 34667
    assert b['frame'] == 'recorded' and b['source'] == 'synthetic' and b['lines'][0]['locus_type'] == 'P0' and b['pages'] == 'paragraph' and b['order'] == 'path1'
    assert b['components']['qokeedy'] == ['q', 'o', 'k', 'ee', 'd', 'y']
    assert b['input_geometry_provenance']['policy'] == 'sensitivity'
    # the default shape: labels, rings and radial words get no synthetic box (they are not horizontal text)
    frames = line_frames(sensitivity_recorded, ms)
    lines = ms.line_words()
    geom = synthetic_geometry(lines, frames, ms)
    v = validate_bundle(make_bundle(ms, lines, geom, 'zattera', geometry_kind='synthetic'))
    assert v['tokens'] == 38876 and v['lines'] == 5365 and v['boxed'] == 34578


def test_clean_geometry_drops_oversized():
    lines = [dict(page='p', start=0, end=5)]
    geometry = [[0, 0, 10, 10], [12, 0, 22, 10], [24, 0, 34, 10], [36, 0, 200, 10], [40, 0, 50, 60]]
    out = clean_geometry(geometry, lines)
    assert out[3] is None and out[4] is None and out[0] == [0, 0, 10, 10]
