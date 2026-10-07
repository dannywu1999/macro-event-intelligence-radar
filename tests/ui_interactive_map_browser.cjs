// Real Edge, actual HTTP routes, actual vendored MapLibre. No collector execution.
const fs=require('node:fs'),assert=require('node:assert/strict');const input=JSON.parse(fs.readFileSync(0,'utf8'));const {chromium}=require(input.playwright);
(async()=>{const browser=await chromium.launch({executablePath:input.browser,headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--use-angle=swiftshader','--enable-unsafe-swiftshader']});let cases=0,basemap='NOT_REQUESTED',mapResponses=[],mapFailures=[];
async function contextFor(mode,width){const context=await browser.newContext({viewport:{width,height:1000},hasTouch:width<500});
 await context.route('**/*',async route=>{const url=route.request().url();
  if(url.startsWith(input.origin+'/'))return route.continue();
  if(mode==='synthetic-map'&&url==='https://tiles.openfreemap.org/styles/liberty')return route.fulfill({contentType:'application/json',body:JSON.stringify({version:8,sources:{},layers:[{id:'synthetic-offline-background',type:'background',paint:{'background-color':'#d9ecf4'}}]})});
  if(mode==='real-map'&&new URL(url).hostname==='tiles.openfreemap.org')return route.continue();
  return route.abort();});return context;}
try{
 for(const mode of ['blocked-map','synthetic-map'])for(const language of ['en','zh-TW'])for(const width of [375,430,1024,1366,1440]){
  const context=await contextFor(mode,width),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(input.origin+'/#/feed');await page.locator('.event-card').first().waitFor();await page.locator('[data-language="'+language+'"]').click();
  await page.waitForFunction(expected=>document.querySelector('.map-provider-state')?.dataset.mapState===expected,mode==='blocked-map'?'FALLBACK':'READY',{timeout:25000});
  const view=await page.evaluate(async()=>await(await fetch('/api/app/radar')).json());assert.equal(view.items.length,28);assert.equal(view.events.length,28);assert.equal(view.official_evidence.length,2);assert.ok(view.events.every(e=>e.verification_status==='UNVERIFIED_NEWS'));
  const event=view.events.find(e=>e.event_id===input.eventId),market=event.market_reality;assert.equal(market.snapshot_status,'PARTIAL');assert.equal(market.instruments.find(i=>i.symbol==='SPY').price_or_level,499);assert.equal(market.instruments.find(i=>i.symbol==='VIX').price_or_level,16);
  assert.equal(market.instruments.find(i=>i.symbol==='QQQ').price_or_level,null);assert.equal(market.instruments.find(i=>i.symbol==='DXY').price_or_level,null);assert.equal(market.instruments.find(i=>i.symbol==='US10Y').price_or_level,null);
  const card=page.locator('.event-card[data-event-id="'+input.eventId+'"]'),panel=card.locator('.market-reality');await panel.locator('summary').click();const text=await panel.innerText();for(const token of ['SPY','QQQ','VIX','DXY','US10Y','NO_POINT_IN_TIME_SOURCE','Synthetic offline fixture','499','16'])assert.ok(text.includes(token),token);assert.match(text,language==='en'?/Unknown/:/未知/);assert.match(text,language==='en'?/Market timestamp/:/市場時間/);assert.match(text,language==='en'?/System knowledge time/:/系統已知時間/);assert.ok(event.official_evidence_count>0);
  if(mode==='blocked-map'){assert.equal(await page.locator('.map-svg-fallback').isVisible(),true);assert.ok(await page.locator('.map-svg-fallback [data-map-event]').count()>0);}
  else {assert.equal(await page.locator('.map-svg-fallback').isVisible(),false);assert.ok(await page.locator('.radar-map-pin').count()>0);
   // Overview anchors can overlap (e.g. Europe/Euro Area). Exercise an actually
   // exposed marker, then keyboard focus on every ring; never force-click pins.
   await page.mouse.move(0,0);await page.locator('.interactive-world-map').scrollIntoViewIfNeeded();
   if(await page.locator('.maplibregl-popup-close-button').count())await page.locator('.maplibregl-popup-close-button').click();
   const exposed=await page.locator('.radar-map-pin').evaluateAll(nodes=>nodes.findIndex(n=>{const r=n.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('.radar-map-pin')===n}));assert.ok(exposed>=0);const marker=page.locator('.radar-map-pin').nth(exposed);const kind=await marker.getAttribute('data-marker-kind');
   if(width<500)await marker.tap();else await marker.hover();await page.locator('.radar-map-popup').waitFor();const popup=page.locator('.radar-map-popup');assert.match(await popup.innerText(),kind==='context'?(language==='en'?/not event location/:/非事件地點/):(language==='en'?/headquarters \/ reference/:/總部／參照背景/));
   const target=popup.locator('[data-map-event]').first();const id=await target.getAttribute('data-map-event');await target.click();assert.equal(await page.locator('.event-card:focus').getAttribute('data-event-id'),id);assert.equal(await page.locator('.event-card:focus .provenance').first().getAttribute('open'),'');
   for(const ring of await page.locator('.radar-map-pin.context').all()){await ring.focus();await page.keyboard.press('Enter');assert.ok(await page.locator('.radar-map-popup').count()>0);}
   for(const kind of ['verified','context','institution','all']){await page.locator('[data-map-filter="'+kind+'"]').click();await page.waitForFunction(()=>document.querySelector('.map-provider-state')?.dataset.mapState==='READY');const kinds=await page.locator('.radar-map-pin').evaluateAll(nodes=>nodes.map(n=>n.dataset.markerKind));assert.ok(kinds.every(k=>kind==='all'||k===kind));}
  }
  assert.ok(await page.locator('.map-attribution').isVisible());assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,mode+' '+width);assert.deepEqual(errors,[]);
  if(width===375)await page.screenshot({path:input.screenshot+'-'+mode+'-'+language+'.png',fullPage:false});cases++;await context.close();
 }
 if(input.allowNetwork){const context=await contextFor('real-map',1440),page=await context.newPage();page.on('response',r=>{if(new URL(r.url()).hostname==='tiles.openfreemap.org')mapResponses.push({url:r.url(),status:r.status()})});page.on('requestfailed',r=>{if(new URL(r.url()).hostname==='tiles.openfreemap.org')mapFailures.push({url:r.url(),error:r.failure()?.errorText})});await page.goto(input.origin+'/#/feed');await page.waitForFunction(()=>['READY','FALLBACK'].includes(document.querySelector('.map-provider-state')?.dataset.mapState),null,{timeout:30000});const state=await page.locator('.map-provider-state').getAttribute('data-map-state');
  if(state==='READY'){
   assert.ok(await page.locator('.maplibregl-canvas').count()>0);await page.locator('.world-map').scrollIntoViewIfNeeded();await page.waitForTimeout(3000);basemap='REAL_STYLE_READY';
   await page.locator('.world-map').screenshot({path:input.screenshot+'-real-provider.png'});
   const rings=page.locator('.radar-map-pin.context');await rings.last().focus();await page.keyboard.press('Enter');const target=page.locator('.radar-map-popup [data-map-event]').first();const id=await target.getAttribute('data-map-event');await target.click();assert.equal(await page.locator('.event-card:focus').getAttribute('data-event-id'),id);
   if(await page.locator('.maplibregl-popup-close-button').count())await page.locator('.maplibregl-popup-close-button').click();
   await page.locator('.world-map').scrollIntoViewIfNeeded();for(let i=0;i<3;i++){await page.locator('.maplibregl-ctrl-zoom-in').click();await page.waitForTimeout(400);}
   const canvas=page.locator('.maplibregl-canvas'),box=await canvas.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+70,box.y+box.height/2+25,{steps:10});await page.mouse.up();await page.waitForTimeout(1500);
   await page.locator('.world-map').screenshot({path:input.screenshot+'-real-provider-zoom.png'});
  }else{assert.equal(await page.locator('.map-svg-fallback').isVisible(),true);basemap='PROVIDER_BLOCKED_FALLBACK_VERIFIED';await page.locator('.world-map').screenshot({path:input.screenshot+'-real-provider.png'});}
  await context.close();}
 console.log(JSON.stringify({status:'PASS',browser:'REAL_EDGE',offline_cases:cases,basemap,mapResponses,mapFailures,markerInteractions:'REAL_MAPLIBRE_WITH_SYNTHETIC_STYLE',languages:['en','zh-TW'],widths:[375,430,1024,1366,1440],market_data:'EXPLICITLY_SYNTHETIC',externalDomainsAllowed:input.allowNetwork?['tiles.openfreemap.org']:[],collectorStarted:false}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
