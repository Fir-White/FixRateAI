import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi, type TaskBundle } from "@/shared/api/maintenance";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { EvidenceGallery } from "@/entities/execution/EvidenceGallery";
import { TaskStateBadge, OverdueBadge } from "@/shared/ui/StatusBadge";
import { useSession } from "@/shared/session/SessionContext";

export function ExecutorTaskPage() {
  const { taskId = "" } = useParams();
  const [refresh, setRefresh] = useState(0);
  const query = useApiQuery(() => maintenanceApi.getExecutorTask(taskId), [taskId, refresh]);
  const { profile } = useSession();
  if (query.status === "loading") return <LoadingState label="Загрузка задания" />;
  if (query.status === "error") return <ErrorState description={query.error} />;
  if (!query.data.task.assignees.some(a => a.executorId === profile?.userId)) return <ErrorState title="Задание назначено другому исполнителю" description="Доступ проверяется сервером." />;
  return <ExecutionEditor key={`${query.data.task.revision}`} bundle={query.data} reload={() => setRefresh(n => n+1)} />;
}

function ExecutionEditor({bundle, reload}: {bundle: TaskBundle; reload: () => void}) {
  const {task, execution, decision} = bundle;
  const editable = task.state === "in_progress" && execution?.state === "draft" && !DEMO_MODE;
  const [narrative, setNarrative] = useState(execution?.narrative ?? "");
  const [answers, setAnswers] = useState<Record<string, string | null>>(Object.fromEntries(execution?.checklist.map(i => [i.id, i.answer]) ?? []));
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [itemId, setItemId] = useState(execution?.checklist[0]?.id ?? "");
  const [phase, setPhase] = useState("before");
  const [viewKey, setViewKey] = useState("front");
  const [file, setFile] = useState<File | null>(null);
  const act = async (action: () => Promise<unknown>) => {
    setBusy(true); setNotice("");
    try { await action(); reload(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Ошибка API"); }
    finally { setBusy(false); }
  };
  return <div className="space-y-5">
    <Link to="/executor" className={buttonClassName("secondary")}>Мои задания</Link>
    <div className="flex gap-2"><TaskStateBadge state={task.state} />{task.isOverdue && <OverdueBadge />}</div>
    <h1 className="text-2xl font-semibold">{task.title}</h1>
    <p>{task.equipmentName} · {task.summary}</p>
    <p>Срок: {formatDate(task.mandatoryDueDate)} · Начало: {formatDateTime(task.scheduledStart)}</p>
    {decision && <Callout tone={decision.verdict === "accepted" ? "success" : "warning"}>{decision.reason} · {decision.decidedBy}</Callout>}
    {DEMO_MODE && <Callout tone="warning">Демонстрационные данные. Изменения доступны при подключении к API.</Callout>}
    {notice && <div role="alert"><Callout tone="danger">{notice}</Callout></div>}
    {(task.state === "assigned" || task.state === "rework_required") && <Button disabled={busy || DEMO_MODE} onClick={() => act(() => maintenanceApi.start(task.id, task.revision))}>{task.state === "rework_required" ? "Начать новую попытку" : "Приступить к работе"}</Button>}
    {execution && <>
      <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-lg">Чек-лист · Попытка №{execution.attemptNumber}</h2>
        {execution.checklist.map(item => <label key={item.id} className="block rounded border border-line p-3">
          <span>{item.text}{item.required ? " *" : ""}</span>
          {item.answerKind === "boolean" ? <input className="ml-3" type="checkbox" checked={answers[item.id] === "done"} disabled={!editable || busy} onChange={e => setAnswers({...answers, [item.id]: e.target.checked ? "done" : "not_done"})} />
            : <input className="ml-3 rounded border border-line bg-surface-raised p-2" value={answers[item.id] ?? ""} disabled={!editable || busy} onChange={e => setAnswers({...answers, [item.id]: e.target.value})} />}
          {item.unit && <span> {item.unit}</span>}
          {item.photoRequired && <span className="ml-2 text-xs text-violet-200">Фото до/после обязательно</span>}
        </label>)}
        <label className="block">Комментарий исполнителя<textarea className="mt-2 block w-full rounded border border-line bg-surface-raised p-3" value={narrative} disabled={!editable || busy} onChange={e => setNarrative(e.target.value)} /></label>
        {editable && <Button disabled={busy} onClick={() => act(() => maintenanceApi.saveReport(task.id, task.revision, narrative, answers))}>Сохранить отчёт</Button>}
      </section>
      <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-lg">Фотоотчёт</h2>
        <EvidenceGallery photos={execution.photos} />
        {editable && <fieldset disabled={busy} className="space-y-3">
          <label className="block">Пункт чек-листа<select className="ml-2 bg-surface-raised p-2" value={itemId} onChange={e => setItemId(e.target.value)}>{execution.checklist.map(i => <option key={i.id} value={i.id}>{i.text}</option>)}</select></label>
          <label className="block">Этап<select className="ml-2 bg-surface-raised p-2" value={phase} onChange={e => setPhase(e.target.value)}><option value="before">До</option><option value="after">После</option></select></label>
          <label className="block">Ракурс<input className="ml-2 rounded border border-line bg-surface-raised p-2" value={viewKey} onChange={e => setViewKey(e.target.value)} /></label>
          <label className="block">Файл фото<input className="block" type="file" accept="image/jpeg,image/png,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
          <Button variant="secondary" disabled={!file || !viewKey.trim()} onClick={() => file && act(() => maintenanceApi.upload(task.id, task.revision, itemId, phase, viewKey, file))}>Загрузить фото</Button>
        </fieldset>}
      </section>
      {editable && <><p className="text-xs text-muted">Сначала сохраните ответы. После сдачи попытка замораживается.</p><Button disabled={busy} onClick={() => act(() => maintenanceApi.submit(task.id, task.revision))}>Сдать работу</Button></>}
    </>}
  </div>;
}
