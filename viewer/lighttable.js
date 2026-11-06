"use strict";
// The Light table: bifolia as open sheets on the parchment scale, or divided into their leaves, either face up, the face underneath seen through; the
// same bifolium or leaf as often as wanted. The board fills the window below a menu bar: drag on it to select, drag a selection to move it, drag with
// the right or middle button to pan, the wheel to zoom; a toolbar floats over the selection. The model, the guides and the address: js/sheet_math.js.
(async function(){
 const {$,esc}=SG,S=VMS_SHEETS,Z=COMPARE_STATE,W=VMS_WORDS;
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const button=(cls,text,title)=>{const b=h('button',cls,text);b.type='button';if(title)b.title=title;return b;};
 const table=$('table'),surface=$('surface'),list=$('list'),status=$('status'),notes=$('notes'),float=$('float'),marquee=$('marquee');
 let pages,sheets={},words,lines=[],lineOfToken=[],tokens=new Map(),nodes=[],state,order=[];
 // the selection, the ids of the pieces chosen; the camera, the table millimetre at the board's top left corner; busy while a piece or the selection
 // box is dragged
 let selection=new Set(),cam=[0,0],busy=false;
 const tags=document.createElement('div');tags.className='lt-tags';surface.append(tags);
 const loading=SG.busyStart('Loading the manuscript…');
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  const index=await SG.load(SG.dataUrl('index.json')),C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const info=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];
  const [compact,orders,bundle]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(info.path))]);
  if(!compact.paper)throw Error('These page records have no parchment data: rebuild them with `vmsspatial viewer-data`.');
  pages=compact.pages;sheets=compact.sheets||{};words=bundle.words;lines=bundle.lines||[];
  lineOfToken=new Int32Array(words.length).fill(-1);lines.forEach((L,i)=>{for(let t=L.start;t<L.end;t++)lineOfToken[t]=i;});
  tokens=new Map(lines.map(L=>[L.page+'|'+L.locus,L.end-L.start]));
  for(const f of Z.pageList(orders,'bifolia',pages))if(!nodes.includes(pages[f].node))nodes.push(pages[f].node);
 }catch(error){loading.end();status.textContent='Could not load the page data.';fit();SG.error(table,error);return;}
 state=S.parse(SG.hash(),nodes);order=state.sheets.map(S.idOf);
 const save=()=>SG.setHash({data:SG.hash().data,...S.serialize(state,nodes)});
 const css=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
 // a colour (sheet_math.js): one of the six sheet colours, 0 ink, or six hex digits chosen with the picker
 const hexOf=c=>typeof c==='string'?'#'+c:null;
 const colourOf=c=>hexOf(c)||(c?css('--hl-'+c):css('--ink2')),colourVar=c=>hexOf(c)||(c?`var(--hl-${c})`:'var(--ink2)');
 const zoom=()=>Number(state.zoom),signed=v=>(v>0.05?'+':v<-0.05?'−':'')+Math.abs(v).toFixed(1);
 const sectionOf=node=>{const f=Object.keys(pages).find(k=>pages[k].node===node);return f?pages[f].section:'';};
 // a leaf's folio number, from its pages: leaf A of A:1-8 is f1, leaf B is f8
 const leafNo=(node,part)=>{const f=Object.keys(pages).find(k=>pages[k].node===node&&S.PARTS[part].includes(pages[k].slot));return f?pages[f].leaf:null;};
 const nameOf=s=>(s.part?`f${leafNo(s.node,s.part)} · `:'')+s.node+((s.copy||1)>1?` (${s.copy})`:'');
 const faceName=s=>{if(!s.part)return s.up==='outer'?'Outer face up':'Inner face up';const slot=S.PARTS[s.part].find(x=>(S.FACE[x]===s.up));return S.RECTOS.includes(slot)?'Recto up':'Verso up';};
 const find=id=>state.sheets.find(s=>S.idOf(s)===id),chosen=()=>state.sheets.filter(s=>selection.has(S.idOf(s)));
 // ---- the pieces' geometry, kept until the coordinates change
 const models=new Map(),els=new Map();
 const modelOf=s=>{const key=s.node+'|'+state.coords;if(!models.has(key))models.set(key,S.sheet(s.node,pages,{coords:state.coords,sheets,tokens}));return models.get(key);};
 // which pages a piece draws: its own choice, and the View menu's visible face and face underneath; with both faces shown, nothing behind
 const viewOf=s=>S.view(modelOf(s),s.up,s.show,s.part,{up:state.faceUp,behind:state.underneath&&!s.twin});
 const other=up=>up==='outer'?'inner':'outer',pairOf=s=>s.twin?S.pair(modelOf(s),s,{up:state.faceUp}):null;
 // a piece's own frame: its view's box, and with both faces shown its other face's beside it
 function frameOf(s){const b=viewOf(s).box,p=pairOf(s);if(!p)return b;const t=p.twin.box;return [Math.min(b[0],t[0]+p.dx),Math.min(b[1],t[1]),Math.max(b[2],t[2]+p.dx),Math.max(b[3],t[3])];}
 const boxOf=s=>{const b=frameOf(s);return [s.x+b[0],s.y+b[1],s.x+b[2],s.y+b[3]];};
 const union=list=>list.reduce((a,r)=>[Math.min(a[0],r[0]),Math.min(a[1],r[1]),Math.max(a[2],r[2]),Math.max(a[3],r[3])]);
 // the lines a piece lines up by: its own, and its other face's where it is shown
 const linesOf=s=>{const l=S.lines(viewOf(s)),p=pairOf(s);if(!p)return l;return {xs:[...l.xs,...S.lines(p.twin).xs.map(x=>x+p.dx)],ys:l.ys};};
 function element(s){
  const id=S.idOf(s);if(els.has(id))return els.get(id);
  // the selection's outline lies on the leaves' own edge (paint), not round the canvas, which also holds any text past them
  // its face up, and its other face beside it when both are shown, each a canvas with its outline
  const el=h('div','lt-sheet');el.tabIndex=0;el.dataset.id=id;el.append(h('canvas'),h('div','lt-selbox'),h('canvas','lt-twin'),h('div','lt-selbox lt-twin'));surface.append(el);els.set(id,el);
  // the keyboard's way in: a piece reached with Tab is selected
  el.addEventListener('focus',()=>{if(!busy&&!selection.has(id))setSelection([id]);});
  return el;
 }
 function position(s){
  const id=S.idOf(s),el=element(s),f=frameOf(s),z=zoom();
  Object.assign(el.style,{left:(s.x+f[0])*z+'px',top:(s.y+f[1])*z+'px',width:(f[2]-f[0])*z+'px',height:(f[3]-f[1])*z+'px'});el.style.zIndex=String(1+order.indexOf(id));el.style.opacity=String(s.opacity??1);
  el.classList.toggle('selected',selection.has(id));layoutTags();
  el.setAttribute('aria-label',`${nameOf(s)}, ${faceName(s).toLowerCase()}, fold edge ${(s.x+S.FOLD).toFixed(1)} mm, top ${s.y.toFixed(1)} mm`);
 }
 // the camera moves the surface the pieces lie on; the selection's toolbar follows
 function applyCamera(){const z=zoom();surface.style.transform=`translate(${-cam[0]*z}px,${-cam[1]*z}px)`;placeFloat();}
 // the table fills the window below the menu bar
 function fit(){table.style.height=Math.max(240,innerHeight-table.getBoundingClientRect().top)+'px';}
 // a piece: its face up, and with both faces shown its other face to the right, linked
 function paint(s){
  const el=element(s),[c1,o1,c2,o2]=el.children,p=pairOf(s),f=frameOf(s);
  el.classList.toggle('paired',!!p);
  let turned=draw(s,c1,o1,viewOf(s),s.up,0,f);
  if(p)turned=draw(s,c2,o2,p.twin,other(s.up),p.dx,f)||turned;
  if(state.words&&turned)turnedOn.add(S.idOf(s));else turnedOn.delete(S.idOf(s));
  $('wdirLabel').hidden=!turnedOn.size;
  position(s);
 }
 // one view of a piece in millimetres, on canvas c at dx in the piece's frame f: its leaves, the folds, the face underneath in outline and the face
 // up filled, each at the View menu's opacity; o, the selection's outline, on the face-up leaves' edge. Returns whether it wrote turned words
 function draw(s,c,o,v,up,dx,f){
  const z=zoom(),[bx,by,bx1,by1]=v.box,dpr=Math.min(2,devicePixelRatio||1),w=Math.ceil((bx1-bx)*z),ht=Math.ceil((by1-by)*z);
  c.width=Math.ceil(w*dpr);c.height=Math.ceil(ht*dpr);Object.assign(c.style,{width:w+'px',height:ht+'px',left:(bx+dx-f[0])*z+'px',top:(by-f[1])*z+'px'});
  const g=c.getContext('2d'),col=colourOf(s.colour),px=1/z,same=(a,b)=>a.every((x,i)=>Math.abs(x-b[i])<.01),O=state.opacity,dim=state.dim?S.DIM:1;
  // by face, the pages of a sheet's outer face take the outer face's colour and those of its inner face the inner's, wherever the piece lies and
  // whichever side is up; the outlines go to ink, and the label squares keep the piece's own colour
  const byFace=state.colouring==='face',faces=state.faceColours.map(colourOf),tone=l=>byFace?faces[l.face==='outer'?0:1]:col,lead=byFace?css('--ink2'):col;
  g.setTransform(dpr*z,0,0,dpr*z,-bx*dpr*z,-by*dpr*z);
  const front=v.leaves.filter(l=>l.front),back=v.leaves.filter(l=>!l.front),H=v.height,cells=front.flatMap(l=>l.cells);
  // the outline round its face-up leaves (the nominal leaf when it has none), every fold and crease between two panels dashed, a panel underneath
  // that sticks out dotted
  g.lineWidth=px;g.strokeStyle=lead;
  const edge=cells.length?cells.reduce((e,c)=>[Math.min(e[0],c[0]),0,Math.max(e[2],c[2]),H],[Infinity,0,-Infinity,H]):[bx,0,bx1,H];
  for(const [x0,y0,x1,y1] of cells){g.globalAlpha=.07*O.paper;g.fillStyle=lead;g.fillRect(x0,y0,x1-x0,y1-y0);}
  g.globalAlpha=.9;g.strokeRect(edge[0],0,edge[2]-edge[0],H);
  const inside=(v0,lo,hi)=>v0>lo+.01&&v0<hi-.01,folds=new Set([...(inside(v.fold,edge[0],edge[2])?[v.fold]:[]),...cells.flatMap(c=>[c[0],c[2]]).filter(x=>inside(x,edge[0],edge[2]))]);
  const creases=new Set(cells.flatMap(c=>[c[1],c[3]]).filter(y=>inside(y,0,H)));
  g.setLineDash([5*px,4*px]);g.globalAlpha=.8;g.beginPath();for(const x of folds){g.moveTo(x,0);g.lineTo(x,H);}for(const y of creases){g.moveTo(edge[0],y);g.lineTo(edge[2],y);}g.stroke();
  g.setLineDash([2*px,3*px]);g.globalAlpha=.6;
  for(const l of back)for(const c of l.cells)if(!cells.some(f=>same(f,c))){const [x0,y0,x1,y1]=c;g.strokeRect(x0,y0,x1-x0,y1-y0);}
  g.setLineDash([]);
  g.lineWidth=Math.max(.9*px,.2);
  // with the words written, the boxes step back so the spellings read, the face underneath further than the face up
  const outlined=(state.words?.45:.8)*O.under*dim,filled=(state.words?.35:.6)*O.boxes*dim;
  if(outlined>0)for(const l of back)if(l.shown){g.globalAlpha=outlined;g.strokeStyle=tone(l);for(const {rect:[x0,y0,x1,y1]} of l.words)g.strokeRect(x0,y0,x1-x0,y1-y0);}
  if(filled>0)for(const l of front)if(l.shown){g.globalAlpha=filled;g.fillStyle=tone(l);for(const {rect:[x0,y0,x1,y1]} of l.words)g.fillRect(x0,y0,x1-x0,y1-y0);}
  const turned=state.words&&spell(g,v,z);
  marks(g,v,px,tone,O);
  // labels in ink, each after a square of its page's colour (the piece's, or by face its face's), on a row of their own for each piece, so pieces
  // stacked on one another keep theirs apart: the pages' names (Page names), and the sheet's on it (Sheet names: on the sheet)
  const row=(state.sheets.indexOf(s)%8)*13*px,label=(text,x,y,ink,mark)=>{g.globalAlpha=1;g.fillStyle=mark;g.fillRect(x,y-7*px,6*px,6*px);g.fillStyle=css(ink);g.fillText(text,x+9*px,y);};
  g.font=`${11*px}px system-ui,sans-serif`;g.textBaseline='middle';
  if(state.pageLabel==='corner'){
   for(const l of front){label(l.name||l.folio,l.leaf[0]+3*px,l.leaf[1]+9*px+row,'--ink',tone(l));if(l.turned){g.fillStyle=css('--ink2');g.fillText('upside down',l.leaf[0]+12*px,l.leaf[1]+21*px+row);}}
   for(const l of back)if(l.shown)label(`(${l.name||l.folio} behind)`,l.leaf[0]+3*px,l.leaf[3]-8*px-row,'--ink2',tone(l));
  }
  if(state.sheetLabel==='inside'){g.globalAlpha=1;g.fillStyle=css('--ink2');g.textAlign='right';g.fillText(`${labelName(s)} · ${faceName({...s,up}).toLowerCase()}`,edge[2]-3*px,9*px+row);g.textAlign='start';}
  Object.assign(o.style,{left:(edge[0]+dx-f[0])*z+'px',top:-f[1]*z+'px',width:(edge[2]-edge[0])*z+'px',height:H*z+'px'});
  return turned;
 }
 // ---- the sheets' names above them (Sheet names: above it): a tag for each face shown, over its face-up leaves' edge. Each goes where it covers
 // the fewest pages and no other tag: over the sheet, side by side along its width and then in rows upwards, else under it. They are placed
 // in the pieces' own order, which choosing one does not change, so a tag stays put under the pointer that clicks it
 const edgeOf=v=>{const cells=v.leaves.filter(l=>l.front).flatMap(l=>l.cells);return cells.length?[Math.min(...cells.map(c=>c[0])),0,Math.max(...cells.map(c=>c[2])),v.height||S.LEAF[1]]:[v.box[0],0,v.box[2],v.height||S.LEAF[1]];};
 function facesOf(s){
  const p=pairOf(s),out=[{v:viewOf(s),up:s.up,dx:0},...(p?[{v:p.twin,up:other(s.up),dx:p.dx}]:[])];
  return out.map(f=>{const e=edgeOf(f.v);return {...f,edge:[s.x+f.dx+e[0],s.y+e[1],s.x+f.dx+e[2],s.y+e[3]]};});
 }
 // a piece's name on the table: without its copy number when Copy numbers is off
 const labelName=s=>state.copyNumbers?nameOf(s):nameOf({...s,copy:1});
 const shortFace=(s,up)=>{const n=faceName({...s,up}).toLowerCase();return s.part?n.replace(/ up$/,''):n.replace(/ face up$/,'');};
 let tagFrame=0;
 const layoutTags=()=>{if(!tagFrame)tagFrame=requestAnimationFrame(()=>{tagFrame=0;placeTags();});};
 // the angles' values (Values) go in the same layer, each beside an end of its own line, where it covers no tag and no other value: past the right
 // end, else before the left, a line higher or lower where those are taken. Its true angle, after a square of its page's colour
 const toneOf=(s,l)=>state.colouring==='face'?colourVar(state.faceColours[l.face==='outer'?0:1]):colourVar(s.colour);
 function placeTags(){
  tags.replaceChildren();
  const above=state.sheetLabel==='above'&&state.sheets.length,values=state.angle&&state.angleValues&&state.opacity.angles>0,pagesAbove=state.pageLabel==='above'&&state.sheets.length;
  if(!above&&!values&&!pagesAbove)return placeFloat();
  const z=zoom(),byFace=state.colouring==='face',items=[],cover=(a,b)=>Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
  for(const s of state.sheets)for(const f of facesOf(s))items.push({s,f,r:f.edge.map(v=>v*z)});
  const sheetsAt=items.map(it=>it.r);
  const placed=[],GAP=4,STEP=3;
  // a tag, over the rectangle r (screen pixels on the surface) or under it
  const tag=(s,r,text,colour,title,cls='')=>{
   const id=S.idOf(s),el=h('div','lt-tag'+cls+(selection.has(id)?' selected':'')),chip=h('i');el.dataset.id=id;chip.style.background=colour;el.title=title;
   el.append(chip,text);tags.append(el);
   const w=el.offsetWidth,ht=el.offsetHeight,[x0,y0,x1,y1]=r,cols=Math.max(1,Math.floor((x1-x0+STEP)/(w+STEP)));
   let best=null;
   // along its width first, then past its right edge, up to six rows over it or under it; a spot that covers nothing wins over a nearer one
   for(const below of [false,true])for(let k=0;k<6;k++)for(let j=0;j<Math.min(cols+4,14);j++){
    const x=x0+j*(w+STEP),y=below?y1+GAP+k*(ht+STEP):y0-GAP-ht-k*(ht+STEP),r=[x,y,x+w,y+ht];
    let cost=k*3+j+(j>=cols?6:0)+(below?20:0);
    for(const q of placed)cost+=cover(r,q)*100;
    for(const q of sheetsAt)cost+=cover(r,q);
    if(!best||cost<best.cost)best={cost,r};
   }
   placed.push(best.r);el.style.left=best.r[0]+'px';el.style.top=best.r[1]+'px';
  };
  // the pages' names over their own leaves, nearest them, then the sheets' over the faces
  if(pagesAbove)for(const {s,f} of items)for(const l of f.v.leaves.filter(l=>l.front)){
   const r=[(s.x+f.dx+l.leaf[0])*z,(s.y+l.leaf[1])*z,(s.x+f.dx+l.leaf[2])*z,(s.y+l.leaf[3])*z],name=l.name||l.folio;
   tag(s,r,name,toneOf(s,l),`${name}, on ${labelName(s)} · ${shortFace(s,f.up)}: click to select, drag to move`,' page');
  }
  if(above)for(const it of items)tag(it.s,it.r,`${labelName(it.s)} · ${shortFace(it.s,it.f.up)}`,byFace?colourVar(state.faceColours[it.f.up==='outer'?0:1]):colourVar(it.s.colour),
   `${nameOf(it.s)}, ${faceName({...it.s,up:it.f.up}).toLowerCase()}: click to select, drag to move`);
  if(values)for(const {s,f} of items)for(const l of f.v.leaves){
   const line=l.shown&&S.tiltLine(l,{coords:state.coords,at:state.angleAt,length:state.angleLength,scale:state.angleScale});if(!line)continue;
   const [a,b]=line.ends.map(([x,y])=>[(s.x+f.dx+x)*z,(s.y+y)*z]),el=h('div','lt-val'+(l.front?'':' behind')),chip=h('i');
   chip.style.background=toneOf(s,l);el.append(chip,deg(line.angle));el.style.opacity=String(Math.min(1,state.opacity.angles));tags.append(el);
   const w=el.offsetWidth,ht=el.offsetHeight;let best=null;
   for(const [end,left,pen] of [[b,false,0],[a,true,4]])for(const k of [0,-1,1,-2,2,-3,3]){
    const x=left?end[0]-5-w:end[0]+5,y=end[1]-ht/2+k*(ht+1),r=[x,y,x+w,y+ht];
    let cost=pen+Math.abs(k)*2;for(const q of placed)cost+=cover(r,q)*100;
    if(!best||cost<best.cost)best={cost,r};
   }
   placed.push(best.r);el.style.left=best.r[0]+'px';el.style.top=best.r[1]+'px';
  }
  placeFloat();
 }
 // the margins and the text angle of every page shown, in its colour over a halo of the table's, so they read over the words; behind, dashed
 const deg=a=>(a>=0?'+':'−')+Math.abs(a).toFixed(2)+'°';
 function marks(g,v,px,tone,O){
  const halo=css('--surface'),stroke=(draw,col,width,dash)=>{g.setLineDash([]);g.strokeStyle=halo;g.lineWidth=width+2*px;g.beginPath();draw();g.stroke();g.setLineDash(dash);g.strokeStyle=col;g.lineWidth=width;g.beginPath();draw();g.stroke();g.setLineDash([]);};
  for(const l of v.leaves)if(l.shown){
   const col=tone(l),dash=l.front?[]:[4*px,3*px],base=l.front?1:.75;
   // the lines as plotted: through each word's baseline point, solid where the angle is measured on them, true to their slope
   if(state.lines&&O.lines>0){
    g.globalAlpha=base*O.lines;g.strokeStyle=col;g.lineWidth=1.1*px;
    for(const b of l.lines){g.setLineDash(l.front&&b.counted?[]:[1.5*px,2.5*px]);g.beginPath();b.points.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.stroke();}
    g.setLineDash([]);
   }
   // a line joins only consecutive rows, so a gap stays a gap
   g.globalAlpha=base*O.margins;
   if(state.margins&&O.margins>0)for(const rows of [l.margins.left,l.margins.right]){
    stroke(()=>{for(let i=1;i<rows.length;i++)if(rows[i].line===rows[i-1].line+1){g.moveTo(...rows[i-1].at);g.lineTo(...rows[i].at);}},col,1.4*px,dash);
    for(const r of rows){g.beginPath();g.arc(r.at[0],r.at[1],2.2*px,0,2*Math.PI);g.fillStyle=l.front?col:halo;g.fill();g.strokeStyle=col;g.lineWidth=px;g.stroke();}
   }
   // the text's angle solid, the level dotted, as long and through the same point: the text's centroid or the page's middle, as wide as the text
   // or of one length (View). The angle is the lines' as drawn: after flattening in flat coordinates, as written in recorded ones. Its value is
   // written with the sheets' tags (placeTags), clear of the others
   const line=state.angle&&O.angles>0&&S.tiltLine(l,{coords:state.coords,at:state.angleAt,length:state.angleLength,scale:state.angleScale});
   if(line){
    g.globalAlpha=base*O.angles;
    const [a,b]=line.ends,c=[(a[0]+b[0])/2,(a[1]+b[1])/2],half=Math.hypot(b[0]-a[0],b[1]-a[1])/2;
    g.strokeStyle=css('--ink2');g.lineWidth=px;g.setLineDash([2*px,3*px]);g.beginPath();g.moveTo(c[0]-half,c[1]);g.lineTo(c[0]+half,c[1]);g.stroke();g.setLineDash([]);
    stroke(()=>{g.moveTo(...a);g.lineTo(...b);},col,2*px,dash);
    g.beginPath();g.arc(c[0],c[1],2.5*px,0,2*Math.PI);g.fillStyle=col;g.fill();
   }
  }
  g.globalAlpha=1;
 }
 // each word's EVA spelling once it is at least MIN_TEXT screen pixels tall, the face underneath's the right way round. Level text goes in its box, at
 // most its width. A ring's or a turned line's words, and those of a panel written upside down, go along the writing, or upright with Word
 // direction Level, one size for the page, sized by their length along it (js/word_labels.js); behind, mirrored, they turn the other way. Returns
 // whether any such word is shown
 const MIN_TEXT=7,textOf=(folio,id)=>{const u=pages[folio].units[id];return words.slice(u[0],u[1]+1).join(' ');};
 // each word's direction on its page, from its line's orientation record: 0 level, null turned but which way unknown
 const angles=new Map(),turnedOn=new Set();
 const anglesOf=folio=>{if(!angles.has(folio))angles.set(folio,pages[folio].units.map(u=>{const L=lines[lineOfToken[u[0]]];return L?W.angleOf(L.orientation,u[0]-L.start):0;}));return angles.get(folio);};
 function spell(g,v,z){
  const mono=css('--mono')||'monospace';let turned=false;g.textBaseline='middle';
  for(const l of v.leaves)if(l.shown){
   // a word's direction on the table: on an upside-down panel turned half way round, behind (mirrored) the other way
   const a=anglesOf(l.folio),round=[],dir=w=>{let t=a[w.id];if(t==null)return null;if(l.turned)t+=t>0?-180:180;return l.front?t:-t;};
   g.globalAlpha=1;g.fillStyle=css(l.front?'--ink':'--ink2');g.textAlign='left';
   for(const w of l.words){
    const t=dir(w);if(t!==0){round.push({rect:w.rect.map(v=>v*z),text:textOf(l.folio,w.id),angle:t});continue;}
    const [x0,y0,x1,y1]=w.rect,size=(y1-y0)*.72;if(size*z<MIN_TEXT)continue;
    g.font=`${size}px ${mono}`;g.fillText(textOf(l.folio,w.id),x0+.3,(y0+y1)/2,Math.max(.5,x1-x0-.6));
   }
   if(!round.length)continue;
   // laid out in screen pixels, as on the Atlas
   turned=true;g.textAlign='center';
   W.layout(round,state.wdir).forEach((f,k)=>{
    if(f.size<MIN_TEXT)return;
    g.save();g.translate(f.x/z,f.y/z);if(f.angle)g.rotate(f.angle*Math.PI/180);g.font=`${f.size/z}px ${mono}`;g.fillText(round[k].text,0,0);g.restore();
   });
  }
  g.textAlign='start';return turned;
 }
 // ---- the pieces' rows (Pieces), and which of a piece's pages are drawn
 function where(s){const ref=state.sheets[0];if(!ref||ref===s)return 'reference';const r=S.relative(s,ref);return `fold edge ${signed(r.fold)} mm, top ${signed(r.top)} mm from ${nameOf(ref)}`;}
 // a piece's pages, by face: a box for a whole face of a sheet, and one a page; changed() after each change
 function pageBoxes(s,changed){
  const box=h('span','lt-pages'),m=modelOf(s),mine=x=>!s.part||S.PARTS[s.part].includes(x);
  for(const f of [s.up,s.up==='outer'?'inner':'outer']){
   const group=h('span','face'),present=S.SLOTS.filter(x=>S.FACE[x]===f&&mine(x)&&m.leaves.some(l=>l.slot===x)),bits=present.reduce((b,x)=>b|S.BIT[x],0);
   if(!s.part&&bits){
    const all=h('label','lt-facecheck'),cb=h('input');cb.type='checkbox';cb.checked=(s.show&bits)===bits;cb.indeterminate=!cb.checked&&!!(s.show&bits);
    cb.onchange=()=>{s.show=cb.checked?s.show|bits:s.show&~bits;paint(s);changed();};
    all.title=`Show or hide every page of its ${f} face`;all.append(cb,f==='outer'?'Outer':'Inner');group.append(all);
   }
   for(const slot of present){
    const leaves=m.leaves.filter(l=>l.slot===slot),label=h('label'),cb=h('input');cb.type='checkbox';cb.checked=!!(s.show&S.BIT[slot]);
    cb.onchange=()=>{s.show^=S.BIT[slot];paint(s);changed();};
    const named=l=>l.name||l.folio;label.title=leaves.map(named).join(', ');label.append(cb,named(leaves[0])+(leaves.length>1?` +${leaves.length-1}`:''));group.append(label);
   }
   if(group.querySelector('label'))box.append(group);
  }
  return box;
 }
 function fillList(){
  list.replaceChildren();$('piecesEmpty').hidden=!!state.sheets.length;$('piecesBtn').textContent=`Pieces · ${state.sheets.length}`;
  for(const s of state.sheets){
   const id=S.idOf(s),row=h('div','lt-row'+(selection.has(id)?' selected':'')),name=button('lt-name',nameOf(s),sectionOf(s.node)),face=button('lt-face',faceName(s));
   const at=h('span','lt-where',where(s)),cut=button('lt-cut',s.part?'Join':'Divide'),remove=button('lt-remove','×'),swatch=button('lt-swatch','','Choose its colour');
   row.style.setProperty('--sheet',colourVar(s.colour));row.dataset.id=id;remove.setAttribute('aria-label','Remove '+nameOf(s));
   swatch.setAttribute('aria-label','Colour of '+nameOf(s));swatch.setAttribute('aria-haspopup','dialog');swatch.onclick=()=>pickColour(swatch,s.colour,c=>recolour([s],c));
   face.title=s.part?'Turn the leaf over where it lies (F)':'Turn the sheet over about its fold (F)';cut.title=s.part?'Join with its other leaf into the whole sheet (D)':'Divide into its two leaves (D)';
   name.onclick=()=>{setSelection([id]);centreOn([s]);};
   face.onclick=()=>turnOver([s]);cut.onclick=()=>cutOrJoin([s]);remove.onclick=()=>removePieces([s]);
   row.append(swatch,name,face,pageBoxes(s,changedPages),at,cut,remove);list.append(row);
  }
 }
 const changedPages=()=>{fillList();syncChecks();describe();save();if(!$('pagesPop').hidden&&pagesFor)openPages(pagesAnchor,pagesFor,true);};
 const markRows=()=>{for(const row of list.children)row.classList.toggle('selected',selection.has(row.dataset.id));};
 const updateWhere=()=>{for(const row of list.children){const s=find(row.dataset.id);if(s)row.querySelector('.lt-where').textContent=where(s);}};
 // ---- choosing a colour: the six sheet colours and ink, or any with the picker; apply(colour) as it changes
 const PRESETS=[[1,'Blue'],[2,'Orange'],[3,'Green'],[4,'Amber'],[5,'Pink'],[6,'Deep green'],[0,'Ink']],pop=$('colourPop'),picker=$('customColour');
 let applyColour=null,popAnchor=null;
 $('presets').replaceChildren(...PRESETS.map(([c,name])=>{const b=button('lt-preset','',name);b.dataset.colour=String(c);b.setAttribute('aria-label',name);b.style.setProperty('--sheet',colourVar(c));b.onclick=()=>{applyColour?.(c);closeColour();};return b;}));
 const asHex=v=>/^#[0-9a-f]{6}$/i.test(v)?v.toLowerCase():'#808080';
 const placePop=(el,anchor)=>{const r=anchor.getBoundingClientRect(),w=el.offsetWidth,ht=el.offsetHeight;el.style.left=Math.max(8,Math.min(innerWidth-w-8,r.left))+'px';el.style.top=(r.bottom+6+ht>innerHeight?Math.max(8,r.top-6-ht):r.bottom+6)+'px';};
 function pickColour(anchor,current,apply){
  if(popAnchor===anchor&&!pop.hidden)return closeColour();
  closePages();applyColour=apply;popAnchor=anchor;
  for(const b of pop.querySelectorAll('.lt-preset'))b.setAttribute('aria-pressed',String(b.dataset.colour===String(current)));
  picker.value=asHex(colourOf(current));pop.hidden=false;anchor.setAttribute('aria-expanded','true');placePop(pop,anchor);
  (pop.querySelector('[aria-pressed="true"]')||pop.querySelector('button')).focus();
 }
 function closeColour(){if(pop.hidden)return;pop.hidden=true;popAnchor?.setAttribute('aria-expanded','false');if(popAnchor?.isConnected)popAnchor.focus({preventScroll:true});applyColour=popAnchor=null;}
 picker.addEventListener('input',()=>applyColour?.(picker.value.slice(1).toLowerCase()));
 // both leaves of a sheet keep one colour
 function recolour(list,c){
  for(const s of list)for(const p of state.sheets)if(S.sameCopy(p,s)){p.colour=c;paint(p);}
  for(const r of $('list').children){const q=find(r.dataset.id);if(q)r.style.setProperty('--sheet',colourVar(q.colour));}
  const sw=float.querySelector('.lt-swatch');if(sw&&list[0])sw.style.setProperty('--sheet',colourVar(list[0].colour));save();
 }
 const faceChips=()=>{$('faceOuter').style.setProperty('--sheet',colourVar(state.faceColours[0]));$('faceInner').style.setProperty('--sheet',colourVar(state.faceColours[1]));};
 [['faceOuter',0],['faceInner',1]].forEach(([id,k])=>$(id).onclick=()=>pickColour($(id),state.faceColours[k],c=>{state.faceColours[k]=c;faceChips();for(const s of state.sheets)paint(s);save();}));
 // ---- a piece's pages, from the selection's toolbar
 const pagesPop=$('pagesPop');let pagesFor=null,pagesAnchor=null;
 function openPages(anchor,s,keep){
  if(!keep&&pagesAnchor===anchor&&!pagesPop.hidden)return closePages();
  closeColour();pagesFor=s;pagesAnchor=anchor;pagesPop.replaceChildren(pageBoxes(s,changedPages));pagesPop.hidden=false;anchor.setAttribute('aria-expanded','true');placePop(pagesPop,anchor);
 }
 function closePages(){if(pagesPop.hidden)return;pagesPop.hidden=true;pagesAnchor?.setAttribute('aria-expanded','false');pagesFor=pagesAnchor=null;}
 // ---- the menu bar: Add sheet, Edit, View, Pieces and Help open their panels under them; one at a time
 const MENUS=[['addBtn','addPanel'],['editBtn','editMenu'],['viewBtn','viewMenu'],['piecesBtn','piecesPanel'],['helpBtn','helpPanel']];
 const openMenu=()=>MENUS.find(([,p])=>!$(p).hidden);
 function closeMenus(){for(const [b,p] of MENUS){$(p).hidden=true;$(b).setAttribute('aria-expanded','false');}}
 function toggleMenu(id){
  const [b,p]=MENUS.find(([x])=>x===id),open=$(p).hidden;closeMenus();closeColour();closePages();
  if(!open)return;
  $(p).hidden=false;$(b).setAttribute('aria-expanded','true');
  if(p==='addPanel'){fillAdd();$('addSearch').focus();$('addSearch').select();}
  if(p==='editMenu'){updateEdit();$('editMenu').querySelector('button:not(:disabled)')?.focus();}
  if(p==='piecesPanel')fillList();
 }
 for(const [b] of MENUS)$(b).onclick=()=>toggleMenu(b);
 // up and down move through a menu's items
 $('editMenu').addEventListener('keydown',e=>{
  if(e.key!=='ArrowDown'&&e.key!=='ArrowUp')return;e.preventDefault();
  const items=[...$('editMenu').querySelectorAll('button:not(:disabled),input')],i=items.indexOf(document.activeElement);
  items[(i+(e.key==='ArrowDown'?1:items.length-1))%items.length]?.focus();
 });
 addEventListener('pointerdown',e=>{
  const t=e.target;
  if(openMenu()&&!t.closest('.lt-wrap')&&!t.closest('.lt-pop'))closeMenus();
  if(!pop.hidden&&!pop.contains(t)&&t!==popAnchor&&!popAnchor?.contains(t)){pop.hidden=true;popAnchor?.setAttribute('aria-expanded','false');applyColour=popAnchor=null;}
  if(!pagesPop.hidden&&!pagesPop.contains(t)&&t!==pagesAnchor&&!pagesAnchor?.contains(t))closePages();
 },true);
 // ---- Add sheet: every bifolium, searched by its name, its section or its folios; its name adds the sheet, a folio that leaf alone
 const addRows=nodes.map(node=>{
  const row=h('div','lt-addrow'),sheet=button('sheet','',`Add ${node} as a whole sheet`);sheet.append(node,h('span','',sectionOf(node)));
  sheet.onclick=()=>{closeMenus();addPiece(node,'');};row.append(sheet);
  for(const part of ['A','B']){const n=leafNo(node,part);if(!n)continue;const b=button('leaf',`f${n}`,`Add leaf ${part} of ${node} alone: f${n}r and f${n}v`);b.onclick=()=>{closeMenus();addPiece(node,part);};row.append(b);}
  $('addList').append(row);
  return {row,node,hay:[node,sectionOf(node),...Object.keys(pages).filter(f=>pages[f].node===node)].join(' ').toLowerCase()};
 });
 function fillAdd(){
  const q=$('addSearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean),full=state.sheets.length>=S.MAX_SHEETS;let n=0;
  for(const r of addRows){const hit=q.every(w=>r.hay.includes(w));r.row.hidden=!hit;if(hit)n++;for(const b of r.row.querySelectorAll('button'))b.disabled=full;}
  $('addHint').textContent=full?`The table holds ${S.MAX_SHEETS} pieces at most: remove one to add another.`:n?(q.length?`${n} of ${nodes.length} bifolia. `:'')+"A bifolium's name adds the whole sheet; a folio adds that leaf alone.":'No bifolium matches.';
 }
 $('addSearch').addEventListener('input',fillAdd);
 $('addSearch').addEventListener('keydown',e=>{
  const first=addRows.find(r=>!r.row.hidden);
  if(e.key==='Enter'&&first){e.preventDefault();first.row.querySelector('.sheet').click();}
  else if(e.key==='ArrowDown'&&first){e.preventDefault();first.row.querySelector('.sheet').focus();}
 });
 $('addList').addEventListener('keydown',e=>{
  if(e.key!=='ArrowDown'&&e.key!=='ArrowUp')return;e.preventDefault();
  const items=addRows.filter(r=>!r.row.hidden).flatMap(r=>[...r.row.querySelectorAll('button')]),i=items.indexOf(document.activeElement);
  if(e.key==='ArrowUp'&&i<=0)return $('addSearch').focus();
  items[Math.min(items.length-1,i+(e.key==='ArrowDown'?1:-1))]?.focus();
 });
 // a new piece goes beside the last one, or on a new row, and comes into view; a leaf whose other leaf is on the table alone joins that copy, in
 // its colour
 function addPiece(node,part){
  if(!node||state.sheets.length>=S.MAX_SHEETS)return;
  const mate=part&&state.sheets.find(p=>p.node===node&&p.part&&p.part!==part&&!state.sheets.some(q=>q!==p&&q.node===node&&(q.copy||1)===(p.copy||1)));
  const s={node,part,copy:mate?mate.copy||1:S.nextCopy(state.sheets,node),x:0,y:0,up:'outer',show:S.ALL,colour:mate?mate.colour:S.nextColour(state.sheets),opacity:1},b=viewOf(s).box;
  if(!state.sheets.length){s.x=cam[0]+20-b[0];s.y=cam[1]+20-b[1];}
  else{
   const last=state.sheets[state.sheets.length-1],lb=boxOf(last),room=cam[0]+table.clientWidth/zoom();
   let bottom=-Infinity;for(const o of state.sheets)bottom=Math.max(bottom,boxOf(o)[3]);
   if(lb[2]+20+(b[2]-b[0])<=room){s.x=lb[2]+20-b[0];s.y=last.y;}else{s.x=cam[0]+20-b[0];s.y=bottom+20-b[1];}
  }
  state.sheets.push(s);render();setSelection([S.idOf(s)]);inView([s]);
 }
 // ---- choosing: a click, Shift-click, a box drawn on the empty table, Select all; the chosen come to the top of the stack
 function setSelection(ids,{front=true}={}){
  selection=new Set(ids.filter(id=>find(id)));
  if(front)order=[...order.filter(x=>!selection.has(x)),...order.filter(x=>selection.has(x))];
  for(const s of state.sheets)position(s);
  markRows();buildFloat();placeFloat();updateEdit();
 }
 function deselect(){setSelection([],{front:false});if(document.activeElement?.closest?.('.lt-sheet'))document.activeElement.blur();}
 // ---- the selection's toolbar: name, colour, opacity, turn over, divide or join, pages, remove
 function buildFloat(){
  const sel=chosen();float.replaceChildren();if(!sel.length)return;
  const one=sel.length===1?sel[0]:null,sep=()=>h('span','lt-sep');
  float.append(h('span','lt-fname',one?`${nameOf(one)} · ${faceName(one).toLowerCase()}`:`${sel.length} pieces`));
  const swatch=button('lt-swatch','','Colour');swatch.style.setProperty('--sheet',colourVar(sel[0].colour));swatch.setAttribute('aria-label','Colour');swatch.setAttribute('aria-haspopup','dialog');
  swatch.onclick=()=>pickColour(swatch,sel[0].colour,c=>recolour(chosen(),c));
  const op=h('label','lt-opacity'),range=h('input'),out=h('output');range.type='range';range.min='10';range.max='100';range.step='5';range.value=String(Math.round((sel[0].opacity??1)*100));range.setAttribute('aria-label','Opacity');
  out.textContent=range.value+'%';op.title='The opacity of the selected pieces';op.append('Opacity',range,out);
  range.oninput=()=>{out.textContent=range.value+'%';for(const s of chosen()){s.opacity=Number(range.value)/100;position(s);}};range.onchange=save;
  const turn=button('lt-turn','Turn over','Turn over (F)');turn.onclick=()=>turnOver(chosen());
  const cut=button('lt-cut',one?(one.part?'Join':'Divide'):'Divide or join',one?(one.part?'Join with its other leaf (D)':'Divide into its two leaves (D)'):'Divide each sheet, or join each leaf (D)');cut.onclick=()=>cutOrJoin(chosen());
  const both=button('lt-twinbtn','Both faces','Show its other face beside it, to the right, moving with it; nothing is drawn behind either face'),on=sel.every(x=>x.twin);
  both.setAttribute('aria-pressed',String(on));both.onclick=()=>pairUp(chosen(),!on);
  float.append(swatch,op,sep(),turn,both,cut);
  if(one){const pg=button('lt-pagesbtn','Pages ▾','Which of its pages are drawn');pg.setAttribute('aria-haspopup','dialog');pg.setAttribute('aria-expanded','false');pg.onclick=()=>openPages(pg,one);float.append(pg);}
  const dup=button('lt-dup','Duplicate','Duplicate (Ctrl D): a copy to the right, as it is'),remove=button('lt-remove','×','Remove (Delete)');remove.setAttribute('aria-label','Remove');
  dup.disabled=state.sheets.length+sel.length>S.MAX_SHEETS;if(dup.disabled)dup.title=`The table holds ${S.MAX_SHEETS} pieces at most`;dup.onclick=()=>duplicate(chosen());remove.onclick=()=>removePieces(chosen());
  float.append(sep(),dup,remove);
 }
 // above the selection, or below it where there is no room, inside the board
 function placeFloat(){
  const sel=chosen();if(!sel.length||busy){float.hidden=true;return;}
  float.hidden=false;
  const z=zoom(),b=union(sel.map(boxOf)),W0=table.clientWidth,H0=table.clientHeight;
  let x0=(b[0]-cam[0])*z,x1=(b[2]-cam[0])*z,y0=(b[1]-cam[1])*z,y1=(b[3]-cam[1])*z;const w=float.offsetWidth,ht=float.offsetHeight;
  // clear of the selection's name tags too, which lie over or under it
  for(const t of tags.children)if(selection.has(t.dataset.id)){const ty=t.offsetTop-cam[1]*z;y0=Math.min(y0,ty);y1=Math.max(y1,ty+t.offsetHeight);}
  let top=y0-ht-10;if(top<6)top=y1+10;if(top+ht>H0-6)top=Math.max(6,Math.min(H0-ht-6,y0+6));
  float.style.left=Math.max(6,Math.min(W0-w-6,(x0+x1)/2-w/2))+'px';float.style.top=top+'px';
 }
 // ---- Edit
 function updateEdit(){
  const n=selection.size,all=state.sheets.length,many=n>=2;
  $('selectAll').disabled=!all;$('turnSel').disabled=$('cutSel').disabled=$('removeSel').disabled=!n;$('clear').disabled=!all;$('dupSel').disabled=!n||all+n>S.MAX_SHEETS;
  $('stack').firstChild.textContent=many?'Stack the selection at the fold':'Stack at the fold';$('stack').disabled=(many?n:all)<2;
  $('spread').firstChild.textContent=many?'Spread out the selection':'Spread out';$('spread').disabled=!all;
 }
 const edit=fn=>()=>{closeMenus();fn();};
 $('selectAll').onclick=edit(()=>setSelection(state.sheets.map(S.idOf)));
 $('turnSel').onclick=edit(()=>turnOver(chosen()));
 $('cutSel').onclick=edit(()=>cutOrJoin(chosen()));
 $('removeSel').onclick=edit(()=>removePieces(chosen()));
 $('dupSel').onclick=edit(()=>duplicate(chosen()));
 // stack and spread act on the selection when two or more are chosen, else on every piece; spread lays them out from where they start
 const targets=()=>selection.size>=2?chosen():state.sheets;
 $('stack').onclick=edit(()=>{const t=targets();if(t.length<2)return;S.stack(t).forEach((p,i)=>Object.assign(t[i],{x:p.x,y:p.y}));render();});
 $('spread').onclick=edit(()=>{
  const t=targets();if(!t.length)return;const boxes=t.map(frameOf),from=selection.size>=2?union(t.map(boxOf)).slice(0,2).map(v=>v-20):cam;
  S.spread(t,table.clientWidth/zoom(),boxes).forEach((p,i)=>Object.assign(t[i],{x:p.x+from[0],y:p.y+from[1]}));render();inView(t);
 });
 $('clear').onclick=edit(()=>{state.sheets=[];render();});
 $('snap').onchange=()=>{state.snap=$('snap').checked;save();};
 // ---- turning, dividing and joining, removing: each of the pieces given
 function turnOver(list){for(const s of list)Object.assign(s,S.turn(s,p=>viewOf(p).box));for(const s of list)paint(s);fillList();buildFloat();placeFloat();describe();save();}
 function cutOrJoin(list){
  const next=[];
  for(const s of list){
   if(!state.sheets.includes(s))continue;
   if(s.part){state.sheets=S.join(s,state.sheets);next.push(S.idOf({...s,part:''}));}
   else{const at=state.sheets.indexOf(s),parts=S.divide(s);state.sheets=[...state.sheets.slice(0,at),...parts,...state.sheets.slice(at+1)];next.push(...parts.map(S.idOf));}
  }
  render();setSelection(next);
 }
 function removePieces(list){const gone=new Set(list);state.sheets=state.sheets.filter(s=>!gone.has(s));render();}
 // both faces side by side, or the face up alone
 function pairUp(list,on){for(const s of list){s.twin=on;paint(s);}buildFloat();placeFloat();describe();save();}
 // a copy of each, as it is (face, pages, colour, opacity, both faces), to the right of them all; two leaves of one copy stay one copy
 function duplicate(list){
  if(!list.length||state.sheets.length+list.length>S.MAX_SHEETS)return;
  const shift=(b=>b[2]-b[0]+20)(union(list.map(boxOf))),copies=new Map(),made=[];
  for(const s of list){
   const key=s.node+'~'+(s.copy||1);
   if(!copies.has(key))copies.set(key,1+[...state.sheets,...made].filter(q=>q.node===s.node).reduce((m,q)=>Math.max(m,q.copy||1),0));
   made.push({...s,copy:copies.get(key),x:s.x+shift});
  }
  state.sheets.push(...made);render();setSelection(made.map(S.idOf));inView(made);
 }
 // ---- guides: a fold or edge of another piece within reach, and how far off, solid once met, while a piece is dragged (gone when it is let go) and
 // for a moment after an arrow key; with Snap to guides on, the dragged pieces are moved onto it, else nothing is pulled into place
 let guides=[],fade=null;
 const alignFor=(s,x=s.x,y=s.y)=>S.align(x,y,linesOf(s),state.sheets.filter(o=>!selection.has(S.idOf(o))&&o!==s).map(o=>S.placed(o,linesOf(o))),Math.max(S.ALIGN_MM,6/zoom()));
 function showGuides(s,linger=0){
  clearTimeout(fade);for(const g of guides)g.remove();
  const z=zoom(),b=s&&frameOf(s);
  guides=(s&&state.guides?alignFor(s):[]).map(g=>{
   const met=Math.abs(g.off)<S.ALIGNED,el=h('div','lt-guide '+g.axis+(met?' on':''));
   el.style[g.axis==='x'?'left':'top']=(g.at-cam[g.axis==='x'?0:1])*z+'px';el.style.setProperty('--at',(g.axis==='x'?(s.y+b[1]-cam[1])*z:(s.x+b[0]-cam[0])*z)+6+'px');
   el.dataset.label=met?'aligned':`${Math.abs(g.off).toFixed(1)} mm`;table.append(el);return el;
  });
  if(linger)fade=setTimeout(()=>showGuides(null),linger);
 }
 function moveTo(s,x,y){s.x=Math.max(-S.LIMIT,Math.min(S.LIMIT,x));s.y=Math.max(-S.LIMIT,Math.min(S.LIMIT,y));position(s);}
 // ---- the board's pointer: a piece drags the selection, the empty table draws a selection box, the right or middle button (or Space) pans
 const toMM=(cx,cy)=>{const r=table.getBoundingClientRect(),z=zoom();return [(cx-r.left)/z+cam[0],(cy-r.top)/z+cam[1]];};
 function track(e,move,end){
  table.setPointerCapture(e.pointerId);
  const up=ev=>{table.removeEventListener('pointermove',move);table.removeEventListener('pointerup',up);table.removeEventListener('pointercancel',up);end(ev);};
  table.addEventListener('pointermove',move);table.addEventListener('pointerup',up);table.addEventListener('pointercancel',up);
 }
 const far=(e,start)=>Math.hypot(e.clientX-start.cx,e.clientY-start.cy)>3;
 function grab(s,e){
  const id=S.idOf(s),additive=e.shiftKey||e.ctrlKey||e.metaKey,was=selection.has(id);
  if(additive){const next=new Set(selection);if(was)next.delete(id);else next.add(id);setSelection([...next]);if(was)return;}
  else if(!was)setSelection([id]);
  const group=chosen(),z=zoom(),start={cx:e.clientX,cy:e.clientY,at:group.map(p=>[p.x,p.y]),x:s.x,y:s.y};let moved=false;
  busy=true;SG.hideTip();
  track(e,ev=>{
   if(!moved&&!far(ev,start))return;
   if(!moved){moved=true;float.hidden=true;}
   let p={x:start.x+(ev.clientX-start.cx)/z,y:start.y+(ev.clientY-start.cy)/z};
   if(state.snap)p=S.snapTo(p.x,p.y,alignFor(s,p.x,p.y));
   group.forEach((q,i)=>moveTo(q,start.at[i][0]+p.x-start.x,start.at[i][1]+p.y-start.y));
   showGuides(s);updateWhere();
  },()=>{
   busy=false;showGuides(null);
   // a click on one of several chosen pieces chooses it alone
   if(!moved&&!additive&&was&&selection.size>1)setSelection([id]);
   placeFloat();updateWhere();if(moved)save();
  });
 }
 function lasso(e){
  const additive=e.shiftKey||e.ctrlKey||e.metaKey,base=additive?[...selection]:[],a=toMM(e.clientX,e.clientY),start={cx:e.clientX,cy:e.clientY};let moved=false;
  busy=true;SG.hideTip();
  track(e,ev=>{
   if(!moved&&!far(ev,start))return;moved=true;float.hidden=true;
   const b=toMM(ev.clientX,ev.clientY),r=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])],z=zoom();
   Object.assign(marquee.style,{left:(r[0]-cam[0])*z+'px',top:(r[1]-cam[1])*z+'px',width:(r[2]-r[0])*z+'px',height:(r[3]-r[1])*z+'px'});marquee.hidden=false;
   // every piece the box touches
   const hit=state.sheets.filter(s=>{const q=boxOf(s);return q[0]<r[2]&&q[2]>r[0]&&q[1]<r[3]&&q[3]>r[1];}).map(S.idOf);
   setSelection([...new Set([...base,...hit])],{front:false});
  },()=>{busy=false;marquee.hidden=true;if(!moved&&!additive)deselect();else placeFloat();});
 }
 function pan(e){
  e.preventDefault();const z=zoom(),start={cx:e.clientX,cy:e.clientY,cam:[...cam]};
  table.classList.add('panning');SG.hideTip();closeColour();closePages();
  track(e,ev=>{cam=[start.cam[0]-(ev.clientX-start.cx)/z,start.cam[1]-(ev.clientY-start.cy)/z];applyCamera();},()=>table.classList.remove('panning'));
 }
 let space=false;
 table.addEventListener('pointerdown',e=>{
  if(e.target.closest('.lt-float,.lt-corner'))return;
  if(e.button===1||e.button===2||(e.button===0&&space))return pan(e);
  if(e.button!==0)return;
  e.preventDefault();closeMenus();closeColour();closePages();table.focus({preventScroll:true});
  const el=e.target.closest('.lt-sheet,.lt-tag');
  if(el&&find(el.dataset.id))grab(find(el.dataset.id),e);else lasso(e);
 });
 table.addEventListener('contextmenu',e=>{if(!e.target.closest('.lt-float'))e.preventDefault();});
 table.addEventListener('auxclick',e=>{if(e.button===1)e.preventDefault();});
 // ---- zoom: the wheel about the pointer, the buttons and keys about the board's middle, Fit to the selection or every piece
 const clampZoom=v=>Math.min(S.ZOOM_RANGE[1],Math.max(S.ZOOM_RANGE[0],v));
 function zoomTo(next,at=[table.clientWidth/2,table.clientHeight/2]){
  const z=zoom(),mm=[at[0]/z+cam[0],at[1]/z+cam[1]];state.zoom=S.zoomOf(clampZoom(next));const z2=zoom();
  cam=[mm[0]-at[0]/z2,mm[1]-at[1]/z2];closeColour();closePages();
  for(const s of state.sheets)paint(s);applyCamera();fillZoom();describe();save();
 }
 let pending=null,frame=0;
 table.addEventListener('wheel',e=>{
  e.preventDefault();SG.hideTip();
  const r=table.getBoundingClientRect(),z=pending?pending.z:zoom(),step=e.deltaMode===1?e.deltaY*16:e.deltaMode===2?e.deltaY*400:e.deltaY;
  const next=clampZoom(z*Math.exp(-step*.0015));if(next===z)return;
  pending={z:next,at:[e.clientX-r.left,e.clientY-r.top]};
  if(!frame)frame=requestAnimationFrame(()=>{frame=0;const p=pending;pending=null;if(p)zoomTo(p.z,p.at);});
 },{passive:false});
 // the pieces given, or every piece, fill the board with a margin
 // the height of a row of the sheets' tags over them, in millimetres at a zoom, when they are written above
 const tagRoom=(z=zoom())=>((state.sheetLabel==='above'?26:0)+(state.pageLabel==='above'?22:0))/z;
 function fitTo(list){
  if(!list.length)return;
  const b=list.map(boxOf).reduce((a,r)=>[Math.min(a[0],r[0]),Math.min(a[1],r[1]),Math.max(a[2],r[2]),Math.max(a[3],r[3])]),pad=15,W0=table.clientWidth,H0=table.clientHeight;
  const fits=top=>clampZoom(Math.min(W0/(b[2]-b[0]+2*pad),H0/(b[3]-top+2*pad)));
  b[1]-=tagRoom(fits(b[1]));state.zoom=S.zoomOf(fits(b[1]));const z=zoom();
  cam=[(b[0]+b[2])/2-W0/2/z,(b[1]+b[3])/2-H0/2/z];
  for(const s of state.sheets)paint(s);applyCamera();fillZoom();describe();save();
 }
 // the pieces given come into view, the camera moving only when one of them is out of it
 function inView(list){
  if(!list.length)return;const z=zoom(),W0=table.clientWidth/z,H0=table.clientHeight/z;
  const b=list.map(boxOf).reduce((a,r)=>[Math.min(a[0],r[0]),Math.min(a[1],r[1]),Math.max(a[2],r[2]),Math.max(a[3],r[3])]);
  if(b[0]>=cam[0]&&b[1]>=cam[1]&&b[2]<=cam[0]+W0&&b[3]<=cam[1]+H0)return;
  centreOn(list);
 }
 function centreOn(list){
  const z=zoom(),b=list.map(boxOf).reduce((a,r)=>[Math.min(a[0],r[0]),Math.min(a[1],r[1]),Math.max(a[2],r[2]),Math.max(a[3],r[3])]);
  cam=[(b[0]+b[2])/2-table.clientWidth/2/z,(b[1]+b[3])/2-table.clientHeight/2/z];applyCamera();
 }
 $('zoomIn').onclick=()=>zoomTo(zoom()*1.25);$('zoomOut').onclick=()=>zoomTo(zoom()/1.25);
 $('fit').onclick=()=>fitTo(selection.size?chosen():state.sheets);
 $('zoom').onchange=()=>zoomTo(Number($('zoom').value));
 function fillZoom(){
  const sel=$('zoom');let custom=sel.querySelector('option[data-custom]');
  if(S.ZOOMS.includes(state.zoom)){if(custom)custom.remove();}
  else{if(!custom){custom=new Option('','');custom.dataset.custom='1';sel.append(custom);}custom.value=state.zoom;custom.textContent=`${state.zoom} px/mm`;}
  sel.value=state.zoom;
 }
 // ---- the keyboard: the arrows move the selection, F turns it over, D divides or joins, Delete removes, Escape lets go; Ctrl A chooses every
 // piece, + and − zoom, Shift 1 fits; Space held pans with the left button
 const typing=t=>t.closest&&t.closest('input,select,textarea,.lt-panel,.lt-pop');
 addEventListener('keydown',e=>{
  if(e.key==='Escape'){
   if(!pop.hidden)closeColour();else if(!pagesPop.hidden)closePages();
   else if(openMenu()){const [b]=openMenu();closeMenus();$(b).focus();}
   else if(selection.size)deselect();
   return;
  }
  if(typing(e.target))return;
  if(e.key===' '&&!e.target.closest('button')){e.preventDefault();if(!space){space=true;table.classList.add('space');}return;}
  if((e.key==='a'||e.key==='A')&&(e.ctrlKey||e.metaKey)){e.preventDefault();setSelection(state.sheets.map(S.idOf));return;}
  if((e.key==='d'||e.key==='D')&&(e.ctrlKey||e.metaKey)){e.preventDefault();duplicate(chosen());return;}
  if(e.ctrlKey||e.metaKey)return;
  if(e.code==='Digit1'&&e.shiftKey){e.preventDefault();fitTo(selection.size?chosen():state.sheets);return;}
  if(e.key==='+'||e.key==='='){e.preventDefault();zoomTo(zoom()*1.25);return;}
  if(e.key==='-'||e.key==='_'){e.preventDefault();zoomTo(zoom()/1.25);return;}
  const sel=chosen();if(!sel.length)return;
  const step=e.altKey?.1:e.shiftKey?5:.5,d={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[e.key];
  if(d){e.preventDefault();for(const s of sel)moveTo(s,Math.round((s.x+d[0])*10)/10,Math.round((s.y+d[1])*10)/10);showGuides(sel[sel.length-1],1500);placeFloat();updateWhere();save();}
  else if(e.key==='f'||e.key==='F'){e.preventDefault();turnOver(sel);}
  else if(e.key==='d'||e.key==='D'){e.preventDefault();cutOrJoin(sel);}
  else if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();removePieces(sel);}
 });
 addEventListener('keyup',e=>{if(e.key===' '){space=false;table.classList.remove('space');}});
 addEventListener('blur',()=>{space=false;table.classList.remove('space');});
 // ---- what is under the pointer: the topmost piece's word there, the face up before the face underneath
 table.addEventListener('pointermove',e=>{
  if(e.buttons||busy||e.target.closest('.lt-float'))return;
  const [mx,my]=toMM(e.clientX,e.clientY);
  for(const id of [...order].reverse()){
   const s=find(id);if(!s)continue;
   const f=frameOf(s);if(mx-s.x<f[0]||mx-s.x>f[2]||my-s.y<f[1]||my-s.y>f[3])continue;
   const pr=pairOf(s);
   for(const [v,dx,twin] of [[viewOf(s),0,false],...(pr?[[pr.twin,pr.dx,true]]:[])]){
    const x=mx-s.x-dx,y=my-s.y;if(x<v.box[0]||x>v.box[2]||y<v.box[1]||y>v.box[3])continue;
    const inside=w=>x>=w.rect[0]&&x<=w.rect[2]&&y>=w.rect[1]&&y<=w.rect[3];
    for(const l of [...v.leaves.filter(l=>l.shown&&l.front),...v.leaves.filter(l=>l.shown&&!l.front)]){
     const w=l.words.find(inside);if(!w)continue;
     const p=pages[l.folio],u=p.units[w.id],text=words.slice(u[0],u[1]+1).join(' ');
     const angle=l.tilt?`<br>text angle ${deg(l.tilt.angle)} as written${l.tilt.flat!=null?`, ${deg(l.tilt.flat)} after flattening`:''}, the median of ${l.tilt.n} lines`:'';
     SG.showTip(`<b>${esc(l.name||l.folio)}</b> · line ${esc(p.lines[u[2]][0])} · <code>${esc(text)}</code><br>${twin?'on its other face, beside it':l.front?'on the face up':'on the face underneath, seen through'}${l.turned?', written upside down':''} · ${esc(nameOf(s))}${angle}`,e.clientX,e.clientY);return;
    }
   }
   SG.hideTip();return;
  }
  SG.hideTip();
 });
 // ---- View: pages, what is drawn, opacities, colour, coordinates
 const FACE_BOXES=[['outerFaces','outer'],['innerFaces','inner']];
 function syncChecks(){
  for(const [id,f] of FACE_BOXES){
   const bits=S.FACE_BITS[f],on=state.sheets.filter(s=>(s.show&bits)===bits).length,some=state.sheets.some(s=>s.show&bits);
   $(id).checked=state.sheets.length>0&&on===state.sheets.length;$(id).indeterminate=some&&on<state.sheets.length;$(id).disabled=!state.sheets.length;
  }
 }
 for(const [id,f] of FACE_BOXES)$(id).onchange=()=>{const bits=S.FACE_BITS[f];for(const s of state.sheets)s.show=$(id).checked?s.show|bits:s.show&~bits;render();};
 for(const [id,key] of [['faceUp','faceUp'],['underneath','underneath'],['words','words'],['margins','margins'],['angle','angle'],['dim','dim'],['copyNumbers','copyNumbers'],['lines','lines']])$(id).onchange=()=>{state[key]=$(id).checked;render();};
 $('sheetLabel').onchange=()=>{state.sheetLabel=$('sheetLabel').value;render();};$('pageLabel').onchange=()=>{state.pageLabel=$('pageLabel').value;render();};
 $('angleAt').onchange=()=>{state.angleAt=$('angleAt').value;render();};$('angleValues').onchange=()=>{state.angleValues=$('angleValues').checked;render();};$('angleScale').onchange=()=>{state.angleScale=$('angleScale').value;render();};$('angleLength').onchange=()=>{state.angleLength=$('angleLength').value;render();};
 $('guides').onchange=()=>{state.guides=$('guides').checked;if(!state.guides)showGuides(null);save();};
 // the opacity sliders repaint once a frame while they move
 let repaint=0;
 for(const k of S.OPACITY){
  const r=$('op-'+k),out=r.nextElementSibling;
  r.oninput=()=>{state.opacity[k]=Number(r.value)/100;out.textContent=r.value+'%';if(!repaint)repaint=requestAnimationFrame(()=>{repaint=0;for(const s of state.sheets)paint(s);});};
  r.onchange=save;
 }
 $('wdir').onchange=()=>{state.wdir=$('wdir').value;render();};
 $('colour').onchange=()=>{state.colouring=$('colour').value;render();};
 $('coords').onchange=()=>{state.coords=$('coords').value;render();};
 // ---- the notes, under Help
 function describe(){
  const n=state.sheets.length,leaves=state.sheets.filter(s=>s.part).length,on=state.sheets.map(viewOf),est=k=>on.flatMap(v=>v.leaves.filter(l=>l.estimated.includes(k)).map(l=>l.folio));
  const missing=[...new Set(state.sheets.flatMap(s=>modelOf(s).missing))],foldouts=[...new Set(state.sheets.filter(s=>{const v=viewOf(s);return !v.folded&&!v.measured&&v.leaves.some(l=>l.k||l.panel);}).map(s=>s.node))];
  const measured=[...new Set(state.sheets.filter(s=>viewOf(s).measured).map(s=>s.node))];
  const rosettes=state.sheets.some(s=>viewOf(s).folded);
  const count=[n-leaves?`${n-leaves} ${n-leaves===1?'sheet':'sheets'}`:'',leaves?`${leaves} ${leaves===1?'leaf':'leaves'}`:''].filter(Boolean).join(' and ');
  status.textContent=n?`${count} on the table · ${state.coords==='flat'?'flat (dewarped)':'recorded'} coordinates · parchment scale, estimated · ${state.zoom} px/mm`:'The table is empty: Add sheet puts a bifolium on it, as a sheet or a leaf.';
  notes.textContent=n?'Filled words are on the face that is up, as read. Outlined words are on the face underneath, mirrored, where they lie behind it on the same leaf. Folds are dashed. '
   +(state.sheets.some(s=>s.twin)?`Both faces side by side, the other face to the right, linked, and nothing drawn behind either: ${state.sheets.filter(s=>s.twin).map(nameOf).join(', ')}. `:'')
   +(!state.faceUp||!state.underneath?`${!state.faceUp&&!state.underneath?'Neither face is drawn':!state.faceUp?'The visible face is not drawn':'The face underneath is not drawn'} (View). `:'')
   +(state.colouring==='face'?'Pages are coloured by the face of their sheet, outer or inner, so overlapping pieces show which side of their sheet is up; outlines are in ink. ':'')
   +(state.words?(zoom()<2?'Zoom in to about 2 px/mm or more to read the words. ':'EVA spellings are written in their boxes; those underneath the right way round, at their mirrored places. ')
    +(turnedOn.size?(state.wdir==='level'?'Words on rings, turned lines and upside-down panels stand upright, one size a page, and can run past their boxes. ':'Words on rings, turned lines and upside-down panels are written along the writing, ring words with their bottoms towards the wheel\'s centre; Word direction: Level stands them upright. '):''):'')
   +(state.margins?'Margins trace each page\'s text edges: the left ends of full paragraph rows that are not a paragraph\'s first, the right ends of those that are not its last, a line joining consecutive rows; behind, dashed. ':'')
   +(state.angle?`Text angle: each page's median line angle as the words are drawn, ${state.coords==='flat'?'after flattening (Recorded coordinates give it as written)':'as written'}, solid, against the level, dotted, through ${state.angleAt==='page'?'the middle of the page':'the centroid of its text'}, ${state.angleLength==='equal'?`each ${S.EQUAL_MM} mm long`:'as wide as the text'}${state.angleScale!=='1'?`, drawn at ${state.angleScale} times its angle (at most ${S.MAX_DRAWN}°) so small differences show; the values beside the lines are the true angles`:''}. `:'')
   +((state.margins||state.angle)?'Both are measured against the photograph\'s frame, not the parchment\'s edge. ':'')
   +(state.angle?(f=>f.length?`No text angle, for want of horizontal paragraph lines: ${f.join(', ')}. `:'')([...new Set(on.flatMap(v=>v.leaves.filter(l=>l.shown&&!l.tilt).map(l=>l.name||l.folio)))]):'')
   +[['fold','Fold estimated'],['top','Top edge estimated'],['scale','Scale estimated']].map(([k,t])=>{const f=[...new Set(est(k))];return f.length?`${t}: ${f.join(', ')}. `:'';}).join('')
   +(rosettes?'The Rosettes sheet folds three panels by two, as the Beinecke photographs show it: the Rosettes fill its inside (f85v | f86r); outside, the lower row (f86v5, f86v3, f85r1) reads the same way up as the Rosettes and the upper row (f86v6, f86v4, f85r2) is written upside down, to be read with the upper half folded down. Panels are drawn at the catalogue leaf size. The Rosettes are drawn whole, as photographed, placed by their fold and horizontal crease, which are placed by eye on the scan to about 5 mm. ':'')
   +(measured.length?`Foldout leaves at their widths measured on the Beinecke photographs, to about 3 mm, creases dashed: ${measured.join(', ')}. `:'')
   +[...new Set(measured.filter(n=>Object.values(sheets[n]||{}).some(p=>p&&p.faces)))].map(n=>`${n}: the panel by the binding is drawn at each face's own width, as the binding hides more of it on one face than the other. `).join('')
   +(foldouts.length?`Foldout panels are laid outward a leaf apiece, their real folding not modelled: ${foldouts.join(', ')}. `:'')+(missing.length?`Not on the parchment, so not drawn: ${missing.join(', ')}. `:''):'';
 }
 // ---- everything from the state
 function render(){
  const ids=new Set(state.sheets.map(S.idOf));
  for(const [id,el] of els)if(!ids.has(id)){el.remove();els.delete(id);turnedOn.delete(id);}
  if(!state.sheets.length)$('wdirLabel').hidden=true;
  order=order.filter(id=>ids.has(id));for(const id of ids)if(!order.includes(id))order.push(id);
  selection=new Set([...selection].filter(id=>ids.has(id)));
  for(const id of ['coords','wdir','colour'])$(id).value=state[id==='colour'?'colouring':id];
  for(const id of ['guides','snap','words','margins','angle','faceUp','underneath','dim','copyNumbers','lines'])$(id).checked=state[id];$('sheetLabel').value=state.sheetLabel;$('pageLabel').value=state.pageLabel;
  $('angleAt').value=state.angleAt;$('angleLength').value=state.angleLength;$('angleScale').value=state.angleScale;$('angleValues').checked=state.angleValues;
  // drawn steeper than true, said once, in the table's corner
  $('angleBadge').hidden=!(state.angle&&state.angleScale!=='1');$('angleBadge').textContent=`Angles drawn ×${state.angleScale}${state.angleValues?'; the values are true':''}`;$('angleOpts').hidden=!state.angle;
  for(const k of S.OPACITY){const r=$('op-'+k);r.value=String(Math.round(state.opacity[k]*100));r.nextElementSibling.textContent=r.value+'%';}
  $('legend').hidden=state.colouring!=='face';faceChips();fillZoom();
  for(const s of state.sheets)paint(s);
  fillList();fillAdd();syncChecks();describe();fit();applyCamera();buildFloat();placeFloat();updateEdit();save();
 }
 addEventListener('hashchange',()=>{const next=S.parse(SG.hash(),nodes);if(JSON.stringify(S.serialize(next,nodes))===JSON.stringify(S.serialize(state,nodes)))return;state=next;render();});
 // a theme change repaints, as the colours are read from the page's tokens
 new MutationObserver(()=>{for(const s of state.sheets)paint(s);}).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{for(const s of state.sheets)paint(s);});
 addEventListener('resize',()=>{fit();placeFloat();});
 // the camera starts at the table's corner, or far enough up and left to show a piece placed there
 {const b=state.sheets.map(boxOf);if(b.length)cam=[Math.min(0,Math.min(...b.map(r=>r[0]))-20),Math.min(0,Math.min(...b.map(r=>r[1]))-20-tagRoom())];}
 try{render();}finally{loading.end();}
})();
