"use strict";
/* The comparison page: loads the compare data (index.json key `compare`) and the manuscript bundle's words, keeps the
   state in the address (compare_state.js), selects and scores pages with compare_math.js and draws them as SVG in a
   common frame. Views: overlay, side by side, composite, segments, top matches, wheels. */
(async()=>{
 const {$,esc}=SG,S=COMPARE_STATE,M=VMS_COMPARE,Words=VMS_WORDS,NS='http://www.w3.org/2000/svg';
 const status=$('status'),figure=$('figure'),readout=$('readout'),extra=$('extra'),tools=$('viewTools'),zoomLevel=$('zoomLevel');
 const ctl={a:$('pageA'),b:$('pageB'),order:$('order'),text:$('text'),cutoff:$('cutoff'),words:$('words'),expand:$('expand'),wdir:$('wdir'),boxes:$('boxes'),step:$('step'),drift:$('drift'),color:$('color'),align:$('align'),coords:$('coords'),scale:$('scale'),scope:$('scope'),face:$('face'),blockA:$('blockA'),blockB:$('blockB'),metric:$('metric'),gain:$('gain')};
 function fail(message){status.textContent='Error: '+message;status.classList.add('error-text');}
 addEventListener('error',e=>fail(e.message||String(e.error)));addEventListener('unhandledrejection',e=>fail((e.reason&&e.reason.message)||String(e.reason)));
 const el=(tag,attrs={},text)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))if(v!=null&&v!=='')n.setAttribute(k,String(v));if(text!=null)n.textContent=text;return n;};
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 // a word's direction on the page, from its line's orientation record: 0 = level, null = turned but direction unknown
 const wordAngle=t=>{const L=lines[lineOfToken[t]];return L?Words.angleOf(L.orientation,t-L.start):0;};
 // the labels of the turned words of one group (a page, a wheel), by unit id; level text keeps its box fit
 function wordFaces(units){
  const turned=units.filter(u=>wordAngle(u.first)!==0);if(turned.length)turnedShown=true;
  const faces=Words.layout(turned.map(u=>({rect:u.rect,text:u.text,angle:wordAngle(u.first)})),state.wdir);
  return new Map(turned.map((u,i)=>[u.id,faces[i]]));
 }
 function wordLabel(f,cls,text,style){
  const x=f.x.toFixed(1),y=f.y.toFixed(1);
  return el('text',{class:cls,x,y,'text-anchor':'middle','dominant-baseline':'central','font-size':f.size.toFixed(2),transform:f.angle?`rotate(${f.angle.toFixed(1)} ${x} ${y})`:null,style},text);
 }
 const f3=x=>Number.isFinite(x)?x.toFixed(3):'—',deg=x=>x==null?'—':(x>=0?'+':'−')+Math.abs(x).toFixed(2)+'°',color=k=>`var(--cmp-${(k%12)+1})`;
 const META={both:'combined rank',dice:'Dice',js:'JS distance',spatial:'position-constrained EVA'};
 // a flat sheet's slots by where the page sits when the face is open (A verso and B recto form the inner face, B verso and A recto the outer)
 const SLOT_NAMES={Av:'inner left',Br:'inner right',Bv:'outer left',Ar:'outer right'};
 const PALETTE=SG.defaultPalette();
 let index,compact,orders,words,rankings=null,wheels=null,quarantine=new Set(),C=null,lines=[],lineOfToken=null,turnedShown=false;
 let state=S.parse(SG.hash()),res=S.resolveText(state),list=[],sheets=[],view=null,full=null,frameKey='',panels=[],pendingZoom=state.zoom,groupHit=null,ticket=0,domain=[0,1];
 const kept=new Map();let moved=false,overviewScroll=0;   // per panel, the line page moves keep, which a short page can only approximate; whether render must place them; where a maximize left the page
 const last={a:null,b:null,det:null,scores:null,perLine:null,drift:null};
 // the left margin: each page's line labels, then its paragraph bar and number; narrow panels keep the bars only
 const WIDE_MARGIN={columns:[4,46],bar:26,numbers:true,px:92},NARROW_MARGIN={columns:[4,33],bar:26,numbers:false,px:72},NARROW_PANEL=500;
 let margin=WIDE_MARGIN;
 let shown=[];                                        // the panels of the last render
 // ---- data
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  index=await SG.load(SG.dataUrl('index.json'));C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const bundle=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];
  [compact,orders,words]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(bundle.path)).then(d=>{lines=d.lines;return d.words;})]);
 }catch(error){status.textContent='Could not load the comparison data.';SG.error(figure,error);return;}
 quarantine=new Set(compact.quarantine||[]);
 lineOfToken=new Int32Array(words.length).fill(-1);lines.forEach((L,i)=>{for(let t=L.start;t<L.end;t++)lineOfToken[t]=i;});
 const loadRankings=()=>rankings?Promise.resolve(rankings):SG.load(SG.dataUrl(C.rankings)).then(r=>(rankings=r));
 const loadWheels=()=>wheels?Promise.resolve(wheels):SG.load(SG.dataUrl(C.wheels)).then(w=>(wheels=w));
 $('baselineNote').textContent=`Data ${compact.version} · anchors: ${compact.baseline} baseline (ink where the page has clean ink records, glyph-corrected box baseline elsewhere; ${compact.baseline_pages?Object.entries(compact.baseline_pages).map(([k,v])=>v+' '+k).join(', '):''}) · geometry policy ${compact.policy} · ${Object.keys(compact.pages).length} pages.`;
 // ---- lists and controls
 const ORDER_LABELS={bifolia:'Bifolia',folio:'Folio',path1:'Path 1'};
 ctl.order.replaceChildren(...S.ORDERS.filter(k=>orders[k]).map(k=>new Option(ORDER_LABELS[k]||orders[k].label||k,k)));
 for(const k of S.ORDERS)if(orders[k]&&orders[k].note)ctl.order.querySelector(`option[value="${k}"]`).title=orders[k].note;
 const pagesMode=()=>state.scope==='pages';
 const sheetById=id=>sheets.find(s=>s.id===id)||null;
 const sectionOf=f=>(compact.pages[f]&&compact.pages[f].section)||'';
 function rebuildLists(){list=S.pageList(orders,state.order,compact.pages);sheets=S.sheetList(compact.pages,list);}
 function currentList(){return pagesMode()?list:sheets.map(s=>s.id);}
 function fillPickers(){
  const options=pagesMode()?list.map(f=>[f,f+' · '+sectionOf(f)]):sheets.map(s=>[s.id,s.id+' · '+sectionOf(s.slots.Av[0]||s.slots.Ar[0]||s.slots.Br[0]||s.slots.Bv[0])]);
  for(const sel of [ctl.a,ctl.b])sel.replaceChildren(...options.map(([v,t])=>new Option(t,v)));
  const ids=currentList();
  if(!ids.includes(state.a))state.a=ids[0];if(!ids.includes(state.b))state.b=ids[Math.min(1,ids.length-1)];
  ctl.a.value=state.a;ctl.b.value=state.b;
 }
 function blockLabel(p,k,lines){if(k==='opening')return 'Opening';if(k==='page')return 'Whole page';if(k[0]==='p')return 'Paragraph '+k.slice(1)+' · '+lines.length+(lines.length===1?' line':' lines');const L=p.lines[lines[0]];return 'Line '+L[0]+' · '+(L[3]==='horizontal'?'horizontal':L[3]);}
 function slotFolios(id){return S.slotPages(sheetById(id),state.face).map(x=>x.folio);}
 function currentFolios(){return pagesMode()?[state.a,state.b]:[slotFolios(state.a)[0],slotFolios(state.b)[0]];}
 function fillBlocks(){
  const fill=(sel,folio,key)=>{const p=compact.pages[folio];if(!p){sel.replaceChildren();return key;}sel.replaceChildren(...p.blocks.map(([k,lines])=>new Option(blockLabel(p,k,lines),k)));sel.value=key;if(sel.value!==key)sel.value=p.blocks[0][0];return sel.value;};
  const [fa,fb]=currentFolios();
  if(state.text==='custom'){state.blocka=fill(ctl.blockA,fa,state.blocka);state.blockb=fill(ctl.blockB,fb,state.blockb);}else{fill(ctl.blockA,fa,res.blocka);fill(ctl.blockB,fb,res.blockb);}
  res=S.resolveText(state);ctl.cutoff.value=res.cutoff;
 }
 function syncControls(){
  ctl.order.value=state.order;ctl.text.value=state.text;ctl.words.checked=state.words;ctl.expand.checked=state.expand;$('expandLabel').hidden=!stackable();ctl.wdir.value=state.wdir;ctl.boxes.value=state.boxes;ctl.step.value=pagesMode()?state.step:'bifolio';ctl.step.disabled=!pagesMode();ctl.drift.checked=state.drift;ctl.color.value=state.color;ctl.align.value=state.align;ctl.coords.value=state.coords;ctl.scale.value=state.scale;
  ctl.scope.value=state.scope;ctl.face.value=state.face;ctl.metric.value=state.metric;ctl.gain.value=String(state.gain);$('faceLabel').hidden=pagesMode();
  ctl.color.disabled=state.view==='composite'||state.view==='wheels';
  for(const b of $('views').querySelectorAll('button')){const on=b.dataset.view===state.view;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));}
  fillPickers();
 }
 function save(){SG.setHash({data:SG.hash().data,...S.serialize(state)});}
 const stackable=()=>state.view==='overlay'||state.view==='matches',stacked=()=>state.expand&&stackable();   // Expand all lines applies in these views
 function clearTransient(){state.lines=[];state.seg=null;groupHit=null;}
 function clearPanels(){clearTransient();state.max=null;kept.clear();}          // the panels themselves change
 // ---- selections and panels
 function select(folio,block){
  const page=compact.pages[folio];if(!page)return null;
  const sel=M.selectUnits(page,words,{block,cutoff:res.cutoff==='all'?'all':Number(res.cutoff),coordinates:state.coords,alignment:state.align,scale:state.scale==='body'?'body_height':'pixels'});
  sel.folio=folio;return sel;
 }
 function compositeFolios(){
  if(state.pages.length)return state.pages.filter(f=>compact.pages[f]);
  return pagesMode()?[state.a,state.b]:[...slotFolios(state.a),...slotFolios(state.b)].filter(Boolean);
 }
 const sideName=s=>s.tag==='A'||s.tag==='B'?s.tag+' '+s.sel.folio:s.tag;
 const hidden=s=>S.isHidden(state,S.hideKey(state,s.tag));
 function buildPanels(){
  const v=state.view;
  if(v==='composite'){const folios=compositeFolios();return [{title:'Composite',sels:folios.map((f,k)=>({sel:select(f,res.blocka),k,tag:f}))}];}
  if(pagesMode()){
   const a={sel:select(state.a,res.blocka),k:0,tag:'A'},b={sel:select(state.b,res.blockb),k:1,tag:'B'};
   return v==='side'?[{title:'',sels:[a]},{title:'',sels:[b]}]:[{title:'',sels:[a,b]}];
  }
  const out=[],pa=S.slotPages(sheetById(state.a),state.face),pb=S.slotPages(sheetById(state.b),state.face);
  pa.forEach((x,i)=>{const y=pb[i];
   const a={sel:x.folio?select(x.folio,res.blocka):null,k:0,tag:'A',panels:x.panels},b={sel:y.folio?select(y.folio,res.blockb):null,k:1,tag:'B',panels:y.panels};
   if(v==='side')out.push({title:SLOT_NAMES[x.slot],slot:x.slot,sels:[a]},{title:SLOT_NAMES[y.slot],slot:y.slot,sels:[b]});else out.push({title:SLOT_NAMES[x.slot],slot:x.slot,sels:[a,b]});});
  return out;
 }
 // the two selections a click in panel k compares: a panel holding both pages, or a pair of panels in the side view
 const lineViews=['overlay','matches','side'];
 function pairAt(k){
  if(state.view==='side'){const q=Math.floor(k/2),x=shown[2*q],y=shown[2*q+1];return x&&y?{a:x.sels[0].sel,b:y.sels[0].sel,panel:q}:null;}
  const p=shown[k];return p&&p.sels.length===2?{a:p.sels[0].sel,b:p.sels[1].sel,panel:k}:null;
 }
 const readable=pair=>!!(pair&&pair.a&&pair.b&&pair.a.all.length&&pair.b.all.length);
 // the live overlap colours of every two-selection pairing (both pages of a panel, or the two panels of the side view)
 function assignColors(ps){
  for(const p of ps)for(const s of p.sels)s.ov=null;
  if(state.color==='pages'||state.view==='composite')return;
  const pairs=[];
  for(const p of ps)if(p.sels.length===2&&p.sels[0].sel&&p.sels[1].sel)pairs.push([p.sels[0],p.sels[1]]);
  if(!pairs.length&&state.view==='side')for(let i=0;i+1<ps.length;i+=2)if(ps[i].sels[0].sel&&ps[i+1].sels[0].sel)pairs.push([ps[i].sels[0],ps[i+1].sels[0]]);
  for(const [a,b] of pairs){const ov=S.overlapValues(a.sel,b.sel);a.ov=ov.a;b.ov=ov.b;}
  domain=S.colorDomain(ps.flatMap(p=>p.sels).filter(s=>s.ov).flatMap(s=>[...s.ov.values()].map(v=>v&&v[state.color])));
 }
 // ---- drawing
 function tagButton(s,label,key,{none=false}={}){
  const tag=h('button','tag'+(none?' none':S.isHidden(state,key)?' off':'')),sw=h('i','swatch');sw.style.setProperty('--c',color(s.k));tag.type='button';
  tag.append(sw,document.createTextNode(label));
  if(none){tag.disabled=true;return tag;}
  tag.setAttribute('aria-pressed',String(!S.isHidden(state,key)));tag.dataset.tip=(S.isHidden(state,key)?'Show ':'Hide ')+label;
  tag.onclick=()=>{state=S.toggleHidden(state,key);render();};
  return tag;
 }
 function maxButton(p,k){
  const on=state.max===k,b=h('button','maximize',on?'⤡ Back to all':'⤢');b.type='button';
  b.title=on?'Return to all panels':'Maximize '+(p.title||p.sels.filter(s=>s.sel).map(sideName).join(' and '));b.setAttribute('aria-label',b.title);b.setAttribute('aria-pressed',String(on));
  b.onclick=()=>setMax(on?null:k);return b;
 }
 const toolbarHeight=()=>document.querySelector('.compare .toolbar').offsetHeight;
 function setMax(k){if(k!=null)overviewScroll=scrollY;state.max=k;render();scrollTo({top:k==null?overviewScroll:figure.getBoundingClientRect().top+scrollY-toolbarHeight()-8,behavior:'instant'});}   // the toolbar is sticky: stop below it
 function drawPanel(p,F,{det,hit,k,many}){
  const wrap=h('div','panel'),head=h('h3'),split=p.split,open=split&&split.bands;
  if(p.title)head.append(h('span','',p.title));
  for(const s of p.sels){if(!s.sel)continue;head.append(tagButton(s,sideName(s)+(s.panels>1?' (+'+(s.panels-1)+' more panels)':''),S.hideKey(state,s.tag)));}
  if(many)head.append(maxButton(p,k));
  const svg=el('svg',{viewBox:`${F.x} ${F.y} ${F.w} ${F.h}`,role:'img','data-panel':k,'aria-label':(p.title||'Overlay')+' of '+p.sels.filter(s=>s.sel).map(sideName).join(' and ')});
  if(p.sels.length>2)svg.classList.add('many');if(hit)svg.classList.add('dim');if(p.sels.some(s=>s.ov))svg.classList.add('colored');
  svg.append(el('line',{class:'zero',x1:F.x,x2:F.x+F.w,y1:0,y2:0}));
  const sels=p.sels;sels.forEach((s,i)=>{s.draw=s.sel?(split?split.selections[i]:s.sel):null;});
  if(open)for(const [y0,y1] of split.bands)svg.append(el('rect',{class:'band',x:F.x,y:y0,width:F.w,height:y1-y0}));
  else if(split){
   svg.append(el('rect',{class:'band',x:F.x,y:split.start,width:F.w,height:split.end-split.start}));
   split.row_tops.forEach((y,k)=>svg.append(el('text',{class:'band-head',x:F.x+12,'data-px':margin.px+4,y:y-5,style:'--c:'+color(sels[k].k)},(k?'B ':'A ')+sels[k].sel.folio+' · line '+(split.indices[k]+1))));
  }
  if(det&&sels.length===2&&sels[0].draw&&sels[1].draw&&!hidden(sels[0])&&!hidden(sels[1])){
   const g=el('g',{class:'shared-layer'}),A=sels[0].draw.chosen,B=sels[1].draw.chosen;
   for(const x of A)for(const y of B){const r=M.intersection(x.rect,y.rect);if(r)g.append(el('rect',{class:'shared',x:r[0],y:r[1],width:r[2]-r[0],height:r[3]-r[1]}));}
   svg.append(g);
  }
  sels.forEach((s,i)=>{
   if(!s.draw||hidden(s))return;
   const g=el('g',{class:'page-layer',style:'--c:'+color(s.k),'data-side':s.k}),vis=S.visible(s.draw,res.cutoff);
   const hitIds=hit?new Set(s.tag==='A'?hit.a:s.tag==='B'?hit.b:[]):null,bandLine=split&&!open?split.indices[i]:null;
   const paint=new Map();
   for(const u of vis){
    const cls=['u',u.anchor?'anchor':u.selected?'':'ctx',hitIds&&hitIds.has(u.id)?'hit':''].filter(Boolean);
    let tip=`<b>${esc(sideName(s))}</b> · line ${u.line+1} · ${esc(u.text)}`+(u.anchor?'<div class="tipsub">anchor box: sets the origin</div>':'')+(!u.selected&&!u.anchor?'<div class="tipsub">context beyond the line cutoff, not scored</div>':'')+(u.grouped?'<div class="tipsub">one rectangle holding several tokens</div>':'')+(u.intrusion?'<div class="tipsub">intrusion break after this word</div>':'');
    const attrs={class:'',x:u.rect[0],y:u.rect[1],width:u.rect[2]-u.rect[0],height:u.rect[3]-u.rect[1],'data-side':s.k,'data-id':u.id,'data-line':u.line};
    if(s.ov&&u.selected){
     const v=s.ov.get(u.id),value=v?v[state.color]:null,idx=S.colorIndex(value,state.color,domain);
     if(idx===null){cls.push('nohit');tip+=`<div class="tipsub">${v?S.COLOR_LABELS[state.color]+': no glyph pairs to compare':'nothing of the other page touches this box'}</div>`;}
     else{cls.push('painted');paint.set(u.id,PALETTE[idx]);attrs.style=`fill:${PALETTE[idx]};stroke:${PALETTE[idx]}`;tip+=`<div class="tipsub">${S.COLOR_LABELS[state.color]} ${f3(value)} · against ${esc(v.text)}</div>`;}
    }
    attrs.class=cls.join(' ');attrs['data-tip']=tip;g.append(el('rect',attrs));
   }
   const byLine=new Map();for(const u of vis){if(!byLine.has(u.line))byLine.set(u.line,[]);byLine.get(u.line).push(u);}
   for(const units of byLine.values()){units.sort((x,y)=>x.rect[0]-y.rect[0]);for(let j=0;j<units.length-1;j++){const u=units[j],v=units[j+1];if(u.intrusion&&v.rect[0]>u.rect[2])g.append(el('line',{class:'mark',x1:u.rect[2],x2:v.rect[0],y1:u.baseline,y2:u.baseline,'data-tip':'Intrusion break in the transcription (ZL &lt;-&gt; or &lt;~&gt;) between '+esc(u.text)+' and '+esc(v.text)}));}}
   const column=margin.columns[sels.length===2?s.k:0];
   if(sels.length<=2)for(const sp of S.paragraphSpans(s.draw,res.cutoff)){
    const H=s.draw.H||30,tip=`<b>${esc(sideName(s))}</b> · paragraph ${sp.n}<div class="tipsub">${sp.first===sp.last?'line '+sp.first:'lines '+sp.first+' to '+sp.last}${sp.rows<sp.total?` · ${sp.rows} of ${sp.total} lines shown`:''}</div>`;
    g.append(el('line',{class:'pbar',x1:F.x,x2:F.x,y1:sp.y0-.7*H,y2:sp.y1+.15*H,'data-px':column+margin.bar,'data-tip':tip}));
    if(margin.numbers)g.append(el('text',{class:'pnum',x:F.x,y:sp.y0,'data-px':column+margin.bar+4,'data-tip':tip},'¶'+sp.n));
   }
   if(sels.length<=2)for(const row of S.lineRows(s.draw,res.cutoff)){g.append(el('text',{class:'lnum',x:F.x,y:row.baseline,'data-px':column,'data-side':s.k,'data-line':row.index,'data-tip':`<b>${esc(sideName(s))}</b> · line ${row.index+1}${lineViews.includes(state.view)&&!open?'<div class="tipsub">click to read this line beside its partner</div>':''}<div class="tipsub">${esc(row.text)}</div>`},(s.tag==='A'||s.tag==='B'?s.tag:'')+(row.index+1)));}
   const shown=vis.filter(u=>state.words||open||u.line===bandLine),faces=wordFaces(shown);
   for(const u of shown){
    const cls='w'+(u.selected||u.anchor||u.line===bandLine?'':' ctx')+(hitIds&&hitIds.has(u.id)?' hit':''),f=faces.get(u.id),style=state.boxes==='hidden'&&paint.has(u.id)?`fill:${paint.get(u.id)}`:null;   // boxes hidden: the colour modes paint the word
    if(f){g.append(wordLabel(f,cls,u.text,style));continue;}
    const w=u.rect[2]-u.rect[0],hh=u.rect[3]-u.rect[1],size=Math.max(3,Math.min(hh*.62,1.6*w/Math.max(1,u.text.length)));
    g.append(el('text',{class:cls,x:(u.rect[0]+u.rect[2])/2,y:u.rect[1]+hh*.72,'text-anchor':'middle','font-size':size.toFixed(2),style},u.text));
   }
   svg.append(g);
  });
  if(state.drift)sels.forEach((s,i)=>{if(s.sel&&!hidden(s))drawDrift(svg,s,i,F,split);});
  wrap.append(head,svg);return wrap;
 }
 function drawDrift(svg,s,i,F,split){
  const sel=s.sel,page=sel.page,d=M.pageDrift(page,words,state.coords,quarantine.has(sel.folio));s.drift=d;
  const g=el('g',{class:'drift-layer',style:'--c:'+color(s.k)}),factor=sel.H/(page.H||30),drawn=split?split.selections[i]:sel,vis=S.visible(drawn,res.cutoff);
  const ax=u=>(u.base[0]-sel.origin[0])*factor;
  for(const l of d.lines){
   if(!l.qualifies)continue;
   const us=vis.filter(u=>u.line_abs===l.index&&u.anchor_kind!=='box centre').sort((p,q)=>ax(p)-ax(q));if(us.length<2)continue;
   const a=us[0],b=us[us.length-1];
   g.append(el('line',{class:'guide line-guide'+(s.k===1?' b':''),x1:ax(a),y1:a.baseline,x2:ax(b),y2:b.baseline,'data-tip':`<b>${esc(sideName(s))}</b> · line ${l.index+1} chord ${deg(l.angle)}<div class="tipsub">${l.units} boxes · ${state.coords} coordinates</div>`}));
  }
  const guide=split?null:M.driftGuide(d,state.gain,F.x,F.x+F.w);
  if(guide)g.append(el('line',{class:'guide'+(s.k===1?' b':''),x1:guide[0][0],y1:guide[0][1],x2:guide[1][0],y2:guide[1][1],'data-tip':`<b>${esc(sideName(s))}</b> · page drift ${deg(d.angle)}<div class="tipsub">median chord angle of ${d.n} lines · ${state.coords} coordinates${state.gain>1?' · drawn at slope ×'+state.gain:''} · through the origin</div>`}));
  svg.append(g);
 }
 function applyView(){$('wdirLabel').hidden=!turnedShown;
  if(!full)return;if(view&&S.isFit(view,full))view=null;const v=view||full;
  for(const svg of panels){svg.setAttribute('viewBox',`${v.x} ${v.y} ${v.w} ${v.h}`);const ctm=svg.getScreenCTM(),s=ctm?Math.max(ctm.a,1e-6):1;svg.style.setProperty('--fs',(11/s).toFixed(3)+'px');
   const left=ctm?(svg.getBoundingClientRect().left-ctm.e)/s:v.x;for(const t of svg.querySelectorAll('[data-px]')){const x=(left+Number(t.dataset.px)/s).toFixed(2);if(t.tagName==='line'){t.setAttribute('x1',x);t.setAttribute('x2',x);}else t.setAttribute('x',x);}}   // the labels hold the panel's left edge at any zoom
  zoomLevel.textContent=view?S.zoomScale(view,full).toFixed(view.w>full.w?2:1).replace(/\.?0+$/,'')+'×':'';state.zoom=view;save();
 }
 // ---- the readouts
 const metric=(v,l,d)=>{const m=h('div','metric');m.append(h('div','v',v),h('div','l',l));if(d)m.append(h('div','d',d));return m;};
 const textOf=sel=>sel.chosen.map(u=>u.text).join(' ');
 // how often a word occurs in the whole manuscript, for the opening words' readout
 let wordCounts=null;
 const countOf=u=>{if(u.first!==u.last)return null;if(!wordCounts){wordCounts=new Map();for(const w of words)wordCounts.set(w,(wordCounts.get(w)||0)+1);}return wordCounts.get(words[u.first])||0;};
 const rarity=n=>n==null?'':n===1?' (hapax)':` (${n}×)`;
 // the first words of the two blocks, which often say the most: a page's opening word is often a hapax
 function firstWords(a,b){
  const x=a.all.find(u=>u.anchor),y=b.all.find(u=>u.anchor);if(!x||!y)return null;
  const p=h('p','note first-words');p.append(h('b','','First words '),document.createTextNode(`${x.text}${rarity(countOf(x))} / ${y.text}${rarity(countOf(y))} · similarity ${f3(M.similarity(x.atoms,y.atoms))}`));return p;
 }
 const jsJoined=(a,b)=>M.jsDistance(M.lineFeatures(textOf(a)).joined,M.lineFeatures(textOf(b)).joined);
 function completeness(s){const sel=s.sel;if(!sel)return sideName(s)+': no page in this slot';if(!sel.available)return sel.fallback_line==null?`${sideName(s)}: no located boxes, not scored`:`${sideName(s)}: no box on the block's first line, aligned on line ${sel.fallback_line+1}, not scored`;if(!sel.complete)return `${sideName(s)}: ${sel.located} of ${sel.expected} lines located`;if(sel.nonhorizontal.length)return `${sideName(s)}: ${sel.nonhorizontal.join(', ')} lines in the block`;return null;}
 function colorBar(){
  if(state.color==='pages'||state.view==='composite'||state.view==='wheels')return null;
  const bar=h('div','cbar'),[lo,hi]=domain,ends={js:['alike','different'],sim:['different','alike'],area:['uncovered','covered']}[state.color];
  bar.append(h('b','',S.COLOR_LABELS[state.color]),h('span','',lo.toFixed(2)+' · '+ends[0]),h('i','spectrum'+(state.color==='js'?' rev':'')),h('span','',hi.toFixed(2)+' · '+ends[1]));
  bar.append(h('span','muted','scale: 5th to 95th percentile of the boxes in view'));
  const key=h('span','muted');key.append(h('i','nohit-key'),document.createTextNode(state.color==='js'?'nothing touches the box, or no glyph pairs':'nothing of the other page touches the box'));bar.append(key);
  return bar;
 }
 function renderReadout(ps,det,hit){
  readout.replaceChildren();const notes=[],bar=colorBar();if(bar)readout.append(bar);
  for(const p of ps)for(const s of p.sels){const n=completeness(s);if(n)notes.push(n);}
  if(state.view==='composite'){
   const sels=ps[0].sels.filter(s=>s.sel&&s.sel.available).map(s=>s.sel);
   if(sels.length>=2){const d=h('details','pairs'),sm=h('summary','','Pairwise Dice');d.append(sm);const t=h('table'),tr=h('tr');tr.append(h('th'));sels.forEach(s=>tr.append(h('th','num',s.folio)));t.append(tr);
    sels.forEach(a=>{const r=h('tr');r.append(h('th','',a.folio));sels.forEach(b=>r.append(h('td','num',a===b?'·':a.frame===b.frame?f3(M.measure(a,b).dice):'—')));t.append(r);});const w=h('div','table-wrap');w.append(t);d.append(w);readout.append(d);}
  }else if(pagesMode()){
   const a=ps[0].sels[0].sel,b=(ps[0].sels[1]||ps[1].sels[0]).sel;Object.assign(last,{a,b,det,scores:null,perLine:null});
   if(a&&b&&a.frame!==b.frame)notes.push(`${a.folio} and ${b.folio} are in different coordinate frames, so this pair is not scored`);
   else if(a&&b){const m=M.measure(a,b),js=a.available&&b.available?jsJoined(a,b):null;last.scores={...m,js_joined:js};last.perLine=M.perLine(a,b);
    const first=firstWords(a,b);if(first)readout.append(first);
    const grid=h('div','metrics');grid.append(metric(f3(m.dice),'Dice','shared area'),metric(f3(m.local_segment_similarity),'Direct EVA','overlapping boxes'),metric(f3(m.nearby_similarity),'Nearby EVA','best neighbour'),metric(f3(js),'JS','wording only'),metric(`${m.units_a} / ${m.units_b}`,'Boxes scored','A / B'));readout.append(grid);}
  }else{
   const rows=ps.filter(p=>p.sels.length===2).map(p=>({slot:p.slot,a:p.sels[0].sel,b:p.sels[1].sel,result:p.sels[0].sel&&p.sels[1].sel?M.measure(p.sels[0].sel,p.sels[1].sel):null}));
   if(!rows.length&&state.view==='side'){for(let i=0;i+1<ps.length;i+=2){const r={slot:ps[i].slot,a:ps[i].sels[0].sel,b:ps[i+1].sels[0].sel};r.result=r.a&&r.b?M.measure(r.a,r.b):null;rows.push(r);}}
   const J=M.joint(rows),grid=h('div','metrics');
   for(const [k,l] of [['dice','Dice'],['local_segment_similarity','Direct EVA'],['nearby_similarity','Nearby EVA']])grid.append(metric(f3(J.mean[k]),l+' · mean',J.complete?'equal-page mean':'withheld: a slot is incomplete'),metric(f3(J.minimum[k]),l+' · min','weaker page'));
   readout.append(grid);
   const line=h('p','note');line.textContent=rows.map(r=>`${SLOT_NAMES[r.slot]||r.slot}: ${r.a?r.a.folio:'—'} / ${r.b?r.b.folio:'—'}${r.result&&r.result.dice!=null?' · Dice '+f3(r.result.dice):''}`).join(' · ')+` · ${J.available_pairs} of ${J.required_pairs} slots available`;readout.append(line);
   Object.assign(last,{a:rows[0]&&rows[0].a,b:rows[0]&&rows[0].b,det:null,scores:J,perLine:null});
  }
  if(state.drift){
   const d=h('div','drift-read');d.append(h('span','','Drift'));
   const seen=new Set();for(const p of ps)for(const s of p.sels){if(!s.sel||!s.drift||seen.has(s.sel.folio))continue;seen.add(s.sel.folio);const sp=h('span');const sw=h('i','swatch'+(s.k===1?' dashed':''));sw.style.setProperty('--c',color(s.k));sp.append(sw,document.createTextNode(' '+sideName(s)+' '));const b=h('b','',s.drift.angle==null?'unavailable':deg(s.drift.angle));sp.append(b);if(s.drift.angle!=null)sp.append(document.createTextNode(' · '+s.drift.n+(s.drift.n===1?' line':' lines')));else if(s.drift.unavailable)sp.append(document.createTextNode(' · '+s.drift.unavailable));d.append(sp);}
   d.append(h('span','muted',state.coords==='recorded'?'recorded, before the warp correction':'flat, after the warp correction'));readout.append(d);
   last.drift=Object.fromEntries(ps.flatMap(p=>p.sels).filter(s=>s.sel&&s.drift).map(s=>[s.sel.folio,{angle:s.drift.angle,n:s.drift.n,coordinates:state.coords,unavailable:s.drift.unavailable}]));
  }else last.drift=null;
  if(state.view==='segments'&&pagesMode()){
   const r=h('div','seg-read');
   if(hit){const rec=hit.record;r.append(h('span','k','A'),h('code','',rec.text_a),h('span','','↔'),h('span','k','B'),h('code','',rec.text_b),h('span','',`${rec.edits} ${rec.edits===1?'edit':'edits'} · similarity ${f3(rec.similarity)} · ${hit.kind==='direct'?'overlapping boxes':hit.kind==='nearby'?'nearest box, no overlap':'connected group'}`));
    const x=h('button','','Clear');x.type='button';x.onclick=()=>{state.seg=null;groupHit=null;render();};r.append(x);}
   else if(state.seg)r.append(h('span','','No partner within reach for this word.'));
   else r.append(h('span','muted','Click a word for its partners on the other page; green patches are the shared areas.'));
   readout.append(r);
  }
  if(notes.length)readout.append(h('p','note',notes.join(' · ')));
 }
 async function renderExtra(ps,det){
  extra.replaceChildren();
  if(state.view==='matches'){
   await loadRankings();const rows=S.matchRows(rankings,state),i=S.matchIndex(rows,state),bif=!pagesMode();
   const note=h('p','note');
   note.textContent=rows.length?(bif?`${rows.length} best ${state.face}-face sheet pairs of ${rankings.bifolia[state.face].rows} (${rankings.bifolia[state.face].sheets} sheets) by ${META[state.metric]}, scored on the pages' first lines.`:`${rows.length} best matches for ${state.a} by ${META[state.metric]}, out of ${rankings.scan.eligible_pairs.toLocaleString('en-US')} scanned page pairs; scored on the first lines, flat coordinates.`):`${state.a} is not in the first-line scan (its opening line is not a located horizontal paragraph line).`;
   extra.append(note);if(!rows.length)return;
   const wrap=h('div','table-wrap'),t=h('table'),head=h('tr');
   for(const c of ['#',...(bif?['Sheet A','Sheet B']:['Page']),'Dice','JS','Positional EVA','Dice, x only'])head.append(h('th',/Dice|JS|EVA/.test(c)?'num':'',c));
   const thead=h('thead');thead.append(head);t.append(thead);const body=h('tbody');
   rows.forEach((r,k)=>{const tr=h('tr',k===i?'on':'');tr.append(h('td','num',String(k+1)));if(bif)tr.append(h('td','',r.a),h('td','',r.b));else tr.append(h('td','',r.b+' · '+sectionOf(r.b)));tr.append(h('td','num',f3(r.dice)),h('td','num',f3(r.js)),h('td','num',f3(r.spatial)),h('td','num',f3(r.x_dice)));tr.onclick=()=>gotoMatch(k);body.append(tr);});
   t.append(body);wrap.append(t);extra.append(wrap);
  }else if(state.view==='segments'&&det){
   const groups=det.connected.slice().sort((p,q)=>q.similarity-p.similarity);
   const note=h('p','note',`${groups.length} connected ${groups.length===1?'group':'groups'} of overlapping boxes (overlap of at least a fifth of the smaller box); ${det.nearby.length} boxes of A have a box of B within reach.`);extra.append(note);
   if(!groups.length)return;
   const wrap=h('div','table-wrap'),t=h('table'),head=h('tr');for(const c of ['A','B','Similarity','Edits','Lines A / B'])head.append(h('th',/Similarity|Edits/.test(c)?'num':'',c));const thead=h('thead');thead.append(head);t.append(thead);const body=h('tbody');
   groups.forEach(g=>{const tr=h('tr',groupHit===g?'on':'');tr.append(h('td','t',g.text_a),h('td','t',g.text_b),h('td','num',f3(g.similarity)),h('td','num',String(g.edits)),h('td','',g.lines_a.join(',')+' / '+g.lines_b.join(',')));tr.onclick=()=>{groupHit=groupHit===g?null:g;state.seg=null;render();};body.append(tr);});
   t.append(body);wrap.append(t);extra.append(wrap);
  }
 }
 // the page chips of the composite and wheel views: remove, add from a list, section shortcuts
 function pageChips(folios,{candidates,shortcuts=[]}){
  const chips=h('div','chips');
  folios.forEach((f,k)=>{const c=h('span','chip');const sw=h('i');sw.style.setProperty('--c',color(k));c.append(sw,document.createTextNode(f));if(folios.length>1){const x=h('button','x','×');x.type='button';x.setAttribute('aria-label','Remove '+f);x.onclick=()=>{state.pages=folios.filter(g=>g!==f);state.hide=state.hide.filter(k=>k!==f);render();};c.append(x);}chips.append(c);});
  const add=h('select');add.setAttribute('aria-label','Page to add');add.append(...candidates.filter(f=>!folios.includes(f)).map(f=>new Option(f+' · '+sectionOf(f),f)));
  const btn=h('button','add','Add');btn.type='button';btn.disabled=folios.length>=S.MAX_PAGES||!add.options.length;btn.onclick=()=>{if(add.value&&folios.length<S.MAX_PAGES){state.pages=[...folios,add.value];render();}};
  chips.append(add,btn);
  if(shortcuts.length){chips.append(h('i','sep'));for(const [label,pages] of shortcuts){const b=h('button','shortcut',label);b.type='button';b.dataset.tip=pages.length+' pages: '+pages.join(', ');b.onclick=()=>{state.pages=pages.slice(0,S.MAX_PAGES);state.hide=[];render();};chips.append(b);}}
  if(folios.length>=S.MAX_PAGES)chips.append(h('span','muted',S.MAX_PAGES+' pages at most'));
  return chips;
 }
 function renderTools(ps){
  tools.replaceChildren();tools.hidden=true;
  for(const [,,k] of [...state.lines].sort((x,y)=>x[2]-y[2])){
   const lp=ps[k];if(!lp||!lp.split||lp.split.bands)continue;
   const sp=lp.split,row=h('span','reading'),prev=h('button','','‹'),next=h('button','','›'),close=h('button','','Close');prev.type=next.type=close.type='button';
   prev.setAttribute('aria-label','Previous line pair');next.setAttribute('aria-label','Next line pair');
   prev.onclick=()=>stepSplit(-1,k);next.onclick=()=>stepSplit(1,k);close.onclick=()=>{state.lines=S.setLine(state.lines,k,null);render();};
   const lab=h('span');lab.append(document.createTextNode((lp.title?lp.title+': ':'')+'Reading '),h('b','','A line '+(sp.indices[0]+1)),document.createTextNode(' with '),h('b','','B line '+(sp.indices[1]+1)));
   const pg=h('span','pager');pg.append(prev,next);row.append(lab,pg,close);tools.append(row);tools.hidden=false;
  }
  if(state.view==='matches'&&rankings){
   const rows=S.matchRows(rankings,state),i=S.matchIndex(rows,state),prev=h('button','','‹ Previous match'),next=h('button','','Next match ›');prev.type=next.type='button';
   prev.disabled=next.disabled=!rows.length;prev.onclick=()=>gotoMatch(i<0?rows.length-1:i-1);next.onclick=()=>gotoMatch(i<0?0:i+1);
   const pos=h('span','',rows.length?(i>=0?`match ${i+1} of ${rows.length}`:'current B is not among the matches'):'');tools.append(prev,next,pos);tools.hidden=false;
  }
  if(state.view==='composite'){tools.append(pageChips(compositeFolios(),{candidates:list}));tools.hidden=false;}
  if(state.view==='wheels'&&wheels){
   const withWheels=S.wheelPages(wheels,compact.pages,list),shortcuts=['Zodiac','Astronomical','Cosmological'].map(sec=>[sec,S.wheelPages(wheels,compact.pages,list,sec)]).filter(x=>x[1].length);
   tools.append(pageChips(wheelFolios(),{candidates:withWheels,shortcuts}));
   for(const [key,label] of [['rings','Rings'],['labels','Labels']]){const l=h('label'),c=h('input');c.type='checkbox';c.checked=state[key];c.onchange=()=>{state[key]=c.checked;render();};l.append(c,document.createTextNode(' '+label));tools.append(l);}
   tools.hidden=false;
  }
 }
 function describe(ps){
  status.classList.remove('error-text');
  const [fa,fb]=currentFolios(),pa=compact.pages[fa],pb=compact.pages[fb];
  const block=k=>{const p=k==='a'?pa:pb;if(!p)return '';const key=k==='a'?res.blocka:res.blockb,b=p.blocks.find(x=>x[0]===key)||p.blocks[0];return blockLabel(p,b[0],b[1]).toLowerCase();};
  const parts=[];
  if(!pagesMode())parts.push(`${state.face==='both'?'both faces':state.face+' face'} · ${S.SLOTS[state.face].map(s=>SLOT_NAMES[s]).join(', ')}`);
  if(state.view==='composite')parts.push(`${compositeFolios().length} pages · ${block('a')}`);
  if(state.text==='page')parts.push(state.view==='composite'?'every line scored':'whole pages scored');
  else if(state.text!=='custom')parts.push(`opening blocks · top ${res.cutoff} ${res.cutoff==='1'?'line':'lines'} scored`);
  else{if(state.view!=='composite')parts.push(res.blocka===res.blockb?block('a'):`A: ${block('a')} · B: ${block('b')}`);parts.push(res.cutoff==='all'?'every line scored':`top ${res.cutoff} ${res.cutoff==='1'?'line':'lines'} scored`);}
  parts.push(state.coords+' coordinates',state.align==='starts'?'aligned on block starts':'page positions');if(state.scale==='body')parts.push('body-height scale');
  const hiddenNames=ps.flatMap(p=>p.sels).filter(s=>s.sel&&hidden(s)).map(sideName);
  if(hiddenNames.length)parts.push([...new Set(hiddenNames)].join(', ')+' hidden');
  if(state.boxes==='hidden')parts.push('boxes hidden');
  status.textContent=parts.join(' · ');
 }
 // ---- render
 async function render(){
  const my=++ticket;turnedShown=false;$('wdirLabel').hidden=true;figure.dataset.boxStyle=state.boxes;res=S.resolveText(state);fillBlocks();ctl.text.value=state.text;ctl.color.disabled=state.view==='composite'||state.view==='wheels';
  if(state.view==='wheels'){await renderWheels(my);return;}
  const ps=buildPanels();shown=ps;if(moved)placeLines();
  if(ps.length<2||!ps[state.max])state.max=null;
  const on=state.max==null?ps:[ps[state.max]],allSels=on.flatMap(p=>p.sels.map(s=>s.sel).filter(Boolean));   // the panels drawn; the readouts stay on all of them
  let F=S.frame(allSels,res.cutoff);
  const panelPx=Math.max(300,(figure.clientWidth||900)/Math.min(on.length,4)),scale=panelPx/F.w,open=[];let y0=F.y,y1=F.y+F.h;
  if(stacked()){
   const splits=on.map(p=>p.split=p.sels.length===2?S.expandLines(p.sels[0].sel,p.sels[1].sel,res.cutoff,scale,p.sels.map(hidden)):null).filter(Boolean);
   if(splits.length){y0=Math.min(...splits.map(s=>s.ymin));y1=Math.max(...splits.map(s=>s.ymax));}           // the frame is the stack of bands
  }else{if(stackable())for(const line of state.lines){
   const k=line[2],p=ps[k];if(!p||!readable(pairAt(k)))continue;
   if(on.includes(p)){const split=M.splitLines(p.sels[0].sel,p.sels[1].sel,line.slice(0,2),scale,res.cutoff);if(!split)continue;y0=Math.min(y0,split.ymin);y1=Math.max(y1,split.ymax);p.split=split;}
   open.push(line);
  }
  state.lines=open;}F={x:F.x,y:y0,w:F.w,h:y1-y0};
  margin=panelPx<NARROW_PANEL?NARROW_MARGIN:WIDE_MARGIN;
  if(ps.some(p=>p.sels.length<=2))F=S.withGutter(F,allSels,res.cutoff,panelPx,margin.px);
  const key=JSON.stringify([F,on.length,state.view]);if(key!==frameKey){view=pendingZoom?S.clampView(pendingZoom,F):null;pendingZoom=null;frameKey=key;}
  full=F;
  const two=ps.length===1&&ps[0].sels.length===2&&ps[0].sels.every(s=>s.sel);
  const det=state.view==='segments'&&two?M.details(ps[0].sels[0].sel,ps[0].sels[1].sel):null;
  const hit=det?(groupHit&&det.connected.includes(groupHit)?{kind:'group',a:groupHit.a,b:groupHit.b,record:groupHit}:state.seg?S.partners(det,state.seg.side,state.seg.id):null):null;
  if(det&&groupHit&&!det.connected.includes(groupHit))groupHit=null;
  assignColors(ps);
  figure.style.setProperty('--panels',String(Math.min(on.length,4)));figure.classList.toggle('maximized',state.max!=null);figure.classList.toggle('expanded',stacked());figure.style.setProperty('--toolbar',toolbarHeight()+'px');
  figure.replaceChildren(...on.map(p=>drawPanel(p,F,{det,hit,k:ps.indexOf(p),many:ps.length>1})));
  panels=[...figure.querySelectorAll('svg')];for(const svg of panels)SG.attachTips(svg);SG.attachTips(figure);
  applyView();renderReadout(ps,det,hit);renderTools(ps);SG.attachTips(tools);describe(ps);save();
  await renderExtra(ps,det);
  if(my!==ticket)return;
 }
 function wheelFolios(){
  if(state.pages.length)return state.pages.filter(f=>compact.pages[f]);
  const base=pagesMode()?state.a:(slotFolios(state.a)[0]||state.a);return compact.pages[base]?[base]:[];
 }
 async function renderWheels(my){
  await loadWheels();if(my!==ticket)return;
  const folios=wheelFolios(),entries=folios.map((f,k)=>({folio:f,k,tag:f,rec:wheels.pages[f],lay:S.wheelLayout(f,wheels.pages[f],M.pageUnits(compact.pages[f],words))}));
  readout.replaceChildren();extra.replaceChildren();renderTools([]);
  const pagesWith=S.wheelPages(wheels,compact.pages,list);
  const chips=h('p','note linkchips');chips.append(document.createTextNode('Pages with fitted wheels: '));
  for(const f of pagesWith){const a=h('a','',f);a.href='#';a.onclick=e=>{e.preventDefault();if(!pagesMode()){state.scope='pages';syncControls();}state.a=f;state.pages=[];state.hide=[];ctl.a.value=f;render();};chips.append(a);}
  extra.append(chips);
  const drawn=entries.filter(e=>e.lay.wheels.length);
  if(!drawn.length){figure.replaceChildren(h('div','empty',`${folios.join(', ')||'this page'} ${folios.length>1?'have':'has'} no circular text with a fitted wheel.`));status.textContent=`${folios.join(', ')} · no wheel`;full=null;zoomLevel.textContent='';save();return;}
  const R=Math.max(...drawn.map(e=>e.lay.radius))*1.05+15,F={x:-R,y:-R,w:2*R,h:2*R};
  const key=JSON.stringify([F,'wheels',folios]);if(key!==frameKey){view=pendingZoom?S.clampView(pendingZoom,F):null;pendingZoom=null;frameKey=key;}full=F;
  const wrap=h('div','panel'),head=h('h3'),svg=el('svg',{viewBox:`${F.x} ${F.y} ${F.w} ${F.h}`,role:'img','aria-label':'Centred wheels of '+folios.join(', ')});
  for(const e of entries){const n=e.lay.wheels.length;head.append(tagButton(e,e.folio+(n?(n>1?' · '+n+' wheels':''):' · no wheel'),e.folio,{none:!n}));}
  svg.append(el('line',{class:'cross',x1:-R,x2:R,y1:0,y2:0}),el('line',{class:'cross',x1:0,x2:0,y1:-R,y2:R}));
  if(drawn.length>2)svg.classList.add('many');
  for(const e of drawn){
   if(S.isHidden(state,e.folio))continue;
   const g=el('g',{class:'page-layer',style:'--c:'+color(e.k)});
   for(const w of e.lay.wheels){
    if(state.rings)for(const r of w.rings)g.append(el('circle',{class:'ring',cx:r.cx,cy:r.cy,r:r.r,'data-tip':`<b>${esc(e.folio)}</b> · ${esc(w.id.replace(e.folio+'/',''))} · locus ${esc(r.locus)} · radius ${r.r.toFixed(0)} px<div class="tipsub">${r.n} boxes · arc ${r.arc.toFixed(0)}° · residual ${r.residual.toFixed(1)} px · ring centre ${Math.hypot(r.cx,r.cy).toFixed(1)} px from the wheel centre</div>`}));
    const boxes=state.labels?w.boxes.concat(w.labels.map(b=>({...b,label:true}))):w.boxes,faces=state.words?wordFaces(boxes):new Map();
    for(const u of boxes){g.append(el('rect',{class:'u'+(u.label?' label-box':''),x:u.rect[0],y:u.rect[1],width:u.rect[2]-u.rect[0],height:u.rect[3]-u.rect[1],'data-tip':`<b>${esc(e.folio)}</b> · line ${u.line+1} · ${esc(u.text)}${u.label?'<div class="tipsub">nearby label, not on a ring</div>':''}`}));
     if(state.words){const f=faces.get(u.id);if(f)g.append(wordLabel(f,'w',u.text));else{const ww=u.rect[2]-u.rect[0],hh=u.rect[3]-u.rect[1];g.append(el('text',{class:'w',x:(u.rect[0]+u.rect[2])/2,y:u.rect[1]+hh*.72,'text-anchor':'middle','font-size':Math.max(3,Math.min(hh*.62,1.6*ww/Math.max(1,u.text.length))).toFixed(2)},u.text));}}}
   }
   svg.append(g);
  }
  wrap.append(head,svg);figure.style.setProperty('--panels','1');figure.classList.remove('maximized','expanded');figure.replaceChildren(wrap);panels=[svg];SG.attachTips(svg);SG.attachTips(figure);SG.attachTips(tools);applyView();
  const nw=drawn.reduce((s,e)=>s+e.lay.wheels.length,0),nr=drawn.reduce((s,e)=>s+e.lay.wheels.reduce((t,w)=>t+w.rings.length,0),0),nb=drawn.reduce((s,e)=>s+e.lay.wheels.reduce((t,w)=>t+w.boxes.length,0),0);
  const spread=Math.max(...drawn.flatMap(e=>e.lay.wheels.map(w=>w.spread)));
  readout.append(h('p','note',`${drawn.length} ${drawn.length===1?'page':'pages'} · ${nw} ${nw===1?'wheel':'wheels'} · ${nr} rings · ${nb} boxes on rings${state.labels?' · '+drawn.reduce((s,e)=>s+e.lay.wheels.reduce((t,w)=>t+w.labels.length,0),0)+' nearby labels':''} · largest centre spread ${spread.toFixed(1)} px. Centring is a display transform: every wheel is moved so that its centre lies at the common origin; sizes, angles and spacing are unchanged, and the dashed circles are the fitted ring radii (recorded coordinates).`));
  const rejected=drawn.flatMap(e=>(e.rec.rejected||[]).map(r=>e.folio+' locus '+r.locus+' ('+r.reason.toLowerCase()+')'));
  if(rejected.length)readout.append(h('p','note','Not fitted: '+rejected.join('; ')+'.'));
  const hiddenNames=entries.filter(e=>e.lay.wheels.length&&S.isHidden(state,e.folio)).map(e=>e.folio);
  status.textContent=`${drawn.map(e=>e.folio).join(', ')} · circular text centred`+(hiddenNames.length?' · '+hiddenNames.join(', ')+' hidden':'')+(state.boxes==='hidden'?' · boxes hidden':'');save();
 }
 // ---- interactions
 function gotoMatch(i){const rows=S.matchRows(rankings,state);if(!rows.length)return;keepLines(pagesMode()?['b']:['a','b']);const r=rows[((i%rows.length)+rows.length)%rows.length];if(pagesMode())state.b=r.b;else{state.a=r.a;state.b=r.b;}clearTransient();ctl.a.value=state.a;ctl.b.value=state.b;render();}
 function setSplit(side,line,k=0){
  const pair=pairAt(k);if(!readable(pair))return;
  const rowsA=S.lineRows(pair.a,res.cutoff),rowsB=S.lineRows(pair.b,res.cutoff);let la,lb;
  if(side===0){la=line;const row=rowsA.find(r=>r.index===line),n=row?S.nearestLine(rowsB,row.baseline):null;lb=n?n.index:null;}
  else{lb=line;const row=rowsB.find(r=>r.index===line),n=row?S.nearestLine(rowsA,row.baseline):null;la=n?n.index:null;}
  if(la==null||lb==null)return;
  const open=S.lineAt(state.lines,pair.panel),same=open&&open[0]===la&&open[1]===lb;
  if(state.view==='side'){state.view='overlay';if(state.max!=null)state.max=pair.panel;syncControls();}               // the comparison needs the two pages in one frame
  state.lines=S.setLine(state.lines,pair.panel,same?null:[la,lb]);render();
 }
 // the line the keyboard acts on: the maximized panel's, or the latest opened
 function activeLine(){if(stacked())return null;if(state.max!=null)return S.lineAt(state.lines,state.max)?state.max:null;const l=state.lines[state.lines.length-1];return l?l[2]:null;}
 function stepSplit(delta,k){const open=S.lineAt(state.lines,k),pair=pairAt(k);if(!open||!readable(pair))return;const rows=S.lineRows(pair.a,res.cutoff),i=rows.findIndex(r=>r.index===open[0]),j=Math.max(0,Math.min(rows.length-1,i+delta));if(j===i||i<0)return;const row=rows[j],n=S.nearestLine(S.lineRows(pair.b,res.cutoff),row.baseline);if(!n)return;state.lines=S.setLine(state.lines,k,[row.index,n.index]);render();}
 // a page move keeps each panel's open line: it stays on the page that stays, or on A when both move, and the other page takes its partner
 function keepLines(sides){
  const side=sides.length===1&&sides[0]==='a'?1:0;
  for(const [k,c] of kept)if(c.pair&&!S.lineAt(state.lines,k))kept.delete(k);   // closed since the last move
  for(const l of state.lines){const c=kept.get(l[2]),pair=l.join();if(!(c&&c.pair===pair&&c.side===side))kept.set(l[2],{side,line:l[side],pair});}
  moved=kept.size>0&&(state.view==='overlay'||state.view==='matches');
 }
 function placeLines(){
  state.lines=[];moved=false;
  for(const [k,c] of kept){
   const pair=pairAt(k),at=readable(pair)?S.carriedLines(S.lineRows(pair.a,res.cutoff),S.lineRows(pair.b,res.cutoff),c.side,c.line):null;
   c.pair=at?[...at,k].join():null;if(at)state.lines=S.setLine(state.lines,k,at);
  }
 }
 figure.addEventListener('click',e=>{
  const t=e.target instanceof Element?e.target:null;if(!t)return;
  const num=t.closest('.lnum'),box=t.closest('.u');
  if(state.view==='segments'&&pagesMode()&&box&&box.dataset.id!=null){const side=box.dataset.side==='0'?'a':'b',id=Number(box.dataset.id);state.seg=state.seg&&state.seg.side===side&&state.seg.id===id?null:{side,id};groupHit=null;render();return;}
  const hit=num||box;if(!hit||hit.dataset.line==null||!lineViews.includes(state.view)||stacked())return;
  const k=Number(hit.closest('svg').dataset.panel),pair=pairAt(k);
  if(readable(pair))setSplit(Number(hit.dataset.side),Number(hit.dataset.line),k);
  else if(pair){const none=[pair.a,pair.b].find(s=>!s||!s.all.length);status.textContent=`${none?none.folio:'This slot'} has no located boxes in this selection, so there is no line to compare.`;}
 });
 const toUser=(svg,e)=>{const m=svg.getScreenCTM();if(!m)return {x:0,y:0};const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse());return {x:p.x,y:p.y};};
 figure.addEventListener('wheel',e=>{const svg=e.target instanceof Element?e.target.closest('svg'):null;if(!svg||!full)return;e.preventDefault();view=S.zoomAt(view||full,full,e.deltaY<0?1.25:0.8,toUser(svg,e));applyView();},{passive:false});
 let drag=null;
 figure.addEventListener('pointerdown',e=>{const svg=e.target instanceof Element?e.target.closest('svg'):null;if(!svg||e.button!==0||!full)return;const m=svg.getScreenCTM();drag={svg,x:e.clientX,y:e.clientY,view:view||full,s:m?m.a:1,moved:false,id:e.pointerId};});
 addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!drag.moved&&Math.hypot(dx,dy)<4)return;if(!drag.moved){drag.moved=true;drag.svg.classList.add('dragging');}view=S.pan(drag.view,full,dx,dy,drag.s);applyView();});
 const endDrag=e=>{if(!drag||e.pointerId!==drag.id)return;const moved=drag.moved;drag.svg.classList.remove('dragging');drag=null;if(moved){const stop=ev=>{ev.stopPropagation();ev.preventDefault();removeEventListener('click',stop,true);};addEventListener('click',stop,true);setTimeout(()=>removeEventListener('click',stop,true),0);}};
 addEventListener('pointerup',endDrag);addEventListener('pointercancel',endDrag);
 const centre=v=>({x:v.x+v.w/2,y:v.y+v.h/2});
 $('zoomFit').onclick=()=>{view=null;applyView();};
 $('zoomIn').onclick=()=>{if(full){const v=view||full;view=S.zoomAt(v,full,1.25,centre(v));applyView();}};
 $('zoomOut').onclick=()=>{if(full){const v=view||full;view=S.zoomAt(v,full,0.8,centre(v));applyView();}};
 addEventListener('resize',()=>applyView());
 addEventListener('keydown',e=>{if(e.target instanceof Element&&e.target.matches('input,select,textarea'))return;
  const k=activeLine();
  if(e.key==='Escape'){if(k!=null){state.lines=S.setLine(state.lines,k,null);render();}else if(state.max!=null)setMax(null);else if(state.seg||groupHit){state.seg=null;groupHit=null;render();}}
  else if(k!=null&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();stepSplit(e.key==='ArrowRight'?1:-1,k);}});
 ctl.order.onchange=()=>{state.order=ctl.order.value;rebuildLists();fillPickers();render();};
 ctl.a.onchange=()=>{state.a=ctl.a.value;clearTransient();render();};ctl.b.onchange=()=>{state.b=ctl.b.value;clearTransient();render();};
 $('prevA').onclick=()=>advance(['a'],-1);$('nextA').onclick=()=>advance(['a'],1);
 $('prevB').onclick=()=>advance(['b'],-1);$('nextB').onclick=()=>advance(['b'],1);
 // one arrow press on A, B or both, in the chosen step: a page, a sheet or a paragraph
 function advance(sides,d){
  keepLines(sides);
  if(!pagesMode()||state.step==='page'){if(sides.length===2)[state.a,state.b]=S.stepPair(currentList(),state.a,state.b,d);else state[sides[0]]=S.step(currentList(),state[sides[0]],d);}
  else if(state.step==='bifolio')for(const k of sides)state[k]=S.stepSheet(sheets,compact.pages,state[k],d);
  else{
   const r=S.resolveText(state),blocks={blocka:r.blocka,blockb:r.blockb};
   for(const k of sides){const key=k==='a'?'blocka':'blockb',to=S.stepParagraph(compact.pages,list,state[k],blocks[key],d);state[k]=to.folio;blocks[key]=to.block;}
   state=S.customize(state,blocks);
  }
  ctl.a.value=state.a;ctl.b.value=state.b;clearTransient();render();
 }
 $('prevPair').onclick=()=>advance(['a','b'],-1);$('nextPair').onclick=()=>advance(['a','b'],1);
 $('swap').onclick=()=>{[state.a,state.b]=[state.b,state.a];[state.blocka,state.blockb]=[state.blockb,state.blocka];ctl.a.value=state.a;ctl.b.value=state.b;state.lines=state.lines.map(([x,y,k])=>[y,x,k]);if(state.view==='side'&&state.max!=null)state.max^=1;if(state.seg)state.seg={side:state.seg.side==='a'?'b':'a',id:state.seg.id};state.hide=state.hide.map(k=>k==='a'?'b':k==='b'?'a':k);groupHit=null;render();};
 $('views').addEventListener('click',async e=>{const b=e.target instanceof Element?e.target.closest('button[data-view]'):null;if(!b||b.dataset.view===state.view)return;const keepSplit=['overlay','matches'].includes(b.dataset.view)&&['overlay','matches'].includes(state.view);state.view=b.dataset.view;if(!keepSplit){state.lines=[];state.max=null;}state.seg=null;groupHit=null;syncControls();if(state.view==='matches')await loadRankings();render();});
 ctl.text.onchange=()=>{state=S.setText(state,ctl.text.value);state.lines=[];render();};
 ctl.blockA.onchange=()=>{state=S.customize(state,{blocka:ctl.blockA.value});state.lines=[];render();};
 ctl.blockB.onchange=()=>{state=S.customize(state,{blockb:ctl.blockB.value});state.lines=[];render();};
 ctl.cutoff.onchange=()=>{state=S.customize(state,{cutoff:ctl.cutoff.value});render();};
 ctl.words.onchange=()=>{state.words=ctl.words.checked;render();};ctl.expand.onchange=()=>{state.expand=ctl.expand.checked;render();};ctl.drift.onchange=()=>{state.drift=ctl.drift.checked;render();};
 for(const k of ['align','coords','scale','metric','color','wdir','boxes'])ctl[k].onchange=()=>{state[k]=ctl[k].value;render();};
 ctl.step.onchange=()=>{const was=state.step;state.step=ctl.step.value;if(was==='paragraph'&&state.step!=='paragraph'){state=S.setText(state,'page');state.lines=[];}syncControls();render();};   // leaving paragraph steps returns to whole pages
 ctl.gain.onchange=()=>{state.gain=Number(ctl.gain.value);render();};
 ctl.face.onchange=()=>{state.face=ctl.face.value;clearPanels();render();};
 ctl.scope.onchange=()=>{
  const to=ctl.scope.value;
  if(to==='bifolia'){const na=compact.pages[state.a]&&compact.pages[state.a].node,nb=compact.pages[state.b]&&compact.pages[state.b].node;state.scope=to;state.a=na||sheets[0].id;state.b=nb&&nb!==state.a?nb:S.step(sheets.map(s=>s.id),state.a,1);}
  else{const fa=slotFolios(state.a)[0],fb=slotFolios(state.b)[0];state.scope=to;state.a=fa||list[0];state.b=fb||list[1];}
  clearPanels();syncControls();render();
 };
 $('export').onclick=()=>{
  const det=last.det||(last.a&&last.b&&pagesMode()?M.details(last.a,last.b):null),rec=S.exportRecord(state,compact,last.a,last.b,last.scores,det,last.perLine,last.drift);
  const blob=new Blob([JSON.stringify(rec,null,1)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=`compare_${state.a}_${state.b}.json`.replace(/[^\w.-]+/g,'_');document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
 };
 addEventListener('hashchange',async()=>{const s=S.parse(SG.hash());if(JSON.stringify(S.serialize(s))===JSON.stringify(S.serialize(state)))return;state=s;pendingZoom=s.zoom;frameKey='';groupHit=null;rebuildLists();syncControls();if(state.view==='matches')await loadRankings();render();});
 // ---- start
 rebuildLists();syncControls();
 if(state.view==='matches')await loadRankings();
 render();
})();
