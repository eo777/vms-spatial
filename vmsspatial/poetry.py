"""Finite verse controls through vmsspatial's existing native-line typesetter.

Input: [{book, line, words}], with source verse IDs retained. No text is repeated
to fill the manuscript. Template cycles repeat geometry only, not source words.
"""
import hashlib, json
from collections import Counter
from pathlib import Path
import numpy as np
from vmsspatial.controls import native_layout
from vmsspatial.geometry import line_frames, synthetic_geometry, line_profile, place_in_slot
from vmsspatial.shuffles import check_typesetting

def load_verses(path):
    rows=json.loads(Path(path).read_text(encoding='utf8'))
    if not isinstance(rows,list) or not rows:raise ValueError('Expected nonempty verse records')
    for r in rows:
        if not all(k in r for k in ('book','line','words')) or not r['words']:raise ValueError('Malformed verse')
        if any(not isinstance(w,str) or not w or any(c.isspace() for c in w) for w in r['words']):raise ValueError('Malformed word')
    return rows

def typeset_verses(ms, app, verses, mode='native', frames=None):
    """Use native_layout(start=0), or finite char-budget input to synthetic_geometry.

    Native mode retains supplied line breaks, with the toolkit's ordinary carry
    when a verse exceeds a frame. Synthetic overflow below a page is retained as
    separate physical rows. Neither mode substitutes manuscript word rectangles.
    """
    if mode not in ('native','reflow'):raise ValueError('mode must be native or reflow')
    frames=frames if frames is not None else line_frames(app,ms)
    source=[w for r in verses for w in r['words']]
    books=[r['book'] for r in verses for w in r['words']]
    source_ids=[k for k,r in enumerate(verses) for w in r['words']]
    starts=np.r_[0,np.cumsum([len(r['words']) for r in verses])]
    words=[];boxes=[];rows=[];checks=[];at=0;cycle=0;skipped_empty=0
    while at<len(source):
        if mode=='native':
            vi=int(np.searchsorted(starts,at));assert starts[vi]==at
            placed,geom,_=native_layout(ms,app,[r['words'] for r in verses[vi:]],np.random.default_rng(0),start=0,frames=frames)
        else:
            assigned=[];p=at
            for L in ms.lines:
                ws=[];used=0
                while p<len(source) and (not ws or used+1+len(source[p])<=L['chars']):
                    w=source[p];used+=len(w)+(1 if ws else 0);ws.append(w);p+=1
                assigned.append(ws)
            placed=[list(x) for x in assigned];geom=synthetic_geometry(placed,frames,ms)
        flat=[w for ws in placed for w in ws];n=len(flat)
        if not n:raise ValueError('No placement progress')
        assert flat==source[at:at+n]
        report=check_typesetting(ms,frames,placed,geom)
        checks.append({k:report[k] for k in ('ok','no_box','overlaps','width')})
        local=0
        for slot,ws in enumerate(placed):
            if not ws:skipped_empty+=1;continue
            L=ms.lines[slot];fr=frames[slot];g=geom[local:local+len(ws)]
            # fill_slots appends overflow to the final slot. The offset from the
            # frame's own drift identifies distinct overflow baselines exactly.
            shifts=[]
            for box in g:
                if box is None or fr is None:shifts.append(None)
                else:
                    top,bot=line_profile(fr)((box[0]+box[2])/2)
                    shifts.append((box[1]+box[3]-top-bot)/2)
            # Recover the exact prefix placed in the real frame. Any suffix
            # was added by fill_slots' page-bottom overflow loop, using another
            # frame. Vertical proximity is not a reliable way to identify it.
            normal=len(ws)
            if fr is not None:
                cw=sum(b-a for a,b in fr[4])/max(ms.lines[slot]['chars'],1)
                normal,normal_boxes=place_in_slot(ws,fr,cw)
                assert normal_boxes==g[:normal]
            split=[0]
            for k in range(1,len(ws)):
                if k==normal or (g[k] is not None and g[k-1] is not None and g[k][0]<=g[k-1][0]):split.append(k)
            split.append(len(ws))
            for a,b in zip(split[:-1],split[1:]):
                st=len(words);words.extend(ws[a:b]);boxes.extend(g[a:b])
                rows.append(dict(start=st,end=len(words),page=f'{cycle}:{L["folio"]}',template_page=L['folio'],
                                 locus=f'{L["locus"]}:{a}',bifolium=f'{cycle}:{L["node"]}',slot=slot,cycle=cycle,overflow=a>=normal))
            local+=len(ws)
        assert local==n
        at+=n;cycle+=1
    assert words==source and len(boxes)==len(words)
    token_row=np.empty(len(words),int)
    for j,r in enumerate(rows):token_row[r['start']:r['end']]=j
    split_verses=sum(len(set(token_row[a:b]))>1 for a,b in zip(starts[:-1],starts[1:]))
    return dict(schema=2,window=100,words=words,geometry=boxes,lines=rows,book=books,source_verse=source_ids,
                components={w:list(w) for w in set(words)},component_mode='letters; letter pairs',
                geometry_kind='synthetic',mode=mode,source_sha256=hashlib.sha256(json.dumps(verses,separators=(',',':')).encode()).hexdigest(),
                audit=dict(source_tokens=len(source),source_verses=len(verses),source_verses_split_across_rows=int(split_verses),
                           physical_rows=len(rows),pages=len(set(r['page'] for r in rows)),template_cycles=cycle,
                           overflow_rows=sum(r['overflow'] for r in rows),checks=checks,skipped_empty_slots=skipped_empty))

def main():
    """python -m vmsspatial.poetry verses.json --out control.json.gz"""
    import argparse
    from vmsspatial.manuscript import Manuscript
    from vmsspatial.bundle import load_bundle,save_bundle,validate_bundle
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',help='Normalized verse JSON: [{book, line, words}]')
    p.add_argument('--mode',choices=['native','reflow'],default='native')
    p.add_argument('--out',required=True)
    args=p.parse_args();ms=Manuscript.load();app=load_bundle('sensitivity')
    bundle=typeset_verses(ms,app,load_verses(args.source),args.mode)
    bundle['input_geometry_provenance']=app['geometry_provenance']
    validate_bundle(bundle);save_bundle(bundle,args.out)
    print(json.dumps(bundle['audit'],indent=2))

if __name__=='__main__':main()
