import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { canOpenSection, taskPathForRole } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { OverdueBadge, TaskStateBadge } from "@/shared/ui/StatusBadge";
import type { MaintenanceTask } from "@/shared/types/domain";

function weekDates(today: string) {
  const date = new Date(`${today}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
  return Array.from({ length: 7 }, (_, index) => {
    const current = new Date(date);
    current.setUTCDate(date.getUTCDate() + index);
    return {
      key: current.toISOString().slice(0, 10),
      day: new Intl.DateTimeFormat("ru-RU", { day: "2-digit", timeZone: "UTC" }).format(current),
      weekday: new Intl.DateTimeFormat("ru-RU", { weekday: "short", timeZone: "UTC" }).format(current),
    };
  });
}

export function DispatcherPage() {
  const { profile } = useSession();
  const timezone = profile?.timezone ?? "Asia/Yekaterinburg";
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const query = useApiQuery(() => Promise.all([maintenanceApi.listTasks(), maintenanceApi.listComparisons()]), []);

  if (query.status === "loading") return <LoadingState label="Загрузка панели диспетчера" />;
  if (query.status === "error") return <ErrorState description={query.error} />;

  const [tasks, comparisons] = query.data;
  const overdue = tasks.filter(task => task.isOverdue && task.state !== "accepted" && task.state !== "cancelled");
  const unassigned = tasks.filter(task => task.state === "draft" && task.assignees.length === 0);
  const onReview = tasks.filter(task => task.state === "submitted");
  const todayTasks = tasks.filter(task => task.mandatoryDueDate === today && task.state !== "accepted" && task.state !== "cancelled");
  const attention = tasks.filter(task => overdue.includes(task) || onReview.includes(task));
  const canTasks = canOpenSection(profile?.role, "tasks");
  const canCalendar = canOpenSection(profile?.role, "calendar");
  const canComparisons = canOpenSection(profile?.role, "comparisons");
  const days = weekDates(today);
  const weekKeys = new Set(days.map(day => day.key));
  const weekTasks = tasks.filter(task => task.mandatoryDueDate && weekKeys.has(task.mandatoryDueDate) && task.state !== "cancelled");
  const rows = new Map<string, MaintenanceTask[]>();
  weekTasks.forEach(task => {
    const key = `${task.operationCode}\u0000${task.title}`;
    rows.set(key, [...(rows.get(key) ?? []), task]);
  });
  const latestRun = comparisons[0];
  const dateLabel = new Intl.DateTimeFormat("ru-RU", { timeZone: timezone, weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
  const monthLabel = new Intl.DateTimeFormat("ru-RU", { timeZone: timezone, month: "long", year: "numeric" }).format(new Date());

  return (
    <div className="ops-overview">
      <div className="ops-overview-main">
        <section className="ops-intro" aria-labelledby="dispatcher-title">
          <p className="ops-kicker">Оперативная смена / {dateLabel}</p>
          <div className="ops-intro-heading">
            <div>
              <h1 id="dispatcher-title" aria-label="Панель диспетчера">Обслуживание.<br /><span>В поле зрения.</span></h1>
              <p>Плановые работы, нормативные сроки и решения — в одном месте.</p>
            </div>
            {canTasks && <Link className="ops-outline-action" to="/tasks">Очередь заданий <span aria-hidden="true">→</span></Link>}
          </div>
          <div className="ops-statline" aria-label="Сводка заданий">
            <Summary value={todayTasks.length} label={`на ${formatDate(today)}`} />
            <Summary value={unassigned.length} label="без исполнителя" tone="warning" />
            <Summary value={onReview.length} label="на проверке" tone="accent" />
            <Summary value={overdue.length} label="просрочено" tone={overdue.length ? "danger" : undefined} />
          </div>
        </section>

        <section className="ops-section" aria-labelledby="week-title">
          <div className="ops-section-heading">
            <div><h2 id="week-title">График на неделю</h2><p>Обязательные сроки заданий · {profile?.siteName}</p></div>
            {canCalendar && <Link className="ops-outline-action" to="/calendar">{monthLabel} <span aria-hidden="true">→</span></Link>}
          </div>
          <div className="ops-week-scroll" role="region" aria-label="График заданий на неделю" tabIndex={0} data-scroll-key="overview-week">
            <table className="ops-week-table">
              <thead><tr><th scope="col">Работы / даты</th>{days.map(day => <th key={day.key} scope="col" className={day.key === today ? "is-today" : undefined}><span>{day.day}</span><small>{day.weekday}</small></th>)}</tr></thead>
              <tbody>
                {[...rows].slice(0, 6).map(([key, group]) => <tr key={key}>
                  <th scope="row"><span className="ops-operation-code">{group[0].operationCode || "—"}</span><span className="ops-operation-name">{group[0].title}<small>{group[0].maintenanceType || "Обслуживание"}</small></span></th>
                  {days.map(day => {
                    const due = group.filter(task => task.mandatoryDueDate === day.key);
                    const first = due[0];
                    const path = first && (due.length > 1 && canTasks ? "/tasks" : taskPathForRole(profile?.role, first.id));
                    const description = `${formatDate(day.key)}: ${due.length ? `заданий — ${due.length}` : "нет заданий"}`;
                    const markClass = `ops-week-mark ${due.length > 1 ? "is-multiple" : `state-${first?.state}`}`;
                    return <td key={day.key} className={day.key === today ? "is-today" : undefined}>
                      {first ? path ? <Link to={path} className={markClass} aria-label={description} title={description}>{due.length > 1 ? due.length : ""}</Link> : <span className={markClass} aria-label={description} title={description}>{due.length > 1 ? due.length : ""}</span> : <span className="ops-week-empty" aria-label={description}>—</span>}
                    </td>;
                  })}
                </tr>)}
              </tbody>
            </table>
            {!rows.size && <p className="ops-empty">На этой неделе заданий с обязательным сроком нет.</p>}
          </div>
          <p className="ops-week-hint">Проведите по таблице вбок, чтобы увидеть всю неделю.</p>
          <div className="ops-section-note"><p>Показаны {rows.size > 6 ? "первые шесть операций с заданиями" : "сохранённые задания"} по обязательному сроку объекта. Отметка не подтверждает выполнение работы.</p>{canCalendar && <Link to="/calendar">Открыть полный календарь →</Link>}</div>
        </section>

        <section className="ops-section" aria-labelledby="today-title">
          <div className="ops-section-heading"><div><h2 id="today-title">Сегодня в работе</h2><p>Задания с обязательным сроком на {formatDate(today)}</p></div>{canTasks && <Link className="ops-text-link" to="/tasks">Все задания →</Link>}</div>
          <TaskList tasks={todayTasks} empty="На сегодня заданий нет." />
        </section>

        {attention.length > 0 && <section className="ops-section" aria-labelledby="attention-title">
          <div className="ops-section-heading"><div><h2 id="attention-title">Требуют внимания</h2><p>Просроченные задания и отчёты на проверке</p></div></div>
          <TaskList tasks={attention} empty="Просрочек и отчётов на проверке нет." />
        </section>}
      </div>

      <aside className="ops-insights" aria-label="Панель решений">
        <p className="ops-kicker">Панель решений</p>
        <div className="ops-insight-number">{String(unassigned.length).padStart(2, "0")}<span>↗</span></div>
        <h2>{unassigned.length ? "Требуют назначения исполнителя" : "Нет заданий без исполнителя"}</h2>
        <div className="ops-insight-block"><p className="ops-kicker">Назначение</p><p>{unassigned.length ? "В очереди есть задания без назначенной бригады." : "Сейчас нет черновиков без назначенной бригады."}</p>{canTasks && <Link to="/tasks">Перейти к заданиям →</Link>}</div>
        <div className="ops-insight-block"><p className="ops-kicker">AI / прогнозирование</p><h3>{latestRun ? latestRun.equipmentName : "Нет сохранённых сравнений"}</h3><p>{latestRun ? latestRun.operationTitle : "Сравнение будет доступно после запуска прогноза."}</p>{canComparisons && <Link to={latestRun ? `/comparisons/${latestRun.runId}` : "/comparisons"}>Открыть сравнение →</Link>}</div>
        <div className="ops-insight-block"><p className="ops-kicker">Объект</p><h3>{profile?.siteName}</h3><p>Время и обязательные сроки показаны для часового пояса {timezone}.</p></div>
      </aside>
    </div>
  );
}

function Summary({ value, label, tone }: { value: number; label: string; tone?: "warning" | "accent" | "danger" }) {
  return <div className="ops-stat"><strong className={tone ? `is-${tone}` : undefined}>{String(value).padStart(2, "0")}</strong><span>{label}</span></div>;
}

function TaskList({ tasks, empty }: { tasks: MaintenanceTask[]; empty: string }) {
  const { profile } = useSession();
  if (!tasks.length) return <p className="ops-empty ops-task-list">{empty}</p>;
  return <ul className="ops-task-list">{tasks.map(task => {
    const path = taskPathForRole(profile?.role, task.id);
    return <li key={task.id}><div><div className="ops-task-title">{path ? <Link to={path}>{task.title}</Link> : task.title}{task.isOverdue && <OverdueBadge />}</div><p>{task.code} · {task.equipmentName}</p></div><TaskStateBadge state={task.state} /></li>;
  })}</ul>;
}
