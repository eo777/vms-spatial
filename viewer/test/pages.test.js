'use strict';
// Every page tells Dark Reader to stay out. It rewrites colours that carry data, and it reads the layout once per fill, which froze the Atlas for good on 37,596 boxes.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const root=path.join(__dirname,'..'),pages=fs.readdirSync(root).filter(f=>f.endsWith('.html'));
test('every page carries the Dark Reader lock in its head',()=>{
 assert.ok(pages.length>=7);
 for(const f of pages)assert.match(fs.readFileSync(path.join(root,f),'utf8').split('</head>')[0],/<meta name="darkreader-lock">/,f);
});
