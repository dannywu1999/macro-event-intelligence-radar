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
   assert.equal(await page.locator('.event-card').count(),5);
   assert.equal(await page.locator('.official-record').count(),1);
   assert.deepEqual(await page.locator('.count').allTextContents(),['5','5','1']);
   assert.equal(await page.locator('[data-event-status="UNVERIFIED_NEWS"]').count(),5);
   assert.equal(await page.locator('[data-evidence-status="OFFICIAL_CONFIRMED"]').count(),1);
   assert.equal(await page.locator('.official-panel').getAttribute('open'),'');
   assert.equal(await page.locator('.no-evidence').count(),4);
   assert.ok((await page.locator('.official-record').innerText()).includes(locale==='zh-TW'?'發布時間: 未知':'Published: Unknown'));
   assert.ok((await page.locator('.official-record').innerText()).includes('Crude oil prices and refinery margins generally increased throughout the third quarter'));
   for(const width of [375,430,1024,1366,1440]){
    await page.setViewportSize({width,height:1000});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${locale}: overflow at ${width}`);
    assert.ok(await page.locator('.language-control').isVisible());
    assert.ok(await page.locator('.official-panel').isVisible());
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
   results.push(`${locale}/keyboard-persistence-disclosure:PASS`);
   await context.close();
  }
  assert.deepEqual(blocked,[],'UI must not attempt external resources');
  console.log(JSON.stringify({results,externalRequests:blocked,screenshot:input.screenshot,closed:true}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
