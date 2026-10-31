"""Wheels: the circle fit and its screens on synthetic rings, the manuscript's wheels (34 on 25 pages, 7 rejected
circular loci, 1,994 accepted boxes), the orientation records that take their centres from them, the shipped product
and the display transform's frame tag."""
import math

import pytest

from conftest import needs_data

from vmsspatial import wheels as Wh
from vmsspatial.frames import FrameError, require_same, tags


def _ring(cx, cy, r, n, w=20.0, h=10.0, arc=2 * math.pi):
    out = []
    for k in range(n):
        th = arc * k / n
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        out.append(dict(first=k, last=k, box=[x - w / 2, y - h / 2, x + w / 2, y + h / 2]))
    return out


def test_fit_circle_and_acceptance():
    pts = [[123 + 200 * math.cos(k * math.pi * 2 / 30), 456 + 200 * math.sin(k * math.pi * 2 / 30)] for k in range(30)]
    f = Wh.fit_circle(pts)
    assert abs(f['centre'][0] - 123) < 1e-7 and abs(f['centre'][1] - 456) < 1e-7 and abs(f['radius'] - 200) < 1e-7 and f['residual'] < 1e-7
    assert Wh.acceptance(f, 30.0) == ''
    moved = Wh.fit_circle([[x + 100000, y - 90000] for x, y in pts])                     # the centred solve survives a large offset
    assert abs(moved['centre'][0] - 100123) < 1e-5 and abs(moved['centre'][1] + 89544) < 1e-5
    assert Wh.fit_circle([[1, 2], [2, 4], [3, 6]]) is None                                # collinear
    assert Wh.acceptance(Wh.fit_circle(pts[:4]), 30.0) == Wh.REASONS['few']
    assert Wh.acceptance(Wh.fit_circle(pts[:10]), 30.0) == Wh.REASONS['arc']               # 10 of 30 points cover 108 degrees
    assert Wh.acceptance(Wh.fit_circle(pts), 150.0) == Wh.REASONS['radius']
    assert Wh.acceptance(None, 30.0) == Wh.REASONS['few']


def test_rings_and_grouping():
    H = 10.0
    lines = [dict(line=0, locus='1', units=_ring(500, 500, 200, 12)), dict(line=1, locus='2', units=_ring(503, 498, 150, 9)),
             dict(line=2, locus='3', units=_ring(900, 900, 120, 8)), dict(line=3, locus='4', units=_ring(500, 500, 100, 4))]
    rings, rejected = Wh.fit_rings(lines, H)
    assert [r['locus'] for r in rings] == ['1', '2', '3'] and rejected[0]['locus'] == '4' and rejected[0]['reason'] == Wh.REASONS['few']
    wheels = Wh.group_rings(rings, H)
    assert len(wheels) == 2 and [len(w['rings']) for w in wheels] == [2, 1]                # 500/500 twice (within max(H, 8% of 150)), 900/900 apart
    assert abs(wheels[0]['centre'][0] - 501.5) < 1e-6 and wheels[0]['radius'] == pytest.approx(200.0, abs=1e-6)
    assert wheels[0]['centre_spread'] == pytest.approx(math.hypot(1.5, 1.0), abs=1e-6)
    # a duplicated rectangle counts once for the fit
    dup = dict(line=0, locus='1', units=_ring(500, 500, 200, 4) + _ring(500, 500, 200, 4))
    assert Wh.fit_rings([dup], H)[1][0]['reason'] == Wh.REASONS['few']


@needs_data
@pytest.mark.slow
def test_manuscript_wheels(ms, sensitivity_recorded):
    prod = Wh.fit_wheels(sensitivity_recorded, ms)
    s = prod['summary']
    assert (s['pages_with_wheels'], s['wheels'], s['rejected_loci'], s['accepted_boxes']) == (26, 35, 4, 2216)
    assert s['by_section']['Zodiac'] == 12 and s['by_section']['Astronomical'] == 6 and sum(s['by_section'].values()) == 35
    assert len(prod['pages']['f68r2']['wheels']) == 2 and len(prod['pages']['fRos']['wheels']) == 9 and prod['pages']['fRos']['frame'] == 'detected'
    zodiac = [p['folio'] for p in ms.pages if p['section_name'] == 'Zodiac']
    assert len(zodiac) == 12 and all(len(prod['pages'][f]['wheels']) == 1 for f in zodiac)
    f68r1 = prod['pages']['f68r1']
    assert not f68r1['wheels'] and f68r1['rejected'][0]['reason'] == Wh.REASONS['few'] and f68r1['rejected'][0]['fit']['n'] == 4
    assert 'f67r2' not in prod['pages'] or not prod['pages']['f67r2']['circular_lines']      # radial labels only: no centre is inferred
    w = prod['pages']['f57v']['wheels'][0]
    assert abs(w['centre'][0] - 682.4) < 0.1 and abs(w['centre'][1] - 588.1) < 0.1 and abs(w['radius'] - 444.4) < 0.1 and w['words'] == 156 and len(w['rings']) == 4
    # the shipped product is this fit
    shipped = Wh.load_wheels()
    assert shipped['summary']['wheels'] == 35 and shipped['words_sha256'] == prod['words_sha256']
    assert len(Wh.wheels_table(shipped)) == 35
    # orientation records take their centres from the wheels: rejected rings have none, radial lines the nearest wheel
    recs = [L['orientation'] for L in sensitivity_recorded['lines']]
    circ = [r for r in recs if r['kind'] == 'circular']
    assert len(circ) == 83 and sum(1 for r in circ if r['centre'] is None) == 4 and sum(1 for r in circ if r.get('wheel')) == 79
    rad = [r for r in recs if r['kind'] == 'radial']
    assert len(rad) == 141 and sum(1 for r in rad if r['centre'] is not None) == 116
    for L in sensitivity_recorded['lines']:
        if L['page'] == 'f68r2' and L['orientation']['kind'] == 'circular':
            assert L['orientation']['wheel'] in ('f68r2/wheel1', 'f68r2/wheel2')
    # the display transform: a frame of its own
    lay = Wh.centered_layout(sensitivity_recorded, ms, 'f68r2')
    assert tags(lay)['frame'] == 'display' and [w['id'] for w in lay['wheels']] == ['f68r2/wheel1', 'f68r2/wheel2']
    first = lay['wheels'][0]['words'][0]
    src = sensitivity_recorded['geometry'][first['first']]
    assert first['rect'][0] == pytest.approx(src[0] - lay['wheels'][0]['centre'][0]) and first['rect'][2] - first['rect'][0] == pytest.approx(src[2] - src[0])
    with pytest.raises(FrameError):
        require_same(lay, sensitivity_recorded, 'a centred layout and the bundle')
    assert Wh.extent(Wh.centered_layout(sensitivity_recorded, ms, pages=[f for f in prod['pages'] if prod['pages'][f]['wheels']], labels=True)) == 650.0
