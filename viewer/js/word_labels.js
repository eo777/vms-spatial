/* Word labels that follow the writing, shared by the atlas and the comparison page.

   A rectangle is axis-aligned, so its width says nothing about a word that runs down the page: on a ring the boxes at
   3 and 9 o'clock are narrow, and a label fitted to the width comes out about half the size of one at 12 o'clock. Here
   a word's size comes from its length ALONG ITS OWN DIRECTION, and one size serves a whole group (a wheel, a page), so
   the glyphs keep one height around the ring.

   Directions are degrees clockwise on the page, 0 = left to right, the sense of SVG's rotate():
     circular text   orientation.word_angles: the word's bottom towards the wheel's centre (0 at 12 o'clock, 90 at 3,
                     180 at 6, -90 at 9);
     rotated text,   orientation.angle_deg, the line's chord in reading order;
     steep labels
     radial text     the chord where the line has one; otherwise the ray from the centre, turned so that it does not
                     read upside down, because the boxes cannot say which way a single word runs.

   Modes: 'ring' draws each word in that direction; 'level' draws every word upright at the same size, which keeps the
   words at 3 and 9 o'clock readable without turning your head. Boxes never move: only the labels turn.
   No DOM; viewer/test/word_labels.test.js runs this in node. */
(function(root){
'use strict';
const ADVANCE=0.6,TURNED=30,MIN_SIZE=3,MODES=['ring','level'];           // ADVANCE: a monospace glyph's width in ems
const rad=d=>d*Math.PI/180;
const median=v=>{const s=[...v].sort((a,b)=>a-b),n=s.length;return n?(n%2?s[(n-1)/2]:(s[n/2-1]+s[n/2])/2):NaN;};

/* ringAngle(x, y, cx, cy) -> the direction that puts the bottom of a word at (x, y) towards the centre (cx, cy) */
function ringAngle(x,y,cx,cy){return Math.atan2(x-cx,cy-y)*180/Math.PI;}

/* upright(angle) -> the same line of writing, turned half way round where it would read upside down: (-90, 90] */
function upright(a){let d=((a+180)%360+360)%360-180;if(d>90)d-=180;else if(d<=-90)d+=180;return d;}

/* angleOf(orientation, j) -> the direction of token j of a line from its orientation record: 0 for level text, null
   for a turned line whose direction is unknown (a ring that failed the wheel screens) */
function angleOf(o,j){
  if(!o)return 0;
  const a=o.word_angles?o.word_angles[j]:null;
  if(o.kind==='circular')return a==null?null:a;
  if(o.kind==='radial')return o.angle_deg!=null?o.angle_deg:(a==null?null:upright(a));
  if(o.kind==='rotated')return o.angle_deg==null?null:o.angle_deg;
  if(o.kind==='label'&&Math.abs(o.angle_deg||0)>=TURNED)return o.angle_deg;
  return 0;
}

/* extents(rect, angle) -> an axis-aligned box seen along a direction: `along` and `across` are its projections, and
   k = |sin 2a| is how much of the other dimension each one holds (along = L + k T, across = T + k L for a word of
   length L and thickness T) */
function extents(rect,angle){
  const w=rect[2]-rect[0],h=rect[3]-rect[1],c=Math.abs(Math.cos(rad(angle))),s=Math.abs(Math.sin(rad(angle)));
  return {along:c*w+s*h,across:s*w+c*h,k:2*c*s};
}

/* thickness(items) -> the group's median text thickness, solved on the words well away from 45 degrees, where the two
   equations above are independent */
function thickness(items){
  const t=[];
  for(const it of items){
    if(it.angle==null)continue;
    const e=extents(it.rect,it.angle);
    if(e.k<0.7){const v=(e.across-e.k*e.along)/(1-e.k*e.k);if(v>0)t.push(v);}
  }
  return t.length?median(t):0.5*median(items.map(it=>Math.min(it.rect[2]-it.rect[0],it.rect[3]-it.rect[1])));
}

/* alongLength(rect, angle, T) -> the word's length along its direction; with no direction, the box's longer side */
function alongLength(rect,angle,T){
  if(angle==null)return Math.max(rect[2]-rect[0],rect[3]-rect[1]);
  const e=extents(rect,angle);
  return Math.max(0.5*e.along,e.along-e.k*T);
}

/* layout(items, mode) -> per item {x, y, angle, size} for a label centred on its box.
   items = [{rect: [x0, y0, x1, y1], text, angle}], one group sharing a size: a wheel, or a page's turned words.
   The size is the group's median fit, and a word that would overrun its own box takes a smaller one. */
function layout(items,mode='ring'){
  const T=thickness(items),fits=items.map(it=>alongLength(it.rect,it.angle,T)/(ADVANCE*Math.max(1,it.text.length))),F=median(fits);
  return items.map((it,i)=>({x:(it.rect[0]+it.rect[2])/2,y:(it.rect[1]+it.rect[3])/2,angle:mode==='level'||it.angle==null?0:it.angle,size:Math.max(MIN_SIZE,Math.min(F,1.25*fits[i]))}));
}

const api={MODES,ADVANCE,TURNED,ringAngle,upright,angleOf,extents,thickness,alongLength,layout};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VMS_WORDS=api;
})(typeof window!=='undefined'?window:globalThis);
