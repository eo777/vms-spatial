/* Provenance and display groups for the reviewed ZL-to-Voynichese association. */
"use strict";
const SG_REVIEW=(()=>{
 function groups(data,positions){
  const keep=new Set(positions),review=data.spatialReview;
  if(!review)return positions.filter(p=>data.geometry[p]).map(p=>({id:String(p),positions:[p],parts:[data.geometry[p]],box:data.geometry[p],label:data.words[p],flags:[],safe:true}));
  return Object.values(review.groups).filter(g=>g.safe&&g.positions.some(p=>keep.has(p)));
 }
 function note(data,pos){
  const t=data.spatialReview?.tokens[pos];if(!t)return '';
  const g=data.spatialReview.groups[t.group],shared=g?.tokens.length>1;
  return (g?.resolution?(g.resolution.method==='exact_compound_union'?'Resolved compound: adjacent original boxes merged for this ZL word. ':'Image-reviewed word boundary: separate geometry derived from the original box pieces. '):shared?'Shared physical box: '+g.label+'. Individual word positions are unresolved. ':t.strict?'Word-level assignment passes the conservative checks. ':'Word location is excluded from the conservative spatial pool. ')+
   (t.flags.length?'Review: '+t.flags.map(f=>f.replaceAll('_',' ')).join(', ')+'. ':'')+
   (t.after===','?'The following ZL space is uncertain. ':'')+
   (g?'Coordinate transcription: '+g.xml_words.join(' / ')+'.':'No coordinate assignment.');
 }
 function boxLabel(data,positions){
  const seen=new Set(),labels=[];
  for(const pos of positions){
   const token=data.spatialReview?.tokens[pos],group=data.spatialReview?.groups[token?.group],key=group?'g:'+group.id:'p:'+pos;
   if(seen.has(key))continue;seen.add(key);labels.push(group?.label||data.words[pos]);
  }
  return labels.join(' / ');
 }
 function nativePage(review,page){
  const info=review.pages[page],groups=Object.values(review.groups).filter(g=>g.page===page),boxes=new Map();
  for(const g of groups)g.xml_indices.forEach((index,k)=>{
   const b=g.display_parts?.[k];if(b&&b[2]>b[0]&&b[3]>b[1])boxes.set(index,b);
  });
  return {image:info?.display_image,boxes,registration:displayRegistration(groups)};
 }
 // Native display boxes include pixel rounding/padding. Fit their centres to
 // the XML coordinates to recover the page's uniform display scale. Word boxes
 // themselves always use display_parts directly; this is only for guide lengths.
 function displayRegistration(items){
  const points=[];
  for(const g of items){if(g.parts?.length!==g.display_parts?.length)continue;
   g.parts.forEach((a,i)=>{const b=g.display_parts[i];if(a[2]>a[0]&&a[3]>a[1]&&b[2]>b[0]&&b[3]>b[1])points.push([(a[0]+a[2])/2,(a[1]+a[3])/2,(b[0]+b[2])/2,(b[1]+b[3])/2]);});
  }
  if(points.length<3)return null;
  const mean=[0,1,2,3].map(k=>points.reduce((sum,p)=>sum+p[k],0)/points.length);
  let numerator=0,denominator=0;
  for(const p of points){numerator+=(p[0]-mean[0])*(p[2]-mean[2])+(p[1]-mean[1])*(p[3]-mean[3]);denominator+=(p[0]-mean[0])**2+(p[1]-mean[1])**2;}
  if(!denominator)return null;
  const scale=numerator/denominator,tx=mean[2]-scale*mean[0],ty=mean[3]-scale*mean[1];
  const maxCenterError=Math.max(...points.flatMap(p=>[Math.abs(scale*p[0]+tx-p[2]),Math.abs(scale*p[1]+ty-p[3])]));
  return {scale,tx,ty,maxCenterError,count:points.length};
 }
 return {groups,note,boxLabel,nativePage,displayRegistration};
})();
if(typeof module!=='undefined')module.exports=SG_REVIEW;
