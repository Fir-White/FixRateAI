import { useState } from "react";
import { useSession } from "@/shared/session/SessionContext";
import { DEMO_MODE } from "@/shared/api/request";
import { Link, useParams, useNavigate } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { EvidenceGallery } from "@/entities/execution/EvidenceGallery";
import { ChecklistSummary } from "@/entities/execution/ChecklistSummary";
import { Callout } from "@/shared/ui/Callout";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import {
  EngineerDecisionBadge,
  OriginBadge,
  OverdueBadge,
  ReviewStatusBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const navigate = useNavigate();
  const { profile } = useSession();
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
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
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
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
            {!DEMO_MODE && (profile?.role === "dispatcher" || profile?.role === "engineer") && <Button variant="secondary" disabled={busy} onClick={async () => {
              setBusy(true); setNotice("");
              try { const result = await maintenanceApi.forecast(task.id, task.revision); navigate(`/comparisons/${result.run.runId}`); }
              catch (error) { setNotice(error instanceof Error ? error.message : "Ошибка прогноза"); }
              finally { setBusy(false); }
            }}>Сравнить прогнозы</Button>}
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

      {notice && <div role="alert"><Callout tone="danger">{notice}</Callout></div>}
      <div className="flex flex-wrap items-center gap-2">
        <TaskStateBadge state={task.state} />
        {task.isOverdue ? <OverdueBadge /> : null}
        <OriginBadge origin={task.dataOrigin} />
        <span className="text-xs text-muted">Ревизия {task.revision}</span>
      </div>

      {task.isOverdue ? (
        <Callout tone="danger" title="Просрочено.">
          Текущий статус сохранён, но обязательный срок нарушен. Обычное
          закрытие требует резолюции главного инженера.
        </Callout>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Параметры задания" />
            <InfoList className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 sm:p-6">
              <InfoItem label="Оборудование" value={task.equipmentName} />
              <InfoItem
                label="Операция"
                value={`${task.maintenanceType} · ${task.operationCode}`}
              />
              <InfoItem
                label="Обязательный срок"
                value={formatDate(task.mandatoryDueDate)}
              />
              <InfoItem
                label="Планируемый интервал"
                value={`${formatDateTime(task.scheduledStart)} — ${formatDateTime(task.scheduledEnd)}`}
              />
              <InfoItem label="Размер бригады" value={`${task.crewSize} чел.`} />
              <InfoItem
                label="Нарушение срока"
                value={task.deadlineBreached ? "Зафиксировано" : "Нет"}
              />
            </InfoList>
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
                    className="text-sm font-semibold text-accent"
                  >
                    Фото и проверка
                  </Link>
                }
              />
              <div className="p-5 sm:p-6">
                <p className="text-sm leading-6 text-ink-soft">
                  {execution.narrative || "Комментарий пока не заполнен."}
                </p>
                <div className="mt-4">
                  <ChecklistSummary items={execution.checklist} />
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
              <ul className="divide-y divide-line">
                {task.assignees.map((assignee) => (
                  <li key={assignee.executorId} className="px-5 py-4 sm:px-6">
                    <p className="font-semibold text-ink">
                      {assignee.name}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {assignee.qualifications.join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-6 text-sm text-muted">
                Исполнитель не назначен.
              </p>
            )}
          </Card>

          {review ? (
            <Card>
              <CardHeader title="AI-контроль" />
              <div className="p-5 sm:p-6">
                <ReviewStatusBadge status={review.status} />
                <p className="mt-3 text-sm leading-6 text-ink-soft">
                  Модель {review.modelRef}
                </p>
                <p className="mt-1 text-xs text-muted">
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
                <p className="mt-3 text-sm leading-6 text-ink-soft">
                  {decision.reason}
                </p>
                <p className="mt-2 text-xs text-muted">
                  {decision.decidedBy} · {formatDateTime(decision.decidedAt)}
                </p>
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Переходы" />
            <div className="p-5 text-xs leading-5 text-muted sm:p-6">
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
