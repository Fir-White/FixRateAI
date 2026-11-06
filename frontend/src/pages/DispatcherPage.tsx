import { PerformanceOverview } from "@/features/analyst/AnalystPanels";
import { useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { todayAt, formatShortDate, pluralize } from "@/shared/lib/format";
import { canOpenSection } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName, IconButton } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { TaskLine } from "@/entities/task/TaskLine";
import { DEMO_DATE, dateLabel, isOpenTask, isTaskOverdue, isUnassigned, matchesTaskFilter, shiftDay, taskPriority, taskWorkDate, weekFor } from "@/shared/lib/operations";
import "./management-redesign.css";

export function DispatcherPage() {
  const {profile}=useSession();
  const timezone=profile?.timezone??"Asia/Yekaterinburg";
  const today=DEMO_MODE?DEMO_DATE:todayAt(timezone);
  const [selected,setSelected]=useState(today);
  const canTasks=canOpenSection(profile?.role,"tasks"), canCalendar=canOpenSection(profile?.role,"calendar"), canCompare=canOpenSection(profile?.role,"comparisons");
  const query=useApiQuery(()=>maintenanceApi.listTasks(),[]);
  const forecasts=useApiQuery(()=>canCompare?maintenanceApi.listComparisons():Promise.resolve([]),[canCompare]);
  if(query.status==="loading")return <LoadingState label="Загрузка оперативного центра"/>;
  if(query.status==="error")return <ErrorState description={query.error}/>;
  const tasks=query.data, open=tasks.filter(isOpenTask);
  const days=weekFor(selected);
  const daily=tasks.filter(t=>t.state!=="cancelled" && taskWorkDate(t,timezone)===selected).sort((a,b)=>(a.scheduledStart??"z").localeCompare(b.scheduledStart??"z")||taskPriority(a)-taskPriority(b));
  const attention=tasks.filter(t=>matchesTaskFilter(t,"attention")).sort((a,b)=>taskPriority(a)-taskPriority(b));
  const overdue=tasks.filter(isTaskOverdue).length, unassigned=tasks.filter(isUnassigned).length, review=tasks.filter(t=>t.state==="submitted").length;
  const run=forecasts.status==="success"?[...forecasts.data].sort((a,b)=>b.createdAt.localeCompare(a.createdAt))[0]:null;
  const rawReason=run?.decision.reasons[0];
  const reason=rawReason?.includes("INSUFFICIENT_HISTORY")?"Для AI-прогноза недостаточно принятой истории. Используется подтверждённый регламент.":rawReason?.startsWith("AI_UNAVAILABLE")?"AI-прогноз сейчас недоступен. Обязательный срок сохраняется.":rawReason?.startsWith("AI_")?"Результат требует проверки. Исходное обоснование доступно ниже.":rawReason;
  const director=profile?.role==="director", chief=profile?.role==="chief_engineer";
  const signals=[{value:overdue,label:"Просрочено",filter:"overdue",tone:"danger"},{value:review,label:"На проверке",filter:"submitted",tone:"accent"},director?{value:tasks.filter(t=>t.state==="accepted").length,label:"Принято",filter:"accepted",tone:"accent"}:{value:unassigned,label:"Без исполнителя",filter:"unassigned",tone:"warning"}];
  return <div className="fr-overview fr-management-v2">
    <header className="fr-overview-heading"><div><p className="fr-eyebrow">{chief?"Технический контроль":director?"Руководитель / обзор объекта":"Эксплуатация / обзор объекта"}</p><h1 aria-label="Панель диспетчера">{director?"Обзор объекта":chief?"Технический обзор":"Оперативный центр"}</h1><p>{profile?.siteName} · {director?"Просмотр отклонений и результатов работ.":chief?"Обязательства, регламенты и контроль качества.":"Работы, обязательные сроки и решения."}</p></div>
      {canCalendar && <Link to={`/calendar?date=${selected}`} className={buttonClassName("primary")}><Icon name="calendar" size={17}/>Открыть график</Link>}
    </header>
    <div className="fr-signal-strip"><div className="fr-signal-total"><span className="fr-live-dot"/><strong>{open.length}</strong><span>незавершённых нарядов</span></div>
      <div className="fr-signals">{signals.map(s=>canTasks?<Link key={s.filter} to={`/tasks?status=${s.filter}`} className={`fr-signal ${s.value?`tone-${s.tone}`:""}`}><span>{s.label}</span><strong>{s.value}</strong><span aria-hidden="true">↗</span></Link>:<span key={s.filter} className={`fr-signal ${s.value?`tone-${s.tone}`:""}`}><span>{s.label}</span><strong>{s.value}</strong></span>)}</div>
    </div>
    <p className="fr-scope-note">Текущее состояние доступных заданий. Счётчики пересекаются и не суммируются.</p>
    <div className="fr-overview-grid"><div className="fr-overview-work">
      <section className="fr-attention" aria-labelledby="attention-title"><div className="fr-section-heading"><div><p className="fr-eyebrow">{chief?"Технические отклонения":director?"Исключения и обязательства":"Очередь решений"}</p><h2 id="attention-title">Требуют внимания <span className="fr-count">{attention.length}</span></h2></div>{canTasks&&<Link className="fr-text-link" to="/tasks?status=attention">Вся очередь →</Link>}</div>
        {attention.length?<ul className="fr-task-lines">{attention.slice(0,4).map(task=><TaskLine key={task.id} task={task} compact/>)}</ul>:<div className="fr-empty-inline compact"><Icon name="check"/><p>Нет просроченных, неназначенных нарядов и отчётов, ожидающих решения.</p></div>}
        {attention.length>4&&<p className="text-xs text-muted mt-3">Показаны 4 из {attention.length}. Остальные — в полной очереди.</p>}
      </section>
      <section className="fr-daybook" aria-labelledby="daybook-title"><div className="fr-section-heading"><div><p className="fr-eyebrow">План работ</p><h2 id="daybook-title">{dateLabel(selected,{day:"numeric",month:"long"})}<span className="fr-heading-aside">{dateLabel(selected,{weekday:"long"})}</span></h2></div>
        <div className="fr-toolbar"><IconButton label="Предыдущая неделя" onClick={()=>setSelected(shiftDay(selected,-7))}><Icon name="back" size={16}/></IconButton><button type="button" className="fr-text-button" onClick={()=>setSelected(today)}>{DEMO_MODE?"Дата демо":"Сегодня"}</button><IconButton label="Следующая неделя" onClick={()=>setSelected(shiftDay(selected,7))}><Icon name="chevron" size={16}/></IconButton></div></div>
        <div className="fr-week-picker" aria-label="Выбор дня недели">{days.map(day=>{const count=tasks.filter(t=>t.state!=="cancelled"&&taskWorkDate(t,timezone)===day).length;return <button key={day} type="button" aria-pressed={day===selected} className={day===selected?"is-selected":""} onClick={()=>setSelected(day)} aria-label={`${dateLabel(day,{day:"numeric",month:"long"})}, нарядов: ${count}`}><span>{dateLabel(day,{weekday:"short"})}</span><strong>{day.slice(8)}</strong><small>{count?`${count} ${pluralize(count,"наряд","наряда","нарядов")}`:"Нет работ"}</small>{day===today&&<i aria-label={DEMO_MODE?"Дата демо":"Сегодня"}/>}</button>})}</div>
        <div className="fr-list-caption"><span>{daily.length?`Нарядов на выбранный день: ${daily.length}`:"Свободный день в сохранённом плане"}</span><span>Время объекта · {timezone}</span></div>
        {daily.length?<ul className="fr-task-lines">{daily.map(task=><TaskLine key={task.id} task={task}/>)}</ul>:<div className="fr-empty-inline"><Icon name="calendar" size={24}/><h3>На этот день работ нет</h3><p>Это не отменяет регламент. Проверьте другие даты или задания без планового времени.</p>{canTasks&&<Link to="/tasks?status=unassigned">Посмотреть неназначенные наряды →</Link>}</div>}
        <div className="fr-section-footer"><span>Плановое начало; без него — обязательная дата. Это разные сроки.</span>{canTasks&&<Link to={`/tasks?date=${selected}`}>Наряды дня →</Link>}</div>
      </section>
    </div><aside className="fr-decision-rail" aria-label="Панель решений">
      <section className="fr-rail-section"><p className="fr-eyebrow">{director?"Результаты работ":"Обязательные сроки"}</p><h2>{director?"Принятые работы":"Регламент и качество"}</h2><p>{director?"Показания, фотографии, документы и решения инженера доступны в карточке каждой работы.":"Алгоритм и AI помогают выбрать дату внутри допустимого окна. Нормативная граница не переносится."}</p>{director?<Link className="fr-text-link" to="/tasks?status=accepted">Смотреть результаты →</Link>:<>{canOpenSection(profile?.role,"quality")&&<Link className="fr-text-link" to="/quality">Очередь проверки →</Link>}{chief&&<p><Link className="fr-text-link" to="/settings/equipment">Открыть регламенты →</Link></p>}</>}</section>
      {canCompare&&<section className="fr-rail-section"><div className="fr-rail-label"><span className="fr-eyebrow">Последнее сравнение</span><span className="fr-ai-label">AI / ALG</span></div>
        {forecasts.status==="loading"?<p>Загрузка сравнения…</p>:forecasts.status==="error"?<p role="alert">Не удалось загрузить сравнения. Основной план доступен.</p>:run?<><h3>{run.equipmentName}</h3><p>{run.operationTitle}</p><dl className="fr-rail-dates"><div><dt>Регламент</dt><dd>{formatShortDate(run.mandatoryDueDate)}</dd></div><div><dt>Алгоритм</dt><dd>{formatShortDate(run.algorithmic.recommendedDate)}</dd></div><div><dt>AI-прогноз</dt><dd>{run.ai.recommendedDate?formatShortDate(run.ai.recommendedDate):"Нет результата"}</dd></div></dl><p className="fr-rail-explanation">{reason||"Обоснование не передано сервером."}</p>{reason!==rawReason&&<details><summary>Исходное обоснование</summary><p className="break-words text-xs text-muted">{rawReason}</p></details>}<Link className="fr-text-link" to={`/comparisons/${run.runId}`}>Разобрать решение <span>↗</span></Link></>:<><h3>Пока нет результатов</h3><p>Сохранённых сравнений пока нет. Доступные результаты появятся в разделе прогнозов.</p><Link className="fr-text-link" to="/comparisons">Перейти к прогнозам →</Link></>}
      </section>}
      <section className="fr-rail-section fr-site-note"><p className="fr-eyebrow">Рабочий объект</p><h3>{profile?.siteName}</h3><p>{timezone}</p>{DEMO_MODE&&<p className="fr-demo-note">DEMO · снимок на 30.10.2026. Демонстрационные записи не обновляют сервер.</p>}</section>
    </aside></div>
    <details className="fr-overview-report"><summary>Показатели доступных объектов и месячный экспорт</summary><PerformanceOverview/></details>
  </div>;
}
