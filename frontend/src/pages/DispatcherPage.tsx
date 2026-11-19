import { readQueries } from "@/shared/api/readQueries";
import { PerformanceOverview } from "@/features/analyst/AnalystPanels";
import { useState } from "react";
import { Link } from "react-router-dom";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { todayAt, formatShortDate, pluralize } from "@/shared/lib/format";
import { canOpenSection } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { IconButton } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { TaskLine } from "@/entities/task/TaskLine";
import { DEMO_DATE, dateLabel, isOpenTask, isTaskOverdue, isUnassigned, matchesTaskFilter, shiftDay, taskPriority, taskWorkDate, weekFor } from "@/shared/lib/operations";
import "./management-redesign.css";
import { DailyActions } from '@/features/navigation/DailyActions';
import { WorkdayHeading, WorkdayUpcoming } from '@/features/navigation/Workday';
import { WorkdayAssistant } from '@/features/assistant/WorkdayAssistant';

export function DispatcherPage() {
  const {profile}=useSession();
  const timezone=profile?.timezone??"Asia/Yekaterinburg";
  const today=DEMO_MODE?DEMO_DATE:todayAt(timezone);
  const [selected,setSelected]=useState(today);
  const admin=profile?.role==="admin";
  const canTasks=canOpenSection(profile?.role,"tasks"), canCalendar=canOpenSection(profile?.role,"calendar"), canCompare=canOpenSection(profile?.role,"comparisons");
  const query=useApiQuery(readQueries.tasks.load,[],undefined,readQueries.tasks.key);
  const forecasts=useApiQuery(()=>canCompare?readQueries.comparisons.load():Promise.resolve([]),[canCompare],undefined,canCompare?readQueries.comparisons.key:undefined);
  const workforce=useApiQuery(()=>admin&&!DEMO_MODE?readQueries.workforce.load():Promise.resolve(null),[admin],undefined,admin&&!DEMO_MODE?readQueries.workforce.key:undefined);
  if(query.status==="loading")return <LoadingState label="Загрузка оперативного центра"/>;
  if(query.status==="error")return <ErrorState description={query.error}/>;
  const tasks=query.data, open=tasks.filter(isOpenTask);
  const dates=new Map(tasks.map(task=>[task.id,taskWorkDate(task,timezone)??""]));
  const days=weekFor(selected);
  const daily=tasks.filter(t=>t.state!=="cancelled" && dates.get(t.id)===selected).sort((a,b)=>(a.scheduledStart??"z").localeCompare(b.scheduledStart??"z")||taskPriority(a)-taskPriority(b));
  const attention=tasks.filter(t=>matchesTaskFilter(t,"attention")).sort((a,b)=>taskPriority(a)-taskPriority(b));
  const overdue=tasks.filter(isTaskOverdue).length, unassigned=tasks.filter(isUnassigned).length, review=tasks.filter(t=>t.state==="submitted").length;
  const run=forecasts.status==="success"?[...forecasts.data].sort((a,b)=>b.createdAt.localeCompare(a.createdAt))[0]:null;
  const rawReason=run?.decision.reasons[0];
  const reason=rawReason?.includes("INSUFFICIENT_HISTORY")?"Для AI-прогноза недостаточно принятой истории. Используется подтверждённый регламент.":rawReason?.startsWith("AI_UNAVAILABLE")?"AI-прогноз сейчас недоступен. Обязательный срок сохраняется.":rawReason?.startsWith("AI_")?"Результат требует проверки. Исходное обоснование доступно ниже.":rawReason;
  const director=profile?.role==="director", chief=profile?.role==="chief_engineer";
  const title=director?"Обзор объекта":chief?"С чего начнём рабочий день?":admin?"Рабочее пространство":profile?.role==="engineer"?"Рабочий день инженера":"Рабочий день диспетчера";
  const signals=admin ? (workforce.data?.applications ? [{value:workforce.data.applications.length,label:"Заявки на доступ",to:"/settings/workforce?view=access"}]:[]) : [
    {value:overdue,label:"Просрочено",to:canTasks?"/tasks?status=overdue":undefined,tone:"danger" as const},
    director
      ? {value:tasks.filter(t=>t.state==="accepted").length,label:"Принято",to:"/tasks?status=accepted"}
      : {value:unassigned,label:"Без исполнителя",to:canTasks?"/tasks?status=unassigned":undefined,tone:"warning" as const},
  ];
  const upcoming=open.filter(task=>(dates.get(task.id)??"")>=today)
    .sort((a,b)=>(dates.get(a.id)??"").localeCompare(dates.get(b.id)??"")||(a.scheduledStart??"z").localeCompare(b.scheduledStart??"z"));
  return <div className="fr-overview fr-management-v2">
    <WorkdayHeading title={title} description={admin?"Оборудование, команда и доступы.":`${open.length} ${pluralize(open.length,"незавершённая работа","незавершённые работы","незавершённых работ")}`} label={admin?"Подготовка и доступы":"Сроки и назначения"} signals={signals}/>
    <WorkdayAssistant/>
    {!admin && <WorkdayUpcoming tasks={upcoming} link={canCalendar?`/calendar?date=${selected}`:undefined} linkText="Открыть график"/>}
    <DailyActions/>
    <div className="fr-overview-grid"><div className="fr-overview-work">
      <section className="fr-attention" aria-labelledby="attention-title"><div className="fr-section-heading"><div><h2 id="attention-title">Требуют внимания <span className="fr-count">{attention.length}</span></h2></div>{canTasks&&<Link className="fr-text-link" to="/tasks?status=attention">Вся очередь →</Link>}</div>
        {attention.length?<ul className="fr-task-lines">{attention.slice(0,4).map(task=><TaskLine key={task.id} task={task} compact/>)}</ul>:<div className="fr-empty-inline compact"><Icon name="check"/><p>Нет просроченных, неназначенных нарядов и отчётов, ожидающих решения.</p></div>}
        {attention.length>4&&<p className="text-xs text-muted mt-3">Показаны 4 из {attention.length}. Остальные — в полной очереди.</p>}
      </section>
      <section className="fr-daybook" aria-labelledby="daybook-title"><div className="fr-section-heading"><div><h2 id="daybook-title">{dateLabel(selected,{day:"numeric",month:"long"})}<span className="fr-heading-aside">{dateLabel(selected,{weekday:"long"})}</span></h2></div>
        <div className="fr-toolbar"><IconButton label="Предыдущая неделя" onClick={()=>setSelected(shiftDay(selected,-7))}><Icon name="back" size={16}/></IconButton><button type="button" className="fr-text-button" onClick={()=>setSelected(today)}>{DEMO_MODE?"Дата демо":"Сегодня"}</button><IconButton label="Следующая неделя" onClick={()=>setSelected(shiftDay(selected,7))}><Icon name="chevron" size={16}/></IconButton></div></div>
        <div className="fr-week-picker" aria-label="Выбор дня недели">{days.map(day=>{const count=tasks.filter(t=>t.state!=="cancelled"&&dates.get(t.id)===day).length;return <button key={day} type="button" aria-pressed={day===selected} className={day===selected?"is-selected":""} onClick={()=>setSelected(day)} aria-label={`${dateLabel(day,{day:"numeric",month:"long"})}, нарядов: ${count}`}><span>{dateLabel(day,{weekday:"short"})}</span><strong>{day.slice(8)}</strong><small className="fr-week-workload"><span className="fr-week-workload-value">{count}</span><span className="fr-week-workload-label">{pluralize(count,"наряд","наряда","нарядов")}</span></small>{day===today&&<i aria-label={DEMO_MODE?"Дата демо":"Сегодня"}/>}</button>})}</div>
        <div className="fr-list-caption"><span>{daily.length?`Нарядов на выбранный день: ${daily.length}`:"Свободный день в сохранённом плане"}</span><span>Время объекта · {timezone}</span></div>
        {daily.length?<><ul className="fr-task-lines">{daily.slice(0,25).map(task=><TaskLine key={task.id} task={task}/>)}</ul>{daily.length>25&&<p className="text-xs text-muted">Показаны первые 25 работ. Остальные доступны в заданиях дня.</p>}</>:<div className="fr-empty-inline"><Icon name="calendar" size={24}/><h3>На этот день работ нет</h3><p>Выберите другой день или проверьте задания без исполнителя.</p>{canTasks&&<Link to="/tasks?status=unassigned">Посмотреть неназначенные наряды →</Link>}</div>}
        <div className="fr-section-footer"><span>Плановое начало; без него — обязательная дата. Это разные сроки.</span>{canTasks&&<Link to={`/tasks?date=${selected}`}>Наряды дня →</Link>}</div>
      </section>
    </div><aside className="fr-decision-rail" aria-label="Панель решений">
      <section className="fr-rail-section"><h2>{director?"Принятые работы":"Регламент и качество"}</h2><p>{director?"Показания, фотографии, документы и решения инженера доступны в карточке каждой работы.":"Алгоритм и AI помогают выбрать дату внутри допустимого окна. Нормативная граница не переносится."}</p>{director?<Link className="fr-text-link" to="/tasks?status=accepted">Смотреть результаты →</Link>:<>{canOpenSection(profile?.role,"quality")&&<Link className="fr-text-link" to="/quality">На проверке: {review} →</Link>}{chief&&<p><Link className="fr-text-link" to="/settings/equipment">Открыть регламенты →</Link></p>}</>}</section>
      {canCompare&&(forecasts.status!=="success"||run)&&<section className="fr-rail-section">
        {forecasts.status==="loading"?<p>Загрузка сравнения…</p>:forecasts.status==="error"?<p role="alert">Не удалось загрузить сравнения. Основной план доступен.</p>:run?<><h3>{run.equipmentName}</h3><p>{run.operationTitle}</p><dl className="fr-rail-dates"><div><dt>Регламент</dt><dd>{formatShortDate(run.mandatoryDueDate)}</dd></div><div><dt>Алгоритм</dt><dd>{formatShortDate(run.algorithmic.recommendedDate)}</dd></div><div><dt>AI-прогноз</dt><dd>{run.ai.recommendedDate?formatShortDate(run.ai.recommendedDate):"Нет результата"}</dd></div></dl><p className="fr-rail-explanation">{reason||"Обоснование не передано сервером."}</p>{reason!==rawReason&&<details><summary>Исходное обоснование</summary><p className="break-words text-xs text-muted">{rawReason}</p></details>}<Link className="fr-text-link" to={`/comparisons/${run.runId}`}>Разобрать решение <span>↗</span></Link></>:null}
      </section>}
      <section className="fr-rail-section fr-site-note"><h3>{profile?.siteName}</h3><p>{timezone}</p>{DEMO_MODE&&<p className="fr-demo-note">DEMO · снимок на 30.10.2026. Демонстрационные записи не обновляют сервер.</p>}</section>
    </aside></div>
    <details className="fr-overview-report"><summary>Показатели доступных объектов и месячный экспорт</summary><PerformanceOverview/></details>
  </div>;
}
