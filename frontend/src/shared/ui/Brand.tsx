import mark from "@/assets/fixrate-mark.svg";
import wordmark from "@/assets/fixrate-wordmark.svg";
export function BrandMark({size=44,className=""}:{size?:number;className?:string}) {return <img src={mark} width={size} height={size} alt="" aria-hidden="true" className={className}/>;}
export function BrandLockup({subtitle="ТО / ППР",size="md"}:{subtitle?:string;size?:"sm"|"md"|"lg"}) {return <span className="flex items-center gap-3"><BrandMark size={size==="lg"?56:size==="sm"?34:42}/><span><img src={wordmark} alt="FixRate AI" width={size==="lg"?174:138}/><span className="mt-1 block text-[10px] tracking-widest text-muted">{subtitle}</span></span></span>;}
