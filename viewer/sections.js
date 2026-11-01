"use strict";
// The Sections page: a group's pages laid over each other, with paragraph polygons, marks and the word-box heatmap. Geometry: js/section_math.js.
(async function(){
 const {$,esc}=SG,X=VMS_SECTIONS,Z=COMPARE_STATE,NS='http://www.w3.org/2000/svg';
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const el=(tag,attrs)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs||{}))if(v!=null)n.setAttribute(k,String(v));return n;};
 const figure=$('figure'),status=$('status'),notes=$('notes'),legend=$('heatLegend'),pageKey=$('pageKey'),sliders=$('sliders'),editor=$('editor');
 const ctl={by:$('by'),group:$('group'),align:$('align'),anchor:$('anchor'),color:$('color'),coords:$('coords'),scale:$('scale'),cell:$('cell'),palette:$('palette')};
 const LAYER_LABELS={heatmap:'Heatmap',polygons:'Paragraph polygons',boxes:'Word boxes',breaks:'Breaks',starts:'Paragraph starts',ends:'Paragraph ends'};
 let state=X.parse(SG.hash()),pages,words,tokens,list,view=null,full=null,drawn=[],editTarget='';
 const cache=new Map(),undo=new Map(),SLACK=.85;    // the view may be dragged this far past the frame: pages can leave the margin, and a part always stays in sight
 const loading=SG.busyStart('Loading the manuscript…');
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  const index=await SG.load(SG.dataUrl('index.json')),C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const bundle=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];
  const [compact,orders,data]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(bundle.path))]);
  pages=compact.pages;words=data.words;tokens=X.lineTokens(data.lines);list=Z.pageList(orders,'bifolia',pages);
 }catch(error){loading.end();status.textContent='Could not load the page data.';SG.error(figure,error);return;}
 state.edits=X.cleanEdits(pages,list,state.edits);
 const save=()=>SG.setHash({data:SG.hash().data,...X.serialize(state)});
 const dark=()=>{const c=getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();return parseInt(c.slice(1,3),16)<128;};
 const editKey=name=>X.editKey(state.by,name),customized=()=>X.groups(pages,list,state.by).map(g=>X.customize(g,list,state.edits[editKey(g.name)]));
 const label=name=>name==='—'?'Unassigned':name,keyOf=f=>X.colorKey(state.color,f,pages[f]);
 function entry(folio){
  const key=[folio,state.align,state.anchor,state.coords,state.scale].join('|');
  if(!cache.has(key))cache.set(key,X.extract(folio,pages[folio],words,tokens,{align:state.align,anchor:state.anchor,coordinates:state.coords,scale:state.scale}));
  return cache.get(key);
 }
 // ---- the marks of one page
 const on=k=>state.layers.includes(k);
 function drawPage(e,color){
  const key=keyOf(e.folio),g=el('g',{class:'pg'+(state.focus===key?' on':''),'data-key':key,style:'--c:'+color});
  if(on('boxes')&&e.boxes.length)g.append(el('path',{class:'boxes',d:e.boxes.map(b=>`M${b.rect[0]} ${b.rect[1]}H${b.rect[2]}V${b.rect[3]}H${b.rect[0]}Z`).join('')}));
  if(on('polygons'))for(const p of e.paragraphs)for(const area of p.polygons)g.append(el('polygon',{class:'poly',points:area.points.map(q=>q[0].toFixed(1)+','+q[1].toFixed(1)).join(' '),'data-tip':`<b>${esc(e.folio)}</b> · paragraph ${esc(p.key.slice(1))}<div class="tipsub">${area.lines.length} ${area.lines.length===1?'line':'lines'}, loci ${esc(area.loci[0])} to ${esc(area.loci[area.loci.length-1])}</div>`}));
  const line=(f,tail)=>`M${f.x1} ${f.y1}L${f.x2} ${f.y2}${tail||''}`;
  const mark=(type,cls,tail,name)=>{const fs=e.features.filter(f=>f.type===type);if(fs.length)g.append(el('path',{class:'mark '+cls,d:fs.map(f=>line(f,tail(f))).join(''),'data-tip':`<b>${esc(e.folio)}</b> · ${fs.length} ${name}`}));};
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
 // ---- the colours of a group: one chip a colour, click to pick it out, × to take its pages out of the view
 function chips(g,colors){
  const by=new Map();for(const f of g.pages){const k=keyOf(f);if(!by.has(k))by.set(k,[]);by.get(k).push(f);}
  return [...by].map(([key,folios])=>{
   const wrap=h('span','chip-wrap'),b=h('button','chip'+(state.focus===key?' on':''),state.color==='page'?key:`${label(key)} (${folios.length})`),x=h('button','chip-x','×');
   b.type=x.type='button';b.dataset.key=key;b.style.setProperty('--c',X.hue(colors.get(key)));b.title=folios.join(', ');b.setAttribute('aria-pressed',String(state.focus===key));
   b.onclick=()=>setFocus(state.focus===key?'':key);
   x.setAttribute('aria-label',`Remove ${key} from ${g.name}`);x.title='Remove from this view';x.onclick=()=>setIncluded(g.name,folios,false);
   wrap.append(b,x);return wrap;});
 }
 // ---- a group's panel
 function drawGroup(g,F,many){
  const entries=g.pages.map(entry),colors=X.colorIndex(state.color,g.universe,pages),wrap=h('div','panel'),head=h('h3');
  const unaligned=entries.filter(e=>!e.available).map(e=>e.folio),title=h('span');
  if(many){const b=h('button','group-open',label(g.name));b.type='button';b.title='Show '+label(g.name)+' alone';b.onclick=()=>{state.group=g.name;state.focus='';render();};const edit=h('button','panel-edit','Edit pages');edit.type='button';edit.onclick=()=>openEditor(g.name);title.append(b,edit);}else title.textContent=label(g.name);
  head.append(title,h('span','count',`${g.pages.length} ${g.pages.length===1?'page':'pages'}`+(g.added.length||g.removed.length?` · edited, ${g.added.length} added, ${g.removed.length} removed`:'')+(unaligned.length?` · ${unaligned.length} not aligned`:'')));
  const svg=el('svg',{viewBox:`${F.x} ${F.y} ${F.w} ${F.h}`,role:'img','aria-label':'Composite of '+g.name});
  let occ=null;
  if(on('heatmap')){occ=X.occupancy(entries,Number(state.cell));occ.index=new Map(occ.cells.map(c=>[c.ix+','+c.iy,c]));const img=drawHeat(occ);if(img)svg.append(img);}
  for(const e of entries)if(e.available)svg.append(drawPage(e,X.hue(colors.get(keyOf(e.folio)))));
  svg.addEventListener('mousemove',e=>{if(occ&&!(e.target instanceof Element&&e.target.dataset.tip))heatTip(e,svg,occ);});
  svg.addEventListener('mouseleave',()=>SG.hideTip());
  wrap.append(head,svg);
  if(!entries.some(e=>e.boxes.length))wrap.append(h('p','note',g.pages.length?'No horizontal text to draw here. Rings and rays are in the Wheels view of Compare.':'No pages in this view. Edit pages to add some.'));
  if(many&&g.pages.length){const d=h('details','page-key'),s=h('summary','',`Page colours · ${colors.size&&new Set(g.pages.map(keyOf)).size}`),c=h('div','chips');c.append(...chips(g,colors));d.append(s,c);wrap.append(d);}
  return {wrap,svg,entries,occ,colors,unaligned,group:g};
 }
 function renderKey(d){
  pageKey.hidden=!d;if(!d)return;
  const n=new Set(d.group.pages.map(keyOf)).size,noun={page:'page',bifolium:'bifolium',group:'Golf group',section:'section'}[state.color];
  $('pageKeySummary').textContent=`Page colours · ${n} ${n===1?noun:noun==='bifolium'?'bifolia':noun+'s'}`;
  $('pageChips').replaceChildren(...chips(d.group,d.colors));
 }
 const focusFolios=()=>{const f=new Set();for(const d of drawn)for(const p of d.group.pages)if(keyOf(p)===state.focus)f.add(p);return [...f];};
 function renderFocus(){
  const folios=state.focus?focusFolios():[],bar=$('focusBar');bar.hidden=!folios.length;
  if(!folios.length)return;
  const count=drawn.flatMap(d=>d.entries).filter(e=>keyOf(e.folio)===state.focus).reduce((n,e)=>n+e.paragraphs.reduce((m,p)=>m+p.polygons.length,0),0);
  $('focusLabel').innerHTML=`Picked out: <b>${esc(label(state.focus))}</b> · ${folios.length>6?folios.length+' pages':esc(folios.join(', '))} · ${count} paragraph ${count===1?'polygon':'polygons'}`;
  $('removeFocus').hidden=drawn.length>1;
 }
 function setFocus(key){
  state.focus=key;figure.classList.toggle('focused',!!key);
  for(const svg of figure.querySelectorAll('svg'))for(const g of [...svg.querySelectorAll('.pg')]){const hit=g.dataset.key===key;g.classList.toggle('on',hit);if(hit)svg.append(g);}
  for(const c of document.querySelectorAll('.sections .chip')){const hit=c.dataset.key===key;c.classList.toggle('on',hit);c.setAttribute('aria-pressed',String(hit));}
  renderFocus();save();
 }
 function renderLegend(){
  legend.hidden=!on('heatmap');if(!on('heatmap'))return;
  const colors=X.ramp(state.palette,dark());
  legend.replaceChildren(h('span','legend-title','Share of the group\'s pages with a word box in the cell'),...colors.map((c,i)=>{const s=h('span','swatch-cell',`${i*10}–${(i+1)*10}%`);s.style.setProperty('--swatch',c);return s;}));
 }
 // ---- adding and removing pages
 function saveEdit(name,change){
  const k=editKey(name),history=undo.get(k)||[];history.push(state.edits[k]?JSON.parse(JSON.stringify(state.edits[k])):null);if(history.length>20)history.shift();undo.set(k,history);
  if(change&&(change.add.length||change.remove.length))state.edits[k]=change;else delete state.edits[k];
  render();
 }
 function setIncluded(name,folios,include){const g=customized().find(x=>x.name===name);if(g)saveEdit(name,X.included(g,list,folios,include));}
 function editorSync(){
  if(editor.hidden)return;
  const gs=customized();if(!gs.some(g=>g.name===editTarget))editTarget=state.group==='all'?gs[0].name:state.group;
  $('editGroupLabel').hidden=state.group!=='all';$('editGroup').replaceChildren(...gs.map(g=>new Option(label(g.name),g.name)));$('editGroup').value=editTarget;
  const g=gs.find(x=>x.name===editTarget),selected=new Set(g.pages),base=new Set(g.original),colors=X.colorIndex(state.color,g.universe,pages),unit=$('editUnit').value;
  const rows=unit==='pages'?list.map(f=>({id:f,ids:[f],info:`${pages[f].node} · ${pages[f].section} · Golf ${pages[f].group}`})):[...new Set(list.map(f=>pages[f].node))].map(node=>{const ids=list.filter(f=>pages[f].node===node);return {id:node,ids,info:ids.join(' · ')+' · '+[...new Set(ids.map(f=>pages[f].section))].join(', ')};});
  const query=$('editSearch').value.trim().toLowerCase(),plain=s=>s.replace(/[^a-z0-9]/g,''),matches=r=>{const text=(r.id+' '+r.info).toLowerCase();return text.includes(query)||(plain(query)&&plain(text).includes(plain(query)));};
  const shown=rows.filter(r=>query?matches(r):$('editScope').value==='all'||r.ids.some(f=>base.has(f)||selected.has(f))),list2=$('memberList'),top=list2.scrollTop;
  list2.replaceChildren(...shown.map(r=>{
   const n=r.ids.filter(f=>selected.has(f)).length,row=h('label','member'),c=h('input'),text=h('span');c.type='checkbox';c.checked=n===r.ids.length;c.indeterminate=n>0&&n<r.ids.length;
   c.setAttribute('aria-label',`Include ${r.id} in ${label(editTarget)}`);c.onchange=()=>setIncluded(editTarget,r.ids,c.checked);
   if(unit==='pages')row.style.setProperty('--c',X.hue(colors.get(keyOf(r.id))));
   text.append(h('b','',r.id),h('small','',unit==='bifolia'?`${n} of ${r.ids.length} pages · ${r.info}`:r.info+(base.has(r.id)?'':' · outside this group')));row.append(c,text);return row;}));
  if(!shown.length)list2.append(h('p','note','No matching pages or bifolia.'));
  list2.scrollTop=top;
  $('editNote').textContent=`${g.pages.length} selected: ${g.original.length-g.removed.length} of the group's ${g.original.length}, plus ${g.added.length} added. Check to include, uncheck to remove. The changes are saved in the link.`;
  $('editUndo').disabled=!(undo.get(editKey(editTarget))||[]).length;$('editReset').disabled=!state.edits[editKey(editTarget)];
 }
 function openEditor(name){editTarget=name||(state.group==='all'?customized()[0].name:state.group);editor.hidden=false;$('editButton').setAttribute('aria-expanded','true');$('editSearch').value='';$('memberList').scrollTop=0;editorSync();}
 function closeEditor(){editor.hidden=true;$('editButton').setAttribute('aria-expanded','false');}
 $('editButton').onclick=()=>editor.hidden?openEditor():closeEditor();$('editClose').onclick=closeEditor;
 $('editGroup').onchange=()=>{editTarget=$('editGroup').value;$('editSearch').value='';$('memberList').scrollTop=0;editorSync();};
 for(const id of ['editUnit','editScope'])$(id).onchange=()=>{$('memberList').scrollTop=0;editorSync();};
 $('editSearch').oninput=()=>{$('memberList').scrollTop=0;editorSync();};
 $('editReset').onclick=()=>saveEdit(editTarget,null);
 $('editUndo').onclick=()=>{const k=editKey(editTarget),history=undo.get(k);if(!history||!history.length)return;const previous=history.pop();if(previous)state.edits[k]=previous;else delete state.edits[k];render();};
 // ---- the view
 function applyView(){if(!full)return;if(view&&Z.isFit(view,full))view=null;const v=view||full;for(const p of drawn)p.svg.setAttribute('viewBox',`${v.x} ${v.y} ${v.w} ${v.h}`);$('zoomLevel').textContent=view?Z.zoomScale(view,full).toFixed(1).replace(/\.0$/,'')+'×':'';}
 function applyOpacity(){for(const [k] of X.OPACITY)figure.style.setProperty('--o-'+k,String(state.op[k]/100));legend.style.setProperty('--o-heatmap',String(state.op.heatmap/100));}
 // every change redraws, and several changes in one frame redraw once
 let queued=null;
 const render=()=>queued||(queued=SG.busy('Drawing the pages…',()=>{queued=null;draw();}));
 function draw(){
  const all=customized();
  ctl.group.replaceChildren(new Option('All groups','all'),...all.map(g=>new Option(`${label(g.name)} (${g.pages.length})${g.added.length||g.removed.length?' · edited':''}`,g.name)));
  if(state.group!=='all'&&!all.some(g=>g.name===state.group))state.group=all[0].name;
  ctl.group.value=state.group;
  const shown=state.group==='all'?all:all.filter(g=>g.name===state.group),many=shown.length>1;
  if(state.focus&&!shown.some(g=>g.pages.some(f=>keyOf(f)===state.focus)))state.focus='';
  const box=X.bounds(shown.flatMap(g=>g.pages.map(entry)))||{x0:0,y0:0,x1:100,y1:100},pad=24,F={x:box.x0-pad,y:box.y0-pad,w:box.x1-box.x0+2*pad,h:box.y1-box.y0+2*pad};
  view=view?Z.clampView(view,F,SLACK):null;full=F;
  drawn=shown.map(g=>drawGroup(g,F,many));
  figure.style.setProperty('--panels',String(many?3:1));figure.classList.toggle('grid',many);figure.classList.toggle('focused',!!state.focus);
  figure.replaceChildren(...drawn.map(d=>d.wrap));for(const d of drawn)SG.attachTips(d.wrap);
  for(const svg of figure.querySelectorAll('svg'))for(const g of [...svg.querySelectorAll('.pg.on')])svg.append(g);
  applyOpacity();applyView();renderLegend();renderKey(many?null:drawn[0]);renderFocus();editorSync();
  const views=shown.reduce((n,g)=>n+g.pages.length,0),distinct=new Set(shown.flatMap(g=>g.pages)).size,entries=drawn.flatMap(d=>d.entries),polys=entries.reduce((n,e)=>n+e.paragraphs.reduce((m,p)=>m+p.polygons.length,0),0),skipped=[...new Set(drawn.flatMap(d=>d.unaligned))],left=entries.reduce((n,e)=>n+e.stats.omittedParagraphs,0);
  status.textContent=`${many?'All groups':label(shown[0].name)} · ${views===distinct?distinct+' pages':views+' page appearances, '+distinct+' distinct pages'} · ${polys.toLocaleString('en-US')} paragraph polygons · ${state.align==='page'?'page positions':'all paragraph starts'} · ${state.coords} coordinates`+(on('heatmap')?` · ${state.cell}-unit cells`:'');
  notes.textContent=(skipped.length?`Not aligned, so not drawn, but still counted in the heatmap's pages: ${skipped.join(', ')}. `:'')+(left?`${left} paragraphs have no complete horizontal anchor line and are left out. `:'');
  save();
 }
 // ---- the controls
 for(const k of ['by','align','anchor','color','coords','scale','cell','palette'])ctl[k].value=state[k];
 ctl.by.onchange=()=>{state.by=ctl.by.value;state.group='';state.focus='';render();};
 ctl.group.onchange=()=>{state.group=ctl.group.value;state.focus='';render();};
 ctl.color.onchange=()=>{state.color=ctl.color.value;state.focus='';render();};
 for(const k of ['align','anchor','coords','scale','cell','palette'])ctl[k].onchange=()=>{state[k]=ctl[k].value;render();};
 const stepGroup=d=>{const names=['all',...X.groups(pages,list,state.by).map(g=>g.name)],i=names.indexOf(state.group),n=names.length;state.group=names[((i+d)%n+n)%n];state.focus='';render();};
 $('prevGroup').onclick=()=>stepGroup(-1);$('nextGroup').onclick=()=>stepGroup(1);
 $('layers').append(...X.LAYERS.map(k=>{const l=h('label','check'),c=h('input');c.type='checkbox';c.checked=on(k);c.onchange=()=>{state.layers=X.LAYERS.filter(x=>x===k?c.checked:state.layers.includes(x));render();};l.append(c,document.createTextNode(' '+LAYER_LABELS[k]));return l;}));
 function buildSliders(){
  sliders.replaceChildren(...X.OPACITY.map(([k,name])=>{const l=h('label','slider'),r=h('input'),v=h('span','pct',state.op[k]+'%');r.type='range';r.min='0';r.max='100';r.step='1';r.value=String(state.op[k]);r.setAttribute('aria-label',name+' opacity');
   r.oninput=()=>{state.op[k]=Number(r.value);v.textContent=r.value+'%';applyOpacity();save();};l.append(h('span','name',name),r,v);return l;}));
 }
 buildSliders();
 $('resetOpacity').onclick=()=>{state.op={...X.OPACITY_DEFAULTS};buildSliders();applyOpacity();save();};
 $('clearFocus').onclick=()=>setFocus('');
 $('removeFocus').onclick=()=>{const g=drawn[0]&&drawn[0].group;if(g)setIncluded(g.name,focusFolios(),false);};
 addEventListener('keydown',e=>{if(e.key==='Escape'&&state.focus)setFocus('');});
 figure.addEventListener('click',e=>{const t=e.target instanceof Element?e.target.closest('.pg'):null;if(t&&!dragged)setFocus(state.focus===t.dataset.key?'':t.dataset.key);});
 // zoom and pan, shared by the panels
 const toUser=(svg,e)=>{const m=svg.getScreenCTM();if(!m)return {x:0,y:0};const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse());return {x:p.x,y:p.y};};
 const centre=v=>({x:v.x+v.w/2,y:v.y+v.h/2});
 figure.addEventListener('wheel',e=>{const svg=e.target instanceof Element?e.target.closest('svg'):null;if(!svg||!full)return;e.preventDefault();view=Z.zoomAt(view||full,full,e.deltaY<0?1.25:.8,toUser(svg,e),SLACK);applyView();},{passive:false});
 let drag=null,dragged=false;
 figure.addEventListener('pointerdown',e=>{const svg=e.target instanceof Element?e.target.closest('svg'):null;dragged=false;if(!svg||e.button!==0||!full)return;const m=svg.getScreenCTM();drag={x:e.clientX,y:e.clientY,view:view||full,s:m?m.a:1,id:e.pointerId};});
 addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!dragged&&Math.hypot(dx,dy)<4)return;dragged=true;view=Z.pan(drag.view,full,dx,dy,drag.s,SLACK);applyView();});
 const endDrag=e=>{if(drag&&e.pointerId===drag.id)drag=null;};addEventListener('pointerup',endDrag);addEventListener('pointercancel',endDrag);
 $('zoomFit').onclick=()=>{view=null;applyView();};
 $('zoomIn').onclick=()=>{if(full){const v=view||full;view=Z.zoomAt(v,full,1.25,centre(v),SLACK);applyView();}};
 $('zoomOut').onclick=()=>{if(full){const v=view||full;view=Z.zoomAt(v,full,.8,centre(v),SLACK);applyView();}};
 // the heatmap's colours follow the theme
 new MutationObserver(()=>render()).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 if(!state.group)state.group=X.groups(pages,list,state.by)[0].name;
 try{await render();}finally{loading.end();}
})();
