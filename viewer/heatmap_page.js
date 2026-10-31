/* Display-only page layers. Never alter the geometry used by source-pool scores. The Coordinates control moves the drawn
   boxes between the recorded and the flat state; the measures stay flat either way, and a page image forces recorded. */
"use strict";
const SG_HEATMAP_PAGE=(()=>{
 const NS='http://www.w3.org/2000/svg';
 function create({atlas,onChange}){
  const controls=document.getElementById('pageDisplayControls'),imageToggle=document.getElementById('pageImage'),
   labelToggle=document.getElementById('pageWords'),boxStyle=document.getElementById('pageBoxes'),status=document.getElementById('pageImageStatus'),
   overlayList=document.getElementById('pageOverlays'),overlayChoice=document.getElementById('overlayChoice'),overlayCount=document.getElementById('overlayCount'),coordSel=document.getElementById('coordinates'),wdirSel=document.getElementById('wdir'),wdirLabel=document.getElementById('wdirLabel'),
   locusSel=document.getElementById('pageLocus'),locusChoice=document.getElementById('locusChoice'),zoomReset=document.getElementById('zoomReset'),zoomLevel=document.getElementById('zoomLevel');
  let data=null,layout=null,expanded=null,reviewPromise=null,reviewUrl='data/spatial_review.json.gz',ticket=0,overlayNote='';
  // zoom state of the expanded figure: `view` in the svg's base frame (null = the whole page); pending values from the address
  let view=null,pendingView=null,pendingLocus=null,framedLocus='';
  let chosenOverlays=new Set();
  const states=new WeakMap(),recordedY=new WeakMap(),overlayIndex=new WeakMap();
  // ---- coordinates. A rectangle is rendered at its recorded y with its way to the flat state in data-dy.
  function coordState(figure){
   return VMS_ATLAS.coordinateState({choice:coordSel?.value,canFlat:!!data?.geometry_recorded,image:!!figure&&figure===expanded&&imageToggle.checked,pageWarp:figure?data?.warp_pages?.[figure.dataset.page]:''});
  }
  function flatY(y,dy){return (y-dy).toFixed(2);}
  // every rectangle outside the expanded page, which `raw` and the page image place
  function placeRows(){
   const flat=coordState(null).drawn==='flat';
   for(const box of atlas.querySelectorAll('rect[data-dy]')){
    if(expanded&&expanded.contains(box))continue;
    const y=recordedY.get(box);if(y!==undefined)box.setAttribute('y',flat?flatY(y,Number(box.dataset.dy)):y);
   }
  }
  function state(figure){
   if(!states.has(figure)){
    const svg=figure.querySelector('svg');
    states.set(figure,{svg,viewBox:svg.getAttribute('viewBox'),native:null,
     boxes:[...svg.querySelectorAll('rect')].map(box=>({box,dy:Number(box.dataset.dy||0),raw:['x','y','width','height'].map(a=>a==='y'&&recordedY.has(box)?recordedY.get(box):Number(box.getAttribute(a)))}))});
   }
   return states.get(figure);
  }
  // the figure's coordinate view; `leaving` = it returns to the rows, where no image is shown
  function raw(figure,leaving=false){
   const s=state(figure),flat=coordState(leaving?null:figure).drawn==='flat';s.svg.setAttribute('viewBox',s.viewBox);s.svg.dataset.baseView=s.viewBox;
   for(const {box,raw,dy} of s.boxes){['x','y','width','height'].forEach((a,k)=>box.setAttribute(a,k===1&&flat&&dy?flatY(raw[1],dy):raw[k]));box.classList.remove('no-native-box');}
   s.svg.querySelector('.manuscript-image')?.remove();s.svg.querySelector('.page-overlays')?.remove();s.native=null;
   figure.classList.remove('image-backed');
  }
  // ---- zoom and pan (js/zoom_math.js): the viewBox of the expanded svg changes, so boxes, image and overlays move together
  function fullView(){const s=state(expanded);return SG_ZOOM.parse((s.svg.dataset.baseView||s.viewBox).trim().split(/\s+/).join(','));}
  function setView(v,{locus=''}={}){
   if(!expanded)return;
   const s=state(expanded),full=fullView();
   view=v&&!SG_ZOOM.isFull(v,full)?v:null;framedLocus=locus;
   s.svg.setAttribute('viewBox',view?`${view.x} ${view.y} ${view.w} ${view.h}`:s.svg.dataset.baseView||s.viewBox);
   s.svg.classList.toggle('zoomed',!!view);
   if(zoomLevel)zoomLevel.textContent=view?SG_ZOOM.scale(view,full).toFixed(1)+'×':'';
   if(zoomReset)zoomReset.hidden=!view;
   if(locusSel)locusSel.value=locus&&[...locusSel.options].some(o=>o.value===locus)?locus:'';
   onChange();
  }
  function currentView(){return view||fullView();}
  function pagePoint(e){const s=state(expanded),r=s.svg.getBoundingClientRect();return SG_ZOOM.toPage(currentView(),e.clientX-r.left,e.clientY-r.top,r.width,r.height);}
  function onWheel(e){
   if(!expanded||!expanded.contains(e.target))return;
   e.preventDefault();
   const factor=e.deltaY<0?1.25:0.8;
   setView(SG_ZOOM.zoomAt(currentView(),fullView(),factor,pagePoint(e)));
  }
  let drag=null;
  function onPointerDown(e){
   if(!expanded||e.button!==0||!expanded.contains(e.target))return;
   const s=state(expanded);
   drag={x:e.clientX,y:e.clientY,moved:false,view:currentView(),rect:s.svg.getBoundingClientRect(),id:e.pointerId};
  }
  function onPointerMove(e){
   if(!drag||e.pointerId!==drag.id)return;
   const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
   if(!drag.moved&&Math.hypot(dx,dy)<4)return;
   if(!drag.moved){drag.moved=true;state(expanded).svg.classList.add('dragging');}
   setView(SG_ZOOM.pan(drag.view,fullView(),dx,dy,drag.rect.width,drag.rect.height),{locus:framedLocus});
  }
  function onPointerUp(e){
   if(!drag||e.pointerId!==drag.id)return;
   const moved=drag.moved;drag=null;
   if(expanded)state(expanded).svg.classList.remove('dragging');
   if(moved){const stop=ev=>{ev.stopPropagation();ev.preventDefault();window.removeEventListener('click',stop,true);};window.addEventListener('click',stop,true);setTimeout(()=>window.removeEventListener('click',stop,true),0);}
  }
  // the loci of the expanded page: locus, type, orientation and word count, for the chooser
  function pageLoci(page){
   if(!data)return [];
   return data.lines.map((L,k)=>({L,k})).filter(({L})=>L.page===page).map(({L,k})=>{
    const o=L.orientation||{},located=[...Array(L.end-L.start).keys()].filter(j=>data.geometry[L.start+j]).length;
    return {index:k,locus:String(L.locus),type:L.locus_type||'',kind:o.kind||'',n:L.end-L.start,located,angle:o.angle_deg};
   });
  }
  function fillLoci(){
   if(!locusSel)return;
   const loci=expanded?pageLoci(expanded.dataset.page):[];
   locusSel.replaceChildren(new Option('Whole page',''),...loci.map(l=>new Option(`${l.locus} · ${l.type||'?'} ${l.kind}${l.angle!=null&&l.kind!=='circular'?' '+(l.angle>0?'+':'')+l.angle+'°':''} · ${l.located}/${l.n} words`,l.locus)));
   if(locusChoice)locusChoice.hidden=!loci.length;
   locusSel.value=framedLocus&&loci.some(l=>l.locus===framedLocus)?framedLocus:'';
  }
  function frameLocus(locus){
   if(!expanded||!data)return;
   const page=expanded.dataset.page,L=data.lines.find(l=>l.page===page&&String(l.locus)===String(locus));
   if(!L){setView(null);return;}
   const s=state(expanded),boxes=[];
   for(const {box} of s.boxes){
    if(box.classList.contains('no-native-box')||box.classList.contains('invalid-geometry'))continue;
    const idx=box.dataset.tokenIndices.split(',').map(Number);
    if(!idx.some(i=>i>=L.start&&i<L.end))continue;
    const [x,y,w,h]=['x','y','width','height'].map(a=>Number(box.getAttribute(a)));boxes.push([x,y,x+w,y+h]);
   }
   setView(SG_ZOOM.frame(boxes,fullView()),{locus:String(locus)});
  }
  function applyPending(){
   if(!expanded)return;
   if(pendingLocus){const l=pendingLocus;pendingLocus=null;frameLocus(l);return;}
   if(pendingView){const v=pendingView;pendingView=null;setView(SG_ZOOM.clampTo(v,fullView()));return;}
   if(framedLocus)frameLocus(framedLocus);else if(view)setView(SG_ZOOM.clampTo(view,fullView()));
  }
  // the overlays a bundle brings (lines and markers in the page's coordinate frame, per page), drawn on the expanded
  // page and mapped onto the image with the same registration as the boxes
  function pageItems(overlay,page){
   if(!overlayIndex.has(overlay)){const by=new Map();for(const item of overlay.items||[]){if(!by.has(item.page))by.set(item.page,[]);by.get(item.page).push(item);}overlayIndex.set(overlay,by);}
   return overlayIndex.get(overlay).get(page)||[];
  }
  function overlays(){
   if(!expanded||!data)return;
   const s=state(expanded);s.svg.querySelector('.page-overlays')?.remove();overlayNote='';
   if(!data.overlays||!chosenOverlays.size)return;
   const keys=Object.keys(data.overlays).filter(k=>chosenOverlays.has(k)),page=expanded.dataset.page,drawn=coordState(expanded).drawn,shifts=VMS_ATLAS.tokenShifts(data);
   const reg=s.native?(s.native.identity?{scale:1,tx:0,ty:0,maxCenterError:0}:s.native.registration):null;
   if(s.native&&(!reg||reg.maxCenterError>=2)){overlayNote='Overlays are not drawn on this image: its box registration is off by '+(reg?reg.maxCenterError.toFixed(1):'?')+' px (the limit is 2). Turn Page image off to see them.';noteStatus();return;}
   const map=([x,y])=>reg?[reg.scale*x+reg.tx,reg.scale*y+reg.ty]:[x,y];
   const layer=document.createElementNS(NS,'g');layer.setAttribute('class','page-overlays');layer.setAttribute('aria-hidden','true');
   let count=0;
   for(const k of keys)for(const item of [...VMS_ATLAS.fieldMarkers(data.overlays[k],data,page,drawn),...pageItems(data.overlays[k],page)]){
    const points=VMS_ATLAS.overlayPoints(item,drawn,shifts);if(!points||!points.length)continue;
    const pts=points.map(map),cls='ov ov-'+(item.style||'line')+' ov-key-'+k;
    let el;
    if(item.kind==='marker'){el=document.createElementNS(NS,'circle');el.setAttribute('cx',pts[0][0]);el.setAttribute('cy',pts[0][1]);el.setAttribute('r',String((item.r||3)*(reg?reg.scale:1)));}
    else{el=document.createElementNS(NS,'polyline');el.setAttribute('points',pts.map(p=>p[0].toFixed(2)+','+p[1].toFixed(2)).join(' '));}
    el.setAttribute('class',cls);
    const title=VMS_ATLAS.overlayTitle(item,data);
    if(title){const t=document.createElementNS(NS,'title');t.textContent=title;el.append(t);}
    layer.append(el);count++;
   }
   if(count)s.svg.append(layer);
  }
  function labels(){
   if(!expanded||!data)return;
   const s=state(expanded);s.svg.querySelector('.page-word-labels')?.remove();
   expanded.classList.toggle('words-visible',labelToggle.checked);
   if(wdirLabel)wdirLabel.hidden=true;
   if(!labelToggle.checked)return;
   const layer=document.createElementNS(NS,'g');layer.setAttribute('class','page-word-labels');layer.setAttribute('aria-hidden','true');
   const seen=new Set(),turned=[];
   for(const {box} of s.boxes){
    if(!box.dataset.tokenIndices||box.classList.contains('invalid-geometry')||box.classList.contains('no-native-box'))continue;
    const indices=box.dataset.tokenIndices.split(',').map(Number),key=indices.join(',');
    if(seen.has(key))continue;seen.add(key);
    const related=s.boxes.map(entry=>entry.box).filter(b=>b.dataset.tokenIndices===box.dataset.tokenIndices&&!b.classList.contains('no-native-box'));
    const parts=related.map(b=>['x','y','width','height'].map(a=>Number(b.getAttribute(a))));
    // A multi-piece label spans its whole adjacent group, never just piece one.
    const x=Math.min(...parts.map(b=>b[0])),y=Math.min(...parts.map(b=>b[1])),
     w=Math.max(...parts.map(b=>b[0]+b[2]))-x,h=Math.max(...parts.map(b=>b[1]+b[3]))-y;
    const L=data.lines[data.lineOf[indices[0]]],angle=L?VMS_WORDS.angleOf(L.orientation,indices[0]-L.start):0;
    if(angle!==0){turned.push({rect:[x,y,x+w,y+h],text:SG_REVIEW.boxLabel(data,indices),angle,member:box.classList.contains('window-member')});continue;}
    const text=document.createElementNS(NS,'text');
    text.textContent=SG_REVIEW.boxLabel(data,indices);text.setAttribute('x',x+1);text.setAttribute('y',y+h*.72);
    text.setAttribute('font-size',Math.min(s.native?12:18,h*.65));text.setAttribute('textLength',Math.max(2,w-2));text.setAttribute('lengthAdjust','spacingAndGlyphs');
    text.classList.toggle('label-member',box.classList.contains('window-member'));layer.append(text);
   }
   // words that do not run left to right: sized along their own direction, one size for the page; the boxes do not move
   if(turned.length){
    VMS_WORDS.layout(turned,wdirSel?.value||'ring').forEach((face,k)=>{
     const text=document.createElementNS(NS,'text');text.textContent=turned[k].text;
     text.setAttribute('x',face.x);text.setAttribute('y',face.y);text.setAttribute('text-anchor','middle');text.setAttribute('dominant-baseline','central');text.setAttribute('font-size',face.size);
     if(face.angle)text.setAttribute('transform',`rotate(${face.angle} ${face.x} ${face.y})`);
     text.classList.toggle('label-member',turned[k].member);layer.append(text);
    });
    if(wdirLabel)wdirLabel.hidden=false;
   }
   s.svg.append(layer);
  }
  // the status line: what the Coordinates choice does here, then the page's own message, then the overlay note
  function setStatus(text){status.textContent=[coordState(expanded).note,text,overlayNote].filter(Boolean).join(' · ');}
  function noteStatus(){if(overlayNote&&!status.textContent.includes(overlayNote))status.textContent+=' · '+overlayNote;}
  // fRos and other detected pages: how many of the page's words have a detected box
  function detectedNote(page){
   if(!data)return '';
   let total=0,placed=0;
   for(const L of data.lines){if(L.page!==page)continue;for(let i=L.start;i<L.end;i++){total++;if(data.geometry[i])placed++;}}
   return ` Detection coverage: ${placed} of ${total} words placed.`;
  }
  async function apply(){
   const current=++ticket;controls.hidden=!expanded;status.hidden=!expanded;
   if(!expanded){if(zoomReset)zoomReset.hidden=true;if(zoomLevel)zoomLevel.textContent='';if(locusChoice)locusChoice.hidden=true;return;}
   const figure=expanded,s=state(figure);
   figure.dataset.boxStyle=boxStyle.value;raw(figure);labels();overlays();fillLoci();applyPending();onChange();
   setStatus('Word labels preserve uncertain spaces (commas). Dashed amber boxes have unresolved word positions. Wheel to zoom, drag to pan, or choose a locus to frame its boxes.');
   if(!imageToggle.checked)return;
   const self=layout?.pages?.[figure.dataset.page];
   if(self?.self_hosted){
    // a page the toolkit hosts itself (detected geometry): the boxes are already in the image's frame
    const native={image:self.image,identity:true,boxes:new Map(),registration:{maxCenterError:0,scale:1}};
    s.native=native;figure.classList.add('image-backed');
    const image=document.createElementNS(NS,'image');image.setAttribute('class','manuscript-image');image.setAttribute('width',String(self.width));image.setAttribute('height',String(self.height));
    image.setAttribute('aria-hidden','true');image.setAttribute('preserveAspectRatio','none');
    const note=detectedNote(figure.dataset.page);
    image.addEventListener('load',()=>{if(current===ticket)setStatus('Beinecke image (quarter scale) with detected word boxes: positions found on the image and linked to the transcription by the toolkit, not recorded coordinates. Thin amber boxes have unresolved positions.'+note);});
    image.addEventListener('error',()=>{if(current===ticket)setStatus('The page image could not load. Turn off Page image to return to the coordinate view.');});
    s.svg.prepend(image);image.setAttribute('href',self.image);labels();overlays();applyPending();onChange();
    return;
   }
   setStatus('Loading matching Voynichese image coordinates…');
   try{
    if(!reviewPromise)reviewPromise=SG.load(reviewUrl).catch(error=>{reviewPromise=null;throw error;});
    const review=await reviewPromise;if(current!==ticket)return;
    const native=SG_REVIEW.nativePage(review,figure.dataset.page);
    if(!native.image||!native.boxes.size){setStatus('No registered Voynichese image is available for this page.');return;}
    s.native=native;s.svg.setAttribute('viewBox','0 0 636 900');s.svg.dataset.baseView='0 0 636 900';figure.classList.add('image-backed');
    let missing=0;
    for(const {box} of s.boxes){
     const b=box.dataset.nativeBox?box.dataset.nativeBox.split(',').map(Number):box.hasAttribute('data-xml-index')?native.boxes.get(Number(box.dataset.xmlIndex)):null;
     box.classList.toggle('no-native-box',!b);
     if(b){['x','y','width','height'].forEach((a,k)=>box.setAttribute(a,[b[0],b[1],b[2]-b[0],b[3]-b[1]][k]));}else missing++;
    }
    const image=document.createElementNS(NS,'image');image.setAttribute('class','manuscript-image');image.setAttribute('width','636');image.setAttribute('height','900');
    image.setAttribute('aria-hidden','true');image.setAttribute('preserveAspectRatio','none');
    image.addEventListener('load',()=>{if(current===ticket)setStatus('Voynichese image · matching native word boxes · commas mark uncertain spaces.'+(missing?' '+missing+' unregistered boxes are hidden.':''));});
    image.addEventListener('error',()=>{if(current===ticket)setStatus('The external image could not load. Turn off Page image to return to the coordinate view.');});
    s.svg.prepend(image);image.setAttribute('href',native.image);labels();overlays();
    // the boxes moved into the image's frame: re-frame the chosen locus or re-clamp the view there
    if(framedLocus)frameLocus(framedLocus);else if(view)setView(SG_ZOOM.clampTo({...view,x:view.x*636/Number(s.viewBox.split(/\s+/)[2]),y:view.y*900/Number(s.viewBox.split(/\s+/)[3]),w:view.w*636/Number(s.viewBox.split(/\s+/)[2]),h:view.h*900/Number(s.viewBox.split(/\s+/)[3])},fullView()));
    onChange();
   }catch(error){if(current===ticket)setStatus('Could not load the image registration. Turn Page image off and on to retry.');}
  }
  function overlayDefault(){const keys=Object.keys(data?.overlays||{});return data?.overlay_default||(keys.length>1?'all':keys[0]||'none');}
  function syncOverlays(){
   for(const box of overlayList?.querySelectorAll('input')||[])box.checked=chosenOverlays.has(box.value);
   if(overlayCount)overlayCount.textContent=chosenOverlays.size?String(chosenOverlays.size):'';
  }
  for(const control of [imageToggle,labelToggle,boxStyle,wdirSel].filter(Boolean))control.addEventListener('change',()=>{
   if(control===imageToggle)apply();else{if(expanded)expanded.dataset.boxStyle=boxStyle.value;labels();onChange();}
  });
  if(overlayList)overlayList.addEventListener('change',e=>{if(e.target.checked)chosenOverlays.add(e.target.value);else chosenOverlays.delete(e.target.value);syncOverlays();overlays();onChange();});
  if(coordSel)coordSel.addEventListener('change',()=>{placeRows();apply();onChange();atlas.dispatchEvent(new CustomEvent('coordinates:changed'));});
  if(locusSel)locusSel.addEventListener('change',()=>{if(locusSel.value)frameLocus(locusSel.value);else setView(null);});
  if(zoomReset)zoomReset.addEventListener('click',()=>setView(null));
  atlas.addEventListener('wheel',onWheel,{passive:false});
  atlas.addEventListener('pointerdown',onPointerDown);
  window.addEventListener('pointermove',onPointerMove);
  window.addEventListener('pointerup',onPointerUp);
  window.addEventListener('pointercancel',onPointerUp);
  return {
   expand(figure){
    if(expanded&&expanded!==figure){raw(expanded,true);expanded.removeAttribute('data-box-style');expanded.classList.remove('words-visible');state(expanded).svg.querySelector('.page-word-labels')?.remove();state(expanded).svg.classList.remove('zoomed');view=null;framedLocus='';}
    if(!figure){view=null;framedLocus='';}
    expanded=figure;apply();},
   setData(value){data=value;imageToggle.disabled=!data.spatialReview;
    for(const box of atlas.querySelectorAll('rect[data-token-indices]'))recordedY.set(box,Number(box.getAttribute('y')));     // as rendered: recorded
    if(coordSel){coordSel.disabled=!data.geometry_recorded;coordSel.title=coordSel.disabled?'This text carries one set of coordinates.':'';if(coordSel.disabled)coordSel.value='recorded';}
    const keys=Object.keys(data.overlays||{}),kept=[...chosenOverlays].filter(k=>keys.includes(k));
    chosenOverlays=kept.length?new Set(kept):VMS_ATLAS.parseOverlays(overlayDefault(),keys);
    if(overlayList){overlayList.replaceChildren(...keys.map(k=>{const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=k;label.title=data.overlays[k].description||'';label.append(box,' '+(data.overlays[k].label||k));return label;}));syncOverlays();}
    if(overlayChoice)overlayChoice.hidden=!keys.length;
    placeRows();
    if(imageToggle.disabled&&imageToggle.checked){imageToggle.checked=false;apply();}else{labels();overlays();fillLoci();}},labels,overlays,
   setLayout(value){layout=value;},
   setReviewUrl(url){if(url!==reviewUrl){reviewUrl=url;reviewPromise=null;}},
   readHash(h){imageToggle.checked=h.image==='1';labelToggle.checked=h.words==='1';boxStyle.value=['fill','outline','hidden'].includes(h.boxes)?h.boxes:'fill';if(wdirSel)wdirSel.value=h.wdir==='level'?'level':'ring';
    if(h.overlays){const keys=Object.keys(data?.overlays||{}),asked=VMS_ATLAS.parseOverlays(h.overlays,keys);if(h.overlays==='none'||asked.size){chosenOverlays=asked;syncOverlays();}}
    if(coordSel){coordSel.value=h.coords==='flat'&&!coordSel.disabled?'flat':'recorded';placeRows();}
    pendingLocus=h.zoom||null;pendingView=h.view?SG_ZOOM.parse(h.view):null;if(!h.zoom&&!h.view){view=null;framedLocus='';}},
   hash(){const keys=Object.keys(data?.overlays||{}),chosen=VMS_ATLAS.formatOverlays(chosenOverlays,keys);
    return {image:imageToggle.checked?'1':undefined,words:labelToggle.checked?'1':undefined,boxes:boxStyle.value==='fill'?undefined:boxStyle.value,overlays:keys.length&&chosen!==overlayDefault()?chosen:undefined,coords:coordSel?.value==='flat'?'flat':undefined,wdir:wdirSel?.value==='level'?'level':undefined,
     zoom:expanded&&framedLocus?framedLocus:undefined,view:expanded&&view&&!framedLocus?SG_ZOOM.format(view):undefined};},
   // the point of a source guide: the pools are measured flat, so it follows its box when the box is drawn recorded
   guide(box,point){const figure=box.closest('figure'),s=states.get(figure);
    if(!s?.native){const dy=coordState(figure===expanded?figure:null).drawn==='recorded'?Number(box.dataset.dy||0):0;return {...point,y:point.y+dy,scale:1};}
    const r=s.native.registration;if(!r||r.maxCenterError>=2)return null;
    return {x:Number(box.getAttribute('x'))+Number(box.getAttribute('width'))/2,y:Number(box.getAttribute('y'))+Number(box.getAttribute('height'))/2,scale:r.scale};},
   frameLocus,view(){return view;},coordinates(){return coordSel?.disabled?'recorded':coordSel?.value||'recorded';}
  };
 }
 return {create};
})();
