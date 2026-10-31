import numpy as np
import pytest

from conftest import needs_data

from vmsspatial.geometry import line_frames, oversized_flags, vertical_gaps, place_in_slot, fill_slots, synthetic_geometry, PageGeometry, Layout
from vmsspatial.layout_check import overlaps, width_error


@needs_data
def test_frames_and_flags_default_shape(ms, sensitivity_recorded, strict):
    flags = oversized_flags(sensitivity_recorded, ms)
    assert sum(flags) == 38876 - 38605                              # a reviewed bundle's mask: what has no box under its policy
    assert sum(oversized_flags(strict, ms)) == 38876 - 35613       # the strict mask excludes what has no word-level box
    frames = line_frames(sensitivity_recorded, ms)
    assert len(frames) == 5365 and sum(f is None for f in frames) == 1295
    assert frames.skipped == {'skipped_lines': 1295, 'by_kind': {'unknown': 102, 'label': 921, 'circular': 83, 'radial': 141, 'rotated': 48}}
    assert frames.frame_tags['warp'] == 'recorded'
    v = vertical_gaps(sensitivity_recorded, ms, flags)
    f29r = ms.page('f29r')
    assert any(l in v for l in range(f29r['start_line'], f29r['end_line']))      # the plant stem splits lines of f29r
    assert len(v) == 595


@needs_data
def test_frames_and_flags_study_shape(ms_study, sensitivity_study, strict_study):
    flags = oversized_flags(sensitivity_study, ms_study)
    assert sum(flags) == 34977 - 34876
    assert sum(oversized_flags(strict_study, ms_study)) == 34977 - 32319
    frames = line_frames(sensitivity_study, ms_study)
    assert len(frames) == 4130 and sum(f is None for f in frames) == 60      # 12 lines whose words all lack a usable rectangle + 48 rotated lines (no frame: not horizontal text)
    assert frames.skipped == {'skipped_lines': 60, 'by_kind': {'unknown': 12, 'rotated': 48}}
    assert sum(f is None for f in line_frames(sensitivity_study, ms_study, orientations=None)) == 12
    assert len(vertical_gaps(sensitivity_study, ms_study, flags)) == 580


@needs_data
def test_synthetic_geometry_is_pinned(ms, sensitivity_recorded, ms_study, sensitivity_study):
    frames = line_frames(sensitivity_recorded, ms)
    lines = ms.line_words()
    before = [len(ws) for ws in lines]
    geom = synthetic_geometry(lines, frames, ms)
    assert sum(max(0, a - len(ws)) for a, ws in zip(before, lines)) == 758
    assert sum(1 for g in geom if not g) == 4298                  # labels, rings, radial and rotated words are not typeset into a horizontal frame
    assert overlaps(geom, lines, ms) == 1371
    w = width_error(ms, frames, lines, geom)
    assert w['off_1p5'] < 0.002 and w['boxed'] == 34578
    # the study shape (its published layout numbers)
    frames = line_frames(sensitivity_study, ms_study)
    lines = ms_study.line_words()
    before = [len(ws) for ws in lines]
    geom = synthetic_geometry(lines, frames, ms_study)
    assert sum(max(0, a - len(ws)) for a, ws in zip(before, lines)) == 797
    assert sum(1 for g in geom if not g) == 310                   # the words of the lines without a frame, the 48 rotated lines among them
    assert overlaps(geom, lines, ms_study) == 1391
    w = width_error(ms_study, frames, lines, geom)
    assert w['off_1p5'] < 0.002 and w['boxed'] == 34667


def test_place_in_slot_segments():
    fr = (0.0, 0.0, 100.0, 10.0, [(0.0, 30.0), (50.0, 100.0)], np.array([15.0, 75.0]), np.array([0.0, 0.0]), np.array([10.0, 10.0]))
    placed, boxes = place_in_slot(['ab', 'cd', 'efgh', 'ij'], fr, 5.0)
    assert placed == 4
    assert boxes[0][0] == 0 and boxes[1][0] == 15                 # 2 chars + 1 gap at width 5
    assert boxes[2][0] == 50                                      # efgh does not fit before the drawing; continues after it
    assert boxes[3][0] == 75
    placed, boxes = place_in_slot(['abcdefghijklmnopqrstuvwxyz'], fr, 5.0)
    assert placed == 1 and boxes[0][0] == 50                      # a word longer than every segment is forced into the widest


@needs_data
@pytest.mark.slow
def test_incremental_layout_equals_fill_slots(ms_study, sensitivity_study):
    ms, sensitivity = ms_study, sensitivity_study
    geo = PageGeometry(ms, sensitivity)
    lay = Layout(geo)
    pos = 0
    for l, L in enumerate(ms.lines):
        for w in L['words']:
            lay.add(pos, w, l)
            pos += 1
    lay.finish()
    lines = ms.line_words()
    geom = synthetic_geometry(lines, line_frames(sensitivity, ms), ms)
    inc = lay.geometry_in_order(pos)
    same = sum(1 for a, b in zip(inc, geom) if (a is None and b is None) or (a is not None and b is not None and np.allclose(a, b)))
    assert same == len(geom)
