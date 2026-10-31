'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const H=require('../../js/heatmap_math.js'),C=require('../../js/copy_math.js'),DATA=path.resolve(__dirname,'../data');
const have=fs.existsSync(path.join(DATA,'manuscript/words.json.gz'));
const data=have?JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,'manuscript/words.json.gz')))):null;

test('all window directions and sizes match independent counts, including stream edges',()=>{
 const words=['a','a','b','c','d','a','b','b','e','f','f'];
 for(const width of [2,3,4,5,10,11,20])for(const direction of ['backward','forward','centered']){
  const series=H.series(words,width,direction);
  for(let i=0;i<words.length;i++){
   const before=direction==='backward'?width-1:direction==='forward'?0:Math.floor((width-1)/2);
   const first=i-before,last=first+width;
   const expected=words.slice(Math.max(0,first),Math.min(words.length,last));
   const full=first>=0&&last<=words.length,w=H.windowAt(words,i,width,direction);
   assert.deepEqual(w.words,expected);assert.equal(w.unique,new Set(expected).size);
   assert.equal(w.score,full?new Set(expected).size/width:null);
   assert.equal(series.repeated[i],expected.filter(word=>word===words[i]).length>1?1:0);
   if(full)assert.equal(series.scores[i],w.score);else assert.ok(Number.isNaN(series.scores[i]));
  }
 }
 assert.deepEqual(H.bounds(100,100,'centered',500),{start:51,end:151,full:true});
});
test('word impact counts containing windows with another copy; step change splits arriving and leaving',()=>{
 const words=['a','b','a','c','a','b'],I=H.wordImpact(words,3);
 for(let i=0;i<words.length;i++){
  const wins=[];for(let s=Math.max(0,i-2);s<=Math.min(i,words.length-3);s++)wins.push(words.slice(s,s+3));
  assert.equal(I.windows[i],wins.length);assert.equal(I.affected[i],wins.filter(w=>w.filter(x=>x===words[i]).length>1).length);
 }
 // 'c' arrives at 3: a new type enters; the outgoing 'a' (position 0) still has a copy at 2 inside the window, so no type leaves
 assert.equal(I.enter[3],1);assert.equal(I.leave[3],0);assert.ok(Math.abs(I.change[3]-1/3)<1e-12);
 // 'a' arrives at 4: its spelling is already in the window (enter 0); the outgoing 'b' (position 1) has no copy in 2..4, so a type leaves
 assert.equal(I.enter[4],0);assert.equal(I.leave[4],1);assert.ok(Math.abs(I.change[4]+1/3)<1e-12);
});
test('contributions add up: shares to the distinct count, costs to the repeats',()=>{
 const w=H.windowAt(['a','b','a','c','a','b'],5,6,'backward'),K=H.contributions(w);
 assert.deepEqual(K.share,[1/3,1/2,1/3,1,1/3,1/2]);assert.equal(K.lost,3);
 assert.deepEqual(K.spellings.map(s=>[s.word,s.count,s.lost]),[['a',3,2],['b',2,1]]);
});
test('on the manuscript, bifolium means over complete windows and brute-force rolling scores agree',{skip:!have},()=>{
 const s=H.series(data.words,100,'backward');
 for(let i=99;i<data.words.length;i+=211)assert.equal(s.scores[i],new Set(data.words.slice(i-99,i+1)).size/100);
 const start=data.lines.find(l=>l.bifolium==='M:75-84').start,end=data.lines.filter(l=>l.bifolium==='M:75-84').at(-1).end;
 const mean=H.meanWithin(s.scores,start,end,100,'backward');
 let sum=0,n=0;for(let i=start+99;i<end;i++){sum+=s.scores[i];n++;}
 assert.ok(Math.abs(mean-sum/n)<1e-12);
});
test('glyph-unit edit distance and candidate counts',()=>{
 const d={words:['qokeedy','qokedy','qokeedy','okeedy'],components:{qokeedy:['q','o','k','ee','d','y'],qokedy:['q','o','k','e','d','y'],okeedy:['o','k','ee','d','y']},geometry:[],lines:[]};
 const c=C.prepare(d),m=C.measure(c,2,{indices:[0,1],weights:[1,1]},true);
 assert.equal(m.minedit,0);assert.equal(m.nearestTypes,1);assert.equal(m.candidateTypes1,2);
 assert.equal(C.distance(['a','b','c'],['a','c']),1);
});

test('measures a bundle brings: colour domains and fractions',()=>{
 const d=H.measureDomain([0,1,2,3,4,5,6,7,8,9,10,null,NaN],'sequential');
 assert.ok(d[0]>=0&&d[1]<=10&&d[1]>d[0]);
 assert.equal(H.measureFraction(d[0],d,'sequential'),0);assert.equal(H.measureFraction(d[1],d,'sequential'),1);
 assert.equal(H.measureFraction(-5,d,'sequential'),0);
 const dv=H.measureDomain([-3,-1,0,2,8],'diverging');assert.equal(dv[0],-dv[1]);
 assert.equal(H.measureFraction(0,dv,'diverging'),0.5);assert.ok(Number.isNaN(H.measureFraction(NaN,dv,'diverging')));
 assert.deepEqual(H.measureDomain([1,2,3],'sequential',[0,10]),[0,10]);
 assert.equal(H.measureDomain([null,NaN],'sequential'),null);
 assert.deepEqual(H.measureDomain([2,2,2],'sequential'),[1,3]);
});
