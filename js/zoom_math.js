/* Zoom and pan of an SVG page through its viewBox: pure functions shared by the atlas (heatmap_page.js) and the node
   tests. A view is {x, y, w, h} in the page's coordinate frame; the figure's full view is the page size. */
"use strict";
const SG_ZOOM=(()=>{
 const MIN_SCALE=1,MAX_SCALE=40;
 function parse(text){
  if(!text)return null;const v=String(text).split(',').map(Number);
  if(v.length!==4||v.some(n=>!Number.isFinite(n))||v[2]<=0||v[3]<=0)return null;
  return {x:v[0],y:v[1],w:v[2],h:v[3]};
 }
 function format(view){return [view.x,view.y,view.w,view.h].map(n=>Math.round(n*100)/100).join(',');}
 function clampTo(view,full){
  // never larger than the page, never further out than the page's edges, never magnified beyond MAX_SCALE
  const scale=Math.min(MAX_SCALE,Math.max(MIN_SCALE,full.w/view.w));
  const w=full.w/scale,h=w*full.h/full.w;
  const x=Math.min(Math.max(view.x,full.x),full.x+full.w-w),y=Math.min(Math.max(view.y,full.y),full.y+full.h-h);
  return {x,y,w,h};
 }
 // zoom by `factor` (>1 magnifies) about a point given in page coordinates: the point stays where it is on screen
 function zoomAt(view,full,factor,point){
  const w=view.w/factor,h=view.h/factor;
  const fx=(point.x-view.x)/view.w,fy=(point.y-view.y)/view.h;
  return clampTo({x:point.x-fx*w,y:point.y-fy*h,w,h},full);
 }
 // pan by a screen delta (pixels) given the element's screen size: the page moves with the pointer
 function pan(view,full,dxPx,dyPx,screenW,screenH){
  return clampTo({x:view.x-dxPx*view.w/screenW,y:view.y-dyPx*view.h/screenH,w:view.w,h:view.h},full);
 }
 // the view that frames a set of boxes [[x0,y0,x1,y1],...] with a margin (a share of the frame), keeping the page's aspect
 function frame(boxes,full,margin=0.15){
  const valid=boxes.filter(b=>b&&b[2]>b[0]&&b[3]>b[1]);
  if(!valid.length)return {...full};
  let x0=Math.min(...valid.map(b=>b[0])),y0=Math.min(...valid.map(b=>b[1])),x1=Math.max(...valid.map(b=>b[2])),y1=Math.max(...valid.map(b=>b[3]));
  let w=x1-x0,h=y1-y0;
  const m=Math.max(w,h)*margin;x0-=m;y0-=m;w+=2*m;h+=2*m;
  // match the page's aspect ratio so the boxes are not stretched
  const aspect=full.w/full.h;
  if(w/h>aspect){const nh=w/aspect;y0-=(nh-h)/2;h=nh;}else{const nw=h*aspect;x0-=(nw-w)/2;w=nw;}
  return clampTo({x:x0,y:y0,w,h},full);
 }
 // screen pixel -> page coordinates for an element of size screenW x screenH showing `view`
 function toPage(view,px,py,screenW,screenH){return {x:view.x+px*view.w/screenW,y:view.y+py*view.h/screenH};}
 function isFull(view,full,eps=1e-6){return Math.abs(view.x-full.x)<eps&&Math.abs(view.y-full.y)<eps&&Math.abs(view.w-full.w)<eps&&Math.abs(view.h-full.h)<eps;}
 function scale(view,full){return full.w/view.w;}
 return {parse,format,clampTo,zoomAt,pan,frame,toPage,isFull,scale,MIN_SCALE,MAX_SCALE};
})();
if(typeof module!=='undefined')module.exports=SG_ZOOM;
