/* Word patterns, and the tiles of the Word search page. The language is the Echo rule builder's, on the toolkit's text: a term is a glob over the whole
   spelling, and no regular expression is ever run. Terms combine with ordinary logic, NOT (!) before AND (&) before OR (|), with parentheses, and NOT applies to
   the whole term or group after it. Operator words are capitals only, because lowercase or is a Voynich word. A term may start with an offset (-1: the word
   before, 1: the word after, along the line), and then with qualifiers for where its word stands: [li] [lf] line initial and final, [pi] [pgi] [lpi] [npi] the
   line classes, [!code] that place negated. A missing neighbour (line end, unreadable token) matches no term. No DOM. Node tests: viewer/test/pattern_math.test.js. */
(function(root){
'use strict';
const T=(typeof module!=='undefined'&&module.exports)?require('./stream_math.js'):root.VMS_STREAM;
const LAYERS=6,SIZES=['70','100','140','200'],MIN_SHARE=20;
const OPERATORS={'&':'AND','|':'OR','!':'NOT',AND:'AND',OR:'OR',NOT:'NOT'};
const core=word=>word&&word.replace(/^q/,'');
// ---- the places a word can stand
/* markPageInitial(lines): the first prose line of each page, by lowest locus, marked from the whole text so that any subset keeps the marks */
function markPageInitial(lines){
 const first=new Map();
 for(const l of lines)if(l.category==='P'){const f=first.get(l.folio);if(!f||parseFloat(l.locus)<parseFloat(f.locus))first.set(l.folio,l);}
 for(const l of lines)l.pageFirst=first.get(l.folio)===l;
 return lines;
}
const QUALIFIERS={
 li:{name:'line initial',not:'not line initial',test:(line,i)=>i===0},
 lf:{name:'line final',not:'not line final',test:(line,i)=>i===line.words.length-1},
 pi:{name:'paragraph-initial line',not:'not a paragraph-initial line',test:l=>!!l.first},
 pgi:{name:'page-initial line',not:'not a page-initial line',test:l=>!!l.pageFirst},
 lpi:{name:'later paragraph-initial line',not:'not a later paragraph-initial line',test:l=>!!l.first&&!l.pageFirst},
 npi:{name:'line that is not paragraph initial',not:'paragraph-initial line',test:l=>!l.first},
};
const QUALIFIER_LIST=Object.keys(QUALIFIERS).map(q=>`[${q}]`).join(', ');
const qualifierName=q=>q.startsWith('!')?QUALIFIERS[q.slice(1)].not:QUALIFIERS[q].name;
const qualifierTest=q=>{if(!q.startsWith('!'))return QUALIFIERS[q].test;const test=QUALIFIERS[q.slice(1)].test;return (line,i)=>!test(line,i);};
// ---- reading a pattern
function qualified(rest,text){
 const quals=[];
 for(let m;(m=/^\[([^\]]*)\]/.exec(rest));rest=rest.slice(m[0].length)){
  if(!QUALIFIERS[m[1].replace(/^!/,'')])throw Error(`"[${m[1]}]" is not a qualifier; use ${QUALIFIER_LIST}, or one with ! inside to negate it, as in [!pgi].`);
  if(!quals.includes(m[1]))quals.push(m[1]);
 }
 if(rest.startsWith('['))throw Error(`"${text}": close the qualifier with ], as in [li]p*.`);
 const offset=/^[+-]?\d+:/.exec(rest);
 if(offset&&quals.length)throw Error(`Write the offset first: ${offset[0]}${quals.map(q=>`[${q}]`).join('')}${rest.slice(offset[0].length)}.`);
 if(/[[\]]/.test(rest))throw Error(`"${text}": a qualifier such as [li] goes at the start of a term, before the spelling.`);
 if(quals.length&&!rest)throw Error(`"${text}" needs a spelling after the qualifier, e.g. ${text}*.`);
 return {glob:rest,quals};
}
function parsePattern(query=''){
 query=String(query??'');
 if(query.length>160)throw Error('Keep patterns under 160 characters.');
 const tokens=[];
 for(let i=0;i<query.length;){
  const ch=query[i];
  if(/\s/.test(ch)){i++;continue;}
  if('()&|!'.includes(ch)){tokens.push(ch==='('||ch===')'?{t:ch}:{t:'op',v:OPERATORS[ch]});i++;continue;}
  // a term runs to a space or an operator symbol, except that inside a qualifier's brackets ! negates the code
  let j=i,inside=false;
  for(;j<query.length;j++){const c=query[j];if(c==='[')inside=true;else if(c===']')inside=false;else if(/\s/.test(c)||(!inside&&/[()&|!]/.test(c)))break;}
  const text=query.slice(i,j);i=j;
  if(/^(AND|OR|NOT)$/.test(text)){tokens.push({t:'op',v:text});continue;}
  const at=/^([+-]?\d+):(.*)$/.exec(text);
  if(at&&!at[2])throw Error(`"${text}" needs a pattern after the colon.`);
  const {glob:v,quals}=qualified(at?at[2]:text,text);
  tokens.push({t:'term',v,quals,offset:at?Number(at[1])||0:0,text});
 }
 if(!tokens.length)return null;
 let k=0;
 const peek=()=>tokens[k],isOp=v=>peek()?.t==='op'&&peek().v===v,name=tok=>tok.t==='term'?`"${tok.text}"`:tok.t==='op'?tok.v:'a parenthesis';
 function primary(){
  const tok=peek();
  if(!tok)throw Error(tokens[k-1].t==='('?'A parenthesis is not closed.':`${tokens[k-1].v} needs a pattern after it.`);
  if(tok.t==='term'){k++;return {t:'term',v:tok.v,quals:tok.quals,offset:tok.offset,text:tok.text};}
  if(tok.t==='('){
   k++;if(peek()?.t===')')throw Error('The parentheses are empty.');
   const inner=or();if(peek()?.t!==')')throw Error('A parenthesis is not closed.');
   k++;return inner;
  }
  if(tok.t===')')throw Error('A closing parenthesis has no opening one.');
  throw Error(`${tok.v} needs a pattern before it.`);
 }
 function not(){if(isOp('NOT')){k++;return {t:'not',a:not()};}return primary();}
 function and(){let a=not();while(isOp('AND')){k++;a={t:'and',a,b:not()};}return a;}
 function or(){let a=and();while(isOp('OR')){k++;a={t:'or',a,b:and()};}return a;}
 const tree=or();
 if(k<tokens.length){
  const tok=tokens[k],before=tokens[k-1];
  if(tok.t===')')throw Error('A closing parenthesis has no opening one.');
  // "chol or chor" (or "chol or" while typing): a lowercase operator word after a pattern was meant as the operator
  if(tok.t==='term'&&/^(and|or|not)$/i.test(tok.text))throw Error(`Write ${tok.text.toUpperCase()} in capitals; "${tok.text}" is searched as a word.`);
  throw Error(`Put AND/OR between ${name(before)} and ${name(tok)}.`);
 }
 return tree;
}
/* glob(p, word): dynamic programming keeps even adversarial *a*a*... patterns bounded */
function glob(p,word){
 let row=[true,...Array(word.length).fill(false)];
 for(const ch of p){
  const next=[ch==='*'&&row[0]];
  for(let j=1;j<=word.length;j++)next[j]=ch==='*'?row[j]||next[j-1]:row[j-1]&&(ch==='?'||ch===word[j-1]);
  row=next;
 }
 return row[word.length];
}
function compileTree(node,term){
 if(!node)return ()=>true;
 if(node.t==='term')return term(node);
 if(node.t==='not'){const a=compileTree(node.a,term);return x=>!a(x);}
 const a=compileTree(node.a,term),b=compileTree(node.b,term);
 return node.t==='and'?x=>a(x)&&b(x):x=>a(x)||b(x);
}
/* indexAt(o, offset) -> the place `offset` words from an occurrence along its line; -1 at a line end or past an unreadable token */
function indexAt(o,offset){
 if(!offset)return o.index;
 const words=o.line.words,step=offset<0?-1:1,target=o.index+offset;
 for(let i=o.index+step;;i+=step){
  if(i<0||i>=words.length||!words[i])return -1;
  if(i===target)return i;
 }
}
/* one term against an occurrence: the word its offset points at exists, matches the spelling and stands where the qualifiers say. A spelling is globbed once a term */
function occurrenceTerm(node){
 const tests=node.quals.map(qualifierTest),seen=new Map();
 const spelled=word=>{let hit=seen.get(word);if(hit===undefined)seen.set(word,hit=glob(node.v,word));return hit;};
 return o=>{
  const i=indexAt(o,node.offset);if(i<0)return false;
  return spelled(node.offset?(o.mergeQ?core(o.line.words[i]):o.line.words[i]):o.word)&&tests.every(t=>t(o.line,i));
 };
}
const occurrencePattern=(query='')=>compileTree(parsePattern(query),occurrenceTerm);
// ---- the reading written out
const flatten=(n,t)=>n.t===t?[...flatten(n.a,t),...flatten(n.b,t)]:[n];
function showTree(n,parent=null){
 if(n.t==='term')return `${n.offset?`${n.offset}:`:''}${n.quals.map(q=>`[${q}]`).join('')}${n.v}`;
 if(n.t==='not')return `NOT (${showTree(n.a)})`;
 const text=flatten(n,n.t).map(c=>showTree(c,n.t)).join(n.t==='and'?' AND ':' OR ');
 return parent?`(${text})`:text;
}
function describePattern(query=''){const tree=parsePattern(query);return tree?showTree(tree):'';}
function patternQualifiers(query=''){
 const out=[],walk=n=>{if(!n)return;if(n.t==='term')n.quals.forEach(q=>{if(!out.includes(q))out.push(q);});else{walk(n.a);walk(n.b);}};
 walk(parsePattern(query));return out;
}
function patternTerms(query=''){
 const out=[],walk=n=>{if(!n)return;if(n.t==='term')out.push(n.v);else{walk(n.a);walk(n.b);}};
 walk(parsePattern(query));return out;
}
/* literalWord(query) -> the exact spelling a pattern names, '' when it uses wildcards or operators or does not parse */
function literalWord(query=''){
 try{const tree=parsePattern(query);return tree&&tree.t==='term'&&!tree.offset&&!tree.quals.length&&!/[*?]/.test(tree.v)?tree.v:'';}
 catch(e){return '';}
}
/* rateBase(query) -> the words where a pattern can match, so that a share is matches per word of that class: {all, text, test}. Qualifiers restrict it ([pi]p* is
   over [pi]*); spellings and neighbour spellings never do. AND and OR combine the terms' bases. NOT keeps a base only over qualifiers alone (p* AND NOT [li]* is
   over [!li]*); NOT over a spelling too leaves all words, as does OR with an unrestricted side. Terms on the word itself merge into one. */
function rateBase(query=''){
 const placeOnly=n=>n.t==='term'?n.quals.length>0&&n.v==='*':n.t==='not'?placeOnly(n.a):placeOnly(n.a)&&placeOnly(n.b);
 const strip=n=>{
  if(!n)return null;
  if(n.t==='term')return n.quals.length?{t:'term',v:'*',quals:n.quals,offset:n.offset}:null;
  if(n.t==='not'){
   if(!placeOnly(n.a))return null;
   // NOT of one code on the word itself reads as that code negated: NOT [li]* is [!li]*
   const a=strip(n.a),one=a.t==='term'&&!a.offset&&a.quals.length===1;
   return one?{t:'term',v:'*',quals:[a.quals[0].startsWith('!')?a.quals[0].slice(1):'!'+a.quals[0]],offset:0}:{t:'not',a};
  }
  const a=strip(n.a),b=strip(n.b);
  return n.t==='and'?(a&&b?{t:'and',a,b}:a||b):(a&&b?{t:'or',a,b}:null);
 };
 let node=strip(parsePattern(query));
 if(node&&node.t==='and'){
  const parts=flatten(node,'and'),own=parts.filter(x=>x.t==='term'&&!x.offset);
  if(own.length>1)node=[{t:'term',v:'*',quals:[...new Set(own.flatMap(x=>x.quals))],offset:0},...parts.filter(x=>!own.includes(x))].reduce((a,b)=>({t:'and',a,b}));
 }
 if(!node)return {all:true,text:'',test:()=>true};
 return {all:false,text:showTree(node),test:compileTree(node,occurrenceTerm)};
}
/* advice(query, matches) -> a sentence for someone who has written the pattern another tool's way, or '' */
function advice(query='',matches=0){
 let terms;try{terms=patternTerms(query);}catch(e){return '';}
 if(terms.some(t=>/[$^]/.test(t)))return 'A pattern already matches the whole word, so ^ and $ are not needed: write qo* for words starting qo, and *dy for words ending dy.';
 const word=literalWord(query);
 return word&&!matches?`No word is spelled exactly ${word}. Write *${word}* for words containing it.`:'';
}
// ---- the text
/* textLines(bundle, pages, tokens) -> the lines as the language reads them: {folio, locus, node, category, first, pageFirst, words, positions}. words holds the
   spelling at each place on the line, and null at a token the transliteration marks unreadable, so that no neighbour term reaches across one. The bundle has
   dropped those tokens; tokens = the review file's list, which keeps them. positions holds each place's index in bundle.words, -1 at a null. A line's flag
   `first` counts on paragraph lines only: the compact pages also set it on every label, circle and radial line, which start no paragraph. Without tokens the
   lines have no nulls. */
function textLines(bundle,pages,tokens=null){
 const texts=new Map(),info=new Map();
 for(const t of tokens||[]){const key=t.page+'|'+t.locus;if(!texts.has(key))texts.set(key,[]);texts.get(key).push(t.text);}
 for(const f of Object.keys(pages))for(const l of pages[f].lines)info.set(f+'|'+l[0],l);
 return markPageInitial(bundle.lines.map(l=>{
  const key=l.page+'|'+l.locus,own=texts.get(key)||bundle.words.slice(l.start,l.end),meta=info.get(key)||[l.locus,0,'P'],words=[],positions=[];let next=l.start;
  for(const text of own){if(text.includes('?')){words.push(null);positions.push(-1);}else{words.push(text);positions.push(next++);}}
  if(next!==l.end||positions.some(p=>p>=0&&bundle.words[p]!==words[positions.indexOf(p)]))throw Error(`The review tokens of ${key} do not match the bundle.`);
  return {folio:l.page,locus:l.locus,node:l.bifolium,category:meta[2],first:meta[2]==='P'&&!!meta[1],words,positions};
 }));
}
/* occurrences(lines, mergeQ) -> one record per readable word. mergeQ matches every word and neighbour without one initial q */
function occurrences(lines,mergeQ=false){
 const out=[];
 for(const line of lines)line.words.forEach((raw,index)=>{if(raw)out.push({line,index,raw,mergeQ,word:mergeQ?core(raw):raw,position:line.positions[index]});});
 return out;
}
/* displayParts(first, last, review) -> the rectangles of a unit's tokens on the Voynichese display image: a word's own resolved box, else its group's parts */
function displayParts(first,last,review){
 const out=[],seen=new Set();
 for(let p=first;p<=last;p++){
  const t=review.tokens[p],g=t&&review.groups[t.group];if(!g)continue;
  const own=(g.resolved||[]).find(r=>r.token===t.id);
  if(own&&own.display_box){out.push(own.display_box);continue;}
  if(seen.has(g.id))continue;seen.add(g.id);
  out.push(...(g.display_parts||[]).filter(b=>b[2]>b[0]&&b[3]>b[1]));
 }
 return out;
}
/* share(n, base) -> n/base, or null under MIN_SHARE words: a share of a handful of words reads as more than it is */
const share=(n,base)=>base>=MIN_SHARE?n/base:null;
// ---- the tiles
/* tiles(plan, columns) -> one tile a bifolium, in the sequence's order: {node, index, pages, cells: [{slot, pages}]}. columns 'singulion' runs Ar Av Br Bv, 'faces'
   the physical faces Bv Ar and Av Br. A position with no page stays in as an empty cell, and foldout panels stay together in their cell. */
function tiles(plan,columns='singulion'){
 const slots=columns==='faces'?['Bv','Ar','Av','Br']:T.SLOTS;
 return plan.nodes.map((node,index)=>{const members=plan.pages.filter(p=>p.node===node);return {node,index,pages:members,cells:slots.map(slot=>({slot,pages:members.filter(p=>p.slot===slot)}))};});
}
// ---- the address: group, order, columns, custom and pages mean what they mean on the Page stream, so a link's tail works on both pages
/* parse(hash) -> the page's state, every value checked; serialize(state) -> the hash, defaults left out. A pattern's key names its colour: q3 stays the third colour */
function parse(h={}){
 const s=T.parse(h),layers=[];
 for(let slot=1;slot<=LAYERS;slot++)if(typeof h['q'+slot]==='string')layers.push({slot,query:h['q'+slot].slice(0,160)});
 return {by:s.by,group:s.group,order:s.order,columns:s.columns,custom:s.custom,pages:s.pages,layers:layers.length?layers:[{slot:1,query:''}],merge:h.merge==='1',size:SIZES.includes(h.size)?h.size:SIZES[0],open:typeof h.open==='string'?h.open:'',image:h.image!=='0',labels:h.labels==='1'};
}
function serialize(s){
 const o=T.serialize({...T.parse({}),by:s.by,group:s.group,order:s.order,columns:s.columns,custom:s.custom,pages:s.pages});
 for(const l of s.layers)if(l.query.trim())o['q'+l.slot]=l.query;
 if(s.merge)o.merge='1';if(s.size!==SIZES[0])o.size=s.size;if(s.open)o.open=s.open;if(!s.image)o.image='0';if(s.labels)o.labels='1';
 return o;
}
const api={LAYERS,SIZES,MIN_SHARE,QUALIFIERS,core,markPageInitial,qualifierName,parsePattern,glob,occurrencePattern,indexAt,describePattern,patternQualifiers,patternTerms,literalWord,rateBase,advice,textLines,occurrences,displayParts,share,tiles,parse,serialize};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VMS_PATTERN=api;
})(typeof window!=='undefined'?window:globalThis);
