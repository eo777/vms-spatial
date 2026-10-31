import pytest

from conftest import needs_data

from vmsspatial.geometry import line_frames, line_units, line_breaks


def _toy():
    # one page, one line of five words; the median box is 20 wide, so the gap rule is 40
    ms = dict(lines=[dict(page=0, chars=20)], pages=[dict(index=0, start_line=0, end_line=1)])
    app = dict(words=list('abcde'), lines=[dict(start=0, end=5, page='p', locus='1')],
               geometry=[[0, 0, 20, 10], [25, 0, 45, 10], [50, 0, 70, 10], [200, 0, 220, 10], [225, 0, 245, 10]])
    return ms, app


def test_breaks_transcript_and_geometric():
    ms, app = _toy()
    boundaries = ['certain', 'intrusion_aligned', 'certain', 'certain', 'END']
    br = line_breaks(app, ms, line_frames(app, ms), boundaries)
    assert len(br) == 1
    assert [(r['left'], r['right'], r['transcript'], r['geometric'], r['adjacent']) for r in br[0]] == \
        [(1, 2, True, False, True), (2, 3, False, True, True)]
    assert br[0][1]['gap'] == (70.0, 200.0)
    assert line_breaks(app, ms)[0] == [br[0][1]]           # no boundaries, no review: geometric breaks only


def test_breaks_shared_box_and_missing_word():
    ms, app = _toy()
    app['geometry'][4] = app['geometry'][3]                 # d and e share one rectangle
    app['geometry'][2] = None                               # c has no rectangle
    units = line_units(app, ms)[0]
    assert [(u['first'], u['last']) for u in units] == [(0, 0), (1, 1), (3, 4)]
    boundaries = ['certain', 'certain', 'intrusion_misaligned', 'certain', 'END']
    br = line_breaks(app, ms, line_frames(app, ms), boundaries)[0]
    assert len(br) == 1 and br[0]['left'] == 1 and br[0]['right'] == 3     # the marker after the unlocated c joins b and d
    assert br[0]['transcript'] and br[0]['geometric']
    boundaries = ['certain', 'certain', 'certain', 'certain', 'intrusion_aligned']
    br = line_breaks(app, ms, line_frames(app, ms), boundaries)[0]
    assert any(r['transcript'] and r['right'] is None and r['left'] == 4 for r in br)   # a marker after the last located word


@needs_data
def test_breaks_on_the_manuscript(ms, sensitivity_recorded, ms_study, sensitivity_study):
    # the default shape: every page and locus; breaks and units are read on horizontal lines
    toks = sensitivity_recorded['spatialReview']['tokens']
    br = line_breaks(sensitivity_recorded, ms)
    assert len(br) == len(ms.lines) == 5365
    flat = [r for rs in br for r in rs]
    assert sum(1 for t in toks if t['boundary'].startswith('intrusion')) == 761
    assert sum(r['transcript'] for r in flat) == 749
    units = line_units(sensitivity_recorded, ms)
    assert sum(u['last'] - u['first'] + 1 for us in units for u in us) == 34625 and sum(len(us) for us in units) == 33614
    assert units.skipped['by_kind'] == {'unknown': 102, 'label': 921, 'circular': 83, 'radial': 141, 'rotated': 48}
    every = line_units(sensitivity_recorded, ms, orientations=None)
    assert sum(u['last'] - u['first'] + 1 for us in every for u in us) == 38605
    # the study shape
    toks = sensitivity_study['spatialReview']['tokens']
    br = line_breaks(sensitivity_study, ms_study)
    first = br[0]                                            # f27r line 1: ...shy<->shod...
    assert len(first) == 1 and toks[first[0]['left']]['text'] == 'shy' and toks[first[0]['right']]['text'] == 'shod'
    assert first[0]['transcript'] and first[0]['geometric']
    flat = [r for rs in br for r in rs]
    assert sum(1 for t in toks if t['boundary'].startswith('intrusion')) == 749
    assert sum(r['transcript'] for r in flat) == 749
    units = line_units(sensitivity_study, ms_study)
    assert sum(u['last'] - u['first'] + 1 for us in units for u in us) == 34625                        # every located token of a horizontal line in one unit
    assert sum(len(us) for us in units) == 33614                                                       # shared boxes once each
    assert units.skipped['by_kind'] == {'unknown': 12, 'rotated': 48}
    every = line_units(sensitivity_study, ms_study, orientations=None)
    assert sum(u['last'] - u['first'] + 1 for us in every for u in us) == 34876 and sum(len(us) for us in every) == 33858
