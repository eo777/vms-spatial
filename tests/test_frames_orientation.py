"""Frame tags and orientation records: the tags travel with every table, two tables that differ in frame or warp
state cannot be combined, and the orientation classifier reads a line's rectangles the way the ZL locus types say."""
import math

import numpy as np
import pytest

from conftest import needs_data

from vmsspatial import frames
from vmsspatial.frames import FrameError, tags, tag, require_same, require_recorded, describe
from vmsspatial import orientation as O
from vmsspatial.audit.flags import QUARANTINE


def test_tags_default_and_from_geometry_kind():
    assert tags({'words': []}) == dict(frame='recorded', warp='recorded', source='voynichese', detected_pages=())
    assert tags({'geometry_kind': 'flattened'})['warp'] == 'flat'
    assert tags({'geometry_kind': 'synthetic'})['source'] == 'synthetic'
    t = tags({'geometry_kind': 'detected', 'detected_pages': ['fRos']})
    assert t['frame'] == 'detected' and t['detected_pages'] == ('fRos',)
    b = tag({'a': 1}, warp='flat')
    assert b['warp'] == 'flat' and b['frame'] == 'recorded' and 'flat warp' in describe(b)
    with pytest.raises(FrameError):
        tag({}, warp='bent')
    with pytest.raises(FrameError):
        tags(None)


def test_require_same_names_both_tags():
    a = dict(frame='recorded', warp='recorded', source='voynichese')
    b = dict(frame='recorded', warp='flat', source='beinecke')
    with pytest.raises(FrameError) as err:
        require_same(a, b, 'the bundle and the ink product')
    msg = str(err.value)
    assert 'recorded warp' in msg and 'flat warp' in msg and 'source beinecke' in msg and 'differ in warp' in msg
    c = dict(frame='recorded', warp='recorded', source='beinecke')
    assert require_same(a, c, 'x')['frame'] == 'recorded'                      # sources may differ: the registration put them in one frame
    with pytest.raises(FrameError):
        require_same(a, c, 'x', keys=('frame', 'warp', 'source'))
    with pytest.raises(FrameError):
        require_recorded(b, 'an overlay')
    assert require_recorded(a)['warp'] == 'recorded'


def _line(n, angle_deg=0.0, w=60.0, h=28.0, step=70.0, y0=300.0, x0=100.0):
    th = math.radians(angle_deg)
    boxes = []
    for k in range(n):
        cx, cy = x0 + k * step * math.cos(th), y0 + k * step * math.sin(th)
        boxes.append([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
    return boxes


def test_line_record_kinds():
    W, H = 60.0, 28.0
    r = O.line_record(_line(8), 'P0', W, H)
    assert r['kind'] == 'horizontal' and abs(r['angle_deg']) < 1e-6 and r['confidence'] > 0.5 and 'locus_type:P0' in r['basis']
    r = O.line_record(_line(8, angle_deg=4.0), 'P0', W, H)
    assert r['kind'] == 'horizontal' and abs(r['angle_deg'] - 4.0) < 0.2
    r = O.line_record(_line(6, angle_deg=88.0, w=20.0, h=70.0), 'Pb', W, H)              # a rotated block: tall boxes down the page
    assert r['kind'] == 'rotated' and abs(r['angle_deg'] - 88.0) < 0.5 and 'tall boxes' in r['basis']
    r = O.line_record(_line(6, angle_deg=-40.0), 'P0', W, H)
    assert r['kind'] == 'rotated' and abs(r['angle_deg'] + 40.0) < 0.5
    rev = O.line_record(_line(6)[::-1], 'P0', W, H)                                      # boxes recorded right to left: a reversal, not rotation
    assert rev['kind'] == 'horizontal' and 'reversed box order' in rev['basis'] and abs(rev['angle_deg']) < 1e-6
    # a ring of 12 words around (500, 500), radius 200, clockwise (y down)
    ring = []
    for k in range(12):
        th = math.radians(-90 + 30 * k)
        cx, cy = 500 + 200 * math.cos(th), 500 + 200 * math.sin(th)
        ring.append([cx - 25, cy - 14, cx + 25, cy + 14])
    r = O.line_record(ring, 'Cc', W, H)
    assert r['kind'] == 'circular' and abs(r['centre'][0] - 500) < 1 and abs(r['centre'][1] - 500) < 1 and abs(r['radius'] - 200) < 1
    assert r['clockwise'] and r['word_angles'][0] == pytest.approx(0.0, abs=0.5) and r['word_angles'][3] == pytest.approx(90.0, abs=0.5)
    r = O.line_record(ring, 'P0', W, H)                                                  # a paragraph locus that runs in a circle
    assert r['kind'] == 'circular'
    r = O.line_record(_line(3, angle_deg=-60.0), 'Ri', W, H, page_centre=[500, 500, 200])
    assert r['kind'] == 'radial' and r['centre'] == [500.0, 500.0] and len(r['word_angles']) == 3
    r = O.line_record(_line(1), 'L0', W, H)
    assert r['kind'] == 'label' and r['angle_deg'] == 0.0
    r = O.line_record([None, None], 'P0', W, H)
    assert r['kind'] == 'unknown' and r['confidence'] == 0.0
    with pytest.raises(ValueError):
        O.line_mask({'lines': []}, 'diagonal')


@needs_data
def test_manuscript_orientation_counts_and_quarantine_alias(sensitivity, ms):
    s = O.summary(sensitivity, ms)
    assert s['lines_by_kind'] == {'horizontal': 4070, 'unknown': 102, 'label': 921, 'circular': 83, 'radial': 141, 'rotated': 48}
    assert s['lines_by_kind']['horizontal'] >= 4000 and s['lines_by_kind'].get('rotated', 0) >= 40
    assert set(s['lines_by_kind']) <= set(O.KINDS)
    pages = O.nonhorizontal_pages(sensitivity, ms)
    assert QUARANTINE <= pages, pages - QUARANTINE
    joined = sorted(pages - QUARANTINE)
    assert joined == [], 'pages joining the quarantine alias: %s' % joined
    assert all('orientation' in L and 'locus_type' in L for L in sensitivity['lines'])
    first = sensitivity['lines'][0]['orientation']
    assert first['kind'] == 'horizontal' and first['locus_type'] == 'P0'
    mask = O.line_mask(sensitivity, 'horizontal')
    assert sum(mask) == s['lines_by_kind']['horizontal'] and O.skipped(sensitivity, mask)['skipped_lines'] == len(mask) - sum(mask)
    assert sensitivity['frame'] == 'recorded' and sensitivity['warp'] == 'flat' and sensitivity['source'] == 'voynichese'


@needs_data
def test_extra_bundle_covers_every_locus_with_kinds(ms, ms_study, sensitivity):
    from vmsspatial import Manuscript, load_bundle
    full = ms
    assert len(full.pages) == 227 and all(L.get('locus_type') for L in full.lines)
    types = {L['locus_type'][0] for L in full.lines}
    assert types == {'P', 'L', 'C', 'R'}
    f67v2 = [L for L in full.lines if L['folio'] == 'f67v2']
    assert sorted({L['locus_type'] for L in f67v2}) == ['La', 'Pb', 'Ri', 'Ro']        # labels and radial words, not only the paragraphs
    assert len(ms_study.pages) == 207 and ms_study.n_tokens == 34977                      # the study shape, by explicit option
    b = sensitivity
    s = O.summary(b)
    assert s['lines_by_kind']['circular'] >= 80 and s['lines_by_kind']['radial'] >= 100 and s['lines_by_kind']['label'] >= 700
    assert b.get('frame_image', {}).get('fRos', '').endswith('fRos.jpg') and b['detected_pages'] == ['fRos']
