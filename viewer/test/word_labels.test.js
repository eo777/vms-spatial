'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const W=require('../js/word_labels.js');
const near=(a,b,eps=1e-9)=>assert.ok(Math.abs(a-b)<=eps,`${a} is not ${b}`);

/* the axis-aligned box of a word of length L and thickness T, centred at (x, y), running in direction `angle` */
function box(x,y,L,T,angle){
  const c=Math.abs(Math.cos(angle*Math.PI/180)),s=Math.abs(Math.sin(angle*Math.PI/180)),w=L*c+T*s,h=L*s+T*c;
  return [x-w/2,y-h/2,x+w/2,y+h/2];
}
/* n identical words evenly round a ring of radius R about the origin, each with its bottom towards the centre */
function ring(n,R,L,T,text='chedyl'){
  return Array.from({length:n},(_,i)=>{
    const t=2*Math.PI*i/n,x=R*Math.sin(t),y=-R*Math.cos(t),angle=W.ringAngle(x,y,0,0);
    return {rect:box(x,y,L,T,angle),text,angle};
  });
}

test('a word at each clock position has its bottom towards the centre',()=>{
  near(W.ringAngle(0,-100,0,0),0);near(W.ringAngle(100,0,0,0),90);near(W.ringAngle(0,100,0,0),180);near(W.ringAngle(-100,0,0,0),-90);
  near(W.ringAngle(510,200,500,300),W.ringAngle(10,-100,0,0));            // the centre is wherever the wheel is
});
test('upright turns a direction half way round only where it would read upside down',()=>{
  near(W.upright(0),0);near(W.upright(45),45);near(W.upright(90),90);near(W.upright(135),-45);near(W.upright(-135),45);near(W.upright(180),0);near(W.upright(-90),90);
});
test('angleOf reads each kind of line from its orientation record',()=>{
  near(W.angleOf({kind:'circular',word_angles:[12.5,20]},1),20);
  assert.equal(W.angleOf({kind:'circular'},0),null);                      // a ring that failed the wheel screens
  near(W.angleOf({kind:'rotated',angle_deg:-65},3),-65);
  near(W.angleOf({kind:'radial',angle_deg:40,word_angles:[120]},0),40);   // the chord wins over the ray
  near(W.angleOf({kind:'radial',word_angles:[135]},0),-45);               // one word: not upside down
  assert.equal(W.angleOf({kind:'radial'},0),null);
  near(W.angleOf({kind:'label',angle_deg:90},0),90);near(W.angleOf({kind:'label',angle_deg:4},0),0);
  near(W.angleOf({kind:'horizontal',angle_deg:1.2},0),0);near(W.angleOf({kind:'unknown'},0),0);near(W.angleOf(undefined,0),0);
});
test('the length along the writing is recovered from an axis-aligned box at any angle',()=>{
  for(const a of [0,20,45,70,90,-90,135,180])near(W.alongLength(box(0,0,80,20,a),a,20),80);
  assert.equal(W.alongLength([0,0,20,90],null,10),90);
});
test('thickness is solved from the words away from 45 degrees',()=>{near(W.thickness(ring(36,400,80,20)),20);});
test('words at 3 and 9 o\'clock are as large as words at 12 o\'clock',()=>{
  const out=W.layout(ring(12,400,80,20),'ring'),want=80/(W.ADVANCE*6);
  for(const f of out)near(f.size,want);                                   // 22.2, where fitting the box width gave 5.3 at 3 o'clock
  near(out[3].angle,90);near(out[9].angle,-90);near(out[6].angle,180);near(out[0].angle,0);
  near(out[3].x,400);near(out[3].y,0);                                    // centred on the box
});
test('level mode keeps the size and turns every word upright',()=>{
  const items=ring(12,400,80,20),a=W.layout(items,'ring'),b=W.layout(items,'level');
  b.forEach((f,i)=>{near(f.angle,0);near(f.size,a[i].size);near(f.x,a[i].x);near(f.y,a[i].y);});
});
test('a word with no known direction is drawn level, sized by the longer side of its box',()=>{
  const [f]=W.layout([{rect:[0,0,20,90],text:'chedyl',angle:null}],'ring');
  near(f.angle,0);near(f.size,90/(W.ADVANCE*6));
});
test('a word that would overrun its box takes a smaller size than the group',()=>{
  const items=ring(12,400,80,20);items[0].text='chedylchedylchedyl';
  const out=W.layout(items,'ring');
  assert.ok(out[0].size<out[1].size);near(out[0].size,1.25*80/(W.ADVANCE*18));
});
test('an empty group lays out to nothing',()=>{assert.deepEqual(W.layout([],'ring'),[]);});
