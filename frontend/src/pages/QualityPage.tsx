import { readQueries } from "@/shared/api/readQueries";
import { Link, useSearchParams } from "react-router-dom";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { TaskTable } from "@/entities/task/TaskTable";
import { Icon } from "@/shared/ui/Icon";
import { Input } from "@/shared/ui/Form";
import "./quality-redesign.css";
export function QualityPage() {
  const query=useApiQuery(readQueries.quality.load,[],undefined,readQueries.quality.key);
  const [params,setParams]=useSearchParams();
  const filter=['all','submitted','rework_required'].includes(params.get('queue')??'')?params.get('queue')!:'submitted';
  const search=params.get('q')??'';
  const update=(key:string,value:string)=>setParams(previous=>{const next=new URLSearchParams(previous);if(key!=='page')next.delete('page');value?next.set(key,value):next.delete(key);return next;},{replace:key==='q'});
  const all=query.data??[];
  const items=all.filter(task=>(filter==="all"||task.state===filter)&&`${task.title} ${task.code} ${task.equipmentName}`.toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru")));
  const pages=Math.max(1,Math.ceil(items.length/25)),requested=Number(params.get('page')??1),page=Number.isSafeInteger(requested)?Math.max(1,Math.min(pages,requested)):1;
  return <div className="space-y-6"><PageHeader title="Приёмка работ" description="Отчёты текущего объекта, ожидающие решения инженера." actions={<Link to="/tasks" className={buttonClassName("secondary")}>Все наряды</Link>}/>
    {query.status==="loading"&&<LoadingState label="Загрузка очереди приёмки"/>}{query.status==="error"&&<ErrorState description={query.error}/>}
    {query.status==="success"&&<section className="ops-register"><div className="ops-register-tabs" aria-label="Очереди приёмки">{([['submitted','Ожидают решения'],['rework_required','На доработке'],['all','Вся очередь']] as const).map(([id,label])=><button key={id} aria-pressed={filter===id} onClick={()=>update('queue',id)}>{label}<span>{id==='all'?all.length:all.filter(t=>t.state===id).length}</span></button>)}</div>
    <div className="ops-register-tools"><div className="w-full max-w-md"><Input leadingIcon={<Icon name="search" size={17}/>} aria-label="Поиск в очереди приёмки" placeholder="Наряд, оборудование или операция" value={search} onChange={e=>update('q',e.target.value)}/></div></div>
    {items.length?<TaskTable items={items.slice((page-1)*25,page*25)} detailBasePath="/quality"/>:<EmptyState title={all.length?"В этой выборке нет отчётов":"Очередь приёмки пуста"} description="Новые отчёты появятся после отправки работы исполнителем."/>}{pages>1&&<nav className="fr-pagination" aria-label="Страницы приёмки"><Button variant="secondary" disabled={page===1} onClick={()=>update('page',String(page-1))}>Предыдущая</Button><span>{page} / {pages}</span><Button variant="secondary" disabled={page===pages} onClick={()=>update('page',String(page+1))}>Следующая</Button></nav>}</section>}
  </div>;
}
