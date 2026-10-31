/* Raw Zattera-unit distance and causal source alternatives. No grammar filtering. */
"use strict";
const SG_COPY=(()=>{
 function distance(a,b){
  let row=Array.from({length:b.length+1},(_,i)=>i);
  for(let i=0;i<a.length;i++){const next=[i+1];for(let j=0;j<b.length;j++)next[j+1]=Math.min(next[j]+1,row[j+1]+1,row[j]+(a[i]!==b[j]));row=next;}
  return row[b.length];
 }
 function prepare(data){
  const cache=new Map();
  return {data,distance(a,b){
   const key=a<b?a+'\0'+b:b+'\0'+a;
   if(!cache.has(key)){
    if(cache.size>=150000)cache.clear();
    if(!data.components[a]||!data.components[b])throw Error('Missing lossless glyph units');
    cache.set(key,distance(data.components[a],data.components[b]));
   }
   return cache.get(key);
  }};
 }
 function measure(ctx,pos,pool,detail=false){
  const target=ctx.data.words[pos],types=new Map(),items=[];let minimum=Infinity;
  pool.indices.forEach((p,k)=>{
   if(p>=pos)throw Error('Copy sources must precede the target');
   const word=ctx.data.words[p],d=ctx.distance(word,target);minimum=Math.min(minimum,d);
   if(!types.has(word))types.set(word,{word,distance:d,positions:[],weight:0});
   const item=types.get(word);item.positions.push(p);item.weight+=pool.weights[k];
   if(detail)items.push({position:p,word,distance:d,weight:pool.weights[k]});
  });
  const values=[...types.values()],nearest=values.filter(x=>x.distance===minimum),n=pool.indices.length;
  const result={n,distinct:types.size,minedit:n?minimum:NaN,nearestTypes:nearest.length,nearestOccurrences:nearest.reduce((a,x)=>a+x.positions.length,0),missingTarget:!!pool.missingTarget};
  for(let d=0;d<=3;d++){
   const close=values.filter(x=>x.distance<=d);
   result['candidateTypes'+d]=n?close.length:NaN;
   result['candidateOccurrences'+d]=n?close.reduce((a,x)=>a+x.positions.length,0):NaN;
  }
  if(detail){result.sources=values.sort((a,b)=>a.distance-b.distance||b.weight-a.weight||a.word.localeCompare(b.word));result.items=items;}
  return result;
 }
 async function series(ctx,geometry,cap,options,isCurrent=()=>true,onProgress=()=>{},sources=SG_SOURCES){
  const out=[];
  for(let p=0;p<ctx.data.words.length;p++){
   if(p%128===0){await new Promise(r=>setTimeout(r,0));if(!isCurrent())return null;onProgress(p,ctx.data.words.length);}
   out.push(measure(ctx,p,sources.sourcePool(geometry,p,cap,options)));
  }
  if(!isCurrent())return null;onProgress(out.length,out.length);return out;
 }
 function distanceColor(d){return !Number.isFinite(d)?'var(--line2)':['#397d69','#70aa8c','#d1b05f','#ce8058','#ad5251','#84586e'][Math.max(0,Math.min(5,Math.round(d)))];}
 // Separate zero, one and two alternatives; compress the sparse upper tail.
 // Fixed bands keep pages, edit cutoffs and source-count modes comparable.
 const candidateBands=[
  {max:0,label:'0',color:'#c05c50'},
  {max:1,label:'1',color:'#d9a84a'},
  {max:2,label:'2',color:'#b5c887'},
  {max:4,label:'3–4',color:'#6eada1'},
  {max:8,label:'5–8',color:'#6094b5'},
  {max:16,label:'9–16',color:'#6f7fb4'},
  {max:Infinity,label:'17+',color:'#83649f'},
 ];
 function candidateColor(n){return !Number.isFinite(n)?'var(--line2)':candidateBands.find(b=>n<=b.max).color;}
 return {distance,prepare,measure,series,distanceColor,candidateColor,candidateBands};
})();
if(typeof module!=='undefined')module.exports=SG_COPY;
