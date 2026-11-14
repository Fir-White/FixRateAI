import { useDeferredValue,useState } from 'react';
import { draftPlansApi as api,type PlanningChoice } from '@/shared/api/draftPlans';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { FieldCaption,Input } from '@/shared/ui/Form';
import { ErrorState,LoadingState } from '@/shared/ui/States';

export function PlanningChoices({kind,selected,onAdd}:{kind:'skills'|'workers';selected:string[];onAdd:(item:PlanningChoice)=>void}) {
  const [open,setOpen]=useState(false),[search,setSearch]=useState(''),[offset,setOffset]=useState(0);
  const needle=useDeferredValue(search),label=kind==='skills'?'Допуски':'Исполнители';
  return <div className="space-y-3"><Button variant="secondary" aria-expanded={open} disabled={selected.length>=100} onClick={()=>setOpen(v=>!v)}>{kind==='skills'?'Добавить допуск':'Добавить исполнителя'}</Button>{open&&<>
    <label><FieldCaption>{label}: поиск</FieldCaption><Input aria-label={`${label}: поиск`} value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label>
    <Results kind={kind} q={needle} offset={offset} selected={selected} onAdd={onAdd} onPage={setOffset}/>
  </>}</div>;
}
function Results({kind,q,offset,selected,onAdd,onPage}:{kind:'skills'|'workers';q:string;offset:number;selected:string[];onAdd:(item:PlanningChoice)=>void;onPage:(n:number)=>void}) {
  const query=useApiQuery(()=>api.choices(kind,q,offset),[kind,q,offset],undefined,`planning-choices:${JSON.stringify([kind,q,offset])}`);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  return <><ul className="space-y-2">{query.data.items.map(item=><li key={item.id}><Button variant="secondary" disabled={selected.includes(item.id)||selected.length>=100} onClick={()=>onAdd(item)}>{item.label}</Button></li>)}</ul>{!query.data.total&&<p>Подходящих записей нет.</p>}
    <PlanningPages offset={offset} total={query.data.total} onPage={onPage}/></>;
}
export function PlanningPages({offset,total,onPage}:{offset:number;total:number;onPage:(n:number)=>void}) {return total>25&&<nav className="flex flex-wrap items-center gap-3" aria-label="Страницы планирования"><Button variant="secondary" disabled={offset===0} onClick={()=>onPage(offset-25)}>Назад</Button><span>{offset+1}–{Math.min(offset+25,total)} из {total}</span><Button variant="secondary" disabled={offset+25>=total} onClick={()=>onPage(offset+25)}>Далее</Button></nav>;}
