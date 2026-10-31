"""A study's viewer data: a bundle with its own measures, overlays and line notes, read by the toolkit's atlas."""
import json

import pytest

from conftest import needs_data

from vmsspatial.bundle import read_json
from vmsspatial.viewer_data import study_data, measure, line_measure, per_line, overlay, overlay_item, default_palette


def test_measure_and_overlay_constructors():
    m = measure('Word length', [1, 2.5, None, float('nan')], unit='glyphs', kind='sequential', digits=0, domain=(0, 10))
    assert m['values'] == [1.0, 2.5, None, None] and m['domain'] == [0.0, 10.0] and m['digits'] == 0
    with pytest.raises(ValueError):
        measure('x', [1], kind='other')
    assert measure('x', [1], per='line')['per'] == 'line' and m['per'] == 'token'
    with pytest.raises(ValueError):
        measure('x', [1], per='page')
    it = overlay_item('f1r', [(0, 0), (10, 2.5)], style='chord', title='t', line=3)
    assert it == dict(page='f1r', points=[[0.0, 0.0], [10.0, 2.5]], style='chord', kind='polyline', title='t', line=3)
    with pytest.raises(ValueError):
        overlay('bad', [dict(page='f1r')])
    assert len(default_palette()) == 501 and default_palette()[0].startswith('#')


def test_line_measure_and_the_new_overlay_fields():
    m = line_measure('Tilt', [1.5, None, float('nan')], unit='deg', kind='diverging', digits=1, group='Lines', menu=False)
    assert m['line_values'] == [1.5, None, None] and 'values' not in m and m['per'] == 'line' and m['group'] == 'Lines' and m['menu'] is False
    assert 'menu' not in line_measure('x', [1.0]) and 'group' not in measure('x', [1.0]) and measure('x', [1.0], group='G')['group'] == 'G'
    it = overlay_item('f1r', [(0, 0)], kind='marker', points_flat=[(0, -2)], states=['recorded'], token=7, info=[1, 2])
    assert it['points_flat'] == [[0.0, -2.0]] and it['states'] == ['recorded'] and it['token'] == 7 and it['info'] == [1, 2]
    with pytest.raises(ValueError):
        overlay_item('f1r', [(0, 0)], states=['sideways'])
    o = overlay('Anchors', [], markers_from='anchors', r=2)
    assert o['markers_from'] == 'anchors' and o['r'] == 2.0 and o['items'] == []


@needs_data
def test_an_overlay_in_either_state_reaches_both(strict, tmp_path):
    """The atlas can draw a flat study bundle in both states, so a study's overlay carries both, whichever it was given in."""
    from vmsspatial import warp as W
    L = next(l for l in strict['lines'] if l['page'] == 'f75r' and l['orientation']['kind'] == 'horizontal')
    line = strict['lines'].index(L)
    other = next(k for k, l in enumerate(strict['lines']) if l['orientation']['kind'] == 'circular' and l['page'] == 'f72r1')
    recorded = overlay('Given recorded', [overlay_item('f75r', [[300, 400]], style='chord', line=line), overlay_item('f72r1', [[300, 400]], style='chord', line=other),
                                          overlay_item('f57v', [[300, 400]], style='chord')], frame='recorded', warp='recorded', source='voynichese')
    flat = overlay('Given flat', [overlay_item('f75r', [[300, 400]], style='chord', line=line)], frame='recorded', warp='flat', source='voynichese')
    measures = {'tilt': line_measure('Tilt', [0.5] * len(strict['lines']))}
    study_data(tmp_path, strict, 'study', 'Study test', measures=measures, overlays={'rec': recorded, 'flat': flat}, log=lambda s: None)
    b = read_json(tmp_path / 'study' / 'words.json.gz')
    moved, ring, unfitted = b['overlays']['rec']['items']
    assert moved['points'] == [[300.0, 400.0]] and moved['points_flat'][0][1] == pytest.approx(W.apply('f75r', 300.0, 400.0, str(L['locus']), 'flat')) and moved['points_flat'][0][1] != 400.0
    assert ring['points_flat'] == ring['points'] and unfitted['points_flat'] == unfitted['points']                 # the warp moves neither, as it moves neither's boxes
    item = b['overlays']['flat']['items'][0]
    assert item['points_flat'] == [[300.0, 400.0]] and item['points'][0][1] != 400.0 and b['overlays']['flat']['warp'] == 'recorded'
    assert b['measures']['tilt']['line_values'][0] == 0.5
    with pytest.raises(ValueError):
        study_data(tmp_path, strict, 'bad', 'bad', measures={'x': line_measure('x', [1.0])}, log=lambda s: None)


@needs_data
def test_study_data_writes_a_viewer_folder(strict, tmp_path):
    n = len(strict['words'])
    lengths = measure('Word length', [len(w) for w in strict['words']], unit='glyphs', digits=0)
    first_line = strict['lines'][0]
    page = first_line['page']
    tilt = measure('Line tilt', per_line(strict, [float(i % 7 - 3) for i in range(len(strict['lines']))]), unit='deg', kind='diverging')
    chords = overlay('Chords', [overlay_item(page, [[100, 100], [900, 140]], style='chord', title='first line'), overlay_item(page, [[500, 120]], style='baseline', kind='marker')])
    notes = [None] * len(strict['lines'])
    notes[0] = {'chord angle': 1.5, 'words': first_line['end'] - first_line['start']}
    index = study_data(tmp_path, strict, 'study', 'Study test', measures={'length': lengths, 'tilt': tilt}, overlays={'chords': chords}, line_notes=notes, log=lambda s: None)
    assert (tmp_path / 'index.json').exists() and (tmp_path / 'study' / 'words.json.gz').exists()
    b = read_json(tmp_path / 'study' / 'words.json.gz')
    assert b['measures']['length']['values'][:3] == [float(len(w)) for w in strict['words'][:3]]
    assert b['measures']['tilt']['values'][first_line['start']] == -3.0 and b['measures']['tilt']['kind'] == 'diverging'
    assert b['overlays']['chords']['items'][0]['page'] == page and b['line_notes'][0]['chord angle'] == 1.5 and b['palette']
    assert b['words'] == strict['words'] and b['geometry'] == strict['geometry']
    assert index['bundles'][0]['tokens'] == n and index['layout'] and index['review']
    saved = json.loads((tmp_path / 'index.json').read_text(encoding='utf-8'))
    assert saved == index
    with pytest.raises(ValueError):
        study_data(tmp_path, strict, 'bad', 'bad', measures={'x': measure('x', [1.0])}, log=lambda s: None)
    with pytest.raises(ValueError):
        study_data(tmp_path, strict, 'bad', 'bad', overlays={'o': overlay('o', [overlay_item('fNope', [[0, 0]])])}, log=lambda s: None)
