import { EquipmentOperations,IncidentWorkspace } from "@/features/analyst/AnalystPanels";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import { Icon } from "@/shared/ui/Icon";
import { useSession } from "@/shared/session/SessionContext";
import { Disclosure } from "@/shared/ui/Disclosure";
import { canOpenSection } from "@/shared/lib/roles";
import { DEMO_MODE } from "@/shared/api/request";
import { ComponentPanel } from "@/features/equipment/ComponentPanel";
import { JourneySteps, type JourneyStep } from "@/shared/ui/JourneySteps";
import {
  EquipmentStateBadge,
  OriginBadge,
} from "@/shared/ui/StatusBadge";

export function EquipmentDetailPage() {
  const formatDateTime=useSiteDateTime();
  const { profile } = useSession();
  const canCompare = canOpenSection(profile?.role, "comparisons");
  const tasksPath = profile?.role === "executor" ? "/executor" : canOpenSection(profile?.role, "tasks") ? "/tasks" : null;
  const { equipmentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const query = useApiQuery(
    () => maintenanceApi.getEquipment(equipmentId),
    [equipmentId],
    undefined,
    `equipment-detail:${equipmentId}`,
  );

  if (query.status === "loading") {
    return <LoadingState label="Загрузка карточки оборудования" />;
  }

  if (query.status === "error") {
    return (
      <ErrorState
        description={query.error}
        action={
          <Link to="/equipment" className={buttonClassName("secondary")}>
            Вернуться в реестр
          </Link>
        }
      />
    );
  }

  const { equipment, history } = query.data;
  const executor = profile?.role === "executor";
  const passport = <Card>
    <CardHeader title="Паспорт оборудования" />
    <InfoList className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 sm:p-6">
      <InfoItem label="Тип" value={equipment.equipmentType} />
      <InfoItem label="Инвентарный номер" value={equipment.inventoryCode} mono/>
      <InfoItem label="Расположение" value={equipment.location} />
      <InfoItem label="Ввод в эксплуатацию" value={formatDate(equipment.commissionedOn)} />
      <InfoItem label="Последнее принятое ТО" value={formatDateTime(equipment.lastServiceAt)} />
      <InfoItem label="Следующий срок" value={formatDate(equipment.nextDueDate)} />
    </InfoList>
  </Card>;
  const historyPanel = <Card>
    <CardHeader title="Принятая история" description="Решения и даты по принятым работам."/>
    {history.length ? <ol className="divide-y divide-line">
      {history.map(event=><li key={event.id} className="flex gap-4 px-5 py-4 sm:px-6">
        <Icon name="check" size={16} className="mt-1 shrink-0 text-accent"/>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">{event.operation}</p>
          <p className="mt-1 text-sm text-muted">{event.taskCode} · проверил {event.engineer} · Выполнено {formatDateTime(event.performedAt)}</p>
          <p className="mt-1 text-sm text-muted">Принято {formatDateTime(event.acceptedAt)}
            {event.runtimeHours !== null ? ` · наработка ${event.runtimeHours} ч` : ""}
          </p>
        </div>
      </li>)}
    </ol> : <p className="px-5 py-8 text-sm text-muted">Принятых событий обслуживания ещё нет.</p>}
  </Card>;
  const steps: JourneyStep[] = [
    {id:"service",title:"Обслуживание",content:()=><div className="fr-work-grid">
      <div className="space-y-5">
        <Card className="p-5"><h2 className="font-semibold">Ближайшее обслуживание</h2><p className="mt-2 text-muted">{formatDate(equipment.nextDueDate)}</p>
          {equipment.activeOperation&&<p className="mt-2">{equipment.activeOperation}</p>}
        </Card>
        <EquipmentOperations equipmentId={equipmentId}/>
      </div>
      {passport}
    </div>},
    {id:"passport",title:"Паспорт",content:()=>passport},
    {id:"history",title:"История",content:()=>historyPanel},
    ...(!DEMO_MODE ? [{id:"components",title:"Детали",content:()=><ComponentPanel equipmentId={equipmentId}/>}]:[]),
  ];

  return (
    <div className="space-y-6">
      <Link
        to="/equipment"
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink"
      >
        <Icon name="back" size={18} />
        Реестр оборудования
      </Link>

      <PageHeader
        title={equipment.name}
        description={`${equipment.equipmentType} · ${equipment.location}`}
        actions={
          <>
            {canCompare && <Link
              to={`/comparisons?equipment=${encodeURIComponent(equipmentId)}`}
              className={buttonClassName("secondary")}
            >
              Сравнить прогнозы
            </Link>}
            {tasksPath && <Link to={`${tasksPath}?equipment=${encodeURIComponent(equipmentId)}`} className={buttonClassName("primary")}>
              {profile?.role === "executor" ? "Мои задания" : "Очередь заданий"}
            </Link>}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <EquipmentStateBadge state={equipment.state} />
        <OriginBadge origin={equipment.dataOrigin} />
        <span className="text-xs text-muted">
          Ревизия {equipment.revision} · {equipment.siteName}
        </span>
      </div>

      <JourneySteps key={equipmentId} label="Карточка оборудования" steps={steps} numbered={false}
        value={params.get("view")??(executor?"passport":"service")}
        onChange={view=>setParams(previous=>{const next=new URLSearchParams(previous);next.set("view",view);return next;})}/>
      <Disclosure title="Дефекты и обращения по оборудованию"><IncidentWorkspace equipmentId={equipmentId}/></Disclosure>
    </div>
  );
}
