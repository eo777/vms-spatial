"use strict";
// The Light table: bifolia as open sheets on the parchment scale, or divided into their leaves, each dragged where you like, either face up, the face
// underneath seen through; the same bifolium or leaf as often as wanted. The model, the alignment guides and the address: js/sheet_math.js.
(async function(){
 const {$,esc}=SG,S=VMS_SHEETS,Z=COMPARE_STATE,W=VMS_WORDS;
 const h=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const table=$('table'),surface=$('surface'),list=$('list'),status=$('status'),notes=$('notes');
 let pages,sheets={},words,lines=[],lineOfToken=[],nodes=[],state,selected=null,order=[];
 const loading=SG.busyStart('Loading the manuscript…');
 const config=await fetch('config.json').then(r=>r.ok?r.json():{}).catch(()=>({}));
 SG.setBase(SG.hash().data||config.dataBase||'data/');
 try{
  const index=await SG.load(SG.dataUrl('index.json')),C=index.compare;
  if(!C)throw Error('index.json has no compare entry: run `vmsspatial viewer-data`.');
  const info=index.bundles.find(b=>b.key===C.bundle)||index.bundles[0];
  const [compact,orders,bundle]=await Promise.all([SG.load(SG.dataUrl(C.pages)),SG.load(SG.dataUrl(C.orders)),SG.load(SG.dataUrl(info.path))]);
  if(!compact.paper)throw Error('These page records have no parchment data: rebuild them with `vmsspatial viewer-data`.');
  pages=compact.pages;sheets=compact.sheets||{};words=bundle.words;lines=bundle.lines||[];
  lineOfToken=new Int32Array(words.length).fill(-1);lines.forEach((L,i)=>{for(let t=L.start;t<L.end;t++)lineOfToken[t]=i;});
  for(const f of Z.pageList(orders,'bifolia',pages))if(!nodes.includes(pages[f].node))nodes.push(pages[f].node);
 }catch(error){loading.end();status.textContent='Could not load the page data.';SG.error(table,error);return;}
 state=S.parse(SG.hash(),nodes);order=state.sheets.map(S.idOf);
 const save=()=>SG.setHash({data:SG.hash().data,...S.serialize(state,nodes)});
 const css=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
 // a colour (sheet_math.js): one of the six sheet colours, 0 ink, or six hex digits chosen with the picker
 const hexOf=c=>typeof c==='string'?'#'+c:null;
 const colourOf=c=>hexOf(c)||(c?css('--hl-'+c):css('--ink2')),colourVar=c=>hexOf(c)||(c?`var(--hl-${c})`:'var(--ink2)');
 const zoom=()=>Number(state.zoom),signed=v=>(v>0.05?'+':v<-0.05?'−':'')+Math.abs(v).toFixed(1);
 const sectionOf=node=>{const f=Object.keys(pages).find(k=>pages[k].node===node);return f?pages[f].section:'';};
 // a leaf's folio number, from its pages: leaf A of A:1-8 is f1, leaf B is f8
 const leafNo=(node,part)=>{const f=Object.keys(pages).find(k=>pages[k].node===node&&S.PARTS[part].includes(pages[k].slot));return f?pages[f].leaf:null;};
 const nameOf=s=>(s.part?`f${leafNo(s.node,s.part)} · `:'')+s.node+((s.copy||1)>1?` (${s.copy})`:'');
 const faceName=s=>{if(!s.part)return s.up==='outer'?'Outer face up':'Inner face up';const slot=S.PARTS[s.part].find(x=>(S.FACE[x]===s.up));return S.RECTOS.includes(slot)?'Recto up':'Verso up';};
 const find=id=>state.sheets.find(s=>S.idOf(s)===id);
 // ---- the pieces' geometry, kept until the coordinates change
 const models=new Map(),els=new Map();
 const modelOf=s=>{const key=s.node+'|'+state.coords;if(!models.has(key))models.set(key,S.sheet(s.node,pages,{coords:state.coords,sheets}));return models.get(key);};
 const viewOf=s=>S.view(modelOf(s),s.up,s.show,s.part);
 function element(s){
  const id=S.idOf(s);if(els.has(id))return els.get(id);
  const el=h('div','lt-sheet'),canvas=h('canvas');el.tabIndex=0;el.dataset.id=id;el.append(canvas);surface.append(el);els.set(id,el);
  el.addEventListener('pointerdown',e=>drag(find(id),el,e));el.addEventListener('keydown',e=>keys(find(id),e));el.addEventListener('focus',()=>select(id));
  return el;
 }
 function position(s){
  const el=element(s),v=viewOf(s),z=zoom();
  el.style.left=(s.x+v.box[0])*z+'px';el.style.top=(s.y+v.box[1])*z+'px';el.style.zIndex=String(1+order.indexOf(S.idOf(s)));
  el.setAttribute('aria-label',`${nameOf(s)}, ${faceName(s).toLowerCase()}, fold edge ${(s.x+S.FOLD).toFixed(1)} mm, top ${s.y.toFixed(1)} mm`);
 }
 // a piece in millimetres: its leaves, the folds, the face underneath in outline and the face up filled
 function paint(s){
  const el=element(s),c=el.firstChild,v=viewOf(s),z=zoom(),[bx,by,bx1,by1]=v.box,dpr=Math.min(2,devicePixelRatio||1),w=Math.ceil((bx1-bx)*z),ht=Math.ceil((by1-by)*z);
  c.width=Math.ceil(w*dpr);c.height=Math.ceil(ht*dpr);c.style.width=w+'px';c.style.height=ht+'px';
  const g=c.getContext('2d'),col=colourOf(s.colour),px=1/z,same=(a,b)=>a.every((x,i)=>Math.abs(x-b[i])<.01);
  // by face, the pages of a sheet's outer face take the outer face's colour and those of its inner face the inner's, wherever the piece lies and
  // whichever side is up; the outlines go to ink, and the label squares keep the piece's own colour
  const byFace=state.colouring==='face',faces=state.faceColours.map(colourOf),tone=l=>byFace?faces[l.face==='outer'?0:1]:col,lead=byFace?css('--ink2'):col;
  g.setTransform(dpr*z,0,0,dpr*z,-bx*dpr*z,-by*dpr*z);
  const front=v.leaves.filter(l=>l.front),back=v.leaves.filter(l=>!l.front),H=v.height,cells=front.flatMap(l=>l.cells);
  // the outline round its face-up leaves (the nominal leaf when it has none), every fold and crease between two panels dashed, a panel underneath
  // that sticks out dotted
  g.lineWidth=px;g.strokeStyle=lead;
  const edge=cells.length?cells.reduce((e,c)=>[Math.min(e[0],c[0]),0,Math.max(e[2],c[2]),H],[Infinity,0,-Infinity,H]):[bx,0,bx1,H];
  for(const [x0,y0,x1,y1] of cells){g.globalAlpha=.07;g.fillStyle=lead;g.fillRect(x0,y0,x1-x0,y1-y0);}
  g.globalAlpha=.9;g.strokeRect(edge[0],0,edge[2]-edge[0],H);
  const inside=(v0,lo,hi)=>v0>lo+.01&&v0<hi-.01,folds=new Set([...(inside(v.fold,edge[0],edge[2])?[v.fold]:[]),...cells.flatMap(c=>[c[0],c[2]]).filter(x=>inside(x,edge[0],edge[2]))]);
  const creases=new Set(cells.flatMap(c=>[c[1],c[3]]).filter(y=>inside(y,0,H)));
  g.setLineDash([5*px,4*px]);g.globalAlpha=.8;g.beginPath();for(const x of folds){g.moveTo(x,0);g.lineTo(x,H);}for(const y of creases){g.moveTo(edge[0],y);g.lineTo(edge[2],y);}g.stroke();
  g.setLineDash([2*px,3*px]);g.globalAlpha=.6;
  for(const l of back)for(const c of l.cells)if(!cells.some(f=>same(f,c))){const [x0,y0,x1,y1]=c;g.strokeRect(x0,y0,x1-x0,y1-y0);}
  g.setLineDash([]);
  g.lineWidth=Math.max(.9*px,.2);
  // with the words written, the boxes step back so the spellings read, the face underneath further than the face up
  for(const l of back)if(l.shown){g.globalAlpha=state.words?.45:.8;g.strokeStyle=tone(l);for(const {rect:[x0,y0,x1,y1]} of l.words)g.strokeRect(x0,y0,x1-x0,y1-y0);}
  for(const l of front)if(l.shown){g.globalAlpha=state.words?.35:.6;g.fillStyle=tone(l);for(const {rect:[x0,y0,x1,y1]} of l.words)g.fillRect(x0,y0,x1-x0,y1-y0);}
  if(state.words&&spell(g,v,z))turnedOn.add(S.idOf(s));else turnedOn.delete(S.idOf(s));
  $('wdirLabel').hidden=!turnedOn.size;
  // labels in ink, each after a square of its page's colour (the piece's, or by face its face's), on a row of their own for each piece, so pieces
  // stacked on one another keep theirs apart
  const row=(state.sheets.indexOf(s)%8)*13*px,label=(text,x,y,ink,mark)=>{g.globalAlpha=1;g.fillStyle=mark;g.fillRect(x,y-7*px,6*px,6*px);g.fillStyle=css(ink);g.fillText(text,x+9*px,y);};
  g.font=`${11*px}px system-ui,sans-serif`;g.textBaseline='middle';
  for(const l of front){label(l.name||l.folio,l.leaf[0]+3*px,l.leaf[1]+9*px+row,'--ink',tone(l));if(l.turned){g.fillStyle=css('--ink2');g.fillText('upside down',l.leaf[0]+12*px,l.leaf[1]+21*px+row);}}
  for(const l of back)if(l.shown)label(`(${l.name||l.folio} behind)`,l.leaf[0]+3*px,l.leaf[3]-8*px-row,'--ink2',tone(l));
  g.globalAlpha=1;g.fillStyle=css('--ink2');g.textAlign='right';g.fillText(`${nameOf(s)} · ${faceName(s).toLowerCase()}`,edge[2]-3*px,9*px+row);g.textAlign='start';
  position(s);
 }
 // each word's EVA spelling once it is at least MIN_TEXT screen pixels tall, the face underneath's the right way round. Level text goes in its box, at
 // most its width. A ring's or a turned line's words, and those of a panel written upside down, go along the writing, or upright with Word
 // direction Level, one size for the page, sized by
 // their length along it (js/word_labels.js); behind, mirrored, they turn the other way. Returns whether any such word is shown
 const MIN_TEXT=7,textOf=(folio,id)=>{const u=pages[folio].units[id];return words.slice(u[0],u[1]+1).join(' ');};
 // each word's direction on its page, from its line's orientation record: 0 level, null turned but which way unknown
 const angles=new Map(),turnedOn=new Set();
 const anglesOf=folio=>{if(!angles.has(folio))angles.set(folio,pages[folio].units.map(u=>{const L=lines[lineOfToken[u[0]]];return L?W.angleOf(L.orientation,u[0]-L.start):0;}));return angles.get(folio);};
 function spell(g,v,z){
  const mono=css('--mono')||'monospace';let turned=false;g.textBaseline='middle';
  for(const l of v.leaves)if(l.shown){
   // a word's direction on the table: on an upside-down panel turned half way round, behind (mirrored) the other way
   const a=anglesOf(l.folio),round=[],dir=w=>{let t=a[w.id];if(t==null)return null;if(l.turned)t+=t>0?-180:180;return l.front?t:-t;};
   g.globalAlpha=1;g.fillStyle=css(l.front?'--ink':'--ink2');g.textAlign='left';
   for(const w of l.words){
    const t=dir(w);if(t!==0){round.push({rect:w.rect.map(v=>v*z),text:textOf(l.folio,w.id),angle:t});continue;}
    const [x0,y0,x1,y1]=w.rect,size=(y1-y0)*.72;if(size*z<MIN_TEXT)continue;
    g.font=`${size}px ${mono}`;g.fillText(textOf(l.folio,w.id),x0+.3,(y0+y1)/2,Math.max(.5,x1-x0-.6));
   }
   if(!round.length)continue;
   // laid out in screen pixels, as on the Atlas
   turned=true;g.textAlign='center';
   W.layout(round,state.wdir).forEach((f,k)=>{
    if(f.size<MIN_TEXT)return;
    g.save();g.translate(f.x/z,f.y/z);if(f.angle)g.rotate(f.angle*Math.PI/180);g.font=`${f.size/z}px ${mono}`;g.fillText(round[k].text,0,0);g.restore();
   });
  }
  g.textAlign='start';return turned;
 }
 function sizeSurface(){
  const z=zoom();let w=0,ht=0;
  for(const s of state.sheets){const b=viewOf(s).box;w=Math.max(w,s.x+b[2]);ht=Math.max(ht,s.y+b[3]);}
  surface.style.width=Math.max(table.clientWidth,(w+120)*z)+'px';surface.style.height=Math.max(table.clientHeight,(ht+120)*z)+'px';
 }
 // ---- the list: a row a piece
 function where(s){const ref=state.sheets[0];if(!ref||ref===s)return 'reference';const r=S.relative(s,ref);return `fold edge ${signed(r.fold)} mm, top ${signed(r.top)} mm from ${nameOf(ref)}`;}
 function fillList(){
  list.replaceChildren();
  for(const s of state.sheets){
   const id=S.idOf(s),row=h('div','lt-row'+(id===selected?' selected':'')),name=h('button','lt-name',nameOf(s)),face=h('button','lt-face',faceName(s)),box=h('span','lt-pages'),at=h('span','lt-where',where(s));
   const cut=h('button','lt-cut',s.part?'Join':'Divide'),remove=h('button','lt-remove','×'),swatch=h('button','lt-swatch');
   row.style.setProperty('--sheet',colourVar(s.colour));row.dataset.id=id;
   name.type=face.type=cut.type=remove.type=swatch.type='button';name.title=sectionOf(s.node);remove.setAttribute('aria-label','Remove '+nameOf(s));
   swatch.title='Choose its colour';swatch.setAttribute('aria-label','Colour of '+nameOf(s));swatch.setAttribute('aria-haspopup','dialog');
   // both leaves of a sheet keep one colour
   swatch.onclick=()=>pickColour(swatch,s.colour,c=>{for(const p of state.sheets)if(S.sameCopy(p,s)){p.colour=c;paint(p);}for(const r of list.children){const q=find(r.dataset.id);if(q)r.style.setProperty('--sheet',colourVar(q.colour));}save();});
   face.title=s.part?'Turn the leaf over where it lies (F)':'Turn the sheet over about its fold (F)';cut.title=s.part?'Join with its other leaf into the whole sheet (D)':'Divide into its two leaves (D)';
   name.onclick=()=>{select(id);els.get(id)?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'});};
   face.onclick=()=>flip(s);cut.onclick=()=>cutOrJoin(s);remove.onclick=()=>removeSheet(s);
   const m=modelOf(s),mine=x=>!s.part||S.PARTS[s.part].includes(x);
   for(const f of [s.up,s.up==='outer'?'inner':'outer']){
    const group=h('span','face'),present=S.SLOTS.filter(x=>S.FACE[x]===f&&mine(x)&&m.leaves.some(l=>l.slot===x)),bits=present.reduce((b,x)=>b|S.BIT[x],0);
    // a sheet's face: every page on it at once
    if(!s.part&&bits){
     const all=h('label','lt-facecheck'),cb=h('input');cb.type='checkbox';cb.checked=(s.show&bits)===bits;cb.indeterminate=!cb.checked&&!!(s.show&bits);
     cb.onchange=()=>{s.show=cb.checked?s.show|bits:s.show&~bits;paint(s);fillList();syncChecks();save();};
     all.title=`Show or hide every page of its ${f} face`;all.append(cb,f==='outer'?'Outer':'Inner');group.append(all);
    }
    for(const slot of present){
     const leaves=m.leaves.filter(l=>l.slot===slot);
     const label=h('label'),cb=h('input');cb.type='checkbox';cb.checked=!!(s.show&S.BIT[slot]);
     cb.onchange=()=>{s.show^=S.BIT[slot];paint(s);fillList();syncChecks();save();};
     const named=l=>l.name||l.folio;label.title=leaves.map(named).join(', ');label.append(cb,named(leaves[0])+(leaves.length>1?` +${leaves.length-1}`:''));group.append(label);
    }
    if(group.querySelector('label'))box.append(group);
   }
   row.append(swatch,name,face,box,at,cut,remove);list.append(row);
  }
 }
 // ---- choosing a colour: the six sheet colours and ink, or any with the picker; apply(colour) as it changes
 const PRESETS=[[1,'Blue'],[2,'Orange'],[3,'Green'],[4,'Amber'],[5,'Pink'],[6,'Deep green'],[0,'Ink']],pop=$('colourPop'),picker=$('customColour');
 let applyColour=null,popAnchor=null;
 $('presets').replaceChildren(...PRESETS.map(([c,name])=>{const b=h('button','lt-preset');b.type='button';b.dataset.colour=String(c);b.title=name;b.setAttribute('aria-label',name);b.style.setProperty('--sheet',colourVar(c));b.onclick=()=>{applyColour?.(c);closeColour();};return b;}));
 const asHex=v=>/^#[0-9a-f]{6}$/i.test(v)?v.toLowerCase():'#808080';
 function pickColour(anchor,current,apply){
  if(popAnchor===anchor&&!pop.hidden)return closeColour();
  applyColour=apply;popAnchor=anchor;
  for(const b of pop.querySelectorAll('.lt-preset'))b.setAttribute('aria-pressed',String(b.dataset.colour===String(current)));
  picker.value=asHex(colourOf(current));pop.hidden=false;anchor.setAttribute('aria-expanded','true');
  const r=anchor.getBoundingClientRect(),w=pop.offsetWidth,ht=pop.offsetHeight;
  pop.style.left=Math.max(8,Math.min(innerWidth-w-8,r.left))+'px';pop.style.top=(r.bottom+6+ht>innerHeight?Math.max(8,r.top-6-ht):r.bottom+6)+'px';
  (pop.querySelector('[aria-pressed="true"]')||pop.querySelector('button')).focus();
 }
 function closeColour(){if(pop.hidden)return;pop.hidden=true;popAnchor?.setAttribute('aria-expanded','false');popAnchor?.focus({preventScroll:true});applyColour=popAnchor=null;}
 picker.addEventListener('input',()=>applyColour?.(picker.value.slice(1).toLowerCase()));
 const faceChips=()=>{$('faceOuter').style.setProperty('--sheet',colourVar(state.faceColours[0]));$('faceInner').style.setProperty('--sheet',colourVar(state.faceColours[1]));};
 [['faceOuter',0],['faceInner',1]].forEach(([id,k])=>$(id).onclick=()=>pickColour($(id),state.faceColours[k],c=>{state.faceColours[k]=c;faceChips();for(const s of state.sheets)paint(s);save();}));
 // ---- the Add menu: a leaf of the bifolium on its own
 const menu=$('addMenu'),more=$('addMore');
 const closeMenu=()=>{if(menu.hidden)return;menu.hidden=true;more.setAttribute('aria-expanded','false');};
 more.onclick=()=>{if(!menu.hidden)return closeMenu();menu.hidden=false;more.setAttribute('aria-expanded','true');menu.querySelector('button:not(:disabled)')?.focus();};
 menu.addEventListener('keydown',e=>{
  const items=[...menu.querySelectorAll('button:not(:disabled)')],i=items.indexOf(document.activeElement);
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();items[(i+(e.key==='ArrowDown'?1:items.length-1))%items.length]?.focus();}
 });
 addEventListener('pointerdown',e=>{
  if(!menu.hidden&&!e.target.closest('.lt-split'))closeMenu();
  if(!pop.hidden&&!pop.contains(e.target)&&e.target!==popAnchor&&!popAnchor?.contains(e.target)){pop.hidden=true;popAnchor?.setAttribute('aria-expanded','false');applyColour=popAnchor=null;}
 },true);
 addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!menu.hidden){closeMenu();more.focus();}else if(!pop.hidden)closeColour();});
 const updateWhere=()=>{for(const row of list.children){const s=find(row.dataset.id);if(s)row.querySelector('.lt-where').textContent=where(s);}};
 const FACE_BOXES=[['outerFaces','outer'],['innerFaces','inner']];
 function syncChecks(){
  for(const [id,f] of FACE_BOXES){
   const bits=S.FACE_BITS[f],on=state.sheets.filter(s=>(s.show&bits)===bits).length,some=state.sheets.some(s=>s.show&bits);
   $(id).checked=state.sheets.length>0&&on===state.sheets.length;$(id).indeterminate=some&&on<state.sheets.length;$(id).disabled=!state.sheets.length;
  }
 }
 function fillAdd(){
  if(!$('add').options.length){$('add').replaceChildren(...nodes.map(n=>new Option(`${n} · ${sectionOf(n)}`,n)));$('add').value=nodes[0];}
  const node=$('add').value,full=state.sheets.length>=S.MAX_SHEETS;
  $('addSheet').disabled=full||!node;
  for(const part of ['A','B']){const b=$('addLeaf'+part),n=leafNo(node,part);b.textContent=n?`Add leaf f${n}`:`Add leaf ${part}`;b.disabled=full||!n;b.title=n?`Leaf ${part} of ${node} on its own: f${n}r and f${n}v`:`${node} has no leaf ${part} here`;}
  $('addMore').disabled=full||!node||(!leafNo(node,'A')&&!leafNo(node,'B'));if($('addMore').disabled)closeMenu();
 }
 function describe(){
  const n=state.sheets.length,leaves=state.sheets.filter(s=>s.part).length,on=state.sheets.map(viewOf),est=k=>on.flatMap(v=>v.leaves.filter(l=>l.estimated.includes(k)).map(l=>l.folio));
  const missing=[...new Set(state.sheets.flatMap(s=>modelOf(s).missing))],foldouts=[...new Set(state.sheets.filter(s=>{const v=viewOf(s);return !v.folded&&!v.measured&&v.leaves.some(l=>l.k||l.panel);}).map(s=>s.node))];
  const measured=[...new Set(state.sheets.filter(s=>viewOf(s).measured).map(s=>s.node))];
  const rosettes=state.sheets.some(s=>viewOf(s).folded);
  const count=[n-leaves?`${n-leaves} ${n-leaves===1?'sheet':'sheets'}`:'',leaves?`${leaves} ${leaves===1?'leaf':'leaves'}`:''].filter(Boolean).join(' and ');
  status.textContent=n?`${count} on the table · ${state.coords==='flat'?'flat (dewarped)':'recorded'} coordinates · parchment scale, estimated · ${state.zoom} px/mm`:'The table is empty: choose a bifolium and add it as a sheet or a leaf.';
  notes.textContent=n?'Filled words are on the face that is up, as read. Outlined words are on the face underneath, mirrored, where they lie behind it on the same leaf. Folds are dashed. The wheel zooms about the pointer; drag the empty table, or drag with the middle button, to pan. '
   +(state.colouring==='face'?'Pages are coloured by the face of their sheet, outer or inner, so overlapping pieces show which side of their sheet is up; outlines are in ink. ':'')
   +(state.words?(zoom()<2?'Zoom in to about 2 px/mm or more to read the words. ':'EVA spellings are written in their boxes; those underneath the right way round, at their mirrored places. ')
    +(turnedOn.size?(state.wdir==='level'?'Words on rings, turned lines and upside-down panels stand upright, one size a page, and can run past their boxes. ':'Words on rings, turned lines and upside-down panels are written along the writing, ring words with their bottoms towards the wheel\'s centre; Word direction: Level stands them upright. '):''):'')
   +[['fold','Fold estimated'],['top','Top edge estimated'],['scale','Scale estimated']].map(([k,t])=>{const f=[...new Set(est(k))];return f.length?`${t}: ${f.join(', ')}. `:'';}).join('')
   +(rosettes?'The Rosettes sheet folds three panels by two, as the Beinecke photographs show it: the Rosettes fill its inside (f85v | f86r); outside, the lower row (f86v5, f86v3, f85r1) reads the same way up as the Rosettes and the upper row (f86v6, f86v4, f85r2) is written upside down, to be read with the upper half folded down. Panels are drawn at the catalogue leaf size. The Rosettes are drawn whole, as photographed, placed by their fold and horizontal crease, which are placed by eye on the scan to about 5 mm. ':'')
   +(measured.length?`Foldout leaves at their widths measured on the Beinecke photographs, to about 3 mm, creases dashed: ${measured.join(', ')}. `:'')
   +[...new Set(measured.filter(n=>Object.values(sheets[n]||{}).some(p=>p&&p.faces)))].map(n=>`${n}: the panel by the binding is drawn at each face's own width, as the binding hides more of it on one face than the other. `).join('')
   +(foldouts.length?`Foldout panels are laid outward a leaf apiece, their real folding not modelled: ${foldouts.join(', ')}. `:'')+(missing.length?`Not on the parchment, so not drawn: ${missing.join(', ')}. `:''):'';
 }
 function fillZoom(){
  const sel=$('zoom');let custom=sel.querySelector('option[data-custom]');
  if(S.ZOOMS.includes(state.zoom)){if(custom)custom.remove();}
  else{if(!custom){custom=new Option('','');custom.dataset.custom='1';sel.append(custom);}custom.value=state.zoom;custom.textContent=`${state.zoom} px/mm`;}
  sel.value=state.zoom;
 }
 function render(){
  const ids=new Set(state.sheets.map(S.idOf));
  for(const [id,el] of els)if(!ids.has(id)){el.remove();els.delete(id);turnedOn.delete(id);}
  if(!state.sheets.length)$('wdirLabel').hidden=true;
  order=order.filter(id=>ids.has(id));for(const id of ids)if(!order.includes(id))order.push(id);
  if(selected&&!ids.has(selected))selected=null;
  $('coords').value=state.coords;$('guides').checked=state.guides;$('snap').checked=state.snap;$('words').checked=state.words;$('wdir').value=state.wdir;$('colour').value=state.colouring;$('legend').hidden=state.colouring!=='face';faceChips();fillZoom();
  for(const s of state.sheets)paint(s);
  sizeSurface();fillList();fillAdd();syncChecks();describe();save();
 }
 // ---- choosing, moving, turning, dividing
 function select(id){
  if(selected===id)return;selected=id;order=[...order.filter(x=>x!==id),id];
  for(const s of state.sheets)position(s);
  for(const row of list.children)row.classList.toggle('selected',row.dataset.id===id);
 }
 // a click on the empty table lets go of the piece chosen; it keeps its place in the stack
 function deselect(){
  selected=null;for(const row of list.children)row.classList.remove('selected');
  if(document.activeElement&&document.activeElement.closest&&document.activeElement.closest('.lt-sheet'))document.activeElement.blur();
 }
 // a fold or edge of another piece within reach, and how far off: shown as guides, solid once met; with Snap to guides on, the piece is moved onto it
 // while it is dragged, else nothing is pulled into place
 let guides=[],fade=null;
 const alignFor=(s,x=s.x,y=s.y)=>S.align(x,y,S.lines(viewOf(s)),state.sheets.filter(o=>o!==s).map(o=>S.placed(o,S.lines(viewOf(o)))),Math.max(S.ALIGN_MM,6/zoom()));
 const guidesFor=s=>state.guides?alignFor(s):[];
 // the guides of piece s, their labels beside it; none for null. linger: ms before they go, 0 to keep them while it moves
 function showGuides(s,linger=0){
  clearTimeout(fade);for(const g of guides)g.remove();
  const z=zoom(),b=s&&viewOf(s).box;
  guides=(s?guidesFor(s):[]).map(g=>{
   const met=Math.abs(g.off)<S.ALIGNED,el=h('div','lt-guide '+g.axis+(met?' on':''));
   el.style[g.axis==='x'?'left':'top']=g.at*z+'px';el.style.setProperty('--at',(g.axis==='x'?(s.y+b[1])*z:(s.x+b[0])*z)+6+'px');
   el.dataset.label=met?'aligned':`${Math.abs(g.off).toFixed(1)} mm`;surface.append(el);return el;
  });
  if(linger)fade=setTimeout(()=>showGuides(null),linger);
 }
 function moveTo(s,x,y){const b=viewOf(s).box;s.x=Math.max(-b[0],x);s.y=Math.max(-b[1],y);position(s);}
 function drag(s,el,e){
  if(e.button===1)return pan(e);
  if(e.button!==0)return;
  e.preventDefault();el.focus({preventScroll:true});select(S.idOf(s));
  const z=zoom(),start={cx:e.clientX,cy:e.clientY,x:s.x,y:s.y};
  el.setPointerCapture(e.pointerId);el.classList.add('dragging');SG.hideTip();
  const move=ev=>{
   let p={x:start.x+(ev.clientX-start.cx)/z,y:start.y+(ev.clientY-start.cy)/z};
   if(state.snap)p=S.snapTo(p.x,p.y,alignFor(s,p.x,p.y));
   moveTo(s,p.x,p.y);showGuides(s);updateWhere();
  };
  const end=()=>{el.removeEventListener('pointermove',move);el.classList.remove('dragging');showGuides(s,1500);sizeSurface();updateWhere();save();};
  el.addEventListener('pointermove',move);el.addEventListener('pointerup',end,{once:true});el.addEventListener('pointercancel',end,{once:true});
 }
 function keys(s,e){
  const step=e.altKey?.1:e.shiftKey?5:.5,d={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[e.key];
  if(d){e.preventDefault();moveTo(s,Math.round((s.x+d[0])*10)/10,Math.round((s.y+d[1])*10)/10);showGuides(s,1500);sizeSurface();updateWhere();save();}
  else if(e.key==='f'||e.key==='F'){e.preventDefault();flip(s);}
  else if(e.key==='d'||e.key==='D'){e.preventDefault();cutOrJoin(s);}
  else if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();removeSheet(s);}
 }
 function flip(s){Object.assign(s,S.turn(s,p=>viewOf(p).box));paint(s);fillList();describe();save();}
 function cutOrJoin(s){
  const at=state.sheets.indexOf(s),focus=s.part?{...s,part:''}:{...s,part:'A'};
  state.sheets=s.part?S.join(s,state.sheets):[...state.sheets.slice(0,at),...S.divide(s),...state.sheets.slice(at+1)];
  selected=null;render();select(S.idOf(focus));els.get(S.idOf(focus))?.focus({preventScroll:true});
 }
 function removeSheet(s){state.sheets=state.sheets.filter(x=>x!==s);render();}
 // a new piece goes beside the last one, or on a new row; a leaf whose other leaf is on the table alone joins that copy, in its colour
 function addPiece(node,part){
  if(!node||state.sheets.length>=S.MAX_SHEETS)return;
  const mate=part&&state.sheets.find(p=>p.node===node&&p.part&&p.part!==part&&!state.sheets.some(q=>q!==p&&q.node===node&&(q.copy||1)===(p.copy||1)));
  const s={node,part,copy:mate?mate.copy||1:S.nextCopy(state.sheets,node),x:0,y:0,up:'outer',show:S.ALL,colour:mate?mate.colour:S.nextColour(state.sheets)},b=viewOf(s).box,room=table.clientWidth/zoom();
  let right=0,bottom=0;for(const o of state.sheets){const ob=viewOf(o).box;right=Math.max(right,o.x+ob[2]);bottom=Math.max(bottom,o.y+ob[3]);}
  if(!state.sheets.length){s.x=20-b[0];s.y=20-b[1];}
  else if(right+20+(b[2]-b[0])<=room){s.x=right+20-b[0];s.y=state.sheets[state.sheets.length-1].y;}
  else{s.x=20-b[0];s.y=bottom+20-b[1];}
  state.sheets.push(s);selected=null;render();select(S.idOf(s));
  els.get(S.idOf(s))?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'});
 }
 // ---- the wheel zooms about the pointer; the empty table, or the middle button anywhere, pans
 let pending=null;
 table.addEventListener('wheel',e=>{
  e.preventDefault();SG.hideTip();
  const r=table.getBoundingClientRect(),z=pending?pending.z:zoom(),step=e.deltaMode===1?e.deltaY*16:e.deltaMode===2?e.deltaY*400:e.deltaY;
  const next=Math.min(S.ZOOM_RANGE[1],Math.max(S.ZOOM_RANGE[0],z*Math.exp(-step*.0015)));if(next===z)return;
  const cx=e.clientX-r.left,cy=e.clientY-r.top,mm=pending?pending.mm:[(table.scrollLeft+cx)/z,(table.scrollTop+cy)/z];
  pending={z:next,mm,cx,cy};
  if(pending.frame)return;
  pending.frame=requestAnimationFrame(()=>{
   const p=pending;pending=null;state.zoom=S.zoomOf(p.z);const z2=zoom();
   for(const s of state.sheets)paint(s);sizeSurface();fillZoom();describe();
   // room enough to scroll the millimetre under the pointer back under it
   const left=p.mm[0]*z2-p.cx,top=p.mm[1]*z2-p.cy;
   surface.style.width=Math.max(parseFloat(surface.style.width)||0,left+table.clientWidth)+'px';surface.style.height=Math.max(parseFloat(surface.style.height)||0,top+table.clientHeight)+'px';
   table.scrollLeft=left;table.scrollTop=top;save();
  });
 },{passive:false});
 // click: what to do when the pointer comes up without having moved more than a few pixels
 function pan(e,click){
  e.preventDefault();const start={x:e.clientX,y:e.clientY,l:table.scrollLeft,t:table.scrollTop};let moved=false;
  table.setPointerCapture(e.pointerId);table.classList.add('panning');SG.hideTip();
  const move=ev=>{if(Math.hypot(ev.clientX-start.x,ev.clientY-start.y)>3)moved=true;table.scrollLeft=start.l-(ev.clientX-start.x);table.scrollTop=start.t-(ev.clientY-start.y);};
  const end=ev=>{table.removeEventListener('pointermove',move);table.classList.remove('panning');if(click&&!moved&&ev.type==='pointerup')click();};
  table.addEventListener('pointermove',move);table.addEventListener('pointerup',end,{once:true});table.addEventListener('pointercancel',end,{once:true});
 }
 table.addEventListener('pointerdown',e=>{if(e.target.closest('.lt-sheet'))return;if(e.button===0)pan(e,deselect);else if(e.button===1)pan(e);});
 table.addEventListener('auxclick',e=>{if(e.button===1)e.preventDefault();});
 // ---- what is under the pointer: the topmost piece's word there, the face up before the face underneath
 table.addEventListener('pointermove',e=>{
  if(e.buttons)return;
  const r=surface.getBoundingClientRect(),z=zoom(),mx=(e.clientX-r.left)/z,my=(e.clientY-r.top)/z;
  for(const id of [...order].reverse()){
   const s=find(id);if(!s)continue;
   const v=viewOf(s),x=mx-s.x,y=my-s.y;
   if(x<v.box[0]||x>v.box[2]||y<v.box[1]||y>v.box[3])continue;
   const inside=w=>x>=w.rect[0]&&x<=w.rect[2]&&y>=w.rect[1]&&y<=w.rect[3];
   for(const l of [...v.leaves.filter(l=>l.shown&&l.front),...v.leaves.filter(l=>l.shown&&!l.front)]){
    const w=l.words.find(inside);if(!w)continue;
    const p=pages[l.folio],u=p.units[w.id],text=words.slice(u[0],u[1]+1).join(' ');
    SG.showTip(`<b>${esc(l.name||l.folio)}</b> · line ${esc(p.lines[u[2]][0])} · <code>${esc(text)}</code><br>${l.front?'on the face up':'on the face underneath, seen through'}${l.turned?', written upside down':''} · ${esc(nameOf(s))}`,e.clientX,e.clientY);return;
   }
   SG.hideTip();return;
  }
  SG.hideTip();
 });
 // ---- the controls
 $('add').onchange=fillAdd;
 $('addSheet').onclick=()=>addPiece($('add').value,'');
 for(const part of ['A','B'])$('addLeaf'+part).onclick=()=>{closeMenu();addPiece($('add').value,part);};
 for(const [id,f] of FACE_BOXES)$(id).onchange=()=>{const bits=S.FACE_BITS[f];for(const s of state.sheets)s.show=$(id).checked?s.show|bits:s.show&~bits;render();};
 $('stack').onclick=()=>{if(state.sheets.length<2)return;S.stack(state.sheets).forEach((p,i)=>Object.assign(state.sheets[i],{x:p.x,y:p.y}));render();};
 $('spread').onclick=()=>{S.spread(state.sheets,table.clientWidth/zoom(),state.sheets.map(s=>viewOf(s).box)).forEach((p,i)=>Object.assign(state.sheets[i],{x:p.x,y:p.y}));render();};
 $('guides').onchange=()=>{state.guides=$('guides').checked;if(!state.guides)showGuides(null);save();};
 $('snap').onchange=()=>{state.snap=$('snap').checked;save();};
 $('words').onchange=()=>{state.words=$('words').checked;render();};
 $('wdir').onchange=()=>{state.wdir=$('wdir').value;render();};
 $('colour').onchange=()=>{state.colouring=$('colour').value;render();};
 $('coords').onchange=()=>{state.coords=$('coords').value;render();};
 $('zoom').onchange=()=>{state.zoom=S.zoomOf($('zoom').value);render();};
 $('clear').onclick=()=>{state.sheets=[];render();};
 addEventListener('hashchange',()=>{const next=S.parse(SG.hash(),nodes);if(JSON.stringify(S.serialize(next,nodes))===JSON.stringify(S.serialize(state,nodes)))return;state=next;render();});
 // a theme change repaints, as the colours are read from the page's tokens
 new MutationObserver(()=>{for(const s of state.sheets)paint(s);}).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{for(const s of state.sheets)paint(s);});
 addEventListener('resize',sizeSurface);
 try{render();}finally{loading.end();}
})();
