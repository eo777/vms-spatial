"use strict";
(async()=>{
 const {$,esc}=SG,page=$('reviewPage'),filter=$('reviewFilter'),image=$('reviewImage'),labels=$('reviewLabels'),sources=$('reviewSources'),closeup=$('reviewCloseup'),colors=$('reviewColors');
 let data,tokens,byId,byPage,selected=null,sourceData,sourceCtx,sourcePositions,colorScores,colorDomain,colorTask;
 const displayBoxScores=new Map();let imageJob=null;
 const interesting=t=>filter.value==='all'?true:filter.value==='review'?!t.strict:t.flags.includes(filter.value);
 const flags=a=>a.map(f=>'<span class="review-flag">'+esc(f.replaceAll('_',' '))+'</span>').join('');
 function save(){SG.setHash({page:page.value,token:selected,filter:filter.value,sources:sources.checked?'1':undefined,closeup:closeup.checked?'1':undefined,labels:labels.checked?'1':undefined,colors:colors.value==='review'?undefined:colors.value});}
 async function ensureColors(){
  if(colors.value!=='components'||colorScores)return;
  if(!colorTask)colorTask=SG_SOURCES.series(sourceCtx,100,'spatial',{left:3,depth:8,angle:45,weight:'distance'}).then(stats=>{colorScores=stats.map(s=>s.components);colorDomain=SG_SOURCES.colorDomain(colorScores);});
  $('reviewSummary').textContent='Calculating component diversity…';await SG.busy('Calculating component diversity…',colorTask);
 }
 async function update(){await ensureColors();render();save();}
 function originalBoxScore(group,part){
  const pos=group.tokens.map(id=>sourcePositions.get(id)).find(Number.isInteger),box=group.parts[part];
  if(pos===undefined||!box)return NaN;
  const key=pos+':'+box.join(',');if(displayBoxScores.has(key))return displayBoxScores.get(key);
  // Locate only this displayed target at its original physical rectangle.
  // Keep the source inventory and all saved study scores unchanged.
  const centers=sourceCtx.centers.slice();
  centers[pos]={x:(box[0]+box[2])/2,y:(box[1]+box[3])/2,width:box[2]-box[0],height:box[3]-box[1]};
  const ctx={...sourceCtx,centers},pool=SG_SOURCES.sourcePool(ctx,pos,100,{left:3,depth:8,angle:45,weight:'distance'}),value=SG_SOURCES.measure(ctx,pool).components;
  displayBoxScores.set(key,value);return value;
 }
 function componentColor(value){return Number.isFinite(value)?sourceData.palette[Math.min(500,Math.floor(SG_SOURCES.colorFraction(value,colorDomain)*501))]:null;}
 function watchImage(el){imageJob?.end();imageJob=null;if(!el)return;const job=imageJob=SG.busyStart('Loading the page image…');for(const ev of ['load','error'])el.addEventListener(ev,()=>job.end(),{once:true});}
 function choose(id){selected=selected===id?null:id;render();save();}
 function render(){
  const rows=byPage.get(page.value)||[],shown=rows.filter(interesting),info=data.pages[page.value];
  const selectedToken=byId.get(selected),selectedGroup=selectedToken?.group;
  const groups=Object.values(data.groups).filter(g=>g.page===page.value&&g.tokens.length),active=new Set(shown.map(t=>t.group));
  const pos=sourcePositions.get(selected),sourceMode=sources.checked&&pos!==undefined;
  const pool=sourceMode?SG_SOURCES.sourcePool(sourceCtx,pos,100,{left:3,depth:8,angle:45,weight:'distance'}):null;
  const sourceGroups=new Set(pool?.indices.map(i=>{const g=sourceData.spatialReview.groups[sourceData.spatialReview.tokens[i].group];return g.source_group||g.id;})||[]);
  const score=pool?SG_SOURCES.measure(sourceCtx,pool):null;
  const contextGroups=new Set();
  if(sourceMode&&!pool.missingTarget){
   const point=sourceCtx.centers[pos],pg=sourceCtx.pages.get(page.value),targetLine=sourceData.lines[sourceCtx.lineOf[pos]].locus;
   for(const g of groups){
    if(sourceGroups.has(g.id)||g.id===selectedGroup||!g.tokens.some(id=>sourcePositions.get(id)<pos))continue;
    const sameLine=g.tokens.some(id=>byId.get(id)?.locus===targetLine);
    if(g.parts.some(b=>{const cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;if(sameLine)return cx<point.x&&point.x-cx<=3*pg.wordWidth;const near=Math.max(0,point.y-b[3]),far=Math.min(8*pg.pitch,point.y-b[1]);return cy<point.y&&far>0&&near<=far&&Math.max(b[0]-point.x,point.x-b[2],0)<=far;}))contextGroups.add(g.id);
   }
  }
  const registration=sourceMode?SG_REVIEW.displayRegistration(groups):null;
  let guide='',guideBounds=[];
  if(sourceMode&&!pool.missingTarget&&registration?.maxCenterError<2){
   const parts=selectedToken.display_box?[selectedToken.display_box]:data.groups[selectedGroup].display_parts,box=[Math.min(...parts.map(b=>b[0])),Math.min(...parts.map(b=>b[1])),Math.max(...parts.map(b=>b[2])),Math.max(...parts.map(b=>b[3]))];
   const cx=(box[0]+box[2])/2,cy=(box[1]+box[3])/2,pageGeometry=sourceCtx.pages.get(page.value),depth=8*pageGeometry.pitch*registration.scale,left=3*pageGeometry.wordWidth*registration.scale;
   guideBounds=[[cx-depth,cy-depth,cx+depth,cy],[cx-left,cy,cx,cy]];
   guide='<g class="source-guide" aria-hidden="true"><path d="M '+cx+' '+cy+' L '+(cx-depth)+' '+(cy-depth)+' L '+(cx+depth)+' '+(cy-depth)+' Z"/><path class="left-guide" d="M '+cx+' '+cy+' H '+(cx-left)+' M '+(cx-left)+' '+(cy-3)+' V '+(cy+3)+'"/></g>';
  }
  let viewBox='0 0 636 900';
  if(closeup.checked&&selectedGroup){
   const parts=groups.filter(g=>g.id===selectedGroup||sourceGroups.has(g.id)).flatMap(g=>g.display_parts||[]).filter(b=>b[2]>b[0]&&b[3]>b[1]).concat(guideBounds);
   if(parts.length){const x=Math.min(...parts.map(b=>b[0]))-18,y=Math.min(...parts.map(b=>b[1]))-18,r=Math.max(...parts.map(b=>b[2]))+18,b=Math.max(...parts.map(b=>b[3]))+18;viewBox=[x,y,r-x,b-y].join(' ');}
  }
  $('reviewCanvas').classList.toggle('source-window',sourceMode);
  const componentMode=colors.value==='components'&&!sourceMode;
  $('reviewCanvas').closest('main').classList.toggle('component-overview',componentMode&&!selectedToken);
  $('reviewCanvas').classList.toggle('component-colors',componentMode);
  $('reviewCanvas').classList.toggle('green-boxes',colors.value==='green'||sourceMode);
  const legend=$('reviewComponentLegend');legend.hidden=!componentMode||!colorDomain;
  if(componentMode&&colorDomain){legend.dataset.low=colorDomain.low;legend.dataset.high=colorDomain.high;legend.innerHTML='Component diversity · effective pairs <span class="component-spectrum"></span> '+colorDomain.low.toFixed(1)+' low → '+colorDomain.high.toFixed(1)+' high';}
  $('reviewSummary').textContent=page.value+' · '+shown.length+' / '+rows.length+' words shown · '+rows.filter(t=>t.strict).length+' conservative word-level assignments';
  if(score)$('reviewSummary').textContent=page.value+' · '+selectedToken.text+' · '+(Number.isFinite(score.components)?score.components.toFixed(1)+' effective pairs':'No scored source pool')+' · '+score.n+' source words';
  $('reviewRows').innerHTML=shown.map(t=>{const g=data.groups[t.group];return '<tr class="'+(t.id===selected?'selected':'')+'"><td>'+esc(t.locus)+' · '+esc(t.locus_type)+'</td><td><button type="button" data-token="'+esc(t.id)+'">'+esc(t.text+t.after)+'</button></td><td>'+esc(g?.xml_words.join(' / ')||'Unlocated')+'<small> ['+esc(g?.xml_indices.join(', ')||'—')+']</small></td><td>'+flags(t.flags)+'</td></tr>';}).join('');
  if(!info?.display_image){$('reviewCanvas').innerHTML='<p>No coordinate image available for this ZL page.</p>';$('reviewImageStatus').textContent='';}
  else{
   $('reviewCanvas').innerHTML='<svg viewBox="'+viewBox+'" role="group" aria-label="'+esc(page.value)+' source image and original display boxes">'+(image.checked?'<image data-source-image="1" width="636" height="900"/>':'')+guide+groups.map(g=>{
    const members=g.tokens.map(id=>byId.get(id)),text=members.map((t,i)=>t.text+(i<members.length-1?t.after:'')).join('');
    const parts=g.display_parts||[],p=parts.find(b=>b[2]>b[0]&&b[3]>b[1]);if(!p)return '';
    const clean=members.every(t=>t.strict),inWindow=sourceGroups.has(g.id),inContext=contextGroups.has(g.id),isTarget=g.id===selectedGroup,cls=['audit-box',clean?'clean':'',isTarget?'selected':'',inWindow?'source-word':'',selectedGroup?!isTarget&&!inWindow&&!inContext?'dim':'':!active.has(g.id)?'dim':''].join(' ');
    const labelParts=inContext&&g.xml_words.length===parts.length?parts.map((b,k)=>({box:b,text:g.xml_words[k]})):[{box:p,text}];
    const wordLabels=labels.checked&&(!sourceMode||inWindow||inContext||isTarget)?labelParts.map(({box:b,text:word})=>'<text x="'+(b[0]+1)+'" y="'+(b[1]+(b[3]-b[1])*.8)+'" font-size="'+Math.min(11,(b[3]-b[1])*.6)+'" textLength="'+Math.max(2,b[2]-b[0]-2)+'" lengthAdjust="spacingAndGlyphs">'+esc(word)+'</text>').join(''):'';
    const values=componentMode&&colorScores?g.tokens.map(id=>colorScores[sourcePositions.get(id)]).filter(Number.isFinite):[],value=values.length?values.reduce((a,b)=>a+b,0)/values.length:NaN;
    const color=componentColor(value);
    const rectangles=parts.map((b,k)=>{if(b[2]<=b[0]||b[3]<=b[1])return '';const partValue=componentMode&&!Number.isFinite(value)?originalBoxScore(g,k):value,partColor=componentMode?componentColor(partValue):null;return '<rect x="'+b[0]+'" y="'+b[1]+'" width="'+(b[2]-b[0])+'" height="'+(b[3]-b[1])+'"'+(partColor?' style="--component-color:'+partColor+'" data-component-diversity="'+partValue+'"':'')+'/>';}).join('');
    return '<g class="'+cls+'"'+(color?' style="--component-color:'+color+'" data-component-diversity="'+value+'"':'')+' data-token="'+esc(g.tokens[0])+'" role="button" tabindex="0" aria-label="'+esc(text+' · '+g.xml_words.join(' / '))+'"><title>'+esc(text+(Number.isFinite(value)?' · '+value.toFixed(1)+' effective pairs':'')+' · '+g.flags.join(', '))+'</title>'+rectangles+wordLabels+'</g>';
   }).join('')+'</svg>';
   if(guide){const svg=$('reviewCanvas').querySelector('svg'),overlay=svg.querySelector('.source-guide');svg.append(overlay);for(const text of svg.querySelectorAll('.audit-box text'))overlay.append(text);}
   $('reviewImageStatus').innerHTML=(image.checked?'Native Voynichese display coordinates on its matching image. ':'Original display boxes; image hidden. ')+'<a href="https://www.voynichese.com/#/'+encodeURIComponent(info.xml.replace('.xml',''))+'/0" target="_blank" rel="noopener">Open source viewer</a>';
   if(sourceMode)$('reviewImageStatus').append(' · 8 line spacings up; 45° half-angle; 3 word widths left.');
  }
  for(const el of $('reviewCanvas').querySelectorAll('image[data-source-image]'))el.setAttribute('href',info.display_image);
  watchImage($('reviewCanvas').querySelector('image[data-source-image]'));
  // Overlay derived word boundaries only when that original assignment is
  // selected. The audit's pink rectangles remain the untouched source evidence.
  if(selectedGroup&&data.groups[selectedGroup]?.resolved){
   const resolved=data.groups[selectedGroup].resolved;
   $('reviewCanvas').querySelector('svg')?.insertAdjacentHTML('beforeend','<g aria-label="Resolved word boundaries" pointer-events="none">'+resolved.map(r=>{const b=r.display_box;return b?'<rect x="'+b[0]+'" y="'+b[1]+'" width="'+(b[2]-b[0])+'" height="'+(b[3]-b[1])+'" fill="none" stroke="#00e6cc" stroke-width=".5"/>':'';}).join('')+'</g>');
  }
  if(!selectedToken){$('reviewDetails').innerHTML=componentMode?'<h2>Component diversity</h2><p>Each word is colored by the diversity of the word components in its source window. Warm colors indicate lower diversity; teal indicates higher diversity. Select a word to inspect its window.</p>':'<h2>Inspect an assignment</h2><p>Select a word or original box. Amber marks words needing location review; teal marks assignments passing the conservative checks.</p>';return;}
  const t=selectedToken,g=data.groups[t.group];
  $('reviewDetails').innerHTML='<h2>'+esc(t.text+t.after)+'</h2><p><code>'+esc(t.id)+'</code></p>'+flags(t.flags)+'<p>'+(t.strict?'Included in the conservative spatial policy.':'Excluded from conservative spatial calculations; canonical text is retained.')+'</p>'+(g?'<h3>ZL words sharing this assignment</h3><p>'+g.tokens.map(id=>'<button type="button" data-token="'+esc(id)+'">'+esc(byId.get(id).text+byId.get(id).after)+'</button>').join(' ')+'</p><p>Coordinate spelling: <b>'+esc(g.xml_words.join(' / ')||'Unlocated')+'</b><br>Original XML indices: '+esc(g.xml_indices.join(', ')||'—')+'</p><div id="reviewCrops"></div><h3>Original XML rectangles</h3><pre>'+esc(JSON.stringify(g.parts))+'</pre><h3>Native display rectangles</h3><pre>'+esc(JSON.stringify(g.display_parts||[]))+'</pre><p>Coordinates are [left, top, right, bottom]. Separate pieces remain separate; no spanning rectangle is used as observed word geometry.</p>':'<p>No coordinate assignment exists.</p>');
  if(g?.resolved)$('reviewDetails').insertAdjacentHTML('beforeend','<h3>Resolved word geometry</h3><p>Teal outlines show derived word positions. Original boxes above are retained as evidence. Uncertain spaces remain uncertain.</p>'+g.resolved.map(r=>'<p><b>'+esc(byId.get(r.token).text)+'</b> · '+esc(r.method.replaceAll('_',' '))+'<br>'+esc(r.reason)+'</p><pre>'+esc(JSON.stringify({analysis:r.box,native:r.display_box}))+'</pre>').join(''));
  if(g&&info?.display_image){
   $('reviewCrops').innerHTML=(g.display_parts||[]).map((b,k)=>b[2]>b[0]&&b[3]>b[1]?'<figure class="review-crop"><svg viewBox="'+[Math.max(0,b[0]-24),Math.max(0,b[1]-12),b[2]-b[0]+48,b[3]-b[1]+24].join(' ')+'" role="img" aria-label="Original source context for XML word '+g.xml_indices[k]+'"><image data-source-image="1" width="636" height="900"/><rect x="'+b[0]+'" y="'+b[1]+'" width="'+(b[2]-b[0])+'" height="'+(b[3]-b[1])+'" fill="none" stroke="#ed145b" stroke-width=".8"/></svg><figcaption>Original box '+g.xml_indices[k]+' · '+esc(g.xml_words[k])+'</figcaption></figure>':'').join('');
   for(const el of $('reviewCrops').querySelectorAll('image[data-source-image]'))el.setAttribute('href',info.display_image);
  }
 }
 const loading=SG.busyStart('Loading the alignment review…');
 try{
  const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
  SG.setBase(SG.hash().data||config.dataBase||'data/');
  const index=await SG.load(SG.dataUrl('index.json')),entry=index.bundles.find(b=>b.key===(config.defaultBundle||'manuscript'))||index.bundles[0];
  [data,sourceData]=await Promise.all([SG.load(SG.dataUrl(index.review||'spatial_review.json.gz')),SG.load(SG.dataUrl(entry.path))]);
  sourceCtx=SG_SOURCES.prepare(sourceData);sourcePositions=new Map(sourceData.spatialReview.tokens.map((t,i)=>[t.id,i]));
  tokens=data.tokens;byId=new Map(tokens.map(t=>[t.id,t]));byPage=new Map();
  for(const t of tokens){if(!byPage.has(t.page))byPage.set(t.page,[]);byPage.get(t.page).push(t);}
  const pages=[...byPage.keys()].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));page.replaceChildren(...pages.map(p=>new Option(p,p)));
  const h=SG.hash();page.value=byPage.has(h.page)?h.page:'f108r';selected=byId.has(h.token)?h.token:null;if(selected)page.value=byId.get(selected).page;
  if([...filter.options].some(o=>o.value===h.filter))filter.value=h.filter;
  sources.checked=h.sources==='1';closeup.checked=h.closeup==='1';labels.checked=h.labels==='1';
  if(['review','green','components'].includes(h.colors))colors.value=h.colors;
  $('reviewCoverage').textContent=data.metrics.canonical_tokens+' canonical tokens across '+data.metrics.canonical_pages+' ZL page identifiers; '+data.metrics.coordinate_pages+' coordinate pages; '+data.metrics.strict_eligible+' word-level assignments pass the conservative policy, '+data.metrics.sensitivity_eligible+' the sensitivity policy.';
  await ensureColors();render();page.onchange=()=>{selected=null;update();};filter.onchange=update;image.onchange=labels.onchange=sources.onchange=closeup.onchange=colors.onchange=update;
  $('reviewNext').onclick=()=>{const at=pages.indexOf(page.value);for(let k=1;k<=pages.length;k++){const p=pages[(at+k)%pages.length];if(byPage.get(p).some(interesting)){page.value=p;selected=null;render();save();break;}}};
  document.querySelector('main').addEventListener('click',e=>{const item=e.target.closest('[data-token]');if(item)choose(item.dataset.token);else if(e.target.closest('svg')){selected=null;render();save();}});
  document.querySelector('main').addEventListener('keydown',e=>{const item=e.target.closest('g[data-token]');if(item&&(e.key==='Enter'||e.key===' ')){e.preventDefault();choose(item.dataset.token);}});
 }catch(error){$('reviewSummary').textContent='Could not load the alignment review.';SG.error($('reviewDetails'),error);}finally{loading.end();}
})();
