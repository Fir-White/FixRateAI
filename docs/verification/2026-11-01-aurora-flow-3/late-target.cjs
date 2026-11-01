const {chromium,expect}=require('../../../frontend/node_modules/@playwright/test');
const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
  await context.route('**/*',route=>new URL(route.request().url()).pathname.startsWith('/api/')?route.fulfill({status:401,json:{detail:'QA session'}}):route.continue());
  await context.addInitScript(()=>{let time=0,next=0;const queue=new Map();window.requestAnimationFrame=callback=>{const id=++next;queue.set(id,callback);return id;};window.cancelAnimationFrame=id=>queue.delete(id);window.__advance=frames=>{for(let i=0;i<frames;i++){time+=1000/60;const callbacks=[...queue.values()];queue.clear();callbacks.forEach(callback=>callback(time));}};});
  const page=await context.newPage();await page.goto(process.env.FIXRATE_BASE_URL+'/login');await expect(page.getByLabel('Email',{exact:true})).toBeVisible();await page.waitForTimeout(100);
  const paths=()=>page.locator('[data-aurora-ribbon]').evaluateAll(elements=>elements.map(e=>e.getAttribute('d')));
  const frames=[];
  for(let i=0;i<8;i++){await page.evaluate(()=>window.__advance(480));frames.push(await paths());}
  expect(new Set(frames.map(frame=>frame[0])).size).toBe(8);expect(new Set(frames.map(frame=>frame[1])).size).toBe(8);
  await expect(page.getByRole('dialog')).toHaveCount(0);await page.screenshot({path:path.join(__dirname,'controlled-high-motion-64s.png')});
  fs.writeFileSync(path.join(__dirname,'eight-second-targets.json'),JSON.stringify({status:'PASS',times:'8,16,24,32,40,48,56,64 seconds',samplingIntervalSeconds:8,note:'Sampling interval is independent of the motion target duration.',frames},null,2));
  console.log('Eight samples spaced8seconds apart distinct for both ribbons; clean64second screenshot saved.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

