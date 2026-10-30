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
import {
  EngineerDecisionBadge,
  OriginBadge,
  OverdueBadge,
  ReviewStatusBadge,
  TaskStateBadge,
  VerdictBadge,
} from "@/shared/ui/StatusBadge";
import type { ChecklistItem } from "@/shared/types/domain";

export function QualityTaskPage() {
  const { taskId = "" } = useParams();
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
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
  };

  return (
    <div className="space-y-6">
      <Link
        to="/quality"
        className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
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
        <span className="text-xs text-slate-500">
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
              <p className="text-sm leading-6 text-slate-700">
                {execution?.narrative || "Комментарий отсутствует."}
              </p>
              <div className="mt-4 space-y-2">
                {execution?.checklist.map((item) => (
                  <ChecklistRow key={item.id} item={item} />
                ))}
              </div>
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
                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold text-slate-500">
                      Модель
                    </p>
                    <p className="mt-1 font-mono text-xs break-all text-slate-700">
                      {review.modelRef}
                    </p>
                    <p className="mt-2 text-xs text-slate-500">
                      Prompt set {review.promptSetVersion} ·{" "}
                      {formatDateTime(review.createdAt)}
                    </p>
                  </div>

                  <ul className="mt-4 space-y-3">
                    {review.items.map((item) => (
                      <li
                        key={item.id}
                        className="rounded-xl border border-slate-200 p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-800">
                            {item.label}
                          </p>
                          <VerdictBadge verdict={item.verdict} />
                        </div>
                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          {item.note}
                        </p>
                      </li>
                    ))}
                  </ul>

                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
                    <p className="text-xs font-bold text-amber-900">
                      Ограничения
                    </p>
                    <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-800">
                      {review.limitations.map((limitation) => (
                        <li key={limitation}>{limitation}</li>
                      ))}
                    </ul>
                  </div>
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
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <Info label="Срок" value={formatDate(task.mandatoryDueDate)} />
                <Info label="Ревизия" value={String(task.revision)} />
              </dl>
              <p className="mt-4 text-xs leading-5 text-slate-500">
                Причина обязательна и при приёмке, и при отклонении. Для
                неуверенного AI-результата она служит основанием ручной оценки.
              </p>

              <label className="mt-4 block">
                <span className="text-xs font-bold text-slate-600">
                  Причина решения
                </span>
                <textarea
                  value={reason}
                  onChange={(event) => {
                    setReason(event.target.value);
                    setNotice(null);
                  }}
                  rows={4}
                  placeholder="Опишите, что проверено и на каком основании"
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                />
              </label>

              {notice ? (
                <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-900">
                  {notice}
                </div>
              ) : null}

              <div className="mt-4 grid gap-2">
                <Button
                  disabled={!reason.trim()}
                  onClick={() => handleDecision("accepted")}
                >
                  <Icon name="check" size={18} />
                  Принять работу
                </Button>
                <Button
                  variant="danger"
                  disabled={!reason.trim()}
                  onClick={() => handleDecision("rejected")}
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
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {decision.reason}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  {decision.decidedBy} · {formatDateTime(decision.decidedAt)}
                </p>
              </div>
            </Card>
          ) : null}

          <Card className="border-slate-200 bg-slate-50">
            <div className="p-5 text-xs leading-5 text-slate-500 sm:p-6">
              Принятие, запись EngineerDecision, создание ServiceEvent и аудит
              должны выполняться в одной транзакции на backend. Скрытие кнопки
              не заменяет проверку прав.
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ChecklistRow({ item }: { item: ChecklistItem }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
      <div>
        <p className="text-sm text-slate-800">{item.text}</p>
        <p className="mt-0.5 text-xs text-slate-400">
          {item.visualVerifiability === "not_verifiable"
            ? "Не проверяется по фото"
            : item.photoRequired
              ? "Требуется фото"
              : "Без обязательного фото"}
        </p>
      </div>
      <span className="text-sm font-semibold text-slate-700">
        {formatAnswer(item)}
      </span>
    </div>
  );
}

function formatAnswer(item: ChecklistItem): string {
  if (!item.answer) {
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
      <dt className="text-xs font-semibold text-slate-500">{label}</dt>
      <dd className="mt-1 font-bold text-slate-900">{value}</dd>
    </div>
  );
}
