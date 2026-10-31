"use strict";
// One menu for every page: fills <nav class="site-nav"></nav>, marks the current page, adds the theme toggle.
(function(){
 const pages=[['./','Atlas'],['compare.html','Compare'],['sections.html','Sections'],['alignment.html','Alignment review'],['about.html','About']];
 let nav=document.querySelector('nav.site-nav');
 if(!nav){nav=document.createElement('nav');nav.className='site-nav';document.body.prepend(nav);}
 nav.setAttribute('aria-label','vms-spatial');
 const here=decodeURIComponent(location.pathname.split('/').pop()||'index.html');
 const brand=document.createElement('a');brand.className='brand';brand.href='./';brand.textContent='vms-spatial';
 const links=pages.map(([href,label])=>{const a=document.createElement('a');a.href=href;a.textContent=label;if((href==='./'?'index.html':href)===here)a.setAttribute('aria-current','page');return a;});
 const spacer=document.createElement('span');spacer.className='spacer';
 const tag=document.createElement('span');tag.className='tag';tag.id='releaseTag';
 const theme=document.createElement('button');theme.type='button';theme.className='theme';
 const stored=(()=>{try{return localStorage.getItem('vms-theme');}catch(e){return null;}})();
 if(stored)document.documentElement.dataset.theme=stored;
 const label=()=>{const t=document.documentElement.dataset.theme;theme.textContent=t==='dark'?'Light':t==='light'?'Dark':(matchMedia('(prefers-color-scheme: dark)').matches?'Light':'Dark');};
 theme.addEventListener('click',()=>{const dark=document.documentElement.dataset.theme==='dark'||(!document.documentElement.dataset.theme&&matchMedia('(prefers-color-scheme: dark)').matches);const next=dark?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('vms-theme',next);}catch(e){}label();document.dispatchEvent(new CustomEvent('themechange'));});
 label();
 nav.replaceChildren(brand,...links,spacer,tag,theme);
})();
