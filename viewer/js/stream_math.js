/* The Page stream on the toolkit's compact pages (compare/pages.json.gz): which bifolia and pages run in which order, how a page is
   registered and turned, and where the rows of a chain sit. A page gets one translation, one optional uniform scale and one optional
   rigid turn; a row moves as a whole sheet. Nothing is fitted to a neighbour. No DOM. Node tests: viewer/test/stream_math.test.js. */
(function(root){
'use strict';
const M=(typeof module!=='undefined'&&module.exports)?require('./compare_math.js'):root.VMS_COMPARE;
const SLOTS=['Ar','Av','Br','Bv'],CYCLE={Ar:'Bv',Av:'Av',Br:'Ar',Bv:'Br'},MAX_OVERLAP=.95,PRESET_SCHEMA=1;
// the first value of each list is the default
const BY=['golf','section'],ORDERS=['bifolia','path1'],VIEWS=['chain','stream','overlay'],COLUMNS=['singulion','faces'],JOINS=['touch','half','frames'],COVERED=['faint','outline','margin','hidden','full'];
const ANCHORS=['source','opening','margin'],COORDS=['flat','recorded'],SCALES=['body_height','pixels'],TILTS=['restore','turn','none'],TRAILS=['all','pair','single'],ZOOMS=['1','0.5','0.75','1.5','2','3'];
const ROUTES=['all',...SLOTS.map(s=>'slot:'+s),...SLOTS.map(s=>'cycle:'+s)];
const pick=(value,allowed)=>allowed.includes(value)?value:allowed[0];
const clampOverlap=v=>Math.max(0,Math.min(MAX_OVERLAP,v));
// ---- the address
/* overlaps in the address: 'A:1-8>F:42-47=0.333|D:27-30>A:1-8=0.575'. A boundary belongs to a directed pair of neighbouring bifolia */
const encodeOverlaps=o=>Object.keys(o).sort().map(k=>k+'='+o[k]).join('|');
function decodeOverlaps(text){
 const out={};if(typeof text!=='string')return out;
 for(const item of text.split('|')){
  const i=item.lastIndexOf('='),raw=item.slice(i+1),value=Number(raw),pair=item.slice(0,i).split('>');
  if(i>0&&raw!==''&&Number.isFinite(value)&&pair.length===2&&pair[0]&&pair[1]&&pair[0]!==pair[1])out[pair.join('>')]=clampOverlap(value);
 }
 return out;
}
const decodeList=text=>typeof text==='string'?[...new Set(text.split(',').filter(Boolean))]:[];
/* fromWorkspace(hash) -> the view of a link or saved boundary set of the comparison workspace this page came from. Its order, joins and overlaps carry over.
   Its rigid turn does not: that turn leans every margin, so such a link opens on the recorded tilt, and Rigid turn stays a choice on the page */
const WORKSPACE_KEYS={seqGroup:'group',seqRoute:'route',seqIndex:'at',seqMode:'trail',seqJoin:'join',seqCovered:'covered',seqCoveredOpacity:'strength',seqSeam:'seam',seqOpacity:'fade',seqEdges:'margins',seqPages:'pages',scale:'scale',zoom:'zoom'};
function fromWorkspace(h){
 const json=text=>{try{return JSON.parse(text);}catch(e){return null;}},out={};
 for(const [from,to] of Object.entries(WORKSPACE_KEYS))if(h[from]!=null)out[to]=String(h[from]);
 out.view=h.seqDisplay==='four'?'chain':h.seqDisplay==='overlay'?'overlay':'stream';
 out.order=h.seqOrder==='path1'?'path1':'bifolia';
 out.columns=h.seqColumns==='singulion'?'singulion':'faces';
 out.anchor=h.seqAnchor||'opening';
 out.coords=['recorded','study_recorded'].includes(h.coordinates)?'recorded':'flat';
 out.tilt=String(h.seqRestore)==='0'?'none':'restore';
 if(h.eva!=null)out.words=String(h.eva)==='0'?'0':'1';
 if(h.seqCovered==null&&h.seqHideCovered!=null)out.covered=String(h.seqHideCovered)==='0'?'full':'hidden';
 const overlaps=json(h.seqOverlaps),custom=json(h.seqCustomOrder);
 if(overlaps&&typeof overlaps==='object'&&!Array.isArray(overlaps))out.overlaps=Object.entries(overlaps).map(([k,v])=>k+'='+v).join('|');
 if(Array.isArray(custom))out.custom=custom.join(',');
 return out;
}
/* parse(hash) -> the page's state, every value checked; serialize(state) -> the hash, defaults left out. oldLink marks a workspace link that turned its pages,
   so that the page can say why it does not look the same; it is not part of the address */
function parse(h={}){
 const workspace=Object.keys(h).some(k=>k.startsWith('seq')),oldLink=workspace&&String(h.seqRestore)!=='0';
 if(workspace)h=fromWorkspace(h);
 const number=(v,lo,hi,fallback)=>{const n=Number(v);return v!=null&&v!==''&&Number.isFinite(n)?Math.max(lo,Math.min(hi,n)):fallback;};
 return {by:pick(h.by,BY),group:typeof h.group==='string'&&h.group?h.group:'all',order:pick(h.order,ORDERS),route:pick(h.route,ROUTES),view:pick(h.view,VIEWS),columns:pick(h.columns,COLUMNS),join:pick(h.join,JOINS),
  covered:pick(h.covered,COVERED),strength:number(h.strength,0,1,.3),seam:typeof h.seam==='string'?h.seam:'',anchor:pick(h.anchor,ANCHORS),coords:pick(h.coords,COORDS),scale:pick(h.scale,SCALES),trail:pick(h.trail,TRAILS),
  fade:number(h.fade,.02,1,.2),zoom:pick(h.zoom,ZOOMS),tilt:pick(h.tilt,TILTS),words:h.words!=='0',margins:h.margins!=='0',at:Math.max(0,parseInt(h.at,10)||0),overlaps:decodeOverlaps(h.overlaps),custom:decodeList(h.custom),pages:decodeList(h.pages),oldLink};
}
function serialize(s){
 const o={};
 for(const [k,d] of [['by',BY[0]],['group','all'],['order',ORDERS[0]],['route',ROUTES[0]],['view',VIEWS[0]],['columns',COLUMNS[0]],['join',JOINS[0]],['covered',COVERED[0]],['strength',.3],['seam',''],['anchor',ANCHORS[0]],['coords',COORDS[0]],['scale',SCALES[0]],['trail',TRAILS[0]],['fade',.2],['zoom',ZOOMS[0]],['tilt',TILTS[0]],['at',0]])if(s[k]!==d)o[k]=String(s[k]);
 for(const k of ['words','margins'])if(!s[k])o[k]='0';
 const overlaps=encodeOverlaps(s.overlaps);if(overlaps)o.overlaps=overlaps;
 if(s.custom.length)o.custom=s.custom.join(',');
 if(s.pages.length)o.pages=s.pages.join(',');
 return o;
}
/* clean(state, pages, list) -> the state with only bifolia and pages that exist: a link from elsewhere can name anything */
function clean(state,pages,list){
 const nodes=new Set(list.map(f=>pages[f].node));
 state.overlaps=Object.fromEntries(Object.entries(state.overlaps).filter(([k])=>k.split('>').every(n=>nodes.has(n))));
 state.pages=state.pages.filter(f=>pages[f]);
 if(!state.custom.every(n=>nodes.has(n)))state.custom=[];
 return state;
}
// ---- saved boundary sets
const PRESET_KEYS=['by','group','order','route','view','columns','join','covered','strength','seam','anchor','coords','scale','trail','fade','zoom','at','tilt','words','margins','overlaps','custom','pages'];
/* normalizePreset(input) -> {schema, name, params}: only known settings, checked, or an Error saying what is wrong. A set saved in the workspace is translated */
function normalizePreset(input){
 if(!input||input.schema!==PRESET_SCHEMA||typeof input.name!=='string'||!input.name.trim()||!input.params||typeof input.params!=='object'||Array.isArray(input.params))throw Error('Choose a boundary set JSON file.');
 const source=Object.keys(input.params).some(k=>k.startsWith('seq'))?fromWorkspace(input.params):input.params,params={};
 if(Object.keys(input.params).some(k=>k.startsWith('seq'))){
  if(input.params.seqOverlaps!=null&&source.overlaps==null)throw Error('Invalid saved boundary percentages.');
  if(input.params.seqCustomOrder!=null&&source.custom==null)throw Error('Invalid saved bifolium order.');
 }
 for(const key of PRESET_KEYS)if(Object.hasOwn(source,key)){
  const value=source[key];
  if(!['string','number','boolean'].includes(typeof value)||String(value).length>30000)throw Error('Invalid setting: '+key);
  params[key]=String(value);
 }
 if(!params.group||!params.order)throw Error('This set does not name a group and an order.');
 if(params.overlaps!=null){
  const items=params.overlaps.split('|').filter(Boolean),out=decodeOverlaps(params.overlaps);
  if(items.length!==Object.keys(out).length||items.some(item=>{const v=Number(item.slice(item.lastIndexOf('=')+1));return v<0||v>MAX_OVERLAP;}))throw Error('Invalid saved boundary percentages.');
 }
 if(params.custom!=null){
  const items=params.custom.split(',');
  if(items.length>500||items.some(n=>!n||n.length>100)||new Set(items).size!==items.length)throw Error('Invalid saved bifolium order.');
 }
 return {schema:PRESET_SCHEMA,name:input.name.trim().slice(0,100),params};
}
/* presetParams(state) -> what a saved set stores; group and order are always named, so a set says what it was saved on */
const presetParams=s=>({group:s.group,order:s.order,...serialize(s)});
// ---- the order
function reorderNodes(base,custom=[]){return Array.isArray(custom)&&custom.length===base.length&&new Set(custom).size===base.length&&custom.every(n=>base.includes(n))?[...custom]:[...base];}
function moveNode(nodes,node,index){
 if(!nodes.includes(node)||!Number.isInteger(index))return [...nodes];
 const next=nodes.filter(n=>n!==node);next.splice(Math.max(0,Math.min(next.length,index)),0,node);return next;
}
/* sequence(pages, list, {by, group, route, selected, custom}) -> {nodes, baseNodes, custom, pages, missing}. list = the folios in the chosen order;
   a bifolium stands where its first page falls, and its pages run Ar, Av, Br, Bv. route 'slot:Ar' keeps one position; 'cycle:Ar' walks the
   candidate correspondence Ar > Bv > Br > Ar (Av > Av) from sheet to sheet, a hypothesis to look at and not an established reading order. */
function sequence(pages,list,{by='golf',group='all',route='all',selected=[],custom=[]}={}){
 const ids=new Set(selected),name=p=>(by==='golf'?p.group:p.section)||'—',scope=list.filter(f=>ids.size?ids.has(f):group==='all'||name(pages[f])===group);
 const baseNodes=[...new Set(scope.map(f=>pages[f].node))],nodes=reorderNodes(baseNodes,custom),out=[];
 let target=route.split(':')[1];
 nodes.forEach((node,nodeIndex)=>{
  const members=scope.filter(f=>pages[f].node===node).sort((a,b)=>SLOTS.indexOf(pages[a].slot)-SLOTS.indexOf(pages[b].slot)||a.localeCompare(b,undefined,{numeric:true}));
  for(const folio of members){
   const p=pages[folio];
   if(route==='all'||p.slot===target)out.push({folio,node,nodeIndex,slot:p.slot,face:p.face,panel:p.panel,section:p.section,group:p.group,position:SLOTS.indexOf(p.slot)+1,panels:list.filter(f=>pages[f].node===node&&pages[f].slot===p.slot).length});
  }
  if(route.startsWith('cycle:'))target=CYCLE[target];
 });
 return {nodes,baseNodes,custom:nodes.some((n,i)=>n!==baseNodes[i]),pages:out,missing:nodes.filter(n=>!out.some(p=>p.node===n))};
}
function visible(list,index,trail){return trail==='single'?list.slice(index,index+1):trail==='pair'?list.slice(Math.max(0,index-1),index+1):list.slice(0,index+1);}
/* nextBifolium(pages, index, delta) -> the index of the first page of the next sheet, or of the previous one */
function nextBifolium(list,index,delta){
 if(!list.length)return 0;
 const node=list[index].node;
 if(delta>0){const next=list.findIndex((p,i)=>i>index&&p.node!==node);return next<0?list.length-1:next;}
 const previous=list.slice(0,index).reverse().find(p=>p.node!==node);return previous?list.findIndex(p=>p.node===previous.node):0;
}
// ---- the rows of a chain
const seamKey=(before,after)=>before+'>'+after;
/* stackSheets(sheets, {join, overlaps, hideCovered}) -> {rows, height}. A row starts where the last one ends, less its overlap, a share of the
   preceding row's text height: the pair's own value, or the join's default. A pair's value is never carried to a different pair. foldY is the
   top of the next row; hideCovered cuts a row there, even where it runs on past a shorter sheet in front of it. */
function stackSheets(sheets,{join='touch',overlaps={},hideCovered=false}={}){
 const rows=sheets.map((sheet,index)=>({node:sheet.node,index,height:Math.max(0,Number(sheet.height)||0)}));
 rows.forEach((row,i)=>{
  const previous=rows[i-1],key=previous?seamKey(previous.node,row.node):null,value=key&&Object.hasOwn(overlaps,key)?overlaps[key]:null,manual=typeof value==='number'&&Number.isFinite(value);
  Object.assign(row,{key,manual,overlap:previous?(manual?clampOverlap(value):join==='half'?.5:0):0});
  row.top=previous?previous.top+previous.height*(1-row.overlap):0;
 });
 rows.forEach((row,i)=>{row.foldY=rows[i+1]?rows[i+1].top:null;row.visibleHeight=hideCovered&&row.foldY!==null?Math.min(row.height,Math.max(0,row.foldY-row.top)):row.height;});
 return {rows,height:Math.max(0,...rows.map(r=>r.top+r.visibleHeight))};
}
// ---- one page
/* marginRows(folio, page, units, tokens) -> the left end of each complete paragraph body row: {line, locus, x, y}. A row counts when every token of the
   line is located in at least three boxes, on a horizontal paragraph line that is not a paragraph's first. y is the median box bottom. */
function marginRows(folio,page,units,tokens){
 const byLine=new Map(),out=[];
 for(const u of units){if(!byLine.has(u.line_abs))byLine.set(u.line_abs,[]);byLine.get(u.line_abs).push(u);}
 page.lines.forEach(([locus,first,category,orientation],line)=>{
  const us=byLine.get(line)||[];
  if(category!=='P'||orientation!=='horizontal'||first||us.length<3||us.reduce((n,u)=>n+u.token_count,0)!==tokens.get(folio+'|'+locus))return;
  out.push({line,locus,x:Math.min(...us.map(u=>u.rect[0])),y:M.median(us.map(u=>u.rect[3]))});
 });
 return out;
}
/* register(folio, page, words, tokens, {coords, scale, anchor}) -> a whole-page selection in the page's own frame, its opening baseline at y = 0.
   anchor 'opening' puts the opening word at x = 0, 'source' keeps the page's source x, and 'margin' puts the median body margin at x = 0.
   available is false when the page's opening line has no box, because then there is nothing to hang the page on. */
function register(folio,page,words,tokens,{coords='flat',scale='body_height',anchor='source'}={}){
 const sel=M.selectUnits(page,words,{block:'page',cutoff:'all',coordinates:coords,alignment:'page',scale}),factor=scale==='body_height'?M.BODY_HEIGHT_PX/(page.H||30):1;
 const opening=page.blocks[0][1][0],before=marginRows(folio,page,sel.all,tokens);
 const shift=anchor==='source'?-sel.origin[0]*factor:anchor==='margin'&&before.length?M.median(before.map(r=>r.x)):0;
 const all=sel.all.map(u=>({...u,rect:u.rect.map((v,j)=>j%2?v:v-shift)}));
 return {...sel,folio,factor,all,chosen:all.filter(u=>u.selected),available:sel.available&&sel.all.some(u=>u.anchor&&u.line_abs===opening),shift,marginRows:marginRows(folio,page,all,tokens)};
}
/* orient(page, selection, coords, tilt) -> the selection's words as polygons, and its margin points, with the page's recorded median line angle put back
   (page.drift, the same lines in both states). Recorded coordinates already hold it, so nothing moves there.
   'restore', the default, undoes the tilt the way flattening removed it: flattening moves y only, so this is y + kx, and every x stays where it was
   recorded. It is one adjustment for the whole page: the page's median line angle comes back, each line keeps its flat shape and so not its own recorded
   angle, and the rest of the warp stays out.
   'turn' turns the page rigidly by the same angle. Word sizes and distances hold, but a rotation moves x as well, which flattening never did: each
   drawn margin leans by the page's own turn on top of its true slope (docs/STREAM.md). Kept for comparison with the study that used it. 'none' adds nothing. */
function orient(page,selection,coords='flat',tilt='restore'){
 const drift=page.drift||{},recorded=drift.recorded?drift.recorded.angle:null,inState=drift[coords]?drift[coords].angle:null,current=inState==null?null:inState;
 const restored=tilt!=='none'&&recorded!=null&&current!=null,delta=restored?recorded-current:0,rad=Math.PI/180,c=Math.cos(delta*rad),s=Math.sin(delta*rad),k=restored?Math.tan(recorded*rad)-Math.tan(current*rad):0;
 const move=tilt==='turn'?([x,y])=>[x*c-y*s,x*s+y*c]:([x,y])=>[x,y+k*x];
 const words=selection.all.map(u=>({...u,quad:[[u.rect[0],u.rect[1]],[u.rect[2],u.rect[1]],[u.rect[2],u.rect[3]],[u.rect[0],u.rect[3]]].map(move)}));
 const points=words.flatMap(w=>w.quad),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
 return {folio:selection.folio,selection,words,marginRows:selection.marginRows.map(r=>({...r,point:move([r.x,r.y])})),
  angle:{recorded:recorded==null?null:recorded,current,delta,restored,tilt,displayed:current===null?null:current+delta,n:drift.recorded?drift.recorded.n:0,unavailable:drift.recorded?drift.recorded.unavailable:null},
  bounds:points.length?{xmin:xs.reduce((a,b)=>Math.min(a,b)),xmax:xs.reduce((a,b)=>Math.max(a,b)),ymin:ys.reduce((a,b)=>Math.min(a,b)),ymax:ys.reduce((a,b)=>Math.max(a,b))}:{xmin:0,xmax:1000,ymin:0,ymax:80}};
}
/* bounds(selections) -> one frame for a whole overlay, so that stepping cannot resize it */
function bounds(selections){
 const boxes=selections.filter(s=>s.available).flatMap(s=>s.all.map(u=>u.rect));
 if(!boxes.length)return {xmin:-100,xmax:1000,ymin:-80,ymax:1500};
 const low=j=>boxes.reduce((a,r)=>Math.min(a,r[j]),Infinity),high=j=>boxes.reduce((a,r)=>Math.max(a,r[j]),-Infinity);
 return {xmin:Math.min(0,low(0))-110,xmax:high(2)+70,ymin:Math.min(0,low(1))-65,ymax:high(3)+65};
}
const api={SLOTS,CYCLE,MAX_OVERLAP,PRESET_SCHEMA,PRESET_KEYS,BY,ORDERS,VIEWS,COLUMNS,JOINS,COVERED,ANCHORS,COORDS,SCALES,TILTS,TRAILS,ZOOMS,ROUTES,parse,serialize,clean,fromWorkspace,encodeOverlaps,decodeOverlaps,normalizePreset,presetParams,reorderNodes,moveNode,sequence,visible,nextBifolium,seamKey,stackSheets,marginRows,register,orient,bounds};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VMS_STREAM=api;
})(typeof window!=='undefined'?window:globalThis);
