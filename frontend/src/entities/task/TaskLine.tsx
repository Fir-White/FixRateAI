import { Link } from "react-router-dom";
import type { MaintenanceTask } from "@/shared/types/domain";
import { useSession } from "@/shared/session/SessionContext";
import { taskPathForRole } from "@/shared/lib/roles";
import { formatShortDate } from "@/shared/lib/format";
import { TaskStateBadge } from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";
import { isTaskOverdue } from "@/shared/lib/operations";

export function TaskLine({task, compact=false}: {task:MaintenanceTask; compact?:boolean}) {
  const {profile}=useSession();
  const path=taskPathForRole(profile?.role,task.id);
  const time=task.scheduledStart ? new Intl.DateTimeFormat("ru-RU",{timeZone:profile?.timezone??"Asia/Yekaterinburg",hour:"2-digit",minute:"2-digit"}).format(new Date(task.scheduledStart)):"—";
  return <li className={`fr-task-line ${compact?"is-compact":""} ${isTaskOverdue(task)?"is-overdue":""}`}>
    {!compact && <div className="fr-task-time"><strong>{time}</strong><span>{task.scheduledStart?"по плану":"нет времени"}</span></div>}
    <div className="fr-task-line-body"><span className="fr-mono fr-reference">{task.code}</span><h3>{path?<Link to={path}>{task.title}</Link>:task.title}</h3><p>{task.equipmentName}</p>
      {!compact && <span className="fr-task-assignee">{task.assignees.map(a=>a.name).join(", ")||"Исполнитель не назначен"}</span>}
    </div>
    <div className="fr-task-line-status"><TaskStateBadge state={task.state}/><span className={isTaskOverdue(task)?"fr-danger":""}>{isTaskOverdue(task)?"Просрочено · ":"Срок · "}{formatShortDate(task.mandatoryDueDate)}</span></div>
    {!compact && path && <Link className="fr-row-arrow" to={path} aria-label={`Открыть ${task.code}`}><Icon name="chevron" size={17}/></Link>}
  </li>;
}
