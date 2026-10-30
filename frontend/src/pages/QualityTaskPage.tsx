import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { EvidenceGallery } from "@/entities/execution/EvidenceGallery";
import { ChecklistSummary } from "@/entities/execution/ChecklistSummary";
import { Callout } from "@/shared/ui/Callout";
import { FormField, Textarea } from "@/shared/ui/Form";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import { Modal } from "@/shared/ui/Modal";
import {
  EngineerDecisionBadge,
  OriginBadge,
  OverdueBadge,
  ReviewStatusBadge,
  TaskStateBadge,
  VerdictBadge,
} from "@/shared/ui/StatusBadge";

export function QualityTaskPage() {
  const { taskId = "" } = useParams();
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<
    "accepted" | "rejected" | null
  >(null);
  const query = useApiQuery(
    () => maintenanceApi.getQualityBundle(taskId),
    [taskId],
  );

  if (query.status === "loading") {
    return <LoadingState label="Загрузка отчёта на приёмку" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/quality" className={buttonClassName("secondary")}>
            Вернуться в очередь
          </Link>
        }
      />
    );
  }

  const { task, execution, review, decision } = query.data;

  const handleDecision = (verdict: "accepted" | "rejected") => {
    setNotice(
      verdict === "accepted"
        ? "Маршрут готов: приёмка будет отправлять POST /tasks/{id}/review с verdict=accepted. Сервер обязан проверить запрет собственной приёмки."
        : "Маршрут готов: отклонение будет отправлять POST /tasks/{id}/review с verdict=rejected и обязательной причиной.",
    );
    setPendingDecision(null);
  };

  return (
    <div className="space-y-6">
      <Link
        to="/quality"
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
      >
        <Icon name="back" size={18} />
        Контроль качества
      </Link>

      <PageHeader
        eyebrow={task.code}
        title={task.title}
        description={`${task.equipmentName} · ${task.summary}`}
        actions={
          <Link to={`/tasks/${task.id}`} className={buttonClassName("secondary")}>
            Карточка задания
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <TaskStateBadge state={task.state} />
        {task.isOverdue ? <OverdueBadge /> : null}
        <OriginBadge origin={task.dataOrigin} />
        <span className="text-xs text-muted">
          Попытка №{execution?.attemptNumber ?? "—"}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Отчёт исполнителя"
              description={
                execution?.submittedAt
                  ? `Отправлен ${formatDateTime(execution.submittedAt)}`
                  : "Отчёт ещё не отправлен"
              }
            />
            <div className="p-5 sm:p-6">
              <p className="text-sm leading-6 text-ink-soft">
                {execution?.narrative || "Комментарий отсутствует."}
              </p>
              {execution?.checklist.length ? (
                <div className="mt-4">
                  <ChecklistSummary
                    items={execution.checklist}
                    mode="quality"
                  />
                </div>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Фотографии попытки"
              description="Доступ проверяется по Site и заданию"
            />
            <div className="p-5 sm:p-6">
              <EvidenceGallery
                photos={execution?.photos ?? []}
                emptyText="Фото к этой попытке не приложены"
              />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="AI-заключение"
              description="Ограниченный анализ видимых изменений"
              action={
                review ? <ReviewStatusBadge status={review.status} /> : null
              }
            />
            <div className="p-5 sm:p-6">
              {review ? (
                <>
                  <div className="rounded-xl bg-white/[0.035] p-4">
                    <p className="text-xs font-semibold text-muted">
                      Модель
                    </p>
                    <p className="mt-1 font-mono text-xs break-all text-ink-soft">
                      {review.modelRef}
                    </p>
                    <p className="mt-2 text-xs text-muted">
                      Prompt set {review.promptSetVersion} ·{" "}
                      {formatDateTime(review.createdAt)}
                    </p>
                  </div>

                  <ul className="mt-4 space-y-3">
                    {review.items.map((item) => (
                      <li
                        key={item.id}
                        className="rounded-xl border border-line p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-ink">
                            {item.label}
                          </p>
                          <VerdictBadge verdict={item.verdict} />
                        </div>
                        <p className="mt-1 text-xs leading-5 text-muted">
                          {item.note}
                        </p>
                      </li>
                    ))}
                  </ul>

                  <Callout
                    tone="warning"
                    title="Ограничения"
                    className="mt-4 text-xs"
                  >
                    <ul className="space-y-1">
                      {review.limitations.map((limitation) => (
                        <li key={limitation}>{limitation}</li>
                      ))}
                    </ul>
                  </Callout>
                </>
              ) : (
                <EmptyState
                  title="AI-заключение не создано"
                  description="Запрос к POST /executions/{id}/ai-review выполняется только для замороженной submitted-попытки."
                />
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Основание решения" />
            <div className="p-5 sm:p-6">
              <InfoList className="grid grid-cols-2 gap-4">
                <InfoItem
                  label="Срок"
                  value={formatDate(task.mandatoryDueDate)}
                />
                <InfoItem label="Ревизия" value={String(task.revision)} />
              </InfoList>
              <p className="mt-4 text-xs leading-5 text-muted">
                Причина обязательна и при приёмке, и при отклонении. Для
                неуверенного AI-результата она служит основанием ручной оценки.
              </p>

              <FormField
                label="Причина решения"
                htmlFor="quality-reason"
                hint="Основание сохраняется в EngineerDecision."
                required
                className="mt-4"
              >
                <Textarea
                  id="quality-reason"
                  value={reason}
                  onChange={(event) => {
                    setReason(event.target.value);
                    setNotice(null);
                  }}
                  rows={4}
                  placeholder="Опишите, что проверено и на каком основании"
                />
              </FormField>

              {notice ? (
                <Callout tone="info" className="mt-3 text-xs">
                  {notice}
                </Callout>
              ) : null}

              <div className="mt-4 grid gap-2">
                <Button
                  disabled={!reason.trim()}
                  onClick={() => setPendingDecision("accepted")}
                >
                  <Icon name="check" size={18} />
                  Принять работу
                </Button>
                <Button
                  variant="danger"
                  disabled={!reason.trim()}
                  onClick={() => setPendingDecision("rejected")}
                >
                  <Icon name="alert" size={18} />
                  Вернуть на доработку
                </Button>
              </div>
            </div>
          </Card>

          {decision ? (
            <Card>
              <CardHeader title="Предыдущее решение" />
              <div className="p-5 sm:p-6">
                <EngineerDecisionBadge verdict={decision.verdict} />
                <p className="mt-2 text-sm leading-6 text-ink-soft">
                  {decision.reason}
                </p>
                <p className="mt-2 text-xs text-muted">
                  {decision.decidedBy} · {formatDateTime(decision.decidedAt)}
                </p>
              </div>
            </Card>
          ) : null}

          <Callout tone="neutral" className="text-xs leading-5">
            Принятие, запись EngineerDecision, создание ServiceEvent и аудит
            должны выполняться в одной транзакции на backend. Скрытие кнопки не
            заменяет проверку прав.
          </Callout>
        </div>
      </div>
      <Modal
        open={pendingDecision !== null}
        title={
          pendingDecision === "rejected"
            ? "Вернуть работу на доработку?"
            : "Принять работу?"
        }
        description={
          pendingDecision === "rejected"
            ? "Отклонение создаст новую попытку и сохранит текущую в истории."
            : "Принятие закроет задание и добавит событие в историю оборудования."
        }
        tone={pendingDecision === "rejected" ? "danger" : "default"}
        onClose={() => setPendingDecision(null)}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setPendingDecision(null)}
            >
              Отмена
            </Button>
            <Button
              variant={pendingDecision === "rejected" ? "danger" : "primary"}
              onClick={() =>
                pendingDecision ? handleDecision(pendingDecision) : undefined
              }
            >
              {pendingDecision === "rejected"
                ? "Вернуть на доработку"
                : "Подтвердить приёмку"}
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-ink-soft">{reason}</p>
        <p className="mt-3 text-xs text-muted">
          Проверьте фотографии и заключение AI перед подтверждением.
        </p>
      </Modal>

    </div>
  );
}
