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
const ACTIVE:TaskState[]=["assigned","in_progress","rework_required"];
const ORDER:Record<TaskState,number>={in_progress:0,rework_required:1,assigned:2,submitted:3,accepted:4,draft:5,cancelled:6};
export function ExecutorPage(){
 const {profile}=useSession(); const id=profile?.userId??"";
 const query=useApiQuery(()=>maintenanceApi.listExecutorTasks(id),[id]);
 const [filter,setFilter]=useState("active"); const [params,setParams]=useSearchParams(); const equipment=params.get("equipment");
 const all=[...(query.data??[])].filter(t=>!equipment||t.equipmentId===equipment).sort((a,b)=>Number(isTaskOverdue(b))-Number(isTaskOverdue(a))||ORDER[a.state]-ORDER[b.state]);
 const active=all.filter(t=>ACTIVE.includes(t.state));const review=all.filter(t=>t.state==="submitted");
 const items=filter==="active"?active:filter==="submitted"?review:all;
 const spotlight=filter==="active"?items.find(t=>t.state==="in_progress")??items[0]:undefined;
 return <div className="space-y-6 executor-workspace"><PageHeader title="Мои задания" description="Только назначенные вам работы. Приоритет — текущая работа и обязательные сроки." actions={<Link to="/my-shifts" className={buttonClassName("secondary","sm")}><Icon name="clock" size={16}/>Мои смены</Link>}/>
 {query.status==="loading"&&<LoadingState label="Загрузка назначенных заданий"/>}{query.status==="error"&&<ErrorState description={query.error}/>}
 {query.status==="success"&&<><div className="executor-tabs">{([['active','В работе',active.length],['submitted','На проверке',review.length],['all','Все',all.length]] as const).map(([value,label,count])=><button key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{label}<strong>{count}</strong></button>)}</div>
 {equipment&&<div className="ops-active-filters"><span>Показаны задания выбранного оборудования</span><button onClick={()=>setParams({})}>Сбросить ×</button></div>}
 {spotlight&&<section className="executor-spotlight"><div className="executor-spotlight-eyebrow"><span>{spotlight.state==="in_progress"?"Продолжить выполнение":"Следующая приоритетная работа"}</span><span className="font-mono">{spotlight.code}</span></div><div className="flex flex-wrap gap-2"><TaskStateBadge state={spotlight.state}/>{isTaskOverdue(spotlight)&&<OverdueBadge/>}</div><h2>{spotlight.title}</h2><p>{spotlight.equipmentName}</p><div className="executor-spotlight-bottom"><div><span>Обязательный срок</span><strong>{formatDate(spotlight.mandatoryDueDate)}</strong></div><Link to={`/executor/tasks/${spotlight.id}`} className={buttonClassName("primary")}>{spotlight.state==="in_progress"?"Продолжить работу":"Открыть задание"}<Icon name="chevron" size={17}/></Link></div></section>}
 {items.length===0?<EmptyState title={all.length?"В этой очереди пока нет заданий":"Назначенных заданий нет"} description="Когда диспетчер назначит работу, она появится здесь."/>:<div className="executor-queue">{items.filter(t=>t.id!==spotlight?.id).map(task=><TaskRow key={task.id} task={task}/>)}</div>}
 <div className="executor-handoff"><Icon name="quality" size={19}/><p>После сдачи отчёт фиксируется и передаётся инженеру. Возврат на доработку создаёт отдельную попытку — история не теряется.</p></div></>}
 </div>;
}
function TaskRow({task}:{task:MaintenanceTask}){const dateTime=useSiteDateTime();return <article className="executor-task-row"><div className="executor-row-top"><span>{task.code}</span><TaskStateBadge state={task.state}/>{isTaskOverdue(task)&&<OverdueBadge/>}</div><Link to={`/executor/tasks/${task.id}`}><h2>{task.title}</h2><Icon name="chevron" size={20}/></Link><p>{task.equipmentName}</p><div className="executor-row-dates"><span>Срок <b>{formatDate(task.mandatoryDueDate)}</b></span><span>План <b>{dateTime(task.scheduledStart)}</b></span></div></article>;}
