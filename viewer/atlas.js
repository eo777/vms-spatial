/* Renders the atlas rows (bifolia, leaves or single pages) from a word bundle and the layout record, and resolves what a
   page draws (recorded or flat coordinates, the overlays' points and titles, the line notes).
   Pure functions, so the same code runs in the browser and in node tests. */
"use strict";
const VMS_ATLAS=(()=>{
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 // token ranges of every page: contiguous [start,end) runs of the bundle's lines
 function pageRanges(data){
  const out=new Map();
  for(const line of data.lines){
   const list=out.get(line.page)||[];
   if(list.length&&list[list.length-1][1]===line.start)list[list.length-1][1]=line.end;else list.push([line.start,line.end]);
   out.set(line.page,list);
  }
  return out;
 }
 function pagePosition(data){
  const first=new Map();data.lines.forEach(l=>{if(!first.has(l.page))first.set(l.page,l.start);});return first;
 }
 // ---- the two warp states of a bundle. Per token the recorded bottom minus the flat bottom: a box moves up by this much
 // when drawn flat. null when the bundle has one state only (no geometry_recorded: older study folders). A shared box is
 // absent from the strict arrays, so it takes its group's recorded box against the review's flat sensitivity geometry.
 const shiftCache=new WeakMap();
 function tokenShifts(data){
  if(!data.geometry_recorded)return null;
  if(shiftCache.has(data))return shiftCache.get(data);
  const n=data.words.length,dy=new Float32Array(n),review=data.spatialReview,recorded=data.geometry_recorded,flat=data.geometry;
  if(review?.sensitivityGeometry)for(let i=0;i<n;i++){const g=review.groups[review.tokens[i]?.group],b=review.sensitivityGeometry[i];if(g?.box&&b)dy[i]=g.box[3]-b[3];}
  for(let i=0;i<n;i++){const a=recorded[i],b=flat[i];if(a&&b)dy[i]=a[3]-b[3];}
  shiftCache.set(data,dy);return dy;
 }
 // which state a page draws. `choice` is the Coordinates control; the page image is a photograph, so it forces recorded
 // coordinates while the choice stands. `pageWarp` is the page's warp_pages entry ('flat' or 'recorded (reason)').
 function coordinateState({choice='recorded',canFlat=false,image=false,pageWarp=''}={}){
  const wanted=choice==='flat'&&!!canFlat,drawn=wanted&&!image?'flat':'recorded';
  let note='';
  if(wanted&&image)note='Page image shown: boxes in recorded coordinates';
  else if(drawn==='flat'&&String(pageWarp||'').startsWith('recorded')){const why=/\((.*)\)/.exec(pageWarp);note='No fitted warp on this page: boxes stay recorded'+(why?' ('+why[1]+')':'');}
  return {wanted,drawn,note};
 }
 // the overlays chosen on a page: `all`, `none`, or a comma list of keys in the address
 function parseOverlays(value,keys){
  if(value==='all')return new Set(keys);
  if(!value||value==='none')return new Set();
  return new Set(String(value).split(',').filter(k=>keys.includes(k)));
 }
 function formatOverlays(chosen,keys){
  if(!chosen.size)return 'none';
  return chosen.size===keys.length&&keys.length>1?'all':keys.filter(k=>chosen.has(k)).join(',');
 }
 // the points of an overlay item in the drawn state, or null when the item is limited to the other state
 function overlayPoints(item,drawn,shifts){
  if(item.states&&!item.states.includes(drawn))return null;
  if(drawn==='flat'){
   if(item.points_flat)return item.points_flat;
   if(item.token!=null&&shifts)return item.points.map(([x,y])=>[x,y-shifts[item.token]]);
  }
  return item.points;
 }
 function recordedBox(data,i){
  const g=data.spatialReview?.groups[data.spatialReview.tokens[i]?.group];
  return g?.box||(data.geometry_recorded||data.geometry)[i]||null;
 }
 // the markers an overlay names by a per-token field: at the box centre, the field's value below the box bottom
 function fieldMarkers(overlay,data,page,drawn){
  const field=overlay.markers_from?data[overlay.markers_from]:null,out=[];
  if(!field)return out;
  const shifts=tokenShifts(data);
  for(const L of data.lines){
   if(L.page!==page)continue;
   for(let i=L.start;i<L.end;i++){
    if(field[i]==null)continue;
    const b=recordedBox(data,i);if(!b)continue;
    out.push({page,kind:'marker',style:'baseline',r:overlay.r,line:null,points:[[(b[0]+b[2])/2,b[3]+field[i]-(drawn==='flat'&&shifts?shifts[i]:0)]]});
   }
  }
  return out;
 }
 // an overlay element's title: its own, or built from the line's measures and the item's `info`
 function overlayTitle(item,data){
  if(item.title)return item.title;
  const sign=(v,d=2)=>v==null?'?':(v>0?'+':'')+v.toFixed(d),L=item.line!=null?data.lines[item.line]:null,head=L?'line '+L.locus+': ':'';
  const value=k=>data.measures?.[k]?.line_values?.[item.line],words=i=>data.words[i]??'?',info=item.info||[];
  switch(item.style){
   case 'chord':return head+'chord '+sign(value('chord_flat'))+' deg flat, '+sign(value('chord_recorded'))+' deg recorded';
   case 'ls':return head+'fit '+sign(value('ls_angle'))+' deg, RMS '+(value('fit_rms')??0).toFixed(3)+' H';
   case 'warp-fit':return head+'warped baseline, mean shift '+sign(value('warp_mean'),3)+' H, range '+(value('warp_range')??0).toFixed(3)+' H';
   case 'warp-flat':return head+'the straight baseline the line was flattened to';
   case 'ink-fit':return head+'ink baseline fit, '+sign(value('ink_vs_box_angle'))+' deg against the boxes';
   case 'fit':return head+'component fit';
   case 'fit-ext':return head+'component fit extended across the break';
   case 'break-both':case 'break-transcript':case 'break-geometric':
    return head+({'break-both':'transcript and geometric','break-transcript':'transcript','break-geometric':'geometric'})[item.style]+' break, '+words(info[0])+' | '+words(info[1])+': step '+sign(info[2])+' H, gap '+(info[3]??0).toFixed(2)+' W';
   case 'intrusion':case 'intrusion-touch':
    return words(info[0])+(info[4]?' descender into ':' under ascender of ')+words(info[1])+': '+(info[2]??0).toFixed(2)+' H deep, gap '+(info[3]==null?'?':info[3].toFixed(2))+' H'+(item.style==='intrusion-touch'?', touching':', not touching');
  }
  return '';
 }
 // a line's notes as [label, text]: the line's own, the measures `line_note_fields` names, what its page shares
 function lineNoteItems(data,l){
  const out=[],notes=data.line_notes?.[l],add=o=>{for(const [k,v] of Object.entries(o||{}))if(v!=null)out.push([k,typeof v==='number'?(Number.isInteger(v)?String(v):v.toFixed(3)):String(v)]);};
  add(notes);
  if(!notes)return out;
  for(const [label,key,signed,unit] of data.line_note_fields||[]){
   const m=data.measures?.[key],v=m?.line_values?.[l];if(v==null)continue;
   out.push([label,(signed&&v>0?'+':'')+v.toFixed(m.digits??2)+(unit?' '+unit:'')]);
  }
  add(data.page_notes?.[data.lines[l]?.page]);
  return out;
 }
 // the rectangles of one page: one per original rectangle of each reviewed group (shared groups drawn once), or one per
 // token for a bundle without a review
 function pageRects(page,data,ranges){
  const review=data.spatialReview,rects=[],seen=new Set(),shifts=tokenShifts(data);let first=true;
  const tab=()=>{const t=first?0:-1;first=false;return t;};
  const moved=i=>shifts&&Math.abs(shifts[i])>=.005?` data-dy="${shifts[i].toFixed(2)}"`:'';   // the rectangle's way to the flat state; `y` stays recorded here
  for(const [start,end] of ranges){
   for(let i=start;i<end;i++){
    if(!review){
     const b=(data.geometry_recorded||data.geometry)[i];if(!b||b[2]<=b[0]||b[3]<=b[1])continue;   // drawn in recorded coordinates; measures use data.geometry
     rects.push(`<rect x="${b[0]}" y="${b[1]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="#d5dadd" data-token-indices="${i}"${moved(i)} role="button" tabindex="${tab()}" aria-label="Inspect ${esc(data.words[i])}"><title>${esc(data.words[i])}</title></rect>`);
     continue;
    }
    const t=review.tokens[i];if(!t.group||seen.has(t.group))continue;seen.add(t.group);
    const g=review.groups[t.group];if(!g||!g.positions||!g.positions.length)continue;
    const indices=g.positions.join(','),label=esc(g.label||data.words[i]);
    if(g.resolution){
     const b=g.box,native=g.display_parts&&g.display_parts[0];
     rects.push(`<rect x="${b[0]}" y="${b[1]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="#d5dadd" data-token-indices="${indices}"${moved(g.positions[0])} data-resolved-token="${esc(g.tokens[0])}" data-source-xml-indices="${g.xml_indices.join(',')}"${native?` data-native-box="${native.join(',')}"`:''} role="button" tabindex="${tab()}" aria-label="Inspect ${label}"><title>${label} | ${esc(g.resolution.method)}</title></rect>`);
     continue;
    }
    const flags=[...new Set(g.positions.flatMap(p=>review.tokens[p].flags))].sort(),tip=label+(flags.length?' | '+flags.join(', '):'');
    g.parts.forEach((b,k)=>{
     if(!b||b[2]<=b[0]||b[3]<=b[1])return;   // zero-area source placeholders are omitted, never widened
     rects.push(`<rect x="${b[0]}" y="${b[1]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="#d5dadd" data-token-indices="${indices}"${moved(g.positions[0])} data-xml-index="${g.xml_indices[k]}" role="button" tabindex="${tab()}" aria-label="Inspect ${label}"><title>${esc(tip)}</title></rect>`);
    });
   }
  }
  return rects.join('');
 }
 function pageFigure(page,data,layout,ranges){
  const info=layout.pages[page]||{width:1100,height:1500,missing:true};
  if(!ranges||!ranges.length)return `<figure style="--ratio:${(info.width/info.height).toFixed(4)}"><figcaption>${esc(page)}</figcaption><div class="missing">${esc(page)}<br>Not in this text</div></figure>`;
  if(info.missing)return `<figure style="--ratio:${(info.width/info.height).toFixed(4)}"><figcaption>${esc(page)}</figcaption><div class="missing">${esc(page)}<br>Coordinates not available<br><small>Text is included in the scores.</small></div></figure>`;
  return `<figure style="--ratio:${(info.width/info.height).toFixed(4)}"><figcaption>${esc(page)}</figcaption><svg role="group" aria-label="${esc(page)} word diversity" viewBox="0 0 ${info.width} ${info.height}">${pageRects(page,data,ranges)}</svg></figure>`;
 }
 function sectionLabel(layout,pages){
  const names=[];for(const p of pages){const n=layout.pages[p]?.section_name;if(n&&!names.includes(n))names.push(n);}
  const named=names.filter(n=>n!=='Text');return (named.length?named:names).join(' + ');
 }
 // rows: [{id, title, group, label, detail, sections, pages, N}] for a grouping and an order
 function rows(data,layout,options={}){
  const grouping=options.grouping||'bifolia',order=options.order||'bifolia',pr=pageRanges(data),pos=pagePosition(data);
  const tokensOf=pages=>pages.reduce((s,p)=>s+(pr.get(p)||[]).reduce((t,[a,b])=>t+b-a,0),0);
  let out;
  if(grouping==='bifolia'){
   const ids=layout.orders[order]||layout.orders.bifolia,byId=new Map(layout.nodes.map(n=>[n.id,n]));
   out=ids.filter(id=>byId.has(id)).map(id=>{const n=byId.get(id);return {id:n.id,title:n.id,group:n.group,label:n.label,detail:n.detail,sections:n.sections,pages:n.pages,N:tokensOf(n.pages)};});
  }else if(grouping==='leaves'){
   out=layout.leaves.map(l=>{const title='f'+l.leaf+(l.panel||''),g=layout.pages[l.pages[0]];
    return {id:'leaf:'+title,title,group:g.group,label:sectionLabel(layout,l.pages)+' / '+g.group,detail:l.pages.map(p=>p+': '+layout.pages[p].section_name).join('; '),sections:[...new Set(l.pages.map(p=>layout.pages[p].section_name))],pages:l.pages,N:tokensOf(l.pages),node:g.node};});
   if(order==='path1')out.sort((a,b)=>Math.min(...a.pages.map(p=>pos.get(p)??1e9))-Math.min(...b.pages.map(p=>pos.get(p)??1e9)));
  }else{
   const pages=[...pos.keys()];
   if(order==='folio'){const at=new Map((layout.folio_pages||[]).map((f,k)=>[f,k]));pages.sort((a,b)=>(at.get(a)??1e9)-(at.get(b)??1e9));}
   out=pages.map(p=>{const g=layout.pages[p];return {id:'page:'+p,title:p,group:g.group,label:g.section_name+' / '+g.group,detail:g.bifolium+' · leaf '+g.leaf+g.side+' · quire '+g.quire+(g.hand?' · hand '+g.hand:''),sections:[g.section_name],pages:[p],N:tokensOf([p]),node:g.node};});
  }
  return out.filter(r=>r.N>0);        // a text that does not reach a row (a study on fewer pages) leaves it out
 }
 function renderRow(row,data,layout,pr){
  const ranges=row.pages.flatMap(p=>pr.get(p)||[]);
  return `<section class="bifolio" data-row="${esc(row.id)}" data-group="${esc(row.group)}" data-sections="${esc(row.sections.join('|'))}" data-pages="${esc(row.pages.join(','))}" data-ranges="${ranges.map(r=>r[0]+'-'+r[1]).join(',')}">
<header><span class="group" title="${esc(row.detail)}">${esc(row.label)}</span><h2>${esc(row.title)}</h2><strong>—</strong><span>mean MATTR100</span><div class="bar"><i style="width:0%"></i></div><small>${row.N.toLocaleString('en-US')} words</small></header>
<div class="pages">${row.pages.map(p=>pageFigure(p,data,layout,pr.get(p))).join('')}</div></section>`;
 }
 function render(data,layout,options={}){
  const pr=pageRanges(data);
  return rows(data,layout,options).map(r=>renderRow(r,data,layout,pr)).join('\n');
 }
 return {render,rows,pageRects,pageFigure,pageRanges,sectionLabel,tokenShifts,coordinateState,parseOverlays,formatOverlays,overlayPoints,fieldMarkers,overlayTitle,lineNoteItems};
})();
if(typeof module!=='undefined')module.exports=VMS_ATLAS;
