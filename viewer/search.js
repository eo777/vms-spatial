"use strict";
// The Word search page: every bifolium as a small tile of its pages, with the words that match each pattern lit up, in any order of sheets. Patterns, tiles and the address: js/pattern_math.js.
(async function(){
 const {$,esc,int}=SG,T=VMS_STREAM,X=VMS_SECTIONS,Z=COMPARE_STATE,P=VMS_PATTERN;
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const host=$('tiles'),status=$('status'),message=$('message'),notes=$('notes'),rows=$('rows'),dialog=$('pageDialog'),figure=$('pageFigure');
 const ctl={by:$('by'),order:$('order'),columns:$('columns'),size:$('size')},STORE='vms-boundary-presets-v1',BAND=.56,BAND_TOP=.3;   // a tile draws a box from 30% to 86% of its height, or the lines of a page run together at this size
 const EXAMPLES=['*aiin','qok*','[li]p*','*y AND 1:qo*','[pgi]*'];
 const SYNTAX=[[['*'],'any letters, or none','*aiin'],[['?'],'one character','ch?y'],[['AND','&'],'both','qok* AND *y'],[['OR','|'],'either','chol OR chor'],[['NOT','!'],'not; binds before AND, AND before OR','*y AND NOT qo*'],[['( )'],'group','(chol OR chor) AND 1:*y'],
  [['-1:','1:','-2:','…'],'the word before or after a match, within its line','*aiin AND -1:*k*'],[['[li]'],'the word starts its line','[li]p*'],[['[lf]'],'the word ends its line','[lf]*m'],[['[pi]'],'on a paragraph-initial line','[pi]p*'],[['[pgi]'],'on a page-initial line, a page\'s first prose line','[pgi]p*'],[['[lpi]'],'on a later paragraph-initial line','[lpi]p*'],[['[npi]'],'on a line that is not paragraph initial','[npi]p*'],[['[!code]'],'! inside the brackets negates that place only','[!pgi]p*']];
 let state=P.parse(SG.hash()),selectedAtLoad=[...state.pages],pages,bundle,layout,orders,lines,review,list,byFolio=new Map(),occurrences=null,occurrenceKey=null,plan={nodes:[],baseNodes:[],pages:[],missing:[],custom:false},shown=new Set(),minis=[],tileRows=[],bits=new Uint8Array(0),gaps=true;
 const loading=SG.busyStart('Loading the manuscript…');
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  const index=await SG.load(SG.dataUrl('index.json')),C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const info=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];
  const [compact,loadedOrders,data,loadedLayout,tokens]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(info.path)),SG.load(SG.dataUrl(index.layout||'layout.json.gz')),index.review?SG.load(SG.dataUrl(index.review)).then(r=>r.tokens).catch(()=>null):null]);
  pages=compact.pages;orders=loadedOrders;bundle=data;layout=loadedLayout;review=data.spatialReview;gaps=!!tokens;
  lines=P.textLines(bundle,pages,tokens);for(const l of lines){if(!byFolio.has(l.folio))byFolio.set(l.folio,[]);byFolio.get(l.folio).push(l);}
  list=Z.pageList(orders,state.order,pages);bits=new Uint8Array(bundle.words.length);
 }catch(error){loading.end();status.textContent='Could not load the page data.';SG.error(host,error);return;}
 state.custom=T.clean({overlaps:{},pages:[],custom:state.custom},pages,list).custom;state.pages=state.pages.filter(f=>pages[f]);
 const save=()=>SG.setHash({data:SG.hash().data,...P.serialize(state)});
 const css=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
 const colourVar=slot=>`var(--hl-${slot})`;
 const percent=x=>x===null?'':(100*x).toFixed(x<.001?2:1)+'%';
 const wordsIn=(n,one='word',many=one+'s')=>`${int(n)} ${n===1?one:many}`;
 // ---- the patterns
 function words(){if(occurrenceKey!==state.merge){occurrences=P.occurrences(lines,state.merge);occurrenceKey=state.merge;}return occurrences;}
 function runLayer(layer){
  const key=layer.query+'|'+state.merge;if(layer.key===key)return;
  Object.assign(layer,{key,hits:[],base:null,error:'',live:false});
  if(!layer.query.trim())return;
  try{const test=P.occurrencePattern(layer.query);layer.base=P.rateBase(layer.query);layer.hits=words().filter(test);layer.live=true;}catch(error){layer.error=error.message;}
 }
 // A pattern box's line: its grouping written out, the meaning of any qualifier, or what stops it from being read
 function reading(layer){
  if(layer.error)return `<span class="bad">${esc(layer.error)}</span>`;
  if(!layer.live)return '';
  const text=P.describePattern(layer.query),grouped=text&&P.parsePattern(layer.query).t!=='term'?`Reads as <code>${esc(text)}</code>`:'';
  const where=P.patternQualifiers(layer.query).map(q=>`<code>[${q}]</code> ${esc(P.qualifierName(q))}`).join(' · ');
  const masked=state.merge&&P.patternTerms(layer.query).some(t=>t.startsWith('q'))?'With Merge q on, every word loses its initial q, so a term starting q finds nothing.':'';
  return [grouped,where,P.advice(layer.query,layer.hits.length),masked].filter(Boolean).join(' · ');
 }
 function countLine(layer){
  if(!layer.live)return layer.error?'—':'';
  const hits=layer.hits.filter(o=>shown.has(o.line.folio)),base=layer.base.all?words().filter(o=>shown.has(o.line.folio)).length:words().filter(o=>shown.has(o.line.folio)&&layer.base.test(o)).length;
  const onPages=new Set(hits.map(o=>o.line.folio)).size,part=P.share(hits.length,base),missing=hits.filter(o=>unitOf[o.position]<0).length;
  return `<b>${int(hits.length)}</b>${part===null?'':' · '+percent(part)+' of '+(layer.base.all?int(base)+' words':'the '+int(base)+' '+esc(layer.base.text)+' words')} · ${wordsIn(onPages,'page')}${missing?` · ${int(missing)} with no box`:''}`;
 }
 const unitOf=new Int32Array(bundle.words.length).fill(-1);
 for(const f of Object.keys(pages))pages[f].units.forEach((u,id)=>{for(let i=u[0];i<=u[1];i++)unitOf[i]=id;});
 function fillRows(){
  rows.replaceChildren();
  for(const layer of state.layers){
   const row=h('div','hl-row'),swatch=h('span','hl-swatch'),input=h('input'),count=h('span','hl-count'),remove=h('button','hl-remove','×'),line=h('div','hl-reading');
   row.style.setProperty('--hl',colourVar(layer.slot));swatch.setAttribute('aria-hidden','true');row.dataset.slot=layer.slot;
   input.type='text';input.value=layer.query;input.placeholder=state.layers.length>1?'Another pattern':'A pattern, such as *aiin';input.spellcheck=false;input.autocomplete='off';input.setAttribute('autocapitalize','none');input.setAttribute('aria-label','Pattern '+layer.slot);
   line.setAttribute('aria-live','polite');remove.type='button';remove.setAttribute('aria-label','Remove pattern '+layer.slot);remove.hidden=state.layers.length<2;
   let waiting=null;input.oninput=()=>{layer.query=input.value;clearTimeout(waiting);waiting=setTimeout(update,120);};
   input.onfocus=()=>{active=layer;};
   remove.onclick=()=>{state.layers=state.layers.filter(l=>l!==layer);if(active===layer)active=state.layers[0];fillRows();update();};
   Object.assign(layer,{row,count,line});row.append(swatch,input,count,remove,line);rows.append(row);
  }
  $('addRow').disabled=state.layers.length>=P.LAYERS;
 }
 let active=state.layers[0];
 function addLayer(query=''){
  const used=new Set(state.layers.map(l=>l.slot)),slot=[1,2,3,4,5,6].find(s=>!used.has(s));if(!slot)return null;
  const layer={slot,query};state.layers.push(layer);state.layers.sort((a,b)=>a.slot-b.slot);active=layer;fillRows();update();return layer;
 }
 function useExample(query){
  const layer=active&&state.layers.includes(active)?active:state.layers[0];layer.query=query;layer.row.querySelector('input').value=query;update();
 }
 for(const query of EXAMPLES){const b=h('button','',query);b.type='button';b.onclick=()=>useExample(query);$('examples').append(b);}
 $('syntaxRows').replaceChildren(...SYNTAX.map(([write,meaning,example])=>{
  const tr=h('tr'),a=h('td'),b=h('td','',meaning),c=h('td'),go=h('button','',example);go.type='button';go.onclick=()=>useExample(example);
  write.forEach((x,i)=>{if(i)a.append(' ');a.append(x==='…'?x:h('code','',x));});c.append(go);tr.append(a,b,c);return tr;
 }));
 $('addRow').onclick=()=>{const layer=addLayer();if(layer)layer.row.querySelector('input').focus();};
 // ---- the tiles
 const framed=folio=>{const f=layout.pages[folio];return f&&f.height?{width:f.width,height:f.height}:{width:1100,height:1500};};
 function mini(page){
  const frame=framed(page.folio),height=Number(state.size),width=Math.round(height*frame.width/frame.height),b=h('button','mini'),canvas=h('canvas'),label=h('small'),count=h('b');
  b.type='button';b.dataset.folio=page.folio;b.style.width=width+'px';b.onclick=()=>openPage(page.folio);canvas.style.width=width+'px';canvas.style.height=height+'px';
  label.append(h('span','',page.folio),count);b.append(canvas,label);
  const item={folio:page.folio,page,button:b,canvas,count,width,height,scale:height/frame.height};minis.push(item);return b;
 }
 function build(){
  host.replaceChildren();minis=[];tileRows=[];
  const size=Number(state.size);
  for(const tile of P.tiles(plan,state.columns)){
   const el=h('article','tile'),head=h('header','tile-head'),grip=h('button','grip','⠿'),count=h('span','tile-count'),row=h('div','tile-pages'+(state.columns==='faces'?' faces':'')),first=tile.pages[0];
   el.dataset.node=tile.node;grip.type='button';grip.title='Drag to reorder; Alt + ← → also moves this bifolium';grip.setAttribute('aria-label','Reorder '+tile.node);
   const about=first?[first.section,first.group].filter(x=>x&&x!=='—').join(' · '):'';
   head.append(grip,h('strong','',`${tile.index+1} · ${tile.node}`),h('span','tile-about',about),count);head.title=`${tile.node}${about?' · '+about:''}`;
   for(const cell of tile.cells){
    const box=h('div','tile-cell');box.dataset.slot=cell.slot;
    if(cell.pages.length)for(const page of cell.pages)box.append(mini(page));
    else{const empty=h('div','mini-empty');empty.style.width=Math.round(size*.72)+'px';empty.style.height=size+'px';empty.title=`${tile.node}: no page in position ${cell.slot} in this selection`;box.append(empty);}
    row.append(box);
   }
   el.append(head,row);bindTile(el,head,grip,tile.node);host.append(el);tileRows.push({node:tile.node,element:el,count,pages:tile.pages.map(p=>p.folio)});
  }
 }
 function paint(item,colours,faint){
  const {canvas,width,height,scale:s,folio}=item,dpr=Math.min(2,devicePixelRatio||1);
  canvas.width=Math.ceil(width*dpr);canvas.height=Math.ceil(height*dpr);
  const g=canvas.getContext('2d'),lit=[];g.setTransform(dpr,0,0,dpr,0,0);g.fillStyle=faint;g.globalAlpha=.3;g.beginPath();
  for(const u of pages[folio].units){
   let mask=0;for(let i=u[0];i<=u[1];i++)mask|=bits[i];
   if(mask)lit.push([u,mask]);else g.rect(u[3]*s,(u[4]+BAND_TOP*(u[6]-u[4]))*s,Math.max(.8,(u[5]-u[3])*s),Math.max(.8,BAND*(u[6]-u[4])*s));
  }
  g.fill();g.globalAlpha=1;
  for(const [u,mask] of lit){
   const on=state.layers.filter(l=>mask&(1<<l.slot)),w=Math.max(1.6,(u[5]-u[3])*s),hh=Math.max(1.4,BAND*(u[6]-u[4])*s),y=(u[4]+BAND_TOP*(u[6]-u[4]))*s;
   on.forEach((l,k)=>{g.fillStyle=colours[l.slot];g.fillRect(u[3]*s+k*w/on.length,y,w/on.length,hh);});
  }
 }
 function paintAll(){
  const colours={},faint=css('--ink2');for(const l of state.layers)colours[l.slot]=css('--hl-'+l.slot);
  for(const item of minis)paint(item,colours,faint);
 }
 // ---- what the patterns found, on the tiles and in the counts
 function update(){
  for(const layer of state.layers)runLayer(layer);
  bits.fill(0);for(const layer of state.layers){const bit=1<<layer.slot;for(const o of layer.hits)bits[o.position]|=bit;}
  paintAll();
  const live=state.layers.filter(l=>l.live),perPage=new Map();
  for(const l of live)for(const o of l.hits){if(!perPage.has(o.line.folio))perPage.set(o.line.folio,new Map());const m=perPage.get(o.line.folio);m.set(l.slot,(m.get(l.slot)||0)+1);}
  for(const item of minis){
   const m=perPage.get(item.folio),any=m?byFolio.get(item.folio).reduce((n,line)=>n+line.positions.filter(p=>p>=0&&bits[p]).length,0):0;
   item.count.textContent=any?int(any):'';item.button.dataset.count=any;
   item.button.title=`${item.folio} · ${item.page.slot}${item.page.panels>1?' · panel '+(item.page.panel||'?'):''} · ${item.page.section||'no section'}${live.length?' · '+wordsIn(any,'match','matches'):''}`;
   item.button.setAttribute('aria-label',`Open ${item.folio}${live.length?', '+any+' matching words':''}`);
  }
  for(const row of tileRows){
   const cells=live.map(l=>[l,row.pages.reduce((n,f)=>n+((perPage.get(f)||new Map()).get(l.slot)||0),0)]),total=cells.reduce((n,c)=>n+c[1],0);
   row.count.replaceChildren(...cells.filter(c=>c[1]).map(([l,n])=>{const s=h('span');s.style.setProperty('--hl',colourVar(l.slot));if(live.length>1)s.append(h('i'));s.append(int(n));return s;}));
   row.element.classList.toggle('no-match',live.length>0&&!total);row.element.dataset.count=total;
  }
  for(const layer of state.layers){layer.row.classList.toggle('invalid',!!layer.error);layer.count.innerHTML=countLine(layer);layer.line.innerHTML=reading(layer);}
  if($('tablePanel').open)fillTable();
  if(dialog.open)drawPage();
  save();
 }
 function fillTable(){
  const live=state.layers.filter(l=>l.live),head=live.map(l=>`<th class="n" style="--hl:${colourVar(l.slot)}"><i></i>${esc(l.query)}</th><th class="n">per 1,000</th>`).join('');
  const body=tileRows.map((row,i)=>{
   const set=new Set(row.pages),tokens=words().filter(o=>set.has(o.line.folio)),cells=live.map(l=>{
    const n=l.hits.filter(o=>set.has(o.line.folio)).length,base=l.base.all?tokens.length:tokens.filter(l.base.test).length,part=P.share(n,base);
    return `<td class="n">${int(n)}</td><td class="n">${part===null?'—':(1000*part).toFixed(1)}</td>`;
   }).join('');
   return `<tr><td>${i+1}</td><td>${esc(row.node)}</td><td class="n">${row.pages.length}</td><td class="n">${int(tokens.length)}</td>${cells}</tr>`;
  }).join('');
  $('table').innerHTML=`<table><thead><tr><th>#</th><th>Bifolium</th><th class="n">Pages</th><th class="n">Words</th>${head}</tr></thead><tbody>${body}</tbody></table><p class="drawer-note">Per 1,000 words where the pattern can match on that bifolium. A dash marks fewer than ${P.MIN_SHARE} such words.</p>`;
 }
 $('tablePanel').ontoggle=()=>{if($('tablePanel').open)fillTable();};
 // ---- the order
 let dragged=null;
 function moveSheet(node,index,focusGrip=false){
  if(index<0||index>=plan.nodes.length||plan.nodes.indexOf(node)===index)return;
  state.custom=T.moveNode(plan.nodes,node,index);message.textContent=`${node} moved to position ${index+1}.`;render();
  if(focusGrip)host.querySelector(`.tile[data-node="${CSS.escape(node)}"] .grip`)?.focus({preventScroll:true});
 }
 function clearDrop(){for(const el of host.children)el.classList.remove('drop-before','drop-after','dragging');}
 function bindTile(el,head,grip,node){
  head.draggable=true;
  head.ondragstart=e=>{dragged=node;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',node);e.dataTransfer.setDragImage(el,12,10);el.classList.add('dragging');};
  head.ondragend=()=>{clearDrop();dragged=null;};
  el.ondragover=e=>{if(!dragged||dragged===node)return;e.preventDefault();e.dataTransfer.dropEffect='move';clearDrop();const r=el.getBoundingClientRect();el.classList.add(e.clientX<r.left+r.width/2?'drop-before':'drop-after');};
  el.ondrop=e=>{if(!dragged)return;e.preventDefault();const moving=dragged,r=el.getBoundingClientRect(),after=e.clientX>=r.left+r.width/2,target=plan.nodes.filter(n=>n!==moving).indexOf(node);clearDrop();dragged=null;if(target>=0)moveSheet(moving,target+(after?1:0));};
  grip.onkeydown=e=>{if(e.altKey&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();moveSheet(node,plan.nodes.indexOf(node)+(e.key==='ArrowLeft'?-1:1),true);}};
 }
 // the sets saved on the Page stream that name an order: read only, in this browser
 function fillSaved(){
  let sets=[];try{sets=JSON.parse(localStorage.getItem(STORE)||'[]');}catch(e){sets=[];}
  sets=Array.isArray(sets)?sets.filter(s=>s&&s.params&&(s.params.custom||s.params.order)):[];
  $('saved').replaceChildren(new Option('Choose a saved set',''),...sets.map((s,i)=>new Option(String(s.name),String(i))));$('savedLabel').hidden=!sets.length;
  $('saved').onchange=()=>{const s=sets[Number($('saved').value)];if(!s)return;const o=T.parse(s.params);state.order=o.order;state.custom=o.custom;state.group=o.group;state.by=o.by;state.pages=[];message.textContent=`Order from “${s.name}”.`;render();};
 }
 // ---- drawing
 function fillGroups(){
  const groups=X.groups(pages,list,state.by),name=n=>n==='—'?'Unassigned':n;
  $('group').replaceChildren(...(selectedAtLoad.length?[new Option(`Selected pages (${selectedAtLoad.length})`,'selected')]:[]),new Option('Whole manuscript','all'),...groups.map(g=>new Option(`${name(g.name)} (${g.pages.length})`,g.name)));
  if(state.group!=='all'&&!groups.some(g=>g.name===state.group))state.group='all';
  $('group').value=state.pages.length?'selected':state.group;
 }
 function render(){
  list=Z.pageList(orders,state.order,pages);fillGroups();
  const selectedNodes=new Set(state.pages.map(f=>pages[f].node));
  plan=T.sequence(pages,list,{by:state.by,group:state.group,custom:state.custom,selected:state.pages.length?list.filter(f=>selectedNodes.has(pages[f].node)):[]});
  shown=new Set(plan.pages.map(p=>p.folio));
  for(const k of Object.keys(ctl))ctl[k].value=state[k];
  $('merge').checked=state.merge;$('resetOrder').disabled=!plan.custom;
  const name=state.pages.length?'Selected pages':state.group==='all'?'Whole manuscript':state.group==='—'?'Unassigned':state.group,total=lines.filter(l=>shown.has(l.folio)).reduce((n,l)=>n+l.positions.filter(p=>p>=0).length,0);
  status.textContent=`${name} · ${plan.nodes.length} bifolia · ${plan.pages.length} pages · ${int(total)} words${plan.custom?' · custom order':''}`;
  const link={by:state.by,group:state.group,order:state.order,columns:state.columns,custom:state.custom,pages:state.pages};
  $('streamLink').href='stream.html#'+new URLSearchParams(P.serialize({...P.parse({}),...link,layers:[]})).toString();
  notes.textContent=`Grey marks are word boxes, coloured marks are matches, at one scale in recorded coordinates.${gaps?'':' The list of unreadable tokens could not be loaded, so neighbour terms can reach across them here.'}`;
  build();update();
 }
 // ---- the controls
 ctl.order.onchange=()=>{state.order=ctl.order.value;state.custom=[];message.textContent='';render();};
 ctl.by.onchange=()=>{state.by=ctl.by.value;state.group='all';state.pages=[];render();};
 $('group').onchange=()=>{const v=$('group').value;if(v==='selected')state.pages=[...selectedAtLoad];else{state.group=v;state.pages=[];}render();};
 for(const k of ['columns','size'])ctl[k].onchange=()=>{state[k]=ctl[k].value;render();};
 $('merge').onchange=()=>{state.merge=$('merge').checked;update();};
 $('resetOrder').onclick=()=>{state.custom=[];message.textContent='Back to the selected order.';render();};
 $('exportCsv').onclick=()=>{
  const cell=v=>/[",\n]/.test(String(v))?`"${String(v).replace(/"/g,'""')}"`:String(v),out=[['pattern','folio','bifolium','locus','place_on_line','word','has_box']];
  for(const l of state.layers)if(l.live)for(const o of l.hits)if(shown.has(o.line.folio))out.push([l.query,o.line.folio,o.line.node,o.line.locus,o.index+1,o.raw,unitOf[o.position]>=0?1:0]);
  const url=URL.createObjectURL(new Blob([out.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='word_search_matches.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
 };
 // ---- an open page
 const imageOf=folio=>layout.pages[folio]&&layout.pages[folio].image;
 function drawPage(){
  const folio=state.open,page=pages[folio],meta=plan.pages.find(p=>p.folio===folio)||{},image=imageOf(folio),hasImage=!!image,useImage=hasImage&&state.image,own=!!(layout.pages[folio]&&layout.pages[folio].self_hosted),frame=framed(folio);
  $('pageImage').disabled=!hasImage;$('pageImage').checked=useImage;$('pageLabels').checked=state.labels;
  const size=useImage&&!own?[636,900]:[frame.width,frame.height],live=state.layers.filter(l=>l.live);
  let hidden=0;
  const boxes=page.units.map(u=>{
   let mask=0;for(let i=u[0];i<=u[1];i++)mask|=bits[i];
   const parts=useImage&&!own?P.displayParts(u[0],u[1],review):[[u[3],u[4],u[5],u[6]]],text=bundle.words.slice(u[0],u[1]+1).join(' '),locus=page.lines[u[2]]?page.lines[u[2]][0]:'',on=state.layers.filter(l=>mask&(1<<l.slot));
   if(!parts.length){hidden++;return '';}
   const rects=parts.map(b=>{
    const w=b[2]-b[0];
    if(!on.length)return `<rect class="box" x="${b[0]}" y="${b[1]}" width="${w}" height="${b[3]-b[1]}"/>`;
    return on.map((l,k)=>`<rect class="hit" style="--hl:${colourVar(l.slot)}" x="${b[0]+k*w/on.length}" y="${b[1]}" width="${w/on.length}" height="${b[3]-b[1]}"/>`).join('');
   }).join('');
   const b=parts[0],label=state.labels?`<text x="${b[0]+1}" y="${b[1]+(b[3]-b[1])*.8}" font-size="${Math.min(useImage&&!own?11:18,(b[3]-b[1])*.62)}" textLength="${Math.max(2,b[2]-b[0]-2)}" lengthAdjust="spacingAndGlyphs">${esc(text)}</text>`:'';
   return `<g data-hit="${on.length?1:0}"><title>${esc(text)} · ${esc(folio)}.${esc(locus)}</title>${rects}${label}</g>`;
  }).join('');
  figure.classList.toggle('on-image',useImage);figure.style.aspectRatio=size[0]+' / '+size[1];
  full={x:0,y:0,w:size[0],h:size[1]};if(view&&(view.folio!==folio||view.frame!==size.join()))view=null;
  figure.innerHTML=`<svg viewBox="${view?[view.x,view.y,view.w,view.h].join(' '):`0 0 ${size[0]} ${size[1]}`}" role="group" aria-label="${esc(folio)} word boxes">${useImage?`<image href="${esc(image)}" width="${size[0]}" height="${size[1]}" preserveAspectRatio="none" aria-hidden="true"/>`:''}${boxes}</svg>`;
  const picture=figure.querySelector('image');if(picture)picture.addEventListener('error',()=>{$('pageNote').textContent='The page image could not load. Turn off Page image to see the boxes alone.';});
  $('pageTitle').textContent=[folio,meta.node||page.node,meta.slot||page.slot,page.section].filter(Boolean).join(' · ');
  const located=(byFolio.get(folio)||[]).flatMap(l=>l.positions.filter(p=>p>=0));
  $('pageCount').textContent=live.length?wordsIn(located.filter(p=>bits[p]).length,'matching word'):wordsIn(located.length);
  $('pageText').innerHTML=(byFolio.get(folio)||[]).map(l=>`<div class="hl-line"><small>${esc(l.locus)}</small><div>${l.words.map((w,i)=>{
   if(!w)return '<span class="gap" title="Unreadable token">…</span>';
   const p=l.positions[i],on=state.layers.filter(x=>bits[p]&(1<<x.slot));if(!on.length)return esc(w);
   return `<mark class="${on.length>1?'split':''}${unitOf[p]<0?' nobox':''}" style="--hl:${colourVar(on[0].slot)}${on[1]?';--hl2:'+colourVar(on[1].slot):''}"${unitOf[p]<0?' title="No box on the page"':''}>${esc(w)}</mark>`;
  }).join(' ')}</div></div>`).join('')||'<p class="note">No transliterated text on this page.</p>';
  $('pageNote').textContent=[!hasImage?'No page image is available for this page.':'',own&&useImage?'Beinecke image at quarter scale, with the boxes detected on it.':'',hidden?`${hidden} word ${hidden===1?'box has':'boxes have'} no rectangle on this image.`:''].filter(Boolean).join(' ');
  zoomNote();
  const i=plan.pages.findIndex(p=>p.folio===folio);$('prevOpen').disabled=i<=0;$('nextOpen').disabled=i<0||i>=plan.pages.length-1;
 }
 let view=null,full=null,dragging=null;
 function zoomNote(){$('pageZoom').textContent=view?SG_ZOOM.scale(view,full).toFixed(1)+'×':'';$('pageZoom').hidden=!view;figure.classList.toggle('zoomed',!!view);}
 function look(next){
  view=next&&!SG_ZOOM.isFull(next,full)?{...next,folio:state.open,frame:[full.w,full.h].join()}:null;const v=view||full;
  figure.querySelector('svg')?.setAttribute('viewBox',`${v.x} ${v.y} ${v.w} ${v.h}`);zoomNote();
 }
 const pointAt=e=>{const r=figure.querySelector('svg').getBoundingClientRect();return SG_ZOOM.toPage(view||full,e.clientX-r.left,e.clientY-r.top,r.width,r.height);};
 figure.addEventListener('wheel',e=>{e.preventDefault();look(SG_ZOOM.zoomAt(view||full,full,e.deltaY<0?1.25:.8,pointAt(e)));},{passive:false});
 figure.addEventListener('pointerdown',e=>{if(e.button!==0||!view)return;dragging={x:e.clientX,y:e.clientY,view:{...view},rect:figure.getBoundingClientRect()};figure.setPointerCapture(e.pointerId);});
 figure.addEventListener('pointermove',e=>{if(dragging)look(SG_ZOOM.pan(dragging.view,full,e.clientX-dragging.x,e.clientY-dragging.y,dragging.rect.width,dragging.rect.height));});
 for(const name of ['pointerup','pointercancel'])figure.addEventListener(name,()=>{dragging=null;});
 figure.addEventListener('dblclick',()=>look(null));
 $('pageZoom').onclick=()=>look(null);
 function openPage(folio){state.open=folio;if(!dialog.open)dialog.showModal();drawPage();save();}
 function stepPage(delta){const i=plan.pages.findIndex(p=>p.folio===state.open),next=plan.pages[i+delta];if(next)openPage(next.folio);}
 $('prevOpen').onclick=()=>stepPage(-1);$('nextOpen').onclick=()=>stepPage(1);$('closeOpen').onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>{state.open='';save();minis.find(m=>m.folio===dialog.dataset.back)?.button.focus({preventScroll:true});});
 dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});
 dialog.addEventListener('keydown',e=>{if(e.target.matches('input'))return;if(e.key==='ArrowLeft'){e.preventDefault();stepPage(-1);}else if(e.key==='ArrowRight'){e.preventDefault();stepPage(1);}});
 $('pageImage').onchange=()=>{state.image=$('pageImage').checked;drawPage();save();};
 $('pageLabels').onchange=()=>{state.labels=$('pageLabels').checked;drawPage();save();};
 host.addEventListener('click',e=>{const b=e.target.closest('.mini');if(b)dialog.dataset.back=b.dataset.folio;});
 // the colours follow the theme; a pasted link takes effect
 const repaint=()=>{if(pages)paintAll();};
 new MutationObserver(repaint).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 matchMedia('(prefers-color-scheme: dark)').addEventListener('change',repaint);
 addEventListener('hashchange',()=>{const wasOpen=dialog.open;state=P.parse(SG.hash());selectedAtLoad=[...state.pages];state.pages=state.pages.filter(f=>pages[f]);active=state.layers[0];fillRows();render();if(state.open&&pages[state.open])openPage(state.open);else if(wasOpen)dialog.close();});
 fillRows();fillSaved();
 try{await SG.busy('Drawing the tiles…',()=>{render();if(state.open&&pages[state.open])openPage(state.open);else state.open='';});}finally{loading.end();}
})();
