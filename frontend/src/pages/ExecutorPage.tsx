import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { useSession } from "@/shared/session/SessionContext";
import { formatDate } from "@/shared/lib/format";
import { isTaskOverdue } from "@/shared/lib/operations";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { OverdueBadge, TaskStateBadge } from "@/shared/ui/StatusBadge";
import type { MaintenanceTask, TaskState } from "@/shared/types/domain";
import { Input, Select } from "@/shared/ui/Form";
import "./executor-redesign.css";
const ACTIVE:TaskState[]=["assigned","in_progress","rework_required"];
const ORDER:Record<TaskState,number>={in_progress:0,rework_required:1,assigned:2,submitted:3,accepted:4,draft:5,cancelled:6};
export function ExecutorPage(){
 const {profile}=useSession(); const id=profile?.userId??"";
 const query=useApiQuery(()=>maintenanceApi.listExecutorTasks(id),[id]);
 const [params,setParams]=useSearchParams(); const equipment=params.get("equipment");
 const filter=params.get("queue")??"active";
 const setFilter=(value:string)=>setParams(previous=>{const next=new URLSearchParams(previous);next.set("queue",value);return next;});
 const [search,setSearch]=useState(""); const [from,setFrom]=useState(""); const [to,setTo]=useState(""); const [sort,setSort]=useState("priority");
 const all=[...(query.data??[])].filter(t=>!equipment||t.equipmentId===equipment).sort((a,b)=>Number(isTaskOverdue(b))-Number(isTaskOverdue(a))||ORDER[a.state]-ORDER[b.state]);
 const active=all.filter(t=>ACTIVE.includes(t.state));const review=all.filter(t=>t.state==="submitted");
 const history=all.filter(t=>`${t.title} ${t.equipmentName} ${t.code}`.toLocaleLowerCase("ru").includes(search.toLocaleLowerCase("ru"))&&(!from||!!t.mandatoryDueDate&&t.mandatoryDueDate>=from)&&(!to||!!t.mandatoryDueDate&&t.mandatoryDueDate<=to));
 if(sort!=="priority")history.sort((a,b)=>!a.mandatoryDueDate?1:!b.mandatoryDueDate?-1:(sort==="newest"?-1:1)*a.mandatoryDueDate.localeCompare(b.mandatoryDueDate));
 const items=filter==="active"?active:filter==="submitted"?review:history;
 const spotlight=filter==="active"?items.find(t=>t.state==="in_progress")??items[0]:undefined;
 return <div className={`space-y-6 executor-workspace${spotlight?" has-spotlight":""}`}><PageHeader title="Мои задания" description="Только назначенные вам работы. Приоритет — текущая работа и обязательные сроки."/>
 {query.status==="loading"&&<LoadingState label="Загрузка назначенных заданий"/>}{query.status==="error"&&<ErrorState description={query.error}/>}
 {query.status==="success"&&<><div className="executor-tabs">{([['active','К выполнению',active.length],['submitted','На проверке',review.length],['all','Все',all.length]] as const).map(([value,label,count])=><button key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{label}<strong>{count}</strong></button>)}</div>
 {filter==="all"&&<section aria-label="Поиск по загруженным заданиям" className="fr-history-toolbar"><label className="fr-history-search">Поиск<Input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Работа, оборудование или код"/></label><label>Срок с<Input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>Срок по<Input type="date" value={to} onChange={e=>setTo(e.target.value)}/></label><label className="fr-history-order">Порядок<Select value={sort} onChange={e=>setSort(e.target.value)}><option value="priority">По приоритету</option><option value="newest">Поздние сроки</option><option value="oldest">Ранние сроки</option></Select></label><p>Найдено {items.length} из {all.length} загруженных заданий</p>{(search||from||to)&&<button onClick={()=>{setSearch("");setFrom("");setTo("");}}>Сбросить поиск и период</button>}</section>}
 {equipment&&<div className="ops-active-filters"><span>Показаны задания выбранного оборудования</span><button onClick={()=>setParams({})}>Сбросить ×</button></div>}
 {spotlight&&<section className="executor-spotlight"><div className="flex flex-wrap gap-2"><span className="text-xs text-muted font-mono">{spotlight.code}</span><TaskStateBadge state={spotlight.state}/>{isTaskOverdue(spotlight)&&<OverdueBadge/>}</div><h2>{spotlight.title}</h2><p>{spotlight.equipmentName}</p><div className="executor-spotlight-bottom"><div><span>Обязательный срок</span><strong>{formatDate(spotlight.mandatoryDueDate)}</strong></div><Link to={`/executor/tasks/${spotlight.id}`} className={buttonClassName("primary")}>{spotlight.state==="in_progress"?"Продолжить работу":"Открыть задание"}<Icon name="chevron" size={17}/></Link></div></section>}
 {items.length===0?<EmptyState title={filter==="all"&&(search||from||to)?"По этим условиям задания не найдены":all.length?"В этой очереди пока нет заданий":"Назначенных заданий нет"} description={filter==="all"&&(search||from||to)?"Измените поиск или сбросьте период.":"Когда диспетчер назначит работу, она появится здесь."}/>:<div className="executor-queue">{items.filter(t=>t.id!==spotlight?.id).map(task=><TaskRow key={task.id} task={task}/>)}</div>}
 <div className="executor-handoff"><Icon name="quality" size={19}/><p>После сдачи отчёт фиксируется и передаётся инженеру. Возврат на доработку создаёт отдельную попытку — история не теряется.</p></div></>}
 </div>;
}
function TaskRow({task}:{task:MaintenanceTask}){const dateTime=useSiteDateTime();return <article className="executor-task-row"><div className="executor-row-top"><span>{task.code}</span><TaskStateBadge state={task.state}/>{isTaskOverdue(task)&&<OverdueBadge/>}</div><Link to={`/executor/tasks/${task.id}`}><h2>{task.title}</h2><Icon name="chevron" size={20}/></Link><p>{task.equipmentName}</p><div className="executor-row-dates"><span>Срок <b>{formatDate(task.mandatoryDueDate)}</b></span><span>План <b>{dateTime(task.scheduledStart)}</b></span></div></article>;}
