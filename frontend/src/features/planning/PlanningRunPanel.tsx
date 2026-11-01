import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import type { CalendarPreview, PlanningRun } from "@/shared/types/domain";
import { CrewSelectionPanel } from "@/features/assignment/CrewSelectionPanel";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { Card, CardHeader } from "@/shared/ui/Card";
import { formatDate } from "@/shared/lib/format";

export function PlanningRunPanel({preview, onRecalculate}: {preview: CalendarPreview; onRecalculate: () => void}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PlanningRun | null>(null);
  const [assignmentTask, setAssignmentTask] = useState<string | null>(null);
  const [assigned, setAssigned] = useState<string[]>([]);
  const key = useRef(crypto.randomUUID());
  const saving = useRef(false);
  const active = useRef(true);
  useEffect(() => {active.current=true; return () => {active.current=false;};}, []);
  return <section aria-label="Создание заданий из календаря" className="space-y-4">
    <Card><CardHeader title="Создание заданий" />
      <div className="space-y-3 p-5">
        <p className="text-sm text-muted">Будут сохранены задания по подтверждённым датам, оба прогноза и объяснение решения. Прошедшие сроки и неполные правила требуют проверки. Повторный запуск сохраняет существующие задания.</p>
        <p className="text-sm text-muted">Работники бронируются отдельно — после просмотра состава и подтверждения назначения.</p>
        <Button disabled={busy || !preview.generationToken || !preview.items.length || !!result} onClick={async () => {
          if (saving.current || !preview.generationToken) return;
          saving.current=true; setBusy(true); setError("");
          try {
            const saved=await maintenanceApi.generateTasks(preview.year,preview.month,preview.generationToken,key.current);
            if (active.current) setResult(saved);
          } catch (failure) {
            if (active.current) setError(failure instanceof Error ? failure.message : "Не удалось подтвердить создание заданий. Повторите запрос.");
          } finally {saving.current=false; if (active.current) setBusy(false);}
        }}>{busy ? "Создание заданий…" : "Создать задания по расчёту"}</Button>
        {error && <div role="alert"><Callout tone="danger">{error}<p>При повторной попытке используется тот же ключ запроса.</p></Callout>
          <Button className="mt-3" variant="secondary" onClick={onRecalculate}>Обновить расчёт</Button></div>}
      </div>
    </Card>
    {result && <>
      <Callout tone="success" title="Результат создания заданий">
        Создано: {result.createdCount}. Уже существовало: {result.existingCount}.
        {result.replayed && <p>Восстановлен результат предыдущего запроса.</p>}
      </Callout>
      <div className="space-y-3">{result.items.map(item => <Card key={item.occurrenceId}>
        <CardHeader title={item.operationTitle} description={item.equipmentName} />
        <div className="space-y-3 p-5 text-sm">
          <p>План: {formatDate(item.plannedDate)}. Обязательный срок: {formatDate(item.mandatoryDueDate)}.</p>
          <p>{assigned.includes(item.taskId) ? "Бригада назначена" : item.created ? "Создан черновик задания" : "Сохранено существующее задание"}</p>
          {item.comparison && <><p>Регламент: {formatDate(item.comparison.algorithmic.recommendedDate)} · AI: {formatDate(item.comparison.ai.recommendedDate)}</p>
            <p>{item.comparison.decision.reasons.join(" ")}</p></>}
          {item.assignment && <p>{item.assignment.status === "ok" ? "Предварительно найден полный состав. Доступность проверяется повторно при назначении." : item.assignment.explanation}</p>}
          <div className="flex flex-wrap gap-3">
            <Link className={buttonClassName("secondary")} to={`/tasks/${item.taskId}`}>Открыть задание</Link>
            {item.comparison && <Link className={buttonClassName("secondary")} to={`/comparisons/${item.comparison.runId}`}>Сравнить прогнозы</Link>}
            {(item.state === "draft" || item.state === "assigned") && <Button variant="secondary" onClick={() => setAssignmentTask(item.taskId)}>Подобрать и назначить</Button>}
          </div>
        </div>
      </Card>)}</div>
      {result.warnings.map((warning,index) => <Callout key={`${warning.occurrenceId}:${index}`} tone="warning">{warning.explanation}
        {warning.comparisonRunId && <Link className="ml-2 underline" to={`/comparisons/${warning.comparisonRunId}`}>Посмотреть решение</Link>}</Callout>)}
      {assignmentTask && <CrewSelectionPanel key={assignmentTask} taskId={assignmentTask} onClose={() => setAssignmentTask(null)}
        onAssigned={() => {setAssigned(current => [...current,assignmentTask]); setAssignmentTask(null);}} />}
    </>}
  </section>;
}
