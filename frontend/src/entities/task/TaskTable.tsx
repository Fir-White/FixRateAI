import { Link } from "react-router-dom";
import type { MaintenanceTask } from "@/shared/types/domain";
import { formatDateTime } from "@/shared/lib/format";
import {
  OriginBadge,
  OverdueBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";
import { Table, Td, Th, Tr } from "@/shared/ui/Table";

export function TaskTable({
  items,
  detailBasePath = "/tasks",
}: {
  items: MaintenanceTask[];
  detailBasePath?: string;
}) {
  return (
    <Table label="Очередь заданий" minWidth={860}>
      <thead>
        <tr>
          <Th>Задание</Th>
          <Th>Статус</Th>
          <Th>Срок</Th>
          <Th>Бригада</Th>
          <Th>Происхождение</Th>
          <Th className="text-right">
            <span className="sr-only">Действия</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {items.map((task) => (
          <Tr key={task.id} highlighted={task.isOverdue}>
            <Td>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-ink">{task.title}</p>
                {task.isOverdue ? <OverdueBadge /> : null}
              </div>
              <p className="mt-1 text-xs text-muted">
                {task.code} · {task.equipmentName} · ТО {task.operationCode}
              </p>
            </Td>
            <Td>
              <TaskStateBadge state={task.state} />
            </Td>
            <Td className="whitespace-nowrap">
              {formatDateTime(task.scheduledEnd)}
            </Td>
            <Td>
              {task.assignees.length ? (
                <div>
                  {task.assignees.map((assignee) => (
                    <p key={assignee.executorId}>{assignee.name}</p>
                  ))}
                </div>
              ) : (
                <span className="text-muted">Не назначена</span>
              )}
            </Td>
            <Td>
              <OriginBadge origin={task.dataOrigin} />
            </Td>
            <Td className="text-right">
              <Link
                to={`${detailBasePath}/${task.id}`}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent transition-colors hover:bg-accent/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Открыть
                <Icon name="chevron" size={15} />
              </Link>
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}
