import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { TaskTable } from "@/entities/task/TaskTable";
import { StatCard } from "@/widgets/StatCard";
import { Icon } from "@/shared/ui/Icon";

export function QualityPage() {
  const query = useApiQuery(() => maintenanceApi.listQualityQueue(), []);

  if (query.status === "loading") {
    return <LoadingState label="Загрузка очереди приёмки" />;
  }

  if (query.status === "error") {
    return <ErrorState description={query.error} />;
  }

  const submitted = query.data.filter((task) => task.state === "submitted");
  const rework = query.data.filter((task) => task.state === "rework_required");
  const withAi = query.data.filter((task) => task.activeExecutionId);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Инженер"
        title="Контроль качества и приёмка"
        description="Инженер проверяет отчёт, фотографии и ограничения AI. Модель не принимает работу автоматически."
        actions={
          <>
            <Link to="/tasks" className={buttonClassName("secondary")}>
              Все задания
            </Link>
            <Link to="/comparisons" className={buttonClassName("primary")}>
              Прогнозы
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Ждут приёмки"
          value={submitted.length}
          hint="Отправленные и замороженные попытки"
          tone="warning"
          icon={<Icon name="quality" />}
        />
        <StatCard
          label="На доработке"
          value={rework.length}
          hint="Ожидают исправлений исполнителя"
          tone="danger"
          icon={<Icon name="clock" />}
        />
        <StatCard
          label="С попыткой выполнения"
          value={withAi.length}
          hint="Можно запросить AI-заключение"
          tone="default"
          icon={<Icon name="camera" />}
        />
      </div>

      <div className="rounded-2xl border border-violet-200 bg-violet-50 px-5 py-4 text-sm leading-6 text-violet-900">
        <span className="font-bold">AI не принимает работу.</span> Результат
        <span className="font-mono"> uncertain</span> или
        <span className="font-mono"> unavailable</span> требует текстового
        основания инженера и, при необходимости, дополнительных данных.
      </div>

      {query.data.length === 0 ? (
        <EmptyState
          title="Очередь приёмки пуста"
          description="Новые отчёты появятся после отправки работы исполнителем."
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3 sm:px-6">
            <p className="text-xs font-semibold text-slate-500">
              В очереди: {query.data.length}
            </p>
            <p className="text-xs text-slate-400">
              Отклонение не стирает предыдущую попытку
            </p>
          </div>
          <TaskTable items={query.data} detailBasePath="/quality" />
        </Card>
      )}
    </div>
  );
}
