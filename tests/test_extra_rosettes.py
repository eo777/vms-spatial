"""The extra pages (circular pages, the Rosettes) and the detection helpers of vmsspatial.segment."""
import math

import numpy as np
import pytest

from conftest import needs_data, needs_raw

from vmsspatial import segment as S

cv2 = pytest.importorskip('cv2')


def test_clock_and_angles():
    assert S.clock_to_deg('00:00') == 0 and S.clock_to_deg('03:00') == 90 and S.clock_to_deg('10:30') == 315
    assert abs(S.box_angle([10, -30, 20, -20], 0, 0) - math.degrees(math.atan2(15, 25))) < 1e-9   # upper right = clockwise from 12
    assert abs(S.box_angle([-20, -5, -10, 5], 0, 0) - 270) < 1e-9


def test_fit_widths_splits_and_merges_by_glyph_count():
    # three words of 4, 2 and 6 glyphs at 10 px per glyph; the first two were not separated by a gap, the third
    # has a gap inside it
    runs = [(0, 60), (70, 100), (103, 130)]
    segs, err = S.fit_widths(runs, [4, 2, 6])
    assert len(segs) == 3 and err < 0.6
    assert segs[0][0] == 0 and segs[1][1] == 60 and segs[2] == (70, 130)
    exact, e2 = S.fit_widths([(0, 40), (50, 70), (80, 140)], [4, 2, 6])
    assert exact == [(0, 40), (50, 70), (80, 140)] and e2 < 1e-9


def test_strip_words_on_a_synthetic_ring():
    # a strip with five ink blocks of widths proportional to the glyph counts
    glyphs = [3, 5, 2, 4, 6]
    strip = np.zeros((20, 400), np.uint8)
    x = 10
    for g in glyphs:
        strip[5:15, x:x + 12 * g] = 1
        x += 12 * g + 9
    res = S.strip_words(strip, glyphs)
    assert len(res['segments']) == 5 and res['error'] < 0.1 and res['confidence'] > 0.9


def test_unwrap_maps_back_to_the_ring():
    img = np.zeros((400, 400), np.uint8)
    cv2.circle(img, (200, 200), 120, 255, 6)          # a drawn circle at radius 120
    ring = S.Ring(200, 200, 100, 140, start_deg=90, clockwise=True)
    strip, to_image = S.unwrap(img, ring)
    assert strip.shape[0] == 40
    row_profile = strip.mean(axis=1)
    assert abs(int(np.argmax(row_profile)) - 20) <= 2   # the circle sits mid-band
    x, y = to_image(0, 20)                               # the start column at 3 o'clock
    assert abs(x - 320) < 2 and abs(y - 200) < 2
    x2, y2 = to_image(strip.shape[1] / 4, 20)            # a quarter turn clockwise: 6 o'clock
    assert abs(x2 - 200) < 2 and abs(y2 - 320) < 2
    spiral = S.Ring(200, 200, 100, 140, 0, True, r0_end=40, r1_end=80, turns=2)
    s2, back = S.unwrap(img, spiral)
    x3, y3 = back(s2.shape[1], 20)                       # the end of two turns, back at 12 o'clock, at radius 60
    assert abs(x3 - 200) < 2 and abs(y3 - 140) < 2


def test_assign_sequence_and_ordering_hypotheses():
    items = [dict(glyphs=3), dict(glyphs=6), dict(glyphs=2)]
    # candidates around a centre: a 60-px box at 12 o'clock, a 20 px box at 3 o'clock, a 30 px box at 6 o'clock
    cands = [dict(box=[-30, -110, 30, -90]), dict(box=[90, -10, 110, 10]), dict(box=[-15, 90, 15, 110])]
    best = S.best_assignment(items, cands, 10.0, 0, 0)
    # clockwise from 6 o'clock: 30 (3 glyphs), 60 (6 glyphs), 20 (2 glyphs)
    assert best['hypothesis'] == 'cw' and best['boxes'] == [cands[2]['box'], cands[0]['box'], cands[1]['box']]
    assert best['confidence'] > 0.9
    groups = S.clusters([dict(box=[0, 0, 50, 20]), dict(box=[0, 24, 60, 44]), dict(box=[300, 0, 340, 20])])
    assert sorted(len(g) for g in groups) == [1, 2]


@needs_raw
def test_rosettes_loci_are_classified_from_the_transliteration():
    from vmsspatial.rosettes import read_loci, classify, load_layout
    loci = read_loci()
    assert len(loci) == 160 and sum(len(L['tokens']) for L in loci) == 540
    groups = classify(loci, load_layout())
    assert len(groups['rings']) == 12 and set(groups['petersen']) == {str(k) for k in range(1, 10)}
    assert sorted(groups['roman']) == ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII']
    assert [L['num'] for L in groups['clock']] == [112, 115]


@needs_data
def test_extra_pages_join_the_manuscript_and_the_bundle(ms, ms_study):
    from vmsspatial import Manuscript
    from vmsspatial.bundle import load_bundle, validate_bundle
    full = Manuscript.load(extra=True)                                          # the older spelling of the default
    assert len(full.pages) == 227 and len(ms_study.pages) == 207 and full.summary() == ms.summary()
    assert full.n_tokens > ms_study.n_tokens
    ros = [L for L in full.lines if L['folio'] == 'fRos']
    assert len(ros) == 156 and sum(len(L['words']) for L in ros) == 530      # the 11 floating paragraphs plus labels and rings
    node = full.node('N:85-86')
    assert node['pages'].index('fRos') == node['pages'].index('f85r2') + 1
    assert full.physical['fRos']['section_name'] == 'Cosmological'
    b = load_bundle('strict', extra=True)
    v = validate_bundle(b)
    assert v['tokens'] == full.n_tokens and v['pages'] == 227
    assert b['detected_pages'] == ['fRos'] and len(b['detected_confidence']) >= 300
    boxed = sum(1 for L in b['lines'] if L['page'] == 'fRos' for i in range(L['start'], L['end']) if b['geometry'][i])
    assert boxed == len(b['detected_confidence'])
    det = [g for g in b['spatialReview']['groups'].values() if g.get('status') == 'detected']
    assert len(det) == boxed and all(g['page'] == 'fRos' for g in det)
    base = load_bundle('strict', pages='paragraph', order='path1', warp='recorded')
    assert len(base['words']) == 34977                                       # the study bundle is unchanged, by explicit option
