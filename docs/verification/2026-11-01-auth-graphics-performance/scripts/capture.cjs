const {chromium,expect}=require('../../../../frontend/node_modules/@playwright/test');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.FIXRATE_BASE_URL||'http://127.0.0.1:5174';
const label=process.argv[2]||'candidate';
const out=path.join(__dirname, label);fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const results={label,browser:await browser.version(),base,scenes:[],errors:[]};
 try{
  for(const [width,height,phases] of [[1440,900,[0,6,15,31]],[1920,1080,[0,15]],[1366,768,[0,15]],[390,844,[0]]]){
   const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1});
   await context.route('**/*',route=>new URL(route.request().url()).pathname.startsWith('/api/')?route.fulfill({status:401,json:{detail:'Not authenticated'}}):route.continue());
   await context.addInitScript(()=>{
    const clock=window.__qaClock={now:0,pending:new Map(),next:0};
    window.requestAnimationFrame=cb=>{const id=++clock.next;clock.pending.set(id,cb);return id;};
    window.cancelAnimationFrame=id=>clock.pending.delete(id);
    clock.advance=frames=>{for(let i=0;i<frames;i++){clock.now+=1000/60;const callbacks=[...clock.pending.values()];clock.pending.clear();for(const callback of callbacks)callback(clock.now)}return clock.pending.size;};
   });
   const page=await context.newPage();page.on('pageerror',e=>results.errors.push(e.message));
   await page.goto(`${base}/login`);await expect(page.getByLabel('Email',{exact:true})).toBeVisible();
   await expect(page.locator('.auth-aurora')).toBeVisible();await page.waitForTimeout(350);
   let last=0;
   await page.evaluate(()=>window.__qaClock.advance(1));
   for(const seconds of phases){
    const delta=Math.round((seconds-last)*60);last=seconds;
    if(delta)await page.evaluate(n=>window.__qaClock.advance(n),delta);
    const sample=await page.evaluate(()=>({motion:document.querySelector('.auth-aurora').dataset.motion,paths:[...document.querySelectorAll('[data-aurora-ribbon]')].map(e=>e.getAttribute('d')),pending:window.__qaClock.pending.size,logos:[...document.querySelectorAll('.auth-brand img,.auth-aurora__logo img')].map(e=>({box:e.getBoundingClientRect().toJSON(),src:e.getAttribute('src'),transform:getComputedStyle(e).transform,animation:getComputedStyle(e).animationName}))}));
    const file=`${width}x${height}-${seconds}s.png`;await page.screenshot({path:path.join(out,file),animations:'disabled'});
    results.scenes.push({width,height,seconds,file,...sample});
    console.log(`${label}: ${width}x${height} t=${seconds}s, motion=${sample.motion}, pending=${sample.pending}`);
   }
   await context.close();
  }
  expect(results.errors).toEqual([]);results.status='PASS';
 }catch(e){results.status='FAIL';results.error=e.stack;throw e}
 finally{fs.writeFileSync(path.join(out,'capture.json'),JSON.stringify(results,null,2));await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
