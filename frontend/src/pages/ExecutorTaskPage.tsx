import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { useSession } from "@/shared/session/SessionContext";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { Checkbox, FormField, Input, Textarea } from "@/shared/ui/Form";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import { Icon } from "@/shared/ui/Icon";
import { EvidenceGallery } from "@/entities/execution/EvidenceGallery";
import {
  OverdueBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";
import type { ChecklistItem } from "@/shared/types/domain";

export function ExecutorTaskPage() {
  const { taskId = "" } = useParams();
  const { profile } = useSession();
  const [notice, setNotice] = useState<string | null>(null);
  const query = useApiQuery(() => maintenanceApi.getExecutorTask(taskId), [taskId]);

  if (query.status === "loading") {
    return <LoadingState label="Загрузка задания" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/executor" className={buttonClassName("secondary")}>
            Мои задания
          </Link>
        }
      />
    );
  }

  const { task, execution, decision } = query.data;
  const assignedToMe = task.assignees.some(
    (assignee) => assignee.executorId === profile?.userId,
  );

  if (!assignedToMe) {
    return (
      <ErrorState
        title="Задание назначено другому исполнителю"
        description="Доступ к работе и фотоотчёту проверяется по заданию на backend."
        action={
          <Link to="/executor" className={buttonClassName("secondary")}>
            Мои задания
          </Link>
        }
      />
    );
  }

  const canStart = task.state === "assigned";
  const canSubmit =
    task.state === "in_progress" || task.state === "rework_required";

  return (
    <div className="space-y-5">
      <Link
        to="/executor"
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
      >
        <Icon name="back" size={18} />
        Мои задания
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <TaskStateBadge state={task.state} />
          {task.isOverdue ? <OverdueBadge /> : null}
          <span className="text-xs text-muted">{task.code}</span>
        </div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink">
          {task.title}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {task.equipmentName} · {task.summary}
        </p>
      </div>

      {task.isOverdue ? (
        <Callout tone="danger" title="Просрочено.">
          Статус не меняется, факт нарушения срока сохраняется.
        </Callout>
      ) : null}

      <InfoList className="grid grid-cols-2 gap-3 rounded-2xl border border-line bg-surface p-4">
        <InfoItem
          label="Срок"
          value={formatDate(task.mandatoryDueDate)}
        />
        <InfoItem
          label="Интервал"
          value={formatDateTime(task.scheduledStart)}
        />
      </InfoList>

      {execution ? (
        <>
          <section className="rounded-2xl border border-line bg-surface p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-ink">
                  Чек-лист
                </h2>
                <p className="mt-1 text-xs text-muted">
                  Попытка №{execution.attemptNumber}
                </p>
              </div>
              <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] font-semibold text-ink-soft">
                {execution.state === "submitted" ? "Отправлен" : "Черновик"}
              </span>
            </div>

            <div className="mt-4 space-y-3">
              {execution.checklist.map((item) => (
                <ChecklistField key={item.id} item={item} />
              ))}
            </div>

            <FormField
              label="Комментарий исполнителя"
              htmlFor="executor-narrative"
              hint="Комментарий сохраняется в отправленном отчёте."
              className="mt-4"
            >
              <Textarea
                id="executor-narrative"
                value={execution.narrative}
                readOnly
                rows={3}
                placeholder="Комментарий появится в отчёте"
              />
            </FormField>
          </section>

          <section className="rounded-2xl border border-line bg-surface p-4">
            <h2 className="text-base font-semibold text-ink">Фотоотчёт</h2>
            <p className="mt-1 text-xs leading-5 text-muted">
              Фото привязываются к попытке, оборудованию, пункту чек-листа и
              ракурсу. Загрузка станет доступна после подключения storage API.
            </p>
            <div className="mt-4">
              <EvidenceGallery photos={execution.photos} />
            </div>
            <Button variant="secondary" size="sm" className="mt-4 w-full" disabled>
              <Icon name="upload" size={16} />
              Добавить фото
            </Button>
          </section>
        </>
      ) : (
        <EmptyState
          title="Попытка ещё не создана"
          description="При нажатии «Приступить» backend создаёт черновик отчёта и фиксирует время начала."
        />
      )}

      {decision ? (
        <Callout tone="danger" title="Замечание инженера">
          <p>{decision.reason}</p>
          <p className="mt-2 text-xs opacity-80">
            {decision.decidedBy} · {formatDateTime(decision.decidedAt)}
          </p>
        </Callout>
      ) : null}

      {notice ? <Callout tone="info">{notice}</Callout> : null}

      <div className="rounded-2xl border border-line bg-surface p-4">
        <p className="text-xs leading-5 text-muted">
          Демонстрационная форма. Отправка отчёта, проверка обязательных фото и
          заморозка попытки будут выполняться через backend.
        </p>
        {canStart ? (
          <Button
            className="mt-3 w-full"
            onClick={() =>
              setNotice(
                "Маршрут готов: начало работы будет отправлять POST /tasks/{id}/start после подключения API.",
              )
            }
          >
            Приступить к работе
          </Button>
        ) : null}
        {canSubmit ? (
          <Button
            className="mt-3 w-full"
            onClick={() =>
              setNotice(
                "Маршрут готов: сдача отчёта будет отправлять POST /executions/{id}/submit и проверять обязательные фото.",
              )
            }
          >
            Сдать работу
          </Button>
        ) : null}
        {task.state === "submitted" ? (
          <Callout tone="warning" className="mt-3">
            Отчёт отправлен и ожидает решения инженера.
          </Callout>
        ) : null}
        {task.state === "accepted" ? (
          <Callout tone="success" className="mt-3">
            Работа принята. Отчёт заморожен.
          </Callout>
        ) : null}
      </div>
    </div>
  );
}

function ChecklistField({ item }: { item: ChecklistItem }) {
  return (
    <div className="rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-medium text-ink">{item.text}</p>
        {item.required ? (
          <span className="text-[10px] font-semibold tracking-wide text-rose-300 uppercase">
            Обязательно
          </span>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {item.answerKind === "boolean" ? (
          <Checkbox
            label="Выполнено"
            checked={item.answer === "done"}
            readOnly
          />
        ) : (
          <div className="flex items-center gap-2">
            <Input
              value={item.answer ?? ""}
              readOnly
              placeholder="Не заполнено"
              aria-label={item.text}
              className="h-9 w-40"
            />
            {item.unit ? (
              <span className="text-xs font-semibold text-muted">
                {item.unit}
              </span>
            ) : null}
          </div>
        )}
        {item.photoRequired ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-violet-400/10 px-2 py-1 text-[10px] font-semibold text-violet-200">
            <Icon name="camera" size={12} />
            Нужно фото
          </span>
        ) : null}
      </div>
    </div>
  );
}
