import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatMonth } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { Button } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import type { CalendarOccurrence } from "@/shared/types/domain";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

interface MonthCursor {
  year: number;
  month: number;
}

export function CalendarPage() {
  const [cursor, setCursor] = useState<MonthCursor>({ year: 2026, month: 10 });
  const query = useApiQuery(
    () => maintenanceApi.listCalendar(cursor.year, cursor.month),
    [cursor.year, cursor.month],
  );

  const grouped = useMemo(() => {
    const map = new Map<string, CalendarOccurrence[]>();
    if (query.status !== "success") {
      return map;
    }
    query.data.forEach((occurrence) => {
      const bucket = map.get(occurrence.occurrenceDate) ?? [];
      bucket.push(occurrence);
      map.set(occurrence.occurrenceDate, bucket);
    });
    return map;
  }, [query.data, query.status]);

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
  const occurrencesCount = query.status === "success" ? query.data.length : 0;
  const overdueCount =
    query.status === "success"
      ? query.data.filter((item) => item.isOverdue).length
      : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Планирование"
        title="Календарь технического обслуживания"
        description="Проекция строк PlanOccurrence по локальным суткам объекта. Просрочка — отдельный признак, а не статус вхождения."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => shiftMonth(-1)}
              aria-label="Предыдущий месяц"
            >
              <Icon name="back" size={16} />
            </Button>
            <span className="min-w-40 text-center text-sm font-bold text-slate-900 capitalize">
              {formatMonth(cursor.year, cursor.month)}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => shiftMonth(1)}
              aria-label="Следующий месяц"
            >
              <Icon name="chevron" size={16} />
            </Button>
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
          <p className="text-xs font-semibold text-slate-500">Вхождений</p>
          <p className="mt-1 text-2xl font-black text-slate-950">
            {occurrencesCount}
          </p>
        </div>
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4">
          <p className="text-xs font-semibold text-rose-700">Просрочено</p>
          <p className="mt-1 text-2xl font-black text-rose-800">
            {overdueCount}
          </p>
        </div>
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4">
          <p className="text-xs font-semibold text-amber-800">ТО2 без дат</p>
          <p className="mt-1 text-lg font-black text-amber-900">
            Требует уточнения
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-900">
        <span className="font-bold">Набор A — данные заказчика.</span> Октябрь
        2026 выбран для демонстрации. Для ТО2 не подтверждены basis и anchor,
        поэтому даты квартального и годового ТО не создаются автоматически.
      </div>

      {query.status === "loading" ? <LoadingState /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}

      {query.status === "success" ? (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <div className="min-w-[760px]">
              <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50/70">
                {WEEKDAYS.map((weekday) => (
                  <div
                    key={weekday}
                    className="px-2 py-2 text-center text-xs font-bold tracking-wide text-slate-500 uppercase"
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
                  const isToday = dateKey === "2026-10-30";

                  return (
                    <div
                      key={index}
                      className={`min-h-28 border-r border-b border-slate-100 p-2 last:border-r-0 ${
                        validDay ? "bg-white" : "bg-slate-50/40"
                      } ${isToday ? "ring-2 ring-emerald-500 ring-inset" : ""}`}
                    >
                      {validDay ? (
                        <>
                          <div className="flex items-center justify-between">
                            <span
                              className={`text-xs font-bold ${
                                isToday ? "text-emerald-700" : "text-slate-500"
                              }`}
                            >
                              {dayNumber}
                            </span>
                            {dayItems.some((item) => item.isOverdue) ? (
                              <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
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
                              <p className="px-1 text-[10px] font-semibold text-slate-400">
                                +{dayItems.length - 2}
                              </p>
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
          <div className="flex flex-wrap items-center gap-4 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Выполнено
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-sky-500" />
              Запланировано
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              Просрочено
            </span>
          </div>
        </Card>
      ) : null}

      {query.status === "success" && occurrencesCount === 0 ? (
        <p className="text-center text-sm text-slate-500">
          Для выбранного месяца вхождений нет. Это не означает, что регламент
          отменён.
        </p>
      ) : null}
    </div>
  );
}

function OccurrenceChip({ occurrence }: { occurrence: CalendarOccurrence }) {
  const tone = occurrence.isOverdue
    ? "border-rose-200 bg-rose-50 text-rose-800"
    : occurrence.status === "fulfilled"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : "border-sky-200 bg-sky-50 text-sky-800";

  const content = (
    <span
      className={`block truncate rounded-md border px-1.5 py-1 text-[10px] font-semibold ${tone}`}
      title={`${occurrence.operationCode} ${occurrence.operationTitle} · ${occurrence.equipmentName}`}
    >
      {occurrence.operationCode} {occurrence.operationTitle}
    </span>
  );

  if (occurrence.taskId) {
    return <Link to={`/tasks/${occurrence.taskId}`}>{content}</Link>;
  }

  return content;
}
