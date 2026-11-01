const { chromium, expect } = require('../../../frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.FIXRATE_BASE_URL || 'http://127.0.0.1:5173';
const out = path.dirname(__filename);
const report = { date: '2026-11-01', base, browser: 'local installed Chrome, headless', checks: [], errors: [] };
const check = (name, data = {}) => { report.checks.push({ name, ...data }); console.log(name, JSON.stringify(data)); };
async function mock(context) {
  await context.route('**/*', route => new URL(route.request().url()).pathname.startsWith('/api/')
    ? route.fulfill({ status: 401, json: { detail: 'QA unauthenticated session' } }) : route.continue());
}
async function instrument(context, controlled = false) {
  await context.addInitScript(({ controlled }) => {
    const qa = window.__auroraQA = { operations: [], counts: {}, listeners: [], frames: [], longtasks: [], pending: new Map(), stamp: 0, next: 0, controlled, collecting: false };
    const listen = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, listener, options) {
      if (/^(pointermove|mousemove|pointerleave|mouseleave)$/.test(type)) qa.listeners.push({ type, target: this === window ? 'window' : this === document ? 'document' : this.nodeName || '' });
      return listen.call(this, type, listener, options);
    };
    for (const method of ['beginPath','moveTo','lineTo','bezierCurveTo','quadraticCurveTo','setTransform','transform','translate','rotate','scale','drawImage','stroke','fill','clearRect']) {
      const original = CanvasRenderingContext2D.prototype[method];
      CanvasRenderingContext2D.prototype[method] = function(...args) {
        if (qa.collecting && this.canvas.closest?.('.auth-aurora')) {
          qa.counts[method] = (qa.counts[method] || 0) + 1;
          if (qa.operations.length < 3000) qa.operations.push([method, ...args.map(a => typeof a === 'number' ? Math.round(a * 100000) / 100000 : a?.nodeName || typeof a)]);
        }
        return original.apply(this, args);
      };
    }
    if (controlled) {
      window.requestAnimationFrame = callback => { const id = ++qa.next; qa.pending.set(id, callback); return id; };
      window.cancelAnimationFrame = id => qa.pending.delete(id);
      qa.advance = (frames = 1, delta = 1000 / 60) => {
        for (let i = 0; i < frames; i++) {
          qa.stamp += delta;
          const callbacks = [...qa.pending.values()]; qa.pending.clear();
          for (const callback of callbacks) callback(qa.stamp);
        }
        return qa.pending.size;
      };
    }
    try { new PerformanceObserver(entries => qa.longtasks.push(...entries.getEntries().map(e => ({start:e.startTime,duration:e.duration})))).observe({type:'longtask',buffered:true}); } catch {}
  }, { controlled });
}
async function setup(browser, viewport = {width:1440,height:900}, controlled = false) {
  const context = await browser.newContext({viewport, deviceScaleFactor:1});
  await mock(context); await instrument(context, controlled);
  const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  await page.goto(`${base}/login`);
  await expect(page.getByLabel('Email', {exact:true})).toBeVisible();
  await page.waitForTimeout(150);
  return {context,page};
}
const logos = page => page.locator('.auth-brand img,.auth-aurora__brand,.auth-aurora__logo,.auth-aurora__logo img').evaluateAll(elements => elements.map(element => ({
  tag:element.className || element.tagName, box:element.getBoundingClientRect().toJSON(),
  transform:getComputedStyle(element).transform, animation:getComputedStyle(element).animationName,
  opacity:getComputedStyle(element).opacity,
})));
const snapshot = page => page.evaluate(() => ({
  paths:[...document.querySelectorAll('[data-aurora-ribbon]')].map(e => e.getAttribute('d')),
  canvases:[...document.querySelectorAll('.auth-aurora canvas')].map(canvas => {
    const pixels = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    let hash = 2166136261, nonzero = 0;
    for (let i = 0; i < pixels.length; i++) { hash = Math.imul(hash ^ pixels[i], 16777619); if (pixels[i]) nonzero++; }
    return {width:canvas.width,height:canvas.height,hash,nonzero};
  }),
}));
const captureOps = page => page.evaluate(() => {window.__auroraQA.operations=[];window.__auroraQA.counts={};window.__auroraQA.collecting=true;});
const readOps = page => page.evaluate(() => {window.__auroraQA.collecting=false;return {operations:window.__auroraQA.operations, counts:window.__auroraQA.counts};});
const frameSample = (page, ms = 31000) => page.evaluate(ms => new Promise(resolve => {
  const intervals = [], started = performance.now(), longStart = window.__auroraQA.longtasks.length;
  let previous;
  function tick(now) {
    if (previous !== undefined) intervals.push(now-previous); previous=now;
    if (performance.now()-started < ms) { requestAnimationFrame(tick); return; }
    const sorted = [...intervals].sort((a,b)=>a-b);
    resolve({durationMs:performance.now()-started,frames:intervals.length,meanMs:intervals.reduce((a,b)=>a+b,0)/intervals.length,p50Ms:sorted[Math.floor(sorted.length*.5)],p95Ms:sorted[Math.floor(sorted.length*.95)],maxMs:sorted.at(-1),over25Ms:intervals.filter(x=>x>25).length,over50Ms:intervals.filter(x=>x>50).length,longtasks:window.__auroraQA.longtasks.slice(longStart)});
  }
  requestAnimationFrame(tick);
}), ms);
async function toggle(page) {
  await page.locator('.auth-footer button').click();
  await page.locator('.auth-motion-setting input').press('Space');
  await page.keyboard.press('Escape');
}
(async () => {
  fs.mkdirSync(out,{recursive:true});
  const browser = await chromium.launch({channel:'chrome',headless:true});
  report.version = await browser.version();
  try {
    const {context,page} = await setup(browser);
    const originalLogos = await logos(page), before = await snapshot(page);
    await page.screenshot({path:path.join(out,'motion-00s.png')});
    const samplePromise = frameSample(page,31000);
    await page.waitForTimeout(15500);
    await page.screenshot({path:path.join(out,'motion-15s.png')});
    const mid = await snapshot(page);
    const performanceResult = await samplePromise;
    const after = await snapshot(page);
    await page.screenshot({path:path.join(out,'motion-31s.png')});
    expect(after).not.toEqual(before); expect(mid).not.toEqual(before);
    if(before.paths.length>2)expect(after.paths[2]).toEqual(before.paths[2]);
    expect(await logos(page)).toEqual(originalLogos);
    if(before.paths.length>=2){
      report.curvature = [0,1].map(index=>{
        const numbers = value=>(value.match(/-?\d+(?:\.\d+)?/g)||[]).map(Number);
        const a=numbers(before.paths[index]), b=numbers(after.paths[index]);
        const displacements=[];
        for(let i=0;i<a.length;i+=2)displacements.push([b[i]-a[i],b[i+1]-a[i+1]]);
        const maxDisplacement=Math.max(...displacements.map(p=>Math.hypot(...p)));
        const relativeMovement=Math.max(...displacements.map(p=>Math.hypot(p[0]-displacements[0][0],p[1]-displacements[0][1])));
        expect(relativeMovement).toBeGreaterThan(1);
        expect(Math.hypot(...displacements[0])).toBeLessThan(.01);
        expect(Math.hypot(...displacements.at(-1))).toBeLessThan(.01);
        return {index,maxDisplacement,relativeMovement,displacements};
      });
      expect(report.curvature[0].displacements).not.toEqual(report.curvature[1].displacements);
      check('Both curves deform independently with exact fixed endpoints', {curves:report.curvature});
    }
    fs.writeFileSync(path.join(out,'motion-snapshots.json'),JSON.stringify({before,mid,after},null,2));
    check('31 seconds real autonomous movement, logo boxes and transforms unchanged',performanceResult);

    await toggle(page); await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','paused');
    const paused = await snapshot(page); await page.waitForTimeout(1000);
    expect(await snapshot(page)).toEqual(paused);
    await page.mouse.move(500,100,{steps:20}); await page.mouse.move(1390,850,{steps:30}); await page.mouse.move(740,450,{steps:20});
    expect(await snapshot(page)).toEqual(paused); expect(await logos(page)).toEqual(originalLogos);
    check('Pause freezes all light pixels; pointer movement changes neither lights nor logo');
    await toggle(page); await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','running');
    await page.waitForTimeout(1000); expect(await snapshot(page)).not.toEqual(paused);
    check('Help control pause/resume continues motion');

    await page.emulateMedia({reducedMotion:'reduce'}); await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','paused');
    const reduced = await snapshot(page); await page.waitForTimeout(800); expect(await snapshot(page)).toEqual(reduced);
    await page.screenshot({path:path.join(out,'reduced-motion.png')});
    await page.locator('.auth-footer button').click(); await expect(page.locator('.auth-motion-setting input')).toBeDisabled(); await page.keyboard.press('Escape');
    await page.emulateMedia({reducedMotion:'no-preference'}); await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','running');
    check('Live reduced motion freezes composition, disables checkbox, restores motion on preference change');

    await page.getByLabel('Email',{exact:true}).fill('qa@example.test');
    for (const selector of ['#login-email','#login-password','.auth-password__toggle','.auth-submit','.auth-register a','.auth-footer button']) {
      await page.locator(selector).focus(); const state = await page.locator('.auth-aurora').getAttribute('data-motion');
      // Dispatch preserves browser default and tests only whether the global handler steals the key.
      const prevented = await page.locator(selector).evaluate(element=>!element.dispatchEvent(new KeyboardEvent('keydown',{key:' ',code:'Space',bubbles:true,cancelable:true})));
      expect(prevented).toBe(false); expect(await page.locator('.auth-aurora').getAttribute('data-motion')).toBe(state);
    }
    check('Space is not intercepted in inputs, buttons, links');

    for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[1024,768],[390,844]]) {
      await page.setViewportSize({width,height}); await page.waitForTimeout(200);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await expect(page.locator('.auth-submit')).toBeInViewport();
      await page.screenshot({path:path.join(out,`viewport-${width}x${height}.png`),fullPage:true});
      if (width>820) await expect(page.locator('.auth-aurora__logo img')).toBeVisible();
      else {await expect(page.locator('.auth-aurora')).toHaveAttribute('data-motion','paused'); const a=await snapshot(page);await page.waitForTimeout(500);expect(await snapshot(page)).toEqual(a);}
      check(`Viewport ${width}x${height}: no horizontal scroll, submit in viewport`);
    }
    await context.close();

    // Identical clocks isolate pointer influence from autonomous phase progression.
    const control = await setup(browser,{width:1440,height:900},true);
    const mouse = await setup(browser,{width:1440,height:900},true);
    for (const item of [control,mouse]) {await captureOps(item.page);await item.page.evaluate(()=>window.__auroraQA.advance(121));}
    const initialControl=await snapshot(control.page), initialMouse=await snapshot(mouse.page);
    expect(initialControl).toEqual(initialMouse);
    const initialGeometry=await readOps(control.page);
    await mouse.page.mouse.move(1000,300,{steps:25});await mouse.page.mouse.move(700,800,{steps:25});
    for (const item of [control,mouse]) {await captureOps(item.page);await item.page.evaluate(()=>window.__auroraQA.advance(601));}
    expect(await snapshot(control.page)).toEqual(await snapshot(mouse.page));
    const laterGeometry=await readOps(control.page);
    fs.writeFileSync(path.join(out,'geometry-operations.json'),JSON.stringify({initialGeometry,laterGeometry},null,2));
    check('Identical animation clocks: moving pointer produces byte-identical lights');
    report.pointerListeners = await control.page.evaluate(()=>window.__auroraQA.listeners);
    expect(report.pointerListeners.filter(entry=>entry.target==='window'||entry.target==='document')).toEqual([]);
    report.controlledPendingFrames = await control.page.evaluate(()=>window.__auroraQA.pending.size);
    expect(report.controlledPendingFrames).toBe(1);
    await toggle(control.page);await expect(control.page.locator('.auth-aurora')).toHaveAttribute('data-motion','paused');
    const phasePaused=await snapshot(control.page);
    await control.page.evaluate(()=>window.__auroraQA.advance(600));expect(await snapshot(control.page)).toEqual(phasePaused);
    await toggle(control.page);await expect(control.page.locator('.auth-aurora')).toHaveAttribute('data-motion','running');
    await control.page.evaluate(()=>window.__auroraQA.advance(1,30000));expect(await snapshot(control.page)).toEqual(phasePaused);
    await control.page.evaluate(()=>window.__auroraQA.advance(30));expect(await snapshot(control.page)).not.toEqual(phasePaused);
    check('Checkbox pause freezes phase; first resumed frame after30second timestamp gap preserves exact pixels');
    // Test long return gap and body Space with a deterministic clock.
    await control.page.evaluate(()=>document.activeElement?.blur());
    await control.page.keyboard.press('Space');
    const bodySpaceState=await control.page.locator('.auth-aurora').getAttribute('data-motion');
    report.bodySpaceState=bodySpaceState;
    if(bodySpaceState==='paused'){
      const a=await snapshot(control.page);await control.page.evaluate(()=>window.__auroraQA.advance(600));expect(await snapshot(control.page)).toEqual(a);
      await control.page.keyboard.press('Space');await expect(control.page.locator('.auth-aurora')).toHaveAttribute('data-motion','running');
      await control.page.evaluate(()=>window.__auroraQA.advance(1));expect(await snapshot(control.page)).toEqual(a);
      await control.page.evaluate(()=>window.__auroraQA.advance(30));expect(await snapshot(control.page)).not.toEqual(a);
      check('Body Space pause/resume preserves exact pixels on first resumed frame');
    } else check('Body Space was not previously implemented; help checkbox remains pause control');
    if(await control.page.getByRole('dialog').count())await control.page.keyboard.press('Escape');
    await control.page.evaluate(()=>window.__auroraQA.advance(3100));
    await control.page.screenshot({path:path.join(out,'controlled-high-motion-64s.png')});
    report.highMotionPaths = (await snapshot(control.page)).paths;
    check('Controlled clock also inspected at approximately64seconds, covering a later independent target');
    await control.context.close();await mouse.context.close();
    expect(report.errors).toEqual([]);
    report.status='PASS';
  } catch(error) {report.status='FAIL';report.failure=error.stack;throw error;}
  finally {fs.writeFileSync(path.join(out,'browser-review.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

