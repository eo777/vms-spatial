"""The coordinate products: registrations, the baselines table and the page warp are shipped, tagged, and move
coordinates coherently; the stored warp reproduces the refitting flatten to rounding; mixing warp states is refused."""
import numpy as np
import pytest

from conftest import needs_data

from vmsspatial import paths
from vmsspatial.frames import FrameError, tags


def _have(key):
    return paths.resolve(key, required=False) is not None


needs_products = pytest.mark.skipif(not (_have('manuscript/page_warp.json.gz') and _have('manuscript/baselines.json.gz') and _have('manuscript/registrations.json.gz')),
                                    reason='the coordinate products are not built (vmsspatial build-products)')


@needs_data
@needs_products
def test_registration_product_serves_the_pages():
    from vmsspatial.images import registration_product, registration, registrations, Mapping
    from vmsspatial.frames import to_image, to_recorded
    prod = registration_product()
    assert prod['frame'] == 'recorded' and prod['warp'] == 'recorded' and set(prod['sources']) >= {'beinecke', 'display'}
    assert prod['counts']['beinecke']['ok'] >= 200
    rec = registration('f75r', 'beinecke')                       # read from the product, no image needed
    assert rec['ok'] and rec['residual_px'] < 2 and len(rec['lines']) > 40 and isinstance(rec['matrix'], list)
    assert registrations('beinecke')['f75r']['n_inliers'] == rec['n_inliers']
    pts = np.array([[500.0, 700.0], [600.0, 720.0]])
    img = to_image('f75r', pts, 'beinecke')
    back = to_recorded('f75r', img, 'beinecke')
    assert np.allclose(back, pts, atol=1e-6)
    from vmsspatial.bundle import load_bundle
    m = Mapping(rec, next(iter(rec['lines'])))                         # the per-line shifts are keyed by locus
    assert set(rec['lines']) <= {str(L['locus']) for L in load_bundle('sensitivity', warp='recorded', orientation=False)['lines'] if L['page'] == rec['folio']}
    assert np.allclose(m.to_frame(m.to_image(pts)), pts, atol=1e-6)


@needs_data
@needs_products
def test_page_warp_reproduces_the_refitting_flatten(ms, sensitivity_recorded):
    from vmsspatial import warp as W
    from vmsspatial.flatten import flatten
    from vmsspatial.ink import load_ink
    from vmsspatial.bundle import load_bundle
    sensitivity = sensitivity_recorded
    prod = W.load_warp()
    assert prod['frame'] == 'recorded' and prod['warp'] == 'recorded' and prod['produces'] == 'flat'
    assert prod['words_sha256'] == sensitivity['geometry_provenance']['words_sha256'] and prod['geometry_sha256'] == sensitivity['geometry_provenance']['geometry_sha256']
    assert set(prod['baseline_counts']) <= {'ink', 'glyph'} and prod['summary']['fitted'] >= 190
    flat = W.flatten_bundle(sensitivity)
    assert tags(flat)['warp'] == 'flat' and flat['geometry_kind'] == 'flattened' and flat['flatten']['version'] == prod['version']
    ink = load_ink()
    choice = W.baseline_choice(sensitivity, ms, ink)
    ref, rep = flatten(sensitivity, ms, baseline=choice, ink=ink)
    for a, b in zip(ref['geometry'], flat['geometry']):
        assert (a is None) == (b is None)
        if a is not None:
            assert max(abs(x - y) for x, y in zip(a, b)) < 1e-9
    for a, b in zip(ref['spatialReview']['sensitivityGeometry'], flat['spatialReview']['sensitivityGeometry']):
        assert (a is None) == (b is None) and (a is None or max(abs(x - y) for x, y in zip(a, b)) < 1e-9)
    lb = load_bundle('sensitivity')                                  # the default IS the flat state
    assert lb['geometry'] == flat['geometry'] and tags(lb)['warp'] == 'flat'
    assert W.page_status('f75r')['fitted'] and W.page_status('f75r')['moved'] == 'horizontal lines' and W.page_status('f57v')['fitted'] is False
    assert W.page_status('fNope')['reason'] == 'not in the page warp product' and lb['warp_pages']['f57v'].startswith('recorded')
    back = W.transform(flat, 'recorded')
    assert tags(back)['warp'] == 'recorded' and back['geometry_kind'] == 'recorded'
    worst = max(max(abs(x - y) for x, y in zip(a, b)) for a, b in zip(sensitivity['geometry'], back['geometry']) if a and b)
    assert worst < 1e-3, worst
    with pytest.raises(FrameError):
        W.transform(flat, 'flat')
    # apply on one line of f75r equals the bundle, both ways
    pg = ms.page('f75r')
    L = sensitivity['lines'][pg['start_line'] + 3]
    i = L['start']
    b = sensitivity['geometry'][i]
    y = W.apply('f75r', (b[0] + b[2]) / 2, b[3], L['locus'], 'flat')
    assert abs(y - flat['geometry'][i][3]) < 1e-9 and abs(W.apply('f75r', (b[0] + b[2]) / 2, y, L['locus'], 'recorded') - b[3]) < 1e-9
    # rotated lines keep their recorded position in the flat state
    p86 = ms.page('f86v3')
    rot = [l for l in range(p86['start_line'], p86['end_line']) if sensitivity['lines'][l]['orientation']['kind'] == 'rotated']
    assert rot and all(flat['geometry'][i] == sensitivity['geometry'][i] for l in rot for i in range(sensitivity['lines'][l]['start'], sensitivity['lines'][l]['end']))


@needs_data
@needs_products
def test_baselines_table_and_its_transform(ms, sensitivity_recorded):
    from vmsspatial import warp as W
    from vmsspatial.baselines import load_table, table_points, word_baselines, glyph_effects, METHODS
    sensitivity = sensitivity_recorded
    tab = load_table()
    assert tags(tab)['warp'] == 'recorded' and set(tab['methods']) == set(METHODS) and len(tab['x']) == len(sensitivity['words'])
    eff = glyph_effects(sensitivity, ms)
    for m in ('bottom', 'glyph'):
        stored = table_points(sensitivity, m)
        derived = word_baselines(sensitivity, ms, m, effects=eff, table=False)
        assert stored is not None and sum(p is not None for p in stored) == sum(p is not None for p in derived)
        assert max(abs(p[1] - q[1]) for p, q in zip(stored, derived) if p and q) < 0.006       # the table keeps 0.01 px
    assert word_baselines(sensitivity, ms, 'bottom') == table_points(sensitivity, 'bottom')     # read from the table by default
    flat = W.flatten_bundle(sensitivity)
    assert table_points(flat, 'glyph') is None                                                   # a recorded table does not serve a flat bundle
    ftab = W.transform(tab, 'flat')
    assert tags(ftab)['warp'] == 'flat'
    pts = table_points(flat, 'glyph', ftab)
    assert pts is not None
    # every moved point moved with its rectangle
    for i in range(0, len(pts), 97):
        if pts[i] and tab['methods']['glyph']['y'][i] is not None and flat['geometry'][i]:
            assert abs((pts[i][1] - tab['methods']['glyph']['y'][i]) - (flat['geometry'][i][3] - sensitivity['geometry'][i][3])) < 1e-6, i
    with pytest.raises(FrameError):
        W.transform(ftab, 'flat')


@needs_data
@needs_products
def test_ink_product_transform_and_frame_check(ms, sensitivity_recorded):
    from vmsspatial import warp as W
    from vmsspatial.ink import load_ink, baseline_points, intrusions, for_bundle, ink_matches
    from vmsspatial.bundle import load_bundle
    sensitivity = sensitivity_recorded
    ink = load_ink()
    assert ink_matches(ink, sensitivity) and for_bundle(ink, sensitivity) is ink                         # keyed to the default stream
    other = load_bundle('sensitivity', warp='recorded', order='path1', orientation=False)
    assert not ink_matches(ink, other) and ink_matches(for_bundle(ink, other), other)                    # another order: aligned by token id and (page, locus)
    assert for_bundle(ink, other)['remapped_from']['kept'] == len(ink['units']['first'])
    assert tags(ink)['frame'] == 'recorded' and tags(ink)['warp'] == 'recorded' and tags(ink)['source'] == 'beinecke'
    flat = W.flatten_bundle(sensitivity)
    from vmsspatial.frames import FrameWarning
    with pytest.warns(FrameWarning):
        mixed = baseline_points(ink, flat)             # recorded ink on flat boxes: the baseline travels with the box bottom, with a warning
    with pytest.warns(FrameWarning):
        intrusions(flat, ms, ink)
    fink = W.transform(ink, 'flat', ms=ms, app=sensitivity)
    clean = baseline_points(fink, flat)
    assert max(abs(mixed[k][1] - clean[k][1]) for k in clean) < 0.02       # the implicit rule and the explicit transform agree
    assert tags(fink)['warp'] == 'flat' and fink['units']['base'] != ink['units']['base']
    rec_pts, flat_pts = baseline_points(ink, sensitivity), baseline_points(fink, flat)
    assert set(rec_pts) == set(flat_pts)
    worst = max(abs((rec_pts[k][1] - sensitivity['geometry'][k][3]) - (flat_pts[k][1] - flat['geometry'][k][3])) for k in rec_pts)
    assert worst < 0.02, worst                          # the ink baseline keeps its distance to the box bottom (0.01 px rounding of the product)
    with pytest.raises(FrameError):
        W.transform(fink, 'flat')


@needs_data
@needs_products
def test_no_product_is_stale_and_none_depends_on_the_stream(ms, sensitivity_recorded):
    from vmsspatial.bundle import digest, load_bundle
    from vmsspatial import baselines as B, wheels as Wh
    from vmsspatial.ink import load_ink, for_bundle
    from vmsspatial.warp import load_warp
    app = sensitivity_recorded
    words, geom = digest(app['words']), digest(app['geometry'])
    for name, prod in (('baselines', B.load_table()), ('ink', load_ink()), ('warp', load_warp()), ('wheels', Wh.load_wheels())):
        assert prod['words_sha256'] == words, name
        assert prod['geometry_sha256'] == geom, name
    # another order: the same records through (page, locus) and token ids
    other = load_bundle('sensitivity', warp='recorded', order='folio')
    assert B.table_matches(B.load_table(), other) is False
    t = B.table_for(B.load_table(), other)
    pos = {x['id']: i for i, x in enumerate(other['spatialReview']['tokens'])}
    tok = app['spatialReview']['tokens']
    y0, y1 = B.load_table()['methods']['glyph']['y'], t['methods']['glyph']['y']
    assert all(y0[i] == y1[pos[tok[i]['id']]] for i in range(0, len(tok), 41))
    placed = Wh.wheels_for(other)
    home = Wh.wheels_for(app)
    for folio in ('f57v', 'f72r1'):
        for a, b in zip(home['pages'][folio]['wheels'], placed['pages'][folio]['wheels']):
            assert [other['words'][x] for r in b['rings'] for x, _ in r['tokens']] == [app['words'][x] for r in a['rings'] for x, _ in r['tokens']]
    ink = for_bundle(load_ink(), other)
    assert len(ink['units']['first']) == len(load_ink()['units']['first'])
