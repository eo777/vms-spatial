import numpy as np
import pytest
from collections import Counter

from conftest import needs_data

from vmsspatial.manuscript import Manuscript, tokenize, transitions, group_labels, load_order


@needs_data
def test_default_manuscript_is_every_recorded_locus_by_bifolium(ms):
    s = ms.summary()
    assert (s['bifolia'], s['pages'], s['lines'], s['tokens']) == (52, 227, 5365, 38876)
    assert s['order'] == 'bifolia' and s['page_set'] == 'all'
    assert ms.nodes[0]['id'] == 'A:1-8' and ms.nodes[0]['pages'] == ['f1r', 'f1v', 'f8r', 'f8v']
    assert [p['folio'] for p in ms.pages[:8]] == ['f1r', 'f1v', 'f8r', 'f8v', 'f2r', 'f2v', 'f7r', 'f7v']
    assert ms.lines[0]['folio'] == 'f1r' and ms.lines[0]['locus_type'] == 'P0'
    assert {L['locus_type'][0] for L in ms.lines} == {'P', 'L', 'C', 'R'}
    assert sum(L['first'] for L in ms.lines) == 1464
    assert all(ms.lines[p['end_line'] - 1]['final'] for p in ms.pages)
    leaves = [min(ms.physical[q]['leaf'] for q in n['pages']) for n in ms.nodes]
    assert leaves == sorted(leaves)


@needs_data
def test_study_shape_counts(ms_study):
    """The shape of the October 2026 studies, by explicit option: the published numbers."""
    s = ms_study.summary()
    assert (s['bifolia'], s['pages'], s['lines'], s['tokens']) == (50, 207, 4130, 34977)
    assert s['order'] == 'path1' and s['page_set'] == 'paragraph'
    assert ms_study.nodes[0]['id'] == 'D:27-30' and ms_study.nodes[0]['pages'] == ['f27r', 'f27v', 'f30r', 'f30v']
    assert sum(L['first'] for L in ms_study.lines) == 740                     # paragraph starts
    assert all(ms_study.lines[p['end_line'] - 1]['final'] for p in ms_study.pages)
    assert all(ms_study.lines[p['start_line']]['first'] for p in ms_study.pages)
    assert Manuscript.load(extra=False, order='path1').summary() == s         # the older spelling


@needs_data
def test_sheet_orders_keep_bifolia_together():
    for order in ('bifolia', 'path1'):
        m = Manuscript.load(order, pages='paragraph')
        assert len(m.nodes) == 50 and m.n_tokens == 34977
        assert {n['id'] for n in m.nodes} == {n['id'] for n in load_order('path1')}
        for n in m.nodes:
            pages = [p['folio'] for p in m.pages if p['node'] == n['id']]
            assert pages == n['pages']
        full = Manuscript.load(order)
        assert len(full.nodes) == 52 and full.n_tokens == 38876
    sheets = Manuscript.load('bifolia', pages='paragraph')
    leaves = [min(sheets.physical[q]['leaf'] for q in n['pages']) for n in sheets.nodes]
    assert leaves == sorted(leaves)
    with pytest.raises(ValueError):
        Manuscript.load(pages='labels')
    with pytest.raises(ValueError):
        Manuscript.load('quire')


@needs_data
def test_folio_is_the_page_sequence(ms):
    pages = Manuscript.load('folio')
    seq = [p['folio'] for p in pages.pages]
    assert seq[:6] == ['f1r', 'f1v', 'f2r', 'f2v', 'f3r', 'f3v'] and len(seq) == 227 and sorted(seq) == sorted(p['folio'] for p in ms.pages)
    assert seq.index('f72r1') < seq.index('f72r2') < seq.index('f72r3') < seq.index('f72v1')
    assert pages.n_tokens == ms.n_tokens and len(pages.nodes) == len(ms.nodes)
    # a sheet is a label: its pages lie apart in page order, its words are the same words
    assert pages.page('f8r')['node'] == 'A:1-8' and pages.page('f8r')['order_in_node'] == 2
    apart, together = pages.bifolium_ranges(), ms.bifolium_ranges()
    assert len(apart['A:1-8']) == 2 and together['A:1-8'] == [(0, sum(e - s for s, e in apart['A:1-8']))]
    assert all(len(r) == 1 for r in together.values())
    words_a, words_b = pages.words(), ms.words()
    for node in ('A:1-8', 'T:103-116', 'N:85-86'):
        assert Counter(w for s, e in apart[node] for w in words_a[s:e]) == Counter(w for s, e in together[node] for w in words_b[s:e])


@needs_data
def test_tokenize_and_transitions(ms, ms_study):
    tok = tokenize(ms_study)
    assert len(tok['words']) == 34977 and tok['since_par'][0] == 0
    assert (tok['pos'] < tok['linelen']).all()
    tr = transitions(ms_study)
    assert Counter(t['cls'] for t in tr) == {'same-face': 64, 'flip': 93, 'cross-sheet': 49}
    full = tokenize(ms)
    assert len(full['words']) == 38876 and (full['pos'] < full['linelen']).all()
    assert len(transitions(ms)) == 226


def test_group_labels():
    assert group_labels(['3c', '4c', '4a'], sep='|') == ['3c|Stars', '4c', '4a|Bio']
