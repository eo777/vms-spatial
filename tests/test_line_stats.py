"""Line statistics: every sign convention on synthetic lines and a synthetic page, the real tables, the published numbers."""
import csv
import re

import numpy as np
import pytest

from conftest import TOOLKIT, needs_data

from vmsspatial import frames, line_stats as S
from vmsspatial.compare import Records


# ----------------------------------------------------------------------------- synthetic lines
def test_a_line_falling_to_the_right_has_a_positive_chord():
    r = S.line_shape([0, 100, 200, 300, 400], [10, 12, 14, 16, 18], 20)
    assert r['chord'] == pytest.approx(np.degrees(np.arctan(8 / 400))) and r['chord'] > 0
    assert r['offset'] == pytest.approx(0.4) and r['ls_angle'] == pytest.approx(r['chord']) and r['fit_rms'] == pytest.approx(0, abs=1e-12)
    assert S.line_shape([0, 100, 200, 300, 400], [18, 16, 14, 12, 10], 20)['chord'] < 0


def test_a_word_below_the_line_has_a_positive_residual():
    r = S.line_shape([0, 100, 200, 300, 400], [10, 10, 14, 10, 10], 20)
    assert r['resid_chord'][2] == pytest.approx(0.2) and r['resid_chord'][0] == 0 and r['resid_fit'][2] > 0
    assert r['max_u'] == pytest.approx(0.5) and r['fit_max'] == pytest.approx(abs(r['resid_fit'][2]))
    assert S.line_shape([0, 100, 200, 300, 400], [10, 10, 6, 10, 10], 20)['resid_chord'][2] < 0


def test_a_line_whose_middle_is_lower_on_the_page_has_a_positive_sag():
    H, drop = 20.0, 6.0
    x = np.linspace(0, 400, 9)
    u = x / 400
    y = 100 + 4 * drop * u * (1 - u)                     # y grows down the page: the middle lies `drop` px below the ends
    r = S.line_shape(x, y, H)
    assert r['sag'] == pytest.approx(drop / H) and r['sag'] > 0
    assert r['quad_c'] == pytest.approx(-4 * drop / H) and r['sag'] == pytest.approx(-r['quad_c'] / 4)     # the study's c < 0 is a sag
    assert S.line_shape(x, 100 - 4 * drop * u * (1 - u), H)['sag'] == pytest.approx(-drop / H)
    assert r['half_diff'] < 0                                                                                # falling, then rising


def test_steady_lines_accumulate_and_jumps_concentrate():
    x = np.arange(0.0, 800.0, 100.0)
    rise = S.line_shape(x, 100 - 0.05 * x, 10)
    fall = S.line_shape(x, 100 + 0.05 * x, 10)
    assert fall['rho'] == pytest.approx(1) and rise['rho'] == pytest.approx(-1) and fall['mid_share'] == pytest.approx(0.5, abs=1e-9)
    assert fall['jitter'] == pytest.approx(0.5) and fall['jump_share'] == pytest.approx(1 / 7) and fall['step_conc'] == pytest.approx(1)
    one_step = S.line_shape(x, np.array([0, 0, 0, 0, 10, 10, 10, 10.0]), 10)
    assert one_step['jump_share'] == pytest.approx(1) and one_step['jitter'] == 0
    assert S.line_shape(x, np.full(8, 5.0), 10)['rho'] is None                       # nothing to rank
    assert S.line_shape(x, 100 + 0.001 * x, 10)['mid_share'] is None                 # under 0.5 H of offset


def test_small_lines_report_what_they_can_support():
    one, two, three = S.line_shape([5], [1], 10), S.line_shape([0, 10], [0, 1], 10), S.line_shape([0, 10, 20], [0, 1, 3], 10)
    assert one['chord'] is None and two['chord'] is not None and two['ls_angle'] is None
    assert three['ls_angle'] is not None and three['sag'] is None and three['rho'] is None
    assert S.line_shape([3, 3, 3], [0, 1, 2], 10)['chord'] is None                   # no span


def test_a_break_step_is_positive_when_the_right_side_lies_lower():
    r = S.break_step([0, 1, 2], [0, 0, 0], [3, 4, 5], [5, 5, 5], 1.0)
    assert r['step'] == pytest.approx(5) and r['step_lr'] == pytest.approx(5) and r['step_rl'] == pytest.approx(5)
    assert S.break_step([0, 1, 2], [5, 5, 5], [3, 4, 5], [0, 0, 0], 1.0)['step'] == pytest.approx(-5)
    tilted = S.break_step([0, 1, 2], [0, 1, 2], [3, 4, 5], [3, 4, 5], 1.0)
    assert tilted['step'] == pytest.approx(0, abs=1e-9)                              # a steady slope has no step
    assert S.break_step([0], [0], [1], [0], 1.0)['step'] is None and S.break_step([0], [0], [1], [0], 1.0)['fit_left'] is None


def test_the_keys_are_described():
    for k, d in S.KEYS.items():
        assert d['label'] and len(d['label'].split()) <= 3 and d['kind'] in ('sequential', 'diverging') and d['per'] in ('token', 'line', 'page')
        assert d['description'].endswith('.'), k
    assert 'recorded frame' in S.KEYS['intrusion_depth']['description'].lower() and '5 of 36' in S.KEYS['intrusion_depth']['description']
    assert set(S.KEYS) & {'kind', 'line', 'paragraph'} == set()                      # plot.plot_page's colour modes stay free


# ----------------------------------------------------------------------------- a synthetic page, through the whole pipeline
@pytest.fixture(scope='module')
def synthetic():
    """f68r1 has no fitted field, so flat = recorded there; its three long lines are redrawn: one falling, one sagging, one
    with a word below the line. Box height 20 px, anchors = box bottoms."""
    from vmsspatial import Manuscript, load_bundle
    from vmsspatial.geometry import line_units
    ms = Manuscript.load()
    app = load_bundle('sensitivity', warp='recorded')
    app = dict(app, geometry=list(app['geometry']))
    p = ms.page('f68r1')
    units = line_units(app, ms)
    lines = [l for l in range(p['start_line'], p['end_line']) if len(units[l]) >= 8]
    assert len(lines) == 3 and all(app['lines'][l]['orientation']['kind'] == 'horizontal' for l in lines)

    def place(l, bottoms):
        for k, (u, y) in enumerate(zip(units[l], bottoms)):
            for t in range(u['first'], u['last'] + 1):
                app['geometry'][t] = [100.0 + 60 * k, y - 20.0, 140.0 + 60 * k, y]
    place(lines[0], [300.0 + 3 * k for k in range(len(units[lines[0]]))])
    n = len(units[lines[1]])
    place(lines[1], [500.0 + 80.0 * (k / (n - 1)) * (1 - k / (n - 1)) for k in range(n)])           # the middle 20 px = 1 H lower than the ends
    place(lines[2], [700.0 + (10.0 if k == 3 else 0.0) for k in range(len(units[lines[2]]))])
    return dict(app=app, ms=ms, lines=lines, units=units, table=S.line_table(app, ms, baseline='bottom'), words=S.word_table(app, ms, baseline='bottom'))


@needs_data
@pytest.mark.slow
def test_the_signs_on_a_synthetic_page(synthetic):
    by_line = {r['line']: r for r in synthetic['table']}
    a, b, c = (by_line[l] for l in synthetic['lines'])
    assert a['H_px'] == 20.0
    assert a['chord_flat'] == pytest.approx(np.degrees(np.arctan(3 / 60))) and a['chord_flat'] > 0 and a['chord_recorded'] == pytest.approx(a['chord_flat'])
    assert a['offset'] > 0 and a['abs_offset'] == a['offset'] and a['offset'] == pytest.approx(a['offset_recorded'])
    assert b['sag'] == pytest.approx(1.0, abs=0.02) and b['quad_c'] == pytest.approx(-4 * b['sag']) and b['chord_flat'] == pytest.approx(0, abs=1e-9)
    assert c['max_u'] == pytest.approx(3 / 7)
    below = [w for w in synthetic['words'] if w['line'] == synthetic['lines'][2]]
    assert below[3]['resid_chord'] == pytest.approx(0.5) and below[3]['resid_fit'] > 0 and below[0]['resid_chord'] == 0


@needs_data
@pytest.mark.slow
def test_a_page_without_a_fitted_field(synthetic):
    rows = [r for r in synthetic['table'] if r['folio'] == 'f68r1']
    assert rows and all(r['page_flattened'] == 0 and r['page_warp_amplitude'] is None and r['page_tilt'] is None and r['warp_mean'] is None for r in rows)
    assert all(r['chord_flat'] == r['chord_recorded'] for r in rows if r['chord_flat'] is not None)
    assert all(w['warp_shift'] is None for w in synthetic['words'] if w['folio'] == 'f68r1')


# ----------------------------------------------------------------------------- the real tables
@pytest.fixture(scope='module')
def stats():
    return S.compute()


@pytest.fixture(scope='module')
def built():
    from vmsspatial.viewer_measures import builtin
    return builtin(log=None)


@needs_data
@pytest.mark.slow
def test_the_tables_cover_the_manuscript(stats, tmp_path):
    lines, words = S.line_table(), S.word_table()
    assert isinstance(lines, Records) and isinstance(words, Records)
    assert len(lines) == sum(1 for r in stats['lines'] if r) == 4070 and len(words) == 37478
    assert lines.meta['skipped'] == {'unknown': 102, 'label': 921, 'circular': 83, 'radial': 141, 'rotated': 48}
    assert set(lines[0]) == set(S.LINE_COLUMNS) and set(words[0]) == set(S.WORD_COLUMNS)
    assert lines['n_rows'] == 4070 and 'horizontal line' in lines.describe()
    path = tmp_path / 'lines.csv'
    lines.to_csv(path)
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    assert len(rows) == 4070 and rows[0]['folio'] == lines[0]['folio'] and float(rows[0]['chord_flat']) == pytest.approx(lines[0]['chord_flat'])
    words.to_csv(tmp_path / 'words.csv')
    assert frames.tags(lines)['warp'] == 'flat' and frames.tags(lines)['frame'] == 'recorded' and frames.tags(words)['source'] == 'voynichese'
    from vmsspatial import load_bundle
    frames.require_same(lines, load_bundle('strict'), 'the table and a flat bundle')
    with pytest.raises(frames.FrameError):
        frames.require_same(lines, load_bundle('strict', warp='recorded'), 'the table and a recorded bundle')


@needs_data
@pytest.mark.slow
def test_a_flat_bundle_gives_the_same_numbers(stats):
    from vmsspatial import Manuscript, load_bundle
    ms = Manuscript.load()
    other = S.compute(load_bundle('sensitivity'), ms)
    a = [r for r in stats['lines'] if r and r['chord_flat'] is not None]
    b = [r for r in other['lines'] if r and r['chord_flat'] is not None]
    assert len(a) == len(b)
    for k in ('chord_flat', 'chord_recorded', 'offset'):
        assert np.max(np.abs(np.array([r[k] for r in a]) - np.array([r[k] for r in b]))) < 0.02


@needs_data
@pytest.mark.slow
def test_the_arrays_of_the_viewer_fields(stats, built):
    n, nl = stats['n_tokens'], stats['n_lines']
    assert n == 38876 and nl == 5365 and len(built['anchors']) == n and len(built['line_notes']) == nl
    horizontal = [r is not None for r in stats['lines']]
    for k, m in built['measures'].items():
        assert S.KEYS[k]['label'] == m['label'] and m['group'] == S.GROUP
        if 'values' in m:
            assert len(m['values']) == n
            continue
        assert len(m['line_values']) == nl
        if S.KEYS[k]['per'] == 'line':
            assert all(v is None for v, h in zip(m['line_values'], horizontal) if not h), k        # non-horizontal lines have no value
    assert all(n is None for n, h in zip(built['line_notes'], horizontal) if not h)
    # the warp columns of the pages without a fitted field
    unfitted = {f for f, p in stats['pages'].items() if not p['fitted']}
    assert len(unfitted) == 22
    shift, flattened = built['measures']['warp_shift']['values'], built['measures']['page_flattened']['line_values']
    for l, line in enumerate(stats['rec']['lines']):
        assert (flattened[l] == 0) == (line['page'] in unfitted)
        if line['page'] in unfitted:
            assert all(shift[t] is None for t in range(line['start'], line['end']))
    assert sum(1 for v in shift if v is not None) > 30000
    # every overlay in recorded coordinates; flat beside it where the two differ
    for key, o in built['overlays'].items():
        assert o['frame'] == 'recorded' and o['warp'] == 'recorded', key
        frames.require_recorded(o, key)
    assert {i['style'] for i in built['overlays']['breaks']['items']} <= {'break-transcript', 'break-geometric', 'break-both'}
    assert {i['style'] for i in built['overlays']['break_fits']['items']} == {'fit', 'fit-ext'}
    assert all(i['kind'] == 'polyline' for k in ('chords', 'fits', 'warp', 'breaks', 'break_fits', 'ink_fits') for i in built['overlays'][k]['items'])
    assert {'points_flat' in i for i in built['overlays']['chords']['items'] if i['page'] not in unfitted} == {True}
    assert {'points_flat' in i for i in built['overlays']['chords']['items'] if i['page'] in unfitted} == {False}    # flat = recorded there
    straight = [i for i in built['overlays']['warp']['items'] if i['style'] == 'warp-flat']
    assert straight and all(i['states'] == ['recorded'] for i in straight)


@needs_data
@pytest.mark.slow
def test_a_warped_curve_is_straight_in_the_flat_state(stats):
    assert len(stats['warp_curves']) == 3984
    worst, bowed = 0.0, 0
    for c in stats['warp_curves']:
        slope, icpt = np.polyfit(c['x'], c['flat'], 1)
        worst = max(worst, float(np.max(np.abs(c['flat'] - (slope * c['x'] + icpt)))))
        bowed += float(np.ptp(c['warped'] - c['straight'])) > 1.0
    assert worst < 1e-9                                                                # pixels: the shift is the field that bowed the curve
    assert bowed > 1000                                                                # and the field was there to remove


@needs_data
@pytest.mark.slow
def test_intrusions_are_events_of_positive_depth(stats, built):
    from vmsspatial.ink import intrusions, load_ink
    ev = stats['intrusions']
    assert ev and all(e['depth_H'] > 0 for e in ev)
    everything = intrusions(stats['rec'], stats['ms'], load_ink())
    assert sum(1 for e in everything if e['depth_H'] <= 0) > 0                         # the near misses the product lists are left out
    assert min(v for v in built['measures']['intrusion_depth']['values'] if v is not None) >= 0
    deep = max(ev, key=lambda e: e['depth_H'])
    w = {r['first']: r for r in stats['words']}
    assert w[deep['upper_token']]['intrusion_depth'] == pytest.approx(deep['depth_H']) and w[deep['lower_token']]['intrusion_depth'] == pytest.approx(deep['depth_H'])
    assert {i['style'] for i in built['overlays']['intrusions']['items']} == {'intrusion', 'intrusion-touch'}


# ----------------------------------------------------------------------------- the published numbers
@needs_data
@pytest.mark.slow
def test_the_published_numbers_on_the_study_lines():
    """The paragraph lines with at least 4 located rectangles spanning 3 median word widths, outside the pages with
    rotated paragraphs, in the study shape (3,773 lines). Default anchors ('auto'): 0.50 deg, 0.18 H and a line-median RMS
    of 0.08 H flat on the ink baseline, 1.34 deg recorded; the ink baseline 0.190 H above the box bottom over 28,484 clean
    words."""
    from vmsspatial import Manuscript, load_bundle
    from vmsspatial.audit.flags import QUARANTINE
    ms = Manuscript.load(pages='paragraph', order='path1')
    app = load_bundle('sensitivity', pages='paragraph', order='path1', warp='recorded')
    lines = S.line_table(app, ms)
    q = [r for r in lines if r['n_anchors'] >= 4 and (r['span_W'] or 0) >= 3 and r['folio'] not in QUARANTINE and r['chord_flat'] is not None]
    assert len(q) == 3773
    med = lambda k, f=abs: float(np.median([f(r[k]) for r in q if r[k] is not None]))
    assert med('chord_flat') == pytest.approx(0.50, abs=0.01)
    assert med('chord_recorded') == pytest.approx(1.34, abs=0.02)
    assert med('offset') == pytest.approx(0.18, abs=0.005)
    assert med('fit_rms', float) == pytest.approx(0.08, abs=0.003)
    assert med('quad_c', float) == pytest.approx(-0.01, abs=0.01)                      # the sag of the recorded rectangles is gone
    words = [w for w in S.word_table(app, ms) if w['baseline_shift'] is not None and w['folio'] not in QUARANTINE]
    assert len(words) == 28484
    assert float(np.median([w['baseline_shift'] for w in words])) == pytest.approx(-0.190, abs=0.001)
    assert float(np.median([w['ink_shift'] for w in words])) == pytest.approx(-0.094, abs=0.001)


# ----------------------------------------------------------------------------- the route from code
@needs_data
@pytest.mark.slow
def test_the_worked_example_in_the_docs(tmp_path, monkeypatch):
    pytest.importorskip('matplotlib')
    text = (TOOLKIT / 'docs' / 'PLOTTING.md').read_text(encoding='utf-8')
    block = re.search(r'## Line statistics.*?```python\n(.*?)```', text, re.S).group(1)
    monkeypatch.chdir(tmp_path)
    namespace = {}
    exec(compile(block, 'docs/PLOTTING.md', 'exec'), namespace)
    assert (tmp_path / 'lines.csv').exists() and (tmp_path / 'words.csv').exists() and (tmp_path / 'f75r_residuals.png').stat().st_size > 1000
    assert len(namespace['study']) > 3000 and -2 < namespace['median_angle'] < 2


@needs_data
@pytest.mark.slow
def test_plot_page_takes_the_keys(sensitivity):
    matplotlib = pytest.importorskip('matplotlib')
    matplotlib.use('Agg')
    from vmsspatial import plot as P
    ax = P.plot_page('f75r', bundle=sensitivity, color_by='resid_chord', show=('boxes',))
    assert 'Chord residual' in ax.get_title(loc='left') and len(ax.patches) == 418
    matplotlib.pyplot.close(ax.figure)
    ax = P.plot_page('f75r', bundle=sensitivity, color_by='page_flattened', show=('boxes',))
    matplotlib.pyplot.close(ax.figure)
    with pytest.raises(ValueError):
        P.plot_page('f75r', bundle=sensitivity, color_by='not_a_key')
    with pytest.raises(ValueError):
        S.token_values('not_a_key')
