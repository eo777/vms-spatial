'use strict';
// The atlas renderer on the manuscript bundle: every token with a position is covered by exactly one group of
// rectangles, shared groups are drawn once, resolved words carry their native box, orders and groupings are complete.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const A=require('../atlas.js'),DATA=path.resolve(__dirname,'../data');
const gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,p))));
const have=fs.existsSync(path.join(DATA,'manuscript/words.json.gz'))&&fs.existsSync(path.join(DATA,'layout.json.gz'));
const data=have?gz('manuscript/words.json.gz'):null,layout=have?gz('layout.json.gz'):null;

test('rows cover every page once in every grouping and order',{skip:!have},()=>{
 const pages=new Set(data.lines.map(l=>l.page));
 for(const grouping of ['bifolia','leaves','pages'])for(const order of ['bifolia','folio','path1']){
  const rows=A.rows(data,layout,{grouping,order}),seen=rows.flatMap(r=>r.pages);
  assert.equal(seen.length,pages.size,grouping+' '+order);assert.deepEqual(new Set(seen),pages);
  assert.ok(rows.every(r=>r.N>0&&r.label&&r.sections.length));
 }
 assert.equal(A.rows(data,layout,{grouping:'bifolia'}).length,layout.nodes.length);assert.ok(layout.nodes.length>=50);   // 50 Path 1 bifolia, plus the zodiac bifolia when the extra pages are in
 assert.equal(A.rows(data,layout,{grouping:'bifolia',order:'bifolia'})[0].title,'A:1-8');
 const leaves=A.rows(data,layout,{grouping:'leaves',order:'folio'});
 assert.ok(leaves.length>100&&leaves[0].title==='f1');
});

test('every located token appears in exactly one rectangle group; shared boxes are drawn once',{skip:!have},()=>{
 const html=A.render(data,layout,{grouping:'bifolia'});
 const rects=[...html.matchAll(/<rect\b[^>]*data-token-indices="([^"]+)"[^>]*>/g)];
 assert.ok(rects.length>33000);
 const groups=new Set(rects.map(m=>m[1])),covered=new Set();
 for(const key of groups)for(const i of key.split(',').map(Number)){assert.ok(!covered.has(i),'token '+i+' in two groups');covered.add(i);}
 // a token is drawable when its group has a resolved box or at least one original rectangle with area (36 tokens sit in
 // zero-area source placeholders, which are omitted rather than widened)
 const drawable=data.spatialReview.tokens.filter(t=>{const g=t.group&&data.spatialReview.groups[t.group];return g&&g.positions?.length&&(g.resolution||g.parts.some(b=>b&&b[2]>b[0]&&b[3]>b[1]));}).length;
 assert.equal(covered.size,drawable);assert.ok(covered.size>=34904);   // 34,904 on the 207 study pages; more with the extra pages
 assert.ok([...groups].some(k=>k.includes(',')),'shared groups keep all their members');
 const resolved=rects.filter(m=>/data-resolved-token=/.test(m[0]));
 assert.ok(resolved.length>=400);
 for(const m of resolved){assert.match(m[0],/data-native-box="[\d.,-]+"/);assert.doesNotMatch(m[0],/data-xml-index=/);}
 const svgs=[...html.matchAll(/<svg role="group" aria-label="([^"]+) word diversity" viewBox="0 0 (\d+) (\d+)"/g)];
 const drawn=[...new Set(data.lines.map(l=>l.page))].filter(p=>!layout.pages[p].missing).length;
 assert.equal(svgs.length,drawn);   // every page with a coordinate frame; a page without one (f116v) is a placeholder
 assert.ok(html.includes('class="missing">f116v')||drawn===new Set(data.lines.map(l=>l.page)).size);
 if(layout.pages.fRos&&!layout.pages.fRos.missing){assert.ok(layout.pages.fRos.self_hosted);assert.ok(html.includes('aria-label="fRos word diversity"'));}
 for(const [,page,w,h] of svgs){assert.equal(Number(w),layout.pages[page].width);assert.equal(Number(h),layout.pages[page].height);}
});

test('row token ranges are contiguous runs of the bundle and add up to the row size',{skip:!have},()=>{
 const html=A.render(data,layout,{grouping:'leaves',order:'folio'});
 for(const m of html.matchAll(/data-ranges="([^"]*)"[^>]*>\s*<header>.*?<small>([\d,]+) words<\/small>/gs)){
  const ranges=m[1].split(',').map(r=>r.split('-').map(Number)),n=ranges.reduce((s,[a,b])=>s+b-a,0);
  assert.equal(n,Number(m[2].replace(/,/g,'')));
  for(const [a,b] of ranges)assert.ok(0<=a&&a<b&&b<=data.words.length);
 }
});

test('a bundle without a review draws one rectangle per boxed token',()=>{
 const d={words:['a','b','c','d'],lines:[{page:'p1',locus:'1',bifolium:'X',start:0,end:2},{page:'p1',locus:'2',bifolium:'X',start:2,end:4}],geometry:[[0,0,10,10],null,[0,20,10,30],[12,20,22,30]],components:{}};
 const lay={pages:{p1:{width:100,height:100,section_name:'Bio',group:'4a',node:'X',leaf:1,side:'r',quire:'A',quire_num:1,bifolium:'X'}},nodes:[{id:'X',group:'4a',N:4,pages:['p1'],label:'Bio / 4a',detail:'',sections:['Bio']}],orders:{bifolia:['X'],path1:['X']},leaves:[{leaf:1,panel:'',pages:['p1']}],scopes:[]};
 const html=A.render(d,lay,{});
 assert.equal([...html.matchAll(/<rect /g)].length,3);
 assert.ok(html.includes('data-token-indices="0"')&&html.includes('data-token-indices="3"')&&!html.includes('data-token-indices="1"'));
 assert.ok(html.includes('data-ranges="0-4"'));
});
