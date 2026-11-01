const {chromium,expect}=require('../../../../frontend/node_modules/@playwright/test');const esbuild=require('../../../../frontend/node_modules/esbuild');const fs=require('node:fs'),path=require('node:path');
const base=process.env.FIXRATE_BASE_URL||'http://127.0.0.1:5174',out=path.join(__dirname,'candidate2-144hz');fs.mkdirSync(out,{recursive:true});
async function bundle(file){const b=await esbuild.build({entryPoints:[path.join(__dirname,'candidate-source',file)],bundle:true,write:false,platform:'browser',format:'esm',target:'es2022'});return Buffer.from(b.outputFiles[0].contents).toString('base64')}
async function toggle(page){await page.locator('.auth-footer button').click();await page.locator('.auth-motion-setting input').press('Space');await page.keyboard.press('Escape')}
async function hash(page){return page.locator('canvas[data-aurora-particles]').evaluate(c=>{const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let h=2166136261;for(let i=0;i<a.length;i++)h=Math.imul(h^a[i],16777619);return {width:c.width,height:c.height,hash:h>>>0}})}
(async()=>{const [oldCode,geometryCode]=await Promise.all([bundle('canvasRenderer.ts'),bundle('ribbonGeometry.ts')]);const browser=await chromium.launch({channel:'chrome',headless:true});const report={method:'144Hz controlled rAF in real app, compared every frame to independently bundled pixel-exact candidate1 renderer at identical elapsed time; full surfaces each 1/3s and consecutive frames near 7.5s; representative sprite crops each frame; desktop crossover sizes; screenshot and visibility separate.',browser:await browser.version(),scenarios:[],errors:[],status:'PASS'};
try{for(const [width,height,dpr] of [[1440,900,1],[1440,900,1.5],[1920,1080,1],[1366,768,1]]){
 const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:dpr});await context.route('**/*',r=>new URL(r.request().url()).pathname.startsWith('/api/')?r.fulfill({status:401,json:{detail:'Not authenticated'}}):r.continue());
 await context.addInitScript(()=>{const q=window.__qa144={now:0,pending:new Map(),next:0,frame:0,draws:0,clears:0,clearArea:0,pathWrites:0};window.requestAnimationFrame=cb=>{const id=++q.next;q.pending.set(id,cb);return id};window.cancelAnimationFrame=id=>q.pending.delete(id);q.advance=(n=1,delta=1000/144)=>{for(let i=0;i<n;i++){q.now+=delta;q.frame++;const c=[...q.pending.values()];q.pending.clear();for(const f of c)f(q.now)}};for(const key of ['drawImage','clearRect']){const original=CanvasRenderingContext2D.prototype[key];CanvasRenderingContext2D.prototype[key]=function(...args){if(this.canvas.closest?.('.auth-aurora')){q[key==='drawImage'?'draws':'clears']++;if(key==='clearRect')q.clearArea+=Math.max(0,args[2])*Math.max(0,args[3])}return original.apply(this,args)}}const set=Element.prototype.setAttribute;Element.prototype.setAttribute=function(name,value){if(name==='d'&&this.hasAttribute?.('data-aurora-ribbon')&&this.closest?.('.auth-aurora'))q.pathWrites++;return set.call(this,name,value)};});
 const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));await page.goto(`${base}/login`);await expect(page.getByLabel('Email',{exact:true})).toBeVisible();await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','running');await page.waitForTimeout(300);
 const comparison=await page.evaluate(async({oldCode,geometryCode,width,height,dpr})=>{
  const [old,geo]=await Promise.all([import('data:text/javascript;base64,'+oldCode),import('data:text/javascript;base64,'+geometryCode)]);
  const q=window.__qa144,actual=document.querySelector('canvas[data-aurora-particles]'),ctx=actual.getContext('2d'),scene=document.querySelector('.auth-aurora'),rect=scene.getBoundingClientRect(),sceneWidth=rect.width,sceneHeight=rect.height;
  const reference=document.createElement('div');reference.innerHTML='<svg><path data-aurora-ribbon="0"></path><path data-aurora-ribbon="1"></path><path data-aurora-ribbon="2"></path></svg><canvas data-aurora-particles></canvas>';const renderer=old.createAuroraRenderer(reference);renderer.resize(sceneWidth,sceneHeight,dpr);renderer.render(0,false);const baseline=reference.querySelector('canvas'),bc=baseline.getContext('2d');
  if(actual.width!==baseline.width||actual.height!==baseline.height)throw Error('Different canvas sizes');
  const oldClears={calls:0,area:0},clear=bc.clearRect.bind(bc);bc.clearRect=function(x,y,w,h){oldClears.calls++;oldClears.area+=Math.max(0,w)*Math.max(0,h);return clear(x,y,w,h)};
  q.advance(1);q.draws=0;q.clears=0;q.clearArea=0;q.pathWrites=0;
  let elapsed=0,lastLight=0,lastPaint=0,paintFrames=0,skippedFrames=0,maxDelta=0,partialFrames=0,fullSamples=0,cropSamples=0,frameDifferences=0,paintFrameDifferences=0,maxAlphaDiff=0,maxRgbDiff=0,maxPremultipliedDiff=0,maxChanged=0,totalChanged=0;const mismatchExamples=[],paintTimes=[];let coverage;
  function compare(name,x,y,w,h,paintFrame){const a=bc.getImageData(x,y,w,h).data,b=ctx.getImageData(x,y,w,h).data;let changed=0,localAlpha=0,localRgb=0;for(let i=0;i<a.length;i+=4){if(a[i]!==b[i]||a[i+1]!==b[i+1]||a[i+2]!==b[i+2]||a[i+3]!==b[i+3]){changed++;localAlpha=Math.max(localAlpha,Math.abs(a[i+3]-b[i+3]));for(let c=0;c<3;c++){localRgb=Math.max(localRgb,Math.abs(a[i+c]-b[i+c]));maxPremultipliedDiff=Math.max(maxPremultipliedDiff,Math.abs(a[i+c]*a[i+3]/255-b[i+c]*b[i+3]/255));}}}if(changed){frameDifferences++;if(paintFrame)paintFrameDifferences++;if(mismatchExamples.length<10)mismatchExamples.push({name,changed,alphaDiff:localAlpha,rgbDiff:localRgb,paintFrame})}maxAlphaDiff=Math.max(maxAlphaDiff,localAlpha);maxRgbDiff=Math.max(maxRgbDiff,localRgb);maxChanged=Math.max(maxChanged,changed);totalChanged+=changed;}
  const frames=1440,index=width===1920?8:width===1366?3:0,scaleX=actual.width/sceneWidth,scaleY=actual.height/sceneHeight;
  for(let frame=1;frame<=frames;frame++){
    const before=q.draws;q.advance(1);elapsed+=1/144;const light=elapsed-lastLight>=1/30-1e-9;if(light)lastLight+=Math.floor((elapsed-lastLight+1e-9)/(1/30))*(1/30);renderer.render(elapsed,light);
    const paint=q.draws>before;if(paint){paintFrames++;lastPaint=elapsed;paintTimes.push(elapsed)}else skippedFrames++;
    const current=old.particleFrames(elapsed,sceneWidth,sceneHeight),display=old.particleFrames(lastPaint,sceneWidth,sceneHeight);
    for(let i=0;i<current.length;i++)maxDelta=Math.max(maxDelta,Math.hypot(current[i].x-display[i].x,current[i].y-display[i].y));
    if(light||!coverage)coverage=old.waveCoverage([0,1].map(i=>geo.ribbonFrame(i,elapsed)));
    const p=current[index],point=old.cssToWorld(p.x,p.y,old.sceneMapping(sceneWidth,sceneHeight)),v=old.particleVisibility(point,coverage);if(v>0&&v<1)partialFrames++;
    const x=Math.max(0,Math.floor((p.x-p.radius-6)*scaleX)),y=Math.max(0,Math.floor((p.y-p.radius-6)*scaleY)),r=Math.min(actual.width,Math.ceil((p.x+p.radius+6)*scaleX)),b=Math.min(actual.height,Math.ceil((p.y+p.radius+6)*scaleY));
    if(r>x&&b>y){compare('crop@'+elapsed.toFixed(5),x,y,r-x,b-y,paint);cropSamples++}
    if(frame%48===0||(frame>=1080&&frame<=1086)){compare('full@'+elapsed.toFixed(5),0,0,actual.width,actual.height,paint);fullSamples++}
  }
  const paintIntervals=paintTimes.slice(1).map((v,i)=>v-paintTimes[i]),clearRects={before:{...oldClears},after:{calls:q.clears,area:q.clearArea}};renderer.destroy();
  return {width,height,dpr,sceneWidth,sceneHeight,canvasWidth:actual.width,canvasHeight:actual.height,frames,paintFrames,skippedFrames,paintRateHz:paintFrames/elapsed,paintIntervalMin:Math.min(...paintIntervals),paintIntervalMax:Math.max(...paintIntervals),lightUpdates:q.pathWrites/2,maxParticlePhaseDisplacementCssPx:maxDelta,partialVisibilityFrames:partialFrames,fullSamples,cropSamples,frameDifferences,paintFrameDifferences,maxAlphaDiff,maxRgbDiff,maxPremultipliedDiff,maxChanged,totalChanged,mismatchExamples,pending:q.pending.size,clearRects};
 },{oldCode,geometryCode,width,height,dpr});
 report.scenarios.push(comparison);console.log(JSON.stringify(comparison));
 // Same phase screenshots; controlled time is10s after initial frame.
 await page.screenshot({path:path.join(out,`${width}x${height}-dpr${dpr}-10s.png`),animations:'disabled'});
 await toggle(page);await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','paused');const paused=await hash(page);await page.evaluate(()=>window.__qa144.advance(144));const frozen=await hash(page);expect(frozen).toEqual(paused);
 await page.setViewportSize({width:1366,height:768});await page.waitForTimeout(250);const resized=await hash(page);await page.evaluate(()=>window.__qa144.advance(144));expect(await hash(page)).toEqual(resized);
 await toggle(page);await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','running');await page.evaluate(()=>window.__qa144.advance(1,30000));const first=await hash(page);expect(first).toEqual(resized);await page.evaluate(()=>window.__qa144.advance(12));const next=await hash(page);expect(next.hash).not.toEqual(first.hash);
 comparison.pause={paused,frozen,resized,first,next};
 if(comparison.paintFrameDifferences||comparison.maxParticlePhaseDisplacementCssPx>.4||comparison.pending!==1)report.status='FAIL';
 await context.close();
 }
 expect(report.errors).toEqual([]);
}catch(e){report.status='FAIL';report.error=e.stack;throw e}finally{fs.writeFileSync(path.join(out,'comparison.json'),JSON.stringify(report,null,2));await browser.close()}
if(report.status!=='PASS')process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
