import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { dateDifference, formatDate, formatDays } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { ForecastResultCard } from "@/entities/forecast/ForecastResultCard";
import {
  DecisionStatusBadge,
  OriginBadge,
} from "@/shared/ui/StatusBadge";

export function ComparisonDetailPage() {
  const { runId = "" } = useParams();
  const query = useApiQuery(() => maintenanceApi.getComparison(runId), [runId]);

  if (query.status === "loading") {
    return <LoadingState label="Загрузка результата сравнения" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/comparisons" className={buttonClassName("secondary")}>
            Вернуться к сравнениям
          </Link>
        }
      />
    );
  }

  const { run } = query.data;
  const difference =
    run.algorithmic.recommendedDate && run.ai.recommendedDate
      ? dateDifference(run.algorithmic.recommendedDate, run.ai.recommendedDate)
      : null;

  return (
    <div className="space-y-6">
      <Link
        to="/comparisons"
        className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
      >
        <Icon name="back" size={18} />
        Сравнение прогнозов
      </Link>

      <PageHeader
        eyebrow="Один snapshot · два метода"
        title={run.equipmentName}
        description={run.operationTitle}
        actions={
          <Link
            to={`/equipment/${run.equipmentId}`}
            className={buttonClassName("secondary")}
          >
            Карточка оборудования
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <OriginBadge origin={run.dataOrigin} />
        <DecisionStatusBadge status={run.decision.status} />
        <span className="text-xs text-slate-500">
          Политика {run.decision.policyVersion}
        </span>
      </div>

      <Card>
        <CardHeader
          title="Входной снимок"
          description="Оба метода обязаны использовать одинаковые даты, версии и hash"
        />
        <dl className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 lg:grid-cols-4 sm:p-6">
          <Info label="as_of" value={formatDate(run.asOf)} />
          <Info label="Горизонт" value={formatDate(run.horizonEnd)} />
          <Info label="Ранняя граница" value={formatDate(run.earliestDate)} />
          <Info
            label="Обязательный срок"
            value={formatDate(run.mandatoryDueDate)}
          />
        </dl>
        <div className="border-t border-slate-100 px-5 py-4 sm:px-6">
          <p className="text-xs font-semibold text-slate-500">Snapshot hash</p>
          <p className="mt-1 font-mono text-xs break-all text-slate-700">
            {run.snapshotHash}
          </p>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <ForecastResultCard result={run.algorithmic} accent="algorithmic" />
        <ForecastResultCard result={run.ai} accent="ai" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader
            title="Решение оркестратора"
            description="Рекомендация не создаёт задание автоматически"
          />
          <div className="p-5 sm:p-6">
            <div className="flex flex-wrap items-center gap-3">
              <DecisionStatusBadge status={run.decision.status} />
              <p className="text-2xl font-black text-slate-950">
                {formatDate(run.decision.selectedDate)}
              </p>
            </div>
            <ul className="mt-4 space-y-3">
              {run.decision.reasons.map((reason) => (
                <li
                  key={reason}
                  className="flex gap-3 text-sm leading-6 text-slate-600"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
                    <Icon name="check" size={13} />
                  </span>
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card>
          <CardHeader title="Разница методов" />
          <div className="p-5 sm:p-6">
            <p className="text-3xl font-black text-slate-950">
              {difference === null
                ? "Не определена"
                : formatDays(difference)}
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Исходные даты обоих методов сохраняются. Ограничение обязательным
              сроком не переписывает AI-результат.
            </p>
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600">
              Обязательный срок: {formatDate(run.mandatoryDueDate)}. Дата AI не
              может изменить нормативную границу.
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
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
