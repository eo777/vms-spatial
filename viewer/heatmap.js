"use strict";
/* The heatmap controller. VMS_HEATMAP.mount({atlas, data, layout, pageDisplay}) binds the page controls to an atlas
   rendered by VMS_ATLAS (rows of pages with <rect data-token-indices>), computes the colors and the row means, and
   handles clicks: a word's window, its weighted spatial sources, the cone. It returns {ready, destroy, reorder, rowMeans,
   update}. Rows are any grouping of pages (bifolia, leaves, pages); each row's token ranges are in data-ranges.
   Static page geometry: recompute only when controls change; clicks touch one window. */
const VMS_HEATMAP=(()=>{
function mount({atlas,data,layout,pageDisplay}){
 const abort=new AbortController(),signal=abort.signal,on=(el,ev,fn,opt)=>el.addEventListener(ev,fn,{...(opt||{}),signal});
 const selector=document.getElementById('scope');
 const size=document.getElementById('windowSize'),direction=document.getElementById('windowDirection'),colors=document.getElementById('colorMode');
 // measures the bundle brings with it (one value per token) join the Colors menu under their headings ("From this text"
 // unless a measure names its group); a measure with menu=false serves the line notes only
 for(const old of colors.querySelectorAll('optgroup[data-bundle-measures]'))old.remove();
 const measureDomains={},menus=new Map();
 for(const [k,m] of Object.entries(data.measures||{})){
  if(m.menu===false)continue;
  const name=m.group||'From this text';
  if(!menus.has(name)){const og=document.createElement('optgroup');og.label=name;og.dataset.bundleMeasures='1';menus.set(name,og);colors.append(og);}
  menus.get(name).append(new Option(m.label||k,'m:'+k));
 }
 const domainOf=k=>{if(!(k in measureDomains)){const m=data.measures?.[k];measureDomains[k]=m?SG_HEATMAP.measureDomain(m.values,m.kind,m.domain):null;}return measureDomains[k];};
 const leftReach=document.getElementById('leftReach'),aboveDepth=document.getElementById('aboveDepth'),coneAngle=document.getElementById('coneAngle'),sourceWeight=document.getElementById('sourceWeight'),targetMode=document.getElementById('targetMode');
 const editLimit=document.getElementById('editLimit'),candidateUnit=document.getElementById('candidateUnit');
 const rows=[...atlas.querySelectorAll('.bifolio')];
 const scopeDefs=new Map((layout.scopes||[]).map(s=>[s.key,s]));
 const summary=document.getElementById('windowSummary'),restoreButton=document.getElementById('restoreHeatmap'),detailsPanel=document.getElementById('wordDetails'),detailsButton=document.getElementById('wordDetailsButton');let detailsOpen=false;
 const caption=atlas.querySelector('.caption'),shared=document.getElementById('sharedChoice'),choose=document.getElementById('boxWord');
 const tokenBoxes=new Map(),entries=[],byBox=new WeakMap();
 let rolling=null,impact=null,selected=-1,origin=null,marked=[],revision=0,sizeTimer=null,destroyed=false;
 let width=100,mode='backward',colorMode='none',computedWidth=0,computedMode='';
 let sourceCtx=null,sourceStats=null,sourceKey='',colorDomains={},sourceOptions={left:3,depth:8,angle:45,weight:'distance',metric:'centre',target:'box'};
 let copyCtx=null,editRadius=1,countUnit='Types';
 let expandedPage=null,overviewScroll=0,pendingLine=null;
 const pageFigures=new Map();
 for(const figure of atlas.querySelectorAll('figure')){
  if(!figure.querySelector('svg'))continue;
  const cap=figure.querySelector('figcaption'),page=cap.textContent.trim(),button=document.createElement('button');
  figure.dataset.page=page;pageFigures.set(page,figure);button.type='button';button.className='expand-page';button.textContent='⤢';
  button.setAttribute('aria-label','Expand '+page);button.setAttribute('aria-expanded','false');button.title='Expand '+page;
  on(button,'click',()=>showPage(expandedPage===figure?null:figure));cap.append(button);
 }
 const segmentsOf=row=>row.dataset.ranges?row.dataset.ranges.split(',').filter(Boolean).map(r=>r.split('-').map(Number)):[];
 const pagesOf=row=>row.dataset.pages.split(',');
 // opening a page and going back lay the whole atlas out again
 const showPage=figure=>SG.busy(figure?'Opening '+figure.dataset.page+'…':'Returning to the rows…',()=>{expandPage(figure);saveHash();});
 function expandPage(figure,scroll=true){
  if(figure===expandedPage)return;
  if(figure&&selected>=0&&!figure.contains(origin))restore();
  if(expandedPage){
   expandedPage.classList.remove('expanded-page');expandedPage.closest('.bifolio').classList.remove('expanded-row');
   const button=expandedPage.querySelector('.expand-page');button.textContent='⤢';button.setAttribute('aria-label','Expand '+expandedPage.dataset.page);button.title='Expand '+expandedPage.dataset.page;button.setAttribute('aria-expanded','false');
   expandedPage.querySelector('.compare-link')?.remove();
  }else if(figure)overviewScroll=window.scrollY;
  const previous=expandedPage;expandedPage=figure;atlas.classList.toggle('page-expanded',!!figure);
  if(figure){
   figure.classList.add('expanded-page');figure.closest('.bifolio').classList.add('expanded-row');
   const button=figure.querySelector('.expand-page');button.textContent='⤡ Back to rows';button.setAttribute('aria-label','Collapse '+figure.dataset.page);button.title='Return to the rows';button.setAttribute('aria-expanded','true');
   // one link to the comparison page with this page as A (the compare page keeps its own state in its address)
   const link=document.createElement('a');link.className='compare-link';link.href='compare.html#a='+encodeURIComponent(figure.dataset.page);link.textContent='Compare this page';button.before(link);
  }
  visibility();pageDisplay.expand(figure);
  if(scroll)requestAnimationFrame(()=>{
   if(figure){const top=figure.getBoundingClientRect().top+window.scrollY-atlas.querySelector('.controls').getBoundingClientRect().height-12;window.scrollTo({top,behavior:'instant'});}
   else{window.scrollTo({top:overviewScroll,behavior:'instant'});previous?.querySelector('.expand-page')?.focus({preventScroll:true});}
  });
 }
 const copyView=()=>['minedit','candidates'].includes(colorMode);
 const external=()=>colorMode.startsWith('m:'),measureOf=()=>external()?data.measures?.[colorMode.slice(2)]:null;
 const plain=()=>colorMode==='none',spatial=()=>!plain()&&!external()&&mode==='spatial',components=()=>['components','h1','h2','js'].includes(colorMode),advanced=()=>!plain()&&!external()&&(spatial()||components());
 function externalColor(value){const m=measureOf(),f=SG_HEATMAP.measureFraction(value,domainOf(colorMode.slice(2)),m?.kind);return Number.isFinite(f)?paintColor(.5+.5*f):'var(--line2)';}
 function externalText(i){const m=measureOf(),v=m?m.values[i]:NaN;return Number.isFinite(v)?v.toFixed(m.digits??2)+(m.unit?' '+m.unit:''):'no value';}
 // the orientation record of a token's line (vmsspatial.orientation), for the tooltip and the notes
 function orientationOf(pos){return data.lines[data.lineOf[pos]]?.orientation||null;}
 function orientationText(pos){
  const o=orientationOf(pos);if(!o)return '';
  let s=o.kind;if(o.angle_deg!=null)s+=' '+(o.angle_deg>0?'+':'')+o.angle_deg+'°';
  if(o.centre)s+=' about ('+o.centre.map(v=>Math.round(v)).join(', ')+')'+(o.radius?' r '+Math.round(o.radius):'');
  return s;
 }
 function lineNotes(pos){
  const el=document.getElementById('lineNotes'),notes=VMS_ATLAS.lineNoteItems(data,data.lineOf[pos]),o=orientationOf(pos),L=data.lines[data.lineOf[pos]];
  if(!el)return;el.hidden=!notes.length&&!o;if(el.hidden)return;
  const items=notes.map(([k,v])=>{const s=document.createElement('span');s.innerHTML='<b>'+SG.esc(k)+'</b> '+SG.esc(v);return s;});
  if(o){const s=document.createElement('span');s.className='orientation-note';
   s.innerHTML='<b>orientation</b> '+SG.esc(orientationText(pos))+(L?.locus_type?' · locus type '+SG.esc(L.locus_type):'')+' · confidence '+SG.esc(String(o.confidence))+(o.basis?.length?' · cues: '+SG.esc(o.basis.join('; ')):'');
   items.push(s);}
  el.replaceChildren(...items);
 }
 // the clicked word's notes wait behind Details: a tall sticky bar would cover the page and the word itself
 function syncDetails(){const any=[...detailsPanel.children].some(c=>!c.hidden);detailsButton.hidden=!any;detailsPanel.hidden=!any||!detailsOpen;detailsButton.setAttribute('aria-expanded',String(any&&detailsOpen));detailsButton.textContent=any&&detailsOpen?'Hide details':'Details';}
 on(detailsButton,'click',()=>anchored(origin,()=>{detailsOpen=!detailsOpen;syncDetails();}));
 for(const box of atlas.querySelectorAll('rect[data-token-indices]')){
  const entry={box,indices:box.dataset.tokenIndices.split(',').map(Number),title:box.querySelector('title')};
  entries.push(entry);byBox.set(box,entry);
  for(const i of entry.indices){if(!tokenBoxes.has(i))tokenBoxes.set(i,[]);tokenBoxes.get(i).push(box);}
 }
 function inScope(row){
  if(!selector)return true;const def=scopeDefs.get(selector.value);if(!def||def.key==='all')return true;
  if(def.groups)return def.groups.includes(row.dataset.group);
  if(def.sections){const s=row.dataset.sections.split('|');return def.sections.some(x=>s.includes(x));}
  return true;
 }
 function visibility(context=new Set()){
  for(const row of rows){
   const extra=!inScope(row)&&(pagesOf(row).some(p=>context.has(p))||row===expandedPage?.closest('.bifolio'));
   row.hidden=!(inScope(row)||extra);row.classList.toggle('window-context',extra);
  }
 }
 function anchored(box,change){
  const before=box?.getBoundingClientRect();change();
  const after=box?.getBoundingClientRect();
  if(before?.height&&after?.height&&Math.abs(after.top-before.top)>.5)window.scrollBy({top:after.top-before.top,behavior:'instant'});
  if(after?.height){const bar=atlas.querySelector('.controls').getBoundingClientRect().bottom+8,top=box.getBoundingClientRect().top;if(top<bar)window.scrollBy({top:top-bar,behavior:'instant'});}   // never under the sticky controls
 }
 function paintColor(value){
  if(!Number.isFinite(value))return 'var(--line2)';
  return data.palette[Math.max(0,Math.min(500,Math.floor((value-.5)*1002)))];
 }
 function boxScore(indices){
  const scores=indices.map(i=>rolling.scores[i]).filter(Number.isFinite);
  return scores.length?scores.reduce((a,b)=>a+b,0)/scores.length:NaN;
 }
 const attribution=()=>colorMode==='impact'||colorMode==='change';
 const contribColors=()=>colorMode==='mattr'||colorMode==='overlay';
 const copiesFill=count=>'var(--copies-'+Math.max(1,Math.min(5,count))+')';
 const contribList=document.getElementById('contribList');let contribWord=null;
 const pp=value=>(value>0?'+':value<0?'−':'')+(Math.abs(value)*100).toFixed(2)+' pp';
 function impactText(pos){
  const n=impact.windows[pos];
  return n?impact.affected[pos]+'/'+n+' containing windows affected · '+pp(impact.gain[pos])+' mean gain if this occurrence were a new spelling':'No full window contains this word';
 }
 function changeText(pos){
  if(!Number.isFinite(impact.change[pos]))return 'No previous full window to compare';
  return pp(impact.enter[pos]/width)+' arriving − '+(impact.leave[pos]*100/width).toFixed(2)+' pp leaving ('+data.words[pos-width]+') = '+pp(impact.change[pos])+' net';
 }
 // the row statistic: mean MATTR over the complete windows inside the row's token ranges, or the mean of the valid
 // advanced scores in them
 function rowMattr(row){
  let sum=0,n=0;
  for(const [start,end] of segmentsOf(row))for(let i=start;i<end;i++){
   const b=SG_HEATMAP.bounds(i,width,mode==='spatial'?'backward':mode,rolling.scores.length);
   if(b.full&&b.start>=start&&b.end<=end&&Number.isFinite(rolling.scores[i])){sum+=rolling.scores[i];n++;}
  }
  return n?sum/n:null;
 }
 function rowAdvanced(row){
  const key=metric().key;let sum=0,n=0;
  for(const [start,end] of segmentsOf(row))for(let i=start;i<end;i++){const v=sourceStats?.[i]?.[key];if(Number.isFinite(v)){sum+=v;n++;}}
  return n?sum/n:NaN;
 }
 function paintRowMeans(){
  for(const row of rows){
   if(plain()){
    row.querySelector('header>strong').textContent='';row.querySelector('header>span:not(.group)').textContent='';
    row.querySelector('.bar i').style.width='0%';row.dataset.mean='';continue;
   }
   if(external()){
    const m=measureOf();let sum=0,n=0;
    if(m&&m.per==='line'){for(const [start,end] of segmentsOf(row))for(const L of data.lines){if(L.start<start||L.end>end)continue;const v=m.values[L.start];if(Number.isFinite(v)){sum+=v;n++;}}}   // one value per line
    else for(const [start,end] of segmentsOf(row))for(let i=start;i<end;i++){const v=m?m.values[i]:NaN;if(Number.isFinite(v)){sum+=v;n++;}}
    const mean=n?sum/n:NaN;
    row.querySelector('header>strong').textContent=Number.isFinite(mean)?mean.toFixed(m.digits??2):'—';
    row.querySelector('header>span:not(.group)').textContent='mean '+(m.label||colorMode.slice(2))+(m.per==='line'?' · per line':'');
    const bar=row.querySelector('.bar i'),f=SG_HEATMAP.measureFraction(mean,domainOf(colorMode.slice(2)),m.kind);bar.style.width=Number.isFinite(f)?100*f+'%':'0%';bar.style.background=externalColor(mean);
    row.dataset.mean=Number.isFinite(mean)?mean:'';continue;
   }
   if(advanced()){
    const mean=rowAdvanced(row);
    row.querySelector('header>strong').textContent=Number.isFinite(mean)?mean.toFixed(metric().key==='components'?1:3):'—';
    row.querySelector('header>span:not(.group)').textContent='mean '+metric().label;
    const bar=row.querySelector('.bar i');bar.style.width=Number.isFinite(mean)?100*metricScale(mean)+'%':'0%';bar.style.background=advancedColor(mean);
    row.dataset.mean=Number.isFinite(mean)?mean:'';
   }else{
    const mean=rowMattr(row);
    row.querySelector('header>strong').textContent=mean===null?'—':mean.toFixed(3);
    row.querySelector('header>span:not(.group)').textContent='mean MATTR'+width;
    const bar=row.querySelector('.bar i');bar.style.width=mean===null?'0%':Math.max(0,(mean-.5)*200)+'%';bar.style.background=paintColor(mean===null?NaN:mean);
    row.dataset.mean=mean===null?'':mean;
   }
  }
 }
 function paintAttribution(){
  for(const entry of entries){
   let fill;
   if(plain())fill='var(--box-plain)';
   else if(external()){
    const m=measureOf(),values=entry.indices.map(i=>m?m.values[i]:NaN).filter(Number.isFinite);
    fill=externalColor(values.length?values.reduce((a,b)=>a+b,0)/values.length:NaN);
   }
   else if(advanced()){
    const values=entry.indices.map(i=>sourceStats?.[i]?.[metric().key]).filter(Number.isFinite);
    fill=advancedColor(values.length?values.reduce((a,b)=>a+b,0)/values.length:NaN);
   }else if(colorMode==='impact'){
    const values=entry.indices.map(i=>impact.windows[i]?impact.affected[i]/impact.windows[i]:NaN).filter(Number.isFinite);
    const value=values.length?values.reduce((a,b)=>a+b,0)/values.length:NaN;
    fill=Number.isFinite(value)?paintColor(.9-.4*value):'var(--line2)';
   }else if(colorMode==='change'){
    const values=entry.indices.map(i=>impact.change[i]).filter(Number.isFinite);
    const value=values.length?values.reduce((a,b)=>a+b,0)/values.length:NaN;
    fill=!Number.isFinite(value)?'var(--line2)':value>1e-12?'var(--heat-single)':value<-1e-12?'var(--heat-repeat)':'var(--heat-neutral)';
   }else fill=paintColor(boxScore(entry.indices));
   entry.box.setAttribute('fill',fill);entry.box.style.setProperty('--box-color',fill);
  }
  paintRowMeans();
 }
 function metric(){return ({minedit:{key:'minedit',label:'minimum glyph edits'},candidates:{key:'candidate'+countUnit+editRadius,label:'candidate '+(countUnit==='Types'?'spellings':'occurrences')+' ≤'+editRadius+' edits'},components:{key:'components',label:'effective pairs'},h1:{key:'h1',label:'glyph H1 · bits'},h2:{key:'h2',label:'glyph H2 · bits'},js:{key:'js',label:'JS distance'}})[colorMode]||{key:'worddiv',label:'source diversity'};}
 function metricScale(value){return copyView()?Math.min(1,colorMode==='minedit'?value/5:Math.log2(1+Math.max(0,value))/Math.log2(18)):components()?SG_SOURCES.colorFraction(value,colorDomains[colorMode]||{low:0,high:1}):Math.max(0,Math.min(1,value));}
 function metricTicks(){
  if(copyView())return colorMode==='minedit'?['0 · copy','1','2','3','4','5+']:SG_COPY.candidateBands.map(b=>b.label);
  if(!components())return ['0','.25','.50','.75','1'];
  const d=colorDomains[colorMode],digits=colorMode==='components'?1:2;if(!d?.count)return ['No scored words'];
  if(d.constant)return [d.low.toFixed(digits)+' · no variation'];
  return Array.from({length:5},(_,i)=>(i===0?'≤':i===4?'≥':'')+(d.low+(d.high-d.low)*i/4).toFixed(digits));
 }
 function advancedColor(value){if(colorMode==='minedit')return SG_COPY.distanceColor(value);if(colorMode==='candidates')return SG_COPY.candidateColor(value);return Number.isFinite(value)?paintColor(.5+.5*(colorMode==='js'?1-metricScale(value):metricScale(value))):'var(--line2)';}
 function sourceText(s){
  if(!s)return 'Calculating…';
  if(copyView())return !s.n?'No eligible earlier source with usable geometry':s.minedit+' minimum glyph edits · '+s.nearestTypes+' nearest spelling'+(s.nearestTypes===1?'':'s')+' ('+s.nearestOccurrences+' occurrences) · '+s['candidateTypes'+editRadius]+' spellings / '+s['candidateOccurrences'+editRadius]+' occurrences within '+editRadius+' edits · '+s.n+' words in cone';
  const value=s[metric().key],score=Number.isFinite(value)?value.toFixed(metric().key==='components'?1:3)+' '+metric().label:'too few contributing sources';
  return score+' · '+s.n+(spatial()?' source words':' words')+' · '+s.ess.toFixed(1)+' effective sources';
 }
 function setLegend(ticks,reverse=false){
  document.getElementById('heatmapLegend').classList.remove('candidate-legend');
  document.querySelector('#heatmapLegend .ticks').replaceChildren(...ticks.map(text=>{const s=document.createElement('span');s.textContent=text;return s;}));
  document.querySelector('#heatmapLegend .spectrum').style.background=reverse?'linear-gradient(90deg,#185965,#4e9c92,#a1c5ad,#ead6a1,#e9aa6c,#d56b43,#a83c35)':'';
 }
 function markRepeat(box,flags){
  const count=flags.filter(Boolean).length;
  box.classList.toggle('repeat-word',count===flags.length);
  box.classList.toggle('mixed-word',count>0&&count<flags.length);
 }
 function restoreEntry(box){
  const entry=byBox.get(box);markRepeat(box,entry.indices.map(i=>rolling.repeated[i]));
  box.classList.remove('window-member','window-selected','window-related');box.removeAttribute('aria-pressed');box.style.fill='';box.style.opacity='';
  entry.title.textContent=normalTitle(entry);
 }
 function clearMarks(){if(rolling)for(const box of marked)restoreEntry(box);marked=[];for(const g of atlas.querySelectorAll('.source-guide'))g.remove();}
 function normalTitle(entry){
  const identity=boxIdentity(entry);
  if(plain())return identity+' · '+location_(entry.indices[0]);
  if(external())return identity+' · '+entry.indices.map(i=>data.words[i]+' · '+externalText(i)).join(' / ')+' · '+location_(entry.indices[0]);
  if(spatial()&&entry.indices.every(i=>!sourceCtx.centers[i]))return identity+' · Unresolved word positions; excluded from spatial scores.';
  if(advanced())return identity+' · '+entry.indices.map(i=>data.words[i]+' · '+sourceText(sourceStats?.[i])).join(' / ')+(entry.indices.length>1?' · shared box: mean of valid word scores':'');
  if(attribution())return identity+' · '+entry.indices.map(i=>data.words[i]+' · '+(colorMode==='impact'?impactText(i):changeText(i))).join(' / ')+(entry.indices.length>1?' · shared box: color averages its word values':'');
  const value=boxScore(entry.indices);
  return identity+' · D'+width+': '+(Number.isFinite(value)?value.toFixed(3):'incomplete window')+(entry.indices.length>1?' · shared rectangle: mean of available full windows':'');
 }
 function boxIdentity(entry){
  const label=SG_REVIEW.boxLabel(data,entry.indices);
  return label+(entry.indices.length>1?' · shared physical box; individual word positions unresolved':'')+(label.includes(',')?' · comma = uncertain space':'');
 }
 function inspectionLabel(box,pos){const entry=byBox.get(box);return SG_REVIEW.boxLabel(data,entry.indices)+(entry.indices.length>1?' · selected token '+data.words[pos]:'');}
 // the Configuration section shows only the controls the chosen measure reads
 function configVisibility(){
  const config=document.getElementById('config'),group=document.getElementById('windowGroup'),note=document.getElementById('sourceNote');
  if(config)config.hidden=plain()||external();
  if(group)group.hidden=plain()||external();
  document.getElementById('copySettings').hidden=!copyView();
  document.getElementById('sourceSettings').hidden=!spatial();if(note)note.hidden=!spatial();
  document.getElementById('sizeLabel').textContent=spatial()?'Source cap':'Window';
  if(config)config.querySelector('summary').textContent='Configuration · '+(copyView()?'cone and candidate limit':spatial()?'source cap, cone and weights':attribution()?'window size':components()?'window size, direction or spatial sources':'window size and direction');
 }
 function instructions(){
  configVisibility();
  size.setAttribute('aria-label',spatial()?'Source cap words':'Window words');
  if(plain()){
   for(const id of ['repeatLegend','impactLegend','changeLegend','heatmapLegend'])document.getElementById(id).hidden=true;
   caption.textContent='Grey boxes are the recorded word rectangles of the '+(data.spatialReview?'reviewed alignment':'bundle')+'. Choose a measure under Colors to paint them; click a box to name its word and line, or use \u2922 on a page to enlarge it.';
   atlas.dataset.colors='none';document.querySelector('.window-status').classList.toggle('idle',selected<0);return;
  }
  if(external()){
   const m=measureOf(),d=domainOf(colorMode.slice(2)),digits=m?.digits??2;
   for(const id of ['repeatLegend','impactLegend','changeLegend'])document.getElementById(id).hidden=true;
   document.getElementById('heatmapLegend').hidden=false;
   setLegend(d?Array.from({length:5},(_,i)=>(i===0?'≤':i===4?'≥':'')+(d[0]+(d[1]-d[0])*i/4).toFixed(digits)):['no values']);
   document.getElementById('legendLabel').textContent=(m?.label||colorMode.slice(2))+(m?.unit?' · '+m.unit:'')+(m?.kind==='diverging'?' · warm = negative, teal = positive':' · warm = low, teal = high');
   caption.textContent=(m?.description||'A measure carried by this text, one value per word; a shared box shows the mean of its words.')+' Click a box to name its word and line'+(data.line_notes?' and to see the line\'s numbers':'')+'; expand a page for its overlays.';
   atlas.dataset.colors='measure';document.querySelector('.window-status').classList.toggle('idle',selected<0);return;
  }
  colors.querySelector('option[value="mattr"]').textContent=spatial()?'Source word diversity':'MATTR (window diversity)';
  for(const option of colors.options)option.disabled=spatial()&&['repeat','overlay','impact','change'].includes(option.value);
  if(advanced()){
   direction.disabled=copyView();direction.title=copyView()?'Copy/edit overlays use earlier words in the spatial cone.':'';
   caption.textContent=spatial()?'Earlier words only: left on this line and above on the same page. Above-line word rectangles that intersect the cone are included, even if their centers lie outside it. Source cap '+width+'; no backfilling from other pages. The outlined target is excluded from its source pool.':'Components of the chosen '+width+'-word '+mode+' window. ';
   caption.textContent+=' '+(colorMode==='js'?'JS distance shows a difference from the whole text, including later words; it is not a diversity or prediction score.':colorMode==='h2'?'H2 measures uncertainty of the next glyph unit given the current one.':colorMode==='h1'?'H1 measures diversity of individual glyph units.':colorMode==='components'?'Component diversity is the effective number of within-word glyph-pair types.':'Source word diversity is the chance that two weighted draws have different spellings; it is not MATTR.');
   caption.textContent+=' Click to inspect '+(spatial()?'the weighted sources':'the components')+'. Row means average valid target scores.'+(components()?' Gray: fewer than 5 contributing words, fewer than 3 effective contributing sources, or an incomplete window.':'');
   for(const id of ['repeatLegend','impactLegend','changeLegend'])document.getElementById(id).hidden=true;
   document.getElementById('heatmapLegend').hidden=false;setLegend(metricTicks(),colorMode==='js');
   if(components()&&colorDomains[colorMode]?.constant)document.querySelector('#heatmapLegend .spectrum').style.background=advancedColor(colorDomains[colorMode].low);
   document.getElementById('legendLabel').textContent=metric().label+(components()?' · linear · whole text '+(colorDomains[colorMode]?.trimmed?'5–95%':'range'):'')+(colorMode==='js'?' · warm = further':' · warm = lower');
   if(copyView()){
    caption.textContent='Raw glyph-unit distance to earlier words in the cleaned source cone. The target is excluded. '+(colorMode==='minedit'?'Color shows the smallest whole-word distance.':'Color counts '+(countUnit==='Types'?'distinct source spellings':'source occurrences')+' within '+editRadius+' edits.')+' Gray means no usable source pool. Click a target to show source spellings inside its cone and their distances. These are generic edits, not evidence of copying.';
    document.getElementById('legendLabel').textContent=metric().label+(colorMode==='minedit'?' · warm = more edits':' · nonlinear count bands · red = zero');
    if(colorMode==='minedit')document.querySelector('#heatmapLegend .spectrum').style.background='linear-gradient(90deg,'+[0,1,2,3,4,5].map(SG_COPY.distanceColor).join(',')+')';
    else{
     const bands=SG_COPY.candidateBands;document.getElementById('heatmapLegend').classList.add('candidate-legend');
     document.querySelector('#heatmapLegend .spectrum').style.background='linear-gradient(90deg,'+bands.map((b,i)=>b.color+' '+(i*100/bands.length)+'%,'+b.color+' '+((i+1)*100/bands.length)+'%').join(',')+')';
     caption.textContent+=' Fixed nonlinear color bands separate 0, 1 and 2 candidates, then 3–4, 5–8, 9–16 and 17+. The same bands apply on every page.';
    }
   }
   atlas.dataset.colors=colorMode;document.querySelector('.window-status').classList.toggle('idle',selected<0);return;
  }
  setLegend(['.50','.60','.70','.80','.90','1.00']);
  const before=mode==='backward'?width-1:mode==='forward'?0:Math.floor((width-1)/2),after=width-1-before;
  const span=before+' before + this word + '+after+' after';
  caption.textContent='Window: '+span+'. Follows the text order across pages and rows. Click a word to isolate its window; click it again or press Escape to restore. '+
   (colorMode==='mattr'&&selected>=0?'Words in the window are colored by how often their spelling occurs in it: each adds 1/(its copies) of a distinct form, and the score is the mean of those shares.':colorMode==='mattr'?'Colors show local diversity.':selected<0?'Repetition marks whether each word recurs within its own window.':'Repetition marks all occurrences of spellings repeated within the selected window.')+
   ' Gray means unscored text or an incomplete window.';
  if(colorMode==='impact')caption.textContent='Each word is scored across every full '+width+'-word window containing it. Color shows how often replacing this one occurrence with a new spelling would increase diversity; direction does not apply. Click to highlight the full affected neighborhood; amber outlines mark other occurrences of the same spelling.';
  if(colorMode==='change')caption.textContent='Change when this word arrives: the gain from an added spelling minus the loss from the word leaving the backward '+width+'-word window. Click to inspect both effects; amber outlines the leaving word. Forward and centered alignment do not apply.';
  if(attribution())caption.textContent+=' Row means still show MATTR'+width+'. Click again or press Escape to restore the full map.';
  direction.disabled=attribution();direction.title=attribution()?'This view attributes the effect to the word itself; direction does not apply.':'';
  document.getElementById('legendLabel').textContent='Distinct forms / '+width+' words · '+direction.selectedOptions[0].textContent+(colorMode==='overlay'?' · red outline: repeated spelling':'');
  document.getElementById('heatmapLegend').hidden=!['mattr','overlay'].includes(colorMode)||selected>=0;
  document.getElementById('repeatLegend').hidden=colorMode!=='repeat';
  document.getElementById('impactLegend').hidden=colorMode!=='impact';
  document.querySelector('.impact-spectrum').style.background='linear-gradient(90deg,'+[0,.25,.5,.75,1].map(f=>paintColor(.9-.4*f)).join(',')+')';
  document.getElementById('changeLegend').hidden=colorMode!=='change';
  document.getElementById('lossKey').textContent='−'+(100/width).toFixed(2)+' pp';
  document.getElementById('gainKey').textContent='+'+(100/width).toFixed(2)+' pp';
  document.querySelector('#repeatLegend .single-key').hidden=colorMode==='overlay';
  document.querySelector('#repeatLegend .repeat-key').textContent=colorMode==='overlay'?'Red outline: repeated spelling':'Repeated spelling';
  atlas.dataset.colors=colorMode;
  document.querySelector('.window-status').classList.toggle('idle',selected<0);
 }
 function restore(focus=false){
  const box=origin;
  anchored(box,()=>{
   clearMarks();selected=-1;atlas.classList.remove('window-mode');restoreButton.hidden=true;shared.hidden=true;contribList.hidden=true;contribWord=null;
   document.getElementById('alignmentNote').hidden=true;
   const ln=document.getElementById('lineNotes');if(ln)ln.hidden=true;syncDetails();
   visibility();instructions();summary.textContent='Click any word to highlight its calculation window on the pages.';
   pageDisplay.labels();
  });
  if(focus&&box&&!box.closest('.bifolio').hidden)box.focus({preventScroll:true});
 }
 function location_(i){const line=data.lines[data.lineOf[i]],o=orientationText(i);return line.page+' · line '+line.locus+(line.locus_type?' ('+line.locus_type+')':'')+(o?' · '+o:'');}
 function alignmentNote(pos){
  const note=document.getElementById('alignmentNote'),t=data.spatialReview?.tokens[pos];
  note.hidden=!t;if(t)note.innerHTML=SG.esc(SG_REVIEW.note(data,pos))+' <a href="alignment.html#page='+encodeURIComponent(t.page)+'&token='+encodeURIComponent(t.id)+'">Inspect original boxes and transcription</a>';
 }
 function select(box,pos,toggle=true){
  if(!rolling||atlas.hasAttribute('aria-busy'))return;
  if(advanced()){selectAdvanced(box,pos,toggle);return;}
  const indices=byBox.get(box).indices;
  if(toggle&&indices.includes(selected)){restore();return;}
  alignmentNote(pos);lineNotes(pos);syncDetails();
  if(plain()||external()){
   anchored(box,()=>{
    clearMarks();selected=pos;origin=box;restoreButton.hidden=false;shared.hidden=indices.length<2;contribList.hidden=true;
    choose.replaceChildren(...indices.map(i=>new Option(data.words[i]+' · word '+(i+1),i,false,i===pos)));
    const line=data.lines[data.lineOf[pos]];
    summary.textContent=inspectionLabel(box,pos)+' · '+location_(pos)+' · word '+(pos+1)+' of '+data.words.length.toLocaleString('en-US')+' · line: '+data.words.slice(line.start,line.end).join(' ');
    instructions();marked=[box];box.classList.add('window-selected');box.setAttribute('aria-pressed','true');pageDisplay.labels();
   });
   return;
  }
  const svg=box.closest('svg');svg.querySelector('[tabindex="0"]')?.setAttribute('tabindex','-1');box.setAttribute('tabindex','0');
  const w=SG_HEATMAP.windowAt(data.words,pos,width,colorMode==='change'?'backward':mode),context=new Set(),active=new Map();
  const area=colorMode==='impact'?SG_HEATMAP.impactBounds(pos,width,data.words.length):colorMode==='change'?{start:Math.max(0,pos-width),end:pos+1}:w;
  let mapped=0;
  for(let i=area.start;i<area.end;i++){
   context.add(data.lines[data.lineOf[i]].page);
   const matches=tokenBoxes.get(i)||[];if(matches.length)mapped++;
   for(const b of matches){if(!active.has(b))active.set(b,[]);active.get(b).push(i);}
  }
  anchored(box,()=>{
   clearMarks();selected=pos;origin=box;atlas.classList.add('window-mode');visibility(context);
   restoreButton.hidden=false;shared.hidden=indices.length<2;
   choose.replaceChildren(...indices.map(i=>new Option(data.words[i]+' · word '+(i+1),i,false,i===pos)));
   summary.textContent=inspectionLabel(box,pos)+' · '+w.unique+' distinct / '+w.size+' words'+(w.score===null?' · incomplete window; no score':' = '+w.score.toFixed(3));
   if(colorMode==='impact')summary.textContent=inspectionLabel(box,pos)+' · '+impactText(pos);
   if(colorMode==='change')summary.textContent=inspectionLabel(box,pos)+' · '+changeText(pos);
   instructions();
   caption.textContent=location_(area.start)+' → '+location_(area.end-1)+'. '+caption.textContent+
    (mapped<area.end-area.start?' '+(area.end-area.start-mapped)+' context tokens lack drawable coordinates; they still count in the score.':'')+
    (rows.some(r=>r.classList.contains('window-context'))?' Adjacent rows are temporarily shown to include the full window.':'');
   marked=[...active.keys()];renderContrib(w,active);
   for(const [b,ids] of active){
    b.classList.add('window-member');markRepeat(b,ids.map(i=>w.counts.get(data.words[i])>1));
    if(contribColors())b.style.fill=copiesFill(Math.max(...ids.map(i=>w.counts.get(data.words[i]))));
    const isSelected=ids.includes(pos);b.classList.toggle('window-selected',isSelected);
    if(isSelected)b.setAttribute('aria-pressed','true');
    b.classList.toggle('window-related',colorMode==='impact'?ids.some(i=>i!==pos&&data.words[i]===data.words[pos]):colorMode==='change'&&ids.includes(pos-width));
    byBox.get(b).title.textContent=attribution()?normalTitle(byBox.get(b)):boxIdentity(byBox.get(b))+' · '+ids.map(i=>{const c=w.counts.get(data.words[i]);return data.words[i]+': '+c+' in this window · adds 1/'+c+' of a distinct form'+(c>1?' · its '+c+' copies cost '+pp(-(c-1)/width):'');}).join(' / ')+
     (ids.length<byBox.get(b).indices.length?' · box also contains text outside this window':'');
   }
   pageDisplay.labels();
  });
 }
 function drawSourceGuide(box,pos){
  const raw=sourceCtx.centers[pos];if(!raw)return;
  const point=pageDisplay.guide(box,raw);if(!point)return;
  const page=sourceCtx.pages.get(data.lines[sourceCtx.lineOf[pos]].page),depth=sourceOptions.depth*page.pitch*point.scale,spread=depth*Math.tan(sourceOptions.angle*Math.PI/180);
  if(sourceOptions.target==='cursor')point.x=Number(box.getAttribute('x'))+page.wordWidth*point.scale/2;   // the writing cursor: one median width at the left edge
  const ns='http://www.w3.org/2000/svg',g=document.createElementNS(ns,'g'),cone=document.createElementNS(ns,'path'),left=document.createElementNS(ns,'path');
  g.setAttribute('class','source-guide');g.setAttribute('aria-hidden','true');
  cone.setAttribute('d',`M ${point.x} ${point.y} L ${point.x-spread} ${point.y-depth} L ${point.x+spread} ${point.y-depth} Z`);
  left.setAttribute('d',`M ${point.x} ${point.y} L ${point.x-sourceOptions.left*page.wordWidth*point.scale} ${point.y}`);
  g.append(cone,left);box.closest('svg').append(g);
 }
 function drawSourceWords(active,pos,distances){
  const ns='http://www.w3.org/2000/svg',groups=new Map();
  for(const [box,ids] of active){
   if(ids.every(i=>!sourceCtx.centers[i]))continue;
   const svg=box.closest('svg');if(!groups.has(svg)){const g=document.createElementNS(ns,'g');g.setAttribute('class','source-guide source-words');svg.append(g);groups.set(svg,g);}
   const text=document.createElementNS(ns,'text'),x=Number(box.getAttribute('x')),y=Number(box.getAttribute('y')),w=Number(box.getAttribute('width')),h=Number(box.getAttribute('height'));
   text.textContent=SG_REVIEW.boxLabel(data,byBox.get(box).indices);text.setAttribute('x',x+2);text.setAttribute('y',y+h*.72);text.setAttribute('font-size',Math.min(18,h*.65));text.setAttribute('textLength',Math.max(2,w-4));text.setAttribute('lengthAdjust','spacingAndGlyphs');
   groups.get(svg).append(text);
  }
 }
 function selectAdvanced(box,pos,toggle){
  if(atlas.hasAttribute('aria-busy')||!sourceStats)return;
  const indices=byBox.get(box).indices;if(toggle&&indices.includes(selected)){restore();return;}
  alignmentNote(pos);lineNotes(pos);syncDetails();
  const pool=spatial()?SG_SOURCES.sourcePool(sourceCtx,pos,width,sourceOptions):SG_SOURCES.windowPool(sourceCtx,pos,width,mode);
  const stat=copyView()?SG_COPY.measure(copyCtx,pos,pool,true):SG_SOURCES.measure(sourceCtx,pool,true),active=new Map(),context=new Set(),raw=new Map(pool.indices.map((i,k)=>[i,pool.weights[k]]));
  const distances=new Map(copyView()?stat.items.map(x=>[x.position,x.distance]):[]);
  const mass=pool.weights.reduce((a,b)=>a+b,0),maxWeight=Math.max(0,...pool.weights);
  for(const i of new Set([...pool.indices,pos])){
   context.add(data.lines[data.lineOf[i]].page);
   for(const b of tokenBoxes.get(i)||[]){if(!active.has(b))active.set(b,[]);active.get(b).push(i);}
  }
  const svg=box.closest('svg');svg.querySelector('[tabindex="0"]')?.setAttribute('tabindex','-1');box.setAttribute('tabindex','0');
  anchored(box,()=>{
   clearMarks();selected=pos;origin=box;atlas.classList.add('window-mode');visibility(context);marked=[...active.keys()];
   restoreButton.hidden=false;shared.hidden=indices.length<2;
   choose.replaceChildren(...indices.map(i=>new Option(data.words[i]+' · word '+(i+1),i,false,i===pos)));
   summary.textContent=inspectionLabel(box,pos)+' · '+(pool.missingTarget?'No resolved word-level location for this target':sourceText(stat))+(spatial()&&pool.available>stat.n?' · capped from '+pool.available+' eligible words':'');
   instructions();
   if(spatial()&&!copyView()){
    caption.textContent+=' Highlighted sources vary in brightness with their relative draw weight; hover for probabilities.';
    setLegend(['0','25%','50%','75%','100%']);
    document.querySelector('#heatmapLegend .spectrum').style.background='linear-gradient(90deg,var(--surface),var(--heat-single))';
    document.getElementById('legendLabel').textContent='Source weight relative to strongest · target score shown below';
   }
   if(spatial()){drawSourceGuide(box,pos);drawSourceWords(active,pos,distances);}
   if(copyView()){setLegend(['0 · copy','1','2','3','4','5+']);document.querySelector('#heatmapLegend .spectrum').style.background='linear-gradient(90deg,'+[0,1,2,3,4,5].map(SG_COPY.distanceColor).join(',')+')';document.getElementById('legendLabel').textContent='Selected cone: distance from each source to '+data.words[pos];}
   for(const [b,ids] of active){
    b.classList.add('window-member');const isSelected=ids.includes(pos);b.classList.toggle('window-selected',isSelected);
    if(isSelected)b.setAttribute('aria-pressed','true');
    if(spatial()&&!isSelected){b.style.fill=copyView()?SG_COPY.distanceColor(Math.min(...ids.map(i=>distances.get(i)??Infinity))):'var(--heat-single)';b.style.opacity=copyView()?'1':String(.25+.75*Math.max(...ids.map(i=>raw.get(i)||0))/maxWeight);}
    byBox.get(b).title.textContent=boxIdentity(byBox.get(b))+' · '+ids.map(i=>data.words[i]+(spatial()?(i===pos?' · target; excluded from source pool':(copyView()?' · '+distances.get(i)+' glyph edits':'')+' · '+(100*(raw.get(i)||0)/mass).toFixed(2)+'% geometry weight'):' · '+sourceText(sourceStats[i]))).join(' / ');
   }
   pageDisplay.labels();
   if(copyView()){
    const near=stat.sources.filter(s=>s.distance<=editRadius),shown=(near.length?near:stat.sources.filter(s=>s.distance===stat.minedit)).slice(0,20);
    contribList.innerHTML='<span class="contrib-head">'+(near.length?'Candidates within '+editRadius+' edits':'No candidate within '+editRadius+' edits; nearest sources')+':</span>'+shown.map(s=>'<button type="button" data-copyword="'+SG.esc(s.word)+'" aria-pressed="false"><b>'+SG.esc(s.word)+'</b> · d='+s.distance+' · ×'+s.positions.length+'</button>').join('')+(near.length>20?'<span class="more">+'+(near.length-20)+' spellings</span>':'');
    contribList.hidden=!stat.n;let focus=null;
    for(const btn of contribList.querySelectorAll('button'))btn.onclick=()=>{focus=focus===btn.dataset.copyword?null:btn.dataset.copyword;for(const x of contribList.querySelectorAll('button'))x.setAttribute('aria-pressed',String(x.dataset.copyword===focus));for(const [b,ids] of active)b.classList.toggle('window-related',!!focus&&ids.some(i=>raw.has(i)&&data.words[i]===focus));};
    return;
   }
   const kind=colorMode==='h1'?'mono':colorMode==='mattr'?'word':'pairs';
   const top=kind==='word'?stat.types.slice(0,8).map(x=>({name:x.word,p:x.p})):kind==='mono'?stat.topUnits:stat.topPairs;
   contribList.innerHTML='<span class="contrib-head">'+(kind==='word'?'Weighted source spellings':kind==='mono'?'Weighted glyph units':'Weighted within-word pairs')+':</span>'+top.map(x=>'<button type="button" data-component="'+SG.esc(x.name)+'" aria-pressed="false" title="Click to outline source words containing this component"><b>'+SG.esc(x.name)+'</b> '+(100*x.p).toFixed(1)+'%</button>').join('');
   contribList.hidden=!top.length;let activeName=null;
   for(const btn of contribList.querySelectorAll('button'))btn.addEventListener('click',()=>{
    activeName=activeName===btn.dataset.component?null:btn.dataset.component;
    for(const other of contribList.querySelectorAll('button'))other.setAttribute('aria-pressed',String(other.dataset.component===activeName));
    for(const [b,ids] of active)b.classList.toggle('window-related',!!activeName&&ids.some(i=>raw.has(i)&&(kind==='word'?data.words[i]===activeName:sourceCtx.tokenFeatures[i][kind].some(([id])=>(kind==='mono'?sourceCtx.unitNames:sourceCtx.pairNames)[id]===activeName))));
   });
  });
 }
 function renderContrib(w,active){
  if(attribution()){contribList.hidden=true;return;}
  const C=SG_HEATMAP.contributions(w),top=C.spellings.slice(0,12),esc=SG.esc;
  if(!C.spellings.some(s=>s.word===contribWord))contribWord=null;
  const swatch=(c,label)=>'<span class="ck"><i style="background:'+copiesFill(c)+'"></i>'+label+'</span>';
  contribList.innerHTML='<span class="contrib-head">'+w.unique+' distinct of '+w.size+' · repeats cost '+C.lost+' form'+(C.lost===1?'':'s')+(C.lost?' ('+pp(-C.lost/width)+')':'')+(C.spellings.length?':':'')+'</span>'+
   top.map(s=>'<button type="button" data-word="'+esc(s.word)+'" aria-pressed="'+(s.word===contribWord)+'" title="'+esc(s.word)+': '+s.count+' copies in this window, costing '+s.lost+' form'+(s.lost===1?'':'s')+' ('+pp(-s.lost/width)+'), '+Math.round(100*s.share)+'% of the window’s repetition. Click to outline its copies."><b>'+esc(s.word)+'</b> ×'+s.count+' <small>'+pp(-s.lost/width)+'</small></button>').join('')+
   (C.spellings.length>top.length?'<span class="more">+'+(C.spellings.length-top.length)+' more repeated</span>':'')+
   (contribColors()?'<span class="contrib-key">'+swatch(1,'once')+swatch(2,'×2')+swatch(3,'×3')+swatch(4,'×4')+swatch(5,'×5+')+'</span>':'');
  contribList.hidden=false;
  const outline=()=>{for(const [b,ids] of active)b.classList.toggle('window-related',!!contribWord&&ids.some(i=>data.words[i]===contribWord));};
  for(const btn of contribList.querySelectorAll('button[data-word]'))btn.addEventListener('click',()=>{
   contribWord=contribWord===btn.dataset.word?null:btn.dataset.word;
   for(const x of contribList.querySelectorAll('button[data-word]'))x.setAttribute('aria-pressed',String(x.dataset.word===contribWord));outline();});
  queueMicrotask(outline);
 }
 function saveHash(){SG.setHash({...SG.hash(),...pageDisplay.hash(),scope:selector?.value,window:width,direction:mode,colors:colorMode,line:selected>=0&&expandedPage?data.lines[data.lineOf[selected]].locus:undefined,left:sourceOptions.left,depth:sourceOptions.depth,angle:sourceOptions.angle,weight:sourceWeight.value,target:sourceOptions.target==='cursor'?'cursor':undefined,edits:editRadius,count:countUnit,expanded:expandedPage?.dataset.page});}
 function readControls(){
  const raw=Number(size.value);
  width=Number.isFinite(raw)?Math.max(2,Math.min(1000,Math.round(raw))):100;
  size.value=width;mode=direction.value;colorMode=colors.value;
  if(copyView()){mode='spatial';direction.value=mode;}
  editRadius=Math.max(0,Math.min(3,Number(editLimit.value)||0));countUnit=candidateUnit.value==='Occurrences'?'Occurrences':'Types';
  if(spatial()&&['repeat','overlay','impact','change'].includes(colorMode)){colorMode='mattr';colors.value=colorMode;}
  const clamp=(control,lo,hi,fallback)=>{const n=Number(control.value),v=control.value!==''&&Number.isFinite(n)?Math.max(lo,Math.min(hi,n)):fallback;control.value=v;return v;};
  sourceOptions={left:clamp(leftReach,0,20,3),depth:clamp(aboveDepth,1,100,8),angle:clamp(coneAngle,0,85,45),weight:sourceWeight.value==='uniform'?'uniform':'distance',metric:sourceWeight.value==='edge'?'edge':'centre',target:targetMode.value==='cursor'?'cursor':'box'};
 }
 function recolor(){
  rolling=SG_HEATMAP.series(data.words,width,spatial()?'backward':mode);
  if(computedWidth!==width||!impact)impact=SG_HEATMAP.wordImpact(data.words,width);
  computedWidth=width;computedMode=mode;
  for(const entry of entries){
   entry.box.setAttribute('fill',paintColor(boxScore(entry.indices)));
   markRepeat(entry.box,entry.indices.map(i=>rolling.repeated[i]));
   entry.box.classList.toggle('incomplete',entry.indices.every(i=>!Number.isFinite(rolling.scores[i])));
  }
 }
 let busyJob=null;
 function setBusy(stage,percent=null){
  if(!stage){atlas.removeAttribute('aria-busy');busyJob?.end();busyJob=null;return;}
  atlas.setAttribute('aria-busy','true');const text=stage+(percent===null?'…':' · '+percent+'%');
  if(busyJob)busyJob.set(text);else busyJob=SG.busyStart(text);
 }
 async function update(){
  clearTimeout(sizeTimer);
  if(destroyed)return;
  const ticket=++revision;
  readControls();setBusy('Updating colors');
  try{
   await SG.nextPaint();if(ticket!==revision||destroyed)return;       // not a bare animation frame: that runs before the paint, and the indicator would never show
   if(advanced()){
    const key=JSON.stringify([width,mode,sourceOptions,copyView()]);
    if(key!==sourceKey){
     const stage='Calculating '+(spatial()?'spatial source pools':'component distributions');setBusy(stage,0);
     const progress=(done,total)=>{if(ticket===revision)setBusy(stage,Math.floor(100*done/total));};
     const result=copyView()?await SG_COPY.series(copyCtx,sourceCtx,width,sourceOptions,()=>ticket===revision&&!destroyed,progress):await SG_SOURCES.series(sourceCtx,width,mode,sourceOptions,()=>ticket===revision&&!destroyed,progress);
     if(!result||ticket!==revision)return;sourceStats=result;sourceKey=key;
     colorDomains=Object.fromEntries(['components','h1','h2','js'].map(key=>[key,SG_SOURCES.colorDomain(result.map(s=>s[key]))]));
    }
   }
   if(!rolling||computedWidth!==width||computedMode!==mode)recolor();
   paintAttribution();
   setBusy(null);
   if(pendingLine!==null){                        // line=<locus> in the address: select that line's first word on the expanded page
    const want=String(pendingLine),page=expandedPage?.dataset.page;pendingLine=null;
    const L=page?data.lines.find(l=>l.page===page&&String(l.locus)===want):null,box=L?(tokenBoxes.get(L.start)||[])[0]:null;
    if(box){selected=-1;select(box,L.start,false);}
   }
   if(selected>=0)select(origin,selected,false);else{instructions();summary.textContent='Click any word to highlight its calculation window on the pages.';}
   saveHash();
   document.dispatchEvent(new CustomEvent('heatmap:updated'));
  }catch(error){
   if(ticket===revision){summary.textContent='Could not calculate this view. Change a control or reload to retry.';document.querySelector('.window-status').classList.remove('idle');console.error(error);}
  }finally{if(ticket===revision)setBusy(null);}
 }
 function fromHash(){
  const h=SG.hash();if(selector)selector.value=scopeDefs.has(h.scope)?h.scope:'all';size.value=h.window||100;
  direction.value=['backward','forward','centered','spatial'].includes(h.direction)?h.direction:'backward';
  const builtIn=['none','mattr','repeat','overlay','impact','change','components','h1','h2','js','minedit','candidates'];
  const asked=h.colors&&h.colors.startsWith('m:')?data.measures?.[h.colors.slice(2)]:null;
  colors.value=builtIn.includes(h.colors)||(asked&&asked.menu!==false)?h.colors:'none';
  editLimit.value=['0','1','2','3'].includes(h.edits)?h.edits:'1';candidateUnit.value=h.count==='Occurrences'?'Occurrences':'Types';
  leftReach.value=h.left??3;aboveDepth.value=h.depth??8;coneAngle.value=h.angle??45;sourceWeight.value=['uniform','edge'].includes(h.weight)?h.weight:'distance';targetMode.value=h.target==='cursor'?'cursor':'box';
  pageDisplay.readHash(h);pendingLine=h.line!=null&&h.line!==''?h.line:null;
  const figure=pageFigures.get(h.expanded)||null;if(figure===expandedPage)pageDisplay.expand(figure);else expandPage(figure,false);
 }
 on(atlas,'click',e=>{const box=e.target.closest('rect[data-token-indices]');if(box)select(box,byBox.get(box).indices[0]);else if(selected>=0&&e.target.closest('svg'))restore();});
 on(atlas,'pointerover',e=>{const entry=byBox.get(e.target);if(rolling&&entry&&!entry.box.classList.contains('window-member'))entry.title.textContent=normalTitle(entry);});
 on(atlas,'focusin',e=>{const entry=byBox.get(e.target);if(rolling&&entry&&!entry.box.classList.contains('window-member'))entry.title.textContent=normalTitle(entry);});
 on(atlas,'keydown',e=>{
  const box=e.target.closest('rect[data-token-indices]');if(!box)return;
  if(e.key==='Enter'||e.key===' '){e.preventDefault();select(box,byBox.get(box).indices[0]);}
  else if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){
   e.preventDefault();const siblings=[...box.closest('svg').querySelectorAll('rect[data-token-indices]:not(.invalid-geometry):not(.no-native-box)')],i=siblings.indexOf(box);
   if(!siblings.length)return;
   const j=e.key==='Home'?0:e.key==='End'?siblings.length-1:Math.max(0,Math.min(siblings.length-1,i+(e.key==='ArrowRight'?1:-1)));
   box.setAttribute('tabindex','-1');siblings[j].setAttribute('tabindex','0');siblings[j].focus({preventScroll:true});
   if(selected>=0)select(siblings[j],byBox.get(siblings[j]).indices[0],false);
  }
 });
 on(choose,'change',()=>select(origin,Number(choose.value),false));
 on(restoreButton,'click',()=>restore(true));
 on(document,'keydown',e=>{if(e.key==='Escape'){if(selected>=0){e.preventDefault();restore(true);}else if(expandedPage){e.preventDefault();showPage(null);}}});
 for(const control of [size,direction,colors,leftReach,aboveDepth,coneAngle,sourceWeight,targetMode,editLimit,candidateUnit])on(control,'change',update);
 on(size,'input',()=>{clearTimeout(sizeTimer);if(size.value!==''&&size.validity.valid)sizeTimer=setTimeout(update,180);});
 on(size,'keydown',e=>{if(e.key==='Enter'){e.preventDefault();update();}});
 if(selector)on(selector,'change',()=>SG.busy('Updating the rows…',()=>{if(destroyed)return;expandPage(null);restore();saveHash();}));
 on(window,'hashchange',()=>SG.busy('Updating the view…',()=>{if(destroyed)return;fromHash();restore();return update();}));
 // bind the data
 sourceCtx=SG_SOURCES.prepare(data);copyCtx=SG_COPY.prepare(data);
 for(const entry of entries){
  const g=data.spatialReview?.groups[data.spatialReview.tokens[entry.indices[0]].group];
  entry.box.setAttribute('aria-label','Inspect '+SG_REVIEW.boxLabel(data,entry.indices));
  if(g&&!g.safe){entry.box.classList.add('invalid-geometry');entry.box.setAttribute('tabindex','-1');}
  else if(entry.indices.some(i=>sourceCtx.excluded.has(i)))entry.box.classList.add('alignment-ambiguous');
  if(g&&g.status==='detected')entry.box.classList.add('detected-box');
 }
 pageDisplay.setData(data);
 fromHash();visibility();summary.textContent='Calculating…';setBusy('Loading');
 const ready=update();
 return {
  ready,
  destroy(){destroyed=true;revision++;setBusy(null);abort.abort();clearTimeout(sizeTimer);SG.hideTip();for(const g of atlas.querySelectorAll('.source-guide'))g.remove();for(const old of colors.querySelectorAll('optgroup[data-bundle-measures]'))old.remove();},
  update,
  reorder(ids){const host=rows[0]?.parentElement;if(!host)return;const byId=new Map(rows.map(r=>[r.dataset.row,r]));for(const id of ids){const r=byId.get(id);if(r)host.append(r);}},
  rowMeans(){return new Map(rows.map(r=>[r.dataset.row,r.dataset.mean===''||r.dataset.mean==null?NaN:Number(r.dataset.mean)]));},
  rowIds(){return rows.map(r=>r.dataset.row);},
  onDisplayChange(){if(selected>=0&&rolling&&!atlas.hasAttribute('aria-busy'))select(origin,selected,false);saveHash();},
  state(){return {width,mode,colorMode,selected};}
 };
}
return {mount};
})();
if(typeof module!=='undefined')module.exports=VMS_HEATMAP;
