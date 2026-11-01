'use strict';
// The loading indicator: painted before blocking work starts, up until the result is painted, and never left behind.
const test=require('node:test'),assert=require('node:assert/strict');
const log=[];
const node={className:'',classList:{on:false,toggle(k,v){this.on=v;}},setAttribute(){},innerHTML:'',lastChild:{textContent:''}};
globalThis.document={createElement:()=>node,body:{append(){}}};
globalThis.requestAnimationFrame=f=>{log.push('paint');setTimeout(f,0);};
const SG=require('../common.js');
const shown=()=>node.classList.on?node.lastChild.textContent:null,tick=()=>new Promise(r=>setTimeout(r,20));

test('the indicator is painted before blocking work, and stays until the result is painted',async()=>{
 log.length=0;
 const result=await SG.busy('Arranging the pages…',()=>{log.push('work');assert.equal(shown(),'Arranging the pages…');return 7;});
 assert.equal(result,7);assert.deepEqual(log,['paint','work','paint']);assert.equal(shown(),null);
});

test('a promise is watched, and work that fails ends the job and still rejects',async()=>{
 let open;const p=new Promise(r=>{open=r;}),b=SG.busy('Loading the wheels…',p);
 assert.equal(shown(),'Loading the wheels…');open('w');assert.equal(await b,'w');assert.equal(shown(),null);
 await assert.rejects(SG.busy('Failing…',()=>{throw Error('no');}),/no/);assert.equal(shown(),null);
 await assert.rejects(SG.busy('Failing…',Promise.reject(Error('no'))),/no/);assert.equal(shown(),null);
});

test('overlapping jobs show the latest, and the indicator stays until the last one ends',async()=>{
 const a=SG.busyStart('Loading the manuscript…'),b=SG.busyStart('Updating colors…');
 assert.equal(shown(),'Updating colors…');b.set('Calculating · 40%');assert.equal(shown(),'Calculating · 40%');
 b.end();assert.equal(shown(),'Loading the manuscript…');b.end();assert.equal(shown(),'Loading the manuscript…','a second end does nothing');
 a.end();assert.equal(shown(),null);
});

test('a tab that paints nothing still gets its work done',async()=>{
 const raf=globalThis.requestAnimationFrame;globalThis.requestAnimationFrame=()=>{};
 try{assert.equal(await SG.busy('Hidden…',()=>3),3);assert.equal(shown(),null);}finally{globalThis.requestAnimationFrame=raf;}
 await tick();
});
