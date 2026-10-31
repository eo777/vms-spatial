/* Fixed-width local diversity; no second smoothing window. */
"use strict";
const SG_HEATMAP=(()=>{
 function bounds(pos,width,direction,length){
  const before=direction==='forward'?0:direction==='centered'?Math.floor((width-1)/2):width-1;
  const first=pos-before,last=first+width;
  return {start:Math.max(0,first),end:Math.min(length,last),full:first>=0&&last<=length};
 }
 function windowAt(words,pos,width,direction){
  const b=bounds(pos,width,direction,words.length),tokens=words.slice(b.start,b.end),counts=new Map();
  for(const word of tokens)counts.set(word,(counts.get(word)||0)+1);
  return {...b,words:tokens,counts,size:tokens.length,unique:counts.size,score:b.full?counts.size/width:null};
 }
 function series(words,width,direction){
  const scores=new Float64Array(words.length).fill(NaN),repeated=new Uint8Array(words.length),counts=new Map();
  let start=0,end=0;
  for(let i=0;i<words.length;i++){
   const b=bounds(i,width,direction,words.length);
   while(end<b.end){const word=words[end++];counts.set(word,(counts.get(word)||0)+1);}
   while(start<b.start){const word=words[start++],count=counts.get(word)-1;if(count)counts.set(word,count);else counts.delete(word);}
   if(b.full)scores[i]=counts.size/width;
   repeated[i]=counts.get(words[i])>1?1:0;
  }
  return {scores,repeated};
 }
 function meanWithin(scores,start,end,width,direction){
  let sum=0,n=0;
  for(let i=start;i<end;i++){
   const b=bounds(i,width,direction,scores.length);
   if(b.full&&b.start>=start&&b.end<=end&&Number.isFinite(scores[i])){sum+=scores[i];n++;}
  }
  return n?sum/n:null;
 }
 // Exact fixed-length counterfactual: replace ONE occurrence with a fresh spelling.
 // A containing window gains 1/W iff another occurrence remains in that window.
 // Only nearest equal neighbors determine whether a window contains another copy.
 function wordImpact(words,width){
  const length=words.length,previous=new Int32Array(length).fill(-1),next=new Int32Array(length).fill(length),last=new Map();
  for(let i=0;i<length;i++){
   if(last.has(words[i])){const p=last.get(words[i]);previous[i]=p;next[p]=i;}
   last.set(words[i],i);
  }
  const windows=new Uint16Array(length),affected=new Uint16Array(length),gain=new Float64Array(length).fill(NaN);
  const change=new Float64Array(length).fill(NaN),enter=new Uint8Array(length),leave=new Uint8Array(length);
  for(let i=0;i<length;i++){
   const lo=Math.max(0,i-width+1),hi=Math.min(i,length-width),count=Math.max(0,hi-lo+1);
   const unique=Math.max(0,Math.min(hi,next[i]-width)-Math.max(lo,previous[i]+1)+1);
   windows[i]=count;affected[i]=count-unique;if(count)gain[i]=affected[i]/(count*width);
   if(i>=width){
    // Remove the outgoing token first, then add the incoming token to the W-1 retained words.
    enter[i]=previous[i]<i-width+1?1:0;
    leave[i]=next[i-width]>=i?1:0;
    change[i]=(enter[i]-leave[i])/width;
   }
  }
  return {previous,next,windows,affected,gain,change,enter,leave};
 }
 function impactBounds(pos,width,length){
  if(length<width)return {start:0,end:length,windows:0};
  const first=Math.max(0,pos-width+1),last=Math.min(pos,length-width);
  return {start:first,end:last+width,windows:last-first+1};
 }
 // How one window's score splits over its words. Its distinct count is the sum, over its tokens, of 1/(copies of the
 // token's spelling in the window): each token adds 1/c of a distinct form, so the score is the mean of those shares.
 // A spelling with c copies costs c−1 forms, −(c−1)/width of the score; the costs add up to size − distinct.
 function contributions(win){
  const share=win.words.map(word=>1/win.counts.get(word)),lost=win.size-win.unique;
  const spellings=[...win.counts].filter(([,count])=>count>1).map(([word,count])=>({word,count,lost:count-1,share:lost?(count-1)/lost:0}))
   .sort((a,b)=>b.count-a.count||(a.word<b.word?-1:a.word>b.word?1:0));
  return {share,lost,spellings};
 }
 // a measure carried by a bundle (one value per token): its colour domain (given, or the 5-95% range of the finite
 // values; symmetric about zero when diverging) and a value's position in it
 function measureDomain(values,kind,domain){
  if(domain&&domain.length===2&&Number.isFinite(domain[0])&&Number.isFinite(domain[1])&&domain[1]>domain[0])return [domain[0],domain[1]];
  const v=Array.from(values||[]).filter(Number.isFinite).sort((a,b)=>a-b);
  if(!v.length)return null;
  const q=p=>v[Math.min(v.length-1,Math.max(0,Math.floor(p*(v.length-1))))];
  let lo=q(.05),hi=q(.95);
  if(!(hi>lo)){lo=v[0];hi=v[v.length-1];}
  if(!(hi>lo)){lo-=1;hi+=1;}
  if(kind==='diverging'){const m=Math.max(Math.abs(lo),Math.abs(hi));return [-m,m];}
  return [lo,hi];
 }
 // a per-line measure ships one value per line (`line_values`); every token of a line takes its value here, NaN where
 // the line has none, so the domain, the colours and the row means read `values` as for any measure
 function expandMeasures(data){
  const n=data.words.length;
  for(const m of Object.values(data.measures||{})){
   if(m.values||!m.line_values)continue;
   const values=new Float64Array(n).fill(NaN);
   data.lines.forEach((L,k)=>{const v=m.line_values[k];if(v!=null)values.fill(v,L.start,L.end);});
   m.values=values;
  }
  return data;
 }
 function measureFraction(value,domain,kind){
  if(!domain||!Number.isFinite(value))return NaN;
  return Math.max(0,Math.min(1,(value-domain[0])/(domain[1]-domain[0])));
 }
 return {bounds,windowAt,series,meanWithin,wordImpact,impactBounds,contributions,measureDomain,measureFraction,expandMeasures};
})();
if(typeof module!=='undefined')module.exports=SG_HEATMAP;
