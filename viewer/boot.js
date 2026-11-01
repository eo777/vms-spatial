"use strict";
/* Loads the data (index.json, layout.json.gz, the chosen bundle), fills the Text and Order controls, renders the atlas
   with VMS_ATLAS and mounts the controller with VMS_HEATMAP. Changing the text or the order re-renders and re-mounts.
   Order: bifolia = the sheets by their first leaf, each sheet's pages together; pages = single pages in the page
   sequence; path1 = bifolia in Path 1 order. State lives in the location hash (bundle, order + the controller's). */
(async()=>{
 const {$,esc}=SG,atlas=document.querySelector('.heatmap-atlas'),host=$('atlasRows'),bundleSel=$('bundle'),orderSel=$('order'),summary=$('windowSummary');
 const ORDERS={path1:{grouping:'bifolia',order:'path1'},bifolia:{grouping:'bifolia',order:'bifolia'},pages:{grouping:'pages',order:'folio'}};
 let controller=null,layout=null,index=null,data=null,bundleKey='',job=0;
 new MutationObserver(()=>{summary.title=summary.textContent;}).observe(summary,{childList:true});   // the full text when it is cut short
 const pageDisplay=SG_HEATMAP_PAGE.create({atlas,onChange:()=>controller?.onDisplayChange()});
 function save(){SG.setHash({...SG.hash(),bundle:bundleKey,order:orderSel.value});}
 async function loadBundle(key){
  const entry=index.bundles.find(b=>b.key===key)||index.bundles[0];
  const d=await SG.load(SG.dataUrl(entry.path));
  const lineOf=new Uint16Array(d.words.length);
  d.lines.forEach((line,i)=>lineOf.fill(i,line.start,line.end));
  if(!d.palette){const first=index.bundles[0],p=first.path===entry.path?null:await SG.load(SG.dataUrl(first.path));d.palette=p?.palette||SG.defaultPalette();}
  return {key:entry.key,data:SG_HEATMAP.expandMeasures({...d,lineOf})};
 }
 function useBundle(b){data=b.data;bundleKey=b.key;bundleSel.value=b.key;}
 function render(){
  if(controller){controller.destroy();controller=null;}
  pageDisplay.expand(null);
  host.innerHTML=VMS_ATLAS.render(data,layout,ORDERS[orderSel.value]||ORDERS.path1);
  controller=VMS_HEATMAP.mount({atlas,data,layout,pageDisplay});
  document.title='vms-spatial · Atlas · '+bundleKey;
  stateNote();
  save();
 }
 // a rebuild holds the page for a second or more, and of several quick changes the last one wins
 function rebuild(label,load){
  const my=++job;atlas.setAttribute('aria-busy','true');
  return SG.busy(label,async()=>{
   const b=load?await load():null;if(my!==job)return;
   if(b)useBundle(b);
   render();await controller.ready;
  }).catch(error=>{if(my!==job)return;atlas.removeAttribute('aria-busy');bundleSel.value=bundleKey;summary.textContent='Could not load that text. Change a control or reload to retry.';console.error(error);});
 }
 function stateNote(){
  const note=document.getElementById('stateNote');if(!note)return;
  const entry=index.bundles.find(b=>b.key===bundleKey)||{},flat=pageDisplay.coordinates()==='flat';
  note.textContent=(entry.warp!=='flat'?'Boxes and measures are in recorded coordinates.':flat?'Boxes are drawn in the flat state, with each page\'s photographic warp removed; the spatial measures are computed there too. A page image returns its boxes to recorded coordinates.':'Boxes are drawn in recorded coordinates (as on the photographs); the spatial measures are computed in the flat state, with each page\'s photographic warp removed.')+(entry.pages==='all'?' Every page is included, with every locus that has a fully read word.':entry.pages==='paragraph'?' Paragraph text of the 207 study pages only.':'');
 }
 try{await SG.busy('Loading the manuscript…',async()=>{
  const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
  const h=SG.hash();
  SG.setBase(h.data||config.dataBase||'data/');
  index=await SG.load(SG.dataUrl('index.json'));
  layout=await SG.load(SG.dataUrl(index.layout||'layout.json.gz'));pageDisplay.setLayout(layout);pageDisplay.setReviewUrl(SG.dataUrl(index.review||'spatial_review.json.gz'));
  bundleSel.replaceChildren(...index.bundles.map(b=>new Option(b.label,b.key)));
  orderSel.value=ORDERS[h.order]?h.order:(index.default_order==='path1'?'path1':'bifolia');
  useBundle(await loadBundle(h.bundle||config.defaultBundle||index.bundles[0].key));
  render();await controller.ready;
  bundleSel.addEventListener('change',()=>rebuild('Loading '+bundleSel.selectedOptions[0].textContent+'…',()=>loadBundle(bundleSel.value)));
  orderSel.addEventListener('change',()=>rebuild('Arranging the pages…'));
  atlas.addEventListener('coordinates:changed',stateNote);
  window.addEventListener('hashchange',()=>{const hh=SG.hash();if(hh.bundle&&hh.bundle!==bundleKey)rebuild('Loading '+hh.bundle+'…',()=>loadBundle(hh.bundle));});
 });}catch(error){summary.textContent='Could not load the viewer data.';SG.error(host,error);}
})();
