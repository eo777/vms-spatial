/* The comparison page's state and list helpers as pure functions: the address hash (parse / serialise with the
   defaults left out), the Text control's resolution into blocks and a cutoff, the page and sheet lists of an order,
   stepping, the common frame of several selections, zoom views between 0.25x and 40x, the line rows of a selection
   and the nearest partner line, the segment partners of a clicked unit, the ranked match rows, the centred wheel
   layout, the live overlap colours and the export record. No DOM; viewer/test/compare_state.test.js runs them in
   node. The metrics come from viewer/js/compare_math.js (VMS_COMPARE in the browser). */
(function(root){
'use strict';
const M=(typeof module!=='undefined'&&module.exports)?require('./js/compare_math.js'):root.VMS_COMPARE;
const VIEWS=['overlay','side','composite','segments','matches','wheels'];
const CUTOFFS=['1','2','3','4','5','all'],TEXTS=['page','1','2','3','4','5','custom'],ORDERS=['bifolia','folio','path1'],SCOPES=['pages','bifolia'],FACES=['inner','outer','both'];
const ALIGNS=['starts','page'],COORDS=['flat','recorded'],SCALES=['pixels','body'],METRICS=['both','dice','js','spatial'],GAINS=[1,5,10],COLORS=['pages','js','sim','area'],WORD_DIRS=['ring','level'],BOXES=['fill','outline','hidden'],STEPS=['page','bifolio','paragraph'];
const SLOTS={inner:['Av','Br'],outer:['Bv','Ar'],both:['Av','Br','Bv','Ar']};
const MIN_ZOOM=0.25,MAX_ZOOM=40,MAX_PAGES=12;
const DEFAULTS={a:'f20v',b:'f21r',view:'overlay',text:'page',cutoff:'all',order:'bifolia',scope:'pages',face:'inner',align:'starts',coords:'flat',scale:'pixels',
  blocka:'opening',blockb:'opening',metric:'both',gain:1,color:'pages',boxes:'fill',step:'page',words:false,wdir:'ring',drift:false,expand:false,rings:true,labels:false,pages:[],hide:[],lines:[],max:null,zoom:null,seg:null};
const pick=(value,allowed,fallback)=>allowed.includes(value)?value:fallback;
const folio=v=>typeof v==='string'&&/^[A-Za-z0-9:_.-]{1,24}$/.test(v)?v:null;
const BLOCK=/^(opening|page|p\d+|l\d+)$/;
/* lineAt(lines, panel) -> the pair open in that panel, or null. lines holds one [a, b, panel] per panel, the latest last */
const lineAt=(lines,panel)=>lines.find(l=>l[2]===panel)||null;
/* setLine(lines, panel, pair) -> lines with that panel's pair replaced, or closed when pair is null */
const setLine=(lines,panel,pair)=>[...lines.filter(l=>l[2]!==panel),...(pair?[[pair[0],pair[1],panel]]:[])];
// ---- the address
function parse(h={}){
  const s={...DEFAULTS,pages:[],hide:[]};
  s.a=folio(h.a)||DEFAULTS.a;s.b=folio(h.b)||DEFAULTS.b;
  s.view=pick(h.view,VIEWS,DEFAULTS.view);s.order=pick(h.order,ORDERS,DEFAULTS.order);
  s.scope=pick(h.scope,SCOPES,DEFAULTS.scope);s.face=pick(h.face,FACES,DEFAULTS.face);s.align=pick(h.align,ALIGNS,DEFAULTS.align);
  s.wdir=pick(h.wdir,WORD_DIRS,DEFAULTS.wdir);s.boxes=pick(h.boxes,BOXES,DEFAULTS.boxes);s.step=pick(h.step,STEPS,DEFAULTS.step);s.coords=pick(h.coords,COORDS,DEFAULTS.coords);s.scale=pick(h.scale,SCALES,DEFAULTS.scale);s.metric=pick(h.metric,METRICS,DEFAULTS.metric);s.color=pick(h.color,COLORS,DEFAULTS.color);
  s.blocka=BLOCK.test(h.blocka||'')?h.blocka:DEFAULTS.blocka;s.blockb=BLOCK.test(h.blockb||'')?h.blockb:DEFAULTS.blockb;
  s.cutoff=pick(String(h.cutoff??''),CUTOFFS,DEFAULTS.cutoff);
  // Text: explicit, or read from an older address (cutoff=N on the opening blocks = Top N; any other block or cutoff = custom)
  s.text=pick(h.text,TEXTS,null);
  if(s.text===null){const custom=h.blocka!=null||h.blockb!=null;s.text=!custom&&CUTOFFS.includes(String(h.cutoff))&&h.cutoff!=='all'?String(h.cutoff):(custom||h.cutoff!=null)?'custom':'page';}
  s.gain=GAINS.includes(Number(h.gain))?Number(h.gain):DEFAULTS.gain;
  s.words=h.words==='1';s.drift=h.drift==='1';s.expand=h.expand==='1';s.labels=h.labels==='1';s.rings=h.rings!=='0';
  s.pages=typeof h.pages==='string'?[...new Set(h.pages.split(',').map(folio).filter(Boolean))].slice(0,MAX_PAGES):[];
  s.hide=typeof h.hide==='string'?[...new Set(h.hide.split(',').filter(x=>x==='a'||x==='b'||folio(x)))]:[];
  if(typeof h.lines==='string'){const ms=h.lines.split(';').map(x=>/^(\d+),(\d+)(?:,(\d+))?$/.exec(x));s.lines=ms.every(Boolean)?ms.reduce((all,m)=>setLine(all,Number(m[3]||0),[Number(m[1]),Number(m[2])]),[]):[];}
  s.max=/^\d+$/.test(h.max||'')?Number(h.max):null;
  if(typeof h.zoom==='string'){const v=h.zoom.split(',').map(Number);s.zoom=v.length===4&&v.every(Number.isFinite)&&v[2]>0&&v[3]>0?{x:v[0],y:v[1],w:v[2],h:v[3]}:null;}
  if(typeof h.seg==='string'){const m=/^([ab]):(\d+)$/.exec(h.seg);s.seg=m?{side:m[1],id:Number(m[2])}:null;}
  return s;
}
function serialize(s){
  const o={a:s.a,b:s.b};
  for(const k of ['view','text','order','scope','face','align','coords','scale','metric','color','wdir','boxes','step'])if(s[k]!==DEFAULTS[k])o[k]=s[k];
  if(s.text==='custom'){for(const k of ['blocka','blockb','cutoff'])if(s[k]!==DEFAULTS[k])o[k]=s[k];}
  if(s.gain!==DEFAULTS.gain)o.gain=String(s.gain);
  if(s.words)o.words='1';if(s.drift)o.drift='1';if(s.expand)o.expand='1';if(s.labels)o.labels='1';if(!s.rings)o.rings='0';
  if(s.pages&&s.pages.length)o.pages=s.pages.join(',');
  if(s.hide&&s.hide.length)o.hide=s.hide.join(',');
  if(s.lines&&s.lines.length)o.lines=s.lines.map(l=>(l[2]?l:l.slice(0,2)).join(',')).join(';');
  if(s.max!=null)o.max=String(s.max);
  if(s.zoom)o.zoom=[s.zoom.x,s.zoom.y,s.zoom.w,s.zoom.h].map(n=>Math.round(n*100)/100).join(',');
  if(s.seg)o.seg=s.seg.side+':'+s.seg.id;
  return o;
}
/* resolveText(state) -> {blocka, blockb, cutoff}: Whole page = both whole pages, every line scored; Top N = both opening
   blocks, N lines scored; Custom = the blocks and the line cutoff chosen in Settings */
function resolveText(s){
  if(s.text==='page')return {blocka:'page',blockb:'page',cutoff:'all'};
  if(s.text==='custom')return {blocka:s.blocka,blockb:s.blockb,cutoff:s.cutoff};
  return {blocka:'opening',blockb:'opening',cutoff:s.text};
}
/* setText(state, text) -> a new state: a preset resets the blocks and the cutoff to its values; Custom keeps them */
function setText(s,text){const t=pick(text,TEXTS,'page'),r=resolveText({...s,text:t});return t==='custom'?{...s,text:t}:{...s,text:t,blocka:r.blocka,blockb:r.blockb,cutoff:r.cutoff};}
/* customize(state, {blocka?, blockb?, cutoff?}) -> a new state in Custom with that override applied */
function customize(s,change){const r=resolveText(s);return {...s,text:'custom',blocka:change.blocka??r.blocka,blockb:change.blockb??r.blockb,cutoff:change.cutoff??r.cutoff};}
// ---- hidden pages: 'a' / 'b' in the two-page scopes, folios in the composite and wheel views
const hideKey=(s,tag)=>tag==='A'?'a':tag==='B'?'b':tag;
const isHidden=(s,key)=>s.hide.includes(key);
function toggleHidden(s,key){return {...s,hide:s.hide.includes(key)?s.hide.filter(k=>k!==key):[...s.hide,key]};}
// ---- lists
/* pageList(orders, order, pages) -> the folios of an order that have a comparison record, in that order */
function pageList(orders,order,pages){const o=orders[order]||orders.bifolia;return (o?o.pages:Object.keys(pages)).filter(f=>pages[f]);}
/* sheetList(pages, list) -> [{id, slots: {Ar: [folios], Av, Br, Bv}, first}] ordered by the first page of the sheet in `list` */
function sheetList(pages,list){
  const pos=new Map(list.map((f,i)=>[f,i])),sheets=new Map();
  for(const f of list){const p=pages[f];if(!p||!p.node||!p.slot)continue;
    if(!sheets.has(p.node))sheets.set(p.node,{id:p.node,slots:{Ar:[],Av:[],Br:[],Bv:[]},first:pos.get(f)});
    sheets.get(p.node).slots[p.slot].push(f);}
  return [...sheets.values()].sort((x,y)=>x.first-y.first);
}
const step=(list,current,delta)=>{if(!list.length)return current;const i=list.indexOf(current),n=list.length;return list[((i<0?0:i+delta)%n+n)%n];};
/* stepSheet(sheets, pages, folio, delta) -> the page in the same slot of the sheet delta sheets along, or that sheet's
   first page when it has no such slot, wrapping at the ends */
function stepSheet(sheets,pages,folio,delta){
  if(!sheets.length)return folio;
  const p=pages[folio],i=sheets.findIndex(s=>p&&s.id===p.node),n=sheets.length,next=sheets[((i<0?0:i+delta)%n+n)%n];
  return (p&&next.slots[p.slot]&&next.slots[p.slot][0])||Object.values(next.slots).flat()[0]||folio;
}
/* paragraphKeys(page) -> its canonical paragraphs in order: p1, p2, ... */
const paragraphKeys=page=>page&&page.blocks?page.blocks.map(b=>b[0]).filter(k=>/^p\d+$/.test(k)):[];
/* stepParagraph(pages, list, folio, block, delta) -> {folio, block}: the next paragraph on the page, then the first
   paragraph of the next page that has any (going back, the last), wrapping at the ends. From a block that is not a
   paragraph, such as a whole page, it enters the page: its first paragraph going forward, its last going back. */
function stepParagraph(pages,list,folio,block,delta){
  const keys=paragraphKeys(pages[folio]),at=keys.indexOf(block);
  if(at<0&&keys.length)return {folio,block:delta>0?keys[0]:keys[keys.length-1]};
  if(at>=0&&at+delta>=0&&at+delta<keys.length)return {folio,block:keys[at+delta]};
  const n=list.length,i=list.indexOf(folio);
  for(let k=1;k<=n;k++){const f=list[((i+delta*k)%n+n)%n],ks=paragraphKeys(pages[f]);if(ks.length)return {folio:f,block:delta>0?ks[0]:ks[ks.length-1]};}
  return {folio,block};
}
/* stepPair(list, a, b, delta) -> [a, b] both moved along the list: the gap between them holds, wrapping at the ends like step */
const stepPair=(list,a,b,delta)=>[step(list,a,delta),step(list,b,delta)];
/* slotPages(sheet, face) -> [{slot, folio, panels}] : the first panel of every slot of the face (a foldout slot lists its other panels) */
function slotPages(sheet,face){return SLOTS[face].map(slot=>{const fs=sheet?sheet.slots[slot]:[];return {slot,folio:fs[0]||null,panels:fs.length};});}
/* wheelPages(wheels, pages, list, section?) -> the folios with a fitted wheel, in list order, optionally of one section */
function wheelPages(wheels,pages,list,section=null){return list.filter(f=>wheels.pages[f]&&wheels.pages[f].wheels.length&&(!section||(pages[f]&&pages[f].section===section)));}
// ---- geometry of a drawing
const visible=(sel,cutoff)=>cutoff==='all'?sel.all:sel.all.filter(u=>u.line<5);
/* frame(selections, cutoff, margin) -> {x, y, w, h} enclosing every visible unit and the origin, with a margin */
function frame(selections,cutoff,margin=0.06){
  let x0=0,y0=0,x1=0,y1=0,any=false;
  for(const s of selections)for(const u of visible(s,cutoff)){const r=u.rect;if(!any){x0=Math.min(0,r[0]);y0=Math.min(0,r[1]);x1=Math.max(0,r[2]);y1=Math.max(0,r[3]);any=true;}else{x0=Math.min(x0,r[0]);y0=Math.min(y0,r[1]);x1=Math.max(x1,r[2]);y1=Math.max(y1,r[3]);}}
  if(!any)return {x:-50,y:-50,w:100,h:100};
  const w=Math.max(1,x1-x0),h=Math.max(1,y1-y0),m=Math.max(w,h)*margin+12;
  return {x:x0-m,y:y0-m,w:w+2*m,h:h+2*m};
}
/* withGutter(F, selections, cutoff, widthPx, gutterPx) -> the frame widened on the left, so that at fit zoom in a panel
   widthPx wide the first gutterPx hold the line labels and no box */
function withGutter(F,selections,cutoff,widthPx,gutterPx){
  const xs=selections.flatMap(s=>visible(s,cutoff).map(u=>u.rect[0]));if(!xs.length||widthPx<=gutterPx)return F;
  const m=Math.min(...xs)-F.x,e=(gutterPx*F.w-m*widthPx)/(widthPx-gutterPx);
  return e>0?{x:F.x-e,y:F.y,w:F.w+e,h:F.h}:F;
}
/* zoom views: {x, y, w, h} in the frame's units; the scale is full.w / view.w, kept between MIN_ZOOM and MAX_ZOOM;
   a magnified view stays inside the full frame, a reduced view keeps the whole frame inside itself */
function clampView(v,full){
  const scale=Math.min(MAX_ZOOM,Math.max(MIN_ZOOM,full.w/v.w)),w=full.w/scale,h=w*full.h/full.w;
  const range=(a,fa,wa)=>wa<=fa?[a,a+fa-wa]:[a+fa-wa,a];
  const [x0,x1]=range(full.x,full.w,w),[y0,y1]=range(full.y,full.h,h);
  return {x:Math.min(Math.max(v.x,x0),x1),y:Math.min(Math.max(v.y,y0),y1),w,h};
}
function zoomAt(view,full,factor,point){const w=view.w/factor,h=view.h/factor,fx=(point.x-view.x)/view.w,fy=(point.y-view.y)/view.h;return clampView({x:point.x-fx*w,y:point.y-fy*h,w,h},full);}
function pan(view,full,dxPx,dyPx,pxPerUnit){const k=Math.max(pxPerUnit,1e-9);return clampView({x:view.x-dxPx/k,y:view.y-dyPx/k,w:view.w,h:view.h},full);}
const zoomScale=(view,full)=>full.w/view.w;
const isFit=(view,full,eps=1e-6)=>!view||(Math.abs(view.x-full.x)<eps&&Math.abs(view.y-full.y)<eps&&Math.abs(view.w-full.w)<eps&&Math.abs(view.h-full.h)<eps);
/* lineRows(sel, cutoff) -> [{index, units, baseline (median), x0, x1, text, chosen}] per displayed line of a selection */
function lineRows(sel,cutoff){
  const by=new Map();
  for(const u of visible(sel,cutoff)){if(!by.has(u.line))by.set(u.line,[]);by.get(u.line).push(u);}
  return [...by.entries()].sort((p,q)=>p[0]-q[0]).map(([index,units])=>{
    const ys=units.map(u=>u.baseline).sort((p,q)=>p-q),n=ys.length;
    return {index,units,baseline:(ys[Math.floor((n-1)/2)]+ys[Math.floor(n/2)])/2,x0:Math.min(...units.map(u=>u.rect[0])),x1:Math.max(...units.map(u=>u.rect[2])),text:units.map(u=>u.text).join(' '),chosen:units.some(u=>u.selected)};});
}
/* nearestLine(rows, y) -> the row whose median baseline is nearest to y (null when there is none) */
/* paragraphSpans(sel, cutoff) -> the canonical paragraphs among a selection's visible lines, for the margin:
   [{n, rows, total, first, last, y0, y1}]. n is the paragraph's number on the page, rows and total its visible and
   all lines, first and last its line labels' numbers, y0 and y1 the baselines of its first and last visible lines.
   Labels and ring text are in no paragraph and give no span. */
function paragraphSpans(sel,cutoff){
  const blocks=sel.page&&sel.page.blocks;if(!blocks)return [];
  const rows=lineRows(sel,cutoff),out=[];
  for(const [key,lines] of blocks){
    const m=/^p(\d+)$/.exec(key);if(!m)continue;
    const set=new Set(lines),inside=rows.filter(r=>r.units.some(u=>set.has(u.line_abs)));if(!inside.length)continue;
    const ys=inside.map(r=>r.baseline);
    out.push({n:Number(m[1]),rows:inside.length,total:lines.length,first:inside[0].index+1,last:inside[inside.length-1].index+1,y0:Math.min(...ys),y1:Math.max(...ys)});
  }
  return out;
}
function nearestLine(rows,y){let best=null;for(const r of rows){const d=Math.abs(r.baseline-y);if(!best||d<best.d)best={d,row:r};}return best?best.row:null;}
/* linePairs(rowsA, rowsB) -> every line of both pages once, in reading order: [rowA, rowB] when each is the other's nearest
   by baseline, [row, null] or [null, row] for a line with no such partner */
function linePairs(ra,rb){
  const near=new Map([...ra.map(r=>[r,nearestLine(rb,r.baseline)]),...rb.map(r=>[r,nearestLine(ra,r.baseline)])]),mutual=r=>{const n=near.get(r);return n&&near.get(n)===r?n:null;};
  return [...ra.map(r=>[r,mutual(r)]),...rb.filter(r=>!mutual(r)).map(r=>[null,r])].sort((x,y)=>(x[0]||x[1]).baseline-(y[0]||y[1]).baseline);
}
/* expandLines(a, b, cutoff, scale, hide) -> display-only vertical translations that open every line at once, like
   M.splitLines for one: each band holds a horizontal line and its partner, a above b, and the other text (rings, rays) stays
   together below the bands, in its own shape. Sizes, x positions and within-line slopes are unchanged. hide leaves a side
   out of the layout. Returns {frame, warp, selections, bands: [[y0, y1]], ymin, ymax}, or null when no line is shown. */
function expandLines(a,b,cutoff='all',scale=1,hide=[false,false],gapPx=3,paddingPx=7){
  const sels=[a,b],rows=sels.map((s,k)=>!s||hide[k]?[]:lineRows(s,cutoff).map(r=>({...r,top:Math.min(...r.units.map(u=>u.rect[1])),bottom:Math.max(...r.units.map(u=>u.rect[3]))})));
  const shownRows=rows.flat();if(!shownRows.length)return null;
  const level=(k,r)=>sels[k].line_info[r.index].orientation==='horizontal',gap=gapPx/scale,padding=paddingPx/scale,shift=[new Map(),new Map()],bands=[];
  const ymin=Math.min(...shownRows.map(r=>r.top))-padding;let y=ymin;
  for(const pair of linePairs(rows[0].filter(r=>level(0,r)),rows[1].filter(r=>level(1,r)))){
    const start=y;y+=padding;
    pair.forEach((r,k)=>{if(r){shift[k].set(r.index,y-r.top);y+=r.bottom-r.top+gap;}});
    y+=padding-gap;bands.push([start,y]);
  }
  const rest=rows.map((r,k)=>r.filter(x=>!level(k,x)));
  if(rest.flat().length){const top=Math.min(...rest.flat().map(r=>r.top));y+=padding;rest.forEach((r,k)=>r.forEach(x=>shift[k].set(x.index,y-top)));y+=Math.max(...rest.flat().map(r=>r.bottom))-top+padding;}
  const selections=sels.map((s,k)=>{if(!s)return null;
    const all=s.all.map(u=>{const dy=shift[k].get(u.line)||0;return {...u,rect:[u.rect[0],u.rect[1]+dy,u.rect[2],u.rect[3]+dy],baseline:u.baseline+dy};}),chosen=new Set(s.chosen.map(u=>u.id));
    return {...s,all,chosen:all.filter(u=>chosen.has(u.id)),frame:'display',display_of:s.frame};});
  return {frame:'display',warp:(a||b).warp,selections,bands,ymin,ymax:y};
}
/* carriedLines(rowsA, rowsB, side, line) -> [a, b]: the pair to read after a page move. Page `side` (0 A, 1 B) keeps the
   line's number, or the nearest number it has; the other page takes the partner a click would give. null when a page has no lines */
function carriedLines(rowsA,rowsB,side,line){
  const own=side?rowsB:rowsA,other=side?rowsA:rowsB;if(!own.length||!other.length)return null;
  const row=own.reduce((best,r)=>Math.abs(r.index-line)<Math.abs(best.index-line)?r:best),partner=nearestLine(other,row.baseline);
  return side?[partner.index,row.index]:[row.index,partner.index];
}
// ---- segments
/* partners(details, side, id) -> {kind: 'direct'|'nearby', a: [ids], b: [ids], record} for a clicked unit, or null */
function partners(det,side,id){
  if(!det)return null;
  const own=side==='a'?'a':'b',direct=det.direct.find(r=>r[own].length===1&&r[own][0]===id);
  if(direct)return {kind:'direct',a:direct.a,b:direct.b,record:direct};
  const near=side==='a'?det.nearby.find(r=>r.a[0]===id):det.nearby.find(r=>r.b.includes(id));
  return near?{kind:'nearby',a:near.a,b:near.b,record:near}:null;
}
// ---- live overlap colours: every scored box of one page against the boxes of the other page that intersect it
/* overlapValues(a, b) -> {a: Map(id -> v), b: Map(id -> v)}; v = null when nothing of the other page touches the box, else
   {js: JS distance between the box's glyph-pair histogram and that of the touching words joined, sim: best single-partner
   EVA similarity, area: share of the box's area covered by the other page's boxes, partners: [ids], text} */
function overlapValues(a,b){
  const A=a.chosen,B=b.chosen;
  const side=(X,Y)=>{const out=new Map();
    for(const u of X){const parts=[],inter=[];
      for(const v of Y){const r=M.intersection(u.rect,v.rect);if(r){parts.push(v);inter.push(r);}}
      if(!parts.length){out.set(u.id,null);continue;}
      const area=Math.min(1,M.unionArea(inter)/Math.max(1e-9,M.area(u.rect)));
      const js=M.jsDistance(M.lineFeatures(u.text).joined,M.lineFeatures(parts.map(v=>v.text).join(' ')).joined);
      let sim=null;for(const v of parts){const s=M.similarity(u.atoms,v.atoms);if(sim===null||s>sim)sim=s;}
      out.set(u.id,{js,sim,area,partners:parts.map(v=>v.id),text:parts.map(v=>v.text).join(' | ')});}
    return out;};
  return {a:side(A,B),b:side(B,A)};
}
/* colorDomain(values) -> [lo, hi]: the 5th and 95th percentiles of the finite values (the atlas's convention for its
   component colours), so that the palette spans the boxes in view; [0, 1] with fewer than five values or a flat range */
function colorDomain(values){
  const v=values.filter(x=>typeof x==='number'&&Number.isFinite(x)).sort((p,q)=>p-q);if(v.length<5)return [0,1];
  const q=t=>v[Math.min(v.length-1,Math.max(0,Math.round(t*(v.length-1))))],lo=q(0.05),hi=q(0.95);return hi>lo?[lo,hi]:[0,1];
}
/* colorIndex(value, mode, domain) -> 0..500 into the 501-colour diversity palette (warm = low, teal = high) over the domain;
   JS is reversed so that teal always means "more alike / more shared"; null for a missing value */
function colorIndex(value,mode,domain=[0,1]){
  if(value==null||!Number.isFinite(value))return null;
  let t=Math.min(1,Math.max(0,(value-domain[0])/Math.max(1e-12,domain[1]-domain[0])));if(mode==='js')t=1-t;return Math.round(t*500);
}
const COLOR_LABELS={js:'Overlap JS',sim:'Overlap similarity',area:'Shared area'};
// ---- the ranked matches
const VALUES=['dice','js','spatial','x_dice','dice_recorded','edit_all','js_word'];
function valueRow(values){const o={};VALUES.forEach((k,i)=>{o[k]=values[i];});return o;}
/* matchRows(rankings, state) -> [{a, b, position, overlap_rank, js_rank, weakest, dice, js, spatial, ...}] sorted by the chosen metric */
function matchRows(rankings,s){
  let rows;
  if(s.scope==='bifolia'){const face=rankings.bifolia&&rankings.bifolia[s.face];rows=face?face.top.map(r=>({a:r[0],b:r[1],position:r[2],overlap_rank:r[3],js_rank:r[4],weakest:r[5],...valueRow(r.slice(6))})):[];}
  else rows=(rankings.pages&&rankings.pages[s.a]||[]).map(r=>({a:s.a,b:r[0],position:r[1],overlap_rank:r[2],js_rank:r[3],...valueRow(r.slice(4))}));
  const key={dice:['dice',-1],js:['js',1],spatial:['spatial',-1]}[s.metric];
  if(key)rows=rows.filter(r=>Number.isFinite(r[key[0]])).sort((p,q)=>key[1]*(p[key[0]]-q[key[0]])||p.position-q.position);
  else rows=rows.slice().sort((p,q)=>p.position-q.position);
  return rows;
}
const matchIndex=(rows,s)=>rows.findIndex(r=>s.scope==='bifolia'?(r.a===s.a&&r.b===s.b)||(r.a===s.b&&r.b===s.a):r.b===s.b);
// ---- wheels
/* wheelLayout(folio, record, units) -> {wheels: [{id, folio, rings: [{cx, cy, r, locus, n, arc, residual}], boxes: [{id, first, rect, text}], labels: [...]}], radius}
   every wheel translated so that its centre is the origin: a display transform, nothing else changes */
function wheelLayout(folio,record,units){
  if(!record||!record.wheels)return {wheels:[],radius:0};
  const wheels=record.wheels.map(w=>{const [cx,cy]=w.centre,move=u=>({id:u.id,first:u.first,text:u.text,line:u.line,rect:[u.rect[0]-cx,u.rect[1]-cy,u.rect[2]-cx,u.rect[3]-cy]});
    return {id:w.id,folio,radius:w.radius,spread:w.centre_spread,centre:w.centre,rings:w.rings.map(r=>({cx:r.centre[0]-cx,cy:r.centre[1]-cy,r:r.radius,locus:r.locus,line:r.line,n:r.n,arc:r.arc_deg,residual:r.residual,units:r.units})),
      boxes:w.rings.flatMap(r=>r.units).map(i=>units[i]).filter(Boolean).map(move),labels:(w.labels||[]).map(i=>units[i]).filter(Boolean).map(move)};});
  const radius=Math.max(0,...wheels.flatMap(w=>[w.radius,...w.boxes.concat(w.labels).flatMap(b=>[Math.hypot(b.rect[0],b.rect[1]),Math.hypot(b.rect[2],b.rect[3])])]));
  return {wheels,radius};
}
// ---- export
function exportRecord(s,meta,a,b,scores,det,perLine,drift){
  const r=resolveText(s);
  const geometry=sel=>sel?{folio:sel.folio||null,block:sel.block.key,frame:sel.frame,warp:sel.warp,origin:sel.origin,anchor_kind:sel.anchor_kind,complete:sel.complete,located:sel.located,expected:sel.expected,
    units:sel.chosen.map(u=>({id:u.id,text:u.text,line:u.line+1,rect:u.rect.map(v=>Math.round(v*100)/100),baseline:Math.round(u.baseline*100)/100,anchor:u.anchor}))}:null;
  return {tool:'vms-spatial compare page',data_version:meta.version,baseline:meta.baseline,policy:meta.policy,settings:{a:s.a,b:s.b,view:s.view,text:s.text,cutoff:r.cutoff,alignment:s.align,coordinates:s.coords,scale:s.scale==='body'?'body_height':'pixels',block_a:r.blocka,block_b:r.blockb,scope:s.scope,face:s.face},
    scores:scores||null,per_line:perLine||null,segments:det?det.connected:null,geometry:{a:geometry(a),b:geometry(b)},drift:drift||null,
    note:'Translation-only overlay scores describe resemblance, not copying (docs/COMPARE.md).'};
}
const api={VIEWS,CUTOFFS,TEXTS,ORDERS,SCOPES,FACES,ALIGNS,COORDS,SCALES,METRICS,GAINS,COLORS,COLOR_LABELS,WORD_DIRS,BOXES,STEPS,SLOTS,DEFAULTS,MIN_ZOOM,MAX_ZOOM,MAX_PAGES,parse,serialize,resolveText,setText,customize,hideKey,isHidden,toggleHidden,
  pageList,sheetList,step,stepPair,stepSheet,paragraphKeys,stepParagraph,slotPages,wheelPages,visible,frame,withGutter,clampView,zoomAt,pan,zoomScale,isFit,lineRows,paragraphSpans,nearestLine,linePairs,expandLines,carriedLines,lineAt,setLine,partners,overlapValues,colorDomain,colorIndex,matchRows,matchIndex,wheelLayout,exportRecord};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.COMPARE_STATE=api;
})(typeof window!=='undefined'?window:globalThis);
