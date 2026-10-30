import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { useSession } from "@/shared/session/SessionContext";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
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
        className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
      >
        <Icon name="back" size={18} />
        Мои задания
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <TaskStateBadge state={task.state} />
          {task.isOverdue ? <OverdueBadge /> : null}
          <span className="text-xs text-slate-500">{task.code}</span>
        </div>
        <h1 className="mt-3 text-2xl font-black tracking-tight text-slate-950">
          {task.title}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {task.equipmentName} · {task.summary}
        </p>
      </div>

      {task.isOverdue ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
          <span className="font-bold">Просрочено.</span> Статус не меняется,
          факт нарушения срока сохраняется.
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm">
        <Info label="Срок" value={formatDate(task.mandatoryDueDate)} />
        <Info label="Интервал" value={formatDateTime(task.scheduledStart)} />
      </div>

      {execution ? (
        <>
          <section className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-slate-950">
                  Чек-лист
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  Попытка №{execution.attemptNumber}
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">
                {execution.state === "submitted" ? "Отправлен" : "Черновик"}
              </span>
            </div>

            <div className="mt-4 space-y-3">
              {execution.checklist.map((item) => (
                <ChecklistField key={item.id} item={item} />
              ))}
            </div>

            <label className="mt-4 block">
              <span className="text-xs font-bold text-slate-600">
                Комментарий исполнителя
              </span>
              <textarea
                value={execution.narrative}
                readOnly
                rows={3}
                placeholder="Комментарий появится в отчёте"
                className="mt-1 w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-700"
              />
            </label>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-base font-bold text-slate-950">Фотоотчёт</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
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
        <section className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
          <p className="text-sm font-bold text-rose-900">
            Замечание инженера
          </p>
          <p className="mt-1 text-sm leading-6 text-rose-800">
            {decision.reason}
          </p>
          <p className="mt-2 text-xs text-rose-700">
            {decision.decidedBy} · {formatDateTime(decision.decidedAt)}
          </p>
        </section>
      ) : null}

      {notice ? (
        <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm leading-6 text-sky-900">
          {notice}
        </div>
      ) : null}

      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-xs leading-5 text-slate-500">
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
          <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900">
            Отчёт отправлен и ожидает решения инженера.
          </div>
        ) : null}
        {task.state === "accepted" ? (
          <div className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-900">
            Работа принята. Отчёт заморожен.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ChecklistField({ item }: { item: ChecklistItem }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-medium text-slate-800">{item.text}</p>
        {item.required ? (
          <span className="text-[10px] font-bold tracking-wide text-rose-600 uppercase">
            Обязательно
          </span>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {item.answerKind === "boolean" ? (
          <label className="inline-flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={item.answer === "done"}
              readOnly
              className="h-4 w-4 rounded border-slate-300 accent-emerald-700"
            />
            Выполнено
          </label>
        ) : (
          <div className="flex items-center gap-2">
            <input
              value={item.answer ?? ""}
              readOnly
              placeholder="Не заполнено"
              className="h-9 w-40 rounded-lg border border-slate-300 bg-slate-50 px-3 text-sm text-slate-700"
            />
            {item.unit ? (
              <span className="text-xs font-semibold text-slate-500">
                {item.unit}
              </span>
            ) : null}
          </div>
        )}
        {item.photoRequired ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-1 text-[10px] font-bold text-violet-700">
            <Icon name="camera" size={12} />
            Нужно фото
          </span>
        ) : null}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      <p className="mt-1 font-bold text-slate-900">{value}</p>
    </div>
  );
}
