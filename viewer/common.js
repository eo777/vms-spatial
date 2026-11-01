"use strict";
// Shared by the viewer pages: data loading, formatting, the location hash, tooltips, errors, the loading indicator.
const SG=(()=>{
 const $=id=>document.getElementById(id);
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 const fmt=(x,d=1)=>finite(x)?x.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
 const int=x=>finite(x)?Math.round(x).toLocaleString('en-US'):'—';
 const pct=(x,d=1)=>finite(x)?fmt(100*x,d)+'%':'—';
 const signed=(x,d=2)=>finite(x)?(x>0?'+':x<0?'−':'')+fmt(Math.abs(x),d):'—';
 // the data folder: viewer/config.json's dataBase, or ?data=<url> in the hash, or data/
 let base='data/';
 function setBase(b){base=b.endsWith('/')?b:b+'/';}
 function dataUrl(rel){return /^(https?:)?\/\//.test(rel)||rel.startsWith('data:')?rel:base+rel;}
 async function readGz(url){
  const r=await fetch(url);if(!r.ok)throw Error(`${url}: ${r.status}`);
  if(/\.gz(\?|$)/.test(url)){
   if(!('DecompressionStream' in window))throw Error('This browser cannot decompress the data files (no DecompressionStream).');
   return JSON.parse(await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).text());
  }
  return r.json();
 }
 const cache={};
 const load=url=>cache[url]||(cache[url]=readGz(url).catch(e=>{delete cache[url];throw e;}));
 // ---- Zattera units (js port of vmsspatial.units.zattera), for callers that need components of a new word
 const COMPOSITES=['cph','cfh','ckh','cth','ch','sh'];
 function atoms(word){
  const out=[];let i=0;
  while(i<word.length){
   const c=word[i];
   if(c==='{'){const j=word.indexOf('}',i+1);if(j<0){out.push([c,'literal']);i++;continue;}out.push([word.slice(i,j+1),'ligature']);i=j+1;continue;}
   if(c==='@'){const m=/^@\d+;/.exec(word.slice(i));if(m){out.push([m[0],'extended']);i+=m[0].length;continue;}}
   const comp=COMPOSITES.find(k=>word.startsWith(k,i));
   if(comp){out.push([comp,'composite']);i+=comp.length;continue;}
   out.push([c,'glyph']);i++;
  }
  return out;
 }
 function units(word){
  const a=atoms(word),out=[];let i=0;
  while(i<a.length){
   const [raw,kind]=a[i];
   if(kind!=='glyph'){out.push(raw);i++;continue;}
   if(raw==='e'||raw==='i'){let j=i;while(j<a.length&&a[j][1]==='glyph'&&a[j][0]===raw)j++;out.push(raw.repeat(j-i));i=j;continue;}
   out.push(raw);i++;
  }
  return out;
 }
 // ---- tooltip
 let tip=null;
 function showTip(html,x,y){
  if(!tip){tip=document.createElement('div');tip.className='tip';document.body.appendChild(tip);}
  tip.innerHTML=html;tip.style.display='block';
  const w=tip.offsetWidth,h=tip.offsetHeight;
  let left=x+14,top=y+14;
  if(left+w>innerWidth-8)left=x-w-10;if(top+h>innerHeight-8)top=y-h-10;
  tip.style.left=left+'px';tip.style.top=top+'px';
 }
 function hideTip(){if(tip)tip.style.display='none';}
 const TIPZONE='[data-tip],.tipzone';
 if(typeof addEventListener==='function'){
  addEventListener('mousemove',e=>{if(tip&&tip.style.display!=='none'&&!(e.target.closest&&e.target.closest(TIPZONE)))hideTip();},{capture:true,passive:true});
  for(const ev of ['pointerdown','keydown','wheel','scroll'])addEventListener(ev,hideTip,{capture:true,passive:true});
  document.documentElement.addEventListener('mouseleave',hideTip);
 }
 function attachTips(root){
  root.querySelectorAll('[data-tip]').forEach(el=>{
   el.addEventListener('mousemove',e=>showTip(el.dataset.tip,e.clientX,e.clientY));
   el.addEventListener('mouseleave',hideTip);
  });
 }
 // ---- the loading indicator, one on every page, for any wait the reader would otherwise have to guess at. It fades in after a moment, so that
 // quick work shows nothing, and both of its animations run off the page's thread, so it keeps turning while a rebuild holds the page
 const jobs=[];let busyNode=null;
 function nextPaint(){return new Promise(done=>{const fallback=setTimeout(done,250);requestAnimationFrame(()=>setTimeout(()=>{clearTimeout(fallback);done();},0));});}   // the timer serves a hidden tab, which paints nothing
 function showBusy(){
  if(!busyNode){busyNode=document.createElement('div');busyNode.className='busy';busyNode.setAttribute('role','status');busyNode.innerHTML='<i aria-hidden="true"></i><span></span>';document.body.append(busyNode);}
  const job=jobs[jobs.length-1];busyNode.classList.toggle('on',!!job);busyNode.lastChild.textContent=job?job.label:'';
 }
 function busyStart(label){
  const job={label,set(text){job.label=text;showBusy();},end(){const i=jobs.indexOf(job);if(i>=0){jobs.splice(i,1);showBusy();}}};
  jobs.push(job);showBusy();return job;
 }
 // a function runs once the indicator is on screen, because work that blocks the page would otherwise keep it from ever being painted; a promise
 // is simply watched. The indicator stays until the result has been painted
 async function busy(label,work){
  const job=busyStart(label);
  try{if(typeof work==='function'){await nextPaint();return await work();}return await work;}
  finally{await nextPaint();job.end();}
 }
 function hash(){const o={};for(const [k,v] of new URLSearchParams(location.hash.slice(1)))o[k]=v;return o;}
 function setHash(o){const p=new URLSearchParams();for(const k of Object.keys(o))if(o[k]!=null&&o[k]!=='')p.set(k,o[k]);history.replaceState(null,'',(p.toString()?'#'+p.toString():location.pathname));}
 function error(el,e){el.innerHTML=`<div class="error">${esc(e.message||e)}\n\nThe pages read their data with fetch(); open the viewer through a web server (for example: python -m http.server in the viewer folder), not from a file:// address, and build the data first (vmsspatial viewer-data).</div>`;console.error(e);}
 // the 501-colour diversity scale (warm = low, teal = high) for a bundle that carries no palette
 function defaultPalette(){
  const stops=['#a83c35','#d56b43','#e9aa6c','#ead6a1','#a1c5ad','#4e9c92','#185965'].map(h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16)));
  return Array.from({length:501},(_,k)=>{
   const t=k/500*(stops.length-1),i=Math.min(stops.length-2,Math.floor(t)),f=t-i;
   return '#'+stops[i].map((c,j)=>Math.round(c+(stops[i+1][j]-c)*f).toString(16).padStart(2,'0')).join('');
  });
 }
 return {$,esc,finite,fmt,int,pct,signed,load,readGz,setBase,dataUrl,units,showTip,hideTip,attachTips,busy,busyStart,nextPaint,hash,setHash,error,defaultPalette};
})();
if(typeof module!=='undefined')module.exports=SG;
