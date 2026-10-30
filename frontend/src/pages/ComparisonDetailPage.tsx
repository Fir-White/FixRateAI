import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { dateDifference, formatDate, formatDays } from "@/shared/lib/format";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
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
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
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
        <span className="text-xs text-muted">
          Политика {run.decision.policyVersion}
        </span>
      </div>

      <Card>
        <CardHeader
          title="Входной снимок"
          description="Оба метода обязаны использовать одинаковые даты, версии и hash"
        />
        <InfoList className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-4">
          <InfoItem label="as_of" value={formatDate(run.asOf)} />
          <InfoItem label="Горизонт" value={formatDate(run.horizonEnd)} />
          <InfoItem
            label="Ранняя граница"
            value={formatDate(run.earliestDate)}
          />
          <InfoItem
            label="Обязательный срок"
            value={formatDate(run.mandatoryDueDate)}
          />
        </InfoList>
        <div className="border-t border-line px-5 py-4 sm:px-6">
          <p className="text-xs font-semibold text-muted">Snapshot hash</p>
          <p className="mt-1 font-mono text-xs break-all text-ink-soft">
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
              <p className="text-2xl font-semibold text-ink">
                {formatDate(run.decision.selectedDate)}
              </p>
            </div>
            <ul className="mt-4 space-y-3">
              {run.decision.reasons.map((reason) => (
                <li
                  key={reason}
                  className="flex gap-3 text-sm leading-6 text-ink-soft"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
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
            <p className="text-3xl font-semibold text-ink">
              {difference === null
                ? "Не определена"
                : formatDays(difference)}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted">
              Исходные даты обоих методов сохраняются. Ограничение обязательным
              сроком не переписывает AI-результат.
            </p>
            <Callout tone="neutral" className="mt-4 text-xs leading-5">
              Обязательный срок: {formatDate(run.mandatoryDueDate)}. Дата AI не
              может изменить нормативную границу.
            </Callout>
          </div>
        </Card>
      </div>
    </div>
  );
}
