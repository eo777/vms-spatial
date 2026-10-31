import copy
from dataclasses import replace
import numpy as np
import pytest
try:
    from vmsspatial.verse_layout import VerseLayout,typeset_independent
except ImportError:
    from verse_layout import VerseLayout,typeset_independent
from vmsspatial.bundle import validate_bundle
from vmsspatial.selector import SpatialContext

def verses(n=110):
    return [dict(book='one' if i<90 else 'two',line=i,words=['aa','bb','ccc','ddd','eeee','ffff']*(1+i%4)) for i in range(n)]

def test_no_rewrapping_missing_words_or_mis_sized_boxes():
    v=verses();v[0]['words']=['longword']*100
    b=typeset_independent(v,VerseLayout(left_jitter=4,gap_jitter=.5,line_jitter=.12,line_scale_jitter=.1))
    validate_bundle(b);assert b['words']==[w for r in v for w in r['words']]
    assert len(b['lines'])==len(v) and b['audit']['max_character_width_ratio_error']<1e-12
    for r in b['lines']:
        g=b['geometry'][r['start']:r['end']]
        assert len(set(x[1] for x in g))==1
        assert all(a[2]<z[0] for a,z in zip(g,g[1:]))
    for a,z in zip(b['lines'],b['lines'][1:]):
        if a['page']==z['page']:assert b['geometry'][a['start']][3]<=b['geometry'][z['start']][1]
    assert SpatialContext(b).n==len(b['words'])

def test_actual_same_length_permutation_reproduces_every_box():
    v=verses();cfg=VerseLayout(left_jitter=4,gap_jitter=.5,line_jitter=.12,line_scale_jitter=.1)
    a=typeset_independent(v,cfg);vv=copy.deepcopy(v)
    for r in vv:r['words']=[{'aa':'bb','bb':'aa','ccc':'ddd','ddd':'ccc','eeee':'ffff','ffff':'eeee'}[w] for w in r['words']]
    b=typeset_independent(vv,cfg)
    assert a['words']!=b['words'] and a['geometry']==b['geometry'] and a['lines']==b['lines']

def test_page_and_book_boundaries_and_explicit_indentation():
    v=verses(3)
    for i,r in enumerate(v):r['source_page']='a' if i<2 else 'b'
    v[1].update(indent_chars=4,space_before_lines=2)
    b=typeset_independent(v,VerseLayout(lines_per_page=1))
    assert b['lines'][0]['page']==b['lines'][1]['page']!=b['lines'][2]['page']
    g0=b['geometry'][0];g1=b['geometry'][b['lines'][1]['start']]
    assert g1[0]-g0[0]==32 and g1[1]-g0[1]==60
    b=typeset_independent(verses(),VerseLayout(lines_per_page=48))
    assert len(b['page_layout'])==3

def test_fixed_width_fails_instead_of_splitting_or_shrinking():
    with pytest.raises(ValueError,match='never wrap'):typeset_independent(verses(),VerseLayout(page_width_chars=20))

@pytest.mark.parametrize('kw',[dict(gap_jitter=1),dict(line_jitter=.2),dict(left_jitter=7),dict(char_width=0),dict(lines_per_page=0),dict(line_pitch=float('nan'))])
def test_unsafe_dispersion_is_rejected(kw):
    with pytest.raises(ValueError):typeset_independent(verses(),VerseLayout(**kw))

def test_global_scale_and_seed_reproducibility():
    cfg=VerseLayout(left_jitter=1.5,gap_jitter=.25,line_jitter=.05,line_scale_jitter=.05)
    a=typeset_independent(verses(5),cfg);b=typeset_independent(verses(5),cfg)
    c=typeset_independent(verses(5),replace(cfg,char_width=16,word_height=28,line_pitch=40))
    assert a==b and np.allclose(np.array(a['geometry'])*2,c['geometry'])
