// Actual client grouping/popup code; synthetic DOM and MapLibre boundary, no network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Node {constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.handlers={};this.textContent='';this.hidden=false;this.isConnected=true;}appendChild(n){this.children.push(n);return n}setAttribute(k,v){this[k]=v}addEventListener(k,f){this.handlers[k]=f}}
const document={createElement:t=>new Node(t),head:new Node('head')};
let map,markers=[],popup,removed=0;
class MapBoundary {constructor(options){this.options=options;this.handlers={};map=this}on(k,f){this.handlers[k]=f}addControl(){}resize(){}remove(){removed++}getCenter(){return [12,25]}getZoom(){return 1}}
class MarkerBoundary {constructor(o){this.element=o.element;markers.push(this)}setLngLat(p){this.coordinates=p;return this}addTo(){return this}}
class PopupBoundary {setLngLat(){return this}setDOMContent(n){this.node=n;return this}addTo(){popup=this;return this}remove(){return this}}
const window={maplibregl:{Map:MapBoundary,Marker:MarkerBoundary,Popup:PopupBoundary,NavigationControl:class{},AttributionControl:class{}}};
const context=vm.createContext({window,document,setTimeout:()=>1,clearTimeout(){},console});
vm.runInContext(fs.readFileSync(input.client,'utf8'),context);const api=window.RadarWorldMap;
const groups=api.groups(input.events),before=JSON.stringify(input.events);
const data=api.payload(groups.find(g=>g.kind==='context'),'zh-TW');const node=api.popupNode(data);
const canvas=new Node('div'),fallback=new Node('div'),state=new Node('p');const host={querySelector:s=>({'.interactive-world-map':canvas,'.map-svg-fallback':fallback,'.map-provider-state':state}[s])};
api.mount(host,{events:input.events},'zh-TW','all');
setImmediate(()=>{map.handlers.load();const ready=state.dataset.mapState;
 const marker=markers.find(m=>m.element.dataset.markerKind==='context');marker.element.handlers.mouseenter();const hovered=popup.node.children.map(n=>n.textContent);
 marker.element.handlers.focus();marker.element.handlers.click();const clicked=popup.node.children.find(n=>n.tag==='button').dataset.mapEvent;
 const popupTags=node.children.map(n=>n.tag);map.handlers.error();
 api.mount(host,{events:input.events},'en','all');
 setImmediate(()=>console.log(JSON.stringify({groups,data,ready,hovered,clicked,popupTags,unchanged:before===JSON.stringify(input.events),fallback:!fallback.hidden&&canvas.hidden,state:state.dataset.mapState,removed,markerCount:markers.length})))
});
