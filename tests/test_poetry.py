"""Tests target past failure modes: finite input, no wrong-width boxes, reflow nulls."""
import copy
import numpy as np
import pytest
from vmsspatial.manuscript import Manuscript
from vmsspatial.bundle import load_bundle,validate_bundle
from vmsspatial.geometry import line_frames
from vmsspatial.shuffles import size_matched
from vmsspatial.poetry import typeset_verses,load_verses
from vmsspatial.poetry_sources import normalize,aeneid_book,creation

@pytest.fixture(scope='module')
def setup():
    ms=Manuscript.load();app=load_bundle('sensitivity');return ms,app,line_frames(app,ms)

@pytest.mark.parametrize('mode',['native','reflow'])
def test_finite_order_and_width(setup,mode):
    ms,app,frames=setup
    rows=[{'book':'x','line':i,'words':['a','short','longer','word','another','last']} for i in range(45)]
    b=typeset_verses(ms,app,rows,mode,frames)
    assert b['words']==[w for r in rows for w in r['words']]
    assert b['source_verse']==[i for i in range(45) for w in rows[i]['words']]
    validate_bundle(b)
    for r in b['lines']:
        g=b['geometry'][r['start']:r['end']]
        assert all(g[j] is None or g[j-1] is None or g[j][0]>g[j-1][0] for j in range(1,len(g)))
    assert all(c['ok'] and c['width']['off_1p5']==0 for c in b['audit']['checks'])
    assert b['audit']['source_tokens']==270

@pytest.mark.parametrize('mode',['native','reflow'])
def test_same_length_shuffle_retypesets_identically(setup,mode):
    ms,app,frames=setup
    rows=[{'book':'x','line':i,'words':['ab','cd','efg','hij','klmn','opqr']*(1+i%3)} for i in range(100)]
    b=typeset_verses(ms,app,rows,mode,frames)
    shuffled,_=size_matched([r['words'] for r in rows],np.zeros(len(rows)),np.random.default_rng(281029))
    other=[dict(r,words=w) for r,w in zip(rows,shuffled)]
    c=typeset_verses(ms,app,other,mode,frames)
    assert c['geometry']==b['geometry'] and c['lines']==b['lines']
    assert c['words']!=b['words']

def test_reject_malformed_verse(tmp_path):
    p=tmp_path/'bad.json';p.write_text('[{"book":"x","line":1,"words":["two words"]}]')
    with pytest.raises(ValueError):load_verses(p)

def test_source_parser_excludes_line_numbers_and_navigation():
    text='<H1>AENEID BOOK I</H1><P>Arma virumque cano<BR>Italiam fato <FONT SIZE=2>5</FONT></P><HR><A>Next: English translation</A>'
    assert aeneid_book(text,1)==[{'book':'1','line':1,'words':['arma','virumque','cano']},{'book':'1','line':2,'words':['italiam','fato']}]
    assert normalize('ffader, & [son] I-wis')==['ffader','and','son','i','wis']

def test_creation_scope_and_speaker_removal():
    text='The Creatio\n'+'\n'.join(f'{i}: test word. Lucifer' for i in range(1,268))+'\nThe Killing of Abel\n1: contamination'
    rows=creation(text)
    assert len(rows)==267 and all(r['words']==['test','word'] for r in rows)
