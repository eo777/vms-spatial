// The Word search model: the pattern language as the Echo rule builder defines it, on small texts and on the real one; the tiles; the address.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),zlib=require('zlib');
const P=require('../js/pattern_math.js'),T=require('../js/stream_math.js');
const DATA=path.join(__dirname,'..','data'),REVIEW=path.join(__dirname,'..','..','data','manuscript','spatial_review.json.gz');
const gz=p=>JSON.parse(zlib.gunzipSync(fs.readFileSync(p)));
const have=['compare/pages.json.gz','manuscript/words.json.gz'].every(p=>fs.existsSync(path.join(DATA,p)))&&fs.existsSync(REVIEW);
const line=(words,o={})=>({folio:'f1r',locus:'1',category:'P',first:false,words,positions:words.map((w,i)=>w?i:-1),...o});
const text=()=>P.markPageInitial([line(['pchedy','daiin','qokaiin'],{first:true}),line(['pol','chedy',null,'dam'],{locus:'2'}),line(['ychey','pchol'],{locus:'3',first:true})]);
const find=(q,lines=text(),merge=false)=>P.occurrences(lines,merge).filter(P.occurrencePattern(q)).map(o=>o.raw+'@'+o.line.locus);

test('terms are globs over the whole spelling, and nothing runs as a regular expression',()=>{
 assert.deepEqual(find('*aiin'),['daiin@1','qokaiin@1']);
 assert.deepEqual(find('ch?dy'),['chedy@2']);
 assert.deepEqual(find('aiin'),[]);
 assert.deepEqual(find('ch.dy'),[]);
 assert.equal(P.glob('{ct}y','{ct}y'),true);
 assert.throws(()=>P.occurrencePattern('[ab]'),/"\[ab\]" is not a qualifier/);
 assert.throws(()=>P.occurrencePattern('a[b]'),/goes at the start of a term/);
 assert.throws(()=>P.occurrencePattern('a'.repeat(161)),/under 160/);
 assert.equal(P.glob('*a*a*a*a*a*a*a*a*a*a*b','a'.repeat(40)),false);
});
test('operators have one meaning each, with ordinary precedence',()=>{
 assert.equal(P.describePattern('*k*|!*ok*'),'*k* OR NOT (*ok*)');
 assert.equal(P.describePattern('*k* & !*ok*'),'*k* AND NOT (*ok*)');
 assert.equal(P.describePattern('*a*|*b*&*c*'),'*a* OR (*b* AND *c*)');
 assert.equal(P.describePattern('!(*a*|*b*)&*c*'),'NOT (*a* OR *b*) AND *c*');
 assert.equal(P.describePattern(''),'');
 assert.throws(()=>P.parsePattern('chol or chor'),/Write OR in capitals/);
 assert.throws(()=>P.parsePattern('chol chor'),/Put AND\/OR between/);
 assert.throws(()=>P.parsePattern('(chol'),/not closed/);
 assert.throws(()=>P.parsePattern('chol AND'),/AND needs a pattern after it/);
});
test('neighbours stay on the line and never cross an unreadable token',()=>{
 assert.deepEqual(find('*aiin AND -1:p*'),['daiin@1']);
 assert.deepEqual(find('chedy AND 1:*'),[]);
 assert.deepEqual(find('dam AND -1:*'),[]);
 assert.deepEqual(find('-2:pchedy'),['qokaiin@1']);
 assert.throws(()=>P.parsePattern('-1:'),/needs a pattern after the colon/);
});
test('qualifiers say where a word stands, as plain conditions',()=>{
 assert.deepEqual(find('[li]p*'),['pchedy@1','pol@2']);
 assert.deepEqual(find('[lf]*'),['qokaiin@1','dam@2','pchol@3']);
 assert.deepEqual(find('[pgi]*'),['pchedy@1','daiin@1','qokaiin@1']);
 assert.deepEqual(find('[lpi]p*'),['pchol@3']);
 assert.deepEqual(find('[npi]*'),['pol@2','chedy@2','dam@2']);
 assert.deepEqual(find('[!pgi]p*'),['pol@2','pchol@3']);
 assert.equal(find('![pgi]p*').length,7);
 assert.deepEqual(find('-1:[li]*'),['daiin@1','chedy@2','pchol@3']);
 assert.deepEqual(P.patternQualifiers('[pi][li]p* OR -1:[lf]* OR [li]*'),['pi','li','lf']);
 assert.deepEqual(['!pgi','!npi','li'].map(P.qualifierName),['not a page-initial line','paragraph-initial line','line initial']);
 assert.throws(()=>P.parsePattern('[li]-1:*'),/Write the offset first: -1:\[li\]\*/);
 assert.throws(()=>P.parsePattern('[li]'),/needs a spelling after the qualifier/);
 assert.throws(()=>P.parsePattern('[li p*'),/close the qualifier/);
});
test('Merge q matches words and neighbours without one initial q',()=>{
 const lines=text();
 assert.deepEqual(find('okaiin',lines,false),[]);
 assert.deepEqual(find('okaiin',lines,true),['qokaiin@1']);
 assert.deepEqual(find('qok*',lines,true),[]);
 assert.deepEqual(find('daiin AND 1:okaiin',lines,true),['daiin@1']);
});
test('a share is over the words where the pattern can match, never narrowed by spelling',()=>{
 const base=q=>{const b=P.rateBase(q);return b.all?'all':b.text;};
 assert.equal(base('p*'),'all');
 assert.equal(base('[pi]p*'),'[pi]*');
 assert.equal(base('p* AND NOT [li]*'),'[!li]*');
 assert.equal(base('p* AND NOT -1:[li]*'),'NOT (-1:[li]*)');
 assert.equal(base('NOT [pi]p*'),'all');
 assert.equal(base('[pi]p* OR [npi]q*'),'[pi]* OR [npi]*');
 assert.equal(base('[pi]p* OR q*'),'all');
 assert.equal(base('*aiin AND -1:*k*'),'all');
 const os=P.occurrences(text());
 for(const q of ['[pi]p*','p* AND NOT [li]*','[pi][!pgi]p*','-1:[li]*','[pgi]*aiin'])assert.ok(os.filter(P.occurrencePattern(q)).every(P.rateBase(q).test),q);
 assert.equal(P.share(5,19),null);assert.equal(P.share(5,20),.25);
});
test('a pattern written for another tool gets a sentence, not silence',()=>{
 assert.match(P.advice('^qo*'),/not needed/);assert.match(P.advice('dy$'),/not needed/);
 assert.equal(P.advice('qo*',0),'');
 assert.match(P.advice('aiin',0),/Write \*aiin\*/);assert.equal(P.advice('aiin',5),'');assert.equal(P.advice('(unclosed',0),'');
});
test('a display box is a word\'s own resolved box, else its group\'s parts, each once',()=>{
 const review={tokens:[{id:'a',group:'1'},{id:'b',group:'1'},{id:'c',group:'2'},{id:'d',group:'3'},{id:'e',group:'9'}],groups:{1:{id:'1',display_parts:[[1,1,5,5],[6,1,9,5]]},2:{id:'2',display_parts:[[1,1,5,5]],resolved:[{token:'c',display_box:[2,2,3,3]}]},3:{id:'3',display_parts:[[4,4,4,8]]}}};
 assert.deepEqual(P.displayParts(0,1,review),[[1,1,5,5],[6,1,9,5]]);
 assert.deepEqual(P.displayParts(2,2,review),[[2,2,3,3]]);
 assert.deepEqual(P.displayParts(3,4,review),[]);
});
test('tiles keep the sequence, empty positions and foldout panels',()=>{
 const pages={a:{node:'X',slot:'Ar',face:'outer'},b:{node:'X',slot:'Bv',face:'outer'},c:{node:'Y',slot:'Br',face:'inner',panel:'1'},d:{node:'Y',slot:'Br',face:'inner',panel:'2'}};
 const plan=T.sequence(pages,['c','d','a','b'],{}),tiles=P.tiles(plan);
 assert.deepEqual(tiles.map(t=>t.node),['Y','X']);
 assert.deepEqual(tiles[1].cells.map(c=>[c.slot,c.pages.length]),[['Ar',1],['Av',0],['Br',0],['Bv',1]]);
 assert.deepEqual(tiles[0].cells[2].pages.map(p=>p.folio),['c','d']);
 assert.deepEqual(P.tiles(plan,'faces')[1].cells.map(c=>c.slot),['Bv','Ar','Av','Br']);
});
test('ordinary bifolia share the widest one\'s width; a foldout keeps its own',()=>{
 const shape={a:1100/1500,w:1800/1500},tile=cells=>({cells:cells.map(c=>({pages:c.map(folio=>({folio}))}))}),aspect=f=>shape[f];
 assert.equal(P.plainTile(tile([['a'],[],['a'],['a']]),aspect),true,'an empty position is still an ordinary bifolium');
 assert.equal(P.plainTile(tile([['a','a'],['a'],['a'],['a']]),aspect),false,'panels together in one position are a foldout');
 assert.equal(P.plainTile(tile([['w'],['a'],['a'],['a']]),aspect),false,'a page wider than it is tall is a foldout');
 assert.equal(P.evenWidth([{width:420,plain:true},{width:457,plain:true},{width:553,plain:false}]),457);
 assert.equal(P.evenWidth([{width:614,plain:false}]),0,'no ordinary bifolium, no common width');
});
test('the address round-trips, keeps a pattern\'s colour, and shares the Page stream\'s order keys',()=>{
 const h={by:'section',group:'Herbal A',order:'path1',columns:'faces',custom:'A,B',pages:'f1r',q1:'*aiin',q3:'[li]p* OR q*',merge:'1',size:'140',open:'f1r',image:'0',labels:'1'};
 assert.deepEqual(P.serialize(P.parse(h)),h);
 assert.deepEqual(P.serialize(P.parse({})),{});
 assert.deepEqual(P.parse({q2:'x'}).layers,[{slot:2,query:'x'}]);
 assert.deepEqual(P.parse({q7:'x',size:'9'}),P.parse({}));
 assert.equal(P.parse(T.fromWorkspace({seqOrder:'path1',seqCustomOrder:'["B","A"]'})).order,'path1');
 assert.deepEqual(P.parse({seqOrder:'path1',seqCustomOrder:'["B","A"]'}).custom,['B','A']);
});
test('a custom order stays only while every bifolium it names is in the list, by the Page stream\'s own rule',()=>{
 const pages={a:{node:'A'},b:{node:'B'}};
 assert.deepEqual(P.cleanCustom(['B','A'],pages,['a','b']),['B','A']);
 assert.deepEqual(P.cleanCustom(['B','Z'],pages,['a','b']),[]);
});
test('an order the menu does not have opens by bifolium, so the menu and the tiles agree',()=>{
 const menu=fs.readFileSync(path.join(__dirname,'..','search.html'),'utf8').match(/<select id="order">(.*?)<\/select>/)[1];
 assert.deepEqual([...menu.matchAll(/value="(\w+)"/g)].map(m=>m[1]),P.ORDERS);
 assert.equal(P.parse({order:'path1'}).order,'path1');
 assert.equal(P.parse({order:'herbal_a_1a'}).order,'bifolia');
});
test('the Tile size menu offers the sizes the address accepts, largest last, and an older link keeps its size',()=>{
 const menu=fs.readFileSync(path.join(__dirname,'..','search.html'),'utf8').match(/<select id="size">(.*?)<\/select>/)[1];
 assert.deepEqual([...menu.matchAll(/value="(\d+)"/g)].map(m=>m[1]),P.SIZES);
 assert.match(menu,/value="450">Largest</);
 for(const size of P.SIZES.slice(1))assert.deepEqual(P.serialize(P.parse({size})),{size});
 assert.equal(P.parse({size:'200'}).size,'200');
});
test('the real text: the same words as the bundle, the unreadable tokens back in place, and the Echo rule builder\'s counts',{skip:!have},()=>{
 const bundle=gz(path.join(DATA,'manuscript/words.json.gz')),compact=gz(path.join(DATA,'compare/pages.json.gz')),review=gz(REVIEW);
 const lines=P.textLines(bundle,compact.pages,review.tokens),os=P.occurrences(lines);
 assert.equal(lines.length,5365);assert.equal(os.length,bundle.words.length);
 assert.equal(lines.reduce((n,l)=>n+l.words.filter(w=>!w).length,0),130);
 assert.ok(os.every(o=>bundle.words[o.position]===o.raw));
 assert.deepEqual([lines.filter(l=>l.first).length,lines.filter(l=>l.pageFirst).length,lines.filter(l=>l.first&&!l.pageFirst).length],[740,207,533]);
 assert.ok(lines.filter(l=>l.first).every(l=>l.category==='P'));
 // reference counts from workbench_core.js on its own copy of the text
 const count=q=>os.filter(P.occurrencePattern(q)).length,over=q=>os.filter(P.rateBase(q).test).length;
 assert.deepEqual([count('*aiin'),count('qok*'),count('*aiin AND -1:*k*'),count('*y AND 1:qo*')],[3898,3107,854,3425]);
 assert.deepEqual([count('[pi]p*'),over('[pi]p*')],[444,6878]);
 assert.deepEqual([count('[li]p*'),over('[li]p*')],[384,5346]);
 assert.deepEqual([count('[pgi]p*'),over('[pgi]p*')],[109,1833]);
 assert.deepEqual([count('[lf]*m'),over('[lf]*m')],[714,5344]);
 assert.throws(()=>P.textLines({...bundle,words:['x',...bundle.words.slice(1)]},compact.pages,review.tokens),/do not match the bundle/);
 const plain=P.textLines(bundle,compact.pages);assert.equal(plain.reduce((n,l)=>n+l.words.filter(w=>!w).length,0),0);
});
