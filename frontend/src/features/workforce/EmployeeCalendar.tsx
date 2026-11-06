import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { managementApi } from "@/shared/api/management";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { useWorkspaceState } from "@/shared/lib/workspaceState";
import { isDateKey, shiftDay, weekFor } from "@/shared/lib/operations";
import { formatShortDate, pluralize } from "@/shared/lib/format";
import type { MaintenanceTask } from "@/shared/types/domain";
import { Button, IconButton } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";
import { FieldCaption, Input } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { TaskStateBadge } from "@/shared/ui/StatusBadge";
import "./employee-calendar.css";

export interface ShiftInterval { start_at: string; end_at: string; status: string }
export function shiftTasks(row: ShiftInterval, tasks: MaintenanceTask[], userId: string) {
  return tasks.filter(task => task.assignees.some(person => person.executorId === userId) && task.scheduledStart && task.scheduledEnd
    && Date.parse(task.scheduledStart) < Date.parse(row.end_at) && Date.parse(task.scheduledEnd) > Date.parse(row.start_at));
}
function validPeriod(value: unknown): value is { start: string; end: string } {
  if (!value || typeof value !== "object") return false;
  const { start, end } = value as { start: unknown; end: unknown };
  return isDateKey(start) && isDateKey(end) && start <= end && end <= "2100-12-31" && Date.parse(end) - Date.parse(start) <= 366 * 86400000;
}
function duration(row: ShiftInterval) {
  const minutes = Math.round((Date.parse(row.end_at) - Date.parse(row.start_at)) / 60000);
  return `${Math.floor(minutes / 60)} ч${minutes % 60 ? ` ${minutes % 60} мин` : ""}`;
}

export function EmployeeCalendar({ person, today, timezone, personal = false, tasks, tasksLoading = false, tasksError }: {
  person: { user_id: string }; today: string; timezone: string; personal?: boolean;
  tasks?: MaintenanceTask[]; tasksLoading?: boolean; tasksError?: string;
}) {
  const week = weekFor(today);
  const [period, setPeriod] = useWorkspaceState(`employee-calendar${personal ? "-personal" : ""}:${person.user_id}.period`, { start: personal ? week[0] : today, end: personal ? week[6] : today }, validPeriod);
  const [start, setStart] = useState(period.start);
  const [end, setEnd] = useState(period.end);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [customPeriod, setCustomPeriod] = useState(false);
  const query = useApiQuery(() => managementApi.workerCalendar(person.user_id, period.start, period.end), [person.user_id, period.start, period.end, refresh], undefined, personal ? `personal-shifts:${person.user_id}:${period.start}:${period.end}` : undefined);
  const formatter = useMemo(() => ({
    time: new Intl.DateTimeFormat("ru-RU", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
    day: new Intl.DateTimeFormat("ru-RU", { timeZone: timezone, day: "numeric", month: "long" }),
    weekday: new Intl.DateTimeFormat("ru-RU", { timeZone: timezone, weekday: "long" }),
    key: new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }),
  }), [timezone]);
  const dayKey = (value: string) => formatter.key.formatToParts(new Date(value)).filter(part => ["year", "month", "day"].includes(part.type));
  const sameDay = (a: string, b: string) => JSON.stringify(dayKey(a)) === JSON.stringify(dayKey(b));
  const rows = query.status === "success" ? [...query.data.intervals].sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at)) : [];
  const working = rows.filter(row => row.status === "available");
  const exceptions = rows.filter(row => row.status !== "available");
  const assigned = tasks ? [...new Map(working.flatMap(row => shiftTasks(row, tasks, person.user_id)).map(task => [task.id, task])).values()] : undefined;
  const apply = (next: { start: string; end: string }) => {
    if (!validPeriod(next)) { setError("Выберите даты по порядку: диапазон до 366 дней, с 2000 по 2100 год."); return; }
    setError(""); setStart(next.start); setEnd(next.end); setPeriod(next); setRefresh(value => value + 1);
  };
  const move = (offset: number) => { const days = Math.round((Date.parse(period.end) - Date.parse(period.start)) / 86400000) + 1; apply({ start: shiftDay(period.start, offset * days), end: shiftDay(period.end, offset * days) }); };
  const Heading = personal ? "h2" : "h3";
  return <Card className="fr-shift-calendar">
    <header className="fr-shift-header"><div><Heading>{formatShortDate(period.start)} — {formatShortDate(period.end)} <small className="fr-shift-year">{period.start.slice(0,4)}{period.start.slice(0,4)!==period.end.slice(0,4)?`–${period.end.slice(0,4)}`:""}</small></Heading></div><span className="fr-shift-timezone"><Icon name="clock" size={15} />{timezone}</span></header>
    <div className="fr-shift-toolbar"><div className="fr-shift-presets"><IconButton label="Предыдущий период смен" onClick={() => move(-1)} disabled={period.start <= "2000-01-01"}><Icon name="back" size={16}/></IconButton><Button variant="ghost" size="sm" onClick={() => apply({start:today,end:today})}>Сегодня</Button><Button variant="ghost" size="sm" onClick={() => apply({start:week[0],end:week[6]})}>Эта неделя</Button><Button variant="ghost" size="sm" onClick={() => apply({start:shiftDay(week[0],7),end:shiftDay(week[6],7)})}>Следующая неделя</Button><IconButton label="Следующий период смен" onClick={() => move(1)} disabled={period.end >= "2100-12-31"}><Icon name="chevron" size={16}/></IconButton></div>
      <Button variant="secondary" size="sm" className="fr-shift-range-toggle" aria-expanded={customPeriod} onClick={()=>setCustomPeriod(value=>!value)}><Icon name="calendar" size={15}/>Выбрать даты</Button>
      {customPeriod && <form className="fr-shift-range" onSubmit={event => {event.preventDefault();apply({start,end});}}><label><FieldCaption>Показать с</FieldCaption><Input aria-label="Календарь сотрудника: с" type="date" min="2000-01-01" max="2100-12-31" required value={start} onChange={event=>setStart(event.target.value)}/></label><label><FieldCaption>Показать по</FieldCaption><Input aria-label="Календарь сотрудника: по" type="date" min={start || "2000-01-01"} max="2100-12-31" required value={end} onChange={event=>setEnd(event.target.value)}/></label><Button type="submit" variant="secondary" disabled={query.status==="loading"}>Показать смены</Button></form>}
    </div>
    {error && <p className="fr-shift-error" role="alert">{error}</p>}
    {query.status === "loading" && <p className="fr-shift-empty" role="status">Загружаем расписание…</p>}
    {query.status === "error" && <div className="fr-shift-empty"><p role="alert">{query.error}</p><Button variant="secondary" onClick={()=>setRefresh(value=>value+1)}>Повторить загрузку смен</Button></div>}
    {query.status === "success" && <>
      <dl className="fr-shift-metrics"><div><dt>Рабочих интервалов</dt><dd>{working.length}</dd></div><div><dt>Исключений / не работает</dt><dd>{exceptions.length}</dd></div>{personal && <div><dt>Назначенных работ</dt><dd>{assigned ? assigned.length : "—"}</dd></div>}</dl>
      {exceptions.length > 0 && <p className="fr-shift-exception-note">Интервалы «Не работает» могут перекрывать регулярный график. При назначении сервер учитывает исключения отдельно.</p>}
      {tasksError && <p className="fr-shift-error" role="alert">Не удалось загрузить назначения: {tasksError}</p>}
      {tasksLoading && <p className="fr-shift-loading" role="status">Загружаем назначенные работы…</p>}
      {!rows.length ? <div className="fr-shift-empty"><Icon name="calendar" size={28}/><strong>На этот период смен нет</strong><p>Выберите другую неделю или уточните график у руководителя.</p></div> : <ol className="fr-shift-list">{rows.map((row,index)=>{
        const jobs = tasks ? shiftTasks(row,tasks,person.user_id).sort((a,b)=>Date.parse(a.scheduledStart!)-Date.parse(b.scheduledStart!)) : [];
        const begin = new Date(row.start_at), finish = new Date(row.end_at);
        const active = Date.now() >= begin.getTime() && Date.now() < finish.getTime();
        const available = row.status === "available";
        return <li key={`${row.start_at}:${row.end_at}:${row.status}:${index}`} className={`fr-shift-row ${available ? "" : "is-unavailable"}`}>
          <div className="fr-shift-date"><strong>{formatter.day.format(begin)}</strong><span>{formatter.weekday.format(begin)}</span>{active && <small>Сейчас</small>}</div>
          <div className="fr-shift-main"><div className="fr-shift-summary"><div><h3>{formatter.time.format(begin)} <span>—</span> {formatter.time.format(finish)}{!sameDay(row.start_at,row.end_at) && <small>до {formatter.day.format(finish)}</small>}</h3><p><Icon name="clock" size={14}/>{duration(row)}<span>·</span>{available ? "Рабочий интервал" : "Не работает"}</p></div><span className={`fr-shift-status ${available ? "" : "is-unavailable"}`}><Icon name={available?"check":"alert"} size={14}/>{available ? "По графику" : "Не работает"}</span></div>
            {personal && tasks !== undefined && <div className="fr-shift-jobs"><p>{jobs.length ? `${jobs.length} ${pluralize(jobs.length,"назначенная работа","назначенные работы","назначенных работ")}` : "На этот интервал работы не назначены"}</p>{jobs.length > 0 && <ul>{jobs.map(task=><li key={task.id}><Link to={`/executor/tasks/${task.id}`}><span className="fr-shift-job-time">{formatter.time.format(new Date(task.scheduledStart!))}</span><span><strong>{task.title}</strong><small>{task.code} · {task.equipmentName || "Оборудование не указано"}</small></span><TaskStateBadge state={task.state}/><Icon name="chevron" size={15}/></Link></li>)}</ul>}</div>}
          </div>
        </li>;
      })}</ol>}
      {query.data.diagnostics.length > 0 && <div className="fr-shift-diagnostics" role="alert"><strong>Есть ограничения расчёта</strong>{query.data.diagnostics.map((row,index)=><p key={index}>{row.date}: {row.explanation}</p>)}</div>}
    </>}
  </Card>;
}
