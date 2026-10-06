// Optional local visual acceptance using an already-installed browser. No install.
const fs=require('node:fs'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const {chromium}=require(input.playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:input.browser,headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});
 const blocked=[],results=[];
 try{
  for(const locale of ['en-US','zh-TW']){
   const context=await browser.newContext({locale});
   await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin===input.origin)return route.continue();blocked.push(url.href);return route.abort()});
   const page=await context.newPage();
   await page.goto(input.origin+'/#/feed');
   await page.locator('.event-card').first().waitFor();
   assert.equal(await page.locator('.event-card').count(),(input.counts||[5,5,1])[1]);
   assert.equal(await page.locator('.official-record').count(),1);
   if(input.live)assert.equal(await page.locator('[data-live-status]').getAttribute('data-live-status'),'LIVE');
   assert.deepEqual(await page.locator('.count').allTextContents(),(input.counts||[5,5,1]).map(String));
   assert.equal(await page.locator('[data-event-status="UNVERIFIED_NEWS"]').count(),(input.counts||[5,5,1])[1]);
   assert.equal(await page.locator('[data-evidence-status="OFFICIAL_CONFIRMED"]').count(),1);
   assert.equal(await page.locator('.official-panel').getAttribute('open'),'');
   assert.equal(await page.locator('.no-evidence').count(),(input.counts||[5,5,1])[1]-1);
   assert.ok((await page.locator('.official-record').innerText()).includes(locale==='zh-TW'?'發布時間: 未知':'Published: Unknown'));
   assert.ok((await page.locator('.official-record').innerText()).includes('Crude oil prices and refinery margins generally increased throughout the third quarter'));
   assert.equal(await page.locator('.event-timeline').count(),(input.counts||[5,5,1])[1]);
   assert.equal(await page.locator('.event-timeline[open]').count(),1);
   const timeline=page.locator('.has-evidence .event-timeline');
   assert.deepEqual(await timeline.locator('[data-timeline-type]').evaluateAll(nodes=>nodes.map(n=>n.dataset.timelineType)),['NEWS_DISCOVERED','OFFICIAL_EVIDENCE']);
   assert.equal(await timeline.locator('[data-timeline-type="OFFICIAL_EVIDENCE"]').getAttribute('data-timestamp-role'),'EVIDENCE_FIRST_SEEN_AT');
   assert.ok((await timeline.innerText()).includes(locale==='zh-TW'?'發布時間: 未知':'Published: Unknown'));
   assert.ok((await timeline.innerText()).includes('UNVERIFIED_NEWS'));
   assert.ok((await timeline.innerText()).includes('UTC'));
   for(const width of [375,430,1024,1366,1440]){
    await page.setViewportSize({width,height:1000});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${locale}: overflow at ${width}`);
    assert.ok(await page.locator('.language-control').isVisible());
    assert.ok(await page.locator('.official-panel').isVisible());
    assert.ok(await timeline.locator('.timeline-list').isVisible());
    results.push(`${locale}/${width}:PASS`);
    if(width===1440&&locale==='zh-TW'&&input.screenshot)await page.screenshot({path:input.screenshot,fullPage:true});
   }
   // Language buttons are operable by keyboard and remain selected after reload.
   const button=page.locator('[data-language="'+(locale==='zh-TW'?'en':'zh-TW')+'"]');
   await button.focus();await page.keyboard.press('Enter');
   const selected=locale==='zh-TW'?'en':'zh-TW';
   assert.equal(await page.locator('html').getAttribute('lang'),selected);
   await page.reload();await page.locator('.event-card').first().waitFor();
   assert.equal(await page.locator('html').getAttribute('lang'),selected);
   const summary=page.locator('.event-main .provenance summary').first();
   await summary.focus();await page.keyboard.press('Enter');
   assert.equal(await page.locator('.event-main .provenance').first().getAttribute('open'),'');
   const compact=page.locator('.event-card:not(.has-evidence) .event-timeline').first();
   assert.equal(await compact.getAttribute('open'),null);
   await compact.locator('summary').focus();await page.keyboard.press('Enter');
   assert.equal(await compact.getAttribute('open'),'');
   assert.equal(await compact.locator('[data-timeline-type="NEWS_DISCOVERED"]').count(),1);
   assert.equal(await compact.locator('[data-timeline-type="OFFICIAL_EVIDENCE"]').count(),0);
   await page.keyboard.press('Enter');assert.equal(await compact.getAttribute('open'),null);
   results.push(`${locale}/keyboard-persistence-disclosure-timeline:PASS`);
   await context.close();
  }
  assert.deepEqual(blocked,[],'UI must not attempt external resources');
  console.log(JSON.stringify({results,externalRequests:blocked,screenshot:input.screenshot,closed:true}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
