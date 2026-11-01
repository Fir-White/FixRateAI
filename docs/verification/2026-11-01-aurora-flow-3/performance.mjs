import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { writeFileSync, mkdirSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
const require = createRequire(new URL('../../../frontend/package.json', import.meta.url));
const { chromium } = require('@playwright/test');
const label=process.argv[2]||'review';
const out=new URL('./',import.meta.url);
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
await context.addInitScript(()=>{
 const native=window.requestAnimationFrame.bind(window); window.__auroraPerf={calls:[],gaps:[],last:null};
 window.requestAnimationFrame=callback=>native(time=>{const start=performance.now();try{callback(time)}finally{window.__auroraPerf.calls.push(performance.now()-start)}});
 let last; const observe=time=>{if(last!==undefined)window.__auroraPerf.gaps.push(time-last);last=time;native(observe)};native(observe);
});
const page=await context.newPage();await page.route('**/*',route=>new URL(route.request().url()).pathname.startsWith('/api/')?route.fulfill({status:401,json:{detail:'Not authenticated'}}):route.continue());
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:5174/login');await page.locator('.auth-form').waitFor();await page.waitForTimeout(1500);
const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');
const results=[];
const scenarios=process.argv[3] === 'stress' ? [[1440,900,4,30]] : [[1440,900,1,30],[1920,1080,1,12],[1440,900,4,12]];
for(const [width,height,cpu,seconds] of scenarios) {
 await page.setViewportSize({width,height});await cdp.send('Emulation.setCPUThrottlingRate',{rate:cpu});await page.waitForTimeout(1000);
 await page.evaluate(()=>{window.__auroraPerf.calls=[];window.__auroraPerf.gaps=[]});
 const before=(await cdp.send('Performance.getMetrics')).metrics;
 const pathsBefore=await page.locator('[data-aurora-ribbon]').evaluateAll(es=>es.map(e=>e.getAttribute('d')));
 const start=performance.now();await page.waitForTimeout(seconds*1000);const wall=(performance.now()-start)/1000;
 const after=(await cdp.send('Performance.getMetrics')).metrics;
 const perf=await page.evaluate(()=>{const p=window.__auroraPerf;const stats=a=>{a.sort((x,y)=>x-y);return {count:a.length,mean:a.reduce((s,x)=>s+x,0)/a.length,p50:a[Math.floor(a.length*.5)],p95:a[Math.floor(a.length*.95)],p99:a[Math.floor(a.length*.99)],max:Math.max(...a),over25ms:a.filter(x=>x>25).length,over50ms:a.filter(x=>x>50).length}};return {callbacks:stats(p.calls),frames:stats(p.gaps),motion:document.querySelector('.auth-aurora').dataset.motion}});
 const delta={};for(const name of ['TaskDuration','ScriptDuration','LayoutDuration','RecalcStyleDuration','LayoutCount','RecalcStyleCount'])delta[name]=(after.find(m=>m.name===name)?.value||0)-(before.find(m=>m.name===name)?.value||0);
 const pathsAfter=await page.locator('[data-aurora-ribbon]').evaluateAll(es=>es.map(e=>e.getAttribute('d')));
 results.push({width,height,cpuThrottle:cpu,wallSeconds:wall,...perf,cdpDelta:delta,pathChanged:pathsAfter.map((v,i)=>v!==pathsBefore[i])});
 if(cpu===1)await page.screenshot({path:fileURLToPath(new URL(`${label}-${width}x${height}.png`,out))});
 console.log(JSON.stringify(results.at(-1)));
}
await cdp.send('Emulation.setCPUThrottlingRate',{rate:1});
const data={label,date:new Date().toISOString(),browser:browser.version(),headless:true,url:page.url(),results,errors};
writeFileSync(new URL(`${label}-performance.json`,out),JSON.stringify(data,null,2));await browser.close();




