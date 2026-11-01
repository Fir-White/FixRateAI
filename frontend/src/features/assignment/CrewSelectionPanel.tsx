import { useEffect, useRef, useState } from "react";
import { maintenanceApi } from "@/shared/api/maintenance";
import type { TaskBundle } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import type { AssignmentContext, CrewSelection } from "@/shared/types/domain";
import { Button } from "@/shared/ui/Button";
import { Card, CardHeader } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { ErrorState, LoadingState } from "@/shared/ui/States";

export function CrewSelectionPanel({taskId, onClose, onAssigned, onInvalidated}: {
  taskId: string; onClose: () => void; onAssigned?: (bundle: TaskBundle) => void; onInvalidated?: (message: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [notice, setNotice] = useState("");
  const query = useApiQuery(() => maintenanceApi.assignmentContext(taskId), [taskId, generation]);
  return <section aria-label="Подбор бригады">
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-lg font-semibold">Подбор бригады</h2>
      <Button variant="ghost" size="sm" disabled={saving} onClick={onClose}>Закрыть подбор</Button>
    </div>
    {query.status === "loading" && <LoadingState label="Загрузка условий подбора" />}
    {query.status === "error" && <ErrorState description={query.error} />}
    {notice && <div role="alert"><Callout tone="danger">{notice}</Callout></div>}
    {query.status === "success" && <Picker key={`${taskId}:${query.data.expectedRevision}:${generation}`} context={query.data}
      saving={saving} setSaving={setSaving} onAssigned={onAssigned} onSearch={() => setNotice("")}
      onSaveError={message => {setNotice(message); setGeneration(value => value + 1); onInvalidated?.(message);}} />}
  </section>;
}

function Picker({context, saving, setSaving, onAssigned, onSaveError, onSearch}: {
  context: AssignmentContext; saving: boolean; setSaving: (value: boolean) => void;
  onAssigned?: (bundle: TaskBundle) => void; onSaveError: (message: string) => void; onSearch: () => void;
}) {
  const [start, setStart] = useState(context.defaultStartLocal ?? "");
  const [end, setEnd] = useState(context.defaultEndLocal ?? "");
  const [crew, setCrew] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CrewSelection | null>(null);
  const [saved, setSaved] = useState(false);
  const saveLock = useRef(false);
  const requestId = useRef(0);
  useEffect(() => () => { requestId.current += 1; }, []);
  const invalidate = () => { requestId.current += 1; setResult(null); setError(""); setBusy(false); };
  const showTime = (value: string | null) => value ? new Intl.DateTimeFormat("ru-RU", {
    timeZone: context.timezone, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value)) : "не задано";

  if (context.status !== "ready") return <Callout tone="warning" title="Подбор пока невозможен">{context.explanation}</Callout>;
  if (saved) return <Callout tone="success" title="Бригада назначена">Состав и время сохранены. Доступность и допуски проверены повторно.</Callout>;
  return <div className="space-y-4">
    <Card><CardHeader title="Условия поиска" />
      <form className="space-y-4 p-5" onSubmit={async event => {
        event.preventDefault();
        if (end <= start) { setError("Конец окна должен быть позже начала."); return; }
        const current = ++requestId.current;
        setBusy(true); setError(""); setResult(null); onSearch();
        try {
          const selection = await maintenanceApi.previewAssignment(context.taskId, context.expectedRevision, start, end, crew || null);
          if (requestId.current === current) setResult(selection);
        } catch (failure) {
          if (requestId.current === current) setError(failure instanceof Error ? failure.message : "Подбор недоступен");
        } finally { if (requestId.current === current) setBusy(false); }
      }}>
        <p className="text-sm text-muted">Нужно {context.crewSize} чел. на {context.durationMinutes} мин. · Время объекта: {context.timezone}</p>
        <p className="text-sm text-muted">Допуски: {context.requiredQualifications.length ? context.requiredQualifications.join(" · ") : "дополнительные требования отсутствуют"}</p>
        <p className="text-xs text-muted">Допустимо: {showTime(context.earliestAt)} — {showTime(context.deadlineAt)}. Исходная норма: {context.rawNormValue ?? "не задана"}; длительность подтверждена отдельно.</p>
        {context.dataOrigin === "synthetic_demo" && <p className="text-xs text-amber-200">DEMO: синтетические условия работы и исполнители.</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1 text-sm">Начало окна поиска
            <input aria-label="Начало окна поиска" type="datetime-local" required disabled={saving} value={start} onChange={event => {invalidate(); setStart(event.target.value);}}
              className="w-full rounded-lg border border-line bg-canvas p-3 text-ink" />
          </label>
          <label className="space-y-1 text-sm">Конец окна поиска
            <input aria-label="Конец окна поиска" type="datetime-local" required disabled={saving} value={end} onChange={event => {invalidate(); setEnd(event.target.value);}}
              className="w-full rounded-lg border border-line bg-canvas p-3 text-ink" />
          </label>
        </div>
        <label className="block space-y-1 text-sm">Состав
          <select aria-label="Состав" disabled={saving} value={crew} onChange={event => {invalidate(); setCrew(event.target.value);}}
            className="w-full rounded-lg border border-line bg-canvas p-3 text-ink">
            <option value="">Автоматический подбор работников</option>
            {context.crewChoices.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <Button type="submit" disabled={busy || saving || !start || !end}>{busy ? "Подбор…" : "Найти бригаду"}</Button>
        <p className="text-xs text-muted">Поиск предлагает состав и время. Предложение ещё не сохранено. При подтверждении доступность и допуски проверяются повторно.</p>
      </form>
    </Card>
    {error && <div role="alert"><Callout tone="danger">{error}</Callout></div>}
    {busy && <LoadingState label="Подбор работников и общего интервала" />}
    {result && <>
      <Callout tone={result.status === "ok" ? "info" : "warning"} title={result.status === "ok" ? "Полный состав найден" : "Бригада не подобрана"}>
        <p>{result.explanation}</p>
        {result.status === "ok" && <div className="mt-2 space-y-1">
          <p>{result.crewName ?? "Состав из доступных работников"} · {showTime(result.startAt)} — {showTime(result.endAt)}</p>
          <p>Плановая загрузка: {result.planningPersonMinutes} чел.-мин.</p>
          <ul className="list-inside list-disc">{result.selectedWorkers.map(worker => <li key={worker.executorId}>{worker.name}</li>)}</ul>
        </div>}
      </Callout>
      {result.status === "ok" && result.command && <Button disabled={saving || busy} onClick={async () => {
        if (saveLock.current || !result.command) return;
        saveLock.current = true;
        const current = ++requestId.current;
        setSaving(true); setError("");
        try {
          const bundle = await maintenanceApi.assignCrew(context.taskId, result.command, result.crewId);
          if (requestId.current === current) {setSaved(true); onAssigned?.(bundle);}
        } catch (failure) {
          if (requestId.current === current) {
            setResult(null);
            onSaveError(failure instanceof Error ? failure.message : "Не удалось подтвердить сохранение. Повторите подбор.");
          }
        } finally {saveLock.current = false; setSaving(false);}
      }}>{saving ? "Сохранение…" : "Подтвердить назначение"}</Button>}
      <Card className="overflow-hidden"><CardHeader title="Проверка кандидатов" />
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="text-muted"><tr><th className="p-4">Работник</th><th className="p-4">Результат</th><th className="p-4">Загрузка за день</th><th className="p-4">Причина</th></tr></thead>
          <tbody>{result.workers.map(worker => <tr key={worker.executorId} className="border-t border-line align-top">
            <td className="p-4">{worker.name}</td><td className="p-4">{{selected: "Выбран", available: "Доступен", excluded: "Не подходит"}[worker.status]}</td>
            <td className="p-4">{worker.loadMinutes === null ? "Не определена" : `${worker.loadMinutes} мин.`}</td><td className="min-w-60 p-4">{worker.explanation}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
      {result.crews.length > 0 && <Card><CardHeader title="Проверка бригад" />
        <ul className="divide-y divide-line">{result.crews.map(item => <li key={item.id} className="p-4 text-sm"><p className="font-semibold">{item.name}</p><p className="mt-1 text-muted">{item.explanation}</p></li>)}</ul>
      </Card>}
    </>}
  </div>;
}
