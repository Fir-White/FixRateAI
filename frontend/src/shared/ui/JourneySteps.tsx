import { useEffect, useId, useState, type ReactNode } from 'react';

export interface JourneyStep {id:string;title:string;description?:string;content:()=>ReactNode}

/** Visit on demand; keep visited forms mounted so changing a step loses no input. */
export function JourneySteps({label,steps,value,onChange,startAt=1,numbered=true,hideNavigation=false}:{label:string;steps:JourneyStep[];value:string;onChange:(id:string)=>void;startAt?:number;numbered?:boolean;hideNavigation?:boolean}) {
  const identity=useId(),selected=steps.some(step=>step.id===value)?value:steps[0].id;
  const [visited,setVisited]=useState(()=>new Set([selected]));
  useEffect(()=>{setVisited(previous=>previous.has(selected)?previous:new Set([...previous,selected]));},[selected]);
  return <div className="space-y-5"><nav className="journey-step-navigation" aria-label={label} hidden={hideNavigation} inert={hideNavigation}><ol className="journey-steps">{steps.map((step,index)=><li key={step.id}><button type="button" id={`${identity}-step-${step.id}`} aria-current={selected===step.id?'step':undefined} aria-controls={`${identity}-panel-${step.id}`} onClick={()=>onChange(step.id)}>{numbered&&<span className="journey-step-number" aria-hidden="true">{index+startAt}</span>}{step.title}</button></li>)}</ol></nav>{steps.map(step=><section key={step.id} id={`${identity}-panel-${step.id}`} aria-labelledby={`${identity}-step-${step.id}`} className="journey-panel" hidden={selected!==step.id} inert={selected!==step.id}>{(visited.has(step.id)||selected===step.id)&&<>{step.description&&<p className="text-sm text-muted mb-4">{step.description}</p>}{step.content()}</>}</section>)}</div>;
}
