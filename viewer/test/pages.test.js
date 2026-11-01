'use strict';
// Every page tells Dark Reader to stay out. It rewrites colours that carry data, and it reads the layout once per fill, which froze the Atlas for good on 37,596 boxes.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const root=path.join(__dirname,'..'),pages=fs.readdirSync(root).filter(f=>f.endsWith('.html'));
test('every page carries the Dark Reader lock in its head',()=>{
 assert.ok(pages.length>=7);
 for(const f of pages)assert.match(fs.readFileSync(path.join(root,f),'utf8').split('</head>')[0],/<meta name="darkreader-lock">/,f);
});
// Node's require finds a math file's dependency by itself, so only the page's own script list can leave one out
test('a page loads what its math files need, before them',()=>{
 const needs={'js/stream_math.js':['js/compare_math.js','js/stream_1a_preset.js'],'js/pattern_math.js':['js/stream_math.js']};
 for(const f of pages){
  const scripts=[...fs.readFileSync(path.join(root,f),'utf8').matchAll(/<script src="([^"?]+)/g)].map(m=>m[1]);
  for(const [file,deps] of Object.entries(needs))if(scripts.includes(file))for(const dep of deps)assert.ok(scripts.includes(dep)&&scripts.indexOf(dep)<scripts.indexOf(file),`${f}: ${dep} before ${file}`);
 }
});
