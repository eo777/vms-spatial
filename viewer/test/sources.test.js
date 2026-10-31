'use strict';
// The viewer's selector and measures (js/sources.js) on small fixtures and on the manuscript bundle.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),zlib=require('node:zlib'),path=require('node:path');
const S=require('../../js/sources.js'),R=require('../../js/review.js'),DATA=path.resolve(__dirname,'../data');
const have=fs.existsSync(path.join(DATA,'manuscript/words.json.gz'));
const d=have?JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,'manuscript/words.json.gz')))):null;
function fixture(words,components){return {words,components:components||Object.fromEntries(words.map(w=>[w,[...w]])),geometry:words.map((_,i)=>[i*10,0,i*10+8,8]),lines:[{page:'p',locus:'1',bifolium:'b',start:0,end:words.length}]};}
const pool=n=>({indices:Array.from({length:n},(_,i)=>i),weights:Array(n).fill(1),available:n});

test('spatial pool uses recorded same-page left/above geometry, never future text or padding',()=>{
 const f=fixture(['outside','above','angle','left','target','future']);
 f.geometry=[[95,15,105,25],[95,15,105,25],[175,15,185,25],[85,95,95,105],[95,95,105,105],[90,85,100,95]];
 f.lines=[{page:'earlier',start:0,end:1},{page:'p',start:1,end:3},{page:'p',start:3,end:6}];
 const c=S.prepare(f),full=S.sourcePool(c,4,100,{angle:45,depth:2,left:3});
 assert.deepEqual(full.indices,[1,2,3]);assert.equal(full.available,3);
 assert.ok(full.weights[1]<full.weights[0]);
 assert.deepEqual(S.sourcePool(c,4,100,{angle:0,depth:2,left:3}).indices,[1,3]);
 assert.deepEqual(S.sourcePool(c,4,100,{angle:0,depth:2,left:0}).indices,[1]);
 assert.deepEqual(S.sourcePool(c,4,100,{angle:0,depth:.5,left:3}).indices,[3]);
 assert.deepEqual(S.sourcePool(c,4,1,{angle:45,depth:2,left:3,weight:'uniform'}).indices,[3]);
 f.geometry[4]=null;assert.equal(S.sourcePool(S.prepare(f),4,100).missingTarget,true);
});
test('glyph H1, conditional H2 and effective pair types distinguish inventories from branching',()=>{
 const c=S.prepare(fixture(['ab','ab','ac','ac','ab','ac'])),s=S.measure(c,pool(6));
 assert.equal(s.h1,1.5);assert.equal(s.h2,1);assert.equal(s.components,2);assert.equal(s.worddiv,.5);assert.equal(s.js,0);assert.equal(s.ess,6);
 const deterministic=S.measure(S.prepare(fixture(['ab','cd','ab','cd','ab','cd'])),pool(6));
 assert.equal(deterministic.h1,2);assert.equal(deterministic.h2,0);assert.equal(deterministic.components,2);
 const one=S.measure(S.prepare(fixture(Array(6).fill('aaaa'))),pool(6));assert.equal(one.h1,0);assert.equal(one.h2,0);assert.equal(one.components,1);assert.equal(one.worddiv,0);
});
test('cone includes intersecting word boxes beside a gap and clips at the depth limit',()=>{
 const f=fixture(['left-edge','right-edge','outside','too-high','target']);
 f.geometry=[[65,75,90,85],[110,75,135,85],[130,75,150,85],[95,0,105,10],[95,95,105,105]];
 f.lines=[{page:'p',start:0,end:4},{page:'p',start:4,end:5}];
 const c=S.prepare(f);c.pages.get('p').pitch=20;
 assert.deepEqual(S.sourcePool(c,4,100,{depth:2,angle:45}).indices,[0,1]);
 f.geometry[0]=[90,75,101,85];
 const ray=S.prepare(f);ray.pages.get('p').pitch=20;
 assert.deepEqual(S.sourcePool(ray,4,100,{depth:2,angle:0}).indices,[0]);
});
test('strict pools hold reviewed word-level sources only; the sensitivity policy admits shared boxes',{skip:!have},()=>{
 // tokens by their ZL id, so the test holds whichever pages the bundle carries
 const at=id=>{const i=d.spatialReview.tokens.findIndex(t=>t.id===id);assert.ok(i>=0,id);return i;};
 const iShok=at('f40r.6@28:32'),iQop=at('f78r.34@33:41');
 const c=S.prepare(d),shok=S.sourcePool(c,iShok,100),qopchedy=S.sourcePool(c,iQop,100);
 assert.equal(d.words[iShok],'shok');assert.equal(shok.missingTarget,true);
 const shared=S.sourcePool(S.prepare(d,{policy:'sensitivity'}),iShok,100);
 for(const id of ['f40r.5@24:29','f40r.5@30:34'])assert.ok(shared.indices.includes(at(id)),id);
 assert.equal(d.words[iQop],'qopchedy');assert.ok(qopchedy.indices.includes(at('f78r.33@30:35')));
 for(let i=0;i<d.words.length;i+=19)for(const j of S.sourcePool(c,i,100).indices)assert.ok(d.spatialReview.tokens[j].strict);
 assert.equal(R.boxLabel(d,[at('f4v.14@25:28')]),'chy,key');
 assert.equal(R.groups(d,[at('f108r.1@68:72'),at('f108r.1@73:75')]).length,1);
});
test('width-neutral distance and the writing-cursor target do not read the target length',()=>{
 // one left neighbour, a short target (xy) and a long target (longword) at the same gap
 const f=fixture(['abcd','xy','abcd','longword']);
 f.geometry=[[0,0,40,10],[50,0,70,10],[0,20,40,30],[50,20,130,30]];
 f.lines=[{page:'p',locus:'1',start:0,end:2},{page:'p',locus:'2',start:2,end:4}];
 const c=S.prepare(f);c.pages.get('p').wordWidth=20;
 const centre=[S.sourcePool(c,1,100,{left:5,depth:0}),S.sourcePool(c,3,100,{left:5,depth:0})];
 assert.ok(centre[0].weights[0]>centre[1].weights[0]);                       // centre metric: the short target's neighbour is nearer
 const edge=[S.sourcePool(c,1,100,{left:5,depth:0,metric:'edge'}),S.sourcePool(c,3,100,{left:5,depth:0,metric:'edge'})];
 assert.ok(Math.abs(edge[0].weights[0]-edge[1].weights[0])<1e-12);         // same gap, same weight
 assert.ok(Math.abs(edge[0].weights[0]-1/(1+1.5)**2)<1e-12);               // gap 10 = half a word width, plus one
 const cursor=[S.sourcePool(c,1,100,{left:5,depth:0,target:'cursor'}),S.sourcePool(c,3,100,{left:5,depth:0,target:'cursor'})];
 assert.ok(Math.abs(cursor[0].weights[0]-cursor[1].weights[0])<1e-12);     // the cursor box is one median width for both
 assert.deepEqual(S.sourcePool(c,3,100,{left:5,depth:0}).indices,[2]);
});
test('long words do not dominate and thin pools stay unscored',()=>{
 const c=S.prepare(fixture(['a','bbbbbb','a','bbbbbb','a','bbbbbb'])),s=S.measure(c,pool(6));
 assert.equal(s.h1,1);assert.ok(Number.isNaN(s.h2));
 const a=S.measure(c,{...pool(6),weights:[1,2,1,2,1,2]}),b=S.measure(c,{...pool(6),weights:[7,14,7,14,7,14]});
 for(const k of ['h1','ess','worddiv'])assert.ok(Math.abs(a[k]-b[k])<1e-12);
 assert.deepEqual(S.colorDomain([1,2,3,4,5,6,7,8,9,10]).trimmed,true);
 assert.equal(S.colorFraction(5,{low:0,high:10,constant:false}),.5);
});
