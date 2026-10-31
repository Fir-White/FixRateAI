import { DEMO_MODE } from "@/shared/api/request";
import { useSession } from "@/shared/session/SessionContext";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatMonth } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { IconButton } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { StatCard } from "@/widgets/StatCard";
import { Icon } from "@/shared/ui/Icon";
import type { CalendarOccurrence } from "@/shared/types/domain";
import { taskPathForRole } from "@/shared/lib/roles";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

interface MonthCursor {
  year: number;
  month: number;
}

export function CalendarPage() {
  const { profile } = useSession();
  const today = new Intl.DateTimeFormat("en-CA", {timeZone: profile?.timezone ?? "Asia/Yekaterinburg", year: "numeric", month: "2-digit", day: "2-digit"}).format(new Date());
  const [cursor, setCursor] = useState<MonthCursor>(() => DEMO_MODE ? {year: 2026, month: 10} : {year: Number(today.slice(0,4)), month: Number(today.slice(5,7))});
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
            <IconButton
              label="Предыдущий месяц"
              onClick={() => shiftMonth(-1)}
            >
              <Icon name="back" size={16} />
            </IconButton>
            <span className="min-w-40 text-center text-sm font-semibold text-ink capitalize">
              {formatMonth(cursor.year, cursor.month)}
            </span>
            <IconButton
              label="Следующий месяц"
              onClick={() => shiftMonth(1)}
            >
              <Icon name="chevron" size={16} />
            </IconButton>
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Вхождений" value={occurrencesCount} />
        <StatCard label="Просрочено" value={overdueCount} tone="danger" />
        <StatCard
          label="ТО2 без дат"
          value="Требует уточнения"
          tone="warning"
        />
      </div>

      <Callout tone="warning" title="Набор A — данные заказчика.">
        Календарь показывает сохранённые вхождения. Для неподтверждённых правил не определены basis и
        anchor, поэтому даты квартального и годового ТО не создаются
        автоматически.
      </Callout>

      {query.status === "loading" ? <LoadingState /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}

      {query.status === "success" ? (
        <Card className="overflow-hidden">
          <div
            role="region"
            aria-label="Сетка календаря"
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
                              <p className="px-1 text-[10px] font-semibold text-muted/60">
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
          <div className="flex flex-wrap items-center gap-4 border-t border-line px-5 py-3 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent" />
              Выполнено
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-sky-400" />
              Запланировано
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-rose-400" />
              Просрочено
            </span>
          </div>
        </Card>
      ) : null}

      {query.status === "success" && occurrencesCount === 0 ? (
        <p className="text-center text-sm text-muted">
          Для выбранного месяца вхождений нет. Это не означает, что регламент
          отменён.
        </p>
      ) : null}
    </div>
  );
}

function OccurrenceChip({ occurrence }: { occurrence: CalendarOccurrence }) {
  const { profile } = useSession();
  const taskPath = occurrence.taskId ? taskPathForRole(profile?.role, occurrence.taskId) : null;
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
