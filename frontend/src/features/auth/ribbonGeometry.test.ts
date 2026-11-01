import { describe, expect, it } from "vitest";
import { CONTROL_DISPLACEMENT_LIMITS, cubicPoint, flowNoise, ribbonFrame, ribbonPath, type Cubic, type Point } from "./ribbonGeometry";
const mid = (a: Point,b: Point): Point => [(a[0]+b[0])/2,(a[1]+b[1])/2];
function split(c: Cubic): readonly Cubic[] {
  const a=mid(c[0],c[1]),b=mid(c[1],c[2]),d=mid(c[2],c[3]),e=mid(a,b),f=mid(b,d),g=mid(e,f);
  return [[c[0],a,e,g],[g,f,d,c[3]]];
}
function box(c: Cubic) { return [Math.min(...c.map(p=>p[0])),Math.min(...c.map(p=>p[1])),Math.max(...c.map(p=>p[0])),Math.max(...c.map(p=>p[1]))]; }
function certify(a: Cubic,b: Cubic,depth=0): boolean {
  const x=box(a),y=box(b),dx=Math.max(0,x[0]-y[2],y[0]-x[2]),dy=Math.max(0,x[1]-y[3],y[1]-x[3]);
  if(Math.hypot(dx,dy)>70) return true;
  if(depth>=24) return false;
  const da=Math.hypot(x[2]-x[0],x[3]-x[1]),db=Math.hypot(y[2]-y[0],y[3]-y[1]);
  return da>=db ? split(a).every(part=>certify(part,b,depth+1)) : split(b).every(part=>certify(a,part,depth+1));
}
describe("original independently bending composition",()=>{
  it("certifies original baseline centerline separation greater than70 using de Casteljau convex hull bounds",()=>{
    for(const a of ribbonFrame(0,0).cubics) for(const b of ribbonFrame(1,0).cubics) expect(certify(a,b)).toBe(true);
    expect(70-CONTROL_DISPLACEMENT_LIMITS[0]-CONTROL_DISPLACEMENT_LIMITS[1]).toBeGreaterThan(9/2+16/2);
  });
  it("anchors endpoints and bounds ALL actual controls including the reflected S handle for all phases",()=>{
    for(let sample=0;sample<160;sample++) for(const index of [0,1]) {
      const before=ribbonFrame(index,0),after=ribbonFrame(index,sample*937.173);
      after.cubics.flat().forEach((p,i)=>expect(Math.hypot(p[0]-before.cubics.flat()[i][0],p[1]-before.cubics.flat()[i][1])).toBeLessThanOrEqual(CONTROL_DISPLACEMENT_LIMITS[index]+1e-9));
      expect(after.cubics[0][0]).toEqual(before.cubics[0][0]);
      expect(after.cubics[1][3]).toEqual(before.cubics[1][3]);
      const [a,b]=after.cubics;
      expect(b[0]).toEqual(a[3]); expect(b[1][0]).toBeCloseTo(2*a[3][0]-a[2][0],10); expect(b[1][1]).toBeCloseTo(2*a[3][1]-a[2][1],10);
      for(const curve of after.cubics) for(let point=1;point<4;point++) expect(curve[point][0]).toBeGreaterThan(curve[point-1][0]);
    }
  });
  it("changes curvature with distinct phases rather than translating wrappers; ambient remains static",()=>{
    for(const index of [0,1]) {
      const before=ribbonFrame(index,0),after=ribbonFrame(index,10),delta=after.cubics[0].map((p,i)=>p[0]-before.cubics[0][i][0]);
      expect(Math.max(...delta)-Math.min(...delta)).toBeGreaterThan(2);
      expect(ribbonPath(before)).toMatch(/^M .* C .* S /);
      const start=cubicPoint(before.cubics[0],.5),next=cubicPoint(after.cubics[0],.5);
      expect(Math.hypot(next[0]-start[0],next[1]-start[1])).toBeGreaterThan(1);
    }
    const sample=(index:number)=>Array.from({length:80},(_,t)=>cubicPoint(ribbonFrame(index,t).cubics[0],.6)[0]);
    const a=sample(0),b=sample(1),ma=a.reduce((x,y)=>x+y)/a.length,mb=b.reduce((x,y)=>x+y)/b.length;
    const cross=a.reduce((s,x,i)=>s+(x-ma)*(b[i]-mb),0),energy=Math.sqrt(a.reduce((s,x)=>s+(x-ma)**2,0)*b.reduce((s,x)=>s+(x-mb)**2,0));
    expect(Math.abs(cross/energy)).toBeLessThan(.9);
    expect(ribbonFrame(2,100000)).toEqual(ribbonFrame(2,0));
  });
  it("has noticeable centreline deformation with continuous motion across long-running phases",()=>{
    for(const index of [0,1]) {
      const start=cubicPoint(ribbonFrame(index,0).cubics[0],.65);
      const distances=Array.from({length:180},(_,seconds)=>{
        const frame=ribbonFrame(index,seconds), next=ribbonFrame(index,seconds+1/120);
        frame.cubics.flat().forEach((point,i)=>expect(Math.hypot(next.cubics.flat()[i][0]-point[0],next.cubics.flat()[i][1]-point[1])).toBeLessThan(1));
        const point=cubicPoint(frame.cubics[0],.65);
        return Math.hypot(point[0]-start[0],point[1]-start[1]);
      });
      expect(Math.max(...distances)).toBeGreaterThan(index===0?14:10);
      expect(ribbonFrame(index,100000)).toEqual(ribbonFrame(index,100000));
    }
  });
  it("chooses reproducible target directions and distances rather than repeating an eight-second route",()=>{
    const targets=Array.from({length:24},(_,target)=>flowNoise(1709,target*8,8));
    expect(targets).toEqual(Array.from({length:24},(_,target)=>flowNoise(1709,target*8,8)));
    const distances=targets.map(point=>Math.hypot(...point));
    expect(Math.max(...distances)-Math.min(...distances)).toBeGreaterThan(.4);
    const quadrants=new Set(targets.map(([x,y])=>`${x>0}:${y>0}`));
    expect(quadrants.size).toBe(4);
    expect(targets.every((point,i)=>i===0||point.some((value,axis)=>value!==targets[i-1][axis]))).toBe(true);
    expect(flowNoise(1709,16,8)).not.toEqual(flowNoise(3418,16,8));
    expect(ribbonFrame(0,8)).not.toEqual(ribbonFrame(0,16));
    expect(ribbonFrame(0,16)).not.toEqual(ribbonFrame(0,24));
  });
  it("keeps the same seeded trajectory after reverse time jumps and cache eviction",()=>{
    const times=[0,1.27,8,9.54,70.1,-13.7,10000.2];
    const expected=times.map(time=>flowNoise(1709,time,8));
    for(let seed=0;seed<100;seed++) flowNoise(seed*199+7,seed*.37,8);
    expect([...times].reverse().map(time=>flowNoise(1709,time,8)).reverse()).toEqual(expected);
    expect(times.map(time=>flowNoise(1709,time,8))).toEqual(expected);
  });
  it("crosses seeded target boundaries without jumps in position, velocity or acceleration",()=>{
    const dt=.001;
    for(let target=1;target<24;target++) {
      const time=target*8;
      const before=flowNoise(1709,time-dt,8), at=flowNoise(1709,time,8), after=flowNoise(1709,time+dt,8);
      for(const axis of [0,1]) {
        expect(Math.abs(after[axis]-before[axis])).toBeLessThan(1e-8);
        expect(Math.abs((after[axis]-at[axis])/dt-(at[axis]-before[axis])/dt)).toBeLessThan(1e-6);
        expect(Math.abs((after[axis]-2*at[axis]+before[axis])/dt**2)).toBeLessThan(.001);
      }
    }
  });
});
