'use strict';
// compare_math.js against vmsspatial.compare: the saved Python results of 30 pairs (viewer/test/fixtures/compare_pairs.json,
// written by scripts/compare_fixture.py on the atlas's compact comparison records) must come out identical to 1e-9.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const M=require('../js/compare_math.js'),DATA=path.resolve(__dirname,'../data'),FIX=path.join(__dirname,'fixtures/compare_pairs.json');
const gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,p))));
const have=fs.existsSync(FIX)&&fs.existsSync(path.join(DATA,'compare/pages.json.gz'))&&fs.existsSync(path.join(DATA,'manuscript/words.json.gz'));
const fixture=have?JSON.parse(fs.readFileSync(FIX,'utf8')):null,compact=have?gz('compare/pages.json.gz'):null,words=have?gz('manuscript/words.json.gz').words:null;
const close=(a,b,what)=>{if(a===null||b===null)assert.equal(a,b,what);else assert.ok(Math.abs(a-b)<1e-9,what+': '+a+' vs '+b);};
const unit=(text,lo,hi,line=0)=>({id:0,text,atoms:M.atoms(text),rect:[lo,0,hi,10],line,anchor:false,clean:true,flags:[]});

test('primitives: exact unions, atoms, edit distance, spatial gate, JS distance',()=>{
  assert.equal(M.unionArea([[0,0,10,10],[5,0,15,10]]),150);assert.equal(M.unionArea([[0,0,40,20],[40,0,100,20]]),M.unionArea([[0,0,100,20]]));
  assert.deepEqual(M.atoms('cheol dy'),['ch','e','o','l','d','y']);assert.deepEqual(M.atoms('{c@123;h}y'),['{c@123;h}','y']);assert.deepEqual(M.zattera('daiin'),['d','a','ii','n']);
  assert.equal(M.edit(['ch','o','l'],['sh','o','l']),1);assert.equal(M.similarity([],[]),1);
  assert.equal(M.spatialSimilarity([unit('cho',0,10),unit('dy',10,20)],[unit('chody',0,20)]).similarity,1);
  assert.equal(M.spatialSimilarity([unit('cho',0,10),unit('dy',10,20)],[unit('chody',100,120)]).similarity,0);
  assert.equal(M.xDice([unit('cho',0,10),unit('dy',10,20)],[unit('chody',0,20)]),1);
  const h=M.lineFeatures('daiin ol chedy');assert.equal(h.joined[JSON.stringify(['n','o'])],1);assert.ok(Math.abs(h.toolkit[JSON.stringify(['d','a'])]-1/3)<1e-12);
  assert.equal(M.jsDistance({a:1},{b:1}),1);assert.equal(M.jsDistance({a:1},{a:2}),0);assert.equal(M.jsDistance({},{a:1}),null);
  assert.deepEqual(M.faceSlots('inner','A'),['Av']);assert.deepEqual(M.faceSlots('both','B'),['Br','Bv']);assert.equal(M.joint([]).complete,false);
});

test('the combined ranking: the worse of the Dice rank and the JS rank, then the sum, then the id',()=>{
  const rows=[[0.8,0.5],[0.7,0.4],[0.8,0.6],[0.6,0.4],[0.9,0.9]].map((v,k)=>({id:'p:'+k,dice_current:v[0],js_joined:v[1]}));
  const r=M.rankRows(rows);
  assert.deepEqual(r.map(x=>x.id),['p:0','p:1','p:2','p:3','p:4']);assert.deepEqual(r.map(x=>x.both_worst),[3,4,4,5,5]);assert.deepEqual(r.map(x=>x.both_sum),[5,5,6,6,6]);
  if(fixture){assert.deepEqual(M.rankRows(fixture.ranking.rows).map(x=>x.id),fixture.ranking.order);assert.deepEqual(M.rankRows(fixture.ranking.rows).map(x=>x.both_worst),fixture.ranking.both_worst);}
});

test('overlay and block pairs: selection, measure, details and per-line table equal the Python results',{skip:!have},()=>{
  assert.equal(compact.version,fixture.version);
  for(const p of fixture.pairs){
    const options=k=>({block:p['block_'+k],cutoff:p.cutoff,coordinates:p.coordinates,alignment:p.alignment,scale:p.scale});
    const a=M.selectUnits(compact.pages[p.a],words,options('a')),b=M.selectUnits(compact.pages[p.b],words,options('b'));
    assert.equal(a.chosen.length,p.selection.a.chosen,p.a+' chosen');assert.equal(a.complete,p.selection.a.complete);assert.equal(b.chosen.length,p.selection.b.chosen);
    close(a.origin[0],p.selection.a.origin[0],p.a+' origin x');close(a.origin[1],p.selection.a.origin[1],p.a+' origin y');
    const m=M.measure(a,b,p.same_row);
    for(const k of ['dice','local_segment_similarity','nearby_similarity'])close(m[k],p.expected[k],p.a+'/'+p.b+' '+k);
    assert.equal(m.units_a,p.expected.units_a);assert.equal(m.units_b,p.expected.units_b);
    if(p.details){const d=M.details(a,b,p.same_row);assert.equal(d.direct.length,p.details.direct);assert.equal(d.connected.length,p.details.connected);assert.equal(d.nearby.length,p.details.nearby);
      d.connected.forEach((c,i)=>close(c.similarity,p.details.connected_similarity[i],'connected '+i));}
    if(p.per_line){const rows=M.perLine(a,b);assert.equal(rows.length,p.per_line.length);rows.forEach((r,i)=>{for(const k of ['dice','local_segment_similarity','nearby_similarity'])close(r[k],p.per_line[i][k],'line '+(i+1)+' '+k);});}
  }
  assert.equal(fixture.pairs.length+fixture.scan.length,30);
});

test('first-line scan metrics equal the Python results',{skip:!have},()=>{
  for(const s of fixture.scan){
    const sel=(f,coordinates,scale='pixels')=>M.selectUnits(compact.pages[f],words,{block:'opening',cutoff:1,coordinates,alignment:'starts',scale}).chosen.filter(u=>!u.anchor);
    const A=sel(s.a,'flat'),B=sel(s.b,'flat'),fa=M.lineFeatures(s.text_a),fb=M.lineFeatures(s.text_b);
    close(M.spatialSimilarity(A,B).similarity,s.expected.spatial,s.a+'/'+s.b+' spatial');close(M.xDice(A,B),s.expected.x_dice,'x_dice');close(M.dice2d(A,B),s.expected.dice_current,'dice_current');
    close(M.dice2d(sel(s.a,'recorded'),sel(s.b,'recorded')),s.expected.dice_recorded,'dice_recorded');
    close(M.spatialSimilarity(sel(s.a,'flat','body_height'),sel(s.b,'flat','body_height')).similarity,s.expected.spatial_body,'spatial_body');
    close(M.similarity(fa.plain,fb.plain),s.expected.edit_all,'edit_all');close(M.jsDistance(fa.toolkit,fb.toolkit),s.expected.js_word,'js_word');
    close(M.jsDistance(fa.joined,fb.joined),s.expected.js_joined,'js_joined');close(M.jsDistance(fa.boundaries,fb.boundaries),s.expected.js_boundaries,'js_boundaries');
  }
});

test('the drift indicator and the inline line split equal the Python results',{skip:!have},()=>{
  for(const d of fixture.drift){
    const page=compact.pages[d.folio],mine=M.pageDrift(page,words,d.coordinates,d.quarantined);
    close(mine.angle,d.angle,d.folio+' '+d.coordinates+' angle');close(mine.slope,d.slope,'slope');assert.equal(mine.n,d.n);assert.equal(mine.lines.length,d.lines);assert.deepEqual(mine.dropped,d.dropped);assert.equal(mine.unavailable,d.unavailable);
    mine.lines.forEach((l,i)=>{assert.equal(l.index,d.line_angles[i][0]);close(l.angle===undefined?null:l.angle,d.line_angles[i][1],'line angle');assert.equal(l.qualifies,d.line_angles[i][2]);});
    // the shipped per-page summary was computed from unrounded anchors; the recomputation reads anchors rounded to 0.01 px (a few thousandths of a degree over a line)
    if(d.shipped.angle!==null)assert.ok(Math.abs(d.shipped.angle-mine.angle)<5e-3,d.folio+' shipped '+d.shipped.angle+' vs '+mine.angle);else assert.equal(mine.angle,null);
    assert.equal(d.shipped.n,mine.n);
    const g=M.driftGuide(mine,10,0,100);if(mine.angle!==null){close(g[1][1],mine.slope*10*100,'guide');close(g[0][1],0,'guide origin');}else assert.equal(g,null);
  }
  for(const s of fixture.splits){
    const sel=f=>M.selectUnits(compact.pages[f],words,{block:'page',cutoff:'all',coordinates:'flat',alignment:'page'}),a=sel(s.a),b=sel(s.b),before=JSON.stringify([a.all,b.all]);
    const split=M.splitLines(a,b,s.indices,s.scale);
    for(const k of ['start','end','up','down','ymin','ymax'])close(split[k],s[k],s.a+'/'+s.b+' '+k);
    close(split.row_tops[0],s.row_tops[0],'row top A');close(split.row_tops[1],s.row_tops[1],'row top B');
    for(const k of [0,1])for(let j=0;j<4;j++)close(split.selections[k].all[0].rect[j],s.first_rects[k][j],'first rect');
    assert.equal(split.frame,'display');assert.equal(JSON.stringify([a.all,b.all]),before,'the measured selections are unchanged');
    const m=M.measure(a,b);for(const k of ['dice','local_segment_similarity','nearby_similarity'])close(m[k],s.scores_unchanged[k],'scores unchanged');
  }
  assert.equal(M.splitLines(M.selectUnits(compact.pages.f21v,words,{block:'page',alignment:'page'}),M.selectUnits(compact.pages.f15v,words,{block:'page',alignment:'page'}),[99,0]),null);
});

test('the compact records: every unit has a recorded rectangle, a flat shift and an anchor; flags are within range',{skip:!have},()=>{
  let units=0,flat=0;
  for(const [folio,p] of Object.entries(compact.pages)){
    assert.equal(p.lines.length>0,true,folio);assert.ok(p.blocks.length>=2&&p.blocks[0][0]==='opening'&&p.blocks[1][0]==='page');
    for(const u of p.units){units++;assert.equal(u.length,11);assert.ok(u[0]<=u[1]&&u[2]<p.lines.length);assert.ok(u[5]>=u[3]&&u[6]>=u[4]);assert.ok(u[10]>=0&&u[10]<16);if(u[7]!==0)flat++;}
    for(const b of p.breaks){assert.equal(b.length,4);assert.ok(p.units[b[1]]&&p.units[b[2]]);}
  }
  assert.equal(units,37478);assert.ok(flat>30000);
  const w=gz('compare/wheels.json.gz');assert.equal(w.summary.wheels,35);assert.equal(Object.values(w.pages).reduce((n,p)=>n+p.wheels.length,0),35);
  const r=gz('compare/rankings.json.gz');assert.equal(r.scan.eligible_pairs,20100);assert.ok(Object.values(r.pages).every(l=>l.length<=50));assert.deepEqual([r.bifolia.inner.rows,r.bifolia.outer.rows,r.bifolia.both.rows],[703,741,595]);
});
