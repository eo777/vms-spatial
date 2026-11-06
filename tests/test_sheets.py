"""The odd-shaped sheets (vmsspatial.sheets, resources/sheets.json) against the physical map and the leaves product."""
import gzip
import json

from conftest import needs_data

from vmsspatial import paths, sheets


@needs_data
def test_the_resource_agrees_with_the_physical_map():
    assert sheets.check() == []
    s = sheets.load()['sheets']
    assert s['B:12-13']['missing'] == [12] and s['L:73-74']['missing'] == [74]
    assert s['N:85-86']['grid']['pages']['f85r2'] == [1, 1, True], 'the upper row of the Rosettes outside is upside down'


@needs_data
def test_panel_widths_and_the_faces_that_disagree():
    w = sheets.panel_widths('S:100-101')['101']
    assert [round(v) for v in w['width']] == [138, 140], 'f101 runs 278 mm across its two panels, read on the recto'
    f72 = sheets.panel_widths('K:71-72')['72']
    assert len(f72['width']) == 3 and 3 in f72['folds'] and 120 < f72['folds'][3] < 135
    for node in ('I:67-68', 'J:69-70', 'K:71-72', 'O:87-90', 'O:88-89', 'Q:94-95', 'S:99-102', 'S:100-101'):
        for leaf, rec in sheets.panel_widths(node).items():
            if len(rec['width']) > 1:
                assert all(120 < v < 260 for v in rec['width']), (node, leaf, rec['width'])
    # the binding hides about 13 mm more of f101's first panel on the recto: that panel is read on each face's own photograph
    assert sheets.panel_widths('S:100-101')['101']['faces'] == {'r': [138.1, 139.6], 'v': [151.3, 139.6]}
    v = sheets.for_viewer()
    assert set(v) == {'I:67-68', 'J:69-70', 'K:71-72', 'N:85-86', 'O:87-90', 'O:88-89', 'Q:94-95', 'S:99-102', 'S:100-101'}
    assert v['K:71-72'].keys() == {'B'}, 'f71 is an ordinary leaf, its fold placed only'
    assert v['S:100-101']['B']['pages']['f101r'] == [0, 1]


@needs_data
def test_the_leaves_take_the_placed_folds():
    L = json.load(gzip.open(paths.resolve('manuscript/leaves.json.gz')))
    pages = L['pages']
    assert L['calibration']['scans_own_scale'].keys() == {'1006203'}, 'f71v and f72r were photographed at another distance'
    assert 215 < pages['f72r1']['leaf_height_mm'] < 235
    for f in ('f67r2', 'f68r2', 'f68r3', 'f70r2', 'f72r2', 'f72r3', 'f89r2', 'f90r2', 'f95r2', 'f102r2', 'f71v'):
        assert pages[f]['fold_method'] == 'sheet', f
    # f101v's display image shows only its first panel; registered on that panel's photograph, its fold, top and scale are measured
    p = pages['f101v']
    assert p['image_id'] == '1006251' and {p['fold_method'], p['top_method'], p['scale_method']} == {'measured'}
    assert abs(p['fold_sheet'] - p['fold']) / p['mm'] < 1
    # visible widths run to the fold kept (f71v's own scan line was f72r's crease) and to the placed lines on a foldout
    assert 150 < pages['f71v']['visible_width_mm'] < 162 and abs(pages['f101r']['visible_width_mm'] - 278) < 2
    assert all(128 <= p['visible_width_mm'] <= 192 for f, p in pages.items() if 'visible_width_mm' in p and not p['panel'] and f != 'f101r')
    # where the scan's own fold is measured, the placed binding line agrees with it
    for f, p in pages.items():
        if 'fold_sheet' in p and p['fold_method'] == 'measured':
            assert abs(p['fold_sheet'] - p['fold']) / p['mm'] < 4, f
