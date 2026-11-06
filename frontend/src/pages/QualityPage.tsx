import { useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { TaskTable } from "@/entities/task/TaskTable";
import { Icon } from "@/shared/ui/Icon";
import "./quality-redesign.css";
export function QualityPage() {
  const query=useApiQuery(()=>maintenanceApi.listQualityQueue(),[]);
  const [filter,setFilter]=useState("all");
  const [search,setSearch]=useState("");
  const all=query.data??[];
  const items=all.filter(task=>(filter==="all"||task.state===filter)&&`${task.title} ${task.code} ${task.equipmentName}`.toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru")));
  return <div className="space-y-6"><PageHeader eyebrow="Инженер / Проверка исполнения" title="Контроль качества и приёмка" description="Сначала доказательства и ограничения. Затем — личное решение инженера с обязательным основанием." actions={<Link to="/tasks" className={buttonClassName("secondary")}>Все наряды</Link>}/>
    <details className="fr-quality-principle"><summary>Модель анализирует. Инженер принимает.</summary><p>Фото подтверждают только видимые изменения. Показания и невидимые операции проверяются отдельно.</p></details>
    {query.status==="loading"&&<LoadingState label="Загрузка очереди приёмки"/>}{query.status==="error"&&<ErrorState description={query.error}/>}
    {query.status==="success"&&<section className="ops-register"><div className="ops-register-tabs" aria-label="Очереди приёмки">{([['all','Вся очередь'],['submitted','Ожидают решения'],['rework_required','На доработке']] as const).map(([id,label])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}<span>{id==='all'?all.length:all.filter(t=>t.state===id).length}</span></button>)}</div>
    <div className="ops-register-tools"><label className="ops-search"><Icon name="search" size={17}/><input aria-label="Поиск в очереди приёмки" placeholder="Наряд, оборудование, операция" value={search} onChange={e=>setSearch(e.target.value)}/></label><span className="text-xs text-muted">История попыток сохраняется при возврате</span></div>
    {items.length?<TaskTable items={items} detailBasePath="/quality"/>:<EmptyState title={all.length?"В этой выборке нет отчётов":"Очередь приёмки пуста"} description="Новые отчёты появятся после отправки работы исполнителем."/>}</section>}
  </div>;
}
