// The Sections page's geometry on the real data: polygons hold their lines, paragraphs land on their anchors, heatmap votes are per page.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),zlib=require('zlib');
const M=require('../js/compare_math.js'),X=require('../js/section_math.js');
const DATA=path.join(__dirname,'..','data'),gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,p))));
const have=['compare/pages.json.gz','compare/orders.json','manuscript/words.json.gz'].every(p=>fs.existsSync(path.join(DATA,p)));
const compact=have?gz('compare/pages.json.gz'):null,bundle=have?gz('manuscript/words.json.gz'):null,orders=have?JSON.parse(fs.readFileSync(path.join(DATA,'compare/orders.json'))):null;
const pages=have?compact.pages:null,words=have?bundle.words:null,tokens=have?X.lineTokens(bundle.lines):null,list=have?orders.bifolia.pages.filter(f=>pages[f]):null;
const run=(f,o={})=>X.extract(f,pages[f],words,tokens,{align:'page',anchor:'opening',coordinates:'flat',scale:'pixels',...o});
const near=(a,b,eps=1e-6)=>assert.ok(Math.abs(a-b)<=eps,`${a} vs ${b}`);

test('the address round-trips, and bad values fall back',()=>{
 const h={by:'golf',group:'1a',align:'starts',anchor:'bottom-left',coords:'recorded',scale:'body_height',color:'bifolium',cell:'40',palette:'amber',focus:'f20v',layers:'boxes,ends',op:'10,20,30,40,50,60,70'};
 assert.deepEqual(X.serialize(X.parse(h)),h);
 assert.deepEqual(X.serialize(X.parse({})),{});
 const bad=X.parse({by:'x',align:'y',anchor:'z',cell:'7',palette:'q',layers:'heatmap,drop',op:'200,-1,abc'});
 assert.equal(bad.by,'section');assert.equal(bad.cell,'20');assert.equal(bad.palette,'blues');assert.deepEqual(bad.layers,['heatmap']);assert.equal(bad.op.heatmap,X.OPACITY_DEFAULTS.heatmap);
 assert.deepEqual(X.parse({layers:'none'}).layers,[]);assert.equal(X.serialize(X.parse({layers:'none'})).layers,'none');
});
test('a polygon holds its rows, joins them across whitespace and splits at a large step',()=>{
 const one=X.paragraphPolygons([{position:0,line:0,locus:'1',rect:[10,10,110,30],cy:20}],30);
 assert.equal(one.length,1);assert.deepEqual(one[0].points,[[10,10],[10,30],[110,30],[110,10]]);
 const rows=[{position:0,line:0,locus:'1',rect:[10,10,110,30],cy:20},{position:1,line:1,locus:'2',rect:[20,50,90,70],cy:60}],[p]=X.paragraphPolygons(rows,40);
 assert.ok(p.points.some(q=>q[1]===40),'rows join halfway across the gap');
 assert.deepEqual(p.lines,[0,1]);
 assert.equal(X.paragraphPolygons(rows,5).length,2,'a step over 2.5 pitches splits');
 assert.equal(X.paragraphPolygons([rows[0],{...rows[1],position:2}],40).length,2,'a missing row splits');
});
test('groups cover every page once, in manuscript order',{skip:!have},()=>{
 for(const by of X.BY){const g=X.groups(pages,list,by);assert.equal(g.flatMap(x=>x.pages).length,list.length);assert.equal(new Set(g.flatMap(x=>x.pages)).size,list.length);}
 const s=X.groups(pages,list,'section');assert.equal(s[0].name,'Herbal A');assert.equal(s[0].pages.length,95);
 assert.deepEqual(s[0].pages.slice(0,3),list.filter(f=>pages[f].section==='Herbal A').slice(0,3));
 assert.equal(X.groups(pages,list,'golf')[0].name,'1a');
});
test('page positions move a page by one translation and keep box sizes',{skip:!have},()=>{
 const e=run('f20v'),sel=M.selectUnits(pages.f20v,words,{block:'page',cutoff:'all',coordinates:'flat',alignment:'page'});
 assert.equal(e.available,true);assert.equal(e.boxes.length,sel.all.filter(u=>pages.f20v.lines[u.line_abs][3]==='horizontal').length);
 assert.equal(e.paragraphs.length,2);assert.equal(e.features.filter(f=>f.type==='start').length,2);
 const scaled=run('f20v',{scale:'body_height'}),k=M.BODY_HEIGHT_PX/pages.f20v.H;
 e.boxes.forEach((b,i)=>b.rect.forEach((v,j)=>near(scaled.boxes[i].rect[j],v*k,1e-6)));
 const rec=run('f20v',{coordinates:'recorded'});e.boxes.forEach((b,i)=>{near(b.rect[0],rec.boxes[i].rect[0]+e.boxes[0].rect[0]-rec.boxes[0].rect[0],1e-6);near(b.rect[2]-b.rect[0],rec.boxes[i].rect[2]-rec.boxes[i].rect[0]);});
});
test('every polygon contains its lines\' boxes',{skip:!have},()=>{
 let polys=0;
 for(const f of list){
  const e=run(f);if(!e.available)continue;
  for(const p of e.paragraphs)for(const area of p.polygons){
   polys++;
   const xs=area.points.map(q=>q[0]),ys=area.points.map(q=>q[1]),lines=new Set(area.lines);
   for(const b of e.boxes)if(lines.has(b.line)){assert.ok(b.rect[0]>=Math.min(...xs)-1e-6&&b.rect[2]<=Math.max(...xs)+1e-6&&b.rect[1]>=Math.min(...ys)-1e-6&&b.rect[3]<=Math.max(...ys)+1e-6,`${f} line ${b.line}`);}
  }
 }
 assert.ok(polys>600,String(polys));
});
test('all paragraph starts put each paragraph\'s first word on the origin',{skip:!have},()=>{
 let usable=0;
 for(const f of ['f20v','f21r','f33v','f75r','f103r']){
  const e=run(f,{align:'starts'});
  for(const p of e.paragraphs){
   if(!p.available)continue;usable++;
   const first=e.boxes.filter(b=>b.paragraph===p.key&&b.line===p.lines[0]).sort((a,b)=>a.rect[0]-b.rect[0]);
   assert.ok(first.some(b=>Math.abs(b.baseline)<1e-6),`${f} ${p.key}`);
  }
  assert.ok(e.boxes.every(b=>e.paragraphs.some(p=>p.available&&p.key===b.paragraph)),'only aligned paragraphs stay');
 }
 assert.ok(usable>=5);
});
test('a corner anchor lands the page\'s complete text on that corner, and a missing endpoint is not replaced',{skip:!have},()=>{
 const top=run('f112v',{anchor:'top-left'}),bottom=run('f112v',{anchor:'bottom-left'});
 assert.equal(top.available,true);assert.equal(bottom.available,true);
 const box=X.bounds([top]);near(box.x0,0,1e-6);near(box.y0,0,1e-6);
 const low=X.bounds([bottom]);near(low.x0,0,1e-6);near(low.y1,0,1e-6);
 const r=[...Array(pages.f112v.lines.length).keys()];assert.ok(r.length>0);
 for(const f of list){const e=run(f,{align:'starts',anchor:'bottom-left'});for(const p of e.paragraphs)if(p.available){const end=p.lines[p.lines.length-1];assert.equal(pages[f].lines[end][3],'horizontal',`${f} ${p.key}`);}}
});
test('the heatmap gives each page one vote, agreeing with a direct intersection check',{skip:!have},()=>{
 const g=X.groups(pages,list,'section').find(x=>x.name==='Bio'),entries=g.pages.map(f=>run(f)),occ=X.occupancy(entries,40);
 assert.equal(occ.denominator,g.pages.length);
 const seen=occ.cells.filter((c,i)=>i%37===0);assert.ok(seen.length>10);
 for(const c of seen){
  const pagesThere=entries.filter(e=>e.available&&e.boxes.some(b=>b.rect[0]<c.x+40&&b.rect[2]>c.x&&b.rect[1]<c.y+40&&b.rect[3]>c.y)).map(e=>e.folio);
  assert.deepEqual(c.folios.slice().sort(),pagesThere.sort(),`${c.x},${c.y}`);
  near(c.percent,100*pagesThere.length/g.pages.length);
 }
 const two=X.occupancy([{folio:'a',available:true,boxes:[{rect:[1,1,9,9]},{rect:[2,2,8,8]}]},{folio:'b',available:false,boxes:[{rect:[1,1,9,9]}]}],10);
 assert.equal(two.denominator,2);assert.deepEqual(two.unavailable,['b']);assert.equal(two.cells.length,1);assert.equal(two.cells[0].count,1);assert.equal(two.cells[0].percent,50);
 assert.throws(()=>X.occupancy([],0));
});
test('the heatmap\'s bands and ramps',()=>{
 assert.equal(X.band(.5),0);assert.equal(X.band(10),0);assert.equal(X.band(10.01),1);assert.equal(X.band(100),9);
 for(const k of Object.keys(X.HEATMAPS)){assert.equal(X.ramp(k,false).length,10);assert.deepEqual(X.ramp(k,true),X.HEATMAPS[k].colors.slice().reverse());}
});
test('colours are shared across a bifolium or group, and the data\'s totals hold',{skip:!have},()=>{
 const entries=['f1r','f1v','f8r'].map(f=>run(f));
 const byBif=X.colorIndex('bifolium',entries);assert.equal(byBif.get('f1r'),byBif.get('f8r'));
 assert.equal(new Set(X.colorIndex('page',entries).values()).size,3);
 let paragraphs=0,available=0,aligned=0,polys=0;
 for(const f of list){const e=run(f),s=run(f,{align:'starts'});paragraphs+=e.stats.paragraphs;if(e.available)available++;aligned+=s.paragraphs.filter(p=>p.available).length;polys+=s.paragraphs.reduce((n,p)=>n+p.polygons.length,0);}
 console.log(JSON.stringify({pages:list.length,available,paragraphs,aligned,polys}));
 assert.ok(available>=220&&paragraphs>700&&aligned>690);
});
