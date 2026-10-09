// Execute the actual served UI scripts, with a minimal DOM boundary and no network.
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const original=JSON.stringify(input.view),storage={...(input.storage||{})};
const buttons=['zh-TW','en'].map(language=>({dataset:{language},attributes:{},setAttribute(k,v){this.attributes[k]=v}}));
const nodes=Object.fromEntries(['app','brand','language-control'].map(id=>[id,{innerHTML:'',textContent:'',attributes:{},handlers:{},setAttribute(k,v){this.attributes[k]=v},addEventListener(k,f){this.handlers[k]=f}}]));
const popupTarget={focused:false,scrolled:false,timeline:{open:false},provenance:{open:false},querySelector(s){return s==='.event-timeline'?this.timeline:s==='.provenance'?this.provenance:null},focus(){this.focused=true},scrollIntoView(){this.scrolled=true}};
let requests=[];
const document={documentElement:{lang:'en'},title:'',handlers:{},addEventListener(k,f){this.handlers[k]=f},getElementById(id){if(id==='event-synthetic-event-1')return popupTarget;if(!nodes[id])throw Error('Unknown element '+id);return nodes[id]},querySelectorAll(selector){if(selector!=='[data-language]')throw Error('Unexpected selector');return buttons}};
const context=vm.createContext({document,window:{},navigator:{language:input.locale||'en-US'},localStorage:{getItem(k){if(input.storageBlocked)throw Error('Storage denied');return storage[k]||null},setItem(k,v){if(input.storageBlocked)throw Error('Storage denied');storage[k]=v}},URL,Set,console,fetch:async path=>{requests.push(path);if(path!=='/api/app/radar')throw Error('Unexpected request');return {ok:!input.failure,status:input.failure?503:200,json:async()=>input.failure?{error:input.failure}:input.view}}});
for(const match of input.html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)){
  if(/src=/.test(match[1])){if(match[1].includes('/ui/radar_demo_translations.js'))vm.runInContext(input.translations,context);else if(match[1].includes('/ui/radar_interactive_map.js'))vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../ui/radar_interactive_map.js'),'utf8'),context);else throw Error('Unexpected asset')}
  else vm.runInContext(match[2],context);
}
setImmediate(()=>{
 const initial={language:document.documentElement.lang,html:nodes.app.innerHTML,title:document.title};
 // Trigger the real delegated click handler, not a copied render implementation.
 const click=lang=>nodes['language-control'].handlers.click({target:{closest(){return buttons.find(b=>b.dataset.language===lang)}}});
 click('zh-TW');const zh=nodes.app.innerHTML;
 click('en');const en=nodes.app.innerHTML;
 document.handlers['radar-map-event']({detail:{eventId:'synthetic-event-1'}});
 console.log(JSON.stringify({initial,zh,en,requests,storage,unchanged:original===JSON.stringify(input.view),pressed:buttons.map(b=>b.attributes['aria-pressed']),busy:nodes.app.attributes['aria-busy'],popupFocus:popupTarget.focused,popupScroll:popupTarget.scrolled,popupTimeline:popupTarget.timeline.open,popupProvenance:popupTarget.provenance.open}));
});
