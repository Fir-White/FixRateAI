import { AttemptHistory, ExecutionProtocol } from "@/features/analyst/AnalystPanels";
import { ChiefActions,ActsPanel } from "@/features/analyst/AnalystPanels";
import { canOperate } from "@/shared/lib/roles";
import { FieldCaption } from "@/shared/ui/Form";
import { useState } from "react";
import { useSession } from "@/shared/session/SessionContext";
import { DEMO_MODE } from "@/shared/api/request";
import { Link, useParams, useNavigate } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { canOpenSection } from "@/shared/lib/roles";
import { formatDate } from "@/shared/lib/format";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { EvidenceComparison } from "@/entities/execution/EvidenceComparison";
import { ChecklistSummary } from "@/entities/execution/ChecklistSummary";
import { Callout } from "@/shared/ui/Callout";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import { CrewSelectionPanel } from "@/features/assignment/CrewSelectionPanel";
import {
  EngineerDecisionBadge,
  OriginBadge,
  OverdueBadge,
  ReviewStatusBadge,
  TaskStateBadge,
} from "@/shared/ui/StatusBadge";

export function TaskDetailPage() {
  const formatDateTime=useSiteDateTime();
  const { taskId = "" } = useParams();
  const navigate = useNavigate();
  const { profile } = useSession();
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCrewSelection, setShowCrewSelection] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [assignedTaskId, setAssignedTaskId] = useState<string | null>(null);
  const [showCancellation,setShowCancellation]=useState(false);
  const [cancelReason,setCancelReason]=useState("");
  const query = useApiQuery(() => maintenanceApi.getTask(taskId), [taskId, refreshToken]);

  if (query.status === "loading") {
    return <LoadingState label="Загрузка задания" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/tasks" className={buttonClassName("secondary")}>
            Вернуться к заданиям
          </Link>
        }
      />
    );
  }

  const { task, execution, review, decision } = query.data;
  const canOpenQuality = canOpenSection(profile?.role, "quality");

  return (
    <div className="space-y-6 task-detail-page">
      <Link
        to="/tasks"
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
      >
        <Icon name="back" size={18} />
        Очередь заданий
      </Link>

      <PageHeader
        title={task.title}
        description={`${task.code} · ${task.summary}`}
        actions={
          <>
            {!DEMO_MODE && query.data.allowedActions?.includes("forecast") && <Button variant="secondary" disabled={busy} onClick={async () => {
              setBusy(true); setNotice("");
              try { const result = await maintenanceApi.forecast(task.id, task.revision); navigate(`/comparisons/${result.run.runId}`); }
              catch (error) { setNotice(error instanceof Error ? error.message : "Ошибка прогноза"); }
              finally { setBusy(false); }
            }}>Сравнить прогнозы</Button>}
            {task.state === "submitted" && canOpenQuality ? (
              <Link
                to={`/quality/${task.id}`}
                className={buttonClassName("primary")}
              >
                Перейти к приёмке
              </Link>
            ) : null}
            {(["draft","assigned","in_progress","rework_required"].includes(task.state)) && canOperate(profile?.role) ? (
              <Button disabled={DEMO_MODE||busy||!task.equipmentId} aria-describedby={!task.equipmentId ? "assignment-blocker" : undefined} title={DEMO_MODE ? "Нужно подключение к серверу" : undefined} onClick={() => setShowCrewSelection(true)}>
                Подобрать бригаду
              </Button>
            ) : null}
            {!DEMO_MODE&&query.data.allowedActions?.includes('cancel')&&<Button variant="ghost" disabled={busy} onClick={()=>setShowCancellation(value=>!value)}>Отменить задание</Button>}
            {task.state === "in_progress" ? (
              <Button variant="secondary" disabled>
                Работа выполняется
              </Button>
            ) : null}
          </>
        }
      />

      {!task.equipmentId && canOperate(profile?.role) && ["draft","assigned","in_progress","rework_required"].includes(task.state) &&
        <div id="assignment-blocker"><Callout tone="warning" title="Подбор бригады недоступен">
          Задание не связано с оборудованием. Сначала уточните связь у ответственного за регламент.
        </Callout></div>}
      {DEMO_MODE && <Callout tone="neutral">DEMO · Данные для просмотра. Назначение, расчёт и отмена требуют подключения к API.</Callout>}
      {notice && <div role="alert"><Callout tone="danger">{notice}</Callout></div>}
      {showCancellation&&query.data.allowedActions?.includes('cancel')&&<Card className="space-y-3 p-5"><h2 className="font-semibold">Отмена задания до начала выполнения</h2><p className="text-sm text-muted">Назначения освободятся. Задание и история сохранятся.</p><label className="block text-sm"><FieldCaption>Причина отмены</FieldCaption><textarea aria-label="Причина отмены" disabled={busy} className="mt-1 w-full rounded-lg border border-line bg-canvas p-3" value={cancelReason} onChange={e=>setCancelReason(e.target.value)}/></label><Button variant="secondary" disabled={busy||!cancelReason.trim()} onClick={async()=>{
        setBusy(true);setNotice("");try{await maintenanceApi.cancel(task.id,task.revision,cancelReason.trim());setShowCancellation(false);setShowCrewSelection(false);setRefreshToken(value=>value+1);}catch(failure){setNotice(failure instanceof Error?failure.message:"Отмена не выполнена");setRefreshToken(value=>value+1);}finally{setBusy(false);}
      }}>Подтвердить отмену задания</Button></Card>}
      {assignedTaskId === task.id && <Callout tone="success" title="Бригада назначена">Состав и время сохранены.</Callout>}
      {showCrewSelection && canOperate(profile?.role) && !DEMO_MODE &&
        (["draft","assigned","in_progress","rework_required"].includes(task.state)) &&
        <CrewSelectionPanel key={task.id} taskId={task.id} taskTitle={task.title} equipmentName={task.equipmentName} onClose={() => setShowCrewSelection(false)} onAssigned={() => {
          setShowCrewSelection(false); setAssignedTaskId(task.id); setNotice(""); setRefreshToken(value => value + 1);
        }} onInvalidated={message => {setNotice(message); setRefreshToken(value => value + 1);}} />}
      <div className="flex flex-wrap items-center gap-2">
        <TaskStateBadge state={task.state} />
        {task.isOverdue ? <OverdueBadge /> : null}
        <OriginBadge origin={task.dataOrigin} />
        <span className="text-xs text-muted">Ревизия {task.revision}</span>
      </div>

      {task.isOverdue ? (
        <Callout tone="danger" title="Просрочено.">
          Обязательный срок прошёл. Задание сохраняет текущий статус;
          работа требует внимания диспетчера и инженера.
        </Callout>
      ) : null}

      {decision && <Card><CardHeader title="Решение инженера"/><div className="p-5">
        <EngineerDecisionBadge verdict={decision.verdict}/><p className="mt-3 whitespace-pre-wrap">{decision.reason}</p>
        <p className="mt-2 text-sm text-muted">{decision.decidedBy} · {formatDateTime(decision.decidedAt)}</p>
      </div></Card>}
      <ChiefActions task={task} onSaved={()=>window.location.reload()}/>
      <div className="fr-work-grid">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Параметры задания" />
            <InfoList className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 sm:p-6">
              <InfoItem label="Оборудование" value={task.equipmentName} />
              <InfoItem
                label="Операция"
                value={`${task.maintenanceType} · ${task.operationCode}`}
              />
              <InfoItem
                label="Обязательный срок"
                value={formatDate(task.mandatoryDueDate)}
              />
              <InfoItem
                label="Планируемый интервал"
                value={`${formatDateTime(task.scheduledStart)} — ${formatDateTime(task.scheduledEnd)}`}
              />
              <InfoItem label="Размер бригады" value={`${task.crewSize} чел.`} />
              <InfoItem
                label="Приёмка после срока"
                value={task.deadlineBreached ? "Зафиксирована" : "Не зафиксирована"}
              />
            </InfoList>
          </Card>

          {execution ? (
            <Card>
              <CardHeader
                title={`Попытка №${execution.attemptNumber}`}
                description={
                  execution.state === "draft" ? "Черновик отчёта исполнителя" : "Сохранённый результат попытки"
                }
                action={
                  canOpenQuality ? <Link
                    to={`/quality/${task.id}`}
                    className="text-sm font-semibold text-accent"
                  >
                    Фото и проверка
                  </Link> : null
                }
              />
              <div className="p-5 sm:p-6">
                <p className="text-sm leading-6 text-ink-soft">
                  {execution.narrative || "Комментарий пока не заполнен."}
                </p>
                <div className="mt-4">
                  <ChecklistSummary items={execution.checklist} />
                </div>
                <div className="mt-5">
                  <ExecutionProtocol task={task} execution={execution} disabled readOnly value={{actual:execution.actual?{started_at:execution.actual.started_at??"",performed_at:execution.actual.performed_at??"",person_hours:execution.actual.person_hours??""}:null,readings:execution.readings??[]}} onChange={()=>{}}/>
                  <ActsPanel task={task} execution={execution} editable={false} onSaved={()=>window.location.reload()}/>
                  <EvidenceComparison photos={execution.photos} checklist={execution.checklist}/>
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Бригада" />
            {task.assignees.length ? (
              <ul className="divide-y divide-line">
                {task.assignees.map((assignee) => (
                  <li key={assignee.executorId} className="px-5 py-4 sm:px-6">
                    <p className="font-semibold text-ink">
                      {assignee.name}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {assignee.qualifications.join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-6 text-sm text-muted">
                Исполнитель не назначен.
              </p>
            )}
          </Card>

          {review ? (
            <Card>
              <CardHeader title="AI-контроль" />
              <div className="p-5 sm:p-6">
                <ReviewStatusBadge status={review.status} />
                <p className="mt-3 text-sm leading-6 text-ink-soft">
                  Модель {review.modelRef}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Prompt set {review.promptSetVersion}
                </p>
                {canOpenQuality && <Link
                  to={`/quality/${task.id}`}
                  className={buttonClassName("secondary", "sm", "mt-4 w-full")}
                >
                  Открыть заключение
                </Link>}
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Переходы" />
            <div className="p-5 text-xs leading-5 text-muted sm:p-6">
              {task.state === "draft"
                ? "Черновик → Назначено: требуется доступная бригада и подтверждённая длительность."
                : null}
              {task.state === "assigned"
                ? "Назначено → В работе: доступно назначенному исполнителю."
                : null}
              {task.state === "in_progress"
                ? "В работе → На проверке: отправка замораживает текущую попытку."
                : null}
              {task.state === "submitted"
                ? "На проверке → Принято или На доработке: решение принимает инженер."
                : null}
              {task.state === "rework_required"
                ? "На доработке → В работе: создаётся новая попытка, старая не меняется."
                : null}
              {task.state === "accepted"
                ? "Принято: задание закрыто, принятый факт добавлен в историю оборудования."
                : null}
            </div>
          </Card>
        </div>
      </div>
      <AttemptHistory taskId={task.id}/>
    </div>
  );
}
