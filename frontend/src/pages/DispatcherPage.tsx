import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { StatCard } from "@/widgets/StatCard";
import { Card, CardHeader } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { LoadingState, ErrorState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import {
  OriginBadge,
  OverdueBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";
import type { MaintenanceTask } from "@/shared/types/domain";

export function DispatcherPage() {
  const query = useApiQuery(
    () =>
      Promise.all([
        maintenanceApi.listTasks(),
        maintenanceApi.listComparisons(),
      ]),
    [],
  );

  if (query.status === "loading") {
    return <LoadingState label="Загрузка панели диспетчера" />;
  }

  if (query.status === "error") {
    return <ErrorState description={query.error} />;
  }

  const [tasks, comparisons] = query.data;
  const overdue = tasks.filter(
    (task) => task.isOverdue && task.state !== "accepted" && task.state !== "cancelled",
  );
  const unassigned = tasks.filter(
    (task) => task.state === "draft" && task.assignees.length === 0,
  );
  const onReview = tasks.filter((task) => task.state === "submitted");
  const inProgress = tasks.filter((task) => task.state === "in_progress");
  const todayTasks = tasks.filter(
    (task) => task.mandatoryDueDate === "2026-10-30" && task.state !== "accepted",
  );
  const latestRun = comparisons[0];
  const attention = [...overdue, ...onReview];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Диспетчер"
        title="Панель диспетчера"
        description="Просрочки, нераспределённые работы и задания, ожидающие решения. Обзор не заменяет рабочие разделы."
        actions={
          <>
            <Link to="/tasks" className={buttonClassName("primary")}>
              Очередь заданий
            </Link>
            <Link to="/calendar" className={buttonClassName("secondary")}>
              Календарь ТО
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Просрочено"
          value={overdue.length}
          hint="Незавершённые задания за обязательным сроком"
          tone="danger"
          icon={<Icon name="alert" />}
        />
        <StatCard
          label="Без исполнителя"
          value={unassigned.length}
          hint="Черновики без назначенной бригады"
          tone="warning"
          icon={<Icon name="user" />}
        />
        <StatCard
          label="На проверке"
          value={onReview.length}
          hint="Ожидают решения инженера"
          tone="default"
          icon={<Icon name="quality" />}
        />
        <StatCard
          label="В работе"
          value={inProgress.length}
          hint="Начатые попытки выполнения"
          tone="success"
          icon={<Icon name="clock" />}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Требуют внимания"
              description="Просроченные задания и отчёты на проверке"
              action={
                <Link
                  to="/tasks"
                  className="text-sm font-semibold text-accent hover:text-accent"
                >
                  Все задания
                </Link>
              }
            />
            {attention.length ? (
              <ul className="divide-y divide-line">
                {attention.map((task) => (
                  <li key={task.id} className="px-5 py-4 sm:px-6">
                    <TaskAttentionRow task={task} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-8 text-center text-sm text-muted">
                Просрочек и отчётов на проверке нет.
              </p>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Задания на 30 октября"
              description="Срок задания — локальные сутки объекта Asia/Yekaterinburg"
            />
            {todayTasks.length ? (
              <ul className="divide-y divide-line">
                {todayTasks.map((task) => (
                  <li key={task.id} className="px-5 py-4 sm:px-6">
                    <TaskAttentionRow task={task} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-8 text-center text-sm text-muted">
                На выбранную дату заданий нет.
              </p>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Неполные данные"
              description="Система хранит неопределённость и не подставляет значения"
            />
            <div className="space-y-3 p-5 sm:p-6">
              <Callout tone="warning" title="ТО2: даты требуют уточнения">
                <p className="text-xs leading-5">
                  Для правила 1/квартал не подтверждены basis и anchor. Пять дат
                  годового ТО не выдумываются.
                </p>
                <Link
                  to="/calendar"
                  className="mt-2 inline-flex items-center gap-1 text-xs font-semibold hover:underline"
                >
                  Открыть календарь
                  <Icon name="chevron" size={14} />
                </Link>
              </Callout>
              <Callout tone="neutral" title="Нормо-часы не подтверждены">
                <p className="text-xs leading-5">
                  Исходная норма сохранена без округления. Планировочная
                  длительность пуста до подтверждения заказчиком.
                </p>
              </Callout>
              <Callout tone="violet" title="Набор B: synthetic_demo">
                <p className="text-xs leading-5">
                  Синтетические данные не являются историей заказчика и всегда
                  маркируются в интерфейсе.
                </p>
              </Callout>
            </div>
          </Card>

          {latestRun ? (
            <Card>
              <CardHeader
                title="Последнее сравнение"
                description="Оба метода на одном snapshot"
              />
              <div className="p-5 sm:p-6">
                <div className="flex flex-wrap items-center gap-2">
                  <OriginBadge origin={latestRun.dataOrigin} />
                  <span className="text-xs text-muted">
                    as_of {formatDate(latestRun.asOf)}
                  </span>
                </div>
                <p className="mt-3 font-semibold text-ink">
                  {latestRun.equipmentName}
                </p>
                <p className="mt-1 text-xs text-muted">
                  {latestRun.operationTitle}
                </p>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl bg-sky-400/10 p-3">
                    <p className="text-xs font-semibold text-sky-200">
                      Алгоритм
                    </p>
                    <p className="mt-1 font-semibold text-ink">
                      {formatDate(latestRun.algorithmic.recommendedDate)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-violet-400/10 p-3">
                    <p className="text-xs font-semibold text-violet-200">AI</p>
                    <p className="mt-1 font-semibold text-ink">
                      {formatDate(latestRun.ai.recommendedDate)}
                    </p>
                  </div>
                </div>
                <Link
                  to={`/comparisons/${latestRun.runId}`}
                  className={buttonClassName("secondary", "sm", "mt-4 w-full")}
                >
                  Открыть решение
                </Link>
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function TaskAttentionRow({ task }: { task: MaintenanceTask }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/tasks/${task.id}`}
            className="font-semibold text-ink hover:text-accent"
          >
            {task.title}
          </Link>
          {task.isOverdue ? <OverdueBadge /> : null}
        </div>
        <p className="mt-1 text-xs text-muted">
          {task.code} · {task.equipmentName} · срок {formatDateTime(task.scheduledEnd)}
        </p>
      </div>
      <TaskStateBadge state={task.state} />
    </div>
  );
}
