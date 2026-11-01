import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {writeFileSync} from 'node:fs';
import path from 'node:path';
const require=createRequire(new URL('../../../../frontend/package.json',import.meta.url));const esbuild=require('esbuild');
const oldDir=fileURLToPath(new URL('./baseline-source/',import.meta.url));
const newDir=fileURLToPath(new URL('../../../../frontend/src/features/auth/',import.meta.url));
async function load(dir,file){const b=await esbuild.build({entryPoints:[path.join(dir,file)],bundle:true,write:false,platform:'node',format:'esm'});return import('data:text/javascript;base64,'+Buffer.from(b.outputFiles[0].contents).toString('base64'));}
const [old,now,oldGeo,newGeo]=await Promise.all([load(oldDir,'canvasRenderer.ts'),load(newDir,'canvasRenderer.ts'),load(oldDir,'ribbonGeometry.ts'),load(newDir,'ribbonGeometry.ts')]);
const report={method:'Baseline-source and candidate functions evaluated in memory. All particles sampled every .25s for 120s in three scene sizes; crossover phases sampled every 1/60s; boundary points probe segment normals near inner/outer fade radius.',scenes:[],boundaries:{samples:0,maxError:0,differences:0,examples:[]},status:'PASS'};
for(const [width,height] of [[980,900],[1460,1080],[906,768]]){
 const mapping=old.sceneMapping(width,height);let samples=0,partial=0,hidden=0,maxError=0,maxAlphaError=0,differences=0,maskClassChanges=0,geometryMaxError=0;const examples=[];
 function inspect(t){const oldWaves=[0,1].map(i=>oldGeo.ribbonFrame(i,t)),newWaves=[0,1].map(i=>newGeo.ribbonFrame(i,t));
  for(let i=0;i<2;i++)for(let c=0;c<oldWaves[i].cubics.length;c++)for(let p=0;p<4;p++)for(let axis=0;axis<2;axis++)geometryMaxError=Math.max(geometryMaxError,Math.abs(oldWaves[i].cubics[c][p][axis]-newWaves[i].cubics[c][p][axis]));
  const coverageOld=old.waveCoverage(oldWaves),coverageNew=now.waveCoverage(newWaves), frames=old.particleFrames(t,width,height),candidateFrames=now.particleFrames(t,width,height);
  for(let i=0;i<frames.length;i++){const p=frames[i],q=candidateFrames[i];const pos=old.cssToWorld(p.x,p.y,mapping), candidate=now.cssToWorld(q.x,q.y,now.sceneMapping(width,height));const a=old.particleVisibility(pos,coverageOld),b=now.particleVisibility(candidate,coverageNew),error=Math.abs(a-b),alphaError=Math.abs(a*p.opacity-b*q.opacity);samples++;if(a>0&&a<1)partial++;if(a===0)hidden++;if(error>1e-12){differences++;if(examples.length<12)examples.push({time:t,index:i,old:a,candidate:b,error})}if((a===0)!==(b===0)||(a===1)!==(b===1))maskClassChanges++;maxError=Math.max(maxError,error);maxAlphaError=Math.max(maxAlphaError,alphaError);}
 }
 for(let i=0;i<=480;i++)inspect(i*.25);
 if(width===1460||width===906)for(let frame=6*60;frame<=14*60;frame++)inspect(frame/60);
 report.scenes.push({width,height,samples,partial,hidden,differences,maskClassChanges,maxError,maxAlphaError,geometryMaxError,examples});
 if(differences||maskClassChanges||geometryMaxError>1e-10)report.status='FAIL';
}
// Directly sample points just inside and outside each visibility boundary,
// including fractional coordinates around segment endpoints and midpoints.
for(const t of [0,6,7,8,12,15,31,103]){
 const waves=[0,1].map(i=>oldGeo.ribbonFrame(i,t));const oldCoverage=old.waveCoverage(waves),newCoverage=now.waveCoverage([0,1].map(i=>newGeo.ribbonFrame(i,t)));
 for(let wave=0;wave<2;wave++){const pts=oldGeo.flattenWave(waves[wave]);for(let segment=1;segment<pts.length;segment+=8){const a=pts[segment-1],b=pts[segment],dx=b[0]-a[0],dy=b[1]-a[1],length=Math.hypot(dx,dy);if(!length)continue;
   for(const u of [0,.5,1])for(const radius of [([40,52][wave])-1e-8,[40,52][wave],[40,52][wave]+1e-8,([48,60][wave])-1e-8,[48,60][wave],[48,60][wave]+1e-8])for(const side of [-1,1]){
    const point=[a[0]+dx*u-side*dy/length*radius,a[1]+dy*u+side*dx/length*radius],x=old.particleVisibility(point,oldCoverage),y=now.particleVisibility(point,newCoverage),error=Math.abs(x-y);report.boundaries.samples++;report.boundaries.maxError=Math.max(report.boundaries.maxError,error);if(error>1e-12){report.boundaries.differences++;if(report.boundaries.examples.length<12)report.boundaries.examples.push({time:t,wave,segment,u,radius,side,old:x,candidate:y,error})}
   }
 }}
}
if(report.boundaries.differences)report.status='FAIL';writeFileSync(new URL('./visibility-comparison.json',import.meta.url),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));if(report.status!=='PASS')process.exitCode=1;
