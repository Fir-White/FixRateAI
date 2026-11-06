import { PerformanceOverview } from "@/features/analyst/AnalystPanels";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import type { MaintenanceTask } from "@/shared/types/domain";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Button } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { TASK_LABELS } from "@/shared/ui/StatusBadge";
import { TaskTable } from "@/entities/task/TaskTable";

import { csvCell } from "@/shared/lib/exportCsv";
export { csvCell } from "@/shared/lib/exportCsv";

function exportTasks(tasks: MaintenanceTask[]) {
  const rows = [
    ["Код", "Задание", "Оборудование", "Операция", "Статус", "Обязательный срок", "Происхождение"],
    ...tasks.map(task => [task.code, task.title, task.equipmentName, task.operationCode,
      TASK_LABELS[task.state], task.mandatoryDueDate, task.dataOrigin]),
  ];
  const contents = `\ufeff${rows.map(row => row.map(csvCell).join(";")).join("\r\n")}\r\n`;
  const url = URL.createObjectURL(new Blob([contents], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "fixrate-tasks.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ReportsPage() {
  const query = useApiQuery(() => maintenanceApi.listTasks(), []);
  const tasks = query.status === "success" ? query.data : [];
  const metrics = [
    { label: "Всего заданий", value: tasks.length, filter: "all" },
    { label: "Принято", value: tasks.filter(task => task.state === "accepted").length, filter: "accepted" },
    { label: "В работе", value: tasks.filter(task => task.state === "in_progress").length, filter: "in_progress" },
    { label: "На проверке", value: tasks.filter(task => task.state === "submitted").length, filter: "submitted" },
  ];
  const grouped = new Map<string, { code: string; title: string; count: number }>();
  tasks.forEach(task => {
    const key = `${task.operationCode}\u0000${task.title}`;
    const current = grouped.get(key);
    if (current) current.count += 1;
    else grouped.set(key, { code: task.operationCode, title: task.title, count: 1 });
  });
  const operations = [...grouped.values()].sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));
  const maxCount = Math.max(1, ...operations.map(item => item.count));

  return <div className="space-y-6 ops-reports">
    <PageHeader title="Отчёты" description="Сводка по доступным заданиям текущего объекта. Показатели отражают их текущее состояние."
      actions={<Button variant="secondary" disabled={query.status !== "success" || !tasks.length} onClick={() => exportTasks(tasks)}>Выгрузить задания CSV</Button>} />
    {query.status === "loading" && <LoadingState label="Загрузка отчётов" />}
    {query.status === "error" && <ErrorState description={query.error} />}
    {query.status === "success" && <>
      <div className="ops-report-metrics">{metrics.map(item => <Link to={`/tasks?status=${item.filter}`} className="ops-report-metric" key={item.label}><p>{item.label}</p><strong>{String(item.value).padStart(2, "0")}</strong></Link>)}</div>
      <div className="ops-report-split">
        <Card className="p-5 sm:p-6"><h2 className="ops-report-title">Задания по операциям</h2><p className="ops-report-caption">Количество доступных заданий, включая завершённые и отменённые.</p>
          {operations.length ? <ul className="ops-report-bars">{operations.map(item => <li key={`${item.code}:${item.title}`}><div><span>{item.code || "—"} · {item.title}</span><strong>{item.count}</strong></div><div className="ops-report-track"><span style={{ width: `${item.count / maxCount * 100}%` }} /></div></li>)}</ul> : <p className="ops-empty">Пока нет заданий для сводки.</p>}
        </Card>
        <Card className="p-5 sm:p-6"><h2 className="ops-report-title">Срез заданий</h2><p className="ops-report-caption">CSV содержит только доступные текущему пользователю задания и их текущее состояние. Это не отдельный журнал аудита.</p><p className="mt-5 text-xs leading-6 text-muted">Выгрузка доступна сверху страницы. Формат CSV открывается в Excel; значения защищены от интерпретации как формулы.</p></Card>
      </div>
      <section aria-label="Показатели объектов и XLSX"><p className="text-sm text-muted mb-3">Показатели ниже охватывают доступные объекты. Выбранный месяц применяется только к XLSX; CSV выше содержит текущий срез заданий.</p><PerformanceOverview/></section>
      <Card className="overflow-hidden"><div className="border-b border-line px-5 py-4 sm:px-6"><h2 className="ops-report-title">Задания объекта</h2><p className="ops-report-caption">Показаны первые {Math.min(10,tasks.length)} из {tasks.length}. Полный поиск и все записи — в реестре.</p><Link className="fr-text-link" to="/tasks?status=all">Открыть все задания →</Link></div>{tasks.length ? <TaskTable items={tasks.slice(0,10)} /> : <p className="ops-empty">Заданий пока нет.</p>}</Card>
    </>}
  </div>;
}
