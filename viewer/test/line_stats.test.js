'use strict';
// What a page draws: line values expanded to tokens, the two coordinate states, the overlays' points and titles, the line
// notes. Pure functions on small bundles, then the shipped bundle's built-in fields.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const A=require('../atlas.js'),M=require('../../js/heatmap_math.js'),DATA=path.resolve(__dirname,'../data');
const gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,p))));
const have=fs.existsSync(path.join(DATA,'manuscript/words.json.gz'));
const small=()=>({words:['a','b','c','d','e'],lines:[{page:'p',locus:'1',start:0,end:3},{page:'p',locus:'2',start:3,end:5}],
 geometry:[[0,8,10,18],[20,9,30,19],null,[0,28,10,38],[20,30,30,40]],geometry_recorded:[[0,10,10,20],[20,10,30,20],null,[0,30,10,40],[20,30,30,40]]});

test('a per-line measure takes its line value on every token',()=>{
 const d={...small(),measures:{tilt:{line_values:[1.5,null],per:'line'},word:{values:[1,2,3,4,5]}}};
 assert.equal(M.expandMeasures(d),d);
 assert.deepEqual([...d.measures.tilt.values].slice(0,3),[1.5,1.5,1.5]);
 assert.ok(Number.isNaN(d.measures.tilt.values[3])&&Number.isNaN(d.measures.tilt.values[4]));
 assert.deepEqual(d.measures.word.values,[1,2,3,4,5]);                 // a per-token measure is left alone
 assert.deepEqual(M.measureDomain(d.measures.tilt.values,'sequential').length,2);
 const plain={words:[],lines:[]};assert.equal(M.expandMeasures(plain),plain);
});

test('row means weight lines: the value at a line start stands for the whole line',()=>{
 const d=M.expandMeasures({...small(),measures:{m:{line_values:[2,4],per:'line'}}}),m=d.measures.m;
 const lineMean=d.lines.reduce((s,L)=>s+m.values[L.start],0)/d.lines.length,tokenMean=m.values.reduce((a,b)=>a+b,0)/m.values.length;
 assert.equal(lineMean,3);assert.ok(Math.abs(tokenMean-2.8)<1e-9);
});

test('the shift of a token is its recorded bottom minus its flat bottom',()=>{
 const d=small(),dy=A.tokenShifts(d);
 assert.deepEqual([...dy],[2,1,0,2,0]);assert.equal(A.tokenShifts(d),dy);
 assert.equal(A.tokenShifts({words:['a'],lines:[],geometry:[[0,0,1,1]]}),null);    // one state only: nothing to toggle
});

test('a shared box reads its group against the review, where the strict arrays are empty',()=>{
 const d={words:['a','b','c'],lines:[],geometry:[null,null,[0,0,1,1]],geometry_recorded:[null,null,[0,3,1,4]],
  spatialReview:{tokens:[{group:'g'},{group:'g'},{group:'h'}],groups:{g:{box:[0,10,5,20]},h:{box:[0,3,1,4]}},sensitivityGeometry:[[0,6,5,16],[0,6,5,16],[0,0,1,1]]}};
 assert.deepEqual([...A.tokenShifts(d)],[4,4,3]);
});

test('rectangles carry their way to the flat state and stay recorded in the markup',()=>{
 const d=small(),html=A.pageRects('p',d,[[0,5]]);
 assert.match(html,/y="10"[^>]*data-token-indices="0" data-dy="2.00"/);
 assert.match(html,/data-token-indices="4" role/);                       // an unmoved box has no attribute
 assert.doesNotMatch(A.pageRects('p',{...small(),geometry_recorded:undefined},[[0,5]]),/data-dy/);
});

test('the image forces recorded coordinates and the Flat choice stands',()=>{
 const S=A.coordinateState;
 assert.deepEqual(S({choice:'flat',canFlat:true}),{wanted:true,drawn:'flat',note:''});
 const shown=S({choice:'flat',canFlat:true,image:true});
 assert.equal(shown.drawn,'recorded');assert.equal(shown.wanted,true);assert.equal(shown.note,'Page image shown: boxes in recorded coordinates');
 assert.deepEqual(S({choice:'recorded',canFlat:true,image:true}),{wanted:false,drawn:'recorded',note:''});
 assert.equal(S({choice:'flat',canFlat:false}).drawn,'recorded');        // no second state to draw
 assert.equal(S({choice:'flat',canFlat:false,image:true}).note,'');
 assert.equal(S().drawn,'recorded');
 assert.match(S({choice:'flat',canFlat:true,pageWarp:'recorded (no located rectangles)'}).note,/boxes stay recorded \(no located rectangles\)/);
 assert.equal(S({choice:'flat',canFlat:true,pageWarp:'flat'}).note,'');
 assert.equal(S({choice:'recorded',canFlat:true,pageWarp:'recorded (x)'}).note,'');
 assert.equal(S({choice:'flat',canFlat:true,image:true,pageWarp:'recorded (x)'}).note,'Page image shown: boxes in recorded coordinates');
});

test('an overlay item gives the points of the state drawn',()=>{
 const P=A.overlayPoints,line={points:[[0,10],[9,12]],points_flat:[[0,8],[9,9]]},marker={points:[[5,20]],token:1},plain={points:[[1,1]]},only={points:[[2,2]],states:['recorded']};
 assert.deepEqual(P(line,'recorded',null),line.points);assert.deepEqual(P(line,'flat',null),line.points_flat);
 assert.deepEqual(P(marker,'flat',[0,3]),[[5,17]]);assert.deepEqual(P(marker,'recorded',[0,3]),[[5,20]]);
 assert.deepEqual(P(plain,'flat',null),plain.points);                    // a study overlay without flat points
 assert.equal(P(only,'flat',null),null);assert.deepEqual(P(only,'recorded',null),only.points);
 assert.equal(P({points:[[0,0]],states:['flat']},'recorded',null),null);
});

test('the chosen overlays read and write the address',()=>{
 const keys=['chords','fits','warp'],P=A.parseOverlays,F=A.formatOverlays;
 assert.deepEqual([...P('all',keys)],keys);assert.equal(P('none',keys).size,0);assert.equal(P(undefined,keys).size,0);
 assert.deepEqual([...P('fits,warp,nope',keys)],['fits','warp']);assert.deepEqual([...P('warp',keys)],['warp']);
 assert.equal(F(new Set(['warp','chords']),keys),'chords,warp');assert.equal(F(new Set(keys),keys),'all');assert.equal(F(new Set(),keys),'none');
 assert.equal(F(new Set(['only']),['only']),'only');                     // one overlay is its own name
});

test('markers named by a field stand at the box centre in the state drawn',()=>{
 const d={...small(),anchors:[-3,null,null,1,null]},o={markers_from:'anchors',r:2};
 const rec=A.fieldMarkers(o,d,'p','recorded'),flat=A.fieldMarkers(o,d,'p','flat');
 assert.deepEqual(rec.map(m=>m.points[0]),[[5,17],[5,41]]);assert.deepEqual(flat.map(m=>m.points[0]),[[5,15],[5,39]]);
 assert.equal(rec[0].kind,'marker');assert.equal(rec[0].r,2);assert.equal(A.fieldMarkers({items:[]},d,'p','flat').length,0);
 assert.equal(A.fieldMarkers(o,d,'other','flat').length,0);
});

test('titles come from the line and from info',()=>{
 const d={...small(),measures:{chord_flat:{line_values:[0.5,-1]},chord_recorded:{line_values:[1.25,0]}}},T=A.overlayTitle;
 assert.equal(T({title:'mine',style:'chord',line:0},d),'mine');
 assert.equal(T({style:'chord',line:1},d),'line 2: chord -1.00 deg flat, 0.00 deg recorded');
 assert.equal(T({style:'break-both',line:0,info:[0,1,0.12,1.5]},d),'line 1: transcript and geometric break, a | b: step +0.12 H, gap 1.50 W');
 assert.equal(T({style:'intrusion-touch',info:[1,3,0.3,0.6,1]},d),'b descender into d: 0.30 H deep, gap 0.60 H, touching');
 assert.equal(T({style:'intrusion',info:[1,3,0.3,null,0]},d),'b under ascender of d: 0.30 H deep, gap ? H, not touching');
 assert.equal(T({style:'other'},d),'');
});

test('line notes join the line, its measures and its page',()=>{
 const d={...small(),line_notes:[{line:'p.1',paragraph:'first, line 1 of 2'},null],line_note_fields:[['chord','c',1,'deg'],['words','n',0,''],['gone','x',0,'H']],
  page_notes:{p:{'page warp':'amplitude 0.20 H'}},measures:{c:{line_values:[0.5,1],digits:2},n:{line_values:[7,2],digits:0},x:{line_values:[null,null],digits:2}}};
 assert.deepEqual(A.lineNoteItems(d,0),[['line','p.1'],['paragraph','first, line 1 of 2'],['chord','+0.50 deg'],['words','7'],['page warp','amplitude 0.20 H']]);
 assert.deepEqual(A.lineNoteItems(d,1),[]);                              // a line without notes shows only its orientation
 assert.deepEqual(A.lineNoteItems({...small(),line_notes:[{'chord angle':1.5,n:3},null]},0),[['chord angle','1.500'],['n','3']]);   // a study's own notes
});

test('the shipped bundle: the built-in fields and the two states agree',{skip:!have},()=>{
 const d=gz('manuscript/words.json.gz'),n=d.words.length,nl=d.lines.length,groups=new Set();
 assert.equal(n,38876);assert.equal(nl,5365);
 for(const [k,m] of Object.entries(d.measures)){
  groups.add(m.group);
  if(m.line_values)assert.equal(m.line_values.length,nl,k);else assert.equal(m.values.length,n,k);
 }
 assert.deepEqual([...groups],['Lines, baselines and warp']);
 M.expandMeasures(d);
 const dy=A.tokenShifts(d),shift=d.measures.warp_shift.values,ratios=[];
 assert.equal(dy.length,n);
 // the warp shift a measure reports is the box's way to the flat state, in the page's median box height
 for(let i=0;i<n;i++)if(shift[i]!=null&&Math.abs(shift[i])>.2)ratios.push(dy[i]/shift[i]);
 assert.ok(ratios.length>1000);assert.ok(ratios.every(r=>r>5&&r<60),'dy / warp_shift is a box height in px');
 const flat=Object.values(d.warp_pages).filter(v=>v==='flat').length;assert.equal(flat,205);
 assert.ok(Object.values(d.warp_pages).filter(v=>v.startsWith('recorded')).length===22);
 const p=d.overlays.chords.items.find(i=>i.page==='f101v');
 assert.ok(Math.abs((p.points[1][1]-p.points[0][1])-(p.points_flat[1][1]-p.points_flat[0][1]))>5,'f101v bows: the chord differs between the states');
 assert.deepEqual(A.overlayPoints(d.overlays.warp.items.find(i=>i.style==='warp-flat'),'flat',dy),null);
 assert.equal(d.overlay_default,'none');assert.equal(d.anchors.length,n);
 assert.ok(A.lineNoteItems(d,0).length>15);
 assert.ok(A.fieldMarkers(d.overlays.anchors,d,'f75r','flat').length>300);
 for(const item of d.overlays.intrusions.items.slice(0,50))assert.match(A.overlayTitle(item,d),/H deep/);
 for(const item of d.overlays.breaks.items.slice(0,50))assert.match(A.overlayTitle(item,d),/break, .* \| .*: step/);
});
