"""Word labels follow the writing: orientation.label_angle against its JavaScript twin, and the plot functions' labels."""
import json
import shutil
import subprocess

import pytest

from conftest import TOOLKIT, needs_data

from vmsspatial.orientation import label_angle, upright


def test_the_clock_convention():
    ring = dict(kind='circular', word_angles=[0.0, 90.0, 180.0, -90.0, None])
    assert [label_angle(ring, j) for j in range(5)] == [0.0, 90.0, 180.0, -90.0, None]
    assert label_angle(ring, 9) is None                                   # past the end, as undefined is in JavaScript


def test_every_rule():
    assert label_angle(None, 0) == 0 and label_angle({}, 0) == 0
    assert label_angle(dict(kind='horizontal', angle_deg=1.5), 0) == 0 and label_angle(dict(kind='unknown'), 0) == 0
    assert label_angle(dict(kind='circular'), 0) is None                  # a ring that failed the wheel screens
    assert label_angle(dict(kind='rotated', angle_deg=-65.0), 3) == -65.0 and label_angle(dict(kind='rotated'), 0) is None
    assert label_angle(dict(kind='radial', angle_deg=40.0, word_angles=[120.0]), 0) == 40.0                   # the chord wins over the ray
    assert label_angle(dict(kind='radial', word_angles=[120.0]), 0) == -60.0 and label_angle(dict(kind='radial', word_angles=[None]), 0) is None
    assert label_angle(dict(kind='label', angle_deg=29.0), 0) == 0 and label_angle(dict(kind='label', angle_deg=-30.0), 0) == -30.0 and label_angle(dict(kind='label'), 0) == 0
    assert [upright(a) for a in (0, 45, 90, 135, -135, 180, -90, 270)] == [0, 45, 90, -45, 45, 0, 90, 90]


@needs_data
def test_a_ring_reads_clockwise_on_f72r1(ms, sensitivity):
    from vmsspatial.orientation import attach
    attach(sensitivity, ms)
    p = ms.page('f72r1')
    seen = {}
    for l in range(p['start_line'], p['end_line']):
        L = sensitivity['lines'][l]
        o = L['orientation']
        if o['kind'] != 'circular' or o.get('centre') is None or not o.get('clockwise'):
            continue
        for i in range(L['start'], L['end']):
            b, j = sensitivity['geometry'][i], i - L['start']
            assert label_angle(o, j) == o['word_angles'][j]
            if not b:
                continue
            x, y = (b[0] + b[2]) / 2 - o['centre'][0], (b[1] + b[3]) / 2 - o['centre'][1]
            for clock, want, near in ((12, 0, -y > 5 * abs(x)), (3, 90, x > 5 * abs(y)), (6, 180, y > 5 * abs(x)), (9, -90, -x > 5 * abs(y))):
                if near:
                    got = label_angle(o, j)
                    seen[clock] = seen.get(clock, 0) + 1
                    assert abs((got - want + 180) % 360 - 180) < 15, (clock, got)
    assert set(seen) == {12, 3, 6, 9} and min(seen.values()) >= 3


@needs_data
@pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')
def test_the_same_rule_as_the_browser_on_every_token(ms, sensitivity, tmp_path):
    from vmsspatial.orientation import attach
    attach(sensitivity, ms)
    lines = [dict(orientation=L['orientation'], n=L['end'] - L['start']) for L in sensitivity['lines']]
    path = tmp_path / 'lines.json'
    path.write_text(json.dumps(lines), encoding='utf-8')
    script = "const W=require(%s),fs=require('fs');const lines=JSON.parse(fs.readFileSync(%s,'utf8'));console.log(JSON.stringify(lines.map(L=>Array.from({length:L.n},(_,j)=>W.angleOf(L.orientation,j)))))" % (
        json.dumps(str(TOOLKIT / 'viewer' / 'js' / 'word_labels.js')), json.dumps(str(path)))
    out = json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)
    turned = 0
    for L, angles in zip(lines, out):
        for j, a in enumerate(angles):
            mine = label_angle(L['orientation'], j)
            assert (mine is None) == (a is None), (L['orientation'], j)
            assert a is None or abs(mine - a) < 1e-9, (L['orientation'], j)         # the two wraps differ in the last bits only
            turned += a != 0
    assert turned > 3000


def _rotations(ax):
    return [t.get_rotation() for t in ax.texts]


@needs_data
@pytest.mark.slow
def test_the_plots_write_along_the_writing(sensitivity):
    matplotlib = pytest.importorskip('matplotlib')
    matplotlib.use('Agg')
    from vmsspatial import plot as P
    from vmsspatial.bundle import load_bundle
    recorded = load_bundle('sensitivity', warp='recorded')
    ring = P.plot_page('f72r1', bundle=sensitivity, show=('boxes',), labels=True)
    level = P.plot_page('f72r1', bundle=sensitivity, show=('boxes',), labels=True, word_direction='level')
    assert len(ring.texts) == len(level.texts) > 50
    assert set(_rotations(level)) == {0.0} and len(set(_rotations(ring))) > 20
    assert all(t.get_rotation_mode() == 'anchor' for t in ring.texts)
    assert [t.get_position() for t in ring.texts] == [t.get_position() for t in level.texts]      # the labels turn, they do not move
    paragraph = P.plot_page('f75r', bundle=sensitivity, show=('boxes',), labels=True)
    assert sum(1 for r in _rotations(paragraph) if r) < len(paragraph.texts) / 4      # level text stays level
    wheel = P.plot_wheel('f72r1', bundle=recorded)
    assert len(set(_rotations(wheel))) > 20
    assert set(_rotations(P.plot_wheel('f72r1', bundle=recorded, word_direction='level'))) == {0.0}
    centred = P.plot_centered_wheels('f72r1', bundle=recorded, labels=True)
    assert len(set(_rotations(centred))) > 20
    assert set(_rotations(P.plot_centered_wheels('f72r1', bundle=recorded, labels=True, word_direction='level'))) == {0.0}
    with pytest.raises(ValueError):
        P.plot_page('f72r1', bundle=sensitivity, word_direction='sideways')
    matplotlib.pyplot.close('all')
