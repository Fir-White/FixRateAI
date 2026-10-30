import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { TaskTable } from "@/entities/task/TaskTable";
import type { MaintenanceTask, TaskState } from "@/shared/types/domain";

type TaskFilter = "all" | "attention" | TaskState;

const FILTERS: { value: TaskFilter; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "attention", label: "Требуют внимания" },
  { value: "draft", label: "Черновик" },
  { value: "assigned", label: "Назначено" },
  { value: "in_progress", label: "В работе" },
  { value: "submitted", label: "На проверке" },
  { value: "rework_required", label: "На доработке" },
  { value: "accepted", label: "Принято" },
];

function matchesFilter(task: MaintenanceTask, filter: TaskFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "attention") {
    return task.isOverdue || task.state === "submitted" || task.state === "rework_required";
  }
  return task.state === filter;
}

export function TasksPage() {
  const query = useApiQuery(() => maintenanceApi.listTasks(), []);
  const [filter, setFilter] = useState<TaskFilter>("all");

  const tasks = useMemo(() => {
    if (query.status !== "success") {
      return [];
    }
    return query.data.filter((task) => matchesFilter(task, filter));
  }, [filter, query.data, query.status]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Исполнение"
        title="Очередь заданий"
        description="Задание связывает одно вхождение календаря, одну операцию и одну единицу оборудования. Назначение проверяет бригаду, допуски и интервал."
        actions={
          <>
            <Link to="/calendar" className={buttonClassName("secondary")}>
              Календарь
            </Link>
            <Link to="/quality" className={buttonClassName("primary")}>
              На приёмку
            </Link>
          </>
        }
      />

      <Card className="p-3 sm:p-4">
        <div className="flex gap-2 overflow-x-auto">
          {FILTERS.map((item) => {
            const active = filter === item.value;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => setFilter(item.value)}
                className={`rounded-lg px-3 py-2 text-sm font-semibold whitespace-nowrap transition ${
                  active
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </Card>

      {query.status === "loading" ? <LoadingState /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}
      {query.status === "success" && tasks.length === 0 ? (
        <EmptyState
          title="Заданий по фильтру нет"
          description="Выберите другой статус или проверьте календарь вхождений."
        />
      ) : null}
      {query.status === "success" && tasks.length > 0 ? (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3 sm:px-6">
            <p className="text-xs font-semibold text-slate-500">
              Заданий: {tasks.length}
            </p>
            <p className="text-xs text-slate-400">
              Просрочка — отдельный признак
            </p>
          </div>
          <TaskTable items={tasks} />
        </Card>
      ) : null}
    </div>
  );
}
