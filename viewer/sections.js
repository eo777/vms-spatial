"use strict";
// The Sections page: a group's pages laid over each other, with paragraph polygons, marks and the word-box heatmap. Geometry: js/section_math.js.
(async function(){
 const {$,esc}=SG,X=VMS_SECTIONS,Z=COMPARE_STATE,NS='http://www.w3.org/2000/svg';
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const el=(tag,attrs)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs||{}))if(v!=null)n.setAttribute(k,String(v));return n;};
 const figure=$('figure'),status=$('status'),notes=$('notes'),legend=$('heatLegend'),pageKey=$('pageKey'),sliders=$('sliders');
 const ctl={by:$('by'),group:$('group'),align:$('align'),anchor:$('anchor'),color:$('color'),coords:$('coords'),scale:$('scale'),cell:$('cell'),palette:$('palette')};
 const LAYER_LABELS={heatmap:'Heatmap',polygons:'Paragraph polygons',boxes:'Word boxes',breaks:'Breaks',starts:'Paragraph starts',ends:'Paragraph ends'};
 let state=X.parse(SG.hash()),pages,words,tokens,list,view=null,full=null,drawn=[];
 const cache=new Map();
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  const index=await SG.load(SG.dataUrl('index.json')),C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const bundle=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];
  const [compact,orders,data]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(bundle.path))]);
  pages=compact.pages;words=data.words;tokens=X.lineTokens(data.lines);list=Z.pageList(orders,'bifolia',pages);
 }catch(error){status.textContent='Could not load the page data.';SG.error(figure,error);return;}
 const save=()=>SG.setHash({data:SG.hash().data,...X.serialize(state)});
 const dark=()=>{const c=getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();return parseInt(c.slice(1,3),16)<128;};
 function entry(folio){
  const key=[folio,state.align,state.anchor,state.coords,state.scale].join('|');
  if(!cache.has(key))cache.set(key,X.extract(folio,pages[folio],words,tokens,{align:state.align,anchor:state.anchor,coordinates:state.coords,scale:state.scale}));
  return cache.get(key);
 }
 // ---- the marks of one page
 const on=k=>state.layers.includes(k);
 function drawPage(e,color){
  const g=el('g',{class:'pg'+(state.focus===e.folio?' on':''),'data-page':e.folio,style:'--c:'+color});
  if(on('boxes')&&e.boxes.length)g.append(el('path',{class:'boxes',d:e.boxes.map(b=>`M${b.rect[0]} ${b.rect[1]}H${b.rect[2]}V${b.rect[3]}H${b.rect[0]}Z`).join('')}));
  if(on('polygons'))for(const p of e.paragraphs)for(const area of p.polygons)g.append(el('polygon',{class:'poly',points:area.points.map(q=>q[0].toFixed(1)+','+q[1].toFixed(1)).join(' '),'data-tip':`<b>${esc(e.folio)}</b> · paragraph ${esc(p.key.slice(1))}<div class="tipsub">${area.lines.length} ${area.lines.length===1?'line':'lines'}, loci ${esc(area.loci[0])} to ${esc(area.loci[area.loci.length-1])}</div>`}));
  const line=(f,tail)=>`M${f.x1} ${f.y1}L${f.x2} ${f.y2}${tail||''}`;
  const mark=(type,cls,tail,label)=>{const fs=e.features.filter(f=>f.type===type);if(fs.length)g.append(el('path',{class:'mark '+cls,d:fs.map(f=>line(f,tail(f))).join(''),'data-tip':`<b>${esc(e.folio)}</b> · ${fs.length} ${label}`}));};
  if(on('breaks'))mark('break','breaks',()=>'','annotated breaks');
  if(on('starts'))mark('start','starts',f=>`M${f.x1} ${f.y1-8}l10 8l-10 8Z`,'paragraph starts');
  if(on('ends'))mark('end','ends',f=>`M${f.x2-6} ${f.y2-6}h12v12h-12Z`,'paragraph ends');
  return g;
 }
 // ---- the heatmap: one image, one pixel a cell, so that thousands of cells stay fast and the page remains responsive
 function drawHeat(occ){
  if(!occ.cells.length)return null;
  const ix=occ.cells.map(c=>c.ix),iy=occ.cells.map(c=>c.iy),x0=Math.min(...ix),y0=Math.min(...iy),w=Math.max(...ix)-x0+1,h2=Math.max(...iy)-y0+1,canvas=document.createElement('canvas');
  canvas.width=w;canvas.height=h2;
  const ctx=canvas.getContext('2d'),colors=X.ramp(state.palette,dark());
  for(const c of occ.cells){ctx.fillStyle=colors[X.band(c.percent)];ctx.fillRect(c.ix-x0,c.iy-y0,1,1);}
  return el('image',{class:'heat',href:canvas.toDataURL(),x:x0*occ.cellSize,y:y0*occ.cellSize,width:w*occ.cellSize,height:h2*occ.cellSize,preserveAspectRatio:'none'});
 }
 function heatTip(e,svg,occ){
  const m=svg.getScreenCTM();if(!m)return;
  const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse()),ix=Math.floor(p.x/occ.cellSize),iy=Math.floor(p.y/occ.cellSize),c=occ.index.get(ix+','+iy);
  if(!c){SG.hideTip();return;}
  SG.showTip(`<b>${c.count} of ${occ.denominator} pages</b> · ${c.percent.toFixed(1)}%<div class="tipsub">${esc(c.folios.slice(0,14).join(', '))}${c.folios.length>14?` and ${c.folios.length-14} more`:''}</div>`,e.clientX,e.clientY);
 }
 // ---- a group's panel
 function drawGroup(g,F,many){
  const entries=g.pages.map(entry),index=X.colorIndex(state.color,entries),wrap=h('div','panel'),head=h('h3');
  const unaligned=entries.filter(e=>!e.available).map(e=>e.folio);
  if(many){const b=h('button','group-open',g.name);b.type='button';b.title='Show '+g.name+' alone';b.onclick=()=>{state.group=g.name;render();};head.append(b);}else head.append(h('span','',g.name));
  head.append(h('span','count',`${g.pages.length} ${g.pages.length===1?'page':'pages'}`+(unaligned.length?` · ${unaligned.length} not aligned`:'')));
  const svg=el('svg',{viewBox:`${F.x} ${F.y} ${F.w} ${F.h}`,role:'img','aria-label':'Composite of '+g.name});
  let occ=null;
  if(on('heatmap')){occ=X.occupancy(entries,Number(state.cell));occ.index=new Map(occ.cells.map(c=>[c.ix+','+c.iy,c]));const img=drawHeat(occ);if(img)svg.append(img);}
  for(const e of entries)if(e.available)svg.append(drawPage(e,X.hue(index.get(e.folio))));
  svg.addEventListener('mousemove',e=>{if(occ&&!(e.target instanceof Element&&e.target.dataset.tip))heatTip(e,svg,occ);});
  svg.addEventListener('mouseleave',()=>SG.hideTip());
  wrap.append(head,svg);
  if(!entries.some(e=>e.boxes.length))wrap.append(h('p','note','No horizontal text to draw here. Rings and rays are in the Wheels view of Compare.'));
  return {wrap,svg,entries,occ,index,unaligned};
 }
 // ---- the page key: a chip per page, click to pick one out
 function renderKey(d){
  pageKey.hidden=!d;if(!d)return;
  const seen=$('pageChips');seen.replaceChildren(...d.entries.map(e=>{const b=h('button','chip'+(state.focus===e.folio?' on':''),e.folio);b.type='button';b.style.setProperty('--c',X.hue(d.index.get(e.folio)));if(!e.available){b.disabled=true;b.title='Not aligned';}b.onclick=()=>setFocus(state.focus===e.folio?'':e.folio);return b;}));
 }
 function setFocus(folio){state.focus=folio;figure.classList.toggle('focused',!!folio);for(const g of figure.querySelectorAll('.pg'))g.classList.toggle('on',g.dataset.page===folio);for(const c of pageKey.querySelectorAll('.chip'))c.classList.toggle('on',c.textContent===folio);save();}
 function renderLegend(){
  legend.hidden=!on('heatmap');if(!on('heatmap'))return;
  const colors=X.ramp(state.palette,dark());
  legend.replaceChildren(h('span','legend-title','Share of the group\'s pages with a word box in the cell'),...colors.map((c,i)=>{const s=h('span','swatch-cell',`${i*10}–${(i+1)*10}%`);s.style.setProperty('--swatch',c);return s;}));
 }
 // ---- the view
 function applyView(){if(!full)return;if(view&&Z.isFit(view,full))view=null;const v=view||full;for(const p of drawn)p.svg.setAttribute('viewBox',`${v.x} ${v.y} ${v.w} ${v.h}`);$('zoomLevel').textContent=view?Z.zoomScale(view,full).toFixed(1).replace(/\.0$/,'')+'×':'';}
 function applyOpacity(){for(const [k] of X.OPACITY)figure.style.setProperty('--o-'+k,String(state.op[k]/100));legend.style.setProperty('--o-heatmap',String(state.op.heatmap/100));}
 function render(){
  const all=X.groups(pages,list,state.by);
  ctl.group.replaceChildren(new Option('All groups','all'),...all.map(g=>new Option(`${state.by==='golf'?g.name+' ':''}${state.by==='golf'?'':g.name+' '}(${g.pages.length})`,g.name)));
  if(state.group!=='all'&&!all.some(g=>g.name===state.group))state.group=all[0].name;
  ctl.group.value=state.group;
  const shown=state.group==='all'?all:all.filter(g=>g.name===state.group),many=shown.length>1,box=X.bounds(shown.flatMap(g=>g.pages.map(entry)))||{x0:0,y0:0,x1:100,y1:100},pad=24;
  const F={x:box.x0-pad,y:box.y0-pad,w:box.x1-box.x0+2*pad,h:box.y1-box.y0+2*pad};
  view=view?Z.clampView(view,F):null;full=F;
  drawn=shown.map(g=>drawGroup(g,F,many));
  figure.style.setProperty('--panels',String(many?3:1));figure.classList.toggle('grid',many);figure.classList.toggle('focused',!!state.focus);
  figure.replaceChildren(...drawn.map(d=>d.wrap));for(const d of drawn)SG.attachTips(d.svg);
  applyOpacity();applyView();renderLegend();renderKey(many?null:drawn[0]);
  const count=shown.reduce((n,g)=>n+g.pages.length,0),entries=drawn.flatMap(d=>d.entries),polys=entries.reduce((n,e)=>n+e.paragraphs.reduce((m,p)=>m+p.polygons.length,0),0),skipped=[...new Set(drawn.flatMap(d=>d.unaligned))],left=entries.reduce((n,e)=>n+e.stats.omittedParagraphs,0);
  status.textContent=`${many?'All groups':shown[0].name} · ${count} pages · ${polys.toLocaleString('en-US')} paragraph polygons · ${state.align==='page'?'page positions':'all paragraph starts'} · ${state.coords} coordinates`+(on('heatmap')?` · ${state.cell}-unit cells`:'');
  notes.textContent=(skipped.length?`Not aligned, so not drawn, but still counted in the heatmap's pages: ${skipped.join(', ')}. `:'')+(left?`${left} paragraphs have no complete horizontal anchor line and are left out. `:'');
  save();
 }
 // ---- the controls
 for(const k of ['by','align','anchor','color','coords','scale','cell','palette'])ctl[k].value=state[k];
 ctl.by.onchange=()=>{state.by=ctl.by.value;state.group='';state.focus='';render();};
 ctl.group.onchange=()=>{state.group=ctl.group.value;state.focus='';render();};
 for(const k of ['align','anchor','color','coords','scale','cell','palette'])ctl[k].onchange=()=>{state[k]=ctl[k].value;render();};
 const stepGroup=d=>{const names=['all',...X.groups(pages,list,state.by).map(g=>g.name)],i=names.indexOf(state.group),n=names.length;state.group=names[((i+d)%n+n)%n];state.focus='';render();};
 $('prevGroup').onclick=()=>stepGroup(-1);$('nextGroup').onclick=()=>stepGroup(1);
 $('layers').append(...X.LAYERS.map(k=>{const l=h('label','check'),c=h('input');c.type='checkbox';c.checked=on(k);c.onchange=()=>{state.layers=X.LAYERS.filter(x=>x===k?c.checked:state.layers.includes(x));render();};l.append(c,document.createTextNode(' '+LAYER_LABELS[k]));return l;}));
 function buildSliders(){
  sliders.replaceChildren(...X.OPACITY.map(([k,label])=>{const l=h('label','slider'),r=h('input'),v=h('span','pct',state.op[k]+'%');r.type='range';r.min='0';r.max='100';r.step='1';r.value=String(state.op[k]);r.setAttribute('aria-label',label+' opacity');
   r.oninput=()=>{state.op[k]=Number(r.value);v.textContent=r.value+'%';applyOpacity();save();};l.append(h('span','name',label),r,v);return l;}));
 }
 buildSliders();
 $('resetOpacity').onclick=()=>{state.op={...X.OPACITY_DEFAULTS};buildSliders();applyOpacity();save();};
 $('clearFocus').onclick=()=>setFocus('');
 addEventListener('keydown',e=>{if(e.key==='Escape'&&state.focus)setFocus('');});
 figure.addEventListener('click',e=>{const t=e.target instanceof Element?e.target.closest('.pg'):null;if(t&&!dragged)setFocus(state.focus===t.dataset.page?'':t.dataset.page);});
 // zoom and pan, shared by the panels
 const toUser=(svg,e)=>{const m=svg.getScreenCTM();if(!m)return {x:0,y:0};const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse());return {x:p.x,y:p.y};};
 const centre=v=>({x:v.x+v.w/2,y:v.y+v.h/2});
 figure.addEventListener('wheel',e=>{const svg=e.target instanceof Element?e.target.closest('svg'):null;if(!svg||!full)return;e.preventDefault();view=Z.zoomAt(view||full,full,e.deltaY<0?1.25:.8,toUser(svg,e));applyView();},{passive:false});
 let drag=null,dragged=false;
 figure.addEventListener('pointerdown',e=>{const svg=e.target instanceof Element?e.target.closest('svg'):null;dragged=false;if(!svg||e.button!==0||!full)return;const m=svg.getScreenCTM();drag={x:e.clientX,y:e.clientY,view:view||full,s:m?m.a:1,id:e.pointerId};});
 addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!dragged&&Math.hypot(dx,dy)<4)return;dragged=true;view=Z.pan(drag.view,full,dx,dy,drag.s);applyView();});
 const endDrag=e=>{if(drag&&e.pointerId===drag.id)drag=null;};addEventListener('pointerup',endDrag);addEventListener('pointercancel',endDrag);
 $('zoomFit').onclick=()=>{view=null;applyView();};
 $('zoomIn').onclick=()=>{if(full){const v=view||full;view=Z.zoomAt(v,full,1.25,centre(v));applyView();}};
 $('zoomOut').onclick=()=>{if(full){const v=view||full;view=Z.zoomAt(v,full,.8,centre(v));applyView();}};
 // the heatmap's colours follow the theme
 new MutationObserver(()=>render()).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 if(!state.group)state.group=X.groups(pages,list,state.by)[0].name;
 render();
})();
