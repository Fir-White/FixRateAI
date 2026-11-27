import { todayAt } from '@/shared/lib/format';
import { dateLabel, DEMO_DATE } from '@/shared/lib/operations';
import { ROLE_LABELS } from '@/shared/lib/roles';
import { useSession } from '@/shared/session/SessionContext';
import { DEMO_MODE } from '@/shared/api/request';
import { Link } from 'react-router-dom';
import { TaskLine } from '@/entities/task/TaskLine';
import type { MaintenanceTask } from '@/shared/types/domain';
import { Icon } from '@/shared/ui/Icon';
import './workday.css';

type Signal = {label: string; value: number; to?: string; tone?: 'danger' | 'warning'};

export function WorkdayHeading({title, description, label, signals}: {
  title: string; description?: string; label: string; signals: Signal[];
}) {
  const { profile } = useSession();
  return <header className="e3-workday-heading">
    <h1>{title}</h1>
    <div className="e3-workday-summary">
      {description && <p>{description}</p>}
      {signals.length > 0 && <div className="e3-workday-signals" role="group" aria-label={label}>
        {signals.map(({label: text, value, to, tone}) => {
          const content = <><strong>{value}</strong><span>{text}</span>{to && <Icon name="chevron" size={12}/>}</>;
          return to ? <Link key={text} to={to} data-tone={tone}>{content}</Link> : <p key={text} data-tone={tone}>{content}</p>;
        })}
      </div>}
    </div>
    {profile && <div className="e3-workday-context">
      <span className="e3-context-date">{dateLabel(DEMO_MODE ? DEMO_DATE : todayAt(profile.timezone), {day: 'numeric', month: 'long', year: 'numeric', weekday: 'long'})}</span>
      <span className="e3-context-role">{ROLE_LABELS[profile.role]}</span>
    </div>}
  </header>;
}

export function WorkdayUpcoming({tasks, link, linkText}: {tasks: MaintenanceTask[]; link?: string; linkText?: string}) {
  return <section className="e3-workday-upcoming">
    <header><h2>Ближайшие задания</h2>{link && <Link to={link}>{linkText}<Icon name="chevron" size={13}/></Link>}</header>
    {tasks.length ? <ul>{tasks.slice(0,3).map(task => <TaskLine key={task.id} task={task}/>)}</ul> : <p>В графике пока нет ближайших заданий.</p>}
  </section>;
}
