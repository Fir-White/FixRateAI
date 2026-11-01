import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { useSession } from "@/shared/session/SessionContext";
import { formatDate } from "@/shared/lib/format";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { PageHeader } from "@/shared/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { StatCard } from "@/widgets/StatCard";
import { Icon } from "@/shared/ui/Icon";
import {
  OriginBadge,
  OverdueBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";
import type { MaintenanceTask, TaskState } from "@/shared/types/domain";

const ACTIVE_STATES: TaskState[] = [
  "assigned",
  "in_progress",
  "rework_required",
];

const STATE_ORDER: Record<TaskState, number> = {
  in_progress: 0,
  rework_required: 1,
  assigned: 2,
  submitted: 3,
  accepted: 4,
  draft: 5,
  cancelled: 6,
};

export function ExecutorPage() {
  const { profile } = useSession();
  const executorId = profile?.userId ?? "";
  const query = useApiQuery(
    () => maintenanceApi.listExecutorTasks(executorId),
    [executorId],
  );

  if (query.status === "loading") {
    return <LoadingState label="Загрузка назначенных заданий" />;
  }

  if (query.status === "error") {
    return <ErrorState description={query.error} />;
  }

  const tasks = [...query.data].sort(
    (left, right) =>
      Number(right.isOverdue) - Number(left.isOverdue) ||
      STATE_ORDER[left.state] - STATE_ORDER[right.state],
  );
  const active = tasks.filter((task) => ACTIVE_STATES.includes(task.state));
  const overdue = tasks.filter(
    (task) => task.isOverdue && task.state !== "accepted",
  );
  const onReview = tasks.filter((task) => task.state === "submitted");

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Исполнитель"
        title="Мои задания"
        description="Назначенные работы на текущую смену. Отправленный отчёт нельзя изменить после сдачи."
      />

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <StatCard compact label="Активные" value={active.length} />
        <StatCard
          compact
          label="Просрочены"
          value={overdue.length}
          tone="danger"
        />
        <StatCard
          compact
          label="На проверке"
          value={onReview.length}
          tone="warning"
        />
      </div>

      {tasks.length === 0 ? (
        <EmptyState
          title="Назначенных заданий нет"
          description="Когда диспетчер назначит работу, она появится в этом списке."
        />
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <ExecutorTaskCard key={task.id} task={task} />
          ))}
        </div>
      )}
    </div>
  );
}

function ExecutorTaskCard({ task }: { task: MaintenanceTask }) {
  const formatDateTime=useSiteDateTime();
  return (
    <article
      className={`rounded-2xl border bg-surface p-4 ${
        task.isOverdue ? "border-rose-400/25" : "border-line"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <TaskStateBadge state={task.state} />
            {task.isOverdue ? <OverdueBadge /> : null}
            <OriginBadge origin={task.dataOrigin} />
          </div>
          <Link
            to={`/executor/tasks/${task.id}`}
            className="mt-3 block text-base font-semibold text-ink hover:text-accent"
          >
            {task.title}
          </Link>
          <p className="mt-1 text-sm text-muted">{task.equipmentName}</p>
        </div>
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10 text-accent">
          <Icon name="tasks" size={20} />
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-white/[0.035] p-3 text-xs">
        <div>
          <p className="font-semibold text-muted">Срок</p>
          <p className="mt-1 font-semibold text-ink">
            {formatDate(task.mandatoryDueDate)}
          </p>
        </div>
        <div>
          <p className="font-semibold text-muted">Интервал</p>
          <p className="mt-1 font-semibold text-ink">
            {formatDateTime(task.scheduledStart)}
          </p>
        </div>
      </div>

      <Link
        to={`/executor/tasks/${task.id}`}
        className={buttonClassName("primary", "sm", "mt-4 w-full")}
      >
        Открыть задание
        <Icon name="chevron" size={16} />
      </Link>
    </article>
  );
}
