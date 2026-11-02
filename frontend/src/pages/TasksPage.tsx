import { useMemo } from "react";
import { useWorkspaceState } from "@/shared/lib/workspaceState";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { FilterChip } from "@/shared/ui/FilterChip";
import { TaskTable } from "@/entities/task/TaskTable";
import type { MaintenanceTask, TaskState } from "@/shared/types/domain";
import { useSession } from "@/shared/session/SessionContext";
import { canOpenSection } from "@/shared/lib/roles";

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
  const { profile } = useSession();
  const query = useApiQuery(() => maintenanceApi.listTasks(), []);
  const [filter, setFilter] = useWorkspaceState<TaskFilter>("tasks.filter", "all", (value): value is TaskFilter => FILTERS.some(item => item.value === value));

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
            {canOpenSection(profile?.role, "quality") && <Link to="/quality" className={buttonClassName("primary")}>
              На приёмку
            </Link>}
          </>
        }
      />

      <Card className="workspace-task-panel">
        <div className="workspace-task-filters">
        <div className="flex gap-2 overflow-x-auto" data-scroll-key="task-filters">
          {FILTERS.map((item) => (
            <FilterChip
              key={item.value}
              active={filter === item.value}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
            </FilterChip>
          ))}
        </div>
        </div>

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
        <div className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-5 py-3 sm:px-6">
            <p className="text-xs font-semibold text-muted">
              Заданий: {tasks.length}
            </p>
            <p className="text-xs text-muted/60">
              Просрочка — отдельный признак
            </p>
          </div>
          <TaskTable items={tasks} />
        </div>
      ) : null}
      </Card>
    </div>
  );
}
