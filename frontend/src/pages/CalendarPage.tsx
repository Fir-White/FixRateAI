import { DEMO_MODE } from "@/shared/api/request";
import { useSession } from "@/shared/session/SessionContext";
import { useMemo, useState } from "react";
import { useWorkspaceState } from "@/shared/lib/workspaceState";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, formatMonth } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, IconButton } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { StatCard } from "@/widgets/StatCard";
import { Icon } from "@/shared/ui/Icon";
import type { CalendarOccurrence, CalendarPreview, CalendarPreviewOccurrence } from "@/shared/types/domain";
import { taskPathForRole } from "@/shared/lib/roles";
import { PlanningRunPanel } from "@/features/planning/PlanningRunPanel";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

interface MonthCursor {
  year: number;
  month: number;
}

export function CalendarPage() {
  const { profile } = useSession();
  const today = new Intl.DateTimeFormat("en-CA", {timeZone: profile?.timezone ?? "Asia/Yekaterinburg", year: "numeric", month: "2-digit", day: "2-digit"}).format(new Date());
  const [cursor, setCursor] = useWorkspaceState<MonthCursor>("calendar.month", () => DEMO_MODE ? {year: 2026, month: 10} : {year: Number(today.slice(0,4)), month: Number(today.slice(5,7))}, (value): value is MonthCursor => {
    if (!value || typeof value !== "object") return false;
    const cursor = value as MonthCursor;
    return Number.isInteger(cursor.year) && cursor.year >= 2000 && cursor.year <= 2200 && Number.isInteger(cursor.month) && cursor.month >= 1 && cursor.month <= 12;
  });
  const [mode, setMode] = useState<"saved" | "preview">("saved");
  const [calculation, setCalculation] = useState(0);
  const mayPreview = profile?.role === "dispatcher" || profile?.role === "engineer";
  const query = useApiQuery(
    async () => {
      const preview = mode === "preview" ? await maintenanceApi.previewCalendar(cursor.year, cursor.month) : null;
      return {year: cursor.year, month: cursor.month, mode, preview,
        items: preview?.items ?? await maintenanceApi.listCalendar(cursor.year, cursor.month)};
    },
    [cursor.year, cursor.month, mode, calculation],
  );
  // Never display a previous month's response under the new month heading.
  const data = query.status === "success" && query.data.year === cursor.year &&
    query.data.month === cursor.month && query.data.mode === mode ? query.data : null;
  const pending = query.status === "loading" || (query.status === "success" && !data);

  const grouped = useMemo(() => {
    const map = new Map<string, CalendarOccurrence[]>();
    if (!data) {
      return map;
    }
    data.items.forEach((occurrence) => {
      const bucket = map.get(occurrence.occurrenceDate) ?? [];
      bucket.push(occurrence);
      map.set(occurrence.occurrenceDate, bucket);
    });
    return map;
  }, [data]);

  const shiftMonth = (delta: number) => {
    setCursor((current) => {
      const date = new Date(
        Date.UTC(current.year, current.month - 1 + delta, 1),
      );
      return {
        year: date.getUTCFullYear(),
        month: date.getUTCMonth() + 1,
      };
    });
  };

  const daysInMonth = new Date(
    Date.UTC(cursor.year, cursor.month, 0),
  ).getUTCDate();
  const firstWeekday = new Date(
    Date.UTC(cursor.year, cursor.month - 1, 1),
  ).getUTCDay();
  const leadingCells = (firstWeekday + 6) % 7;
  const totalCells = Math.ceil((leadingCells + daysInMonth) / 7) * 7;
  const occurrencesCount = data?.items.length ?? 0;
  const overdueCount = data?.preview
    ? data.preview.items.filter(item => item.deadlinePassed).length
    : data?.items.filter(item => item.isOverdue).length ?? 0;
  const needsInputCount = data?.preview
    ? data.preview.diagnostics.filter(item => item.status === "needs_input" || item.status === "manual_review").length
    : data?.items.filter(item => item.requiresInput).length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Планирование"
        title="Календарь технического обслуживания"
        description="Работы по оборудованию и регламентам в часовом поясе объекта. Откройте сохранённый график или рассчитайте предварительные даты."
        actions={
          <div className="flex items-center gap-2">
            <IconButton
              label="Предыдущий месяц"
              disabled={cursor.year === 2000 && cursor.month === 1}
              onClick={() => shiftMonth(-1)}
            >
              <Icon name="back" size={16} />
            </IconButton>
            <span className="min-w-40 text-center text-sm font-semibold text-ink capitalize">
              {formatMonth(cursor.year, cursor.month)}
            </span>
            <IconButton
              label="Следующий месяц"
              disabled={cursor.year >= (mode === "preview" ? 2100 : 2200) && cursor.month === 12}
              onClick={() => shiftMonth(1)}
            >
              <Icon name="chevron" size={16} />
            </IconButton>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        {mayPreview && <Button disabled={pending || DEMO_MODE || cursor.year > 2100}
          title={DEMO_MODE ? "Для расчёта нужно подключение к серверу" : undefined}
          onClick={() => { setMode("preview"); setCalculation(value => value + 1); }}>
          {mode === "preview" ? "Пересчитать график" : "Рассчитать график"}
        </Button>}
        {mode === "preview" && <Button variant="secondary" onClick={() => setMode("saved")}>
          Сохранённый график
        </Button>}
        <span className="text-sm text-muted">{mode === "preview" ? "Предварительный расчёт" : "Сохранённый график"}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Вхождений" value={occurrencesCount} />
        <StatCard label={mode === "preview" ? "Дат в прошлом" : "Просрочено"} value={overdueCount} tone="danger" />
        <StatCard
          label={mode === "preview" ? "Привязок требуют внимания" : "Вхождений требуют уточнения"}
          value={needsInputCount}
          tone="warning"
        />
      </div>

      <Callout tone="warning" title={mode === "preview" ? "Предварительный расчёт" : "Сохранённые данные"}>
        {mode === "preview"
          ? "Даты рассчитаны по текущим регламентам. Расчёт не сохраняет план и не назначает работников. Дата в прошлом сама по себе не доказывает, что работа не выполнена."
          : "Показаны сохранённые работы. Предварительный расчёт доступен диспетчеру и инженеру; неподтверждённые правила требуют уточнения."}
      </Callout>

      {pending ? <LoadingState label={mode === "preview" ? "Расчёт графика" : "Загрузка календаря"} /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}
      {data?.preview && profile?.role === "dispatcher" && !DEMO_MODE && <PlanningRunPanel
        key={`${cursor.year}:${cursor.month}:${data.preview.generationToken}:${calculation}`} preview={data.preview}
        onRecalculate={() => setCalculation(value => value+1)} />}

      {data ? (
        <Card className="overflow-hidden">
          <div
            role="region"
            aria-label="Сетка календаря"
            data-scroll-key="calendar-grid"
            tabIndex={0}
            className="overflow-x-auto rounded-b-xl focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
          >
            <div className="min-w-[760px]">
              <div className="grid grid-cols-7 border-b border-line bg-white/[0.03]">
                {WEEKDAYS.map((weekday) => (
                  <div
                    key={weekday}
                    className="px-2 py-2 text-center text-xs font-semibold tracking-wide text-muted uppercase"
                  >
                    {weekday}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7">
                {Array.from({ length: totalCells }, (_, index) => {
                  const dayNumber = index - leadingCells + 1;
                  const validDay = dayNumber >= 1 && dayNumber <= daysInMonth;
                  const dateKey = validDay
                    ? `${cursor.year}-${String(cursor.month).padStart(2, "0")}-${String(dayNumber).padStart(2, "0")}`
                    : "";
                  const dayItems = validDay ? (grouped.get(dateKey) ?? []) : [];
                  const isToday = dateKey === (DEMO_MODE ? "2026-10-30" : today);

                  return (
                    <div
                      key={index}
                      className={`min-h-28 border-r border-b border-line p-2 last:border-r-0 ${
                        validDay ? "bg-surface" : "bg-white/[0.015]"
                      } ${isToday ? "ring-2 ring-accent ring-inset" : ""}`}
                    >
                      {validDay ? (
                        <>
                          <div className="flex items-center justify-between">
                            <span
                              className={`text-xs font-semibold ${
                                isToday ? "text-accent" : "text-muted"
                              }`}
                            >
                              {dayNumber}
                            </span>
                            {dayItems.some((item) => item.isOverdue) ? (
                              <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                            ) : null}
                          </div>
                          <div className="mt-1.5 space-y-1">
                            {dayItems.slice(0, 2).map((item) => (
                              <OccurrenceChip
                                key={item.id}
                                occurrence={item}
                              />
                            ))}
                            {dayItems.length > 2 ? (
                              <details className="text-[10px] text-muted">
                                <summary className="cursor-pointer px-1 py-1">Ещё {dayItems.length - 2}</summary>
                                <div className="space-y-1">{dayItems.slice(2).map(item => <OccurrenceChip key={item.id} occurrence={item} />)}</div>
                              </details>
                            ) : null}
                          </div>
                        </>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4 border-t border-line px-5 py-3 text-xs text-muted">
            {mode === "saved" && <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent" />
              Выполнено
            </span>}
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-sky-400" />
              {mode === "preview" ? "Черновик" : "Запланировано"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${mode === "preview" ? "bg-amber-400" : "bg-rose-400"}`} />
              {mode === "preview" ? "Дата в прошлом — требуется проверка" : "Просрочено"}
            </span>
          </div>
        </Card>
      ) : null}

      {data?.preview && <PreviewDiagnostics preview={data.preview} />}

      {data && occurrencesCount === 0 ? (
        <p className="text-center text-sm text-muted">
          {mode === "preview" ? "Для выбранного месяца даты не рассчитаны. Причины указаны по каждой привязке оборудования." : "Для выбранного месяца вхождений нет. Это не означает, что регламент отменён."}
        </p>
      ) : null}
    </div>
  );
}

function OccurrenceChip({ occurrence }: { occurrence: CalendarOccurrence }) {
  const { profile } = useSession();
  const taskPath = occurrence.taskId ? taskPathForRole(profile?.role, occurrence.taskId) : null;
  if ("explanation" in occurrence) {
    const preview = occurrence as CalendarPreviewOccurrence;
    return <details className={`rounded-md border px-1.5 py-1 text-[10px] ${preview.deadlinePassed ? "border-amber-400/30 bg-amber-400/10" : "border-sky-400/25 bg-sky-400/10"}`}>
      <summary className="cursor-pointer font-semibold">{preview.operationCode} {preview.operationTitle}</summary>
      <div className="mt-2 space-y-1 text-ink-soft">
        <p>{preview.equipmentName}</p>
        <p>Бригада: {preview.crewSize} чел.</p>
        <p>Допустимое окно: {formatDate(preview.earliestDate)} — {formatDate(preview.mandatoryDueDate)}</p>
        <p>Норма: {preview.rawNormValue ?? "не задана"} · {preview.normUnit === "person_hour" ? "человеко-часы" : preview.normUnit === "elapsed_hour" ? "часы работы бригады" : "единица требует уточнения"}</p>
        <p>Длительность: {preview.planningDurationMinutes === null ? "требует уточнения" : `${preview.planningDurationMinutes} мин.`}</p>
        {preview.isAssumption && <p className="text-amber-200">Демонстрационные данные / допущение</p>}
        <p>{preview.explanation}</p>
      </div>
    </details>;
  }
  const tone = occurrence.isOverdue
    ? "border-rose-400/25 bg-rose-400/10 text-rose-200"
    : occurrence.status === "fulfilled"
      ? "border-accent/25 bg-accent/10 text-accent"
      : "border-sky-400/25 bg-sky-400/10 text-sky-200";

  const content = (
    <span
      className={`block truncate rounded-md border px-1.5 py-1 text-[10px] font-semibold ${tone}`}
      title={`${occurrence.operationCode} ${occurrence.operationTitle} · ${occurrence.equipmentName}`}
    >
      {occurrence.operationCode} {occurrence.operationTitle}
    </span>
  );

  if (taskPath) {
    return (
      <Link
        to={taskPath}
        className="block rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {content}
      </Link>
    );
  }

  return content;
}

function PreviewDiagnostics({preview}: {preview: CalendarPreview}) {
  const labels = {ok: "Рассчитано", needs_input: "Нужны данные", manual_review: "Ручная проверка", skipped: "Не действует"};
  return <Card className="overflow-hidden">
    <div className="border-b border-line p-5">
      <h2 className="font-semibold text-ink">Результат по оборудованию и операциям</h2>
      <p className="mt-1 text-sm text-muted">{preview.timezone} · Для каждой привязки показаны даты, нагрузка или причина отсутствия расчёта.</p>
    </div>
    {preview.diagnostics.length === 0 ? <p className="p-5 text-sm text-muted">Нет привязанных операций для расчёта.</p> : <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="bg-white/[0.03] text-muted"><tr>
          <th className="p-4">Оборудование / операция</th><th className="p-4">Результат</th>
          <th className="p-4">Нагрузка за месяц</th><th className="p-4">Пояснение</th>
        </tr></thead>
        <tbody>{preview.diagnostics.map(item => <tr key={item.bindingId} className="border-t border-line align-top">
          <td className="p-4"><p>{item.equipmentName}</p><p>{item.operationCode} {item.operationTitle}</p>
            <p className="mt-1 text-xs text-muted">{item.isAssumption ? "DEMO / допущение" : "Данные заказчика"}</p></td>
          <td className="p-4"><p>{labels[item.status]}</p><p className="text-xs text-muted">Дат: {item.occurrencesCount}</p></td>
          <td className="p-4"><p>{item.totalPersonHours === null ? "Человеко-часы требуют уточнения" : `${item.totalPersonHours} чел.-ч`}</p>
            <p className="text-xs text-muted">{item.totalPlanningPersonMinutes === null ? "Длительность требует уточнения" : `${item.totalPlanningPersonMinutes} чел.-мин.`}</p></td>
          <td className="min-w-64 p-4"><p>{item.explanation}</p>
            {item.warnings.includes("EQUIPMENT_OUT_OF_SERVICE") && <p className="mt-1 text-amber-200">Оборудование недоступно для работы; возможность исполнения нужно проверить отдельно.</p>}
            {item.warnings.includes("HISTORY_AFTER_CUTOFF_IGNORED") && <p className="mt-1 text-xs text-muted">Более поздние приёмки не использованы в расчёте.</p>}
            {item.nextDueDate && <p className="mt-1 text-xs">Следующий обязательный срок: {formatDate(item.nextDueDate)}</p>}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </Card>;
}
