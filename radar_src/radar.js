'use strict';
// Progressive enhancement only. Static HTML remains the source of readable content.
(() => {
 const form=document.querySelector('#filters');
 const back=document.querySelector('[data-back]');
 const keys=['q','category','source','official','verification','order'];
 function safeContext(search) {
  const incoming=new URLSearchParams(search), clean=new URLSearchParams();
  for(const k of keys){const value=incoming.get(k);if(value&&value.length<=300)clean.set(k,value);}
  return clean;
 }
 if(back){
  const context=safeContext(location.search);
  if(context.size)back.href='/radar/?'+context.toString()+'#discovery';
 }
 if(form){
  if(matchMedia('(max-width:1000px)').matches){document.querySelector('.category-panel').open=false;document.querySelector('.filter-panel').open=false;}
  const cards=Array.from(document.querySelectorAll('[data-event]'));
  const controls={q:document.querySelector('#query'),category:document.querySelector('#category'),source:document.querySelector('#source'),official:document.querySelector('#official'),verification:document.querySelector('#verification'),order:document.querySelector('#order')};
  const incoming=safeContext(location.search);
  for(const key of keys){
   const control=controls[key], value=incoming.get(key);
   if(value&&(control.tagName==='INPUT'||Array.from(control.options).some(o=>o.value===value)))control.value=value;
  }
  function update(){
   const q=controls.q.value.trim().toLocaleLowerCase();
   let count=0;
   const context=new URLSearchParams();
   for(const key of keys){const val=controls[key].value;if(val&&(key!=='order'||val!=='observed'))context.set(key,val);}
   const orderKey=controls.order.value==='published'?'published':'observed';
   cards.sort((a,b)=>(b.dataset[orderKey]||'').localeCompare(a.dataset[orderKey]||'')||(b.dataset.published||'').localeCompare(a.dataset.published||'')||b.dataset.identity.localeCompare(a.dataset.identity));
   for(const card of cards){
    const visible=(!q||card.dataset.search.toLocaleLowerCase().includes(q))&&(!controls.category.value||card.dataset.category===controls.category.value)&&(!controls.source.value||card.dataset.source===controls.source.value)&&(!controls.official.value||card.dataset.official===controls.official.value)&&(!controls.verification.value||card.dataset.status===controls.verification.value);
    card.hidden=!visible;if(visible)count++;
    document.querySelector('#events').append(card);
    for(const link of card.querySelectorAll('a.detail-link,a.read')){
     const u=new URL(link.href);u.search=context.toString();link.href=u.pathname+u.search;
    }
   }
   document.querySelector('#result-count').textContent='顯示 '+count+' / '+cards.length+' 個保存候選；不是已核實世界事件。';
   document.querySelector('#empty').hidden=count!==0;
   for(const link of document.querySelectorAll('[data-category-link]'))link.setAttribute('aria-current',String(link.dataset.categoryLink===controls.category.value));
   const query=context.toString();
   history.replaceState(null,'',location.pathname+(query?'?'+query:'')+location.hash);
  }
  form.hidden=false;
  form.addEventListener('submit',event=>event.preventDefault());
  form.addEventListener('input',update);form.addEventListener('change',update);
  form.addEventListener('reset',()=>setTimeout(update,0));
  for(const link of document.querySelectorAll('[data-category-link]'))link.addEventListener('click',event=>{
   event.preventDefault();controls.category.value=link.dataset.categoryLink;update();document.querySelector('#discovery').scrollIntoView();document.querySelector('#discovery').focus();
  });
  addEventListener('pageshow',update);
  update();
 }
 const button=document.querySelector('#copy-citation');
 if(button)button.addEventListener('click',async()=>{
  const field=document.querySelector('#citation'),status=document.querySelector('#copy-status');
  try{await navigator.clipboard.writeText(field.value);status.textContent='已複製引用；保留來源、時間與研究限制。';}
  catch{field.focus();field.select();status.textContent='瀏覽器未允許自動複製；請複製已選取的引用原文。';}
 });
})();

