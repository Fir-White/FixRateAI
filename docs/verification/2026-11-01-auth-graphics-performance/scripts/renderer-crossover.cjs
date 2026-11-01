const {chromium}=require('../../../../frontend/node_modules/@playwright/test');
const esbuild=require('../../../../frontend/node_modules/esbuild'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..'), oldDir=path.join(__dirname,'baseline-source'),newDir=path.join(root,'frontend/src/features/auth');
async function bundle(file){const b=await esbuild.build({entryPoints:[file],bundle:true,write:false,platform:'browser',format:'esm',target:'es2022'});return Buffer.from(b.outputFiles[0].contents).toString('base64')}
(async()=>{const [oldCode,newCode,geometryCode]=await Promise.all([bundle(path.join(oldDir,'canvasRenderer.ts')),bundle(path.join(newDir,'canvasRenderer.ts')),bundle(path.join(oldDir,'ribbonGeometry.ts'))]);const browser=await chromium.launch({channel:'chrome',headless:true});const results={browser:await browser.version(),method:'Actual baseline/candidate Canvas renderers bundled from source and executed side by side in Chromium. 15 seconds at 60 Hz, lights at 30 Hz. Read full surfaces each 0.5s and each adjacent crossover frame, and particle crossover crop each frame. clearRect area sums backing-pixel rectangles, including overlaps; excludes resize/init.',scenarios:[],status:'PASS'};
 try{for(const [viewportWidth,height,dpr] of [[1920,1080,1],[1920,1080,1.5],[1366,768,1],[1366,768,1.5]]){
 const context=await browser.newContext({viewport:{width:viewportWidth,height},deviceScaleFactor:dpr});const page=await context.newPage();await page.goto('about:blank');
 const result=await page.evaluate(async({oldCode,newCode,geometryCode,viewportWidth,height,dpr})=>{
  const [old,now,geometry]=await Promise.all([import('data:text/javascript;base64,'+oldCode),import('data:text/javascript;base64,'+newCode),import('data:text/javascript;base64,'+geometryCode)]);
  const width=viewportWidth-460,source=()=>{const div=document.createElement('div');div.innerHTML='<svg><path data-aurora-ribbon="0"></path><path data-aurora-ribbon="1"></path><path data-aurora-ribbon="2"></path></svg><canvas data-aurora-particles></canvas>';return div;};
  const oldScene=source(),newScene=source(),a=old.createAuroraRenderer(oldScene),b=now.createAuroraRenderer(newScene);if(!a||!b)throw Error('Unable to instantiate baseline/candidate renderer');
  a.resize(width,height,dpr);b.resize(width,height,dpr);
  const ca=oldScene.querySelector('canvas'),cb=newScene.querySelector('canvas');if(ca.width!==cb.width||ca.height!==cb.height)throw Error('canvas dimensions differ: '+ca.width+'x'+ca.height+' vs '+cb.width+'x'+cb.height);
  const ac=ca.getContext('2d'),bc=cb.getContext('2d'),stats={before:{calls:0,area:0},after:{calls:0,area:0}};let collect=true;
  function instrument(ctx,entry){const clear=ctx.clearRect.bind(ctx);ctx.clearRect=function(x,y,w,h){if(collect){entry.calls++;entry.area+=Math.max(0,w)*Math.max(0,h)}return clear(x,y,w,h)}}instrument(ac,stats.before);instrument(bc,stats.after);
  const values={viewportWidth,height,dpr,sceneWidth:width,canvasWidth:ca.width,canvasHeight:ca.height,frames:0,fullComparisons:0,cropComparisons:0,totalChangedPixels:0,maxChangedPixels:0,maxByteDifference:0,partialVisibilityFrames:0,hiddenVisibilityFrames:0,mismatches:[],stats};
  const idx=viewportWidth===1920?8:3, scaleX=ca.width/width,scaleY=ca.height/height;
  function compare(name,x,y,w,h){const A=ac.getImageData(x,y,w,h).data,B=bc.getImageData(x,y,w,h).data;let changed=0,max=0,sum=0;for(let i=0;i<A.length;i+=4){let changedHere=false;for(let j=0;j<4;j++){const v=Math.abs(A[i+j]-B[i+j]);if(v){changedHere=true;sum+=v;max=Math.max(max,v)}}if(changedHere)changed++;}values.totalChangedPixels+=changed;values.maxChangedPixels=Math.max(values.maxChangedPixels,changed);values.maxByteDifference=Math.max(values.maxByteDifference,max);if(changed&&values.mismatches.length<20)values.mismatches.push({name,x,y,w,h,changed,max,meanAbsoluteByteDiff:sum/A.length});return changed;}
  let coverage;
  for(let frame=0;frame<=900;frame++){
   const seconds=frame/60,lights=frame%2===0;a.render(seconds,lights);b.render(seconds,lights);values.frames++;
   if(lights)coverage=old.waveCoverage([0,1].map(i=>geometry.ribbonFrame(i,seconds)));
   if(frame>=360&&frame<=840){const p=old.particleFrames(seconds,width,height)[idx],point=old.cssToWorld(p.x,p.y,old.sceneMapping(width,height)),vis=old.particleVisibility(point,coverage);if(vis>0&&vis<1)values.partialVisibilityFrames++;if(vis===0)values.hiddenVisibilityFrames++;
    const x=Math.max(0,Math.floor((p.x-p.radius-5)*scaleX)),y=Math.max(0,Math.floor((p.y-p.radius-5)*scaleY)),r=Math.min(ca.width,Math.ceil((p.x+p.radius+5)*scaleX)),btm=Math.min(ca.height,Math.ceil((p.y+p.radius+5)*scaleY));if(r>x&&btm>y){compare('crop@'+seconds.toFixed(4),x,y,r-x,btm-y);values.cropComparisons++;}
   }
   if(frame%30===0||(frame>=450&&frame<=456)||(frame>=735&&frame<=741)){compare('full@'+seconds.toFixed(4),0,0,ca.width,ca.height);values.fullComparisons++;}
  }
  const finalA=ac.getImageData(0,0,ca.width,ca.height).data,finalB=bc.getImageData(0,0,cb.width,cb.height).data;
  let hashA=2166136261,hashB=2166136261;for(let i=0;i<finalA.length;i++){hashA=Math.imul(hashA^finalA[i],16777619);hashB=Math.imul(hashB^finalB[i],16777619)}values.finalHashBefore=hashA>>>0;values.finalHashAfter=hashB>>>0;
  values.clearedAreaRatio=stats.after.area/stats.before.area;collect=false;a.destroy();b.destroy();return values;
 },{oldCode,newCode,geometryCode,viewportWidth,height,dpr});
 results.scenarios.push(result);if(result.totalChangedPixels||result.finalHashBefore!==result.finalHashAfter||!result.partialVisibilityFrames)results.status='FAIL';console.log(JSON.stringify(result));await context.close();
 }}catch(e){results.status='FAIL';results.error=e.stack;throw e}finally{fs.writeFileSync(path.join(__dirname,'renderer-crossover.json'),JSON.stringify(results,null,2));await browser.close()}
 if(results.status!=='PASS')process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
