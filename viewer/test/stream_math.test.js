// The Page stream's model on the real data: every page present and in its sheet, translations and turns that leave words unchanged, restored tilt, chain placement.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),zlib=require('zlib');
const M=require('../js/compare_math.js'),T=require('../js/stream_math.js'),X=require('../js/section_math.js');
const DATA=path.join(__dirname,'..','data'),gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,p))));
const have=['compare/pages.json.gz','compare/orders.json','manuscript/words.json.gz'].every(p=>fs.existsSync(path.join(DATA,p)));
const compact=have?gz('compare/pages.json.gz'):null,bundle=have?gz('manuscript/words.json.gz'):null,orders=have?JSON.parse(fs.readFileSync(path.join(DATA,'compare/orders.json'))):null;
const pages=have?compact.pages:null,words=have?bundle.words:null,tokens=have?X.lineTokens(bundle.lines):null;
const listOf=o=>orders[o].pages.filter(f=>pages[f]),near=(a,b,eps=1e-8)=>assert.ok(Math.abs(a-b)<=eps,`${a} vs ${b}`);
const sheets=[{node:'A',height:200},{node:'B',height:80},{node:'C',height:120}],key=T.seamKey('A','B');

test('the address round-trips, and bad values fall back',()=>{
 const h={by:'section',group:'Herbal A',order:'path1',route:'cycle:Ar',view:'overlay',columns:'faces',join:'half',covered:'outline',strength:'0.6',seam:'A:1-8>F:42-47',anchor:'margin',coords:'recorded',scale:'pixels',trail:'pair',fade:'0.4',zoom:'0.75',tilt:'turn',at:'12',words:'0',margins:'0',overlaps:'A:1-8>F:42-47=0.333|D:27-30>A:1-8=0.575',custom:'F:42-47,A:1-8',pages:'f1r,f2r'};
 assert.deepEqual(T.serialize(T.parse(h)),h);
 assert.deepEqual(T.serialize(T.parse({})),{});
 const bad=T.parse({order:'x',view:'y',join:'z',covered:'q',anchor:'r',strength:'9',fade:'-1',at:'abc',zoom:'8',overlaps:'A>A=.5|A>B=abc|B>C=7|broken'});
 assert.equal(bad.order,'bifolia');assert.equal(bad.view,'chain');assert.equal(bad.join,'touch');assert.equal(bad.covered,'faint');assert.equal(bad.anchor,'source');assert.equal(bad.strength,1);assert.equal(bad.fade,.02);assert.equal(bad.at,0);assert.equal(bad.zoom,'1');
 assert.deepEqual(bad.overlaps,{'B>C':.95},'a broken pair is dropped and a value past the limit is capped');
});
test('the Herbal A candidate opens recorded geometry and retains explicit changes in links and saved sets',()=>{
 const s=T.parse({order:T.HERBAL_A_ORDER});
 assert.equal(s.coords,'recorded');assert.equal(s.tilt,'none');assert.equal(s.view,'chain');
 assert.deepEqual(T.serialize(s),{order:T.HERBAL_A_ORDER});
 const edited={...s,coords:'flat',tilt:'restore',columns:'faces',overlaps:{'D:27-30>F:42-47':.25},custom:[...T.HERBAL_A_NODES].reverse()};
 assert.deepEqual(T.parse(T.serialize(edited)),edited,'changing back to the ordinary geometry defaults must survive a reload');
 const saved=T.normalizePreset({schema:1,name:'1a boundaries',params:T.presetParams(edited)});
 assert.deepEqual(T.parse(saved.params),edited);
});
test('choosing either Herbal A candidate clears a Bio selection and starts all ten complete sheets',{skip:!have},()=>{
 const bio=T.parse({group:'4a',order:'path1',pages:'f76r,f83v',custom:'M:76-83,M:77-82',coords:'flat',tilt:'turn',view:'overlay',route:'slot:Ar',at:'10',overlaps:'M:76-83>M:77-82=.85'});
 const s=T.selectOrder(bio,T.HERBAL_A_ORDER),list=T.orderPages(orders,s.order,pages),plan=T.sequence(pages,list,s);
 assert.deepEqual(plan.nodes,['A:1-8','D:27-30','F:42-47','G:49-56','A:2-7','D:25-32','C:20-21','E:35-38','A:4-5','D:28-29']);
 assert.equal(plan.pages.length,40);assert.equal(new Set(list).size,40);assert.ok(list.includes('f49v'));
 for(const node of plan.nodes)assert.deepEqual(plan.pages.filter(p=>p.node===node).map(p=>p.slot),T.SLOTS);
 assert.equal(s.group,'all');assert.equal(s.by,'golf');assert.equal(s.at,0);assert.equal(s.coords,'recorded');assert.equal(s.tilt,'none');assert.equal(s.view,'chain');assert.equal(s.anchor,'source');
 assert.deepEqual(s.pages,[]);assert.deepEqual(s.custom,[]);assert.equal(s.foldMode,'shared');assert.equal(s.overlaps['D:27-30>F:42-47'],.8);assert.equal(Object.keys(s.overlaps).length,9);assert.equal(bio.group,'4a','the prior state is not mutated');
 const split=T.selectOrder(bio,T.HERBAL_A_FOLDS);assert.equal(split.foldMode,'separate');assert.deepEqual(T.orderPages(orders,split.order,pages),list);assert.deepEqual(split.overlaps,s.overlaps);assert.deepEqual(split.folds,s.folds);
 for(const order of ['bifolia','path1'])assert.deepEqual(T.orderPages(orders,order,pages),listOf(order));
 assert.equal(T.orderPages(orders,T.selectOrder(s,'bifolia').order,pages).length,Object.keys(pages).length);
 const reversed=T.sequence(pages,list,{custom:[...plan.nodes].reverse()});assert.deepEqual(reversed.nodes,[...plan.nodes].reverse());
 assert.deepEqual(T.sequence(pages,list,{custom:[]}).nodes,plan.nodes,'reset order returns to the candidate chain');
});
test('separate folds are opt-in, round-trip edits, and preserve the original shared joins',()=>{
 assert.equal(T.parse({}).foldMode,'shared');assert.equal(T.parse({order:T.HERBAL_A_ORDER}).foldMode,'shared');
 const s=T.parse({order:T.HERBAL_A_FOLDS});assert.equal(s.foldMode,'separate');assert.equal(Object.keys(s.folds).length,9);
 assert.deepEqual(T.serialize(s),{order:T.HERBAL_A_FOLDS});
 const off={...s,foldMode:'shared'};assert.equal(T.parse(T.serialize(off)).foldMode,'shared');assert.deepEqual(off.folds,s.folds);
 const edited={...s,foldPart:'inner',overlaps:{},folds:{'A:1-8>D:27-30':{Ar:0,inner:.12,Bv:.95}}};
 assert.deepEqual(T.parse(T.serialize(edited)),edited);
 const saved=T.normalizePreset({schema:1,name:'fold edit',params:T.presetParams(edited)});assert.deepEqual(T.parse(saved.params),edited);
 const cleared={...s,overlaps:{},folds:{}};assert.deepEqual(T.parse(T.serialize(cleared)),cleared,'resetting must not reload the preset defaults');
 const hash=Object.fromEntries(new URLSearchParams(Object.fromEntries(Object.entries(T.serialize(cleared)).filter(([,v])=>v!=null&&v!==''))));assert.deepEqual(T.parse(hash),cleared,'the common hash writer omits empty values');
 assert.deepEqual(T.parse(T.normalizePreset({schema:1,name:'reset',params:T.presetParams(cleared)}).params),cleared);
 for(const folds of ['A>B@side=.2','A>B@inner=abc','A>B@Ar=1.5','A>B@Ar=.2|A>B@Ar=.3'])assert.throws(()=>T.normalizePreset({schema:1,name:'bad',params:{group:'all',order:'path1',folds}}));
});
test('three fold groups advance independently, keep Av/Br tied, and restore the shared positions exactly',()=>{
 const rows=[{node:'A',height:100},{node:'B',height:80},{node:'C',height:60}];
 const shared={'A>B':.5,'B>C':.25},folds={'A>B':{Ar:.1,inner:.6,Bv:.8},'B>C':{Ar:.2,inner:.3,Bv:.4}};
 const original=T.stackSheets(rows,{overlaps:shared}),split=T.stackSheets(rows,{overlaps:shared,folds,foldMode:'separate'});
 near(split.rows[1].lanes.Ar.top,90);near(split.rows[1].lanes.inner.top,40);near(split.rows[1].lanes.Bv.top,20);
 near(split.rows[2].lanes.Ar.top,154);near(split.rows[2].lanes.inner.top,96);near(split.rows[2].lanes.Bv.top,68);
 assert.equal(T.foldGroup('Av'),T.foldGroup('Br'));
 const changed=T.stackSheets(rows,{overlaps:shared,foldMode:'separate',folds:{...folds,'A>B':{...folds['A>B'],inner:.7}}});
 for(const lane of ['Ar','Bv'])assert.deepEqual(changed.rows.map(r=>r.lanes[lane]),split.rows.map(r=>r.lanes[lane]));
 near(changed.rows[2].lanes.inner.top,86);assert.deepEqual(T.stackSheets(rows,{overlaps:shared,folds,foldMode:'shared'}),original);
 const hidden=T.stackSheets(rows,{overlaps:shared,foldMode:'separate',folds,hideCovered:true});
 near(hidden.rows[0].lanes.Ar.visibleHeight,90);near(hidden.rows[0].lanes.inner.visibleHeight,40);near(hidden.rows[0].lanes.Bv.visibleHeight,20);
 const reversed=T.stackSheets([...rows].reverse(),{folds,foldMode:'separate'});assert.equal(reversed.rows[1].lanes.Ar.top,60,'no reversed-pair fit is reused');
});
test('saved study registration reproduces the source rectangle positions and sheet extents without rotation',{skip:!have},()=>{
 const state=T.parse({order:T.HERBAL_A_FOLDS});assert.ok(T.studyFrame(state));
 assert.equal(Object.keys(T.STUDY.pages).length,39);assert.equal(T.STUDY.pages.f49v,undefined);
 const extents=new Map();
 for(const [folio,ref] of Object.entries(T.STUDY.pages)){
  const sel=T.register(folio,pages[folio],words,tokens,{...state,reference:ref}),r=T.orient(pages[folio],sel,state.coords,state.tilt),raw=M.pageUnits(pages[folio],words),factor=M.BODY_HEIGHT_PX/ref.H;
  assert.equal(r.angle.delta,0);
  for(const u of sel.all){near(u.rect[0],raw[u.id].rect[0]*factor);near(u.rect[1],(raw[u.id].rect[1]-ref.origin[1])*factor);near(u.rect[3],(raw[u.id].rect[3]-ref.origin[1])*factor);}
  const b=extents.get(ref.node)||{lo:Infinity,hi:-Infinity};b.lo=Math.min(b.lo,r.bounds.ymin);b.hi=Math.max(b.hi,r.bounds.ymax);extents.set(ref.node,b);
 }
 for(const [node,b] of extents){near(b.lo,T.STUDY.sheets[node].ymin*M.BODY_HEIGHT_PX);near(b.hi,T.STUDY.sheets[node].ymax*M.BODY_HEIGHT_PX);}
 const rows=T.HERBAL_A_NODES.map(node=>({node,height:(T.STUDY.sheets[node].ymax-T.STUDY.sheets[node].ymin)*30})),split=T.stackSheets(rows,{folds:state.folds,foldMode:'separate'});
 for(let i=1;i<rows.length;i++)for(const g of T.FOLD_GROUPS){const p=split.rows[i-1].lanes[g],q=split.rows[i].lanes[g],edge=T.STUDY.edges[rows[i-1].node+'>'+rows[i].node];near(q.top-p.top,rows[i-1].height*(1-edge.groups[g].value));}
});
test('a link from the comparison workspace opens the same view',()=>{
 const link='a=f47r&b=f56r&view=sequence&unit=pages&columns=both&order=folio&coordinates=current&scale=body_height&zoom=0.75&eva=1&seqGroup=all&seqOrder=path1&seqRoute=all&seqIndex=100&seqMode=all&seqAnchor=source&seqOpacity=0.2&seqEdges=1&seqDisplay=four&seqColumns=singulion&seqJoin=touch&seqHideCovered=1&seqCovered=hidden&seqCoveredOpacity=0.3&seqSeam=D%3A27-30%3EA%3A1-8&seqRestore=1&seqOverlaps=%7B%22A%3A1-8%3EF%3A42-47%22%3A0%2C%22D%3A27-30%3EA%3A1-8%22%3A0.575%2C%22A%3A2-7%3ED%3A25-32%22%3A0.274%7D';
 const s=T.parse(Object.fromEntries(new URLSearchParams(link)));
 assert.equal(s.view,'chain');assert.equal(s.order,'path1');assert.equal(s.columns,'singulion');assert.equal(s.group,'all');assert.equal(s.anchor,'source');assert.equal(s.coords,'flat');assert.equal(s.scale,'body_height');assert.equal(s.zoom,'0.75');assert.equal(s.covered,'hidden');assert.equal(s.seam,'D:27-30>A:1-8');assert.equal(s.at,100);assert.equal(s.tilt,'restore','no link opens on the rigid turn, which leans every margin');assert.equal(s.oldLink,true,'and the page can say so');assert.equal(s.words,true);
 assert.deepEqual(s.overlaps,{'A:1-8>F:42-47':0,'D:27-30>A:1-8':.575,'A:2-7>D:25-32':.274});
 assert.equal(T.parse({seqDisplay:'four',seqRestore:'0'}).tilt,'none');assert.equal(T.parse({seqDisplay:'four',seqRestore:'0'}).oldLink,false,'nothing was turned there');assert.equal(T.parse({}).tilt,'restore');assert.equal(T.parse({}).oldLink,false);
 assert.equal(T.parse({tilt:'turn'}).tilt,'turn','a turn chosen on this page stays a choice');
 assert.equal(T.parse({seqDisplay:'overlay',seqHideCovered:'0'}).covered,'full');
 assert.equal(T.parse({seqDisplay:'four',coordinates:'recorded',seqEdges:'0'}).coords,'recorded');
 assert.equal(T.parse({seqDisplay:'four',seqCustomOrder:'["B:9-16","A:1-8"]'}).custom.length,2);
});
test('clean drops what the manuscript does not have',{skip:!have},()=>{
 const list=listOf('bifolia'),s=T.clean(T.parse({overlaps:'A:1-8>F:42-47=0.3|Z:1-2>A:1-8=0.3',custom:'A:1-8,Z:1-2',pages:'f1r,f999r'}),pages,list);
 assert.deepEqual(Object.keys(s.overlaps),['A:1-8>F:42-47']);assert.deepEqual(s.custom,[]);assert.deepEqual(s.pages,['f1r']);
});
test('rows stack, overlap by the preceding row and hide what lies under the fold',()=>{
 const before=JSON.stringify(sheets);
 assert.deepEqual(T.stackSheets(sheets).rows.map(r=>r.top),[0,200,280]);
 assert.deepEqual(T.stackSheets(sheets,{join:'half'}).rows.map(r=>r.top),[0,100,140]);
 const config={overlaps:{[key]:.75},hideCovered:true},masked=T.stackSheets(sheets,config);
 assert.deepEqual(masked.rows.map(r=>r.top),[0,50,130]);assert.deepEqual(masked.rows.map(r=>r.visibleHeight),[50,80,120]);
 assert.equal(T.stackSheets(sheets.slice(0,2),config).height,130,'an older sheet stays hidden where it runs past a shorter one');
 assert.equal(T.stackSheets(sheets.slice(0,2),{...config,hideCovered:false}).height,200);
 const scaled=T.stackSheets(sheets.map(s=>({...s,height:2*s.height})),config);
 masked.rows.forEach((r,i)=>{near(scaled.rows[i].top,2*r.top);near(scaled.rows[i].visibleHeight,2*r.visibleHeight);});
 assert.equal(T.stackSheets(sheets,{overlaps:{[key]:Infinity}}).rows[1].overlap,0);assert.equal(T.stackSheets(sheets,{overlaps:{[key]:2}}).rows[1].overlap,.95);assert.equal(T.stackSheets(sheets,{overlaps:{[key]:-1}}).rows[1].overlap,0);
 assert.equal(T.stackSheets([]).height,0);assert.equal(JSON.stringify(sheets),before);
});
test('a boundary stays with its pair: a new pair takes the default and an old pair gets its value back',()=>{
 const config={overlaps:{[key]:.75},hideCovered:true},moved=T.moveNode(['A','B','C'],'C',1),reordered=T.stackSheets(moved.map(n=>sheets.find(s=>s.node===n)),config);
 assert.deepEqual(moved,['A','C','B']);assert.deepEqual(reordered.rows.map(r=>r.top),[0,200,320]);assert.ok(reordered.rows.every(r=>!r.manual));
 assert.equal(T.stackSheets(sheets,config).rows[1].overlap,.75);
 assert.deepEqual(T.reorderNodes(['A','B','C'],['A','B','B']),['A','B','C']);assert.deepEqual(T.reorderNodes(['A','B','C'],['C','A']),['A','B','C']);assert.deepEqual(T.reorderNodes(['D','E'],moved),['D','E']);assert.deepEqual(T.moveNode(moved,'missing',0),moved);
});
test('reordering keeps every page and panel with its sheet',()=>{
 const toy={};for(const node of ['A','B','C'])['Ar','Av','Br','Bv'].forEach((slot,i)=>{toy[node+i]={node,slot,face:'',panel:'',section:'S',group:'t'};});
 toy['B0-panel']={node:'B',slot:'Ar',face:'',panel:'2',section:'S',group:'t'};
 const list=Object.keys(toy),custom=T.moveNode(['A','B','C'],'C',1),plan=T.sequence(toy,list,{group:'t',custom});
 assert.deepEqual(plan.nodes,custom);assert.equal(plan.custom,true);assert.deepEqual(plan.baseNodes,['A','B','C']);assert.equal(plan.pages.length,list.length);assert.deepEqual(new Set(plan.pages.map(p=>p.folio)),new Set(list));
 for(const node of custom){const at=plan.pages.flatMap((p,i)=>p.node===node?[i]:[]);assert.equal(at[at.length-1]-at[0]+1,at.length);}
 assert.equal(plan.pages.find(p=>p.folio==='B0-panel').panels,2);
 assert.deepEqual(T.sequence(toy,list,{group:'t',custom,route:'cycle:Ar'}).pages.map(p=>p.slot),['Ar','Bv','Br']);
});
test('a saved boundary set keeps its values, and only known settings',()=>{
 const preset={schema:1,name:'Golf 1a boundaries',params:{group:'1a',order:'path1',custom:'F:42-47,A:1-8',overlaps:'A:1-8>F:42-47=0.333',covered:'outline',strength:.3,coords:'recorded',scale:'body_height',arbitraryUrl:'javascript:invalid'}};
 const n=T.normalizePreset(JSON.parse(JSON.stringify(preset)));
 assert.equal(n.params.overlaps,preset.params.overlaps);assert.equal(n.params.custom,preset.params.custom);assert.equal(n.params.strength,'0.3');assert.ok(!Object.hasOwn(n.params,'arbitraryUrl'));
 assert.throws(()=>T.normalizePreset({...preset,params:{...preset.params,overlaps:'A>B=1.5'}}));assert.throws(()=>T.normalizePreset({...preset,params:{}}));assert.throws(()=>T.normalizePreset({...preset,schema:2}));assert.throws(()=>T.normalizePreset({...preset,params:{...preset.params,custom:'A,A'}}));
 const round=T.normalizePreset({schema:1,name:'x',params:T.presetParams(T.parse({overlaps:'A>B=0.25',order:'path1'}))});assert.deepEqual(T.parse(round.params).overlaps,{'A>B':.25});assert.equal(T.parse(round.params).order,'path1');
 const study=T.normalizePreset({schema:1,name:'Golf 1a',params:{view:'sequence',seqGroup:'1a',seqOrder:'path1',seqDisplay:'four',seqJoin:'touch',seqCovered:'outline',seqCoveredOpacity:.3,seqOverlaps:'{"A:1-8>F:42-47":0.333}',seqCustomOrder:'["F:42-47","A:1-8"]',coordinates:'recorded',scale:'body_height'}});
 assert.equal(study.params.tilt,'restore');assert.equal(study.params.group,'1a');assert.equal(study.params.view,'chain');assert.equal(study.params.overlaps,'A:1-8>F:42-47=0.333');assert.equal(study.params.coords,'recorded');
 assert.throws(()=>T.normalizePreset({schema:1,name:'x',params:{seqGroup:'1a',seqOrder:'path1',seqOverlaps:'{"A>B":1.5}'}}));
 assert.throws(()=>T.normalizePreset({schema:1,name:'x',params:{seqGroup:'1a',seqOrder:'path1',seqCustomOrder:'not json'}}));
});
test('the sequence covers the manuscript: every page once, each sheet whole, in the order asked',{skip:!have},()=>{
 const list=listOf('path1'),plan=T.sequence(pages,list,{});
 assert.equal(plan.pages.length,Object.keys(pages).length);assert.equal(new Set(plan.pages.map(p=>p.folio)).size,plan.pages.length);assert.equal(plan.nodes.length,52);
 assert.deepEqual(T.sequence(pages,list,{group:'1.5a'}).nodes,['A:3-6','C:17-24','G:52-53','G:51-54','Q:93-96']);
 const g=T.sequence(pages,list,{group:'1.5a'});assert.deepEqual(g.pages.slice(0,4).map(p=>p.folio),['f3r','f3v','f6r','f6v']);assert.equal(g.pages.length,20);
 assert.deepEqual(T.sequence(pages,list,{group:'1.5a',route:'cycle:Ar'}).pages.map(p=>p.slot),['Ar','Bv','Br','Ar','Bv']);
 assert.ok(T.sequence(pages,list,{group:'3c'}).pages.some(p=>p.node.startsWith('N:')),'no pages are held back: the study left quire N out of 3c, this page does not');
 assert.ok(T.sequence(pages,list,{group:'5a'}).pages.length>0);
 assert.deepEqual(T.sequence(pages,list,{selected:['f51v','f52r','f53v']}).pages.map(p=>p.folio),['f52r','f53v','f51v']);
 assert.deepEqual(T.sequence(pages,listOf('bifolia'),{}).nodes,T.sequence(pages,listOf('folio'),{}).nodes,'by bifolium and by folio are one chain');
 assert.equal(T.nextBifolium(g.pages,3,1),4);assert.equal(T.nextBifolium(g.pages,4,-1),0);assert.equal(T.nextBifolium(g.pages,19,1),19);assert.equal(T.visible(g.pages,4,'all').length,5);assert.deepEqual(T.visible(g.pages,4,'pair').map(p=>p.folio),['f6v','f17r']);
});
test('registering and turning a page moves it whole and changes no word, on every page',{skip:!have},()=>{
 let units=0,turned=0;const quarantine=new Set(compact.quarantine);
 for(const [folio,page] of Object.entries(pages))for(const coords of T.COORDS)for(const scale of T.SCALES.filter(s=>s!=='paper')){
  const options={coords,scale},plain=T.register(folio,page,words,tokens,{...options,anchor:'opening'}),source=T.register(folio,page,words,tokens,{...options,anchor:'source'}),margin=T.register(folio,page,words,tokens,{...options,anchor:'margin'});
  const factor=scale==='body_height'?M.BODY_HEIGHT_PX/(page.H||30):1,raw=M.pageUnits(page,words);
  source.all.forEach((u,i)=>{const r=coords==='recorded'?raw[u.id].rect:raw[u.id].flat;near(u.rect[0],r[0]*factor,1e-6);near(u.rect[2],r[2]*factor,1e-6);assert.equal(u.rect[1],plain.all[i].rect[1]);near(margin.all[i].rect[0],plain.all[i].rect[0]-margin.shift);});
  for(const r of plain.marginRows){const [,first,category,orientation]=page.lines[r.line];assert.ok(!first&&category==='P'&&orientation==='horizontal');}
  const up=T.orient(page,margin,coords,'turn'),off=T.orient(page,margin,coords,'none'),back=T.orient(page,margin,coords,'restore');
  assert.equal(off.angle.delta,0);if(coords==='recorded')assert.equal(up.angle.delta,0);
  margin.all.forEach((u,i)=>{
   const q=up.words[i].quad,d=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
   near(d(q[0],q[1]),u.rect[2]-u.rect[0]);near(d(q[0],q[3]),u.rect[3]-u.rect[1]);assert.deepEqual(off.words[i].quad[0],[u.rect[0],u.rect[1]]);
   back.words[i].quad.forEach((p,j)=>assert.equal(p[0],off.words[i].quad[j][0]));units++;
  });
  back.marginRows.forEach(r=>assert.equal(r.point[0],r.x));
  if(up.angle.delta)turned++;
  if(up.angle.restored&&coords==='flat'&&scale==='pixels'){
   // an independent check: the flat chords, turned, must have the recorded median, from the boxes and not from the stored angles. The file rounds boxes
   // to 0.01 px, which puts a recalculated page angle up to 0.0021 degrees from the stored one (all 404 page angles), and this compares two of them
   const flat=M.pageDrift(page,words,'flat',quarantine.has(folio)),recorded=M.pageDrift(page,words,'recorded',quarantine.has(folio));
   near(M.median(flat.lines.filter(l=>l.qualifies).map(l=>l.angle+up.angle.delta)),recorded.angle,.005);assert.equal(flat.n,recorded.n);
  }
 }
 assert.ok(units>140000,`${units} word checks`);assert.ok(turned>300,`${turned} turned pages`);
});
test('on the parchment a page is in millimetres from its fold and its top edge, whatever the anchor, and its text lies on its leaf',{skip:!have||!compact.paper},()=>{
 let measured=0,units=0;const edge=T.LEAF_MM*T.PAPER_UNITS,mm=T.PAPER_UNITS;
 for(const [folio,page] of Object.entries(pages)){
  const P=page.paper;if(!P)continue;
  const raw=M.pageUnits(page,words),k=T.PAPER_UNITS/P.mm,off=page.side==='v'?edge:0;
  const reg=T.register(folio,page,words,tokens,{coords:'recorded',scale:'paper'}),other=T.register(folio,page,words,tokens,{coords:'recorded',scale:'paper',anchor:'opening'});
  reg.all.forEach((u,i)=>{const r=raw[u.id].rect;near(u.rect[0],(r[0]-P.fold)*k+off,1e-6);near(u.rect[3],(r[3]-P.top)*k,1e-6);assert.deepEqual(other.all[i].rect,u.rect);units++;});
  if(P.fold_method==='measured'&&P.top_method==='measured'&&reg.all.length){
   const xs=reg.all.flatMap(u=>[u.rect[0],u.rect[2]]),ys=reg.all.map(u=>u.rect[1]);
   // the fold is found outside the text: a recto's text starts right of it, a verso's ends left of it, and the text is below the top edge
   assert.ok(page.side==='v'?Math.max(...xs)<=edge+2*mm:Math.min(...xs)>=-2*mm,`${folio}: text across its fold`);assert.ok(Math.min(...ys)>=-2*mm,`${folio}: text above its top edge`);
   measured++;
  }
 }
 assert.ok(measured>=180,`${measured} pages measured`);assert.ok(units>30000,`${units} words`);
 assert.equal(T.register('f116v',pages.f116v,words,tokens,{scale:'paper'}).factor,1,'a page with no paper record keeps its pixels');
});
test('on the parchment the dewarped words stay on their leaf, whatever the tilt',{skip:!have||!compact.paper},()=>{
 const centre=o=>[0,1].map(j=>o.words.reduce((a,w)=>a+(w.quad[0][j]+w.quad[2][j])/2,0)/o.words.length),shifts=[];
 for(const [folio,page] of Object.entries(pages)){
  if(!page.paper)continue;
  const rec=T.orient(page,T.register(folio,page,words,tokens,{coords:'recorded',scale:'paper'}),'recorded','none');if(!rec.words.length)continue;
  const flat=tilt=>T.orient(page,T.register(folio,page,words,tokens,{coords:'flat',scale:'paper'}),'flat',tilt),level=flat('none'),at=centre(level);
  // putting the tilt back turns or shears the page about its own words, so it does not move the page off its leaf
  for(const tilt of ['restore','turn']){const c=centre(flat(tilt));near(c[0],at[0],1e-6);near(c[1],at[1],1e-6);}
  flat('restore').words.forEach((w,i)=>near(w.quad[0][0],level.words[i].quad[0][0],1e-9));
  shifts.push(Math.abs(at[1]-centre(rec)[1])/T.PAPER_UNITS);
 }
 // dewarping keeps the page where it was recorded: its mean shift is zero over the fitted points, so a few tenths of a millimetre over all words
 shifts.sort((a,b)=>a-b);
 assert.ok(shifts.length>=200&&shifts[Math.floor(.95*shifts.length)]<0.5&&shifts.at(-1)<1.5,`${shifts.length} pages, 95th ${shifts[Math.floor(.95*shifts.length)]} mm, worst ${shifts.at(-1)} mm`);
});
test('a restored page shows its recorded angle; a page with no angle stays as it is and says so',{skip:!have},()=>{
 const f8r=T.orient(pages.f8r,T.register('f8r',pages.f8r,words,tokens),'flat','restore');
 near(f8r.angle.displayed,pages.f8r.drift.recorded.angle);near(f8r.angle.delta,pages.f8r.drift.recorded.angle-pages.f8r.drift.flat.angle);assert.ok(f8r.angle.delta>3);
 const none=T.orient(pages.f67r2,T.register('f67r2',pages.f67r2,words,tokens),'flat','restore');
 assert.equal(none.angle.restored,false);assert.equal(none.angle.delta,0);assert.equal(none.angle.recorded,null);assert.ok(none.angle.unavailable);
 const all=Object.entries(pages).map(([f,p])=>[f,T.register(f,p,words,tokens)]),missing=all.filter(([,s])=>!s.available).map(([f])=>f);
 assert.ok(missing.length<=3,`pages with no opening box: ${missing.join(', ')}`);
 const b=T.bounds(all.map(([,s])=>s));assert.ok(Object.values(b).every(Number.isFinite));
});
test('f8v\'s first paragraph: the left rail in each display, against the frame\'s vertical',{skip:!have},()=>{
 const slope=pts=>{const n=pts.length,mx=pts.reduce((a,p)=>a+p[0],0)/n,my=pts.reduce((a,p)=>a+p[1],0)/n;let xy=0,yy=0;for(const [x,y] of pts){xy+=(x-mx)*(y-my);yy+=(y-my)**2;}return Math.atan2(xy,yy)*180/Math.PI;};
 const page=pages.f8v,first=new Set(page.blocks.find(b=>b[0]==='p1')[1]),rail=(coords,tilt)=>slope(T.orient(page,T.register('f8v',page,words,tokens,{coords,anchor:'source'}),coords,tilt).marginRows.filter(r=>first.has(r.line)).map(r=>r.point));
 near(rail('recorded','none'),4.15,.01);near(rail('flat','restore'),4.09,.01);near(rail('flat','turn'),7.29,.01);
 near(rail('recorded','restore'),rail('recorded','none'),1e-9);near(rail('recorded','turn'),rail('recorded','none'),1e-9);
});
test('restoring tilt keeps the recorded margin; a rigid turn leans it by the page\'s own turn',{skip:!have},()=>{
 const slope=pts=>{const n=pts.length,mx=pts.reduce((a,p)=>a+p[0],0)/n,my=pts.reduce((a,p)=>a+p[1],0)/n;let xy=0,yy=0;for(const [x,y] of pts){xy+=(x-mx)*(y-my);yy+=(y-my)**2;}return Math.atan2(xy,yy)*180/Math.PI;};
 const view=(f,coords,tilt)=>T.orient(pages[f],T.register(f,pages[f],words,tokens,{coords,anchor:'source'}),coords,tilt),gaps={back:[],turn:[],lean:[]};
 for(const f of Object.keys(pages)){
  const truth=view(f,'recorded','none'),back=view(f,'flat','restore'),turn=view(f,'flat','turn');
  if(truth.marginRows.length<6||!back.angle.restored)continue;
  const m=v=>slope(v.marginRows.map(r=>r.point));gaps.back.push(Math.abs(m(back)-m(truth)));gaps.turn.push(Math.abs(m(turn)-m(truth)));gaps.lean.push(Math.abs(m(turn)-(m(truth)-turn.angle.delta)));
 }
 const med=a=>M.median(a);
 assert.ok(gaps.back.length>170,`${gaps.back.length} pages`);
 assert.ok(med(gaps.back)<.05,`restored margin against the recorded margin: ${med(gaps.back)}`);
 assert.ok(med(gaps.turn)>.8,`a rigid turn moves the margin: ${med(gaps.turn)}`);
 assert.ok(med(gaps.lean)<.05,`and by the page's turn: ${med(gaps.lean)}`);
});
