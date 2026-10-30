import { Link } from "react-router-dom";
import type { MaintenanceTask } from "@/shared/types/domain";
import { formatDateTime } from "@/shared/lib/format";
import {
  OriginBadge,
  OverdueBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";
import { Icon } from "@/shared/ui/Icon";

export function TaskTable({
  items,
  detailBasePath = "/tasks",
}: {
  items: MaintenanceTask[];
  detailBasePath?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] border-collapse text-left">
        <thead>
          <tr className="border-b border-slate-100 text-xs font-bold tracking-wide text-slate-500 uppercase">
            <th className="px-5 py-3 sm:px-6">Задание</th>
            <th className="px-4 py-3">Статус</th>
            <th className="px-4 py-3">Срок</th>
            <th className="px-4 py-3">Бригада</th>
            <th className="px-4 py-3">Происхождение</th>
            <th className="px-5 py-3 sm:px-6" />
          </tr>
        </thead>
        <tbody>
          {items.map((task) => (
            <tr
              key={task.id}
              className={`group border-b border-slate-100 last:border-0 hover:bg-slate-50/70 ${
                task.isOverdue ? "bg-rose-50/30" : ""
              }`}
            >
              <td className="px-5 py-4 sm:px-6">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-900">{task.title}</p>
                  {task.isOverdue ? <OverdueBadge /> : null}
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {task.code} · {task.equipmentName} · ТО {task.operationCode}
                </p>
              </td>
              <td className="px-4 py-4">
                <TaskStateBadge state={task.state} />
              </td>
              <td className="px-4 py-4 text-sm text-slate-700">
                {formatDateTime(task.scheduledEnd)}
              </td>
              <td className="px-4 py-4">
                {task.assignees.length ? (
                  <div className="text-sm text-slate-700">
                    {task.assignees.map((assignee) => (
                      <p key={assignee.executorId}>{assignee.name}</p>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm text-slate-400">Не назначена</span>
                )}
              </td>
              <td className="px-4 py-4">
                <OriginBadge origin={task.dataOrigin} />
              </td>
              <td className="px-5 py-4 text-right sm:px-6">
                <Link
                  to={`${detailBasePath}/${task.id}`}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
                >
                  Открыть
                  <Icon name="chevron" size={16} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
