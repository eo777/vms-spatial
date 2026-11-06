// The Light table's model: an open sheet on the parchment, the face underneath behind its partner on the same leaf, snapping, and the address.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),zlib=require('zlib');
const S=require('../js/sheet_math.js');
const DATA=path.join(__dirname,'..','data'),have=fs.existsSync(path.join(DATA,'compare/pages.json.gz'));
const compact=have?JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,'compare/pages.json.gz')))):null;
const unit=(x0,y0,x1,y1,dy=0)=>[0,0,0,x0,y0,x1,y1,dy,0,0,0],paper={mm:2,fold:100,top:50,fold_method:'measured',top_method:'measured',scale_method:'measured'};
const toy={a1r:{node:'A',slot:'Ar',side:'r',units:[unit(120,60,140,80,4)],paper},a1v:{node:'A',slot:'Av',side:'v',units:[unit(60,60,80,80)],paper},
 a2r:{node:'A',slot:'Br',side:'r',units:[unit(120,60,140,80)],paper},a2v:{node:'A',slot:'Bv',side:'v',units:[unit(60,60,80,80)],paper:{...paper,fold_method:'estimated'}},b:{node:'B',slot:'Ar',side:'r',units:[]}};

test('a page lies on its own leaf, from the fold and the top edge, and flat moves words up and down only',()=>{
 const m=S.sheet('A',toy,{coords:'recorded'}),leaf=f=>m.leaves.find(l=>l.folio===f);
 assert.deepEqual(leaf('a1r').leaf,[160,0,320,225]);assert.deepEqual(leaf('a1r').words[0].rect,[170,5,180,15],'a recto right of the fold');
 assert.deepEqual(leaf('a2v').leaf,[0,0,160,225]);assert.deepEqual(leaf('a2v').words[0].rect,[140,5,150,15],'a verso left of it');
 assert.deepEqual(leaf('a2v').estimated,['fold']);
 assert.deepEqual(S.sheet('A',toy).leaves.find(l=>l.folio==='a1r').words[0].rect,[170,3,180,13]);
 assert.deepEqual(S.sheet('B',{b:{...toy.b,paper:null}}).missing,['b'],'no paper record: not placed, and said');
});
test('a page\'s margins are the ends of its full paragraph rows, and its text angle follows the coordinates, mirrored behind with its words',()=>{
 // four paragraph lines, three boxes each: a paragraph of three lines, then one of a single line; the third line's boxes miss a token
 const line=(i,x0)=>[[3*i,3*i,i,x0,60+20*i,130,70+20*i,0,(x0+130)/2,70+20*i,0],[3*i+1,3*i+1,i,135,60+20*i,150,70+20*i,0,142.5,70+20*i,0],[3*i+2,3*i+2,i,155,60+20*i,170,70+20*i,0,162.5,70+20*i,0]];
 const page={node:'C',slot:'Ar',side:'r',paper,lines:[['1',1,'P','horizontal'],['2',0,'P','horizontal'],['3',0,'P','horizontal'],['4',1,'P','horizontal']],
  units:[...line(0,110),...line(1,112),...line(2,110),...line(3,110)],drift:{recorded:{angle:45,n:3},flat:{angle:5,n:3},lines:[[0,45,0,3,1,1],[1,45,0,3,1,1],[2,45,0,3,1,1],[3,45,0,3,1,0]]}};
 const tokens=new Map([['p|1',3],['p|2',3],['p|3',3],['p|4',3]]),m=S.sheet('C',{p:page},{coords:'recorded',tokens}),l=m.leaves[0];
 assert.deepEqual(l.margins.left,[{line:1,at:[166,20]},{line:2,at:[165,30]}],'left: the rows that are not their paragraph\'s first');
 assert.deepEqual(l.margins.right,[{line:0,at:[195,10]},{line:1,at:[195,20]}],'right: the rows that are not their paragraph\'s last');
 assert.deepEqual(S.sheet('C',{p:page},{tokens:new Map([...tokens,['p|2',4]])}).leaves[0].margins.left.map(r=>r.line),[2],'a row missing a token is not full');
 assert.deepEqual(S.sheet('C',{p:page}).leaves[0].margins,{left:[],right:[]},'no token counts, no margins');
 const near=(x,y,e=1e-9)=>assert.ok(Math.abs(x-y)<e,`${x} vs ${y}`);
 assert.equal(l.tilt.angle,45);assert.equal(l.tilt.flat,5);assert.equal(l.tilt.n,3);assert.equal(l.tilt.span,30,'as wide as the boxes of the lines it is measured on');
 near(l.tilt.at[0],(1276/9-100)/2+160);near(l.tilt.at[1],17.5);
 const out=S.view(m,'outer'),inn=S.view(m,'inner');
 // as written in recorded coordinates, after flattening in flat ones; through the text's centroid, as wide as the text, unless chosen otherwise
 let ln=S.tiltLine(out.leaves[0],{coords:'recorded'});assert.equal(ln.angle,45);near(ln.seen,45);
 near(Math.hypot(ln.ends[1][0]-ln.ends[0][0],ln.ends[1][1]-ln.ends[0][1]),30);near((ln.ends[0][0]+ln.ends[1][0])/2,l.tilt.at[0]);
 ln=S.tiltLine(out.leaves[0],{coords:'flat'});assert.equal(ln.angle,5);near(ln.seen,5);
 ln=S.tiltLine(inn.leaves[0],{coords:'recorded'});assert.equal(ln.angle,45,'behind, the label keeps the angle as written');near(ln.seen,-45);
 ln=S.tiltLine(out.leaves[0],{coords:'recorded',at:'page',length:'equal'});
 near((ln.ends[0][0]+ln.ends[1][0])/2,240);near((ln.ends[0][1]+ln.ends[1][1])/2,112.5);near(Math.hypot(ln.ends[1][0]-ln.ends[0][0],ln.ends[1][1]-ln.ends[0][1]),S.EQUAL_MM);
 assert.equal(S.tiltLine({...out.leaves[0],tilt:{...out.leaves[0].tilt,flat:null}},{coords:'flat'}),null,'no flat angle, no line in flat coordinates');
 // exaggerated: drawn that many times as steep, about the same point and as long, the true angle kept for the label; never past MAX_DRAWN
 const slope=e=>Math.atan2(e[1][1]-e[0][1],e[1][0]-e[0][0])*180/Math.PI;
 ln=S.tiltLine(out.leaves[0],{coords:'flat',scale:'10'});assert.equal(ln.angle,5);near(ln.seen,5);near(ln.drawn,50);near(slope(ln.ends),50);
 near((ln.ends[0][0]+ln.ends[1][0])/2,l.tilt.at[0]);near(Math.hypot(ln.ends[1][0]-ln.ends[0][0],ln.ends[1][1]-ln.ends[0][1]),30);
 near(S.tiltLine(inn.leaves[0],{coords:'flat',scale:'10'}).drawn,-50,1e-9);
 near(S.tiltLine(out.leaves[0],{coords:'recorded',scale:'10'}).drawn,S.MAX_DRAWN);near(S.tiltLine(out.leaves[0],{coords:'flat'}).drawn,5);
 assert.deepEqual(inn.leaves[0].margins.left.map(r=>r.at),[[154,20],[155,30]],'behind, mirrored about the fold: the left ends lie on the right');
 // the lines as plotted: through each word's baseline point, the ones the angle is measured on counted
 assert.deepEqual(l.lines.map(b=>[b.line,b.counted,b.points.length]),[[0,true,3],[1,true,3],[2,true,3],[3,false,3]]);
 assert.deepEqual(l.lines[0].points,[[170,10],[181.25,10],[191.25,10]]);assert.deepEqual(inn.leaves[0].lines[0].points[0],[150,10],'behind, mirrored');
 assert.deepEqual(S.baselines({...page,units:page.units.map(u=>[...u.slice(0,10),4])},()=>0),[],'words anchored at their boxes\' centres make no line');
 assert.equal(S.tilt({...page,drift:{recorded:{angle:null,n:0},lines:[]}},()=>0),null,'no recorded angle, none drawn');
});
test('a piece can show both its faces side by side, nothing behind either; a face can be left out of a view',()=>{
 const m=S.sheet('A',toy,{coords:'recorded'}),p=S.pair(m,{node:'A',part:'',up:'outer',show:S.ALL}),shown=v=>v.leaves.filter(l=>l.shown).map(l=>l.folio).sort();
 assert.deepEqual(shown(p.main),['a1r','a2v'],'the face up, as read');assert.deepEqual(shown(p.twin),['a1v','a2r'],'its other face, beside it');
 assert.ok(p.main.leaves.every(l=>l.shown===l.front)&&p.twin.leaves.every(l=>l.shown===l.front),'nothing behind either');
 assert.equal(p.dx,2*S.LEAF[0]+S.GAP,'a gap to the right of the sheet');
 assert.deepEqual(shown(S.view(m,'outer',S.ALL,'',{up:false})),['a1v','a2r'],'the face up left out');
 assert.deepEqual(shown(S.view(m,'outer',S.ALL,'',{behind:false})),['a1r','a2v'],'the face underneath left out');
});
test('turning the sheet over puts each page behind its partner on the same leaf, seen through',()=>{
 const m=S.sheet('A',toy,{coords:'recorded'});
 const out=S.view(m,'outer'),inn=S.view(m,'inner'),at=(v,f)=>v.leaves.find(l=>l.folio===f);
 assert.equal(at(out,'a1r').front,true);assert.equal(at(out,'a1v').front,false);
 assert.deepEqual(at(out,'a1v').leaf,at(out,'a1r').leaf,'leaf A: f1v behind f1r');assert.deepEqual(at(out,'a2r').leaf,at(out,'a2v').leaf,'leaf B');
 assert.deepEqual(at(out,'a1v').words[0].rect,[170,5,180,15],'the verso mirrored about the fold: 10 to 20 mm left of it as read, so 10 to 20 mm right of it behind');
 assert.deepEqual(at(inn,'a1v').words[0].rect,[140,5,150,15],'and as read with its own face up');
 assert.deepEqual(out.box,[0,0,320,225]);
 const shown=S.view(m,'outer',S.BIT.Ar);assert.deepEqual(shown.leaves.filter(l=>l.shown).map(l=>l.folio),['a1r']);
});
test('a moved piece shows which fold or edge of another it lines up with, and how far off, but is never moved',()=>{
 const m=S.sheet('A',toy,{coords:'recorded'}),L=S.lines(S.view(m)),others=[S.placed({x:100,y:50},L)],near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} vs ${b}`);
 assert.deepEqual(L,{xs:[160,0,320],ys:[0,225]},'the fold first, then the outer edges');
 let g=S.align(100.6,50,L,others);assert.deepEqual(g.map(x=>[x.axis,x.at]),[['x',260],['y',50]],'fold on fold, top on top');near(g[0].off,-0.6);assert.equal(g[1].off,0,'level: met');
 assert.equal(S.align(260.5,90,L,others)[0].at,420,'fold on the outer edge');assert.equal(S.align(419.5,90,L,others)[0].at,420,'side by side');
 assert.deepEqual(S.align(102,90,L,others),[],'2 mm off: no guide, as the tolerance is 1 mm');
 assert.equal(S.align(100,275.4,L,others)[1].at,275,'one above the other');
 assert.ok(Math.abs(S.align(100.04,50,L,others)[0].off)<S.ALIGNED,'within 0.05 mm counts as met');
 // a leaf lines up by its own edges: leaf A's fold edge on the other sheet's outer edge
 const leaf=S.lines(S.view(m,'outer',S.ALL,'A'));assert.deepEqual(leaf.xs,[160,320]);
 assert.equal(S.align(260.3,50,leaf,others)[0].at,420);
});
test('a sheet divides into its two leaves where it lay, each turns over where it lies, and they join again',()=>{
 const m=S.sheet('A',toy,{coords:'recorded'}),boxOf=p=>S.view(m,p.up,S.ALL,p.part).box,at=(v,f)=>v.leaves.find(l=>l.folio===f);
 const a=S.view(m,'outer',S.ALL,'A');
 assert.deepEqual(a.leaves.map(l=>[l.folio,l.front]),[['a1r',true],['a1v',false]]);assert.deepEqual(a.box,[160,0,320,225]);
 assert.deepEqual(S.view(m,'outer',S.ALL,'B').leaves.map(l=>l.folio),['a2v','a2r']);
 const whole=S.view(m,'outer'),[A,B]=S.divide({node:'A',part:'',copy:1,x:10,y:5,up:'outer',show:S.ALL,colour:2});
 assert.deepEqual([A.part,B.part,A.x,B.x,A.colour],['A','B',10,10,2],'both leaves start where the sheet lay, in its colour');
 for(const p of [A,B])for(const l of S.view(m,p.up,p.show,p.part).leaves)assert.deepEqual(l.words,at(whole,l.folio).words,l.folio);
 const t=S.turn(A,boxOf);assert.equal(t.up,'inner');assert.equal(t.x,170);
 assert.deepEqual(boxOf(t).map((v,i)=>v+(i%2?t.y:t.x)),boxOf(A).map((v,i)=>v+(i%2?A.y:A.x)),'a leaf turns over where it lies');
 assert.equal(at(S.view(m,t.up,t.show,t.part),'a1v').front,true,'its verso now up');
 assert.equal(S.turn({node:'A',part:'',x:10,up:'outer'},boxOf).x,10,'a whole sheet turns about its fold');
 const x={node:'X',part:'',copy:1},y={node:'Y',part:'',copy:1};
 const joined=S.join(t,[x,t,y,{...B,show:S.BIT.Bv}]);assert.deepEqual(joined.map(p=>S.idOf(p)),['X','A','Y']);
 assert.deepEqual([joined[1].x,joined[1].up,joined[1].show],[170,'inner',S.ALL],'whole again where the joined leaf lies, every page it showed');
});
test('the same bifolium or leaf goes on the table more than once, each copy whole or divided on its own',()=>{
 const nodes=['A:1-8','A:2-7'];
 assert.equal(S.nextCopy([{node:'A:1-8',copy:1},{node:'A:1-8',part:'A',copy:3}],'A:1-8'),4);assert.equal(S.nextCopy([],'A:1-8'),1);
 const sheets=S.decodeSheets('A:1-8@0,0,o,f,1|A:1-8~2@5,5,i,f,2|A:1-8~3/A@1,1,o,3,3|A:1-8/A~3@1,1,o,3,3|A:1-8/A~4@1,1,o,3,3|A:1-8/B~4@2,2,o,3,3|A:1-8~2/A@0,0,o,f,4|A:1-8/A~4@9,9,o,f,4',nodes);
 assert.deepEqual(sheets.map(S.idOf),['A:1-8','A:1-8~2','A:1-8/A~3','A:1-8/A~4','A:1-8/B~4'],'a copy whole or as its leaves, once each; a malformed id (copy before leaf) dropped');
 assert.equal(S.encodeSheets(sheets),'A:1-8@0,0,o,f,1|A:1-8~2@5,5,i,f,2|A:1-8/A~3@1,1,o,3,3|A:1-8/A~4@1,1,o,3,3|A:1-8/B~4@2,2,o,3,3');
 assert.deepEqual(S.join(sheets[3],sheets).map(S.idOf),['A:1-8','A:1-8~2','A:1-8/A~3','A:1-8~4'],'joining one copy leaves the others alone');
});
test('the wheel zooms to any value in range, and the address keeps it',()=>{
 assert.equal(S.zoomOf('2.345'),'2.35');assert.equal(S.zoomOf('0.3'),'0.3');assert.equal(S.zoomOf('9'),'1.5');assert.equal(S.zoomOf('abc'),'1.5');assert.equal(S.zoomOf(undefined),'1.5');
 assert.deepEqual(S.serialize(S.parse({zoom:'2.35'},['A']),['A']),{zoom:'2.35'});
});
test('stack nests the sheets on the first one\'s fold and top; spread lays them in rows without overlap',()=>{
 const sheets=[{node:'A',x:5,y:7},{node:'B',x:400,y:300}];
 assert.deepEqual(S.stack(sheets).map(s=>[s.x,s.y]),[[5,7],[5,7]]);
 const boxes=[[0,0,320,225],[-160,0,320,225]],out=S.spread(sheets,900,boxes);
 assert.deepEqual(out.map(s=>[s.x,s.y]),[[20,20],[520,20]],'the second, wider sheet starts a leaf to the right of its own origin');
 assert.deepEqual(S.spread(sheets,500,boxes).map(s=>[s.x,s.y]),[[20,20],[180,265]],'no room: a new row');
});
test('the address round-trips and drops what it cannot place',()=>{
 const nodes=['A:1-8','A:2-7','B:9-16'],s={sheets:[{node:'A:2-7',x:12.34,y:-3,up:'inner',show:5,colour:3},{node:'B:9-16',x:0,y:0,up:'outer',show:15,colour:0}],coords:'recorded',zoom:'3',guides:false,colouring:'face',words:true,wdir:'level'};
 const h=S.serialize(s,nodes);assert.equal(h.sheets,'A:2-7@12.3,-3,i,5,3|B:9-16@0,0,o,f,0');assert.equal(h.wdir,'level');
 assert.deepEqual(S.serialize(S.parse(h,nodes),nodes),h);
 assert.deepEqual(S.serialize(S.parse({},nodes),nodes),{},'the defaults leave the address empty');
 assert.deepEqual(S.parse({},nodes).sheets.map(x=>x.node),['A:1-8','A:2-7']);
 // a colour of the viewer's own, the faces' colours and snapping: kept when chosen, and left out of the address otherwise
 const own={...s,sheets:[{...s.sheets[0],colour:'c0ffee'}],faceColours:[4,'1a2b3c'],snap:true},ho=S.serialize(own,nodes);
 assert.equal(ho.sheets,'A:2-7@12.3,-3,i,5,c0ffee');assert.equal(ho.fc,'4,1a2b3c');assert.equal(ho.snap,'1');
 assert.deepEqual(S.serialize(S.parse(ho,nodes),nodes),ho);assert.equal(S.parse(ho,nodes).sheets[0].colour,'c0ffee');
 assert.deepEqual(S.parse({},nodes).faceColours,[1,2]);assert.equal(S.parse({},nodes).snap,false,'snapping is off unless chosen');
 const marked=S.serialize({...s,margins:true,angle:true},nodes);assert.equal(marked.margins,'1');assert.equal(marked.angle,'1');
 assert.deepEqual(S.serialize(S.parse(marked,nodes),nodes),marked);assert.equal(S.parse({},nodes).margins,false,'margins and angles are drawn when chosen');assert.equal(S.parse({},nodes).angle,false);
 // a piece's opacity after its colour, in percent, only when it is not 1; the faces drawn, the dimming and the opacities of the drawing's parts
 const faint={...s,sheets:[{...s.sheets[0],opacity:.4},s.sheets[1]],faceUp:false,dim:true,opacity:{boxes:.5,under:1,margins:1,angles:.6,lines:.3,paper:.2}},hf=S.serialize(faint,nodes);
 assert.equal(hf.sheets,'A:2-7@12.3,-3,i,5,3,40|B:9-16@0,0,o,f,0');assert.equal(hf.faceup,'0');assert.equal(hf.under,undefined);assert.equal(hf.dim,'1');assert.equal(hf.op,'50,100,100,60,30,20');
 const pf=S.parse(hf,nodes);assert.deepEqual(S.serialize(pf,nodes),hf);assert.equal(pf.sheets[0].opacity,.4);assert.equal(pf.sheets[1].opacity,1);
 assert.deepEqual([pf.faceUp,pf.underneath,pf.dim],[false,true,true]);assert.deepEqual(pf.opacity,{boxes:.5,under:1,margins:1,angles:.6,lines:.3,paper:.2});
 assert.deepEqual(S.parse({op:'45,100,80,25'},nodes).opacity,{boxes:.45,under:1,margins:.8,angles:.8,lines:1,paper:.25},'an older address\'s four: margins and angles were one');
 const plain=S.parse({},nodes);assert.deepEqual([plain.faceUp,plain.underneath,plain.dim],[true,true,false],'both faces drawn, nothing dimmed, unless chosen');
 assert.deepEqual(plain.opacity,{boxes:1,under:1,margins:1,angles:1,lines:1,paper:1});assert.deepEqual(S.parse({op:'50,x,1,2'},nodes).opacity,plain.opacity,'a broken opacity list falls back');
 assert.equal(S.parse({sheets:'A:1-8@0,0,o,f,1,5'},nodes).sheets[0].opacity,.1,'an opacity is at least 10 percent');
 // a piece shown with both its faces; where the angle lines are drawn and how long; the pieces' labels
 const both=S.serialize({...s,sheets:[{...s.sheets[0],twin:true},{...s.sheets[1],opacity:.5,twin:true}],angleAt:'page',angleLength:'equal',sheetLabel:'above',pageLabel:'above',copyNumbers:false,lines:true},nodes);
 assert.equal(both.sheets,'A:2-7@12.3,-3,i,5,3,t|B:9-16@0,0,o,f,0,50,t');assert.equal(both.angleat,'page');assert.equal(both.anglelen,'equal');
 assert.equal(both.sheetlabel,'above');assert.equal(both.pagelabels,'above');assert.equal(both.copies,'0');assert.equal(both.lines,'1');assert.equal(both.labels,undefined);
 const pb=S.parse(both,nodes);assert.deepEqual(S.serialize(pb,nodes),both);assert.deepEqual(pb.sheets.map(x=>x.twin),[true,true]);assert.equal(pb.sheets[1].opacity,.5);
 assert.deepEqual([plain.angleAt,plain.angleLength,plain.sheetLabel,plain.pageLabel,plain.copyNumbers,plain.lines,plain.sheets[0].twin],['text','text','inside','corner',true,false,false],'through the centroid, as wide as the text, named on the sheet and the leaves with copy numbers, no lines, one face, unless chosen');
 const old=S.parse({labels:'0'},nodes);assert.deepEqual([old.sheetLabel,old.pageLabel],['off','off'],'labels=0 still turns both off');assert.equal(S.parse({pagelabels:'0'},nodes).pageLabel,'off');
 assert.deepEqual([S.parse({labels:'0',sheetlabel:'above'},nodes).sheetLabel,S.parse({sheetlabel:'sideways'},nodes).sheetLabel],['above','inside']);
 assert.equal(S.serialize({...s,angleScale:'20'},nodes).anglex,'20');assert.equal(S.parse({anglex:'20'},nodes).angleScale,'20');
 assert.equal(plain.angleScale,'1','the true angle unless chosen');assert.equal(plain.angleValues,true);
 assert.equal(S.serialize({...s,angleValues:false},nodes).anglev,'0');assert.equal(S.parse({anglev:'0'},nodes).angleValues,false);assert.equal(S.parse({anglex:'7'},nodes).angleScale,'1','only the factors offered');
 assert.deepEqual(S.parse({fc:'9,zz'},nodes).faceColours,[1,2],'a broken face colour falls back');
 assert.equal(S.parse({sheets:'A:1-8@0,0,o,f,C0FFEE'},nodes).sheets[0].colour,'c0ffee');
 assert.deepEqual(S.snapTo(10,20,[{axis:'x',at:0,off:-0.4},{axis:'y',at:0,off:0.7}]),{x:9.6,y:20.7});
 assert.deepEqual(S.parse({sheets:'Z:1-2@0,0,o,f,1|A:1-8@1,2,x,f,1|A:1-8@1,2,o,g,1|A:1-8@1,2,o,f,1|A:1-8@3,3,o,f,2'},nodes).sheets.map(x=>[x.node,x.x]),[['A:1-8',1]],'unknown, broken and repeated sheets dropped');
 assert.deepEqual(S.parse({sheets:''},nodes).sheets,[],'an empty table stays empty');
 assert.equal(S.parse({coords:'warped',zoom:'9'},nodes).zoom,'1.5');assert.equal(S.parse({wdir:'sideways'},nodes).wdir,'ring','words follow the writing by default');
 assert.equal(S.nextColour([{colour:1},{colour:3}]),2);assert.equal(S.nextColour([1,2,3,4,5,6].map(colour=>({colour}))),0,'a seventh sheet is drawn in ink');
});
test('the menus offer what the address accepts',()=>{
 const html=fs.readFileSync(path.join(__dirname,'..','lighttable.html'),'utf8'),menu=id=>[...html.match(new RegExp(`<select id="${id}"[^>]*>(.*?)</select>`))[1].matchAll(/value="([\w.]+)"/g)].map(m=>m[1]);
 assert.deepEqual(menu('zoom').slice().sort(),S.ZOOMS.slice().sort());assert.deepEqual(menu('coords'),S.COORDS);assert.deepEqual(menu('colour'),S.COLOURINGS);assert.deepEqual(menu('angleAt'),S.ANGLE_AT);assert.deepEqual(menu('angleLength'),S.ANGLE_LENGTHS);assert.deepEqual(menu('angleScale'),S.ANGLE_SCALES);assert.deepEqual(menu('sheetLabel'),S.SHEET_LABELS);assert.deepEqual(menu('pageLabel'),S.PAGE_LABELS);
 for(const z of S.ZOOMS)assert.equal(S.zoomOf(z),z,'every preset is in the wheel\'s range');
 assert.match(fs.readFileSync(path.join(__dirname,'..','site_nav.js'),'utf8'),/lighttable\.html','Light table'/);
});
test('on the real data every measured page\'s text lies on its own leaf, with either face up',{skip:!have},()=>{
 const nodes=[...new Set(Object.values(compact.pages).map(p=>p.node))];let checked=0;
 for(const node of nodes){
  const m=S.sheet(node,compact.pages,{sheets:compact.sheets});
  for(const up of ['outer','inner']){
   for(const l of S.view(m,up).leaves){
    if(l.k||l.panel||l.estimated.includes('fold')||l.estimated.includes('top'))continue;
    for(const w of l.words){const r=w.rect;assert.ok(r[0]>=l.leaf[0]-2&&r[2]<=l.leaf[2]+2&&r[1]>=-2&&r[3]<=S.LEAF[1]+2,`${l.folio} ${up}: a word off its leaf ${r.map(v=>v.toFixed(1))}`);checked++;}
   }
  }
 }
 assert.ok(checked>60000,`${checked} words checked`);
 const a=S.view(S.sheet('A:1-8',compact.pages),'outer');
 assert.deepEqual(a.leaves.map(l=>[l.folio,l.front]).sort(),[['f1r',true],['f1v',false],['f8r',false],['f8v',true]]);
});
test('on the real data the margins lie on their own leaves, and each text angle is the page\'s recorded one, mirrored behind',{skip:!have},()=>{
 const index=JSON.parse(fs.readFileSync(path.join(DATA,'index.json'))),info=index.bundles.find(b=>b.key===index.compare.bundle)||index.bundles[0];
 const bundle=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA,info.path)))),tokens=new Map(bundle.lines.map(L=>[L.page+'|'+L.locus,L.end-L.start]));
 const nodes=[...new Set(Object.values(compact.pages).map(p=>p.node))],withMargins=new Set(),withAngle=new Set();let points=0;
 for(const node of nodes){
  const m=S.sheet(node,compact.pages,{sheets:compact.sheets,tokens});
  for(const up of ['outer','inner'])for(const l of S.view(m,up).leaves){
   if(l.tilt){
    const dr=compact.pages[l.folio].drift;withAngle.add(l.folio);assert.equal(l.tilt.angle,dr.recorded.angle);assert.equal(l.tilt.flat,dr.flat.angle);
    for(const coords of ['recorded','flat']){
     const line=S.tiltLine(l,{coords}),want=(l.front?1:-1)*(coords==='recorded'?dr.recorded.angle:dr.flat.angle);
     assert.ok(Math.abs(line.seen-want)<1e-6,`${l.folio} ${up} ${coords}: seen at ${line.seen}, written at ${want}`);
     const c=S.tiltLine(l,{coords,at:'page'}).ends;assert.ok((c[0][0]+c[1][0])/2>l.leaf[0]&&(c[0][0]+c[1][0])/2<l.leaf[2],`${l.folio}: the page's middle is on its leaf`);
    }
   }
   if(l.estimated.includes('fold')||l.estimated.includes('top'))continue;
   for(const r of [...l.margins.left,...l.margins.right]){
    withMargins.add(l.folio);points++;
    assert.ok(r.at[0]>=l.leaf[0]-2&&r.at[0]<=l.leaf[2]+2&&r.at[1]>=l.leaf[1]-2&&r.at[1]<=l.leaf[3]+2,`${l.folio} ${up}: a margin point off its leaf ${r.at.map(v=>v.toFixed(1))}`);
   }
  }
 }
 assert.ok(withAngle.size>=200,`${withAngle.size} pages with a text angle`);assert.ok(withMargins.size>=150,`${withMargins.size} measured pages with margins`);assert.ok(points>5000,`${points} margin points`);
 assert.ok(!withAngle.has('fRos')&&!withMargins.has('fRos'),'the Rosettes have no paragraph lines');
});
test('every foldout leaf has its measured widths, and every word of a page with a registration lies on its own panels',{skip:!have},()=>{
 const sheets=compact.sheets;let words=0;
 assert.deepEqual(Object.keys(sheets).sort(),['I:67-68','J:69-70','K:71-72','N:85-86','O:87-90','O:88-89','Q:94-95','S:100-101','S:99-102'],'the foldout sheets');
 for(const [node,plan] of Object.entries(sheets)){
  const m=S.sheet(node,compact.pages,{sheets});
  for(const up of ['outer','inner'])for(const l of S.view(m,up).leaves.filter(l=>l.front)){
   const c=l.leaf,H=m.height||S.LEAF[1];
   if(!plan.grid){
    const leaf=plan[l.slot[0]];if(!leaf)continue;
    const widths=(leaf.faces||{})[l.slot[1]]||leaf.widths,w=leaf.pages[l.folio].reduce((a,i)=>a+widths[i],0);assert.ok(Math.abs(c[2]-c[0]-w)<1e-9,`${l.folio} is ${w} mm wide`);
   }
   assert.ok(l.words.every(({rect:r})=>r[0]>=c[0]-3&&r[2]<=c[2]+3&&r[1]>=-3&&r[3]<=H+3),`${l.name||l.folio}: every word on its panels`);words+=l.words.length;
  }
 }
 assert.ok(words>6000,`${words} words checked`);
 const f101=S.view(S.sheet('S:100-101',compact.pages,{sheets}),'inner').leaves.find(l=>l.folio==='f101r');
 assert.equal(f101.cells.length,2,'f101r runs across both panels of its leaf');assert.ok(Math.abs(f101.leaf[2]-f101.leaf[0]-277.7)<0.5,'278 mm across');
 // the binding hides more of f101's first panel on the recto: the verso is drawn at its own width there, its crease in the gap in its text
 const v101=S.view(S.sheet('S:100-101',compact.pages,{sheets}),'outer').leaves.find(l=>l.folio==='f101v'),crease=v101.cells.map(c=>c[0]).sort((a,b)=>b-a)[0];
 assert.ok(Math.abs(v101.leaf[2]-v101.leaf[0]-290.9)<0.5,'f101v: 291 mm from its fold');
 assert.ok(!v101.words.some(({rect:r})=>r[0]<crease&&r[2]>crease),'no f101v word across its crease');
 const f72=S.view(S.sheet('K:71-72',compact.pages,{sheets}),'inner').leaves.filter(l=>l.slot==='Br').map(l=>[l.folio,l.cells.length]);
 assert.deepEqual(f72,[['f72r1',1],['f72r2',1],['f72r3',2]],'f72 folds out three panels, the third with a further fold');
 assert.ok(!S.sheet('K:71-72',compact.pages,{sheets}).leaves.some(l=>l.slot[0]==='A'&&l.cells.length>1),'f71 is an ordinary leaf');
});
test('the Rosettes sheet folds three panels by two: the Rosettes inside, the upper row outside upside down',{skip:!have},()=>{
 const m=S.sheet('N:85-86',compact.pages,{sheets:compact.sheets}),out=S.view(m,'outer'),inn=S.view(m,'inner'),at=(v,n)=>v.leaves.find(l=>(l.name||l.folio)===n);
 assert.equal(out.height,450);assert.deepEqual(m.missing,[]);
 const cells={f86v6:[-160,0,0,225],f86v4:[0,0,160,225],f85r2:[160,0,320,225],f86v5:[-160,225,0,450],f86v3:[0,225,160,450],f85r1:[160,225,320,450]};
 const on=(l,c,t)=>l.words.every(({rect:r})=>r[0]>=c[0]-t&&r[2]<=c[2]+t&&r[1]>=c[1]-t&&r[3]<=c[3]+t);
 for(const [f,c] of Object.entries(cells)){
  const l=at(out,f);assert.deepEqual(l.leaf,c,f);assert.ok(l.front,f);assert.equal(l.turned,c[1]===0,f);assert.ok(on(l,c,3),`${f}: every word on its own panel`);
  const u=compact.pages[f].units,first=l.words[0].rect,last=l.words[u.length-1].rect;
  assert.ok(l.turned?first[1]>last[1]:first[1]<last[1],`${f} reads ${l.turned?'up':'down'} the table`);
 }
 // the Rosettes behind them: f85v behind the f85 panels, f86r behind the four f86 panels; with the inner face up, as read, every word on its half
 assert.deepEqual(at(out,'fRos (f85v)').leaf,[160,0,320,450]);assert.deepEqual(at(out,'fRos (f86r)').leaf,[-160,0,160,450]);assert.ok(!at(out,'fRos (f86r)').front);
 assert.ok(on(at(inn,'fRos (f85v)'),[0,0,160,450],5)&&on(at(inn,'fRos (f86r)'),[160,0,480,450],5));
 assert.equal(at(inn,'fRos (f85v)').words.length+at(inn,'fRos (f86r)').words.length,compact.pages.fRos.units.length,'each word once');
 assert.ok(at(inn,'fRos (f85v)').words.length>50&&at(inn,'fRos (f86r)').words.length>100);
 // divided, leaf A is the f85 panels with the Rosettes' f85v, leaf B the rest
 assert.deepEqual(S.view(m,'outer',S.ALL,'A').leaves.map(l=>l.name||l.folio).sort(),['f85r1','f85r2','fRos (f85v)']);
 const bb=S.view(m,'outer',S.ALL,'B').box;
 assert.ok(bb[0]===-160&&bb[1]===0&&bb[3]===450&&bb[2]>=160&&bb[2]<163,`leaf B ${bb}: its box takes in a Rosettes word that runs a millimetre over the fold`);
 // the Rosettes are one drawing, placed whole: every word at one offset from its place on the scan, so the rosettes run on across the creases
 const I=compact.sheets['N:85-86'].grid.inside,L=compact.pages.fRos.paper,u=compact.pages.fRos.units;
 const offs=[at(inn,'fRos (f85v)'),at(inn,'fRos (f86r)')].flatMap(l=>l.words.map(w=>w.rect[0]-u[w.id][3]/L.mm));
 assert.ok(Math.max(...offs)-Math.min(...offs)<1e-6,'one placement across the panels and rows');
 assert.ok(Math.abs(((I.crease[0]+I.crease[1])-(I.fold[0]+I.fold[1]))/2/L.mm-S.LEAF[0])<3,'the outer crease lands within 3 mm of the panel edge');
 assert.deepEqual(S.lines(out),{xs:[160,-160,0,320],ys:[0,450]});
});
