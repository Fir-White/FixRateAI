import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { EvidenceGallery } from "@/entities/execution/EvidenceGallery";
import {
  EngineerDecisionBadge,
  OriginBadge,
  OverdueBadge,
  ReviewStatusBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";
import type { ChecklistItem } from "@/shared/types/domain";

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const query = useApiQuery(() => maintenanceApi.getTask(taskId), [taskId]);

  if (query.status === "loading") {
    return <LoadingState label="Загрузка задания" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/tasks" className={buttonClassName("secondary")}>
            Вернуться к заданиям
          </Link>
        }
      />
    );
  }

  const { task, execution, review, decision } = query.data;

  return (
    <div className="space-y-6">
      <Link
        to="/tasks"
        className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
      >
        <Icon name="back" size={18} />
        Очередь заданий
      </Link>

      <PageHeader
        eyebrow={task.code}
        title={task.title}
        description={task.summary}
        actions={
          <>
            {task.state === "submitted" ? (
              <Link
                to={`/quality/${task.id}`}
                className={buttonClassName("primary")}
              >
                Перейти к приёмке
              </Link>
            ) : null}
            {task.state === "draft" ? (
              <Button disabled title="Назначение станет доступно после подключения API">
                Назначить бригаду
              </Button>
            ) : null}
            {task.state === "in_progress" ? (
              <Button variant="secondary" disabled>
                Работа выполняется
              </Button>
            ) : null}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <TaskStateBadge state={task.state} />
        {task.isOverdue ? <OverdueBadge /> : null}
        <OriginBadge origin={task.dataOrigin} />
        <span className="text-xs text-slate-500">Ревизия {task.revision}</span>
      </div>

      {task.isOverdue ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm leading-6 text-rose-900">
          <span className="font-bold">Просрочено.</span> Текущий статус
          сохранён, но обязательный срок нарушен. Обычное закрытие требует
          резолюции главного инженера.
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Параметры задания" />
            <dl className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 sm:p-6">
              <Info label="Оборудование" value={task.equipmentName} />
              <Info
                label="Операция"
                value={`${task.maintenanceType} · ${task.operationCode}`}
              />
              <Info label="Обязательный срок" value={formatDate(task.mandatoryDueDate)} />
              <Info label="Планируемый интервал" value={`${formatDateTime(task.scheduledStart)} — ${formatDateTime(task.scheduledEnd)}`} />
              <Info label="Размер бригады" value={`${task.crewSize} чел.`} />
              <Info
                label="Нарушение срока"
                value={task.deadlineBreached ? "Зафиксировано" : "Нет"}
              />
            </dl>
          </Card>

          {execution ? (
            <Card>
              <CardHeader
                title={`Попытка №${execution.attemptNumber}`}
                description={
                  execution.state === "submitted"
                    ? "Отправленный отчёт заморожен"
                    : "Черновик отчёта исполнителя"
                }
                action={
                  <Link
                    to={`/quality/${task.id}`}
                    className="text-sm font-semibold text-emerald-700"
                  >
                    Фото и проверка
                  </Link>
                }
              />
              <div className="p-5 sm:p-6">
                <p className="text-sm leading-6 text-slate-600">
                  {execution.narrative || "Комментарий пока не заполнен."}
                </p>
                <div className="mt-4 space-y-2">
                  {execution.checklist.map((item) => (
                    <ChecklistRow key={item.id} item={item} />
                  ))}
                </div>
                <div className="mt-5">
                  <EvidenceGallery photos={execution.photos} />
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Бригада" />
            {task.assignees.length ? (
              <ul className="divide-y divide-slate-100">
                {task.assignees.map((assignee) => (
                  <li key={assignee.executorId} className="px-5 py-4 sm:px-6">
                    <p className="font-semibold text-slate-900">
                      {assignee.name}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {assignee.qualifications.join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-6 text-sm text-slate-500">
                Исполнитель не назначен.
              </p>
            )}
          </Card>

          {review ? (
            <Card>
              <CardHeader title="AI-контроль" />
              <div className="p-5 sm:p-6">
                <ReviewStatusBadge status={review.status} />
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  Модель {review.modelRef}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Prompt set {review.promptSetVersion}
                </p>
                <Link
                  to={`/quality/${task.id}`}
                  className={buttonClassName("secondary", "sm", "mt-4 w-full")}
                >
                  Открыть заключение
                </Link>
              </div>
            </Card>
          ) : null}

          {decision ? (
            <Card>
              <CardHeader title="Решение инженера" />
              <div className="p-5 sm:p-6">
                <EngineerDecisionBadge verdict={decision.verdict} />
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  {decision.reason}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  {decision.decidedBy} · {formatDateTime(decision.decidedAt)}
                </p>
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Переходы" />
            <div className="p-5 text-xs leading-5 text-slate-500 sm:p-6">
              {task.state === "draft"
                ? "Черновик → Назначено: требуется доступная бригада и подтверждённая длительность."
                : null}
              {task.state === "assigned"
                ? "Назначено → В работе: доступно назначенному исполнителю."
                : null}
              {task.state === "in_progress"
                ? "В работе → На проверке: отправка замораживает текущую попытку."
                : null}
              {task.state === "submitted"
                ? "На проверке → Принято или На доработке: решение принимает инженер."
                : null}
              {task.state === "rework_required"
                ? "На доработке → В работе: создаётся новая попытка, старая не меняется."
                : null}
              {task.state === "accepted"
                ? "Принято: задание закрыто, принятый факт добавлен в историю оборудования."
                : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ChecklistRow({ item }: { item: ChecklistItem }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
      <div>
        <p className="text-sm text-slate-800">{item.text}</p>
        <p className="mt-0.5 text-xs text-slate-400">
          {item.required ? "Обязательный" : "Необязательный"}
          {item.photoRequired ? " · нужен фотофиксатор" : ""}
        </p>
      </div>
      <span className="text-sm font-semibold text-slate-700">
        {formatAnswer(item)}
      </span>
    </div>
  );
}

function formatAnswer(item: ChecklistItem): string {
  if (item.answer === null || item.answer === "") {
    return "—";
  }
  if (item.answer === "done") {
    return "Выполнено";
  }
  if (item.answer === "not_done") {
    return "Не выполнено";
  }
  if (item.answer === "not_applicable") {
    return "Не применимо";
  }
  return item.unit ? `${item.answer} ${item.unit}` : item.answer;
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold text-slate-900">{value}</dd>
    </div>
  );
}
