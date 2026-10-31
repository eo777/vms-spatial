/* The comparison metrics of vmsspatial.compare as pure functions: exact rectangle unions, EVA atom edit distances,
   the overlay scores (occupied-area Dice, direct-overlap and nearby EVA similarity), the segment correspondences,
   the position-constrained EVA similarity, the horizontal-occupancy Dice, the Jensen-Shannon distances of a line's
   unit-pair histograms, the joint value of bifolium slots and the combined ranking. It also reads the compact page
   records of viewer/data/compare/pages.json.gz (selectUnits) so a page can be selected, translated and scored in the
   browser exactly as in Python (viewer/test/compare_math.test.js checks the equality on saved pairs). No DOM. */
(function(root){
'use strict';
const INTRUSION=1,CLEAN=2,BOX_CENTRE=4,GROUPED=8;
const EDGE_SHARE=0.2,NEAR_W=0.5,NEAR_H=0.5,SPATIAL_GATE=0.2,BODY_HEIGHT_PX=30;
const FACES={inner:['Av','Br'],outer:['Bv','Ar'],both:['Av','Br','Bv','Ar']};
const COMPOSITES=['cph','cfh','ckh','cth','ch','sh'];
// ---- EVA atoms (vmsspatial.units.atom_strings / zattera)
function atoms(text){
  const word=text.replace(/ /g,''),out=[];let i=0;
  while(i<word.length){
    const c=word[i];
    if(c==='{'){const j=word.indexOf('}',i+1);if(j<0){out.push(c);i++;continue;}out.push(word.slice(i,j+1));i=j+1;continue;}
    if(c==='@'){const m=/^@\d+;/.exec(word.slice(i));if(m){out.push(m[0]);i+=m[0].length;continue;}}
    const comp=COMPOSITES.find(k=>word.startsWith(k,i));
    if(comp){out.push(comp);i+=comp.length;continue;}
    out.push(c);i++;
  }
  return out;
}
function zattera(word){
  const a=atoms(word),out=[];
  for(let i=0;i<a.length;i++){let s=a[i];if((s==='e'||s==='i')&&s.length===1)while(a[i+1]===a[i])s+=a[++i];out.push(s);}
  return out;
}
// ---- geometry
function intersection(a,b){const r=[Math.max(a[0],b[0]),Math.max(a[1],b[1]),Math.min(a[2],b[2]),Math.min(a[3],b[3])];return r[2]>r[0]&&r[3]>r[1]?r:null;}
const area=r=>r?(r[2]-r[0])*(r[3]-r[1]):0;
function unionArea(rects){
  const xs=[...new Set(rects.flatMap(r=>[r[0],r[2]]))].sort((a,b)=>a-b);
  let total=0;
  for(let k=1;k<xs.length;k++){
    const x=(xs[k-1]+xs[k])/2,spans=rects.filter(r=>r[0]<x&&r[2]>x).map(r=>[r[1],r[3]]).sort((a,b)=>a[0]-b[0]);
    let lo=null,hi=null,length=0;
    for(const [a,b] of spans){if(lo===null){lo=a;hi=b;}else if(a<=hi){hi=Math.max(hi,b);}else{length+=hi-lo;lo=a;hi=b;}}
    if(lo!==null)length+=hi-lo;
    total+=(xs[k]-xs[k-1])*length;
  }
  return total;
}
// ---- text
function edit(a,b){
  let prev=Array.from({length:b.length+1},(_,i)=>i);
  for(let i=0;i<a.length;i++){const row=[i+1];for(let j=0;j<b.length;j++)row.push(Math.min(row[j]+1,prev[j+1]+1,prev[j]+(a[i]===b[j]?0:1)));prev=row;}
  return prev[b.length];
}
const similarity=(a,b)=>1-edit(a,b)/Math.max(a.length,b.length,1);
// ---- the overlay scores on two unit lists in one frame (unit: {rect, atoms, line, anchor})
function measureUnits(A,B,W,H,sameRow=false){
  const empty={dice:null,local_segment_similarity:null,nearby_similarity:null,units_a:A.length,units_b:B.length};
  if(!A.length||!B.length)return empty;
  const inter=A.map(a=>B.map(b=>sameRow&&a.line!==b.line?null:intersection(a.rect,b.rect)));
  let shared,total;
  if(sameRow){shared=0;total=0;for(const line of new Set(A.concat(B).map(u=>u.line))){
    shared+=unionArea(inter.flatMap((row,i)=>A[i].line===line?row.filter(Boolean):[]));
    total+=unionArea(A.filter(u=>u.line===line).map(u=>u.rect))+unionArea(B.filter(u=>u.line===line).map(u=>u.rect));
  }}else{shared=unionArea(inter.flat().filter(Boolean));total=unionArea(A.map(u=>u.rect))+unionArea(B.map(u=>u.rect));}
  const adj=inter.map((row,i)=>row.map((r,j)=>!!r&&area(r)/Math.min(area(A[i].rect),area(B[j].rect))>=EDGE_SHARE));
  let weighted=0,weight=0;
  for(let i=0;i<A.length;i++){const js=B.map((_,j)=>j).filter(j=>adj[i][j]);if(!js.length)continue;const w=unionArea(js.map(j=>inter[i][j]));weighted+=w*similarity(A[i].atoms,js.flatMap(j=>B[j].atoms));weight+=w;}
  for(let j=0;j<B.length;j++){const ix=A.map((_,i)=>i).filter(i=>adj[i][j]);if(!ix.length)continue;const w=unionArea(ix.map(i=>inter[i][j]));weighted+=w*similarity(ix.flatMap(i=>A[i].atoms),B[j].atoms);weight+=w;}
  const bestA=A.map(()=>null),bestB=B.map(()=>null);
  for(let i=0;i<A.length;i++)for(let j=0;j<B.length;j++){
    if(sameRow&&A[i].line!==B[j].line)continue;
    const a=A[i].rect,b=B[j].rect;
    if(Math.max(0,a[0]-b[2],b[0]-a[2])<=NEAR_W*W&&Math.max(0,a[1]-b[3],b[1]-a[3])<=NEAR_H*H){const s=similarity(A[i].atoms,B[j].atoms);bestA[i]=Math.max(bestA[i]??0,s);bestB[j]=Math.max(bestB[j]??0,s);}
  }
  const near=bestA.concat(bestB).filter(v=>v!==null);
  return {...empty,dice:total?2*shared/total:null,local_segment_similarity:weight?weighted/weight:null,nearby_similarity:near.length?near.reduce((a,b)=>a+b,0)/near.length:null};
}
function measure(a,b,sameRow=false){
  if(a.frame!==b.frame||a.warp!==b.warp)throw new Error('the two selections are in different frames or warp states ('+a.frame+'/'+a.warp+' against '+b.frame+'/'+b.warp+')');
  if(!a.available||!b.available)return {dice:null,local_segment_similarity:null,nearby_similarity:null,units_a:0,units_b:0};
  return measureUnits(a.chosen,b.chosen,(a.W+b.W)/2,(a.H+b.H)/2,sameRow);
}
function record(A,B,ix,js){
  const aa=ix.map(i=>A[i]),bb=js.map(j=>B[j]),xa=aa.flatMap(u=>u.atoms),xb=bb.flatMap(u=>u.atoms);
  return {a:aa.map(u=>u.id),b:bb.map(u=>u.id),text_a:aa.map(u=>u.text).join(' | '),text_b:bb.map(u=>u.text).join(' | '),similarity:similarity(xa,xb),edits:edit(xa,xb),
    lines_a:[...new Set(aa.map(u=>u.line+1))].sort((x,y)=>x-y),lines_b:[...new Set(bb.map(u=>u.line+1))].sort((x,y)=>x-y),clean:aa.concat(bb).every(u=>u.clean),flags:[...new Set(aa.concat(bb).flatMap(u=>u.flags||[]))]};
}
function details(a,b,sameRow=false){
  const A=a.chosen,B=b.chosen,edges=A.map(()=>[]),reverse=B.map(()=>[]),direct=[],connected=[],nearby=[];
  for(let i=0;i<A.length;i++)for(let j=0;j<B.length;j++){if(sameRow&&A[i].line!==B[j].line)continue;const r=intersection(A[i].rect,B[j].rect);if(r&&area(r)/Math.min(area(A[i].rect),area(B[j].rect))>=EDGE_SHARE){edges[i].push(j);reverse[j].push(i);}}
  edges.forEach((js,i)=>{if(js.length)direct.push(record(A,B,[i],js));});reverse.forEach((ix,j)=>{if(ix.length)direct.push(record(A,B,ix,[j]));});
  const seenA=new Set(),seenB=new Set();
  for(let i=0;i<A.length;i++){
    if(seenA.has(i)||!edges[i].length)continue;
    const todo=[['a',i]],ix=[],js=[];
    while(todo.length){const [side,k]=todo.pop(),seen=side==='a'?seenA:seenB;if(seen.has(k))continue;seen.add(k);if(side==='a'){ix.push(k);edges[k].forEach(j=>todo.push(['b',j]));}else{js.push(k);reverse[k].forEach(j=>todo.push(['a',j]));}}
    connected.push(record(A,B,ix.sort((x,y)=>x-y),js.sort((x,y)=>x-y)));
  }
  const W=(a.W+b.W)/2,H=(a.H+b.H)/2;
  for(let i=0;i<A.length;i++){let best=null;for(let j=0;j<B.length;j++){if(sameRow&&A[i].line!==B[j].line)continue;const r=A[i].rect,s=B[j].rect;if(Math.max(0,r[0]-s[2],s[0]-r[2])>NEAR_W*W||Math.max(0,r[1]-s[3],s[1]-r[3])>NEAR_H*H)continue;const score=similarity(A[i].atoms,B[j].atoms);if(!best||score>best.score)best={j,score};}if(best)nearby.push(record(A,B,[i],[best.j]));}
  return {direct,connected,nearby};
}
function perLine(a,b){
  const n=Math.max(a.expected,b.expected),W=(a.W+b.W)/2,H=(a.H+b.H)/2,rows=[];
  for(let line=0;line<n;line++)rows.push({line:line+1,...measureUnits(a.chosen.filter(u=>u.line===line),b.chosen.filter(u=>u.line===line),W,H)});
  return rows;
}
// ---- the first-line scan metrics
function lineFeatures(text){
  const words=text.trim().split(/\s+/).filter(Boolean),aa=words.map(atoms),zz=words.map(zattera);
  const hist=(groups,weighted=false)=>{const h={};for(const seq of groups){const den=weighted?Math.max(1,seq.length-1):1;for(let i=1;i<seq.length;i++){const k=JSON.stringify([seq[i-1],seq[i]]);h[k]=(h[k]||0)+1/den;}}return h;};
  return {words,plain:aa.flat(),spaced:aa.flatMap((a,i)=>i?['<boundary>',...a]:a),toolkit:hist(zz,true),within:hist(zz),joined:hist([zz.flat()]),boundaries:hist([zz.flatMap((a,i)=>i?['<boundary>',...a]:a)])};
}
function jsDistance(a,b){
  const sa=Object.values(a).reduce((s,v)=>s+v,0),sb=Object.values(b).reduce((s,v)=>s+v,0);if(!sa||!sb)return null;
  let d=0;for(const k of new Set([...Object.keys(a),...Object.keys(b)])){const p=(a[k]||0)/sa,q=(b[k]||0)/sb,m=(p+q)/2;if(p)d+=p*Math.log2(p/m)/2;if(q)d+=q*Math.log2(q/m)/2;}
  return Math.sqrt(Math.max(0,d));
}
function xGate(a,b,threshold=SPATIAL_GATE){const n=Math.max(0,Math.min(a.rect[2],b.rect[2])-Math.max(a.rect[0],b.rect[0]));return n>0&&n/Math.min(a.rect[2]-a.rect[0],b.rect[2]-b.rect[0])>=threshold;}
function spatialSimilarity(A,B,threshold=SPATIAL_GATE){
  const a=A.flatMap((u,k)=>u.atoms.map(t=>({t,k}))),b=B.flatMap((u,k)=>u.atoms.map(t=>({t,k})));
  if(!a.length||!b.length)return {similarity:null,edits:null,atoms_a:a.length,atoms_b:b.length};
  const gate=A.map(u=>B.map(v=>xGate(u,v,threshold)));
  let prev=Array.from({length:b.length+1},(_,i)=>i);
  for(let i=1;i<=a.length;i++){const row=new Array(b.length+1);row[0]=i;for(let j=1;j<=b.length;j++){const sub=gate[a[i-1].k][b[j-1].k]?(a[i-1].t===b[j-1].t?0:1):2;row[j]=Math.min(row[j-1]+1,prev[j]+1,prev[j-1]+sub);}prev=row;}
  const edits=prev[b.length];
  return {similarity:Math.max(0,1-edits/Math.max(a.length,b.length)),edits,atoms_a:a.length,atoms_b:b.length};
}
function unionLength(intervals){let total=0,end=-Infinity;for(const [lo,hi] of intervals.slice().sort((x,y)=>x[0]-y[0]||x[1]-y[1])){total+=Math.max(0,hi-Math.max(lo,end));end=Math.max(end,hi);}return total;}
function xDice(A,B){
  const a=A.map(u=>[u.rect[0],u.rect[2]]),b=B.map(u=>[u.rect[0],u.rect[2]]);
  const inter=a.flatMap(x=>b.map(y=>[Math.max(x[0],y[0]),Math.min(x[1],y[1])]).filter(r=>r[1]>r[0]));
  const den=unionLength(a)+unionLength(b);return den?2*unionLength(inter)/den:null;
}
function dice2d(A,B){const den=unionArea(A.map(u=>u.rect))+unionArea(B.map(u=>u.rect));if(!den)return null;return 2*unionArea(A.flatMap(u=>B.map(v=>intersection(u.rect,v.rect))).filter(Boolean))/den;}
// ---- bifolia
function faceSlots(face,columns='both'){const slots=FACES[face];if(!slots)throw new Error('face must be inner, outer or both');return slots.filter(s=>columns==='both'||s[0]===columns);}
function joint(rows){
  const complete=rows.length>0&&rows.every(r=>r.a&&r.b&&r.a.available&&r.b.available&&r.a.complete&&r.b.complete),mean={},minimum={};
  for(const key of ['dice','local_segment_similarity','nearby_similarity']){
    const values=rows.map(r=>r.result?.[key]),valid=complete&&values.every(v=>typeof v==='number'&&Number.isFinite(v));
    mean[key]=valid?values.reduce((a,b)=>a+b,0)/values.length:null;minimum[key]=valid?Math.min(...values):null;
  }
  return {complete,mean,minimum,required_pairs:rows.length,available_pairs:rows.filter(r=>r.a&&r.b&&r.a.available&&r.b.available).length};
}
// ---- ranking (rows: {id, dice_current, js_joined, ...})
function ranks(rows,key,descending){
  const sorted=rows.slice().sort((a,b)=>(descending?b[key]-a[key]:a[key]-b[key])||(a.id<b.id?-1:a.id>b.id?1:0)),out=new Map();let rank=1,previous=null;
  sorted.forEach((r,i)=>{if(i&&Math.abs(r[key]-previous)>1e-12)rank=i+1;out.set(r.id,rank);previous=r[key];});return out;
}
function rankRows(rows,metric='both',js='js_joined'){
  const key=metric==='js'?js:metric,needed=metric==='both'?['dice_current',js]:[key];rows=rows.filter(r=>needed.every(k=>Number.isFinite(r[k])));
  const overlap=ranks(rows,'dice_current',true),jsr=ranks(rows,js,false),metricRanks=metric==='both'?null:ranks(rows,key,!key.startsWith('js_'));
  const out=rows.map(r=>({...r,overlap_rank:overlap.get(r.id),js_rank:jsr.get(r.id),metric_rank:metricRanks?.get(r.id)}));
  out.forEach(r=>{r.both_worst=Math.max(r.overlap_rank,r.js_rank);r.both_sum=r.overlap_rank+r.js_rank;});
  out.sort((a,b)=>metric==='both'?(a.both_worst-b.both_worst||a.both_sum-b.both_sum||(a.id<b.id?-1:1)):(a.metric_rank-b.metric_rank||(a.id<b.id?-1:1)));return out;
}
// ---- the compact page records of viewer/data/compare/pages.json.gz
function pageUnits(page,words){
  return page.units.map((u,id)=>{const [first,last,line,x0,y0,x1,y1,dy,bx,by,flags]=u,text=words.slice(first,last+1).join(' ');
    return {id,first,last,line,text,atoms:atoms(text),rect:[x0,y0,x1,y1],flat:[x0,y0-dy,x1,y1-dy],base:[bx,by],flat_base:[bx,by-dy],dy,
      intrusion:!!(flags&INTRUSION),clean:!!(flags&CLEAN),anchor_kind:(flags&BOX_CENTRE)?'box centre':'baseline',grouped:!!(flags&GROUPED),flags:[],token_count:last-first+1};});
}
function blockOf(page,key){const b=page.blocks.find(x=>x[0]===key)||page.blocks[0];return {key:b[0],lines:b[1]};}
/* selectUnits(page, words, {block, cutoff, coordinates, alignment, scale, extent}) -> the selection of vmsspatial.compare.select:
   page = a record of pages.json.gz, words = the atlas bundle's words. */
function selectUnits(page,words,options={}){
  let {block='opening',cutoff='all',coordinates='flat',alignment='starts',scale='pixels',extent=null}=options;
  if(extent==='whole'){block='page';cutoff='all';}else if(extent==='top')block='opening';
  const b=blockOf(page,block),order=new Map(b.lines.map((li,i)=>[li,i])),H=page.H||30,W=page.W||60,factor=scale==='body_height'?BODY_HEIGHT_PX/H:1;
  const rectOf=u=>coordinates==='recorded'?u.rect:u.flat,baseOf=u=>coordinates==='recorded'?u.base:u.flat_base;
  const source=page._units||(page._units=pageUnits(page,words)),us=source.filter(u=>order.has(u.line));
  const pageStart=page.blocks[0][1][0];
  const anchor=alignment==='page'?(source.find(u=>u.line===pageStart)||source[0]||null):(us.find(u=>u.line===b.lines[0])||null);
  // no box on the block's first line: nothing is scored (available stays false), but the block is still drawn and its
  // lines still read, from its first located box
  const fallback=anchor||!us.length?null:us.reduce((m,u)=>order.get(u.line)<order.get(m.line)?u:m);
  const origin=anchor?baseOf(anchor):fallback?baseOf(fallback):[0,0],take=cutoff==='all'?b.lines.length:Number(cutoff);
  const all=us.map(u=>({...u,line_abs:u.line,line:order.get(u.line),rect:rectOf(u).map((v,j)=>(v-origin[j%2])*factor),baseline:(baseOf(u)[1]-origin[1])*factor,anchor:u===anchor,selected:order.get(u.line)<take}));
  const chosen=all.filter(u=>u.selected),located=new Set(chosen.map(u=>u.line)),expected=cutoff==='all'?b.lines.length:Number(cutoff);
  return {page,block:b,all,chosen,line_info:b.lines.map((li,index)=>({index,line_abs:li,locus:page.lines[li][0],orientation:page.lines[li][3],category:page.lines[li][2],first:!!page.lines[li][1]})),
    W:W*factor,H:H*factor,origin,anchor_kind:anchor?anchor.anchor_kind:null,available:!!anchor,fallback_line:fallback?order.get(fallback.line):null,complete:located.size===expected&&b.lines.length>=expected,expected,located:located.size,total_lines:b.lines.length,
    nonhorizontal:[...new Set(chosen.map(u=>page.lines[u.line_abs][3]))].filter(k=>k!=='horizontal'),coordinates,alignment,scale,cutoff,frame:page.frame||'recorded',warp:coordinates==='flat'?'flat':'recorded'};
}
// ---- the drift indicator (vmsspatial.compare.page_drift): median signed baseline chord angle of the qualifying horizontal paragraph lines
const DRIFT_MIN_UNITS=4,DRIFT_MIN_SPAN_W=3;
const median=values=>{const a=values.slice().sort((x,y)=>x-y),n=a.length;return n?(a[Math.floor((n-1)/2)]+a[Math.floor(n/2)])/2:null;};
/* pageDrift(page, words, coordinates, quarantined) -> {angle, slope, n, lines: [{index, locus, angle, units, span, qualifies}], dropped, unavailable};
   quarantined = the page is in pages.json.gz's `quarantine` list (paragraph lines not all horizontal). */
function pageDrift(page,words,coordinates='recorded',quarantined=false){
  const source=page._units||(page._units=pageUnits(page,words)),baseOf=u=>coordinates==='recorded'?u.base:u.flat_base;
  const eligible=page.lines.map((l,index)=>({index,locus:l[0],category:l[2],orientation:l[3]})).filter(l=>l.category==='P'&&l.orientation==='horizontal'),ids=new Set(eligible.map(l=>l.index));
  const units=source.filter(u=>ids.has(u.line)),widths=units.map(u=>u.rect[2]-u.rect[0]).filter(w=>w>0),width=widths.length?median(widths):null;
  const lines=[],dropped={short:0,narrow:0,baseline:0};
  if(!quarantined)for(const line of eligible){
    const us=units.filter(u=>u.line===line.index).sort((a,b)=>baseOf(a)[0]-baseOf(b)[0]),anchored=us.filter(u=>u.anchor_kind!=='box centre');
    const rec={index:line.index,locus:line.locus,units:us.length,qualifies:false};
    if(us.length<DRIFT_MIN_UNITS)dropped.short++;
    const first=us[0],last=us[us.length-1];
    if(us.length>=2){const dx=baseOf(last)[0]-baseOf(first)[0];rec.span=dx;if(first.anchor_kind!=='box centre'&&last.anchor_kind!=='box centre'&&dx>0)rec.angle=Math.atan2(baseOf(last)[1]-baseOf(first)[1],dx)*180/Math.PI;}
    if(us.length>=DRIFT_MIN_UNITS){if(!(width&&(rec.span||0)>=DRIFT_MIN_SPAN_W*width))dropped.narrow++;else if(first.anchor_kind==='box centre'||last.anchor_kind==='box centre'||rec.angle===undefined)dropped.baseline++;else rec.qualifies=true;}
    if(rec.angle!==undefined||anchored.length>=2)lines.push(rec);
  }
  const qualifying=lines.filter(l=>l.qualifies).map(l=>l.angle),angle=qualifying.length?median(qualifying):null;
  return {folio:page.folio,coordinates,angle,slope:angle===null?null:Math.tan(angle*Math.PI/180),n:qualifying.length,lines,dropped,median_word_width:width,
    unavailable:quarantined?'quarantined page (paragraph lines not all horizontal)':qualifying.length?null:(!units.length?'no located rectangles':'no qualifying horizontal paragraph lines')};
}
function driftGuide(drift,gain=1,x0=0,x1=1000){if(!drift||drift.angle==null)return null;const s=drift.slope*gain;return [[x0,s*x0],[x1,s*x1]];}
/* splitLines(a, b, [lineA, lineB], scale, limit) -> display-only vertical translations (vmsspatial.compare.split_lines): the two lines pulled apart
   into a band (a above b), the context above and below moved by shared offsets; sizes, x positions and within-line slopes unchanged. */
function splitLines(a,b,indices,scale=1,limit='all',headingPx=25,gapPx=27,paddingPx=12){
  if(!indices||indices.length!==2||!(scale>0))return null;
  const sels=[a,b],shown=s=>s.all.filter(u=>limit==='all'||u.line<5),rows=sels.map((s,k)=>shown(s).filter(u=>u.line===indices[k]));
  if(rows.some(r=>!r.length))return null;
  const bounds=rows.map(r=>[Math.min(...r.map(u=>u.rect[1])),Math.max(...r.map(u=>u.rect[3]))]),top=Math.min(...bounds.map(x=>x[0])),bottom=Math.max(...bounds.map(x=>x[1]));
  const heading=headingPx/scale,gap=gapPx/scale,padding=paddingPx/scale;
  const height=(bounds[0][1]-bounds[0][0])+(bounds[1][1]-bounds[1][0])+heading+gap+padding,extra=Math.max(0,height-(bottom-top)),start=top-extra/2;
  const rowTops=[start+heading,start+heading+(bounds[0][1]-bounds[0][0])+gap],end=rowTops[1]+(bounds[1][1]-bounds[1][0])+padding;
  const above=sels.flatMap((s,k)=>shown(s).filter(u=>u.line<indices[k])),below=sels.flatMap((s,k)=>shown(s).filter(u=>u.line>indices[k]));
  const up=Math.min(-extra/2,above.length?start-padding-Math.max(...above.map(u=>u.rect[3])):0),down=Math.max(extra/2,below.length?end+padding-Math.min(...below.map(u=>u.rect[1])):0);
  const displayed=sels.map((s,k)=>{const all=s.all.map(u=>{const dy=u.line===indices[k]?rowTops[k]-bounds[k][0]:u.line<indices[k]?up:down;return {...u,rect:[u.rect[0],u.rect[1]+dy,u.rect[2],u.rect[3]+dy],baseline:u.baseline+dy};});
    const chosen=new Set(s.chosen.map(u=>u.id));return {...s,all,chosen:all.filter(u=>chosen.has(u.id)),frame:'display',display_of:s.frame};});
  const visible=displayed.flatMap(shown);
  return {frame:'display',warp:a.warp,selections:displayed,indices:[...indices],start,end,row_tops:rowTops,up,down,ymin:Math.min(start-padding,...visible.map(u=>u.rect[1]-padding)),ymax:Math.max(end+padding,...visible.map(u=>u.rect[3]+padding))};
}
const api={INTRUSION,CLEAN,BOX_CENTRE,GROUPED,EDGE_SHARE,NEAR_W,NEAR_H,SPATIAL_GATE,BODY_HEIGHT_PX,FACES,DRIFT_MIN_UNITS,DRIFT_MIN_SPAN_W,atoms,zattera,intersection,area,unionArea,edit,similarity,measureUnits,measure,details,perLine,lineFeatures,jsDistance,spatialSimilarity,xDice,dice2d,faceSlots,joint,ranks,rankRows,pageUnits,blockOf,selectUnits,pageDrift,driftGuide,splitLines,median};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VMS_COMPARE=api;
})(typeof window!=='undefined'?window:globalThis);
