/* What the pages of a section share, on the toolkit's compact pages (compare/pages.json.gz): for each page its word boxes,
   paragraph polygons, paragraph starts and ends and annotated breaks, moved by translation only; for a group the share of its
   pages with a box in each grid cell. Nothing is fitted, imputed or resampled. Node tests: viewer/test/section_math.test.js. */
(function(root){
'use strict';
const M=(typeof module!=='undefined'&&module.exports)?require('./compare_math.js'):root.VMS_COMPARE;
const GOLF_ORDER=['1a','1b','1.5a','2a','5a','6','3b','3a','3c','4c','4a','—'];
const BY=['section','golf'],ALIGNS=['page','starts'],ANCHORS=['edge','opening','top-left','bottom-left'],COORDS=['flat','recorded'],SCALES=['pixels','body_height'];
const COLORS=['page','bifolium','group','section'],CELLS=['10','20','40','80'],LAYERS=['heatmap','polygons','boxes','breaks','starts','ends'];
const OPACITY=[['heatmap','Heatmap'],['fill','Paragraph fill'],['outline','Paragraph outlines'],['boxes','Word boxes'],['breaks','Breaks'],['starts','Paragraph starts'],['ends','Paragraph ends']];
const OPACITY_DEFAULTS={heatmap:100,fill:0,outline:50,boxes:15,breaks:70,starts:70,ends:70};
const HEATMAPS={
 blues:{label:'Blues',colors:['#eff3ff','#dce8f5','#c6dbef','#aacde5','#85b7d9','#60a1cf','#3f8bc2','#2171b5','#08519c','#08306b']},
 gray:{label:'Gray, for overlays',colors:['#f8f8f8','#efefef','#e6e6e6','#dddddd','#d4d4d4','#cacaca','#c0c0c0','#b6b6b6','#acacac','#a2a2a2']},
 amber:{label:'Amber',colors:['#fffaf0','#fff1d6','#ffe7b8','#ffdda0','#f6d18b','#ecc579','#dfb86a','#d2ab5c','#c49e4f','#b69242']}
};
const pick=(value,allowed,fallback)=>allowed.includes(value)?value:fallback;
const FOLIO=/^[A-Za-z0-9._-]{1,24}$/;
const median=a=>{const s=a.slice().sort((x,y)=>x-y),i=Math.floor(s.length/2);return s.length?s.length%2?s[i]:(s[i-1]+s[i])/2:0;};
// ---- the address
/* parse(hash) -> the page's state, every value checked; serialize(state) -> the hash, defaults left out */
function parse(h={}){
 const s={by:pick(h.by,BY,'section'),group:typeof h.group==='string'?h.group:'',align:pick(h.align,ALIGNS,'page'),anchor:pick(h.anchor,ANCHORS,'edge'),coords:pick(h.coords,COORDS,'flat'),scale:pick(h.scale,SCALES,'pixels'),
  color:pick(h.color,COLORS,'page'),cell:pick(h.cell,CELLS,'20'),palette:pick(h.palette,Object.keys(HEATMAPS),'blues'),focus:typeof h.focus==='string'?h.focus:'',op:{...OPACITY_DEFAULTS},edits:decodeEdits(h.edits)};
 s.layers=typeof h.layers==='string'?LAYERS.filter(k=>h.layers.split(',').includes(k)):['heatmap','polygons'];
 if(typeof h.op==='string')h.op.split(',').forEach((v,i)=>{const n=Number(v),k=OPACITY[i]&&OPACITY[i][0];if(k&&v!==''&&Number.isFinite(n)&&n>=0&&n<=100)s.op[k]=n;});
 return s;
}
function serialize(s){
 const o={};
 for(const [k,d] of [['by','section'],['group',''],['align','page'],['anchor','edge'],['coords','flat'],['scale','pixels'],['color','page'],['cell','20'],['palette','blues'],['focus','']])if(s[k]!==d)o[k]=s[k];
 if(s.layers.join()!=='heatmap,polygons')o.layers=s.layers.join()||'none';
 if(OPACITY.some(([k])=>s.op[k]!==OPACITY_DEFAULTS[k]))o.op=OPACITY.map(([k])=>s.op[k]).join(',');
 const edits=encodeEdits(s.edits||{});if(edits)o.edits=edits;
 return o;
}
/* The pages added to and removed from each group, in the address: 'section/Herbal A:+f67r1,f68r1:-f8v|golf/1a:-f20v' */
function encodeEdits(edits){
 return Object.keys(edits).sort().map(k=>{const e=edits[k],parts=[k];if(e.add&&e.add.length)parts.push('+'+e.add.join(','));if(e.remove&&e.remove.length)parts.push('-'+e.remove.join(','));return parts.length>1?parts.join(':'):null;}).filter(Boolean).join('|');
}
function decodeEdits(text){
 const out={};if(typeof text!=='string')return out;
 for(const item of text.split('|')){
  const [key,...parts]=item.split(':');if(!key||!parts.length)continue;
  const edit={add:[],remove:[]};
  for(const p of parts)edit[p[0]==='+'?'add':'remove'].push(...p.slice(1).split(',').filter(f=>FOLIO.test(f)));
  if(edit.add.length||edit.remove.length)out[key]=edit;
 }
 return out;
}
// ---- groups
/* groups(pages, list, by) -> [{name, pages}], the pages in list order: sections by page count, or Golf groups in their order */
function groups(pages,list,by='section'){
 const map=new Map();
 for(const f of list){const p=pages[f];if(!p)continue;const name=(by==='golf'?p.group:p.section)||'—';if(!map.has(name))map.set(name,[]);map.get(name).push(f);}
 const rank=n=>{const i=GOLF_ORDER.indexOf(n);return i<0?GOLF_ORDER.length:i;};
 return [...map].map(([name,folios])=>({name,pages:folios})).sort((a,b)=>by==='golf'?rank(a.name)-rank(b.name)||a.name.localeCompare(b.name):b.pages.length-a.pages.length||a.name.localeCompare(b.name));
}
const editKey=(by,name)=>by+'/'+name;
/* customize(group, list, edit) -> the group with its pages added and removed: {name, original, universe, pages, added, removed}. pages runs
   in list order. universe is the group's own pages and then the rest of the manuscript: colours follow it, so they hold as pages come and go. */
function customize(group,list,edit={}){
 const base=new Set(group.pages),known=new Set(list),add=new Set((edit.add||[]).filter(f=>known.has(f)&&!base.has(f))),remove=new Set((edit.remove||[]).filter(f=>base.has(f)));
 return {name:group.name,original:group.pages,universe:[...group.pages,...list.filter(f=>!base.has(f))],pages:list.filter(f=>(base.has(f)&&!remove.has(f))||add.has(f)),added:list.filter(f=>add.has(f)),removed:group.pages.filter(f=>remove.has(f))};
}
/* included(custom, list, folios, include) -> the {add, remove} that puts those pages in or takes them out of a customized group */
function included(custom,list,folios,include){
 const selected=new Set(custom.pages),base=new Set(custom.original);
 for(const f of folios)if(include)selected.add(f);else selected.delete(f);
 return {add:list.filter(f=>selected.has(f)&&!base.has(f)),remove:custom.original.filter(f=>!selected.has(f))};
}
/* cleanEdits(pages, list, edits) -> only the edits that change a group that exists, with only pages that exist */
function cleanEdits(pages,list,edits){
 const out={};
 for(const by of BY)for(const g of groups(pages,list,by)){const key=editKey(by,g.name);if(!edits[key])continue;const c=customize(g,list,edits[key]);if(c.added.length||c.removed.length)out[key]={add:c.added,remove:c.removed};}
 return out;
}
/* lineTokens(lines) -> Map 'folio|locus' -> the tokens of that line, from the bundle's lines */
function lineTokens(lines){const out=new Map();for(const L of lines)out.set(L.page+'|'+L.locus,L.end-L.start);return out;}
// ---- one page
/* paragraphPolygons(rows, pitch) -> the outer envelopes of consecutive complete rows ({position, line, locus, rect, cy}). Rows join
   halfway across the whitespace between them; a missing row, a reversed step or one over 2.5 pitches starts a new polygon. Not an
   ink contour: interior gaps are inside it. */
function paragraphPolygons(rows,pitch){
 const runs=[];
 for(const row of rows){const run=runs[runs.length-1],last=run&&run[run.length-1],dy=last?row.cy-last.cy:0;
  if(last&&row.position===last.position+1&&dy>0&&dy<=2.5*pitch)run.push(row);else runs.push([row]);}
 return runs.map((run,index)=>{
  const boxes=run.map(r=>r.rect.slice());
  for(let i=1;i<boxes.length;i++)if(boxes[i][1]>boxes[i-1][3]){const join=(boxes[i][1]+boxes[i-1][3])/2;boxes[i-1][3]=join;boxes[i][1]=join;}
  const ys=[...new Set(boxes.flatMap(r=>[r[1],r[3]]))].sort((a,b)=>a-b),bands=[];
  for(let i=1;i<ys.length;i++){const lo=ys[i-1],hi=ys[i],on=boxes.filter(b=>b[1]<hi&&b[3]>lo);if(on.length)bands.push([Math.min(...on.map(b=>b[0])),lo,Math.max(...on.map(b=>b[2])),hi]);}
  return {index,lines:run.map(r=>r.line),loci:run.map(r=>r.locus),points:[...bands.flatMap(b=>[[b[0],b[1]],[b[0],b[3]]]),...bands.slice().reverse().flatMap(b=>[[b[2],b[3]],[b[2],b[1]]])]};
 }).filter(p=>p.points.length>=4);
}
/* extract(folio, page, words, tokens, {align, anchor, coordinates, scale}) -> {folio, available, boxes, features, paragraphs, stats}.
   align 'page' keeps the page's layout on one anchor; 'starts' moves each paragraph to its own. The anchor is the opening word's
   baseline or a corner of the complete horizontal text. A paragraph or page whose anchor line is not complete and horizontal is
   left out and counted, never given a later line's anchor. Only horizontal lines are drawn.
   The default anchor, 'edge', takes its height from the opening word's baseline and its x from the leftmost box of the paragraph text:
   an opening word is usually at the margin, but not on f84v, whose first paragraph is at the top right. Not the median line start,
   which on f36v and f67r2 falls some 300 px inside the margin, where most lines wrap a drawing. */
function extract(folio,page,words,tokens,options={}){
 const coordinates=options.coordinates==='recorded'?'recorded':'flat',aligned=options.align==='starts',anchorMode=ANCHORS.includes(options.anchor)?options.anchor:'edge',scale=options.scale==='body_height'?'body_height':'pixels';
 const sel=M.selectUnits(page,words,{block:'page',cutoff:'all',coordinates,alignment:'page',scale}),factor=scale==='body_height'?M.BODY_HEIGHT_PX/(page.H||30):1;
 const byLine=new Map();for(const u of sel.all){if(!byLine.has(u.line_abs))byLine.set(u.line_abs,[]);byLine.get(u.line_abs).push(u);}
 for(const us of byLine.values())us.sort((a,b)=>a.first-b.first);
 const horizontal=li=>page.lines[li][3]==='horizontal',complete=li=>{const us=byLine.get(li)||[];return us.length>0&&us.reduce((n,u)=>n+u.token_count,0)===tokens.get(folio+'|'+page.lines[li][0]);};
 let moved=[0,0];
 const point=u=>{const raw=coordinates==='recorded'?u.base:u.flat_base;return [(raw[0]-sel.origin[0])*factor-moved[0],(raw[1]-sel.origin[1])*factor-moved[1]];};
 const leftEdge=lines=>Math.min(...lines.filter(horizontal).flatMap(li=>(byLine.get(li)||[]).map(u=>u.rect[0])));
 const anchorOf=(lines,mode)=>{
  const end=mode==='bottom-left'?lines[lines.length-1]:lines[0];
  if(end==null||!horizontal(end)||!complete(end))return null;
  if(mode==='opening'||mode==='edge'){const p=point(byLine.get(end)[0]);return {point:mode==='edge'?[leftEdge(lines),p[1]]:p,line:end};}
  const boxes=lines.filter(li=>horizontal(li)&&complete(li)).flatMap(li=>byLine.get(li)).map(u=>u.rect);
  return {point:[Math.min(...boxes.map(r=>r[0])),mode==='bottom-left'?Math.max(...boxes.map(r=>r[3])):Math.min(...boxes.map(r=>r[1]))],line:end};
 };
 const moveAll=by=>{moved=by;for(const u of sel.all){u.rect=u.rect.map((v,j)=>v-by[j%2]);u.baseline-=by[1];}};
 const whole=page.blocks.find(b=>b[0]==='page')[1],opening=page.blocks[0][1][0],keys=page.blocks.filter(b=>/^p\d+$/.test(b[0])),byCorner=anchorMode==='top-left'||anchorMode==='bottom-left',corner=byCorner?anchorOf(whole,anchorMode):null;
 if(corner)moveAll(corner.point);
 const first=sel.all.find(u=>u.anchor),opened=!!(sel.available&&first&&first.line_abs===opening),pageAvailable=byCorner?!!corner:opened;
 if(anchorMode==='edge'&&opened){const edge=leftEdge(keys.flatMap(b=>b[1]));if(Number.isFinite(edge))moveAll([edge,0]);}
 const stats={paragraphs:0,omittedParagraphs:0,omittedRows:0,missingStarts:0,missingEnds:0,breaks:0,unlocatedBreaks:0};
 const out={folio,section:page.section,group:page.group,node:page.node,available:pageAvailable,boxes:[],features:[],paragraphs:[],stats};
 if(!pageAvailable&&!aligned)return out;
 const paragraphOf=new Map();
 for(const [key,lines] of keys){stats.paragraphs++;for(const li of lines)paragraphOf.set(li,key);}
 page.lines.forEach((L,li)=>{
  if(!horizontal(li))return;
  const us=byLine.get(li)||[],paragraph=paragraphOf.get(li)||null;
  for(const u of us){
   out.boxes.push({rect:u.rect,line:li,baseline:u.baseline,paragraph});
   if(!u.intrusion)continue;
   stats.breaks++;
   const v=us.find(x=>x.first===u.last+1);
   if(!v||v.rect[0]<=u.rect[2]){stats.unlocatedBreaks++;continue;}
   out.features.push({type:'break',paragraph,line:li,x1:u.rect[2],y1:u.baseline,x2:v.rect[0],y2:v.baseline});
  }
 });
 for(const [key,lines] of keys)for(const type of ['start','end']){
  const li=type==='start'?lines[0]:lines[lines.length-1];
  if(!horizontal(li)||!complete(li)){stats[type==='start'?'missingStarts':'missingEnds']++;continue;}
  const us=byLine.get(li),left=us.reduce((a,b)=>a.rect[0]<b.rect[0]?a:b),right=us.reduce((a,b)=>a.rect[2]>b.rect[2]?a:b);
  out.features.push({type,paragraph:key,line:li,x1:left.rect[0],y1:left.baseline,x2:right.rect[2],y2:right.baseline});
 }
 for(const [key,lines] of keys){
  const registered=anchorMode==='opening'?null:anchorOf(lines,anchorMode),head=(byLine.get(lines[0])||[])[0],base=registered?registered.point:anchorMode==='opening'&&head?point(head):null;
  const usable=anchorMode==='opening'?!!base&&out.features.some(f=>f.type==='start'&&f.paragraph===key):!!registered,shift=aligned&&usable?base:[0,0];
  const paragraph={id:folio+'/'+key,key,lines,available:aligned?usable:pageAvailable,polygons:[],completeRows:0,omittedRows:0};out.paragraphs.push(paragraph);
  if(aligned&&!usable){paragraph.omittedRows=lines.length;stats.omittedParagraphs++;stats.omittedRows+=lines.length;continue;}
  const boxes=out.boxes.filter(b=>b.paragraph===key);
  if(aligned){
   for(const f of out.features)if(f.paragraph===key){f.x1-=shift[0];f.x2-=shift[0];f.y1-=shift[1];f.y2-=shift[1];}
   for(const b of boxes){b.rect=b.rect.map((v,j)=>v-shift[j%2]);b.baseline-=shift[1];}
  }
  const rows=[];
  lines.forEach((li,position)=>{
   const bs=boxes.filter(b=>b.line===li);
   if(!horizontal(li)||!bs.length||!complete(li)){paragraph.omittedRows++;stats.omittedRows++;return;}
   const rect=[Math.min(...bs.map(b=>b.rect[0])),Math.min(...bs.map(b=>b.rect[1])),Math.max(...bs.map(b=>b.rect[2])),Math.max(...bs.map(b=>b.rect[3]))];
   rows.push({line:li,locus:page.lines[li][0],position,rect,cy:(rect[1]+rect[3])/2});
  });
  const steps=rows.slice(1).flatMap((r,i)=>r.position===rows[i].position+1&&r.cy>rows[i].cy?[r.cy-rows[i].cy]:[]),pitch=median(steps)||median(rows.map(r=>r.rect[3]-r.rect[1]))*1.5||30*factor;
  paragraph.completeRows=rows.length;paragraph.polygons=paragraphPolygons(rows,pitch);
 }
 if(aligned){
  const usable=new Set(out.paragraphs.filter(p=>p.available).map(p=>p.key));
  out.features=out.features.filter(f=>usable.has(f.paragraph));out.boxes=out.boxes.filter(b=>usable.has(b.paragraph));out.available=usable.size>0;
 }
 return out;
}
// ---- a group
/* occupancy(entries, cellSize) -> for each grid cell the share of the selected pages with a word box in it. A page votes once however
   many boxes it has there, the grid stays anchored at (0, 0), and a page that could not be aligned stays in the denominator. */
function occupancy(entries,cellSize=20){
 if(!Number.isFinite(cellSize)||cellSize<=0)throw Error('occupancy needs a positive cell size');
 const pages=new Map(),cells=new Map();
 for(const e of entries){if(!pages.has(e.folio))pages.set(e.folio,{available:false,boxes:[]});const p=pages.get(e.folio);p.available=p.available||e.available;if(e.available)p.boxes.push(...e.boxes);}
 let pagesWithBoxes=0,invalidBoxes=0;const unavailable=[];
 for(const [folio,p] of pages){
  if(!p.available)unavailable.push(folio);
  const seen=new Set();let valid=0;
  for(const b of p.boxes){
   const r=b.rect;if(!r||r.length!==4||!r.every(Number.isFinite)||r[2]<=r[0]||r[3]<=r[1]){invalidBoxes++;continue;}
   valid++;
   for(let iy=Math.floor(r[1]/cellSize);iy<Math.ceil(r[3]/cellSize);iy++)for(let ix=Math.floor(r[0]/cellSize);ix<Math.ceil(r[2]/cellSize);ix++){
    const key=ix+','+iy;if(seen.has(key))continue;seen.add(key);
    if(!cells.has(key))cells.set(key,{ix,iy,folios:[]});cells.get(key).folios.push(folio);
   }
  }
  if(valid)pagesWithBoxes++;
 }
 const denominator=pages.size;
 return {cellSize,denominator,pagesWithBoxes,unavailable,invalidBoxes,cells:[...cells.values()].sort((a,b)=>a.iy-b.iy||a.ix-b.ix).map(c=>({ix:c.ix,iy:c.iy,x:c.ix*cellSize,y:c.iy*cellSize,count:c.folios.length,percent:100*c.folios.length/denominator,folios:c.folios}))};
}
/* band(percent) -> 0..9, the ten equal bands of the heatmap; ramp(name, dark) -> their colours, brightest for most pages on a dark page */
const band=percent=>Math.max(0,Math.min(9,Math.ceil(percent/10)-1));
function ramp(name,dark){const c=(HEATMAPS[name]||HEATMAPS.blues).colors;return dark?c.slice().reverse():c;}
/* bounds(entries) -> {x0, y0, x1, y1} of every box, or null */
function bounds(entries){
 let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
 for(const e of entries)for(const b of e.boxes){x0=Math.min(x0,b.rect[0]);y0=Math.min(y0,b.rect[1]);x1=Math.max(x1,b.rect[2]);y1=Math.max(y1,b.rect[3]);}
 return x1>x0?{x0,y0,x1,y1}:null;
}
const hue=i=>'hsl('+((i*137.507764)%360).toFixed(2)+' 65% 56%)';
/* colorKey(mode, folio, page) -> what shares a colour: the page, or its bifolium, Golf group or section */
const colorKey=(mode,folio,page)=>mode==='bifolium'?page.node:mode==='group'?page.group:mode==='section'?page.section:folio;
/* colorIndex(mode, folios, pages) -> Map colour key -> index, in the order of folios (a group's universe, so that colours hold through edits) */
function colorIndex(mode,folios,pages){const seen=new Map();for(const f of folios){const k=colorKey(mode,f,pages[f]);if(!seen.has(k))seen.set(k,seen.size);}return seen;}
const api={GOLF_ORDER,BY,ALIGNS,ANCHORS,COORDS,SCALES,COLORS,CELLS,LAYERS,OPACITY,OPACITY_DEFAULTS,HEATMAPS,parse,serialize,encodeEdits,decodeEdits,groups,editKey,customize,included,cleanEdits,lineTokens,paragraphPolygons,extract,occupancy,band,ramp,bounds,hue,colorKey,colorIndex};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VMS_SECTIONS=api;
})(typeof window!=='undefined'?window:globalThis);
