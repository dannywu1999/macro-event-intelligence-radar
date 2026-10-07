// Actual Chromium rendering of the local API; no fabricated network responses.
const fs=require('node:fs'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const {chromium}=require(input.playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:input.browser,headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});
 let checks=0;
 try{
  for(const locale of ['en-US','zh-TW'])for(const width of [375,1024,1440]){
   const context=await browser.newContext({locale,viewport:{width,height:1000}});
   await context.route('**/*',route=>{const url=route.request().url();return url.startsWith(input.origin+'/')?route.continue():route.abort()});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.goto(input.origin+'/#/feed');await page.locator('.event-card').first().waitFor();
   assert.equal(await page.locator('.event-card').count(),input.events);assert.equal(await page.locator('.official-record').count(),2);assert.equal(await page.locator('.macroview-preview').count(),input.events);
   assert.equal(await page.locator('.expectation-panel.unlinked-expectations').count(),1);assert.equal(await page.locator('.event-card[data-event-status="UNVERIFIED_NEWS"]').count(),input.events);
   assert.equal(await page.locator('[data-evidence-status="OFFICIAL_CONFIRMED"]').count(),2);
   for(const lang of ['en','zh-TW']){
    await page.locator('[data-language="'+lang+'"]').click();assert.equal(await page.locator('html').getAttribute('lang'),lang);
    const card=page.locator('.event-card[data-event-id="'+input.ecbId+'"]');await card.locator('.macroview-preview > summary').click();
    assert.match(await card.locator('.macroview-preview').innerText(),lang==='en'?/not a persisted frozen snapshot/:/並非已持久化/);
    assert.match(await card.locator('.macroview-preview').innerText(),lang==='en'?/Partial proposition-level official evidence/:/部分命題具有官方證據/);
    assert.match(await card.locator('.official-panel').innerText(),/European Central Bank/);assert.match(await card.locator('.official-panel').innerText(),lang==='en'?/Unknown/:/未知/);
    await card.locator('.expectation-panel > summary').click();assert.match(await card.locator('.expectation-panel').innerText(),lang==='en'?/do not verify facts/:/不代表事實/);
    assert.equal(await card.locator('.expectation-panel .confirmed').count(),0);
    const unlinked=page.locator('.unlinked-expectations');await unlinked.locator('summary').click();assert.equal(await unlinked.locator('.expectation-record').count(),input.unlinked);
    assert.equal(await unlinked.locator('a[href^="https://polymarket.com/event/"]').count(),input.links);
    if(!await card.locator('.event-timeline').evaluate(el=>el.open))await card.locator('.event-timeline > summary').click();await card.locator('.timeline-entry').first().waitFor({state:'visible'});assert.equal(await card.locator('.timeline-entry').count(),2);
    assert.match(await card.innerText(),/UNVERIFIED_NEWS/);assert.match(await card.innerText(),/UNKNOWN|Unknown|未知/);
    assert.equal(await page.locator('.world-map [data-map-event]').count(),0);
    const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(bounds.scroll<=bounds.width+1,JSON.stringify(bounds));checks++;
   }
   assert.deepEqual(errors,[]);await context.close();
  }
 }finally{await browser.close()}
 console.log(JSON.stringify({real_browser:'Edge Chromium',groups:checks,network:'loopback only',all_pass:true}));
})().catch(e=>{console.error(e);process.exit(1)});
