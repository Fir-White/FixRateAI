import { AttemptHistory } from "@/features/analyst/AnalystPanels";
import { ChiefActions,ActsPanel,ExecutionProtocol } from "@/features/analyst/AnalystPanels";
import { AiModelSelector } from "@/features/ai/AiModelSelector";
import { getStoredAiSettings } from "@/features/ai/aiSettings";
import { DEMO_MODE } from "@/shared/api/request";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { AnalysisTimerBadge, PhotoReviewCard } from "@/entities/execution/PhotoReviewCard";
import { EvidenceComparison } from "@/entities/execution/EvidenceComparison";
import { ChecklistSummary } from "@/entities/execution/ChecklistSummary";
import { Callout } from "@/shared/ui/Callout";
import { FormField, Textarea } from "@/shared/ui/Form";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import { Modal } from "@/shared/ui/Modal";
import {
  EngineerDecisionBadge,
  OriginBadge,
  OverdueBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";

import { attemptStateSummary } from "@/shared/lib/presentation";
import "./quality-redesign.css";

export function QualityTaskPage() {
  const formatDateTime=useSiteDateTime();
  const { taskId = "" } = useParams();
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [lastMeasured, setLastMeasured] = useState<{ reviewId: string; elapsedMs: number } | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<
    "accepted" | "rejected" | null
  >(null);
  const query = useApiQuery(
    () => maintenanceApi.getQualityBundle(taskId),
    [taskId, refresh],
    bundle => !DEMO_MODE && bundle.photoAnalysisStatus === "pending",
  );
  const executionId = query.data?.execution?.id;
  const decisionContext = useRef("");
  useEffect(() => {
    if (!executionId || decisionContext.current === `${taskId}:${executionId}`) return;
    decisionContext.current = `${taskId}:${executionId}`;
    setReason("");
    setPendingDecision(null);
    setNotice(null);
    setLastMeasured(null);
  }, [taskId, executionId]);

  if (query.status === "loading") {
    return <LoadingState label="Загрузка отчёта на приёмку" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/quality" className={buttonClassName("secondary")}>
            Вернуться в очередь
          </Link>
        }
      />
    );
  }

  const { task, execution, review, decision } = query.data;
  const hasDocuments = !!task.requiredActs?.length || !!execution?.acts?.length;
  const canReview = !DEMO_MODE && !!query.data.allowedActions?.includes("review");
  const canAnalyze = !DEMO_MODE && !!query.data.allowedActions?.includes("photo_review");

  const handleDecision = async (verdict: "accepted" | "rejected") => {
    setPendingDecision(null);
    if (DEMO_MODE) { setNotice("Деморежим: запрос не отправлен."); return; }
    if (!execution) return;
    setBusy(true); setNotice(null);
    try { await maintenanceApi.review(task.id, task.revision, execution.id, verdict, reason,{reviewed_ai_result_id:review?.id,additional_evidence_refs:execution.acts?.filter(a=>a.verified).map(a=>a.id)??[]}); setRefresh(n => n+1); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Ошибка API"); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <Link
        to="/quality"
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
      >
        <Icon name="back" size={18} />
        Контроль качества
      </Link>

      <PageHeader
        title={task.title}
        description={`${task.code} · ${task.equipmentName} · ${task.summary}`}
        actions={
          <Link to={`/tasks/${task.id}`} className={buttonClassName("secondary")}>
            Карточка задания
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <TaskStateBadge state={task.state} />
        {task.isOverdue ? <OverdueBadge /> : null}
        <OriginBadge origin={task.dataOrigin} />
        <span className="text-xs text-muted">
          Попытка №{execution?.attemptNumber ?? "—"}
        </span>
      </div>

      {decision ? (
        <Card>
          <CardHeader title="Предыдущее решение" />
          <div className="p-5 sm:p-6">
            <EngineerDecisionBadge verdict={decision.verdict} />
            <p className="mt-2 text-sm leading-6 text-ink-soft">{decision.reason}</p>
            <p className="mt-2 text-xs text-muted">{decision.decidedBy} · {formatDateTime(decision.decidedAt)}</p>
          </div>
        </Card>
      ) : null}

      <p className="text-sm text-muted">{attemptStateSummary(task.state)}</p>
      {canReview && <a className="fr-decision-shortcut" href="#review-decision">Перейти к основанию решения</a>}
      {notice && !canReview && <div role="alert"><Callout tone="danger" className="text-xs">{notice}</Callout></div>}
      {query.data.photoAnalysisStatus === "pending" && <Callout tone="neutral"><div className="flex flex-wrap items-center justify-between gap-2"><p role="status">Фотографии анализируются автоматически. Результат появится здесь без обновления страницы; запуск инженером не требуется.</p><AnalysisTimerBadge active /></div></Callout>}
      {canAnalyze && query.data.photoAnalysisStatus !== "pending" && (!review || ["failed","unavailable"].includes(review.status)) && <div className="space-y-4 rounded-xl border border-line p-4">
        <AiModelSelector variant="compact" />
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" disabled={busy} onClick={async () => {
            const startedAt = performance.now();
            setBusy(true); setAnalyzing(true); setNotice(null);
            try {
              const aiOpts = getStoredAiSettings();
              const res = await maintenanceApi.photoReview(task.id, task.revision, false, {
                provider: aiOpts.provider,
                model: aiOpts.model,
                api_key: aiOpts.apiKey,
              });
              setLastMeasured({ reviewId: res.id, elapsedMs: res.elapsedMs ?? Math.round(performance.now() - startedAt) });
              setRefresh(n => n+1);
            }
            catch (error) { setNotice(error instanceof Error ? error.message : "Ошибка анализа"); }
            finally { setBusy(false); setAnalyzing(false); }
          }}>{analyzing?"Фотографии анализируются…":review?"Повторить анализ":"Анализировать фото"}</Button>
          <AnalysisTimerBadge active={analyzing} />
          {analyzing&&<p role="status" className="text-sm leading-6 text-muted">Модель сравнивает фотографии с заданием. Дождитесь результата; повторно нажимать кнопку не нужно.</p>}
        </div>
      </div>}
      {DEMO_MODE && <Callout tone="neutral">DEMO · Фото и решения показаны из примера. Анализ и приёмка доступны только при подключении к API.</Callout>}
      <div className="quality-detail-grid fr-work-grid">
        <div className="space-y-6">
          {hasDocuments && <div id="review-documents"><ActsPanel task={task} execution={execution} editable={false} onSaved={()=>setRefresh(n=>n+1)}/></div>}
          {execution&&<ExecutionProtocol task={task} execution={execution} value={{actual:execution.actual?{started_at:execution.actual.started_at??"",performed_at:execution.actual.performed_at??"",person_hours:execution.actual.person_hours??""}:null,readings:execution.readings??[]}} onChange={()=>{}} disabled readOnly/>}
          <Card>
            <CardHeader
              title="Отчёт исполнителя"
              description={
                execution?.submittedAt
                  ? `Отправлен ${formatDateTime(execution.submittedAt)}`
                  : "Отчёт ещё не отправлен"
              }
            />
            <div className="p-5 sm:p-6">
              <p className="text-sm leading-6 text-ink-soft">
                {execution?.narrative || "Комментарий отсутствует."}
              </p>
              {execution?.checklist.length ? (
                <div className="mt-4">
                  <ChecklistSummary
                    items={execution.checklist}
                    mode="quality"
                  />
                </div>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="До / после"
              description="Сравнение по пункту чек-листа и одинаковому ракурсу"
            />
            <div className="p-5 sm:p-6">
              <EvidenceComparison photos={execution?.photos ?? []} checklist={execution?.checklist ?? []} />
            </div>
          </Card>

          {query.data.photoAnalysisStatus !== "pending" && <PhotoReviewCard review={review} formatDateTime={formatDateTime} fallbackElapsedMs={lastMeasured && review?.id === lastMeasured.reviewId ? lastMeasured.elapsedMs : null}/>}
        </div>

        <div id="review-decision" className="space-y-6 quality-decision-rail">
          {canReview&&<Card>
            <CardHeader title="Основание решения" />
            <div className="p-5 sm:p-6">
              <InfoList className="grid grid-cols-2 gap-4">
                <InfoItem
                  label="Обязательный срок"
                  value={formatDate(task.mandatoryDueDate)}
                />
                <InfoItem label="Ревизия" value={String(task.revision)} />
              </InfoList>
              <p className="mt-4 text-xs leading-5 text-muted">
                Причина обязательна и при приёмке, и при отклонении. Для
                неуверенного AI-результата она служит основанием ручной оценки.
              </p>

              <div className="fr-decision-facts"><p>Фото этой попытки: {execution?.photos.length??0}.{hasDocuments && <> <a href="#review-documents">Документы и проверки</a></>}</p>{task.requiredActs?.map(kind=><p key={kind}>{kind}: {execution?.acts?.some(a=>a.kind===kind&&a.verified)?"проверен":execution?.acts?.some(a=>a.kind===kind)?"ожидает проверки":"не приложен"}</p>)}<p>AI не принимает работу. Скрытые операции и точность прибора требуют ручной проверки.</p>{review?.limitations.map(text=><p key={text}>{text}</p>)}</div>
              <FormField
                label="Причина решения"
                htmlFor="quality-reason"
                hint="Ваше основание будет сохранено вместе с решением."
                required
                className="mt-4"
              >
                <Textarea
                  id="quality-reason"
                  disabled={!canReview || busy}
                  value={reason}
                  onChange={(event) => {
                    setReason(event.target.value);
                    setNotice(null);
                  }}
                  rows={4}
                  placeholder="Опишите, что проверено и на каком основании"
                />
              </FormField>

              {notice ? (
                <div role="alert"><Callout tone="danger" className="mt-3 text-xs">{notice}</Callout></div>
              ) : null}

              <div className="mt-4 grid gap-2">
                <Button
                  disabled={!reason.trim() || busy || !canReview}
                  onClick={() => setPendingDecision("accepted")}
                >
                  <Icon name="check" size={18} />
                  Принять работу
                </Button>
                <Button
                  variant="danger"
                  disabled={!reason.trim() || busy || !canReview}
                  onClick={() => setPendingDecision("rejected")}
                >
                  <Icon name="alert" size={18} />
                  Вернуть на доработку
                </Button>
              </div>
            </div>
          </Card>}
          {!DEMO_MODE && task.state === "submitted" && !canReview && <Callout tone="warning" className="mt-3 text-xs">Собственную работу должен проверить другой инженер.</Callout>}

          <Callout tone="neutral" className="text-xs leading-5">
            Решение и доказательства этой попытки сохраняются в истории задания.
          </Callout>
        </div>
      </div>
      <ChiefActions task={task} onSaved={()=>setRefresh(n=>n+1)}/>
      <AttemptHistory taskId={task.id}/>
      <Modal
        open={pendingDecision !== null}
        title={
          pendingDecision === "rejected"
            ? "Вернуть работу на доработку?"
            : "Принять работу?"
        }
        description={
          pendingDecision === "rejected"
            ? "Отклонение сохранит текущую попытку в истории. Исполнитель начнёт новую попытку отдельно."
            : "Принятие закроет задание и добавит событие в историю оборудования."
        }
        tone={pendingDecision === "rejected" ? "danger" : "default"}
        onClose={() => setPendingDecision(null)}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setPendingDecision(null)}
            >
              Отмена
            </Button>
            <Button
              variant={pendingDecision === "rejected" ? "danger" : "primary"}
              onClick={() =>
                pendingDecision ? handleDecision(pendingDecision) : undefined
              }
            >
              {pendingDecision === "rejected"
                ? "Вернуть на доработку"
                : "Подтвердить приёмку"}
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-ink-soft">{reason}</p>
        <p className="mt-3 text-xs text-muted">
          {task.title} · Попытка №{execution?.attemptNumber}. Проверьте фотографии, показания и заключение AI. Обязательные документы: {task.requiredActs?.join(", ")||"не предусмотрены регламентом"}.
        </p>
      </Modal>

    </div>
  );
}
