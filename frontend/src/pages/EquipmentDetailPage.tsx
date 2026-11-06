import { EquipmentOperations,IncidentWorkspace } from "@/features/analyst/AnalystPanels";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card, CardHeader } from "@/shared/ui/Card";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { InfoItem, InfoList } from "@/shared/ui/InfoList";
import { Icon } from "@/shared/ui/Icon";
import { useSession } from "@/shared/session/SessionContext";
import { Disclosure } from "@/shared/ui/Disclosure";
import { canOpenSection } from "@/shared/lib/roles";
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
  const query = useApiQuery(
    () => maintenanceApi.getEquipment(equipmentId),
    [equipmentId],
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

      <div className="fr-work-grid">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Паспорт оборудования" />
            <InfoList className="grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2 sm:p-6">
              <InfoItem label="Тип" value={equipment.equipmentType} />
              <InfoItem
                label="Инвентарный номер"
                value={equipment.inventoryCode}
                mono
              />
              <InfoItem label="Расположение" value={equipment.location} />
              <InfoItem
                label="Ввод в эксплуатацию"
                value={formatDate(equipment.commissionedOn)}
              />
              <InfoItem
                label="Последнее принятое ТО"
                value={formatDateTime(equipment.lastServiceAt)}
              />
              <InfoItem
                label="Следующий срок"
                value={formatDate(equipment.nextDueDate)}
              />
            </InfoList>
          </Card>

          <Card>
            <CardHeader
              title="Принятая история"
              description="Только принятые инженером события. Отклонённые попытки остаются в истории задания."
            />
            {history.length ? (
              <ol className="divide-y divide-line">
                {history.map((event) => (
                  <li key={event.id} className="flex gap-4 px-5 py-4 sm:px-6">
                    <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
                      <Icon name="check" size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-ink">
                        {event.operation}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        {event.taskCode} · проверил {event.engineer} ·{" "}
                        Выполнено {formatDateTime(event.performedAt)}
                      </p>
                      <p className="mt-1 text-xs text-muted/60">
                        Принято {formatDateTime(event.acceptedAt)}
                        {event.runtimeHours !== null
                          ? ` · наработка ${event.runtimeHours} ч`
                          : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 py-8 text-center text-sm text-muted">
                Принятых событий обслуживания ещё нет.
              </p>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <EquipmentOperations equipmentId={equipmentId}/>
          <Card>
            <CardHeader title="Операция в паспорте" description="Справочное поле паспорта; связанные версии обслуживания перечислены отдельно." />
            <div className="p-5 sm:p-6">
              <p className="text-xs font-semibold text-muted">
                Текущая операция
              </p>
              <p className="mt-1 text-sm font-semibold text-ink">
                {equipment.activeOperation ?? "В паспорте не указана"}
              </p>
              <Callout tone="neutral" className="mt-4 text-xs leading-5">
                Обязательства определяются связанными утверждёнными регламентами. Пустое поле паспорта не означает отсутствие этих регламентов.
              </Callout>
            </div>
          </Card>

          <Card>
            <CardHeader title="Связи" />
            <div className="space-y-2 p-5 sm:p-6">
              {canCompare && <Link
                to={`/comparisons?equipment=${encodeURIComponent(equipmentId)}`}
                className="flex items-center justify-between rounded-xl border border-line p-3 text-sm font-semibold text-ink-soft hover:border-accent/40 hover:bg-accent/[0.07]"
              >
                Прогнозы оборудования
                <Icon name="chevron" size={16} />
              </Link>}
              {tasksPath && <Link
                to={`${tasksPath}?equipment=${encodeURIComponent(equipmentId)}`}
                className="flex items-center justify-between rounded-xl border border-line p-3 text-sm font-semibold text-ink-soft hover:border-accent/40 hover:bg-accent/[0.07]"
              >
                {profile?.role === "executor" ? "Мои задания" : "Задания и назначения"}
                <Icon name="chevron" size={16} />
              </Link>}
              {!canCompare && !tasksPath && <p className="text-sm text-muted">Рабочие разделы доступны по роли диспетчера, инженера или исполнителя.</p>}
            </div>
          </Card>
        </div>
      </div>
      <Disclosure title="Дефекты и обращения по оборудованию"><IncidentWorkspace equipmentId={equipmentId}/></Disclosure>
    </div>
  );
}
