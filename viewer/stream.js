"use strict";
// The Page stream page: whole pages in a chosen order, as a chain of bifolia, one column, or laid over each other. Order and geometry: js/stream_math.js.
(async function(){
 const {$}=SG,T=VMS_STREAM,X=VMS_SECTIONS,Z=COMPARE_STATE;
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const host=$('pageStream'),pane=$('streamPane'),overlayWrap=$('overlayWrap'),overlay=$('overlay'),strip=$('strip'),status=$('status'),notes=$('notes'),focus=$('focus'),position=$('position'),slider=$('slider'),jumpTo=$('jump');
 const ctl={by:$('by'),order:$('order'),view:$('view'),columns:$('columns'),join:$('join'),covered:$('covered'),route:$('route'),trail:$('trail'),anchor:$('anchor'),tilt:$('tilt'),coords:$('coords'),scale:$('scale'),zoom:$('zoom')};
 const TILT_NOTES={turn:'Rigid turn: each drawn margin leans by its page\'s own turn, on top of its slope. To compare margins, use Recorded tilt or Recorded coordinates.',oldLink:'This link comes from the comparison workspace, which turned its pages rigidly and so leaned every margin. It opens on the recorded tilt, so it will not look quite as it did there.'};
 const STORE='vms-boundary-presets-v1',LAST=STORE+'-selected',GUTTER=98,SLOT_NAMES={Ar:'A recto',Av:'A verso',Br:'B recto',Bv:'B verso'},DASHES=[[],[7,4],[2,3],[8,3,2,3]],COVERED_NAMES={faint:'faint text',outline:'box outlines',margin:'margin trace',hidden:'hidden',full:'full overlay'};
 let state=T.parse(SG.hash()),pages,words,tokens,orders,compact,list,bundleKey='',plan={nodes:[],baseNodes:[],pages:[],missing:[],custom:false};
 let selectedAtLoad=[...state.pages],pendingJump=state.view!=='overlay'&&state.at>0,requested=null,signature='',autoSeam='';
 const loading=SG.busyStart('Loading the manuscript…');
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  const index=await SG.load(SG.dataUrl('index.json')),C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const bundle=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];bundleKey=bundle.key;
  const [loadedPages,loadedOrders,data]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(bundle.path))]);
  compact=loadedPages;pages=compact.pages;orders=loadedOrders;words=data.words;tokens=X.lineTokens(data.lines);list=T.orderPages(orders,state.order,pages);
 }catch(error){loading.end();status.textContent='Could not load the page data.';SG.error(host,error);return;}
 state=T.clean(state,pages,list);
 // a boundary the page chose for itself is not the reader's choice, so it stays out of the address
 const save=()=>{const o=T.serialize(state);if(state.seam===autoSeam)delete o.seam;SG.setHash({data:SG.hash().data,...o});};
 const dark=()=>parseInt(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().slice(1,3),16)<128;
 const css=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
 const degrees=(a,d=3)=>a==null?'unavailable':(a>=0?'+':'−')+Math.abs(a).toFixed(d)+'°';
 const toolbarHeight=()=>{const bar=$('toolbar');return getComputedStyle(bar).position==='sticky'?bar.offsetHeight:0;};
 const hue=i=>(i*137.507764)%360;
 const color=node=>`hsl(${hue(Math.max(0,plan.baseNodes.indexOf(node))).toFixed(2)} 62% ${dark()?68:36}%)`;
 // ---- a page's placement, kept while the geometry settings hold
 const placed=new Map();let placedKey='';
 function recordOf(folio){
  const key=[state.coords,state.scale,state.anchor,state.tilt,T.studyFrame(state)].join('|');
  if(key!==placedKey){placed.clear();placedKey=key;}
  if(!placed.has(folio))placed.set(folio,T.orient(pages[folio],T.register(folio,pages[folio],words,tokens,{...state,reference:T.studyFrame(state)?T.STUDY.pages[folio]:null}),state.coords,state.tilt));
  return placed.get(folio);
 }
 // ---- the pages: canvases are painted near the view and released away from it, so a whole manuscript needs no giant bitmap
 let observer=null,drawnKey='',shown=[],parts=[],sheets=[],stack=null,paintRequest=null;
 function paint(part){
  const {canvas,frame:F}=part,{words:units,marginRows,angle}=shown[part.index],page=plan.pages[part.index],dpr=devicePixelRatio||1;
  canvas.width=Math.ceil(F.w*dpr);canvas.height=Math.ceil(F.h*dpr);
  const g=canvas.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);
  if(!F.joined){g.fillStyle=css('--surface');g.fillRect(0,0,F.w,F.h);}
  const xy=([x,y])=>[F.padX+(x-F.xmin)*F.s,F.padY+(y-F.ymin)*F.s],col=color(page.node),dash=DASHES[T.SLOTS.indexOf(page.slot)]||[];
  if(F.xmin<=0&&F.xmax>=0&&state.scale!=='paper'){g.strokeStyle=css('--line2');g.setLineDash([3,5]);g.beginPath();g.moveTo(xy([0,0])[0],0);g.lineTo(xy([0,0])[0],F.h);g.stroke();g.setLineDash([]);}
  const draw=(style,alpha,from,to)=>{
   if(to<=from||style==='hidden')return;
   g.save();g.beginPath();g.rect(0,from,F.w,to-from);g.clip();
   if(style!=='margin')for(const u of units){
    const points=u.quad.map(xy);g.beginPath();points.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.closePath();
    if(style!=='outline'){g.globalAlpha=.055*alpha;g.fillStyle=col;g.fill();}
    g.globalAlpha=.65*alpha;g.strokeStyle=col;g.lineWidth=.8;g.stroke();
    if(state.words&&style!=='outline'){
     const r=u.rect,center=points.reduce((p,q)=>[p[0]+q[0]/4,p[1]+q[1]/4],[0,0]);
     g.save();g.translate(...center);g.rotate(angle.delta*Math.PI/180);
     let size=Math.min(13,(r[3]-r[1])*F.s*.6);g.font=size+'px Consolas,monospace';size*=Math.min(1,Math.max(1,(r[2]-r[0])*F.s-3)/Math.max(1,g.measureText(u.text).width));
     g.font=Math.max(4,size)+'px Consolas,monospace';g.globalAlpha=.95*alpha;g.fillStyle=col;g.textAlign='center';g.textBaseline='middle';g.fillText(u.text,0,0);g.restore();
    }
   }
   if(state.margins||style==='margin'){
    g.globalAlpha=alpha;g.strokeStyle=g.fillStyle=col;g.lineWidth=2;g.setLineDash(dash);
    for(let i=1;i<marginRows.length;i++)if(marginRows[i].line===marginRows[i-1].line+1){g.beginPath();g.moveTo(...xy(marginRows[i-1].point));g.lineTo(...xy(marginRows[i].point));g.stroke();}
    g.setLineDash([]);for(const row of marginRows){g.beginPath();g.arc(...xy(row.point),2.5,0,2*Math.PI);g.fill();}
   }
   g.restore();
  };
  const cutoff=F.joined?(F.coveredFrom==null?F.h:F.coveredFrom):F.h;
  draw('full',1,0,cutoff);draw(state.covered,state.covered==='full'?1:state.strength,cutoff,F.h);g.globalAlpha=1;
  part.painted=stamp(part);
 }
 const stamp=part=>[part.frame.coveredFrom,state.covered,state.strength].join('|');
 // a part is painted again only when what it shows has changed: dragging a boundary repaints the rows at that fold and nothing else
 function refreshPaint(){if(paintRequest!==null)return;paintRequest=requestAnimationFrame(()=>{paintRequest=null;for(const part of parts)if(part.active&&part.canvas&&part.painted!==stamp(part))paint(part);});}
 function positionRows(){
  if(!stack)return;
  const hidden=state.covered==='hidden',separate=state.foldMode==='separate',layout=T.stackSheets(sheets,{join:state.join,overlaps:state.overlaps,hideCovered:hidden,foldMode:state.foldMode,folds:state.folds});
  for(const placement of layout.rows){
   const row=sheets[placement.index];row.placement=placement;row.element.style.top=placement.top+'px';
   row.plot.style.clipPath=hidden&&!separate?`inset(0 0 ${Math.max(0,row.height-placement.visibleHeight)}px 0)`:'';
   row.element.classList.toggle('manual-seam',placement.manual);
   if(row.handle){row.handle.disabled=separate;row.handle.title=separate?'Use a column fold handle to move Ar, Av+Br or Bv.':`Drag up or down to adjust ${row.node}: ${(placement.overlap*100).toFixed(1)}% overlap. Arrow keys 1%, with Shift 5%. Moves this bifolium and the ones after it.`;row.handle.setAttribute('aria-label','Adjust overlap before '+row.node);}
   for(const [slot,col] of row.columns){
    const lane=separate?placement.lanes[T.foldGroup(slot)]:placement;
    col.style.transform=separate?`translateY(${lane.top-placement.top}px)`:'';
    col.style.clipPath=hidden&&separate?`inset(0 0 ${Math.max(0,row.height-lane.visibleHeight)}px 0)`:'';
    const handle=col.querySelector('.column-seam');if(handle){handle.title=`${T.foldGroup(slot)==='inner'?'Av + Br':slot}: ${(lane.overlap*100).toFixed(1)}% overlap before ${row.node}. Drag or use arrow keys.`;handle.setAttribute('aria-pressed',String(state.seam===lane.key&&state.foldPart===T.foldGroup(slot)));}
   }
   for(const part of row.parts){
    const lane=separate?placement.lanes[T.foldGroup(plan.pages[part.index].slot)]:placement,fold=lane.foldY===null?row.height:lane.foldY-lane.top;
    Object.assign(part.frame,{plotTop:lane.top+part.rowOffset,coveredFrom:Math.max(0,Math.min(part.frame.h,fold-part.rowOffset))});
   }
  }
  stack.style.height=layout.height+'px';refreshPaint();
 }
 function adjustOverlap(seam,value,commit=true){
  if(!sheets.some(r=>r.placement&&r.placement.key===seam))return;
  const v=value===null?null:Math.round(Math.max(0,Math.min(T.MAX_OVERLAP,Number(value)||0))*1000)/1000;
  if(state.foldMode==='separate'){
   if(v===null){if(state.folds[seam]){delete state.folds[seam][state.foldPart];if(!Object.keys(state.folds[seam]).length)delete state.folds[seam];}}
   else (state.folds[seam]||(state.folds[seam]={}))[state.foldPart]=v;
  }else if(v===null)delete state.overlaps[seam];else state.overlaps[seam]=v;
  state.seam=seam;autoSeam='';positionRows();syncOverlaps();if(commit)save();
 }
 function bindSeam(handle,row,group=null){
  let drag=null;
  const lane=()=>group&&row.placement.lanes?row.placement.lanes[group]:row.placement;
  const selectSeam=()=>{state.seam=row.placement.key;if(group)state.foldPart=group;autoSeam='';syncOverlaps();};
  handle.onclick=selectSeam;
  handle.onpointerdown=e=>{
   if(e.button!==0||handle.disabled)return;e.preventDefault();selectSeam();handle.focus({preventScroll:true});
   const saved=group?state.folds[row.placement.key]?.[group]:state.overlaps[row.placement.key];
   drag={id:e.pointerId,y:e.clientY,value:lane().overlap,height:sheets[row.placement.index-1].height,original:saved??null,moved:false};handle.setPointerCapture(e.pointerId);handle.classList.add('dragging');
  };
  handle.onpointermove=e=>{if(drag&&e.pointerId===drag.id){drag.moved=drag.moved||Math.abs(e.clientY-drag.y)>1;if(drag.moved)adjustOverlap(row.placement.key,drag.value-(e.clientY-drag.y)/Math.max(1,drag.height),false);}};
  const finish=(e,cancel)=>{
   if(!drag||e.pointerId!==drag.id)return;
   const {original,moved}=drag;drag=null;handle.classList.remove('dragging');if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);
   adjustOverlap(row.placement.key,cancel||!moved?original:lane().overlap,true);
  };
  handle.onpointerup=e=>finish(e,false);handle.onpointercancel=e=>finish(e,true);
  handle.onkeydown=e=>{
   if(e.key==='Escape'&&drag){e.preventDefault();finish({pointerId:drag.id},true);return;}
   if(!['ArrowUp','ArrowDown','Home','End'].includes(e.key))return;e.preventDefault();selectSeam();
   adjustOverlap(row.placement.key,e.key==='Home'?0:e.key==='End'?T.MAX_OVERLAP:lane().overlap+(e.key==='ArrowUp'?1:-1)*(e.shiftKey?.05:.01));
  };
 }
 function build(records,width){
  const key=JSON.stringify([records.map(r=>r.folio),plan.baseNodes,state.view,state.columns,state.join,state.coords,state.scale,state.anchor,state.tilt,state.words,state.margins,state.foldMode,T.studyFrame(state),width,state.zoom,dark()]);
  if(key===drawnKey){positionRows();return;}
  clearStream();drawnKey=key;shown=records;
  const chain=state.view==='chain',joined=chain&&state.join!=='frames',valid=records.filter(r=>r.selection.available),singulion=state.columns==='singulion',zoom=Number(state.zoom);
  // on the parchment every column is one leaf, fold to fore-edge, with nothing added at the fold, so the two pages of a face meet there
  const paper=state.scale==='paper',xmin=paper?0:Math.min(0,...valid.map(r=>r.bounds.xmin))-35,xmax=paper?T.LEAF_MM*T.PAPER_UNITS:Math.max(600,...valid.map(r=>r.bounds.xmax))+35,ymin=Math.min(0,...valid.map(r=>r.bounds.ymin)),ymax=Math.max(80,...valid.map(r=>r.bounds.ymax));
  const rowWidth=Math.max(360,Math.max(320,width)*zoom),gutter=joined?GUTTER:0,w=chain?(rowWidth-gutter-26)/4:Math.max(320,width)*zoom,padX=chain?(paper?0:10):24,s=(w-2*padX)/(xmax-xmin);
  host.style.setProperty('--stream-width',w+'px');host.style.setProperty('--row-width',rowWidth+'px');host.style.setProperty('--gutter',gutter+'px');host.classList.toggle('joined',joined);host.classList.toggle('split-folds',joined&&state.foldMode==='separate');
  const byNode=new Map();let parent=host;
  if(joined){
   const heads=h('div','chain-heads');for(const slot of singulion?T.SLOTS:['Bv','Ar','Av','Br'])heads.append(h('strong','',`${slot} · ${['Ar','Bv'].includes(slot)?'outer':'inner'}`));
   stack=h('div','chain-stack');host.append(heads,stack);parent=stack;
  }
  if(chain)records.forEach((r,index)=>{
   const p=plan.pages[index];if(byNode.has(p.node))return;
   const members=plan.pages.map((q,i)=>({q,r:records[i]})).filter(m=>m.q.node===p.node),sheet=h('section','stream-sheet'),columns=new Map();sheet.dataset.node=p.node;sheet.style.setProperty('--sheet',color(p.node));
   let handle=null;
   if(joined){
    const label=h('aside','chain-label');
    if(sheets.length){handle=h('button','chain-seam','↕ '+p.node);handle.type='button';label.append(handle);}else label.append(h('strong','','1 · '+p.node));
    for(const m of members){const line=h('span','',`${m.q.slot} ${m.q.folio} ${degrees(m.r.angle.recorded,2)}`);line.title=`Recorded tilt ${degrees(m.r.angle.recorded)}; displayed ${degrees(m.r.angle.displayed)}; ${m.r.angle.n} lines`;label.append(line);}
    sheet.append(label);
   }
   sheet.append(h('div','stream-boundary',`${sheets.length+1} · BIFOLIUM ${p.node} · START`));
   const addColumn=(into,slot)=>{const col=h('div','stream-col');col.dataset.slot=slot;col.append(h('h4','',`${slot} · ${SLOT_NAMES[slot]}`));into.append(col);columns.set(slot,col);};
   let plot;
   if(singulion){
    sheet.append(h('h3','','Singulion order · Ar → Av → Br → Bv'));
    plot=h('div','stream-singulion');for(const slot of T.SLOTS)addColumn(plot,slot);sheet.append(plot);
   }else{
    plot=h('div','stream-faces');sheet.append(plot);
    for(const [name,slots] of [['Outer face',VMS_COMPARE.faceSlots('outer')],['Inner face',VMS_COMPARE.faceSlots('inner')]]){
     const face=h('section','stream-face'),pair=h('div','stream-pair');face.setAttribute('aria-label',name);face.append(h('h3','',name),pair);for(const slot of slots)addColumn(pair,slot);plot.append(face);
    }
   }
   sheet.append(h('div','stream-boundary end',`BIFOLIUM ${p.node} · END`));
   const extents=members.filter(m=>m.r.selection.available).map(m=>m.r.bounds);
   const row={node:p.node,element:sheet,columns,index,handle,plot,parts:[],ymin:extents.length?Math.min(...extents.map(b=>b.ymin)):ymin,ymax:extents.length?Math.max(...extents.map(b=>b.ymax)):ymax};
   const ref=T.studyFrame(state)&&T.STUDY.sheets[p.node];if(ref){row.ymin=ref.ymin*VMS_COMPARE.BODY_HEIGHT_PX;row.ymax=ref.ymax*VMS_COMPARE.BODY_HEIGHT_PX;}
   if(joined&&state.foldMode==='separate'&&sheets.length)for(const [slot,col] of columns){
    const b=h('button','column-seam','↕ '+p.node+' · '+(T.foldGroup(slot)==='inner'?'Av+Br':slot));b.type='button';b.setAttribute('aria-label',`Adjust ${slot} fold before ${p.node}`);col.prepend(b);bindSeam(b,row,T.foldGroup(slot));
   }
   byNode.set(p.node,row);sheets.push(row);parent.append(sheet);if(handle)bindSeam(handle,row);
  });
  observer=new IntersectionObserver(entries=>{for(const e of entries){const part=parts[Number(e.target.dataset.index)];if(!part||!part.canvas)continue;part.active=e.isIntersecting;if(part.active)paint(part);else{part.canvas.width=1;part.canvas.height=1;part.painted=null;}}},{rootMargin:'1200px 0px'});
  records.forEach((r,i)=>{
   const p=plan.pages[i],el=h('section','stream-page'),first=i===0||plan.pages[i-1].node!==p.node,last=i===records.length-1||plan.pages[i+1].node!==p.node,row=byNode.get(p.node),selectedNote=state.pages.length?' of selected pages':'';
   el.dataset.index=i;el.dataset.folio=p.folio;el.style.setProperty('--sheet',color(p.node));
   if(first&&!chain)el.append(h('div','stream-boundary',`BIFOLIUM ${p.node} · START${selectedNote}`));
   const head=h('div','stream-head');
   head.append(h('strong','',chain?p.folio+(p.panels>1?' · panel '+(p.panel||'?'):''):`${i+1} · ${p.folio} · ${p.node} · ${p.position}${p.panels>1?' (panel)':'/4'} ${p.slot} · ${p.face}`));
   head.append(h('span','stream-angle',`Recorded tilt ${degrees(r.angle.recorded)} · displayed ${degrees(r.angle.displayed)} · ${r.angle.n} lines${state.tilt!=='none'&&!r.angle.restored?' · tilt not restored':''}`));el.append(head);
   const lo=joined?row.ymin:chain?ymin:r.bounds.ymin,hi=joined?row.ymax:chain?ymax:r.bounds.ymax;
   const F={w,h:joined?Math.max(1,(hi-lo)*s):Math.max(50,(hi-lo)*s+24),s,padX,padY:joined?0:12,xmin,xmax,ymin:lo,ymax:hi,joined};
   const part={element:el,frame:F,index:i,canvas:null,active:false,painted:null,rowOffset:0};
   if(r.selection.available){
    const canvas=h('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label',`${p.folio} ${p.slot} text; recorded tilt ${degrees(r.angle.recorded)}`);canvas.style.width=w+'px';canvas.style.height=F.h+'px';canvas.width=canvas.height=1;el.append(canvas);part.canvas=canvas;
   }else{
    const absent=h('p',joined?'chain-gap':'stream-gap','This page has no box on its opening line, so it cannot be placed.');if(joined)absent.style.height=F.h+'px';el.append(absent);
   }
   parts.push(part);
   if(last&&!chain)el.append(h('div','stream-boundary end',`BIFOLIUM ${p.node} · END${selectedNote}`));
   (chain?row.columns.get(p.slot):host).append(el);observer.observe(el);
   if(row)row.parts.push(part);
  });
  if(chain)for(const row of sheets)for(const [slot,col] of row.columns)if(!col.querySelector('.stream-page'))col.append(h('p','stream-gap','No mapped page for '+slot+'.'));
  if(joined){
   for(const row of sheets){const rect=row.element.getBoundingClientRect();row.height=rect.height;for(const part of row.parts)part.rowOffset=part.element.getBoundingClientRect().top-rect.top;}
   positionRows();
  }
 }
 function clearStream(){observer&&observer.disconnect();observer=null;if(paintRequest!==null)cancelAnimationFrame(paintRequest);paintRequest=null;host.replaceChildren();shown=[];parts=[];sheets=[];stack=null;drawnKey='';}
 function jump(index){const part=state.view==='chain'?parts[index]&&parts[index].element.closest('.stream-sheet'):parts[index]&&parts[index].element;if(part){part.style.scrollMarginTop=(toolbarHeight()+8)+'px';part.scrollIntoView({block:'start',inline:'nearest',behavior:'instant'});}}
 function currentIndex(){
  if(state.view==='overlay')return state.at;
  const y=toolbarHeight()+35,items=state.view==='chain'?sheets:parts;if(!items.length)return 0;
  if(stack){let found=items[0];for(const item of items)if(item.element.getBoundingClientRect().top<=y)found=item;return found.index;}
  return (items.find(p=>p.element.getBoundingClientRect().bottom>y)||items[items.length-1]).index;
 }
 // ---- the overlay: one fixed frame across the sequence, so stepping cannot resize it
 function paintOverlay(width){
  const selections=plan.pages.map(p=>recordOf(p.folio).selection),b=T.bounds(selections),w=Math.max(320,width)*Number(state.zoom),s=(w-70)/(b.xmax-b.xmin),H=(b.ymax-b.ymin)*s+70,dpr=devicePixelRatio||1;
  const active=plan.pages[state.at],included=T.visible(plan.pages,state.at,state.trail),drawn=included.map(p=>({page:p,sel:selections[plan.pages.indexOf(p)]})).filter(x=>x.sel.available);
  overlay.width=Math.ceil(w*dpr);overlay.height=Math.ceil(H*dpr);overlay.style.width=w+'px';overlay.style.height=H+'px';
  const g=overlay.getContext('2d'),xy=(x,y)=>[35+(x-b.xmin)*s,35+(y-b.ymin)*s];g.setTransform(dpr,0,0,dpr,0,0);g.fillStyle=css('--surface');g.fillRect(0,0,w,H);
  for(const {page,sel} of drawn){
   const current=active&&page.folio===active.folio,alpha=current?1:state.fade,col=color(page.node);
   for(const u of sel.all){
    const [x,y]=xy(u.rect[0],u.rect[1]),rw=(u.rect[2]-u.rect[0])*s,rh=(u.rect[3]-u.rect[1])*s;
    g.globalAlpha=.08*alpha;g.fillStyle=col;g.fillRect(x,y,rw,rh);g.globalAlpha=.7*alpha;g.strokeStyle=col;g.lineWidth=.8;g.strokeRect(x,y,rw,rh);
    if(state.words){let size=Math.min(13,rh*.6);g.font=size+'px Consolas,monospace';size*=Math.min(1,Math.max(1,rw-3)/Math.max(1,g.measureText(u.text).width));g.font=Math.max(4,size)+'px Consolas,monospace';g.globalAlpha=.95*alpha;g.textAlign='center';g.textBaseline='middle';g.fillText(u.text,x+rw/2,y+rh/2);}
   }
  }
  if(state.margins)for(const {page,sel} of drawn){
   const current=active&&page.folio===active.folio,rows=sel.marginRows;g.globalAlpha=current?1:Math.max(.35,state.fade);g.strokeStyle=g.fillStyle=color(page.node);g.lineWidth=current?2.5:1.4;g.setLineDash(DASHES[T.SLOTS.indexOf(page.slot)]||[]);
   for(let i=1;i<rows.length;i++)if(rows[i].line===rows[i-1].line+1){g.beginPath();g.moveTo(...xy(rows[i-1].x,rows[i-1].y));g.lineTo(...xy(rows[i].x,rows[i].y));g.stroke();}
   g.setLineDash([]);for(const r of rows){g.beginPath();g.arc(...xy(r.x,r.y),current?3:2,0,2*Math.PI);g.fill();}
  }
  g.globalAlpha=1;
  const missing=included.filter(p=>!selections[plan.pages.indexOf(p)].available).map(p=>p.folio);
  notes.textContent=`${drawn.length} ${drawn.length===1?'page':'pages'} shown: the current page strong, earlier pages faded, colours by bifolium. No page is turned here. `+(missing.length?`No box on the opening line: ${missing.join(', ')}. `:'')+(plan.missing.length?`Requested position missing on: ${plan.missing.join(', ')}. `:'')+(state.route.startsWith('cycle:')?'Experimental position mapping, not a claimed chronology. ':'');
 }
 // ---- the parchment scale says what was measured and what was estimated, for the pages on show
 function paperNote(records){
  const P=compact.paper,rec=f=>pages[f].paper,on=k=>plan.pages.filter(p=>rec(p.folio)&&!['measured','sheet','panel'].includes(rec(p.folio)[k])).map(p=>p.folio),edge=T.LEAF_MM*T.PAPER_UNITS;
  const none=plan.pages.filter(p=>!rec(p.folio)).map(p=>p.folio),wide=records.filter(r=>r.selection.available&&rec(r.folio)&&(r.bounds.xmin<-1||r.bounds.xmax>edge+1)).map(r=>r.folio),fold=on('fold_method'),top=on('top_method'),scale=on('scale_method');
  return `Parchment scale, estimated: each page in millimetres from the edge where its leaf meets the binding, taken as the fold, and from the leaf's top edge, both found on the Beinecke scans, which are scaled so that the median leaf is the catalogue's ${P?P.catalogue.height:225} mm tall. A column is one ${T.LEAF_MM} mm leaf; the strip of a leaf hidden in the binding is not measured. `
   +(state.coords==='flat'?`Words dewarped: each page's shared curve and tilt are taken out of the vertical positions, about the page's own text, so it stays on its leaf${state.tilt==='none'?'':'; Tilt puts the recorded page angle back'}. `:'Words as drawn on the photographs: Coordinates, under Settings, has Flat for the dewarped text. ')
   +(fold.length?`Fold estimated from the median inner margin${P?' ('+P.medians.inner_margin_mm+' mm)':''}: ${fold.join(', ')}. `:'')+(top.length?`Top edge estimated from the bottom edge or the median top margin: ${top.join(', ')}. `:'')
   +(scale.length?`Scale estimated: ${scale.join(', ')}. `:'')+(wide.length?`Wider than one leaf, cut at the column edge: ${wide.join(', ')}. `:'')+(none.length?`Not on the parchment: ${none.join(', ')}. `:'');
 }
 // ---- the controls that follow the sequence
 const seamKeys=()=>plan.nodes.slice(1).map((node,i)=>T.seamKey(plan.nodes[i],node));
 function fillGroups(){
  const groups=X.groups(pages,list,state.by),name=n=>n==='—'?'Unassigned':n;
  $('group').replaceChildren(...(selectedAtLoad.length?[new Option(`Selected pages (${selectedAtLoad.length})`,'selected')]:[]),new Option(T.isHerbal(state.order)?'All ten candidate bifolia':'Whole manuscript','all'),...groups.map(g=>new Option(`${name(g.name)} (${g.pages.length})`,g.name)));
  if(state.group!=='all'&&!groups.some(g=>g.name===state.group))state.group='all';
  $('group').value=state.pages.length?'selected':state.group;
 }
 function syncOverlaps(){
  const keys=seamKeys(),key=state.seam,separate=state.foldMode==='separate',edited=keys.filter(k=>separate?Object.keys(state.folds[k]||{}).length:Object.hasOwn(state.overlaps,k)).length,shared=state.overlaps[key]??(state.join==='half'?.5:0),value=separate?(state.folds[key]?.[state.foldPart]??shared):shared,percent=String(Math.round(value*1000)/10);
  $('separateFolds').checked=separate;$('foldPartLabel').hidden=!separate;$('foldPart').value=state.foldPart;
  $('seam').value=key;$('overlap').value=percent;$('overlapNumber').value=percent;$('strength').value=state.strength;$('strengthValue').value=Math.round(state.strength*100)+'%';$('strength').disabled=['hidden','full'].includes(state.covered);
  $('overlap').disabled=$('overlapNumber').disabled=$('resetSeam').disabled=!keys.includes(key);$('resetSeams').disabled=!edited;
  $('overlapSummary').textContent='Adjust overlaps'+(separate?' · separate folds':'')+(edited?` · ${edited} set`:'');
  for(const row of sheets)if(row.handle)row.handle.setAttribute('aria-pressed',String(row.placement&&row.placement.key===key));
  if(notes.dataset.base)notes.textContent=notes.dataset.base+(state.view==='chain'&&state.join!=='frames'?`${edited} configured joins. Covered area: ${COVERED_NAMES[state.covered]}.`:'');
  const fit=T.isHerbal(state.order)&&T.STUDY.edges[key],g=fit?.groups?.[state.foldPart];
  const unchanged=fit&&(separate?T.FOLD_GROUPS.every(p=>Math.abs((state.folds[key]?.[p]??shared)-fit.groups[p].value)<1e-10):Math.abs(shared-fit.shared)<1e-10);
  $('foldFit').textContent=fit?`${unchanged?'Saved':'Reference'} ${separate?'three-fold':'single-join'} mismatch ${(separate?fit.score:fit.shared_score).toFixed(3)} (lower is better). ${unchanged?'':'This edited placement is not rescored. '}${separate&&g?`Chosen ${state.foldPart==='inner'?'Av+Br':state.foldPart} interval ${(g.interval[0]*100).toFixed(1)}–${(g.interval[1]*100).toFixed(1)}%; other near fits may exist. `:''}${fit.missing_slots.length?'f49v was unscored; the inner fold uses Br only. ':''}${!T.studyFrame(state)?'Current coordinate settings differ from the saved study registration. ':''}Ranges are score tolerances, not confidence intervals.`:'';
 }
 function fillSeams(){
  const keys=seamKeys(),active=plan.pages[state.at]&&plan.pages[state.at].node;
  $('seam').replaceChildren(...keys.map(k=>new Option(k.replace('>',' → '),k)));
  if(!keys.includes(state.seam))state.seam=autoSeam=keys.find(k=>k.split('>')[1]===active)||keys[0]||'';
  syncOverlaps();
 }
 function sync(){
  const flowing=state.view!=='overlay',chain=state.view==='chain',joined=chain&&state.join!=='frames';
  for(const k of Object.keys(ctl))ctl[k].value=state[k];
  $('words').checked=state.words;$('margins').checked=state.margins;$('fade').value=state.fade;
  $('separateFolds').checked=state.foldMode==='separate';$('foldPartLabel').hidden=state.foldMode!=='separate';$('foldPart').value=state.foldPart;
  $('columnsLabel').hidden=$('joinLabel').hidden=$('jumpLabel').hidden=!chain;$('routeLabel').hidden=chain;$('trailLabel').hidden=$('fadeLabel').hidden=flowing;$('tiltLabel').hidden=!flowing;
  ctl.tilt.disabled=state.coords==='recorded';    // recorded coordinates already hold the tilt: no setting moves anything there
  ctl.anchor.disabled=state.scale==='paper';ctl.anchor.title=state.scale==='paper'?'On the parchment scale every page is placed by its fold and top edge.':'';
  const flatTurn=flowing&&state.coords==='flat',note=flatTurn&&state.tilt==='turn'?TILT_NOTES.turn:flatTurn&&state.tilt==='restore'&&state.oldLink?TILT_NOTES.oldLink:'';
  $('tiltNote').textContent=note;$('tiltNote').hidden=!note;
  $('overlapPanel').hidden=$('coveredLabel').hidden=!joined;$('prevPage').hidden=$('nextPage').hidden=slider.hidden=strip.hidden=chain;
  overlayWrap.hidden=flowing;host.hidden=!flowing;focus.hidden=flowing;
  $('first').textContent=chain?'First bifolium':flowing?'Start of stream':'Show all';
 }
 function timeline(){
  const scroll=strip.scrollLeft;strip.replaceChildren();
  plan.nodes.forEach((node,ni)=>{
   const card=h('div','stream-card'),rows=h('div');card.style.setProperty('--sheet',color(node));
   const members=plan.pages.filter(p=>p.node===node);card.append(h('strong','',`${ni+1} · ${node}`),rows);
   if(!members.length)rows.append(h('span','note','Requested position missing'));
   for(const page of members){
    const i=plan.pages.indexOf(page),b=h('button');b.type='button';b.append(h('span','',`${page.position} ${page.slot} · ${page.folio}`),h('small','',(page.slot==='Ar'?'START · ':page.slot==='Bv'?'END · ':'')+page.face+(page.panels>1?' · panel '+(page.panel||'?'):'')));
    b.title=`${page.node} · ${page.folio} · ${page.slot} · ${page.section}`;b.setAttribute('aria-label',`Show page ${page.folio} ${page.slot}`);b.setAttribute('aria-current',String(i===state.at));b.classList.toggle('visited',state.view==='stream'||i<=state.at);
    b.onclick=()=>{state.at=i;pendingJump=true;render();};rows.append(b);
   }
   strip.append(card);
  });
  strip.scrollLeft=scroll;
  const active=strip.querySelector('[aria-current=true]');
  if(active){const left=active.getBoundingClientRect().left-strip.getBoundingClientRect().left;if(left<0)strip.scrollLeft+=left-8;else if(left+active.offsetWidth>strip.clientWidth)strip.scrollLeft+=left+active.offsetWidth-strip.clientWidth+8;}
 }
 // ---- reordering
 let reorderNodes=[],dragged=null,pendingFocus=null;
 const reorderList=$('reorderList');
 function cleanDrag(){for(const item of reorderList.children)item.classList.remove('drop-before','drop-after','dragging');dragged=null;}
 function moveSheet(node,index,action='grip'){
  if(!reorderNodes.includes(node)||index<0||index>=reorderNodes.length||reorderNodes.indexOf(node)===index)return;
  pendingFocus={node,action};$('reorderMessage').textContent=`${node} moved to position ${index+1}.`;
  state.custom=T.moveNode(plan.nodes,node,index);requested=plan.pages.find(p=>p.node===node);pendingJump=true;render();
 }
 function fillReorder(){
  const scroll=reorderList.scrollTop,activeButton=document.activeElement&&document.activeElement.closest?document.activeElement.closest('[data-reorder]'):null;
  const wanted=pendingFocus||(activeButton&&reorderList.contains(activeButton)?{node:activeButton.closest('li').dataset.node,action:activeButton.dataset.reorder}:null);pendingFocus=null;
  reorderNodes=[...plan.nodes];cleanDrag();reorderList.replaceChildren();$('resetOrder').disabled=!plan.custom;$('reorderSummary').textContent='Reorder bifolia'+(plan.custom?' · custom':'');
  reorderNodes.forEach((node,index)=>{
   const item=h('li'),grip=h('button','grip','⠿'),label=h('span','name',`${index+1} · ${node}`),up=h('button','','↑'),down=h('button','','↓');
   item.dataset.node=node;item.draggable=true;item.style.setProperty('--sheet',color(node));
   grip.type=up.type=down.type='button';grip.title='Drag to reorder; Alt + ↑ ↓ also moves this bifolium';grip.setAttribute('aria-label','Reorder '+node);grip.dataset.reorder='grip';
   for(const [button,delta,action] of [[up,-1,'up'],[down,1,'down']]){button.setAttribute('aria-label',`Move ${node} ${action}`);button.dataset.reorder=action;button.disabled=index+delta<0||index+delta>=reorderNodes.length;button.onclick=()=>moveSheet(node,index+delta,action);}
   grip.onkeydown=e=>{if(e.altKey&&['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();moveSheet(node,index+(e.key==='ArrowUp'?-1:1));}};
   item.ondragstart=e=>{dragged=node;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',node);item.classList.add('dragging');};
   item.ondragover=e=>{if(!dragged||dragged===node)return;e.preventDefault();e.dataTransfer.dropEffect='move';for(const other of reorderList.children)other.classList.remove('drop-before','drop-after');item.classList.add(e.clientY<item.getBoundingClientRect().top+item.offsetHeight/2?'drop-before':'drop-after');};
   item.ondrop=e=>{if(!dragged)return;e.preventDefault();const moving=dragged,after=e.clientY>=item.getBoundingClientRect().top+item.offsetHeight/2,target=reorderNodes.filter(n=>n!==moving).indexOf(node);cleanDrag();if(target>=0)moveSheet(moving,target+(after?1:0));};
   item.ondragend=cleanDrag;item.append(grip,label,up,down);reorderList.append(item);
  });
  reorderList.scrollTop=scroll;
  if(wanted){const row=[...reorderList.children].find(item=>item.dataset.node===wanted.node),button=row&&row.querySelector(`[data-reorder="${wanted.action}"]`);(button&&!button.disabled?button:row&&row.querySelector('.grip'))?.focus({preventScroll:true});}
 }
 // ---- drawing
 function heading(){
  const name=state.pages.length?'Selected pages':T.isHerbal(state.order)?'Herbal A · 1a candidate':state.group==='all'?'Whole manuscript':state.group==='—'?'Unassigned':state.group;
  return `${name} · ${{chain:'bifolium chain',stream:'continuous column',overlay:'superimposed overlay'}[state.view]}`;
 }
 function draw(){
  list=T.orderPages(orders,state.order,pages);fillGroups();
  const width=Math.max(320,pane.clientWidth-2),next=JSON.stringify([state.by,state.group,state.pages,state.order,state.custom,state.route,state.view,state.columns,state.join,state.anchor,state.tilt,state.coords,state.scale,state.zoom,width]);
  if(signature&&signature!==next&&state.view!=='overlay')pendingJump=true;signature=next;
  const chain=state.view==='chain',selectedNodes=new Set(state.pages.map(f=>pages[f].node));
  plan=T.sequence(pages,list,{by:state.by,group:state.group,custom:state.custom,route:chain?'all':state.route,selected:chain&&state.pages.length?list.filter(f=>selectedNodes.has(pages[f].node)):state.pages});
  if(requested){const same=plan.pages.findIndex(p=>p.folio===requested.folio),sheet=plan.pages.findIndex(p=>p.node===requested.node);if(same>=0||sheet>=0)state.at=same>=0?same:sheet;requested=null;}
  state.at=Math.max(0,Math.min(state.at,plan.pages.length-1));
  const active=plan.pages[state.at],flowing=state.view!=='overlay';
  sync();timeline();slider.max=Math.max(0,plan.pages.length-1);slider.value=state.at;
  $('prevPage').disabled=$('prevSheet').disabled=!flowing&&state.at===0;$('nextPage').disabled=$('nextSheet').disabled=!flowing&&state.at>=plan.pages.length-1;
  jumpTo.replaceChildren(...plan.nodes.map(n=>new Option(n,n)));jumpTo.value=active?active.node:'';
  fillReorder();
  position.textContent=(active?(chain?`${plan.nodes.length} bifolia · ${active.node}`:`${state.at+1} of ${plan.pages.length} · ${active.folio} · ${active.slot}`):'No pages in this selection')+(plan.custom?' · custom order':'');
  status.textContent=`${heading()} · ${plan.pages.length} ${plan.pages.length===1?'page':'pages'} · ${state.coords} coordinates · ${{body_height:'body-height scale',pixels:'source pixels',paper:'parchment scale, estimated'}[state.scale]}`;
  focus.textContent=active?`${active.node} · ${active.folio} · ${active.panels>1?'slot '+active.position:active.position+'/4'} ${active.slot} · ${active.face} face${active.slot==='Ar'?' · BIFOLIUM START':active.slot==='Bv'?' · BIFOLIUM END':''}${active.panels>1?' · foldout panel':''}`:'';
  focus.style.borderColor=active?color(active.node):'';
  fillSeams();
  if(flowing){
   const records=plan.pages.map(p=>recordOf(p.folio));overlay.width=overlay.height=1;build(records,width);
   const absent=records.filter(r=>!r.selection.available).map(r=>r.folio),unturned=state.tilt!=='none'?records.filter(r=>r.selection.available&&!r.angle.restored).map(r=>r.folio):[];
   notes.dataset.base=(chain?`${plan.nodes.length} bifolia, ${state.columns==='singulion'?'singulion Ar Av Br Bv':'outer Bv Ar, inner Av Br'}. ${{touch:'Rows meet with no added gap, four pages locked together. ',half:'Each row overlaps half of the last: a display choice. ',frames:'Separate fixed frames. '}[state.join]}`:`${plan.pages.length} pages top to bottom, colours by bifolium, one horizontal scale. `)
    +(state.coords==='recorded'?'Recorded coordinates already hold each page\'s tilt. ':{restore:'Each page\'s recorded tilt restored by moving words up or down only, so every x stays as recorded. ',turn:'Recorded tilt restored by a rigid turn, which also leans each margin by the page\'s turn. ',none:'No tilt restored. '}[state.tilt])+(state.scale==='paper'?paperNote(records):{opening:'Opening words at x = 0. ',source:'Source x kept; heights from the opening baselines. ',margin:'Median body margins at x = 0. '}[state.anchor])
    +(chain&&state.columns==='faces'&&state.scale!=='paper'?'The space across each fold is not to scale here: Scale, under Settings, has Parchment. ':'')+(absent.length?`No box on the opening line: ${absent.join(', ')}. `:'')+(unturned.length?`No angle, so no tilt restored: ${unturned.join(', ')}. `:'')+(chain&&state.pages.length?'All mapped pages of each selected bifolium are shown. ':'')+(chain&&plan.pages.some(p=>p.panels>1)?'Foldout panels stack within their slot. ':'');
   if(state.foldMode==='separate'&&chain)notes.dataset.base=notes.dataset.base.replace('four pages locked together.','Ar, Av+Br and Bv advance separately; inner pages stay together.');
   if(T.isHerbal(state.order))notes.dataset.base+=T.studyFrame(state)?'Ten-sheet study configuration: saved opening anchors, body heights and sheet extents; current recorded boxes. f49v is visible but was not scored. ':'Ten-sheet candidate; current registration differs from the saved fit. ';
   notes.textContent=notes.dataset.base;syncOverlaps();
  }else{clearStream();delete notes.dataset.base;paintOverlay(width);}
  save();
  if(pendingJump&&flowing)jump(state.at);pendingJump=false;
 }
 let queued=null;
 const render=()=>queued||(queued=SG.busy('Drawing the pages…',()=>{queued=null;draw();}));
 // ---- the controls
 const here=()=>{state.at=currentIndex();pendingJump=true;};
 ctl.order.onchange=()=>{state=T.selectOrder(state,ctl.order.value);if(T.isHerbal(state.order))selectedAtLoad=[];requested=null;render();};
 $('separateFolds').onchange=()=>{state.foldMode=$('separateFolds').checked?'separate':'shared';render();};
 $('foldPart').onchange=()=>{state.foldPart=$('foldPart').value;syncOverlaps();positionRows();save();};
 ctl.by.onchange=()=>{state.by=ctl.by.value;state.group='all';state.pages=[];state.at=0;render();};
 $('group').onchange=()=>{const v=$('group').value;if(v==='selected'){state.pages=[...selectedAtLoad];state.route='all';}else{state.group=v;state.pages=[];}state.at=0;render();};
 ctl.route.replaceChildren(new Option('Ar → Av → Br → Bv','all'),...T.SLOTS.map(s=>new Option(s+' on each bifolium','slot:'+s)),...T.SLOTS.map(s=>new Option('Candidate correspondence · start '+s,'cycle:'+s)));
 ctl.route.onchange=()=>{state.route=ctl.route.value;state.at=0;render();};
 ctl.view.onchange=()=>{const v=ctl.view.value;here();requested=plan.pages[state.at];state.view=v;if(v==='chain')state.zoom='1';render();};
 for(const k of ['columns','join'])ctl[k].onchange=()=>{here();state[k]=ctl[k].value;render();};
 for(const k of ['trail','anchor','tilt','coords','scale','zoom'])ctl[k].onchange=()=>{state[k]=ctl[k].value;render();};
 ctl.covered.onchange=()=>{state.covered=ctl.covered.value;positionRows();syncOverlaps();save();};
 for(const k of ['words','margins'])$(k).onchange=()=>{state[k]=$(k).checked;render();};
 $('fade').oninput=()=>{state.fade=Number($('fade').value);render();};
 $('strength').oninput=()=>{state.strength=Number($('strength').value);positionRows();syncOverlaps();};$('strength').onchange=save;
 jumpTo.onchange=()=>{state.at=Math.max(0,plan.pages.findIndex(p=>p.node===jumpTo.value));pendingJump=true;render();};
 const step=delta=>{state.at=Math.max(0,Math.min(plan.pages.length-1,currentIndex()+delta));pendingJump=true;render();};
 const stepSheet=delta=>{state.at=T.nextBifolium(plan.pages,currentIndex(),delta);pendingJump=true;render();};
 $('prevPage').onclick=()=>step(-1);$('nextPage').onclick=()=>step(1);$('prevSheet').onclick=()=>stepSheet(-1);$('nextSheet').onclick=()=>stepSheet(1);
 $('first').onclick=()=>{state.at=state.view==='overlay'?plan.pages.length-1:0;if(state.view==='overlay')state.trail='all';pendingJump=true;render();};
 slider.oninput=()=>{state.at=Number(slider.value);pendingJump=true;render();};
 addEventListener('keydown',e=>{if(!e.target.closest('input,select,textarea,[contenteditable=true]')&&['[',']'].includes(e.key)){e.preventDefault();step(e.key===']'?1:-1);}});
 $('seam').onchange=()=>{state.seam=$('seam').value;autoSeam='';state.at=Math.max(0,plan.pages.findIndex(p=>p.node===state.seam.split('>')[1]));pendingJump=true;render();};
 for(const input of [$('overlap'),$('overlapNumber')]){
  input.oninput=()=>{if(input.value!==''&&Number.isFinite(input.valueAsNumber))adjustOverlap(state.seam,input.valueAsNumber/100,false);};
  input.onchange=()=>{if(input.value!==''&&Number.isFinite(input.valueAsNumber))adjustOverlap(state.seam,input.valueAsNumber/100,true);else syncOverlaps();};
 }
 $('resetSeam').onclick=()=>adjustOverlap(state.seam,null);
 $('resetSeams').onclick=()=>{for(const row of sheets)if(row.placement&&row.placement.key)delete (state.foldMode==='separate'?state.folds:state.overlaps)[row.placement.key];positionRows();syncOverlaps();save();};
 $('resetOrder').onclick=()=>{pendingFocus=null;requested=plan.pages[currentIndex()];state.custom=[];pendingJump=true;$('reorderMessage').textContent='Back to the selected order. Overlaps stay with their pairs.';render();};
 // ---- saved boundary sets: in this browser, with JSON as the portable copy
 const presetList=$('presetList'),presetName=$('presetName'),presetMessage=$('presetMessage');
 function readPresets(){const raw=JSON.parse(localStorage.getItem(STORE)||'[]');if(!Array.isArray(raw))throw Error('The saved boundary sets cannot be read. Download your current settings as JSON.');return raw.map(item=>({...T.normalizePreset(item),id:String(item.id),created:item.created,updated:item.updated}));}
 function fillPresets(selected){
  const saved=readPresets();presetList.replaceChildren(new Option('Choose a saved set',''),...saved.map(item=>new Option(item.name,item.id)));
  const chosen=saved.find(x=>x.id===selected);presetList.value=chosen?selected:'';if(chosen)presetName.value=chosen.name;
  $('presetLoad').disabled=$('presetUpdate').disabled=!presetList.value;$('presetSummary').textContent='Saved boundaries'+(saved.length?` · ${saved.length}`:'');
 }
 const snapshot=()=>{const params=T.presetParams(state);if(state.seam===autoSeam)delete params.seam;return T.normalizePreset({schema:T.PRESET_SCHEMA,name:presetName.value.trim()||`${heading()} boundaries`,params});};
 function putPreset(data,replace=false){
  const saved=readPresets(),index=replace?saved.findIndex(x=>x.id===presetList.value):-1;if(replace&&index<0)throw Error('Choose a saved set to update.');
  const used=new Set(saved.filter((_,i)=>i!==index).map(x=>x.name));let title=data.name,n=2;while(used.has(title)){const suffix=` (${n++})`;title=data.name.slice(0,100-suffix.length)+suffix;}
  const now=new Date().toISOString(),item={...data,name:title,id:index<0?crypto.randomUUID():saved[index].id,created:index<0?now:saved[index].created,updated:now};
  if(index<0)saved.push(item);else saved[index]=item;
  localStorage.setItem(STORE,JSON.stringify(saved));localStorage.setItem(LAST,item.id);fillPresets(item.id);presetName.value=item.name;presetMessage.textContent=`Saved “${item.name}” in this browser.`;
 }
 const attempt=fn=>{try{fn();}catch(error){presetMessage.textContent=error.message||'Could not save in this browser. Download JSON instead.';}};
 function applyParams(params){state=T.parse(params);list=T.orderPages(orders,state.order,pages);state=T.clean(state,pages,list);selectedAtLoad=[...state.pages];pendingJump=state.view!=='overlay'&&state.at>0;signature='';render();}
 $('presetSave').onclick=()=>attempt(()=>putPreset(snapshot()));$('presetUpdate').onclick=()=>attempt(()=>putPreset(snapshot(),true));
 presetList.onchange=()=>{$('presetLoad').disabled=$('presetUpdate').disabled=!presetList.value;attempt(()=>{const item=readPresets().find(x=>x.id===presetList.value);if(item){presetName.value=item.name;localStorage.setItem(LAST,item.id);}});};
 $('presetLoad').onclick=()=>attempt(()=>{const item=readPresets().find(x=>x.id===presetList.value);if(!item)throw Error('Choose a saved set.');localStorage.setItem(LAST,item.id);applyParams(item.params);});
 const download=(name,value)=>{const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,1)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);};
 $('presetDownload').onclick=()=>attempt(()=>{const data=snapshot();download(`vms-boundaries-${data.name.replace(/[^a-z0-9]+/gi,'-').replace(/^-|-$/g,'')||'set'}.json`,data);presetMessage.textContent='Boundary set downloaded.';});
 $('presetImport').onclick=()=>$('presetFile').click();
 $('presetFile').onchange=async()=>{const file=$('presetFile').files[0];if(!file)return;try{if(file.size>1000000)throw Error('That file is too large to be a boundary set.');putPreset(T.normalizePreset(JSON.parse(await file.text())));}catch(error){presetMessage.textContent=error.message||'Could not import this file.';}finally{$('presetFile').value='';}};
 // ---- the record of the view: what an analysis needs to place every page and margin point on the plot
 $('exportJson').onclick=()=>{
  const placement=new Map(sheets.map(r=>[r.node,r]));
  download(`page_stream_${state.group}_${state.order}.json`.replace(/[^\w.-]+/g,'_'),{schema:1,tool:'vms-spatial page stream',version:compact.version,bundle:bundleKey,baseline:compact.baseline,provenance:compact.provenance,state:T.serialize(state),order:plan.nodes,custom_order:plan.custom,
   seams:sheets.filter(r=>r.placement?.key).map(r=>({seam:r.placement.key,mode:state.foldMode,overlap:state.foldMode==='shared'?r.placement.overlap:null,manual:r.placement.manual,top_px:r.placement.top,fold_px:state.foldMode==='shared'?r.placement.foldY:null,row_height_px:r.height,groups:r.placement.lanes||null})),
   registration:T.studyFrame(state)?{kind:'saved_1a_study',provenance:T.STUDY.provenance,unscored_pages:['f49v']}:{kind:'current'},
   pages:plan.pages.map((p,i)=>{
    const r=recordOf(p.folio),row=placement.get(p.node),part=parts[i];
    return {folio:p.folio,node:p.node,slot:p.slot,position:p.position,face:p.face,panel:p.panel,available:r.selection.available,angle:r.angle,opening:r.selection.origin,shift:r.selection.shift,factor:r.selection.factor,H:r.selection.H,bounds:r.bounds,
     plot:part?{scale_px:part.frame.s,xmin:part.frame.xmin,ymin:part.frame.ymin,pad_x:part.frame.padX,pad_y:part.frame.padY,top_px:part.frame.plotTop==null?null:part.frame.plotTop,row_top_px:row&&row.placement?row.placement.top:null}:null,
     margin_rows:r.marginRows.map(m=>({line:m.line,locus:m.locus,x:m.x,y:m.y,drawn_x:m.point[0],drawn_y:m.point[1]}))};
   }),
   policy:'One translation per page and an optional uniform body-height scale. Tilt restore adds y + kx, so x is as recorded; tilt turn rotates the page rigidly, so drawn margins lean by the page\'s turn. margin_rows x, y are before the tilt and drawn_x, drawn_y after it. Shared joins translate whole bifolia; separate folds translate Ar, tied Av+Br, and Bv independently. No horizontal seam fitting. Saved 1a fits use study registration, not a new fit. Joins and overlaps are display hypotheses, not recovered physical placement.'});
 };
 // the colours follow the theme; a width change redraws; a pasted link takes effect
 new MutationObserver(()=>render()).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 let resizing=null;addEventListener('resize',()=>{clearTimeout(resizing);resizing=setTimeout(render,200);});
 addEventListener('hashchange',()=>applyParams(SG.hash()));
 attempt(()=>fillPresets(localStorage.getItem(LAST)||''));
 try{await render();}finally{loading.end();}
})();
