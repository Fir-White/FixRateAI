import { Link } from 'react-router-dom';
import { dateTimeFormatter } from '@/shared/lib/dateTimeFormatter';
import { dayAt, isOpenTask, isTaskOverdue } from '@/shared/lib/operations';
import { taskPathForRole } from '@/shared/lib/roles';
import type { ApiQuery } from '@/shared/lib/useApiQuery';
import type { MaintenanceTask } from '@/shared/types/domain';
import { Icon } from '@/shared/ui/Icon';
import { TASK_LABELS } from '@/shared/ui/StatusBadge';

const LIMIT = 3;

export function ChiefWorkdayTimeline({ query, today, timezone, canCalendar, onRetry }: {
  query: ApiQuery<MaintenanceTask[]>;
  today: string;
  timezone: string;
  canCalendar: boolean;
  onRetry: () => void;
}) {
  const upcoming = (query.data ?? []).flatMap(task => {
    const start = task.scheduledStart;
    if (!start || !isOpenTask(task)) return [];
    const timestamp = Date.parse(start);
    if (!Number.isFinite(timestamp)) return [];
    const day = dayAt(start, timezone);
    return day >= today ? [{ task, start, timestamp, day }] : [];
  }).sort((a, b) => a.timestamp - b.timestamp || a.task.id.localeCompare(b.task.id)).slice(0, LIMIT);
  const timeLabel = dateTimeFormatter('ru-RU', { timeZone: timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const dateLabel = dateTimeFormatter('ru-RU', { timeZone: timezone, day: 'numeric', month: 'long' });

  return <section className="e3-workday-upcoming e3-workday-timeline" aria-labelledby="chief-upcoming-heading">
    <header>
      <h2 id="chief-upcoming-heading">Ближайшие задания</h2>
      {canCalendar && <Link to={`/calendar?date=${upcoming[0]?.day ?? today}`}>Открыть график<Icon name="chevron" size={14}/></Link>}
    </header>
    {query.status === 'loading' && <p className="e3-timeline-message" role="status" data-workspace-loading="true">Загружаем график заданий…</p>}
    {query.status === 'error' && <div className="e3-timeline-message">
      <p role="alert">Не удалось загрузить график. {query.error}</p>
      <button type="button" onClick={onRetry}>Повторить загрузку</button>
    </div>}
    {query.status === 'success' && !upcoming.length &&
      <p className="e3-timeline-message">На сегодня и ближайшие дни нет заданий с запланированным началом.</p>}
    {upcoming.length > 0 && <ol className="e3-timeline-track" role="list">
      {upcoming.map(({ task, start, timestamp, day }) => {
        const overdue = isTaskOverdue(task);
        const assignees = task.assignees.map(person => person.name).join(', ');
        const path = taskPathForRole('chief_engineer', task.id);
        return <li key={task.id} className="e3-timeline-stop" data-state={task.state}>
          <span className="e3-timeline-marker" aria-hidden="true"/>
          <time dateTime={start} className="e3-timeline-time">
            <strong>{timeLabel.format(timestamp)}</strong>
            <span>{day === today ? 'Сегодня' : dateLabel.format(timestamp)}</span>
          </time>
          <h3>{path ? <Link to={path}>{task.title}<Icon name="chevron" size={14}/></Link> : task.title}</h3>
          <div className="e3-timeline-status">
            <span className="e3-timeline-lifecycle">{TASK_LABELS[task.state] ?? 'Статус неизвестен'}</span>
            {overdue && <span className="e3-timeline-overdue">Просрочено</span>}
            {!assignees && <span className="e3-timeline-unassigned">Без исполнителя</span>}
          </div>
          <p className="e3-timeline-details"><span>{task.equipmentName || 'Оборудование не указано'}</span>{assignees && <span>{assignees}</span>}</p>
        </li>;
      })}
    </ol>}
  </section>;
}
