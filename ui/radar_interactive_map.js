/* A7.1: geographic navigation only. Never reverse-geocode contextual anchors. */
(function(global){'use strict';
const STYLE='https://tiles.openfreemap.org/styles/liberty';
let libraryPromise=null,failed=false,active=null,camera=null;
function groups(events){const result=new Map();
 function add(kind,key,lat,lon,en,zh,event,legacy=false){
  if(typeof lat!=='number'||typeof lon!=='number'||!Number.isFinite(lat)||!Number.isFinite(lon)||lat<-90||lat>90||lon<-180||lon>180)return;
  const id=kind+':'+key;if(!result.has(id))result.set(id,{id,kind,lat,lon,en,zh,members:[],legacy});
  const group=result.get(id);if(!group.members.some(e=>e.event_id===event.event_id))group.members.push(event);
 }
 for(const event of events||[]){
  for(const p of event.event_geography?.geography||[])if(event.event_geography.status==='KNOWN')add('verified',p.latitude+':'+p.longitude,p.latitude,p.longitude,p.place_name,p.place_name,event);
  const c=event.context_geography;
  if(c?.status==='INFERRED'&&c.region_id!=='global')add('context',c.region_id,c.centroid_lat,c.centroid_lon,c.display_name,c.display_name_zh,event);
  for(const i of event.institution_context||[])add('institution',i.institution_id,i.context_lat,i.context_lon,i.short_name+' · '+i.headquarters,i.short_name+' · '+i.headquarters_zh,event);
  for(const p of event.geography||[])if(event.geography_status==='KNOWN'&&p.evidence_type==='CURATED_PRESENTATION'&&typeof p.geography_id==='string')add('context','legacy-'+p.latitude+':'+p.longitude,p.latitude,p.longitude,p.place_name,p.place_name,event,true);
 }
 return [...result.values()].sort((a,b)=>a.id.localeCompare(b.id));
}
function payload(group,language){const zh=language==='zh-TW';return {
 name:group.en,name_zh:group.zh,kind:group.kind,legacy:group.legacy,event_count:group.members.length,
 events:group.members.slice(0,3).map(e=>({event_id:e.event_id,title:e.event_title,
 source:(e.source_names||[]).join(' · '),institution:(e.institution_context||[]).map(i=>i.short_name).join(' · '),
 confidence:e.context_geography?.confidence||null,method:e.context_geography?.method||null})),
 more:Math.max(0,group.members.length-3),language:zh?'zh-TW':'en'};}
function semantic(kind,zh,legacy){return legacy?(zh?'人工展示位置':'Curated presentation point'):kind==='verified'?(zh?'來源支持的事件位置':'Source-supported event location'):kind==='institution'?(zh?'機構總部／參照背景':'Institution headquarters / reference'):(zh?'推測地理脈絡；非事件地點':'Inferred context; not event location');}
function contextTerm(code,zh){const terms={HIGH:['高','High'],MEDIUM:['中','Medium'],LOW:['低','Low'],EXPLICIT_CONTEXT_MENTION:['明確提及區域','Explicit region mention'],INSTITUTION_JURISDICTION:['由機構管轄範圍推定','Institution jurisdiction inference'],MULTI_REGION:['多個區域','Multiple regions']};return terms[code]?(zh?terms[code][0]:terms[code][1])+' ('+code+')':code;}
function popupNode(data){const zh=data.language==='zh-TW',root=document.createElement('section');root.className='radar-map-popup';
 function text(tag,value){const n=document.createElement(tag);n.textContent=value;root.appendChild(n);return n;}
 text('strong',zh?(data.name_zh||data.name):(data.name||data.name_zh));
 text('p',data.event_count+' '+(zh?'相關事件':'related events'));
 for(const e of data.events){const button=text('button',e.title|| (zh?'未知':'Unknown'));button.type='button';button.dataset.mapEvent=e.event_id;button.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();document.dispatchEvent(new CustomEvent('radar-map-event',{detail:{eventId:e.event_id}}))});
  if(e.source)text('p',(zh?'新聞來源：':'News source: ')+e.source);
  if(e.institution)text('p',(zh?'機構參照：':'Institution reference: ')+e.institution);
  if(e.confidence||e.method)text('p',(zh?'推測脈絡：':'Inferred context: ')+[e.confidence,e.method].filter(Boolean).map(code=>contextTerm(code,zh)).join(' · '));}
 text('p',(zh?'地圖標記類型：':'Map marker type: ')+semantic(data.kind,zh,data.legacy));
 if(data.more)text('p','+ '+data.more+' '+(zh?'其他事件':'more'));
 return root;
}
function library(){if(libraryPromise)return libraryPromise;
 libraryPromise=new Promise((resolve,reject)=>{
  if(global.maplibregl){resolve(global.maplibregl);return;}
  const script=document.createElement('script');script.src='/ui/vendor/maplibre-gl.js';
  const timer=setTimeout(()=>{script.remove();reject(Error('MAP_LIBRARY_UNAVAILABLE'));},12000);
  script.onload=()=>{clearTimeout(timer);global.maplibregl?resolve(global.maplibregl):reject(Error('MAP_LIBRARY_UNAVAILABLE'));};
  script.onerror=()=>{clearTimeout(timer);reject(Error('MAP_LIBRARY_UNAVAILABLE'));};document.head.appendChild(script);
 });return libraryPromise;
}
function unmount(){if(active){try{camera={center:active.getCenter(),zoom:active.getZoom()};active.remove();}catch{}active=null;}}
function mount(host,view,language,filter){
 if(!host||typeof host.querySelector!=='function')return;unmount();
 const canvas=host.querySelector('.interactive-world-map'),fallback=host.querySelector('.map-svg-fallback'),state=host.querySelector('.map-provider-state');
 if(!canvas)return;const zh=language==='zh-TW';
 function unavailable(){failed=true;if(active){try{active.remove();}catch{}active=null;}canvas.hidden=true;if(fallback)fallback.hidden=false;
  state.textContent=zh?'互動底圖無法取得；保留離線示意圖與事件清單。':'Interactive basemap unavailable; offline schematic and event list remain available.';state.dataset.mapState='FALLBACK';}
 if(failed){unavailable();return;}
 state.textContent=zh?'載入互動底圖；離線示意圖仍可使用。':'Loading interactive basemap; offline schematic remains usable.';state.dataset.mapState='LOADING';
 library().then(lib=>{
  if(!canvas.isConnected||failed)return;
  canvas.hidden=false;
  const overviewZoom=Math.min(1.15,Math.log2((canvas.clientWidth||512)/512));
  const map=new lib.Map({container:canvas,style:STYLE,center:camera?.center||[12,25],zoom:camera?.zoom??overviewZoom,minZoom:-1.5,
    attributionControl:false,renderWorldCopies:false,maxZoom:12,cooperativeGestures:true});active=map;
  map.addControl(new lib.NavigationControl({showCompass:false}));map.addControl(new lib.AttributionControl({compact:false}));
  let loaded=false;const timer=setTimeout(()=>{if(!loaded&&canvas.isConnected)unavailable();},18000);
  map.on('error',()=>{
   if(!canvas.isConnected)return;
   // A single tile or glyph failure after load must not hide an otherwise usable map.
   if(loaded){state.textContent=zh?'部分底圖圖磚無法取得；互動地圖與事件清單仍可使用。':'Some basemap tiles are unavailable; the interactive map and event list remain usable.';state.dataset.mapState='DEGRADED';return;}
   clearTimeout(timer);unavailable();
  });
  map.on('load',()=>{if(failed||!canvas.isConnected)return;loaded=true;clearTimeout(timer);if(fallback)fallback.hidden=true;
   state.textContent=zh?'OpenFreeMap 互動底圖；脈絡錨點不是事件地點。':'OpenFreeMap interactive basemap; context anchors are not event locations.';state.dataset.mapState='READY';
   let shownPopup=null;
   for(const g of groups(view.events).filter(g=>filter==='all'||g.kind===filter)){
    const button=document.createElement('button');button.type='button';button.className='radar-map-pin '+g.kind;button.dataset.markerKind=g.kind;button.dataset.markerReference=zh?g.zh:g.en;
    button.textContent=g.kind==='institution'?'◆':g.kind==='verified'?'●':'◉';button.setAttribute('aria-label',(zh?g.zh:g.en)+' · '+semantic(g.kind,zh,g.legacy)+' · '+g.members.length);
    const popup=new lib.Popup({closeButton:true,closeOnClick:false,focusAfterOpen:false,maxWidth:'min(330px, 40vw)',offset:24}).setLngLat([g.lon,g.lat]);
    function show(){if(shownPopup&&shownPopup!==popup)shownPopup.remove();shownPopup=popup;popup.setDOMContent(popupNode(payload(g,language))).addTo(map);}
    // Touch browsers can synthesize mouseenter before completing a tap. Do not
    // let a hover popup intercept that tap; keyboard focus remains supported.
    button.addEventListener('mouseenter',()=>{if(!global.matchMedia||global.matchMedia('(hover: hover)').matches)show();});button.addEventListener('focus',show);button.addEventListener('click',show);
    new lib.Marker({element:button}).setLngLat([g.lon,g.lat]).addTo(map);
   }map.resize();
  });
 }).catch(()=>{if(canvas.isConnected)unavailable();});
}
global.RadarWorldMap={groups,payload,popupNode,mount,unmount,style:STYLE};
})(window);
