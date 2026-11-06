import { FieldCaption, Input } from "@/shared/ui/Form";
import { useEffect, useRef, useState } from "react";
import { maintenanceApi } from "@/shared/api/maintenance";
import { ApiError } from "@/shared/api/request";
import type { TaskBundle } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import type { AssignmentContext, CrewSelection } from "@/shared/types/domain";
import { Button } from "@/shared/ui/Button";
import { Card, CardHeader } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import "./assignment.css";

export function CrewSelectionPanel({taskId, taskTitle, equipmentName, onClose, onAssigned, onInvalidated}: {
  taskTitle?: string; equipmentName?: string;
  taskId: string; onClose: () => void; onAssigned?: (bundle: TaskBundle) => void; onInvalidated?: (message: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [notice, setNotice] = useState("");
  const query = useApiQuery(() => maintenanceApi.assignmentContext(taskId), [taskId, generation]);
  return <section aria-label="Подбор бригады" className="fr-assignment">
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-lg font-semibold">Подбор бригады</h2>
      <Button variant="ghost" size="sm" disabled={saving} onClick={onClose}>Закрыть подбор</Button>
    </div>
    {query.status === "loading" && <LoadingState label="Загрузка условий подбора" />}
    {query.status === "error" && <ErrorState description={query.error} action={<Button variant="secondary" onClick={() => setGeneration(value => value + 1)}>Повторить загрузку</Button>} />}
    {notice && <div role="alert"><Callout tone="danger">{notice}</Callout></div>}
    {query.status === "success" && <Picker key={`${taskId}:${query.data.expectedRevision}:${generation}`} context={query.data} taskTitle={taskTitle} equipmentName={equipmentName}
      saving={saving} setSaving={setSaving} onAssigned={onAssigned} onSearch={() => setNotice("")}
      onSaveError={message => {setNotice(message); setGeneration(value => value + 1); onInvalidated?.(message);}} />}
  </section>;
}

function Picker({context, taskTitle, equipmentName, saving, setSaving, onAssigned, onSaveError, onSearch}: {
  taskTitle?: string; equipmentName?: string;
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
  const [picked,setPicked] = useState<string[]>([]);
  const [changed,setChanged] = useState(false);
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
          const selection = crew==='@individual'
            ? await maintenanceApi.previewAssignment(context.taskId,context.expectedRevision,start,end,null,undefined,true)
            : await maintenanceApi.previewAssignment(context.taskId, context.expectedRevision, start, end, crew || null);
          if (requestId.current === current) {setResult(selection);setPicked(selection.selectedWorkers.map(w=>w.executorId));setChanged(false);}
        } catch (failure) {
          if (requestId.current === current) setError(failure instanceof Error ? failure.message : "Подбор недоступен");
        } finally { if (requestId.current === current) setBusy(false); }
      }}>
        <p className="text-sm text-muted">Нужно {context.crewSize} чел. на {context.durationMinutes} мин. · Время объекта: {context.timezone}</p>
        <p className="text-sm text-muted">Допуски: {context.requiredQualifications.length ? context.requiredQualifications.join(" · ") : "дополнительные требования отсутствуют"}</p>
        <p className="text-xs text-muted">Допустимо: {showTime(context.earliestAt)} — {showTime(context.deadlineAt)}. Исходная норма: {context.rawNormValue ?? "не задана"}; длительность подтверждена отдельно.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1 text-sm"><FieldCaption>Начало окна поиска
            </FieldCaption><Input aria-label="Начало окна поиска" type="datetime-local" required disabled={saving} value={start} onChange={event => {invalidate(); setStart(event.target.value);}}
              />
          </label>
          <label className="space-y-1 text-sm"><FieldCaption>Конец окна поиска
            </FieldCaption><Input aria-label="Конец окна поиска" type="datetime-local" required disabled={saving} value={end} onChange={event => {invalidate(); setEnd(event.target.value);}}
              />
          </label>
        </div>
        <label className="block space-y-1 text-sm"><FieldCaption>Состав
          </FieldCaption><select aria-label="Состав" disabled={saving} value={crew} onChange={event => {invalidate(); setCrew(event.target.value);}}
            className="w-full rounded-lg border border-line bg-canvas p-3 text-ink">
            <option value="">Автоматический подбор работников</option>
            <option value="@individual">Работники без постоянной бригады</option>
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
      {changed&&<Callout tone="warning">Состав изменён. Проверьте общий интервал выбранных работников перед подтверждением.</Callout>}
      {!!result.workers.length&&<div className="flex flex-wrap items-center gap-3"><p className="text-sm">Выбрано {picked.length} из {context.crewSize} необходимых работников</p><Button variant="secondary" disabled={saving||busy||picked.length!==context.crewSize} onClick={async()=>{
        const current=++requestId.current;setBusy(true);setError("");
        try{const value=await maintenanceApi.previewAssignment(context.taskId,context.expectedRevision,start,end,crew==='@individual'?null:crew||null,picked,crew==='@individual');
          if(requestId.current===current){setResult(value);setChanged(false);}}
        catch(failure){if(requestId.current===current)setError(failure instanceof Error?failure.message:"Проверка состава недоступна");}
        finally{if(requestId.current===current)setBusy(false);}
      }}>Проверить выбранный состав</Button></div>}
      <Card className="overflow-hidden"><CardHeader title="Проверка кандидатов" />
        <div className="overflow-x-auto"><table className="w-full text-left text-sm" aria-label="Кандидаты для назначения">
          <thead className="text-muted"><tr><th className="p-4">Выбор</th><th className="p-4">Работник</th><th className="p-4">Результат</th><th className="p-4">Загрузка за день</th><th className="p-4">Причина</th></tr></thead>
          <tbody>{result.workers.map(worker => <tr key={worker.executorId} className="border-t border-line align-top">
            <td className="p-4" data-label="Выбор"><input type="checkbox" aria-label={`Выбрать: ${worker.name}`} disabled={saving||busy||worker.status==="excluded"} checked={picked.includes(worker.executorId)} onChange={event=>{
              requestId.current+=1;setChanged(true);setError("");setPicked(event.target.checked?[...picked,worker.executorId]:picked.filter(id=>id!==worker.executorId));
            }}/></td>
            <td className="p-4" data-label="Работник">{worker.name}</td><td className="p-4" data-label="Результат">{{selected: result.recommendationMode==="manual" ? "Выбран" : "Приоритетный", available: "Доступен", excluded: "Не подходит"}[worker.status]}</td>
            <td className="p-4" data-label="Загрузка за день">{worker.loadMinutes === null ? "Не определена" : `${worker.loadMinutes} мин.`}</td><td className="min-w-60 p-4" data-label="Причина">{worker.explanation}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
      {result.crews.length > 0 && <Card><CardHeader title="Проверка бригад" />
        <ul className="divide-y divide-line">{result.crews.map(item => <li key={item.id} className="p-4 text-sm"><p className="font-semibold">{item.name}</p><p className="mt-1 text-muted">{item.explanation}</p></li>)}</ul>
      </Card>}
      {result.status === "ok" && result.command && <div className="fr-assignment-summary" aria-label="Итог назначения">
        <h3 className="font-semibold">Подтверждение назначения</h3>
        <p>{taskTitle ?? "Задание"}{equipmentName ? ` · ${equipmentName}` : ""}</p>
        <p>Плановый интервал: {showTime(result.startAt)} — {showTime(result.endAt)} · {context.timezone}</p>
        <p>Состав: {result.selectedWorkers.map(worker => worker.name).join(", ")}</p>
        <p className="text-sm text-muted">Назначение сохранится после подтверждения. Сервер повторно проверит доступность и допуски.</p>
      </div>}
      {result.status === "ok" && result.command && <Button disabled={saving || busy || changed} onClick={async () => {
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
            if (failure instanceof TypeError || (failure instanceof ApiError && failure.status >= 500)) {
              setError("Сохранение не подтверждено. Параметры поиска сохранены; повторите подбор перед назначением.");
            } else {
              onSaveError(failure instanceof Error ? failure.message : "Не удалось подтвердить сохранение. Повторите подбор.");
            }
          }
        } finally {saveLock.current = false; setSaving(false);}
      }}>{saving ? "Сохранение…" : "Подтвердить назначение"}</Button>}
    </>}
  </div>;
}
