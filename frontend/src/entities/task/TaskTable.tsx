import { Link } from "react-router-dom";
import type { MaintenanceTask } from "@/shared/types/domain";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { formatShortDate } from "@/shared/lib/format";
import { OriginBadge, OverdueBadge, TaskStateBadge } from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";
import { Table, Td, Th, Tr } from "@/shared/ui/Table";
import { isTaskOverdue } from "@/shared/lib/operations";

export function TaskTable({items,detailBasePath="/tasks"}:{items:MaintenanceTask[];detailBasePath?:string}) {
  const formatDateTime=useSiteDateTime();
  return <Table label="Очередь заданий" minWidth={0} className="fr-task-table"><thead><tr><Th>Наряд / оборудование</Th><Th>Статус</Th><Th>Обязательный срок</Th><Th>Исполнители</Th><Th><span className="sr-only">Действия</span></Th></tr></thead><tbody>{items.map(task=><Tr key={task.id} highlighted={isTaskOverdue(task)}>
    <Td className="fr-table-title"><div className="fr-table-reference"><span className="fr-mono">{task.code}</span><OriginBadge origin={task.dataOrigin}/></div><Link className="fr-table-task-link" to={`${detailBasePath}/${task.id}`}>{task.title}</Link><p>{task.equipmentName}</p></Td>
    <Td data-label="Статус"><TaskStateBadge state={task.state}/>{isTaskOverdue(task)&&<span className="fr-overdue-marker"><OverdueBadge/></span>}</Td>
    <Td data-label="Обязательный срок"><strong className={isTaskOverdue(task)?"fr-danger":"fr-table-date"}>{formatShortDate(task.mandatoryDueDate)}</strong><span className="fr-table-subline">Плановое окончание: {formatDateTime(task.scheduledEnd)}</span></Td>
    <Td data-label="Исполнители">{task.assignees.length?<div className="fr-assignee-cell"><span className="fr-avatar-small">{task.assignees[0].name.slice(0,1)}</span><div>{task.assignees.map(a=><p key={a.executorId}>{a.name}</p>)}</div></div>:<span className="fr-unassigned">Не назначены</span>}</Td>
    <Td className="fr-table-action"><Link to={`${detailBasePath}/${task.id}`} aria-label={`Открыть ${task.code}`} className="fr-row-arrow"><span className="fr-mobile-only">Открыть наряд</span><Icon name="chevron" size={17}/></Link></Td>
  </Tr>)}</tbody></Table>;
}
