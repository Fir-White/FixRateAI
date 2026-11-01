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
function bernstein(index:number,t:number):number {return [(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3][index];}
function excursionEnvelope(segment:number,low:number,high:number):number {
  const moving=segment===0 ? [1,2,3] : [0,1,2];
  return moving.reduce((sum,index)=>{
    const critical=index===1 ? 1/3 : index===2 ? 2/3 : undefined;
    const values=[bernstein(index,low),bernstein(index,high)];
    if(critical!==undefined&&low<=critical&&critical<=high)values.push(bernstein(index,critical));
    return sum+Math.max(...values)**(8/7);
  },0)**(7/8);
}
// Independent interval proof: baseline convex hulls minus Holder excursion
// bounds from the GLOBAL p8 budget, not a finite sample of animated frames.
function certifyFlow(a:Cubic,ai:number,al:number,ah:number,b:Cubic,bi:number,bl:number,bh:number,depth=0):boolean {
  const x=box(a),y=box(b),dx=Math.max(0,x[0]-y[2],y[0]-x[2]),dy=Math.max(0,x[1]-y[3],y[1]-x[3]);
  const separation=Math.hypot(dx,dy)-CONTROL_DISPLACEMENT_LIMITS[0]*excursionEnvelope(ai,al,ah)-CONTROL_DISPLACEMENT_LIMITS[1]*excursionEnvelope(bi,bl,bh);
  if(separation>15+1e-7)return true;
  if(depth>=32)return false;
  if(Math.hypot(x[2]-x[0],x[3]-x[1])>=Math.hypot(y[2]-y[0],y[3]-y[1])) {
    const [left,right]=split(a),midpoint=(al+ah)/2;
    return certifyFlow(left,ai,al,midpoint,b,bi,bl,bh,depth+1)&&certifyFlow(right,ai,midpoint,ah,b,bi,bl,bh,depth+1);
  }
  const [left,right]=split(b),midpoint=(bl+bh)/2;
  return certifyFlow(a,ai,al,ah,left,bi,bl,midpoint,depth+1)&&certifyFlow(a,ai,al,ah,right,bi,midpoint,bh,depth+1);
}
describe("original independently bending composition",()=>{
  it("certifies original baseline centerline separation greater than70 using de Casteljau convex hull bounds",()=>{
    for(const a of ribbonFrame(0,0).cubics) for(const b of ribbonFrame(1,0).cubics) expect(certify(a,b)).toBe(true);
  });
  it("certifies larger global control budgets leave both cores separated for every time and never create loops",()=>{
    const first=ribbonFrame(0,0),second=ribbonFrame(1,0);
    first.cubics.forEach((a,ai)=>second.cubics.forEach((b,bi)=>expect(certifyFlow(a,ai,0,1,b,bi,0,1)).toBe(true)));
    expect(15).toBeGreaterThan(9/2+16/2);
    [first,second].forEach((frame,index)=>frame.cubics.forEach((curve,segment)=>curve.slice(1).forEach((point,i)=>{
      const fixed=(segment===0&&i===0)||(segment===1&&i===2),joined=(segment===0&&i===2)||(segment===1&&i===0);
      const bound=CONTROL_DISPLACEMENT_LIMITS[index]*(fixed?1:joined?1/2**(1/8):2**(7/8));
      expect(point[0]-curve[i][0]-bound).toBeGreaterThan(1e-7);
    })));
  });
  it("anchors endpoints and bounds ALL actual controls including the reflected S handle for all phases",()=>{
    for(let sample=0;sample<160;sample++) for(const index of [0,1]) {
      const before=ribbonFrame(index,0),after=ribbonFrame(index,sample*937.173);
      after.cubics.flat().forEach((p,i)=>expect(Math.hypot(p[0]-before.cubics.flat()[i][0],p[1]-before.cubics.flat()[i][1])).toBeLessThanOrEqual(CONTROL_DISPLACEMENT_LIMITS[index]+1e-9));
      const actual=[0,1,2,3,5,6,7].map(i=>{const p=after.cubics.flat()[i],b=before.cubics.flat()[i];return Math.hypot(p[0]-b[0],p[1]-b[1]);});
      expect(actual.reduce((sum,distance)=>sum+distance**8,0)).toBeLessThanOrEqual(CONTROL_DISPLACEMENT_LIMITS[index]**8*(1+1e-10));
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
  it("crosses seeded spline knots with C2 continuity and through-velocity instead of compulsory target stops",()=>{
    const dt=.001;
    for(let target=1;target<24;target++) {
      const time=target*8;
      const before=flowNoise(1709,time-dt,8), at=flowNoise(1709,time,8), after=flowNoise(1709,time+dt,8);
      for(const axis of [0,1]) {
        expect(Math.abs(after[axis]-before[axis])).toBeLessThan(.001);
        expect(Math.abs((after[axis]-at[axis])/dt-(at[axis]-before[axis])/dt)).toBeLessThan(.0001);
        const earlier=flowNoise(1709,time-2*dt,8),later=flowNoise(1709,time+2*dt,8);
        const leftAcceleration=(at[axis]-2*before[axis]+earlier[axis])/dt**2,rightAcceleration=(later[axis]-2*after[axis]+at[axis])/dt**2;
        expect(Math.abs(leftAcceleration-rightAcceleration)).toBeLessThan(.0001);
      }
      expect(Math.hypot((after[0]-before[0])/(2*dt),(after[1]-before[1])/(2*dt))).toBeGreaterThan(.001);
    }
  });
  it("maintains visibly changing curvature and a larger excursion through ten minutes without shared dead windows",()=>{
    const maximum=[0,0],minimum=[Infinity,Infinity];
    for(let step=0;step<=2400;step++) {
      const movement=[0,0];
      for(const index of [0,1]) {
        const frame=ribbonFrame(index,step*.25),next=ribbonFrame(index,step*.25+1),start=ribbonFrame(index,0);
        for(const segment of [0,1]) for(const t of [.25,.5,.75]) {
          const a=cubicPoint(frame.cubics[segment],t),b=cubicPoint(next.cubics[segment],t),original=cubicPoint(start.cubics[segment],t);
          movement[index]=Math.max(movement[index],Math.hypot(b[0]-a[0],b[1]-a[1]));
          maximum[index]=Math.max(maximum[index],Math.hypot(a[0]-original[0],a[1]-original[1]));
        }
        minimum[index]=Math.min(minimum[index],movement[index]);
      }
      expect(Math.max(...movement)).toBeGreaterThan(1);
    }
    expect(maximum[0]).toBeGreaterThan(37);expect(maximum[1]).toBeGreaterThan(28);
    expect(minimum[0]).toBeGreaterThan(.9);expect(minimum[1]).toBeGreaterThan(.6);
  });
});
