"use strict";
// The Light table's model: a bifolium as an open sheet of two leaves on the parchment scale, either face up, each page's words where they lie on its
// leaf, the face underneath seen through the parchment; which folds and edges a moved piece lines up with; and the address.
(function(root){
const T=typeof module!=='undefined'&&module.exports?require('./stream_math.js'):root.VMS_STREAM;
/* An open sheet in millimetres: x from the left edge of the face that is up, the fold at FOLD, y from the leaves' top edge. A leaf is the catalogue's
   LEAF (width, height). The outer face is Bv | Ar and the inner face Av | Br, as in the physical faces of the other pages, so turning the sheet over
   about its fold puts Av behind Ar and Br behind Bv. */
const LEAF=[T.LEAF_MM,225],FOLD=T.LEAF_MM,SLOTS=['Bv','Ar','Av','Br'],FACE={Bv:'outer',Ar:'outer',Av:'inner',Br:'inner'},LEFT={Bv:true,Ar:false,Av:true,Br:false};
/* COLOURINGS: 'sheet' gives each piece its own colour; 'face' gives every page of a sheet's outer face one colour and every page of its inner face
   another, so pieces lying over one another show which side of their sheet is up */
/* WORD_DIRS: the written words of rings and turned lines, 'ring' along the writing, 'level' upright (js/word_labels.js) */
const BIT={Bv:1,Ar:2,Av:4,Br:8},ALL=15,RECTOS=['Ar','Br'],VERSOS=['Bv','Av'],COORDS=['flat','recorded'],COLOURINGS=['sheet','face'],WORD_DIRS=['ring','level'],ZOOMS=['1.5','0.75','1','2','3','4'],ZOOM_RANGE=[0.3,8],COLOURS=6,MAX_SHEETS=24,ALIGN_MM=1,LIMIT=5000;
/* A sheet divided at its fold is two leaves, each a piece of its own: leaf A holds Ar and Av, leaf B holds Bv and Br. A piece is {node, part, copy}:
   part '' for the whole sheet, 'A' or 'B'; copy 1, 2, ... for each time the same bifolium is put on the table. Its id is node, node/A or node/B,
   with ~copy after it from the second copy on. */
const PARTS={A:['Ar','Av'],B:['Bv','Br']},idOf=s=>s.node+(s.part?'/'+s.part:'')+((s.copy||1)>1?'~'+s.copy:'');
const sameCopy=(a,b)=>a.node===b.node&&(a.copy||1)===(b.copy||1);
/* nextCopy(pieces, node) -> the copy number a new piece of this bifolium takes: one past the highest on the table */
const nextCopy=(pieces,node)=>1+pieces.filter(p=>p.node===node).reduce((m,p)=>Math.max(m,p.copy||1),0);
const panelOrder=p=>p===''||p==null?0:Number.isFinite(Number(p))?Number(p):99;
/* sheet(node, pages, {coords, sheets}) -> {node, leaves, missing}. One leaf a page, on its own face: a recto's x from the fold rightwards, a verso's
   leftwards, both from the page's fold and top edge (page.paper, vmsspatial.leaves), at its own millimetres. coords 'flat' takes each box's warp
   shift out of its y. missing: the pages with no paper record, which cannot be placed.
   sheets: the foldout sheets of the page data (compact.sheets, vmsspatial.sheets). A foldout leaf listed there spans its panels' measured widths out
   from the fold, split at its creases and further folds, or each face's own (faces, where the binding hides a different strip of a panel on each
   face); the Rosettes sheet is drawn by its grid (rosettes). A foldout not listed lays its panels outward a catalogue leaf apiece, in panel order. */
function sheet(node,pages,{coords='flat',sheets={}}={}){
 const S=(sheets||{})[node]||{};
 if(S.grid)return rosettes(node,pages,coords,S.grid);
 const members=Object.entries(pages).filter(([,p])=>p.node===node),leaves=[],missing=[];
 for(const slot of SLOTS){
  const plan=S[slot[0]],widths=plan&&((plan.faces||{})[slot[1]]||plan.widths),cum=widths&&widths.reduce((a,w)=>[...a,a[a.length-1]+w],[0]);
  members.filter(([,p])=>p.slot===slot).sort((a,b)=>panelOrder(a[1].panel)-panelOrder(b[1].panel)||(a[0]<b[0]?-1:1)).forEach(([folio,p],k)=>{
   const L=p.paper;if(!L){missing.push(folio);return;}
   const span=plan&&plan.pages[folio],lo=span?cum[span[0]]:k*LEAF[0],hi=span?cum[span[span.length-1]+1]:(k+1)*LEAF[0];
   const cuts=span?[...new Set([...span.map(i=>cum[i]),hi,...(plan.creases||[]).filter(([i])=>span.includes(i)).map(([i,at])=>cum[i]+at)])].sort((a,b)=>a-b):[lo,hi];
   const left=LEFT[slot],at=v=>left?FOLD-v:FOLD+v,off=at(lo),d=u=>coords==='flat'?u[7]:0;
   const cells=cuts.slice(0,-1).map((c,i)=>{const a=at(c),b=at(cuts[i+1]);return [Math.min(a,b),0,Math.max(a,b),LEAF[1]];});
   const words=p.units.map((u,id)=>({id,rect:[(u[3]-L.fold)/L.mm+off,(u[4]-d(u)-L.top)/L.mm,(u[5]-L.fold)/L.mm+off,(u[6]-d(u)-L.top)/L.mm]}));
   leaves.push({folio,slot,face:FACE[slot],side:p.side,panel:p.panel||'',k,leaf:[Math.min(at(lo),at(hi)),0,Math.max(at(lo),at(hi)),LEAF[1]],cells,words,measuredWidth:!!span,
    estimated:estimatedOf(L)});
  });
 }
 return {node,leaves,missing,measured:!!(S.A||S.B)};
}
/* a page's fold, top and scale count as measured when measured on its scan, or placed there: a fold or crease from vmsspatial.sheets ('sheet'), a
   foldout panel's top from the panel beside it ('panel') */
const estimatedOf=L=>['fold_method','top_method','scale_method'].filter(m=>!['measured','sheet','panel'].includes(L[m])).map(m=>m.split('_')[0]);
/* rosettes(node, pages, coords, grid) -> the Rosettes sheet, three panels across and two down (vmsspatial.sheets, docs/LIGHTTABLE.md). Inside, the
   Rosettes across all six panels, f85v | f86r; outside, the lower row the same way up as the Rosettes and the upper row upside down, to be read with
   the upper half folded down over the lower. Each panel is a catalogue leaf, anchored at its side toward the fold and at the horizontal crease, which
   is a panel's own top edge as photographed. grid.pages: folio -> [panel out from the fold, row (1 upper, 2 lower), upside down]; grid.inside: the
   Rosettes image's fold and outer crease, in the upper and the lower row, and its horizontal crease, in its own frame. The outer crease is a check:
   with the drawing placed by its fold, it lands within 3 mm of the panel edge. */
function rosettes(node,pages,coords,grid){
 const [W,H]=LEAF,leaves=[],missing=[],d=u=>coords==='flat'?u[7]:0,box=(a,b)=>[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];
 for(const [folio,[col,row1,turned]] of Object.entries(grid.pages)){
  const p=pages[folio],L=p&&p.paper,row=row1-1;if(!p)continue;if(!L){missing.push(folio);continue;}
  const left=LEFT[p.slot],X=FOLD+(left?-1:1)*(col-1)*W,x0=left?X-W:X,cell=[x0,row*H,x0+W,row*H+H],s=turned?-1:1;
  // upside down, a page's side toward the fold is its far side as read: its fold, estimated from the median inner margin on the near side, is
  // reflected about its text
  const fold=turned?Math.min(...p.units.map(u=>u[3]))+Math.max(...p.units.map(u=>u[5]))-L.fold:L.fold,at=(x,y)=>[X+s*(x-fold)/L.mm,H+s*(y-L.top)/L.mm];
  const words=p.units.map((u,id)=>({id,rect:box(at(u[3],u[4]-d(u)),at(u[5],u[6]-d(u)))}));
  leaves.push({folio,slot:p.slot,face:FACE[p.slot],side:p.side,panel:p.panel||'',k:col-1,turned,leaf:cell,cells:[cell],words,estimated:estimatedOf(L)});
 }
 // the Rosettes, one page across the inside, as photographed: one placement for the whole drawing, by its fold (the line's mean place in the upper
 // and the lower row) and its horizontal crease, so that the rosettes run on unbroken across the creases; each word goes with the leaf it lands on.
 // Placed panel by panel, the fold's 34 px lean between the rows broke the middle row of rosettes at the horizontal crease
 const I=grid.inside,p=pages[I.folio],L=p&&p.paper;
 if(p&&!L)missing.push(I.folio);
 else if(p){
  const parts={Av:[],Br:[]},fold=(I.fold[0]+I.fold[1])/2;
  p.units.forEach((u,id)=>{
   const rect=[FOLD+(u[3]-fold)/L.mm,H+(u[4]-d(u)-I.middle)/L.mm,FOLD+(u[5]-fold)/L.mm,H+(u[6]-d(u)-I.middle)/L.mm];
   parts[(rect[0]+rect[2])/2>=FOLD?'Br':'Av'].push({id,rect});
  });
  const estimated=estimatedOf(L),base={folio:I.folio,face:'inner',panel:p.panel||'',k:0,turned:false,estimated};
  leaves.push({...base,name:'fRos (f85v)',slot:'Av',side:'v',leaf:[0,0,W,2*H],cells:[[0,0,W,H],[0,H,W,2*H]],words:parts.Av});
  leaves.push({...base,name:'fRos (f86r)',slot:'Br',side:'r',leaf:[W,0,3*W,2*H],cells:[[W,0,2*W,H],[2*W,0,3*W,H],[W,H,2*W,2*H],[2*W,H,3*W,2*H]],words:parts.Br});
 }
 return {node,leaves,missing,height:2*H,folded:true};
}
/* view(model, up, show, part) -> the sheet as drawn with face `up` ('outer' or 'inner') on top: {box, fold, leaves: [{..., front, shown, leaf, words}]}.
   A leaf of the face underneath is mirrored about the fold, so it lands behind its partner on the same physical leaf, as seen through the parchment.
   show is a bit mask over the slots (BIT); a leaf not shown keeps its outline. part 'A' or 'B' keeps that leaf's two pages only, in the same frame,
   so a divided sheet's leaves start where they lay. box holds the sheet, or the leaf, and any text past it. */
function view(model,up='outer',show=ALL,part=''){
 const H=model.height||LEAF[1],flip=r=>[2*FOLD-r[2],r[1],2*FOLD-r[0],r[3]],right=(part==='A')===(up==='outer');
 const box=part?[right?FOLD:FOLD-LEAF[0],0,right?FOLD+LEAF[0]:FOLD,H]:[0,0,2*LEAF[0],H];
 const leaves=model.leaves.filter(l=>!part||PARTS[part].includes(l.slot)).map(l=>{
  const front=l.face===up,leaf=front?l.leaf:flip(l.leaf),cells=(l.cells||[l.leaf]).map(c=>front?c:flip(c)),words=front?l.words:l.words.map(w=>({...w,rect:flip(w.rect)})),shown=!!(show&BIT[l.slot]);
  for(const r of [leaf,...(shown?words.map(w=>w.rect):[])]){box[0]=Math.min(box[0],r[0]);box[1]=Math.min(box[1],r[1]);box[2]=Math.max(box[2],r[2]);box[3]=Math.max(box[3],r[3]);}
  return {...l,front,shown,leaf,cells,words};
 });
 return {node:model.node,part,up,box,fold:FOLD,height:H,folded:!!model.folded,measured:!!model.measured,leaves};
}
/* lines(view) -> the lines a piece lines up by, in its own frame: every edge of its face-up leaves, the fold first among them, so that of two equal
   matches the guide is drawn at the fold, and its top and bottom edges */
function lines(v){
 const front=v.leaves.filter(l=>l.front),edges=new Set(front.length?front.flatMap(l=>(l.cells||[l.leaf]).flatMap(c=>[c[0],c[2]])):[v.box[0],v.box[2]]);
 return {xs:[...(edges.has(v.fold)?[v.fold]:[]),...[...edges].filter(x=>x!==v.fold).sort((a,b)=>a-b)],ys:[0,v.height||LEAF[1]]};
}
/* align(x, y, mine, others, tolerance) -> guides: [{axis, at, off}]. Nothing is moved. For a piece at (x, y) with lines `mine` (its own frame), the
   nearest of another piece's lines (others: their lines already on the table) that one of its own lines comes within the tolerance of, across and
   down separately: a fold on a fold or on an outer edge, two sheets or leaves side by side, top edges level, or one piece above another. at is that
   line on the table, and off how far the piece would have to move to meet it, 0 when it does. */
function align(x,y,mine,others,tolerance=ALIGN_MM){
 let bx=null,gx=null,by=null,gy=null;
 for(const o of others){
  for(const a of mine.xs)for(const c of o.xs){const t=c-a;if(Math.abs(t-x)<=tolerance&&(bx===null||Math.abs(t-x)<Math.abs(bx-x))){bx=t;gx=c;}}
  for(const a of mine.ys)for(const c of o.ys){const t=c-a;if(Math.abs(t-y)<=tolerance&&(by===null||Math.abs(t-y)<Math.abs(by-y))){by=t;gy=c;}}
 }
 return [...(bx===null?[]:[{axis:'x',at:gx,off:bx-x}]),...(by===null?[]:[{axis:'y',at:gy,off:by-y}])];
}
/* within ALIGNED mm a guide counts as met: the address keeps positions to 0.1 mm */
const ALIGNED=0.05;
/* placed(piece, lines) -> its lines on the table */
const placed=(s,l)=>({xs:l.xs.map(v=>v+s.x),ys:l.ys.map(v=>v+s.y)});
/* relative(piece, reference) -> how far a piece's fold edge and top edge sit from the reference's, in mm. A piece's fold edge is at x + FOLD */
const relative=(s,ref)=>({fold:s.x-ref.x,top:s.y-ref.y});
/* turn(piece, boxOf) -> the piece turned over. A whole sheet turns about its fold, which stays where it is. A leaf turns over where it lies, so its
   bound edge goes to the other side: boxOf(piece) gives its view box, whose centre is kept. */
function turn(s,boxOf){
 const t={...s,up:s.up==='outer'?'inner':'outer'};
 if(s.part){const a=boxOf(s),b=boxOf(t);t.x=s.x+((a[0]+a[2])-(b[0]+b[2]))/2;}
 return t;
}
/* divide(sheet) -> its two leaves, each where it lay; join(piece, pieces) -> the list with the piece's sheet whole again, where that piece lies, in
   the place of the first of its leaves. Both leaves of a sheet keep its colour. */
const divide=s=>['A','B'].map(part=>({...s,part}));
function join(s,pieces){
 const mates=pieces.filter(p=>sameCopy(p,s)),at=pieces.indexOf(mates[0]),whole={...s,part:'',show:mates.reduce((m,p)=>m|p.show,0)};
 return [...pieces.slice(0,at).filter(p=>!sameCopy(p,s)),whole,...pieces.slice(at+1).filter(p=>!sameCopy(p,s))];
}
/* stack(sheets) puts every sheet's fold and top edge on the first one's, as nested in a quire; spread(sheets, width) lays them out in rows across
   `width` mm, a sheet's own width apart. Both return new positions in list order. */
const stack=sheets=>sheets.map(s=>({...s,x:sheets[0].x,y:sheets[0].y}));
function spread(sheets,width,boxes,gap=20){
 let x=gap,y=gap,row=0;
 return sheets.map((s,i)=>{const b=boxes[i],w=b[2]-b[0],h=b[3]-b[1];if(x>gap&&x+w>width){x=gap;y+=row+gap;row=0;}const out={...s,x:x-b[0],y:y-b[1]};x+=w+gap;row=Math.max(row,h);return out;});
}
// ---- the address: sheets=node[/A|/B][~copy]@x,y,face,mask,colour|..., coords, zoom, guides, snap, fc (the face colours)
/* a colour: 1 to COLOURS, one of the page's six sheet colours (stepped for each theme), 0 ink, or six hex digits of the viewer's own choosing */
const colourOfText=t=>/^[0-6]$/.test(t)?Number(t):/^[0-9a-f]{6}$/i.test(t)?t.toLowerCase():null;
const fx=v=>String(Math.round(v*10)/10);
const encodeSheets=sheets=>sheets.map(s=>`${idOf(s)}@${fx(s.x)},${fx(s.y)},${s.up==='inner'?'i':'o'},${s.show.toString(16)},${s.colour}`).join('|');
function decodeSheets(text,nodes){
 const out=[];
 for(const item of String(text||'').split('|')){
  const m=/^([^@|/~]+)(?:\/([AB]))?(?:~([1-9]\d?))?@(-?[\d.]+),(-?[\d.]+),([oi]),([0-9a-f]),([0-6]|[0-9a-fA-F]{6})$/.exec(item);
  if(!m)continue;
  const s={node:m[1],part:m[2]||'',copy:Number(m[3]||1)};
  // each copy of a sheet is on the table whole or as its leaves, once each
  if(!nodes.includes(s.node)||out.some(o=>sameCopy(o,s)&&(!s.part||!o.part||o.part===s.part))||out.length>=MAX_SHEETS)continue;
  const x=Number(m[4]),y=Number(m[5]);if(!Number.isFinite(x)||!Number.isFinite(y))continue;
  out.push({...s,x:Math.max(-LIMIT,Math.min(LIMIT,x)),y:Math.max(-LIMIT,Math.min(LIMIT,y)),up:m[6]==='i'?'inner':'outer',show:parseInt(m[7],16),colour:colourOfText(m[8])});
 }
 return out;
}
/* the first sheets on an empty table: the manuscript's first two bifolia side by side, outer faces up, every page shown */
const defaults=nodes=>nodes.slice(0,2).map((node,i)=>({node,part:'',copy:1,x:20+i*(2*LEAF[0]+20),y:20,up:'outer',show:ALL,colour:i+1}));
const pick=(v,list)=>list.includes(v)?v:list[0];
/* zoomOf(value) -> screen pixels a millimetre, any value in ZOOM_RANGE (the wheel's), to two decimals, else the default */
const zoomOf=v=>{const n=Number(v);return v!=null&&v!==''&&Number.isFinite(n)&&n>=ZOOM_RANGE[0]&&n<=ZOOM_RANGE[1]?String(Math.round(n*100)/100):ZOOMS[0];};
/* the colours of the outer and inner faces when pages are coloured by face: the first two sheet colours unless chosen */
const FACE_COLOURS=[1,2];
function faceColoursOf(text){
 const c=String(text||'').split(',').map(colourOfText);
 return c.length===2&&c.every(v=>v!==null)?c:[...FACE_COLOURS];
}
/* snapping is off unless asked for: a piece goes exactly where it is put */
function parse(h,nodes){
 const sheets=typeof h.sheets==='string'?decodeSheets(h.sheets,nodes):defaults(nodes);
 return {sheets,coords:pick(h.coords,COORDS),zoom:zoomOf(h.zoom),guides:h.guides!=='0',snap:h.snap==='1',colouring:pick(h.colour,COLOURINGS),faceColours:faceColoursOf(h.fc),
  words:h.words==='1',wdir:pick(h.wdir,WORD_DIRS)};
}
function serialize(s,nodes){
 const o={},text=encodeSheets(s.sheets),fc=(s.faceColours||FACE_COLOURS).join(',');
 if(text!==encodeSheets(defaults(nodes)))o.sheets=text;
 if(s.coords!==COORDS[0])o.coords=s.coords;if(s.zoom!==ZOOMS[0])o.zoom=s.zoom;if(!s.guides)o.guides='0';if(s.snap)o.snap='1';
 if(s.colouring!==COLOURINGS[0])o.colour=s.colouring;if(fc!==FACE_COLOURS.join(','))o.fc=fc;if(s.words)o.words='1';if(s.wdir&&s.wdir!==WORD_DIRS[0])o.wdir=s.wdir;
 return o;
}
/* snapTo(x, y, guides) -> the position that meets every guide (align's), one a direction */
const snapTo=(x,y,guides)=>guides.reduce((p,g)=>g.axis==='x'?{...p,x:p.x+g.off}:{...p,y:p.y+g.off},{x,y});
/* nextColour(sheets) -> the first of the six colours no sheet on the table has, else 0: a seventh sheet is drawn in ink, never in a seventh hue */
const nextColour=sheets=>{const used=new Set(sheets.map(s=>s.colour));for(let c=1;c<=COLOURS;c++)if(!used.has(c))return c;return 0;};
/* FACE_BITS: the show bits of each physical face's pages, outer Bv | Ar and inner Av | Br */
const FACE_BITS={outer:BIT.Bv|BIT.Ar,inner:BIT.Av|BIT.Br};
const api={LEAF,FOLD,SLOTS,FACE,BIT,FACE_BITS,ALL,RECTOS,VERSOS,COORDS,COLOURINGS,WORD_DIRS,ZOOMS,ZOOM_RANGE,COLOURS,FACE_COLOURS,MAX_SHEETS,ALIGN_MM,ALIGNED,PARTS,idOf,sameCopy,nextCopy,sheet,view,lines,align,snapTo,placed,relative,turn,divide,join,stack,spread,
 colourOfText,encodeSheets,decodeSheets,defaults,zoomOf,parse,serialize,nextColour};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VMS_SHEETS=api;
})(typeof window!=='undefined'?window:globalThis);
