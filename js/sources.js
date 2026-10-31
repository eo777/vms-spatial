/* Spatial source pools and component distributions. No generator state is changed. */
"use strict";
const SG_SOURCES=(()=>{
 const median=a=>{const s=a.filter(Number.isFinite).sort((a,b)=>a-b),n=s.length;return n?(s[(n-1)>>1]+s[n>>1])/2:NaN;};
 const entropy=a=>{let total=0;for(const x of a)total+=x;if(!total)return NaN;let h=0;for(const x of a)if(x>0){const p=x/total;h-=p*Math.log2(p);}return h;};
 function jsDistance(a,b){
  const sa=a.reduce((s,v)=>s+v,0),sb=b.reduce((s,v)=>s+v,0);if(!sa||!sb)return NaN;
  let d=0;for(let i=0;i<a.length;i++){const p=a[i]/sa,q=b[i]/sb,m=(p+q)/2;if(p)d+=p*Math.log2(p/m)/2;if(q)d+=q*Math.log2(q/m)/2;}
  return Math.sqrt(Math.max(0,d));
 }
 function prepare(data,options={}){
  const pages=new Map(),lineOf=new Uint16Array(data.words.length),unitIds=new Map(),pairIds=new Map(),pairLeft=[],unitNames=[],pairNames=[];
  data.lines.forEach((line,k)=>{
   lineOf.fill(k,line.start,line.end);
   if(!pages.has(line.page))pages.set(line.page,{indices:[],lines:[]});
   const page=pages.get(line.page);page.lines.push(k);for(let i=line.start;i<line.end;i++)page.indices.push(i);
  });
  // Same page-relative filter as page_geometry.oversized_flags in the research.
  // Keep canonical words and raw data intact; invalid rectangles are not sources.
  const reviewed=!!data.spatialReview;
  const excluded=new Set(),geometry=(options.policy==='sensitivity'&&reviewed?data.spatialReview.sensitivityGeometry:data.geometry).slice();
  if(reviewed){
   data.spatialReview.tokens.forEach((t,i)=>{if(!geometry[i])excluded.add(i);});
  }else for(const page of pages.values()){
   const boxes=page.indices.map(i=>geometry[i]).filter(Boolean),w=median(boxes.map(b=>b[2]-b[0])),h=median(boxes.map(b=>b[3]-b[1]));
   for(const i of page.indices){const b=geometry[i];if(b&&(b[2]-b[0]>6*w||b[3]-b[1]>2.5*h)){excluded.add(i);geometry[i]=null;}}
  }
  const centers=geometry.map(b=>b?{x:(b[0]+b[2])/2,y:(b[1]+b[3])/2,width:b[2]-b[0],height:b[3]-b[1]}:null);
  for(const page of pages.values()){
   const boxes=page.indices.map(i=>centers[i]).filter(Boolean);
   page.wordWidth=median(boxes.map(b=>b.width))||1;
   const ys=page.lines.map(k=>{const l=data.lines[k],a=[];for(let i=l.start;i<l.end;i++)if(geometry[i])a.push(geometry[i]);return (median(a.map(b=>b[1]))+median(a.map(b=>b[3])))/2;});
   page.pitch=median(ys.slice(1).map((y,i)=>y-ys[i]).filter(v=>v>0))||median(boxes.map(b=>b.height))*1.6||1;
  }
  const getUnit=text=>{if(!unitIds.has(text)){unitIds.set(text,unitIds.size);unitNames.push(text);}return unitIds.get(text);};
  const features=new Map();
  for(const [word,units] of Object.entries(data.components)){
   const mono=new Map(),pairs=new Map(),ids=units.map(getUnit);
   for(const id of ids)mono.set(id,(mono.get(id)||0)+1);
   for(let k=1;k<ids.length;k++){
    const key=ids[k-1]+','+ids[k];
    if(!pairIds.has(key)){pairIds.set(key,pairIds.size);pairLeft.push(ids[k-1]);pairNames.push(units[k-1]+'·'+units[k]);}
    const id=pairIds.get(key);pairs.set(id,(pairs.get(id)||0)+1);
   }
   features.set(word,{mono:[...mono].map(([id,n])=>[id,n/ids.length]),pairs:[...pairs].map(([id,n])=>[id,n/(ids.length-1)])});
  }
  const tokenFeatures=data.words.map(w=>features.get(w)),baseline=new Float64Array(pairIds.size);
  for(const f of tokenFeatures)for(const [id,p] of f.pairs)baseline[id]+=p;
  return {data,pages,lineOf,centers,geometry,excluded,tokenFeatures,baseline,pairLeft,unitNames,pairNames};
 }
 // options: left (same-line reach in word widths), depth (line spacings), angle (degrees), weight ('distance'|'uniform'),
 // metric ('centre' = centre-to-centre same-line distance; 'edge' = gap between the boxes + 1, width-neutral: an adjacent
 // word has distance 1 whatever the target's length), target ('box' = the recorded rectangle; 'cursor' = a provisional
 // box one median word wide at the target's left edge, fixed before the word's width is known).
 function sourcePool(ctx,pos,limit,options={}){
  const {left=3,depth=8,angle=45,weight='distance',metric='centre',target:targetMode='box'}=options;
  const raw=ctx.centers[pos];if(!raw)return {indices:[],weights:[],available:0,missingTarget:true};
  const line=ctx.lineOf[pos],page=ctx.pages.get(ctx.data.lines[line].page),candidates=[],tan=Math.tan(angle*Math.PI/180);
  const tb=ctx.geometry[pos],target=targetMode==='cursor'?{x:tb[0]+page.wordWidth/2,y:raw.y}:raw;
  for(const i of page.indices){
   if(i>=pos)break;
   const b=ctx.centers[i];if(!b)continue;
   const dx=b.x-target.x,dy=target.y-b.y;let distance,alignment=1;
   if(ctx.lineOf[i]===line){if(dx>=0||-dx>left*page.wordWidth)continue;distance=metric==='edge'?1+Math.max(0,tb[0]-ctx.geometry[i][2])/page.wordWidth:-dx/page.wordWidth;}
   else{
    // A source word is eligible when its recorded rectangle intersects the
    // finite cone, even when its center falls outside the drawn guide.
    const box=ctx.geometry[i],near=Math.max(0,target.y-box[3]),far=Math.min(depth*page.pitch,target.y-box[1]);
    const horizontal=Math.max(box[0]-target.x,target.x-box[2],0);
    if(dy<=0||far<=0||near>far||horizontal>far*tan+1e-8)continue;
    distance=Math.hypot(dx,dy)/page.pitch;alignment=dy*dy/(dx*dx+dy*dy);
   }
   candidates.push({i,distance,w:weight==='uniform'?1:alignment/(1+distance)**2});
  }
  candidates.sort((a,b)=>b.w-a.w||a.distance-b.distance||b.i-a.i);
  const chosen=candidates.slice(0,limit).sort((a,b)=>a.i-b.i);
  return {indices:chosen.map(c=>c.i),weights:chosen.map(c=>c.w),available:candidates.length,missingTarget:false};
 }
 function windowPool(ctx,pos,width,direction){
  const before=direction==='forward'?0:direction==='centered'?Math.floor((width-1)/2):width-1,start=pos-before,end=start+width;
  const indices=[];for(let i=Math.max(0,start);i<Math.min(ctx.data.words.length,end);i++)indices.push(i);
  return {indices,weights:indices.map(()=>1),available:indices.length,full:start>=0&&end<=ctx.data.words.length};
 }
 function measure(ctx,pool,detail=false){
  const mono=new Float64Array(ctx.unitNames.length),pairs=new Float64Array(ctx.pairNames.length),lefts=new Float64Array(ctx.unitNames.length),types=new Map();
  let mass=0,squared=0,pairMass=0,pairSquared=0,pairWords=0;
  pool.indices.forEach((i,k)=>{
   const w=pool.weights[k],f=ctx.tokenFeatures[i];mass+=w;squared+=w*w;
   types.set(ctx.data.words[i],(types.get(ctx.data.words[i])||0)+w);
   for(const [id,p] of f.mono)mono[id]+=w*p;
   if(f.pairs.length){pairWords++;pairMass+=w;pairSquared+=w*w;}
   for(const [id,p] of f.pairs)pairs[id]+=w*p;
  });
  let collision=0;for(const w of types.values())collision+=(w/mass)**2;
  for(let id=0;id<pairs.length;id++)lefts[ctx.pairLeft[id]]+=pairs[id];
  const n=pool.indices.length,ess=squared?mass*mass/squared:0,pairEss=pairSquared?pairMass*pairMass/pairSquared:0;
  const full=pool.full!==false,monoOK=full&&n>=5&&ess>=3,pairOK=full&&pairWords>=5&&pairEss>=3;
  const pairH=entropy(pairs),h1=monoOK?entropy(mono):NaN,h2=pairOK?Math.max(0,pairH-entropy(lefts)):NaN;
  const result={n,ess,pairWords,pairEss,available:pool.available,worddiv:n?Math.max(0,1-collision):NaN,
   h1,h2,components:pairOK?2**pairH:NaN,js:pairOK?jsDistance(pairs,ctx.baseline):NaN,distinct:types.size};
  if(detail){
   const top=(values,names)=>{const total=values.reduce((a,b)=>a+b,0);return [...values].map((v,i)=>({name:names[i],p:v/total})).filter(x=>x.p>0).sort((a,b)=>b.p-a.p).slice(0,8);};
   result.topUnits=top(mono,ctx.unitNames);result.topPairs=top(pairs,ctx.pairNames);
   result.types=[...types].map(([word,w])=>({word,p:w/mass})).sort((a,b)=>b.p-a.p);
  }
  return result;
 }
 // A shared linear contrast range, fitted once to the full path for these settings.
 // Saturate the tails without changing scores or rescaling individual pages/regions.
 function colorDomain(values){
  const a=values.filter(Number.isFinite).sort((a,b)=>a-b),n=a.length;
  if(!n)return {low:0,high:1,count:0,constant:false};
  const quantile=p=>{const i=(n-1)*p,k=Math.floor(i);return a[k]+(a[Math.min(k+1,n-1)]-a[k])*(i-k);};
  let low=quantile(.05),high=quantile(.95),trimmed=true;
  if(high-low<1e-9){low=a[0];high=a[n-1];trimmed=false;}
  return {low,high,count:n,trimmed,constant:high-low<1e-9};
 }
 function colorFraction(value,domain){
  return !Number.isFinite(value)?NaN:domain.constant ? .5 : Math.max(0,Math.min(1,(value-domain.low)/(domain.high-domain.low)));
 }
 async function series(ctx,width,direction,options,isCurrent=()=>true,onProgress=()=>{}){
  const stats=[];
  for(let i=0;i<ctx.data.words.length;i++){
   if(i%96===0){await new Promise(resolve=>setTimeout(resolve,0));if(!isCurrent())return null;onProgress(i,ctx.data.words.length);}
   const pool=direction==='spatial'?sourcePool(ctx,i,width,options):windowPool(ctx,i,width,direction);
   stats.push(measure(ctx,pool));
  }
  if(!isCurrent())return null;
  onProgress(ctx.data.words.length,ctx.data.words.length);return stats;
 }
 return {prepare,sourcePool,windowPool,measure,series,entropy,jsDistance,colorDomain,colorFraction};
})();
if(typeof module!=='undefined')module.exports=SG_SOURCES;
