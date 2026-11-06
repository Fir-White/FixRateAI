import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { useWorkspaceState } from "@/shared/lib/workspaceState";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { FilterChip } from "@/shared/ui/FilterChip";
import { Input, Select } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { TaskTable } from "@/entities/task/TaskTable";
import { useSession } from "@/shared/session/SessionContext";
import { canOpenSection } from "@/shared/lib/roles";
import { isTaskFilter, matchesTaskFilter, TASK_FILTERS, taskWorkDate, taskPriority, type TaskFilter } from "@/shared/lib/operations";
import { formatShortDate } from "@/shared/lib/format";
import "./management-redesign.css";

export function TasksPage() {
  const {profile}=useSession();
  const query=useApiQuery(()=>maintenanceApi.listTasks(),[]);
  const [params,setParams]=useSearchParams();
  const [savedFilter,setSavedFilter]=useWorkspaceState<TaskFilter>("tasks.filter","all",isTaskFilter);
  const status=params.get("status"); const filter=isTaskFilter(status)?status:savedFilter;
  const search=params.get("q")??"", equipment=params.get("equipment")??"", date=params.get("date"), due=params.get("due");
  const timezone=profile?.timezone??"Asia/Yekaterinburg";
  const update=(key:string,value:string,replace=false)=>{const next=new URLSearchParams(params);if(key!=="page")next.delete("page");if(value)next.set(key,value);else next.delete(key);setParams(next,{replace});};
  const changeFilter=(value:TaskFilter)=>{setSavedFilter(value);update("status",value);};
  const clear=()=>{setSavedFilter("all");setParams({});};
  const all=query.status==="success"?query.data:[];
  const options=[...new Map(all.filter(t=>t.equipmentId).map(t=>[t.equipmentId!,t.equipmentName])).entries()];
  const tasks=useMemo(()=>all.filter(task=>matchesTaskFilter(task,filter) && (!equipment||task.equipmentId===equipment) && (!date||taskWorkDate(task,timezone)===date) && (!due||task.mandatoryDueDate===due) && (!search.trim()||[task.code,task.title,task.equipmentName,...task.assignees.map(a=>a.name)].join(" ").toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru")))),[query.data,filter,equipment,date,due,search,timezone]);
  const primaryFilters=TASK_FILTERS.filter(item=>["all","attention","unassigned","in_progress","submitted","accepted"].includes(item.value));
  const ordered=[...tasks].sort((a,b)=>taskPriority(a)-taskPriority(b)||(a.mandatoryDueDate??"z").localeCompare(b.mandatoryDueDate??"z")||a.id.localeCompare(b.id));
  const pageCount=Math.max(1,Math.ceil(ordered.length/25));
  const requestedPage=Number(params.get("page")??1);
  const page=Number.isSafeInteger(requestedPage)?Math.min(pageCount,Math.max(1,requestedPage)):1;
  const visible=ordered.slice((page-1)*25,page*25);
  return <div className="space-y-6 fr-task-page">
    <PageHeader eyebrow={profile?.role==="director"?"Контроль / результаты работ":"Исполнение / диспетчеризация"} title="Наряды и назначения" description={profile?.role==="director"?"Просматривайте обязательные сроки, результаты работ и решения инженера.":"Назначайте бригады, следите за выполнением и обязательными сроками."}
      actions={<><Link to="/calendar" className={buttonClassName("secondary")}><Icon name="calendar" size={16}/>Календарь</Link>{canOpenSection(profile?.role,"quality")&&<Link to="/quality" className={buttonClassName("primary")}>Открыть приёмку</Link>}</>}/>
    <Card className="fr-register">
      <div className="fr-register-tabs" aria-label="Фильтр нарядов">{primaryFilters.map(item=><FilterChip key={item.value} active={filter===item.value} onClick={()=>changeFilter(item.value)}>{item.label}<span className="fr-tab-count">{all.filter(task=>matchesTaskFilter(task,item.value)).length}</span></FilterChip>)}</div>
      <div className="fr-register-tools"><Input aria-label="Поиск нарядов" value={search} onChange={event=>update("q",event.target.value,true)} placeholder="Найти по названию, коду или исполнителю" leadingIcon={<Icon name="search" size={16}/>}/>
        <Select aria-label="Оборудование" value={equipment} onChange={event=>update("equipment",event.target.value)}><option value="">Всё оборудование</option>{options.map(([id,name])=><option key={id} value={id}>{name}</option>)}</Select>
        <Select aria-label="Статус наряда" value={filter} onChange={event=>changeFilter(event.target.value as TaskFilter)}>{TASK_FILTERS.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}</Select>
      </div>
      {(date||due||equipment||search||filter!=="all")&&<div className="fr-active-filters"><span>Найдено: <strong>{tasks.length}</strong></span>{date&&<button type="button" onClick={()=>update("date","")}>Работы на {formatShortDate(date)} ×</button>}{due&&<button type="button" onClick={()=>update("due","")}>Срок {formatShortDate(due)} ×</button>}<button type="button" onClick={clear}>Сбросить фильтры</button></div>}
      {query.status==="loading"&&<LoadingState/>}{query.status==="error"&&<ErrorState description={query.error}/>}
      {query.status==="success"&&(tasks.length?<TaskTable items={visible}/>:<EmptyState title={all.length?"Заданий по фильтру нет":"Заданий пока нет"} description={all.length?"Измените поиск или фильтры. Данные, не подходящие под условия, не удалены.":"На доступном объекте пока нет заданий."} action={all.length?<Button variant="secondary" onClick={clear}>Сбросить фильтры</Button>:undefined}/>) }
      {query.status==="success"&&tasks.length>0&&<nav className="fr-pagination" aria-label="Страницы заданий"><span>Показаны {(page-1)*25+1}–{Math.min(page*25,tasks.length)} из {tasks.length}. Сначала актуальные работы.</span>{pageCount>1&&<div><Button variant="secondary" disabled={page===1} onClick={()=>update("page",String(page-1))}>Предыдущая</Button><span>{page} / {pageCount}</span><Button variant="secondary" disabled={page===pageCount} onClick={()=>update("page",String(page+1))}>Следующая</Button></div>}</nav>}
      {query.status==="success"&&<div className="fr-section-footer"><span>{tasks.length} из {all.length} нарядов</span><span>Обязательный срок и плановое время показаны отдельно</span></div>}
    </Card>
  </div>;
}
