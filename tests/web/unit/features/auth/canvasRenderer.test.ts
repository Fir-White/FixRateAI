import { afterEach,describe,expect,it,vi } from "vitest";
import { createAuroraRenderer,cssToWorld,paintParticles,particleFrames,particleVisibility,rasterSizes,sceneMapping,waveCoverage } from "@/features/auth/canvasRenderer";
import { cubicPoint,flattenWave,ribbonFrame,type Point } from "@/features/auth/ribbonGeometry";
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});
describe("original tiny particles and actual curve coverage",()=>{
  it("caps the isolated particle raster",()=>{
    for(const [width,height] of [[980,900],[1460,1080],[4000,3000]]) {
      const s=rasterSizes(width,height,4); expect(s.particleWidth).toBeLessThanOrEqual(2400);expect(s.particleHeight).toBeLessThanOrEqual(1800);
      expect(s.particleWidth).toBeLessThanOrEqual(width*1.5);expect(s.particleHeight).toBeLessThanOrEqual(height*1.5);
    }
  });
  it("covers rendered Beziers while keeping clear particles visible",()=>{
    const waves=[ribbonFrame(0,3),ribbonFrame(1,3)],coverage=waveCoverage(waves),covered=cubicPoint(waves[0].cubics[0],.5);
    expect(particleVisibility(covered,coverage)).toBe(0);expect(particleVisibility([0,0],coverage)).toBe(1);
    const draw=vi.fn(),ctx={globalAlpha:1,drawImage:draw} as unknown as CanvasRenderingContext2D;
    paintParticles(ctx,[{x:covered[0],y:covered[1],radius:1,opacity:.28},{x:0,y:0,radius:1.5,opacity:.22}],sceneMapping(1200,1000),coverage,{} as CanvasImageSource);
    expect(draw).toHaveBeenCalledTimes(1);expect(draw.mock.calls[0].slice(-2)).toEqual([3,3]);expect(ctx.globalAlpha).toBe(1);
  });
  it("restores the exact original diameter/opacity arrays and independently drifting positions",()=>{
    const start=particleFrames(0,980,900),after=particleFrames(3,980,900);
    expect(start.map(p=>p.radius*2)).toEqual([2,3,4,3,3,2,4,3,2,3]);
    expect(start.map(p=>p.opacity)).toEqual([.28,.22,.18,.30,.36,.26,.20,.32,.24,.28]);
    expect(after.every((p,i)=>p.x!==start[i].x&&p.y!==start[i].y)).toBe(true);
  });
  it("matches the original fade for arbitrary points around both changing ribbons",()=>{
    // Straightforward reference: the minimum exact distance to every segment.
    const reference=(point:Point,waves:readonly (readonly Point[])[])=>{
      let visibility=1;
      waves.forEach((points,index)=>{
        let distance=Infinity;
        for(let i=1;i<points.length;i++){
          const a=points[i-1],b=points[i],dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
          const t=length?Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)):0;
          distance=Math.min(distance,Math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy));
        }
        const edge=Math.max(0,Math.min(1,(distance-[40,52][index])/8));
        visibility=Math.min(visibility,edge*edge*(3-2*edge));
      });
      return visibility;
    };
    let seed=87231;
    const sample=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/0x100000000;};
    for(const seconds of [0,3.1,12.7,91.2]){
      const frames=[ribbonFrame(0,seconds),ribbonFrame(1,seconds)],before=frames.map(flattenWave),after=waveCoverage(frames);
      for(let i=0;i<1200;i++){
        const point:Point=[-250+sample()*1750,-300+sample()*1600];
        expect(particleVisibility(point,after)).toBe(reference(point,before));
      }
      // Include points just around both transition boundaries, including zero-length joins.
      for(const points of before) for(const point of [points[0],points[32],points[33],points.at(-1)!]) {
        for(const radius of [40-1e-8,40,40+1e-8,48-1e-8,48,48+1e-8,52,60]){
          const probe:Point=[point[0]+radius,point[1]];
          expect(particleVisibility(probe,after)).toBe(reference(probe,before));
        }
      }
    }
    // Actual particles cross the soft occlusion edge at these viewport/phase pairs.
    for(const [width,height,index,start,end] of [[1460,1080,8,7,13],[906,768,3,6,10]]) {
      const mapping=sceneMapping(width,height);
      for(let step=start*10;step<=end*10;step++) {
        const time=step/10,frames=[ribbonFrame(0,time),ribbonFrame(1,time)];
        const particle=particleFrames(time,width,height)[index],point=cssToWorld(particle.x,particle.y,mapping);
        expect(particleVisibility(point,waveCoverage(frames))).toBe(reference(point,frames.map(flattenWave)));
      }
    }
  });
  it("keeps hidden particle canvases tiny and resumes painting after a resize",()=>{
    vi.stubGlobal("innerWidth",1024); vi.stubGlobal("innerHeight",900);
    const gradient={addColorStop:vi.fn()};
    const context={setTransform:vi.fn(),clearRect:vi.fn(),drawImage:vi.fn(),fillRect:vi.fn(),createRadialGradient:vi.fn(()=>gradient),globalAlpha:1,fillStyle:""};
    vi.spyOn(HTMLCanvasElement.prototype,"getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    const scene=document.createElement("div");
    scene.innerHTML='<svg><path data-aurora-ribbon="0"></path><path data-aurora-ribbon="1"></path><path data-aurora-ribbon="2"></path></svg><canvas data-aurora-particles></canvas>';
    const canvas=scene.querySelector("canvas")!,renderer=createAuroraRenderer(scene)!;
    renderer.resize(604,900,1);expect([canvas.width,canvas.height]).toEqual([1,1]);
    context.clearRect.mockClear(); context.drawImage.mockClear();
    renderer.render(1);renderer.render(2);
    expect(context.clearRect).not.toHaveBeenCalled();expect(context.drawImage).not.toHaveBeenCalled();
    vi.stubGlobal("innerWidth",1440);renderer.resize(980,900,1);renderer.render(2,false);
    expect([canvas.width,canvas.height]).toEqual([980,900]);expect(context.drawImage).toHaveBeenCalled();
    vi.stubGlobal("innerWidth",1024);renderer.resize(604,900,1);
    expect([canvas.width,canvas.height]).toEqual([1,1]);
    context.clearRect.mockClear();context.drawImage.mockClear();renderer.render(3);
    expect(context.clearRect).not.toHaveBeenCalled();expect(context.drawImage).not.toHaveBeenCalled();
    renderer.destroy();
  });
});
