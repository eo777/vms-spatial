"""The leaves on the parchment: the edges of a drawn leaf are found where they are, a crease in the inner margin does not
stand in for the fold, and the shipped numbers hang together."""
import numpy as np
import pytest

from vmsspatial import leaves, paths


def drawn_leaf(recto, crease=None, H=900, W=700, top=40, fold=60):
    """A leaf (200) on a black ground at a quarter of a scan's size, its fold `fold` px from the gutter side, and the text
    block's bounds. `crease`: (offset from the fold into the leaf, darkening) of a straight line in the inner margin."""
    img = np.zeros((H, W))
    x0, x1 = (fold, W - 30) if recto else (30, W - fold)
    img[top:H - 40, x0:x1] = 200.0
    if crease:
        off, dark = crease
        x = x0 + off if recto else x1 - 1 - off
        img[top:H - 40, x] -= dark
    text = [x0 + 80, top + 60, x1 - 60, H - 120] if recto else [x0 + 60, top + 60, x1 - 80, H - 120]
    return img, text, (x0 if recto else x1)


@pytest.mark.parametrize('recto', [True, False])
def test_edges_of_a_drawn_leaf(recto):
    img, text, fold = drawn_leaf(recto)
    e = leaves.measure_scan(img, text, recto)
    assert abs(e['fold']['at'] - fold) <= 1.5
    assert abs(e['top']['at'] - 40) <= 1.5 and abs(e['bottom']['at'] - (900 - 40)) <= 1.5
    assert abs(e['fold']['slope']) < 0.01


@pytest.mark.parametrize('recto', [True, False])
def test_a_crease_in_the_inner_margin_is_not_the_fold(recto):
    # a crease of 40% of the edge's contrast, 5 mm inside the leaf: within the 8 mm reach, so the stronger edge beyond it is taken
    img, text, fold = drawn_leaf(recto, crease=(20, 80))
    assert abs(leaves.measure_scan(img, text, recto)['fold']['at'] - fold) <= 1.5


def test_a_drawn_line_across_the_margin_is_not_an_edge():
    # a line crossing only part of the text's height scores the 35th percentile of the gradient along it: nothing
    img, text, fold = drawn_leaf(True)
    img[300:420, fold + 40] = 0
    assert abs(leaves.measure_scan(img, text, True)['fold']['at'] - fold) <= 1.5


@pytest.fixture(scope='module')
def product():
    p = paths.resolve(leaves.PRODUCT_KEY, required=False)
    if p is None:
        pytest.skip('leaves product not present')
    return leaves.load_leaves()


def test_the_product_hangs_together(product):
    cal = product['calibration']
    assert 14.0 < cal['scan_px_per_mm'] < 18.0 and cal['leaves'] >= 150
    pages = product['pages']
    measured = [p for p in pages.values() if p['fold_method'] == 'measured']
    assert len(measured) >= 180
    # a measured fold leaves an inner margin; an ordinary leaf is about the catalogue's height
    assert all(leaves.FOLD_MARGIN_MM[0] <= p['fold_margin_mm'] <= leaves.FOLD_MARGIN_MM[1] for p in measured)
    heights = [p['leaf_height_mm'] for p in pages.values() if not p['panel'] and p.get('leaf_height_mm') and p['top_method'] == 'measured']
    assert np.mean([205 <= h <= 245 for h in heights]) > 0.95
    # every page with text has a fold, a top and a scale, and says how each was found
    for f, p in pages.items():
        if p.get('text'):
            assert p['fold'] is not None and p['top'] is not None and p['mm'] > 0, f
            assert p['fold_method'] in ('measured', 'sheet', 'estimated') and p['top_method'] in ('measured', 'panel', 'bottom', 'estimated') and p['scale_method'] in ('measured', 'estimated'), f
    assert leaves.for_viewer(product, 'f1r')['fold_method'] == 'measured'
