import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { dateDifference, formatDate, formatDays } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import {
  DecisionStatusBadge,
  ForecastStatusBadge,
  OriginBadge,
} from "@/shared/ui/StatusBadge";

export function ComparisonsPage() {
  const query = useApiQuery(() => maintenanceApi.listComparisons(), []);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Прогнозирование"
        title="Сравнение прогнозов"
        description="Оба метода получают один неизменяемый snapshot. Исходные даты сохраняются отдельно, решение оркестратора объясняется."
        actions={
          <Link to="/equipment" className={buttonClassName("secondary")}>
            Оборудование
          </Link>
        }
      />

      {query.status === "loading" ? <LoadingState /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}
      {query.status === "success" && query.data.length === 0 ? (
        <EmptyState
          title="Запусков сравнения нет"
          description="Сравнение создаётся для подтверждённой привязки оборудования и регламента."
        />
      ) : null}

      {query.status === "success" && query.data.length > 0 ? (
        <div className="grid gap-4">
          {query.data.map((run) => {
            const difference =
              run.algorithmic.recommendedDate && run.ai.recommendedDate
                ? dateDifference(
                    run.algorithmic.recommendedDate,
                    run.ai.recommendedDate,
                  )
                : null;

            return (
              <Card key={run.runId} className="p-5 transition hover:border-emerald-200 sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <OriginBadge origin={run.dataOrigin} />
                      <DecisionStatusBadge status={run.decision.status} />
                    </div>
                    <h2 className="mt-3 text-base font-bold text-slate-950">
                      {run.equipmentName}
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      {run.operationTitle} · as_of {formatDate(run.asOf)}
                    </p>
                  </div>
                  <Link
                    to={`/comparisons/${run.runId}`}
                    className={buttonClassName("secondary", "sm")}
                  >
                    Открыть
                    <Icon name="chevron" size={16} />
                  </Link>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  <ForecastMini
                    label="Алгоритмический"
                    date={run.algorithmic.recommendedDate}
                    status={run.algorithmic.status}
                    tone="sky"
                  />
                  <ForecastMini
                    label="AI"
                    date={run.ai.recommendedDate}
                    status={run.ai.status}
                    tone="violet"
                  />
                  <ForecastMini
                    label="Решение"
                    date={run.decision.selectedDate}
                    status={run.decision.status === "selected" ? "ok" : "needs_input"}
                    tone="emerald"
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span className="font-mono">
                    snapshot {run.snapshotHash.slice(0, 12)}…
                  </span>
                  <span>
                    Обязательный срок {formatDate(run.mandatoryDueDate)}
                  </span>
                  {difference !== null ? (
                    <span className="font-semibold text-slate-700">
                      Разница дат: {formatDays(difference)}
                    </span>
                  ) : null}
                </div>
              </Card>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function ForecastMini({
  label,
  date,
  status,
  tone,
}: {
  label: string;
  date: string | null;
  status: "ok" | "needs_input" | "unavailable" | "failed";
  tone: "sky" | "violet" | "emerald";
}) {
  const toneClasses = {
    sky: "bg-sky-50",
    violet: "bg-violet-50",
    emerald: "bg-emerald-50",
  }[tone];

  return (
    <div className={`rounded-xl p-4 ${toneClasses}`}>
      <p className="text-xs font-semibold text-slate-600">{label}</p>
      <p className="mt-1 text-lg font-black text-slate-950">
        {formatDate(date)}
      </p>
      <div className="mt-2">
        {tone === "emerald" ? null : (
          <ForecastStatusBadge status={status} />
        )}
      </div>
    </div>
  );
}
