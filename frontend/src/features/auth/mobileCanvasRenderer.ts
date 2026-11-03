import { ribbonFrame, type WaveFrame } from "./ribbonGeometry";
import type { SceneMapping } from "./canvasRenderer";

type Stroke = { width: number; opacity: number };
type Layer = readonly [width: number, blur: number, opacity: number];
export type MobileCanvasRenderer = {
  resize: (width: number, height: number, dpr: number, mapping: SceneMapping) => void;
  render: (waves: readonly WaveFrame[]) => void;
  destroy: () => void;
};
// The existing SVG outer, inner and core cross-sections, including their group
// opacity. Only mobile replaces the live Gaussian filters with native strokes.
const LAYERS: readonly (readonly Layer[])[] = [
  [[156,28,.19*.88],[48,11,.42*.905],[9,3,.72*.85]],
  [[220,28,.15*.88],[84,11,.25*.905],[16,3,.3*.85]],
  [[300,28,.09*.88],[140,11,.1*.905]],
];
let cachedProfiles: readonly (readonly Stroke[])[] | undefined;
function erf(value: number): number {
  const sign=value<0?-1:1,x=Math.abs(value),t=1/(1+.3275911*x);
  const polynomial=((((1.061405429*t-1.453152027)*t+1.421413741)*t-.284496736)*t+.254829592)*t;
  return sign*(1-polynomial*Math.exp(-x*x));
}
function profiles() {
  return cachedProfiles ??= LAYERS.map(layers=>{
    const profile=(radius:number)=>1-layers.reduce((transmittance,[width,blur,opacity])=>{
      const alpha=opacity*.5*(erf((width/2-radius)/(blur*Math.SQRT2))+erf((width/2+radius)/(blur*Math.SQRT2)));
      return transmittance*(1-alpha);
    },1);
    const maximum=Math.max(...layers.map(([width,blur])=>width/2+blur*3)),peak=profile(.35);
    let previous=0;
    return Array.from({length:32},(_,index)=>{
      const target=peak*((index+1)/32)**2;
      let low=.35,high=maximum;
      for(let search=0;search<24;search++){
        const middle=(low+high)/2;
        if(profile(middle)>target)low=middle;else high=middle;
      }
      const stroke={width:low+high,opacity:(target-previous)/(1-previous)};
      previous=target;
      return stroke;
    });
  });
}
export function mobileRasterSize(width:number,height:number,dpr:number) {
  const scale=Math.min(Math.max(dpr,1),1.25,960/width,1280/height);
  return {width:Math.max(1,Math.round(width*scale)),height:Math.max(1,Math.round(height*scale))};
}
function rgba(color:string,opacity:number):string {
  const hex=color.trim().replace("#","");
  return `rgba(${parseInt(hex.slice(0,2),16)},${parseInt(hex.slice(2,4),16)},${parseInt(hex.slice(4,6),16)},${opacity})`;
}
function trace(context:CanvasRenderingContext2D,wave:WaveFrame) {
  context.beginPath();context.moveTo(...wave.cubics[0][0]);
  for(const curve of wave.cubics)context.bezierCurveTo(...curve[1],...curve[2],...curve[3]);
}
export function createMobileCanvasRenderer(scene:HTMLDivElement,canvas:HTMLCanvasElement,context:CanvasRenderingContext2D):MobileCanvasRenderer|null {
  const ambient=document.createElement("canvas"),ambientContext=ambient.getContext("2d");
  if(!ambientContext)return null;
  const bands=profiles(),staticAmbient=ribbonFrame(2,0);
  let mapping:SceneMapping={scale:1,x:0,y:0},scaleX=1,scaleY=1;
  let gradients:CanvasGradient[]=[];
  const transform=(target:CanvasRenderingContext2D)=>target.setTransform(mapping.scale*scaleX,0,0,mapping.scale*scaleY,mapping.x*scaleX,mapping.y*scaleY);
  const paint=(target:CanvasRenderingContext2D,wave:WaveFrame)=>{
    trace(target,wave);target.strokeStyle=gradients[wave.index];target.lineCap="round";target.lineJoin="round";
    for(const stroke of bands[wave.index]){target.lineWidth=stroke.width;target.globalAlpha=stroke.opacity;target.stroke();}
    target.globalAlpha=1;
  };
  return {
    resize(width,height,dpr,nextMapping){
      const size=mobileRasterSize(width,height,dpr);
      if(canvas.width!==size.width||canvas.height!==size.height){canvas.width=size.width;canvas.height=size.height;}
      ambient.width=size.width;ambient.height=size.height;
      mapping=nextMapping;scaleX=size.width/width;scaleY=size.height/height;
      transform(context);
      const style=getComputedStyle(scene),primary=style.getPropertyValue("--aurora-primary").trim()||"#28e7e4",secondary=style.getPropertyValue("--aurora-secondary").trim()||"#009eae",background=style.getPropertyValue("--aurora-ambient").trim()||"#08657d";
      gradients=[context.createLinearGradient(0,1000,860,0),context.createLinearGradient(380,1100,1200,470),context.createLinearGradient(0,540,1200,100)];
      const stops:readonly (readonly [number,string][])[]=[
        [[0,rgba(primary,0)],[.2,rgba(primary,.65)],[.48,primary],[.68,"#b6fffa"],[.9,rgba(primary,.65)],[1,rgba(primary,.1)]],
        [[0,rgba(secondary,0)],[.35,secondary],[.7,"#46c4cf"],[1,rgba(secondary,.25)]],
        [[0,rgba(background,0)],[.5,background],[1,rgba(background,.2)]],
      ];
      gradients.forEach((gradient,index)=>stops[index].forEach(([offset,color])=>gradient.addColorStop(offset,color)));
      transform(ambientContext);paint(ambientContext,staticAmbient);
    },
    render(waves){
      context.setTransform(1,0,0,1,0,0);context.clearRect(0,0,canvas.width,canvas.height);context.drawImage(ambient,0,0);
      transform(context);
      for(let index=waves.length-1;index>=0;index--)paint(context,waves[index]);
    },
    destroy(){
      ambient.width=ambient.height=1;gradients=[];
      context.setTransform(1,0,0,1,0,0);context.clearRect(0,0,canvas.width,canvas.height);
      canvas.width=canvas.height=1;
    },
  };
}
