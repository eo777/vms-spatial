'use strict';
// compare_state.js: the comparison page's address, Text resolution, hidden pages, zoom views, lists, frame, line rows,
// partners, overlap colours, match rows, wheel layout and export record.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const S=require('../compare_state.js'),M=require('../js/compare_math.js'),DATA=path.resolve(__dirname,'../data');
const gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,p))));
const have=['compare/pages.json.gz','compare/rankings.json.gz','compare/wheels.json.gz','compare/orders.json','manuscript/words.json.gz'].every(p=>fs.existsSync(path.join(DATA,p)));
const compact=have?gz('compare/pages.json.gz'):null,words=have?gz('manuscript/words.json.gz').words:null;
const rankings=have?gz('compare/rankings.json.gz'):null,wheels=have?gz('compare/wheels.json.gz'):null,orders=have?JSON.parse(fs.readFileSync(path.join(DATA,'compare/orders.json'),'utf8')):null;
const near=(a,b,eps=1e-9)=>assert.ok(Math.abs(a-b)<eps,a+' vs '+b);

test('the address: defaults are left out, every key round-trips, bad values fall back',()=>{
  const d=S.parse({});assert.deepEqual(S.serialize(d),{a:'f20v',b:'f21r'});
  assert.equal(d.view,'overlay');assert.equal(d.text,'page');assert.equal(d.color,'pages');assert.equal(d.words,false);assert.equal(d.rings,true);assert.deepEqual(d.hide,[]);
  const h={a:'f33v',b:'f75r',view:'segments',text:'custom',cutoff:'2',order:'path1',scope:'bifolia',face:'outer',align:'page',coords:'recorded',scale:'body',blocka:'p2',blockb:'l3',metric:'js',color:'area',gain:'5',words:'1',drift:'1',labels:'1',rings:'0',pages:'f1r,f2r,f1r',hide:'a,f2r,a',lines:'2,3',zoom:'1.234,2,300,450.5',seg:'b:12'};
  const s=S.parse(h),back=S.serialize(s);
  assert.deepEqual(back,{...h,pages:'f1r,f2r',hide:'a,f2r',zoom:'1.23,2,300,450.5'});
  assert.deepEqual(s.lines,[[2,3,0]]);assert.deepEqual(s.seg,{side:'b',id:12});assert.equal(s.gain,5);assert.equal(s.scale,'body');
  const bad=S.parse({view:'x',text:'top9',cutoff:'9',order:'y',face:'z',color:'rainbow',gain:'7',lines:'a,b',zoom:'1,2,3',seg:'c:1',blocka:'drop table',a:'f1r;x',hide:',;,f1r x'});
  assert.equal(bad.view,'overlay');assert.equal(bad.cutoff,'all');assert.equal(bad.order,'bifolia');assert.equal(bad.face,'inner');assert.equal(bad.gain,1);assert.equal(bad.color,'pages');
  assert.deepEqual(bad.lines,[]);assert.equal(bad.zoom,null);assert.equal(bad.seg,null);assert.equal(bad.blocka,'opening');assert.equal(bad.a,'f20v');assert.deepEqual(bad.hide,[]);
  assert.deepEqual(S.parse(S.serialize(s)),{...s,zoom:{x:1.23,y:2,w:300,h:450.5}});
  // a Top N preset carries no block or cutoff keys
  assert.deepEqual(S.serialize(S.parse({text:'3',blocka:'p2',cutoff:'1'})),{a:'f20v',b:'f21r',text:'3'});
});

test('Text: presets resolve to both blocks and the cutoff, older addresses are read, Settings changes switch to Custom',()=>{
  assert.deepEqual(S.resolveText(S.parse({})),{blocka:'page',blockb:'page',cutoff:'all'});
  assert.deepEqual(S.resolveText(S.parse({text:'3'})),{blocka:'opening',blockb:'opening',cutoff:'3'});
  assert.deepEqual(S.resolveText(S.parse({text:'custom',blocka:'p2',cutoff:'2'})),{blocka:'p2',blockb:'opening',cutoff:'2'});
  // the first release's links: cutoff=3 meant the opening blocks with three lines scored
  assert.equal(S.parse({cutoff:'3'}).text,'3');assert.equal(S.parse({cutoff:'all'}).text,'custom');assert.equal(S.parse({blocka:'p1'}).text,'custom');assert.equal(S.parse({cutoff:'3',blockb:'p2'}).text,'custom');
  const s=S.parse({text:'custom',blocka:'p2',blockb:'p3',cutoff:'4'});
  const preset=S.setText(s,'page');assert.equal(preset.text,'page');assert.equal(preset.blocka,'page');assert.equal(preset.blockb,'page');assert.equal(preset.cutoff,'all');
  const top=S.setText(s,'2');assert.deepEqual([top.blocka,top.blockb,top.cutoff],['opening','opening','2']);
  const kept=S.setText(s,'custom');assert.deepEqual([kept.blocka,kept.blockb,kept.cutoff],['p2','p3','4']);
  const c=S.customize(S.parse({text:'3'}),{blockb:'p2'});assert.equal(c.text,'custom');assert.deepEqual([c.blocka,c.blockb,c.cutoff],['opening','p2','3']);
  const c2=S.customize(S.parse({}),{cutoff:'1'});assert.deepEqual([c2.blocka,c2.blockb,c2.cutoff],['page','page','1']);
  assert.equal(S.setText(s,'nonsense').text,'page');
});

test('hidden pages: keys, toggling and the address',()=>{
  const s=S.parse({});
  assert.equal(S.hideKey(s,'A'),'a');assert.equal(S.hideKey(s,'B'),'b');assert.equal(S.hideKey(s,'f37r'),'f37r');
  const t=S.toggleHidden(s,'b');assert.deepEqual(t.hide,['b']);assert.equal(S.isHidden(t,'b'),true);assert.equal(S.isHidden(t,'a'),false);
  assert.deepEqual(S.toggleHidden(t,'b').hide,[]);assert.deepEqual(S.toggleHidden(S.toggleHidden(t,'f1r'),'f2r').hide,['b','f1r','f2r']);
  assert.equal(S.serialize(t).hide,'b');assert.deepEqual(S.parse({hide:'b,f1r'}).hide,['b','f1r']);
});

test('zoom views: 0.25x to 40x, the point under the cursor stays, reduced views contain the frame, magnified views stay inside it',()=>{
  const full={x:-100,y:-50,w:1000,h:500};
  const v2=S.zoomAt(full,full,2,{x:300,y:100});near(S.zoomScale(v2,full),2);near((300-v2.x)/v2.w,0.4);near((100-v2.y)/v2.h,0.3);
  const out=S.zoomAt(full,full,0.5,{x:300,y:100});near(S.zoomScale(out,full),0.5);assert.ok(out.x<=full.x&&out.x+out.w>=full.x+full.w&&out.y<=full.y&&out.y+out.h>=full.y+full.h);
  near((300-out.x)/out.w,0.4);
  const floor=S.zoomAt(full,full,0.01,{x:0,y:0});near(S.zoomScale(floor,full),S.MIN_ZOOM);
  const ceil=S.zoomAt(full,full,1e6,{x:0,y:0});near(S.zoomScale(ceil,full),S.MAX_ZOOM);
  const edge=S.zoomAt(full,full,4,{x:-100,y:-50});near(edge.x,-100);near(edge.y,-50);near(edge.w,250);
  const panned=S.pan(v2,full,-100,0,2);near(panned.x,v2.x+50);const stopped=S.pan(v2,full,-1e6,-1e6,2);near(stopped.x,full.x+full.w-v2.w);near(stopped.y,full.y+full.h-v2.h);
  // a reduced view may slide only as far as keeps the whole frame inside it: dragging right moves x down to full.x + full.w - w, dragging left up to full.x
  const pannedOut=S.pan(out,full,1e6,0,0.5);near(pannedOut.x,full.x+full.w-out.w);const pannedOut2=S.pan(out,full,-1e6,0,0.5);near(pannedOut2.x,full.x);
  assert.equal(S.isFit(null,full),true);assert.equal(S.isFit(S.clampView(full,full),full),true);assert.equal(S.isFit(v2,full),false);
});

test('stepping wraps around and tolerates a current value outside the list',()=>{
  const list=['f1r','f1v','f2r'];
  assert.equal(S.step(list,'f1v',1),'f2r');assert.equal(S.step(list,'f2r',1),'f1r');assert.equal(S.step(list,'f1r',-1),'f2r');assert.equal(S.step(list,'zz',1),'f1r');assert.equal(S.step([],'f1r',1),'f1r');
});

test('lists: pages of an order, the sheets with their slots, the face slots, the pages with wheels',{skip:!have},()=>{
  for(const order of ['bifolia','folio','path1']){const list=S.pageList(orders,order,compact.pages);assert.equal(list.length,227);assert.equal(new Set(list).size,227);}
  const folioList=S.pageList(orders,'folio',compact.pages);assert.equal(folioList[0],'f1r');
  const sheets=S.sheetList(compact.pages,folioList);assert.equal(sheets.length,52);assert.equal(sheets[0].id,'A:1-8');
  const c=sheets.find(s=>s.id==='C:20-21');assert.deepEqual(c.slots,{Ar:['f20r'],Av:['f20v'],Br:['f21r'],Bv:['f21v']});
  assert.deepEqual(S.slotPages(c,'inner').map(x=>x.folio),['f20v','f21r']);
  const k=sheets.find(s=>s.id==='K:71-72'),inner=S.slotPages(k,'inner');assert.equal(inner[1].folio,'f72r1');assert.equal(inner[1].panels,3);
  assert.equal(S.slotPages(null,'both').length,4);assert.deepEqual(S.SLOTS.outer,['Bv','Ar']);
  const wp=S.wheelPages(wheels,compact.pages,folioList);assert.equal(wp.length,26);assert.equal(wp[0],'f57v');
  const zodiac=S.wheelPages(wheels,compact.pages,folioList,'Zodiac');assert.equal(zodiac.length,12);assert.ok(zodiac.includes('f72r1')&&!zodiac.includes('f57v'));
  assert.equal(S.wheelPages(wheels,compact.pages,folioList,'Astronomical').length,5);
});

test('frame, line rows and the nearest partner line on f20v / f21r',{skip:!have},()=>{
  const sel=f=>M.selectUnits(compact.pages[f],words,{block:'opening',cutoff:3,coordinates:'flat',alignment:'starts'});
  const a=sel('f20v'),b=sel('f21r'),F=S.frame([a,b],'3');
  assert.ok(F.x<0&&F.y<0&&F.w>0&&F.h>0);
  for(const u of S.visible(a,'3').concat(S.visible(b,'3'))){assert.ok(u.rect[0]>=F.x&&u.rect[2]<=F.x+F.w&&u.rect[1]>=F.y&&u.rect[3]<=F.y+F.h);}
  assert.ok(S.visible(a,'3').every(u=>u.line<5));assert.ok(S.visible(a,'all').length>=S.visible(a,'3').length);
  const rows=S.lineRows(a,'3');assert.deepEqual(rows.map(r=>r.index),[0,1,2,3,4]);assert.equal(rows[0].chosen,true);assert.equal(rows[4].chosen,false);
  assert.ok(rows.every((r,i)=>i===0||r.baseline>rows[i-1].baseline),'baselines increase down the page');
  assert.ok(rows[1].text.split(' ').length>=4);
  const partner=S.nearestLine(S.lineRows(b,'3'),rows[1].baseline);assert.equal(partner.index,1);
  assert.equal(S.nearestLine([],0),null);
  assert.deepEqual(S.frame([],'3'),{x:-50,y:-50,w:100,h:100});
  // whole pages: the frame holds every unit of both pages
  const wa=M.selectUnits(compact.pages.f20v,words,{block:'page',cutoff:'all',coordinates:'flat',alignment:'starts'}),Fw=S.frame([wa],'all');
  assert.equal(S.visible(wa,'all').length,wa.all.length);assert.ok(Fw.h>F.h);
});

test('segment partners of a clicked unit come from the direct records first, then the nearby ones',{skip:!have},()=>{
  const sel=f=>M.selectUnits(compact.pages[f],words,{block:'opening',cutoff:3,coordinates:'flat',alignment:'starts'});
  const a=sel('f20v'),b=sel('f21r'),det=M.details(a,b);
  const first=det.direct.find(r=>r.a.length===1),p=S.partners(det,'a',first.a[0]);
  assert.equal(p.kind,'direct');assert.deepEqual(p.b,first.b);
  const lonely=a.chosen.filter(u=>!u.anchor).map(u=>u.id).find(id=>!det.direct.some(r=>r.a.length===1&&r.a[0]===id));
  if(lonely!==undefined){const q=S.partners(det,'a',lonely);assert.ok(q===null||q.kind==='nearby');}
  assert.equal(S.partners(null,'a',0),null);assert.equal(S.partners(det,'b',99999),null);
});

test('overlap colours on f20v / f21r: area shares, best-partner similarity and the JS distance per box',{skip:!have},()=>{
  const sel=f=>M.selectUnits(compact.pages[f],words,{block:'opening',cutoff:3,coordinates:'flat',alignment:'starts'});
  const a=sel('f20v'),b=sel('f21r'),ov=S.overlapValues(a,b),A=a.chosen,B=b.chosen;
  assert.equal(ov.a.size,A.length);assert.equal(ov.b.size,B.length);
  let touched=0;
  for(const u of A){const v=ov.a.get(u.id),parts=B.filter(w=>M.intersection(u.rect,w.rect));
    if(!parts.length){assert.equal(v,null);continue;}touched++;
    assert.deepEqual(v.partners,parts.map(w=>w.id));
    near(v.area,Math.min(1,M.unionArea(parts.map(w=>M.intersection(u.rect,w.rect)))/M.area(u.rect)));
    assert.ok(v.area>0&&v.area<=1);assert.ok(v.sim>=0&&v.sim<=1);near(v.sim,Math.max(...parts.map(w=>M.similarity(u.atoms,w.atoms))));
    if(v.js!==null){assert.ok(v.js>=0&&v.js<=1+1e-9);near(v.js,M.jsDistance(M.lineFeatures(u.text).joined,M.lineFeatures(parts.map(w=>w.text).join(' ')).joined));}
    for(const id of v.partners){const back=ov.b.get(id);assert.ok(back&&back.partners.includes(u.id),'partnership is mutual');}
  }
  assert.ok(touched>=A.length/2,'most scored boxes of A touch a box of B');
  // a box fully covered by one identical word: area 1, similarity 1, JS 0
  const u={id:0,text:'chol',atoms:M.atoms('chol'),rect:[0,0,40,20],anchor:false},v={id:0,text:'chol',atoms:M.atoms('chol'),rect:[-5,-5,50,25],anchor:false};
  const same=S.overlapValues({chosen:[u]},{chosen:[v]});near(same.a.get(0).area,1);near(same.a.get(0).sim,1);near(same.a.get(0).js,0);assert.ok(same.b.get(0).area<1);
  const apart=S.overlapValues({chosen:[u]},{chosen:[{...v,rect:[100,100,140,120]}]});assert.equal(apart.a.get(0),null);assert.equal(apart.b.get(0),null);
  assert.equal(S.colorIndex(null,'js'),null);assert.equal(S.colorIndex(0,'js'),500);assert.equal(S.colorIndex(1,'js'),0);assert.equal(S.colorIndex(0.5,'area'),250);assert.equal(S.colorIndex(2,'sim'),500);
  // the palette spans the 5th to 95th percentile of the boxes in view, as the atlas does for its component colours
  assert.deepEqual(S.colorDomain([0.2,0.4,0.6]),[0,1]);assert.deepEqual(S.colorDomain([0.5,0.5,0.5,0.5,0.5,0.5]),[0,1]);
  const dom=S.colorDomain(Array.from({length:101},(_,i)=>i/100));near(dom[0],0.05);near(dom[1],0.95);
  assert.equal(S.colorIndex(0.05,'area',dom),0);assert.equal(S.colorIndex(0.95,'area',dom),500);assert.equal(S.colorIndex(0.5,'area',dom),250);assert.equal(S.colorIndex(0.01,'sim',dom),0);assert.equal(S.colorIndex(0.05,'js',dom),500);
  const jsDom=S.colorDomain([...ov.a.values(),...ov.b.values()].map(v=>v&&v.js));assert.ok(jsDom[0]>=0&&jsDom[1]<=1&&jsDom[0]<jsDom[1]);
});

test('match rows: the shipped order for the combined rank, re-sorted for one metric; bifolium faces',{skip:!have},()=>{
  const s=S.parse({a:'f20v'}),rows=S.matchRows(rankings,s);
  assert.equal(rows.length,50);assert.equal(rows[0].b,'f78v');assert.equal(rows[0].position,307);assert.ok(rows.every((r,i)=>i===0||r.position>=rows[i-1].position));
  const byDice=S.matchRows(rankings,{...s,metric:'dice'});assert.ok(byDice.every((r,i)=>i===0||r.dice<=byDice[i-1].dice));assert.equal(new Set(byDice.map(r=>r.b)).size,50);
  const byJs=S.matchRows(rankings,{...s,metric:'js'});assert.ok(byJs.every((r,i)=>i===0||r.js>=byJs[i-1].js));
  assert.equal(S.matchIndex(rows,{...s,b:'f83r'}),1);assert.equal(S.matchIndex(rows,{...s,b:'f20v'}),-1);
  const bif=S.matchRows(rankings,{...s,scope:'bifolia',face:'inner'});assert.equal(bif.length,50);assert.equal(bif[0].a,'F:43-46');assert.equal(bif[0].b,'T:106-113');assert.ok(Number.isFinite(bif[0].weakest));
  assert.equal(S.matchIndex(bif,{...s,scope:'bifolia',face:'inner',a:'T:106-113',b:'F:43-46'}),0);
  assert.deepEqual(S.matchRows(rankings,{...s,a:'nope'}),[]);
});

test('the centred wheel layout moves every wheel to the origin and nothing else',{skip:!have},()=>{
  const page=compact.pages.f72r1,units=M.pageUnits(page,words),lay=S.wheelLayout('f72r1',wheels.pages.f72r1,units);
  assert.equal(lay.wheels.length,1);const w=lay.wheels[0];assert.equal(w.rings.length,3);assert.ok(Math.abs(w.rings[1].cx)<1e-9&&Math.abs(w.rings[1].cy)<1e-9,'the median ring sits at the origin');
  assert.equal(w.boxes.length,41+24+13);assert.equal(w.labels.length,23);
  const u=units[0];assert.deepEqual(w.boxes[0].rect,[u.rect[0]-w.centre[0],u.rect[1]-w.centre[1],u.rect[2]-w.centre[0],u.rect[3]-w.centre[1]]);
  assert.ok(lay.radius>=w.radius&&lay.radius<w.radius*1.5);
  assert.deepEqual(S.wheelLayout('f20v',undefined,[]),{wheels:[],radius:0});
  const ros=S.wheelLayout('fRos',wheels.pages.fRos,M.pageUnits(compact.pages.fRos,words));assert.equal(ros.wheels.length,9);
});

test('the export record carries the settings, scores, segments and both geometries',{skip:!have},()=>{
  const sel=f=>M.selectUnits(compact.pages[f],words,{block:'opening',cutoff:3,coordinates:'flat',alignment:'starts'});
  const a=sel('f20v'),b=sel('f21r'),s=S.parse({text:'3'}),rec=S.exportRecord(s,compact,a,b,M.measure(a,b),M.details(a,b),M.perLine(a,b),{a:null,b:null});
  assert.equal(rec.settings.a,'f20v');assert.equal(rec.settings.scale,'pixels');assert.equal(rec.settings.block_a,'opening');assert.equal(rec.settings.cutoff,'3');assert.ok(Math.abs(rec.scores.dice-0.71)<0.02);
  assert.equal(rec.geometry.a.units.length,a.chosen.length);assert.equal(rec.geometry.b.block,'opening');assert.ok(rec.segments.length>0);assert.equal(rec.per_line.length,3);
  JSON.stringify(rec);
});

test('stepping both moves A and B together: the gap holds, and it wraps at the ends like one page',()=>{
 const list=['f1r','f1v','f2r','f2v','f3r'];
 assert.deepEqual(S.stepPair(list,'f1r','f1v',1),['f1v','f2r']);assert.deepEqual(S.stepPair(list,'f1v','f2r',-1),['f1r','f1v']);
 assert.deepEqual(S.stepPair(list,'f1r','f2v',1),['f1v','f3r']);                       // a wider gap stays that wide
 assert.deepEqual(S.stepPair(list,'f2v','f3r',1),['f3r','f1r']);assert.deepEqual(S.stepPair(list,'f1r','f1v',-1),['f3r','f1r']);
 for(let i=0,p=['f1r','f2r'];i<list.length;i++){p=S.stepPair(list,p[0],p[1],1);if(i===list.length-1)assert.deepEqual(p,['f1r','f2r']);}   // once round comes home
});
test('the arrows step by page, sheet or paragraph',{skip:!have},()=>{
 assert.equal(S.parse({}).step,'page');assert.equal(S.parse({step:'paragraph'}).step,'paragraph');assert.equal(S.parse({step:'x'}).step,'page');
 assert.equal(S.serialize(S.parse({})).step,undefined);assert.equal(S.serialize(S.parse({step:'bifolio'})).step,'bifolio');
 const list=orders.folio.pages.filter(f=>compact.pages[f]),sheets=S.sheetList(compact.pages,list),pages=compact.pages;
 const slot=f=>pages[f].slot,node=f=>pages[f].node,next=S.stepSheet(sheets,pages,'f1v',1);
 assert.notEqual(node(next),node('f1v'));assert.equal(slot(next),slot('f1v'));   // the same slot of the next sheet
 assert.equal(S.stepSheet(sheets,pages,next,-1),'f1v');
 assert.deepEqual(S.paragraphKeys(pages.f20v),['p1','p2']);assert.deepEqual(S.paragraphKeys(pages.f72r1),[]);
 assert.deepEqual(S.stepParagraph(pages,list,'f20v','page',1),{folio:'f20v',block:'p1'});   // a whole page enters at its first paragraph
 assert.deepEqual(S.stepParagraph(pages,list,'f20v','page',-1),{folio:'f20v',block:'p2'});
 assert.deepEqual(S.stepParagraph(pages,list,'f20v','p1',1),{folio:'f20v',block:'p2'});
 const on=S.stepParagraph(pages,list,'f20v','p2',1),back=S.stepParagraph(pages,list,on.folio,on.block,-1);
 assert.notEqual(on.folio,'f20v');assert.equal(on.block,'p1');assert.deepEqual(back,{folio:'f20v',block:'p2'});   // off the end, and back
 const i=list.indexOf('f72r1'),before=list.slice(0,i).reverse().find(f=>S.paragraphKeys(pages[f]).length);
 assert.equal(S.stepParagraph(pages,list,before,S.paragraphKeys(pages[before]).slice(-1)[0],1).folio!=='f72r1',true);   // pages with no paragraph are passed over
});
test('the first box is scored: a pair sharing only its first word still scores',()=>{
 const u=(text,rect,anchor)=>({rect,atoms:M.atoms(text),line:0,anchor,text});
 const a=[u('faiis',[0,0,40,20],true),u('qokedy',[60,0,100,20],false)],b=[u('faiis',[0,0,40,20],true),u('chol',[200,0,240,20],false)];
 const m=M.measureUnits(a,b,50,20);
 assert.equal(m.units_a,2);assert.equal(m.units_b,2);assert.ok(m.dice>0,'the shared first box counts toward Dice');assert.ok(m.local_segment_similarity>0,'and toward direct EVA');
});
test('a line comparison can name its panel, and two-number links still open',()=>{
 assert.deepEqual(S.parse({lines:'2,3'}).lines,[[2,3,0]]);assert.deepEqual(S.parse({lines:'2,3,1'}).lines,[[2,3,1]]);assert.deepEqual(S.parse({lines:'2,3,0'}).lines,[[2,3,0]]);
 assert.deepEqual(S.parse({lines:'2,3,x'}).lines,[]);assert.equal(S.serialize(S.parse({lines:'2,3,1'})).lines,'2,3,1');
 // one open line per panel: several in the address, the latest last, and a panel holds only one
 assert.deepEqual(S.parse({lines:'2,3,1;4,5'}).lines,[[2,3,1],[4,5,0]]);assert.equal(S.serialize(S.parse({lines:'2,3,1;4,5'})).lines,'2,3,1;4,5');
 assert.deepEqual(S.parse({lines:'2,3,1;4,5,1'}).lines,[[4,5,1]]);assert.deepEqual(S.parse({lines:'2,3;x'}).lines,[]);assert.equal('lines' in S.serialize(S.parse({})),false);
 const open=[[2,3,0],[4,5,1]];assert.deepEqual(S.lineAt(open,1),[4,5,1]);assert.equal(S.lineAt(open,2),null);
 assert.deepEqual(S.setLine(open,0,[6,7]),[[4,5,1],[6,7,0]]);assert.deepEqual(S.setLine(open,1,null),[[2,3,0]]);
 assert.equal(S.parse({expand:'1'}).expand,true);assert.equal(S.parse({}).expand,false);assert.equal(S.serialize(S.parse({expand:'1'})).expand,'1');assert.equal('expand' in S.serialize(S.parse({})),false);
 // the maximized panel
 assert.equal(S.parse({max:'1'}).max,1);assert.equal(S.parse({max:'x'}).max,null);assert.equal(S.parse({}).max,null);
 assert.equal(S.serialize(S.parse({max:'0'})).max,'0');assert.equal('max' in S.serialize(S.parse({})),false);
});
test('paragraph spans follow the page\'s own paragraphs and leave out labels and rings',{skip:!have},()=>{
 const opt={block:'page',cutoff:'all',coordinates:'flat',alignment:'starts',scale:'pixels'},sel=f=>M.selectUnits(compact.pages[f],words,opt);
 const a=S.paragraphSpans(sel('f20v'),'all');
 assert.deepEqual(a.map(p=>[p.n,p.first,p.last,p.rows,p.total]),[[1,1,4,4,4],[2,5,11,7,7]]);
 assert.ok(a[0].y0<a[0].y1&&a[0].y1<a[1].y0,'paragraphs run down the page without overlapping');
 assert.deepEqual(S.paragraphSpans(sel('f72r1'),'all'),[]);                      // ring text is in no paragraph
 const top=M.selectUnits(compact.pages.f20v,words,{...opt,block:'opening',cutoff:3}),t=S.paragraphSpans(top,3);
 assert.deepEqual(t.map(p=>[p.n,p.rows,p.total]),[[1,4,4],[2,1,7]]);             // the opening block's five lines cross into paragraph 2
 assert.deepEqual(S.paragraphSpans({},'all'),[]);
});
test('a page move keeps the open line by number, or the nearest number a short page has',()=>{
 const rows=(...r)=>r.map(([index,baseline])=>({index,baseline})),a=rows([0,10],[1,40],[2,70],[3,100]),b=rows([0,12],[1,30],[2,48],[3,66],[4,84],[5,102]);
 assert.deepEqual(S.carriedLines(a,b,0,2),[2,3]);                               // A keeps its line, B takes the partner by baseline
 assert.deepEqual(S.carriedLines(a,b,1,2),[1,2]);                               // B keeps its line
 assert.deepEqual(S.carriedLines(a,b,0,9),[3,5]);                               // a short page: its last line
 assert.deepEqual(S.carriedLines(rows([0,10],[1,40],[4,130]),b,0,3),[4,5]);     // a gap in the numbers: the nearest
 assert.equal(S.carriedLines([],b,0,1),null);assert.equal(S.carriedLines(a,[],1,1),null);
});
test('a zoom carried to another page keeps its scale and stays inside the new frame',()=>{
 const a={x:0,y:0,w:600,h:800},b={x:-50,y:-20,w:700,h:500},v=S.zoomAt(a,a,3,{x:500,y:700}),k=S.clampView(v,b);
 assert.ok(Math.abs(k.w-v.w)<1e-9);assert.ok(Math.abs(k.h-k.w*b.h/b.w)<1e-9);assert.equal(S.isFit(k,b),false);
 assert.ok(k.x>=b.x&&k.y>=b.y&&k.x+k.w<=b.x+b.w+1e-9&&k.y+k.h<=b.y+b.h+1e-9);
});
test('Bifolio steps keep A and B on their own slots through sheets with lost leaves',{skip:!have},()=>{
 const pages=compact.pages,list=S.pageList(orders,'bifolia',pages),sheets=S.sheetList(pages,list);
 const walk=(a,b,n,d)=>{const held={a:{},b:{}},seen=[],go=(k,f)=>{const slot=held[k].folio===f?held[k].slot:pages[f].slot,to=S.stepSheet(sheets,pages,f,d,slot);held[k]={folio:to,slot};return to;};for(let i=0;i<n;i++){a=go('a',a);b=go('b',b);seen.push([a,b]);}return seen;};
 for(const [a,b] of [['f1v','f8r'],['f8v','f1r'],['f20v','f21r'],['f24v','f17r'],['f1r','f1v']]){
  for(const d of [1,-1]){
   const round=walk(a,b,sheets.length,d);
   for(const [x,y] of round)assert.notEqual(x,y,`${a}/${b} step ${d}: both sides on ${x}`);
   for(const [x,y] of round)assert.equal(pages[x].node,pages[y].node,`${x} and ${y} stay on one sheet`);
   assert.deepEqual(round[round.length-1],[a,b],'a full round comes home');
  }
 }
 const w=walk('f1v','f8r',16,1).map(p=>p.join('/'));
 assert.deepEqual(w.slice(5,10),['f11v/f14r','f13v/f13r','f17v/f24r','f18v/f23r','f19v/f22r'],'past the lost f12 the inner faces return');
 assert.equal(S.stepSheet(sheets,pages,'f11v',1),'f13v','the same side of the other leaf');
 assert.equal(S.stepSheet(sheets,pages,'f72r1',1),'f73r');assert.equal(S.stepSheet(sheets,pages,'f72v1',1),'f73v');
});
test('Expand all lines shows every line of both pages once, each beside its partner',{skip:!have},()=>{
 const opt={block:'page',cutoff:'all',coordinates:'flat',alignment:'starts',scale:'pixels'},sel=f=>M.selectUnits(compact.pages[f],words,opt);
 const a=sel('f20v'),b=sel('f21r'),rows=[a,b].map(s=>S.lineRows(s,'all')),pairs=S.linePairs(rows[0],rows[1]);
 for(const k of [0,1])assert.deepEqual(pairs.filter(p=>p[k]).map(p=>p[k].index).sort((x,y)=>x-y),rows[k].map(r=>r.index));    // each line once
 for(const [x,y] of pairs)if(x&&y){assert.equal(S.nearestLine(rows[1],x.baseline),y);assert.equal(S.nearestLine(rows[0],y.baseline),x);}
 const e=S.expandLines(a,b,'all',.5);assert.equal(e.frame,'display');assert.equal(e.bands.length,pairs.length);
 e.bands.forEach(([y0,y1],i)=>{assert.ok(y1>y0);if(i)assert.ok(y0>=e.bands[i-1][1]-1e-9,'bands do not overlap');});
 e.selections.forEach((s,k)=>{const src=[a,b][k];assert.equal(s.all.length,src.all.length);
  s.all.forEach((u,i)=>{const o=src.all[i];assert.equal(u.rect[0],o.rect[0]);assert.equal(u.rect[2],o.rect[2]);assert.ok(Math.abs((u.rect[3]-u.rect[1])-(o.rect[3]-o.rect[1]))<1e-9);
   assert.ok(e.bands.some(([y0,y1])=>u.rect[1]>=y0-1e-6&&u.rect[3]<=y1+1e-6),'every box lies inside a band');});});
 const within=src=>new Map(src.all.map(u=>[u.id,u.rect[1]]));                    // a line moves as one, so its slope is kept
 const A=within(a),dys=new Map();for(const u of e.selections[0].all){const d=u.rect[1]-A.get(u.id);if(dys.has(u.line))assert.ok(Math.abs(dys.get(u.line)-d)<1e-9);dys.set(u.line,d);}
 assert.deepEqual(S.lineRows(a,'all').map(r=>r.index),rows[0].map(r=>r.index));    // the scored selection is untouched
});
test('Expand all lines leaves out a hidden or missing page and keeps rings in their shape',{skip:!have},()=>{
 const opt={block:'page',cutoff:'all',coordinates:'flat',alignment:'starts',scale:'pixels'},sel=f=>M.selectUnits(compact.pages[f],words,opt);
 const a=sel('f20v'),b=sel('f21r'),n=S.lineRows(b,'all').length;
 assert.equal(S.expandLines(a,b,'all',1,[true,false]).bands.length,n);assert.equal(S.expandLines(null,b).bands.length,n);assert.equal(S.expandLines(b,null).selections[1],null);
 assert.equal(S.expandLines(null,null),null);assert.equal(S.expandLines(a,b,'all',1,[true,true]),null);
 const ring=sel('f72r1'),e=S.expandLines(ring,null),moved=e.selections[0].all,kinds=new Set(ring.line_info.map(l=>l.orientation));
 assert.ok(kinds.size>1||!kinds.has('horizontal'));
 const level=new Set(ring.line_info.filter(l=>l.orientation==='horizontal').map(l=>l.index)),d=moved.map((u,i)=>[u,u.rect[1]-ring.all[i].rect[1]]).filter(([u])=>!level.has(u.line)).map(x=>x[1]);
 assert.ok(d.length&&d.every(v=>Math.abs(v-d[0])<1e-9),'rings move together');
});
test('the label gutter clears the leftmost box at fit zoom and leaves a wide enough margin alone',{skip:!have},()=>{
 const sel=M.selectUnits(compact.pages.f20v,words,{block:'page',cutoff:'all',coordinates:'flat',alignment:'starts',scale:'pixels'}),F=S.frame([sel],'all');
 const left=Math.min(...S.visible(sel,'all').map(u=>u.rect[0]));
 for(const px of [300,450,900]){const G=S.withGutter(F,[sel],'all',px,60);assert.ok((left-G.x)*px/G.w>=60-1e-6,px+': '+(left-G.x)*px/G.w);assert.equal(G.y,F.y);assert.equal(G.h,F.h);}
 assert.deepEqual(S.withGutter(F,[sel],'all',20000,60),F);
});
test('a block with no box on its first line is aligned on its first located line and not scored',{skip:!have},()=>{
 const opt={block:'opening',cutoff:3,coordinates:'flat',alignment:'starts',scale:'pixels'},page=compact.pages.f20v,s=M.selectUnits({...page,_units:null,units:page.units.filter(u=>u[2]!==0)},words,opt);
 assert.equal(s.available,false);assert.equal(s.fallback_line,1);assert.ok(Math.hypot(...s.origin)>100);
 assert.ok(Math.abs(s.all.find(u=>u.line===1).baseline)<40,'the block sits at the origin');
 const fine=M.selectUnits(compact.pages.f20v,words,opt);assert.equal(fine.available,true);assert.equal(fine.fallback_line,null);
});
test('the address carries the box style, with the atlas\'s values and key, and filled is the default',()=>{
 assert.equal(S.parse({}).boxes,'fill');assert.equal(S.parse({boxes:'hidden'}).boxes,'hidden');assert.equal(S.parse({boxes:'outline'}).boxes,'outline');assert.equal(S.parse({boxes:'none'}).boxes,'fill');
 assert.equal(S.serialize(S.parse({})).boxes,undefined);assert.equal(S.serialize(S.parse({boxes:'hidden'})).boxes,'hidden');
});
test('the address carries the word direction, and bottom to centre is the default',()=>{
 assert.equal(S.parse({}).wdir,'ring');assert.equal(S.parse({wdir:'level'}).wdir,'level');assert.equal(S.parse({wdir:'sideways'}).wdir,'ring');
 assert.equal(S.serialize(S.parse({})).wdir,undefined);assert.equal(S.serialize(S.parse({wdir:'level'})).wdir,'level');
});
test('every ring box of every wheel faces its centre, at one size round the ring',{skip:!have},()=>{
 const W=require('../js/word_labels.js'),lines=gz('manuscript/words.json.gz').lines,lineOf=new Int32Array(words.length).fill(-1);
 lines.forEach((L,i)=>{for(let t=L.start;t<L.end;t++)lineOf[t]=i;});
 const median=v=>[...v].sort((a,b)=>a-b)[Math.floor(v.length/2)],clock=(a,h)=>Math.abs(((a-h+180)%360+360)%360-180)<25;
 let boxes=0,worst=0,sides=[],tops=[];
 for(const [folio,rec] of Object.entries(wheels.pages)){
  const lay=S.wheelLayout(folio,rec,M.pageUnits(compact.pages[folio],words));
  for(const w of lay.wheels){
   const items=w.boxes.map(u=>{const L=lines[lineOf[u.first]];return {rect:u.rect,text:u.text,angle:W.angleOf(L.orientation,u.first-L.start)};});
   const faces=W.layout(items,'ring');
   items.forEach((it,i)=>{
    assert.notEqual(it.angle,null,folio+' has a ring box with no direction');
    const want=W.ringAngle((it.rect[0]+it.rect[2])/2,(it.rect[1]+it.rect[3])/2,0,0),off=Math.abs(((it.angle-want+180)%360+360)%360-180);
    worst=Math.max(worst,off);boxes++;
    if(clock(it.angle,90)||clock(it.angle,-90))sides.push(faces[i].size);else if(clock(it.angle,0))tops.push(faces[i].size);
   });
  }
 }
 assert.equal(boxes,2216);assert.ok(worst<0.5,'a ring box is '+worst+' degrees off its centre');
 assert.ok(Math.abs(median(sides)/median(tops)-1)<0.15,`median size ${median(sides)} at 3 and 9 o'clock against ${median(tops)} at 12`);
});
