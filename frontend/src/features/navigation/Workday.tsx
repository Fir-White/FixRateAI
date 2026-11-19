import { Link } from 'react-router-dom';
import { TaskLine } from '@/entities/task/TaskLine';
import type { MaintenanceTask } from '@/shared/types/domain';
import { Icon } from '@/shared/ui/Icon';
import './workday.css';

type Signal = {label: string; value: number; to?: string; tone?: 'danger' | 'warning'};

export function WorkdayHeading({title, description, label, signals}: {
  title: string; description: string; label: string; signals: Signal[];
}) {
  return <header className="e3-workday-heading">
    <div><h1>{title}</h1><p>{description}</p></div>
    {signals.length > 0 && <section className="e3-workday-signals" aria-label={label}>
      <h2>{label}</h2>
      {signals.map(({label: text, value, to, tone}) => {
        const content = <><strong data-tone={tone}>{value}</strong><span>{text}</span>{to && <Icon name="chevron" size={13}/>}</>;
        return to ? <Link key={text} to={to}>{content}</Link> : <p key={text}>{content}</p>;
      })}
    </section>}
  </header>;
}

export function WorkdayUpcoming({tasks, link, linkText}: {tasks: MaintenanceTask[]; link?: string; linkText?: string}) {
  return <section className="e3-workday-upcoming">
    <header><h2>Ближайшие задания</h2>{link && <Link to={link}>{linkText}<Icon name="chevron" size={13}/></Link>}</header>
    {tasks.length ? <ul>{tasks.slice(0,3).map(task => <TaskLine key={task.id} task={task}/>)}</ul> : <p>В графике пока нет ближайших заданий.</p>}
  </section>;
}
