'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const Z=require('../../js/zoom_math.js');
const full={x:0,y:0,w:1000,h:1500};
const near=(a,b,eps=1e-9)=>assert.ok(Math.abs(a-b)<eps,`${a} vs ${b}`);

test('parse and format round-trip, bad input rejected',()=>{
 assert.deepEqual(Z.parse('10,20,300,450'),{x:10,y:20,w:300,h:450});
 assert.equal(Z.parse('10,20,300'),null);assert.equal(Z.parse('a,b,c,d'),null);assert.equal(Z.parse('0,0,-5,5'),null);assert.equal(Z.parse(''),null);
 assert.deepEqual(Z.parse(Z.format({x:1.234,y:2.345,w:3.456,h:4.567})),{x:1.23,y:2.35,w:3.46,h:4.57});
});
test('zoomAt keeps the point under the cursor fixed and clamps to the page',()=>{
 const p={x:400,y:600};
 const v=Z.zoomAt(full,full,2,p);
 near(v.w,500);near(v.h,750);
 // the fraction of the view at the point is unchanged: (400-0)/1000 = 0.4 -> (400-v.x)/500 = 0.4
 near((p.x-v.x)/v.w,0.4);near((p.y-v.y)/v.h,0.4);
 const out=Z.zoomAt(full,full,0.5,p);                      // zooming out beyond the page gives the page
 assert.ok(Z.isFull(out,full));
 const edge=Z.zoomAt(full,full,4,{x:5,y:5});                // near the corner: the point stays fixed and the view stays inside the page
 near(edge.x,3.75);near(edge.y,3.75);near(edge.w,250);
 const outside=Z.zoomAt({x:900,y:1400,w:200,h:300},full,0.5,{x:1000,y:1500});   // zooming out at the corner: pushed back inside
 near(outside.x,600);near(outside.y,900);near(outside.w,400);
 const deep=Z.zoomAt(full,full,1000,p);                     // magnification is capped
 near(Z.scale(deep,full),Z.MAX_SCALE);
});
test('pan moves the page with the pointer and stops at the edges',()=>{
 const v={x:200,y:300,w:500,h:750};
 const moved=Z.pan(v,full,-100,0,1000,1500);                // dragging 100 screen px left on a 1000 px wide element = 50 page px
 near(moved.x,250);near(moved.y,300);
 const stopped=Z.pan(v,full,-10000,-10000,1000,1500);
 near(stopped.x,500);near(stopped.y,750);
 const back=Z.pan(v,full,10000,10000,1000,1500);
 near(back.x,0);near(back.y,0);
});
test('frame encloses the boxes with a margin at the page aspect',()=>{
 const boxes=[[100,100,200,130],[300,105,400,135],null,[0,0,0,0]];
 const v=Z.frame(boxes,full);
 assert.ok(v.x<=100&&v.y<=100&&v.x+v.w>=400&&v.y+v.h>=135);
 near(v.w/v.h,full.w/full.h);
 assert.ok(v.w<full.w);
 assert.ok(Z.isFull(Z.frame([],full),full));
 const tall=Z.frame([[500,0,520,1500]],full);               // a column as tall as the page cannot be magnified
 assert.ok(Z.isFull(tall,full));
});
test('toPage inverts the screen mapping',()=>{
 const v={x:100,y:200,w:500,h:750};
 const p=Z.toPage(v,250,375,1000,1500);
 near(p.x,225);near(p.y,387.5);
});
