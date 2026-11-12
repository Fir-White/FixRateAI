import { readQueries } from "@/shared/api/readQueries";
import { useMemo } from "react";
import { isShortString, useWorkspaceState } from "@/shared/lib/workspaceState";
import { Link } from "react-router-dom";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { buttonClassName } from "@/shared/ui/Button";
import { FormField, Input, Select } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { EquipmentTable } from "@/entities/equipment/EquipmentTable";
import type { EquipmentState } from "@/shared/types/domain";
import { useSession } from "@/shared/session/SessionContext";
import { DEMO_MODE } from "@/shared/api/request";
import { EquipmentRegistry } from "@/features/equipment/EquipmentRegistry";

type StateFilter = "all" | EquipmentState;

export function EquipmentPage() {
  const { profile } = useSession();
  return !DEMO_MODE && profile?.role !== 'executor' ? <EquipmentRegistry/> : <LegacyEquipmentPage/>;
}

function LegacyEquipmentPage() {
  const { profile } = useSession();
  const query = useApiQuery(readQueries.equipment.load, [], undefined, readQueries.equipment.key);
  const [search, setSearch] = useWorkspaceState("equipment.search", "", isShortString);
  const [stateFilter, setStateFilter] = useWorkspaceState<StateFilter>("equipment.filter", "all", (value): value is StateFilter => typeof value === "string" && ["all", "active", "out_of_service", "retired"].includes(value));

  const items = useMemo(() => {
    if (query.status !== "success") {
      return [];
    }
    const normalized = search.trim().toLowerCase();
    return query.data.filter((item) => {
      const matchesState =
        stateFilter === "all" || item.state === stateFilter;
      const matchesSearch =
        normalized.length === 0 ||
        [item.name, item.inventoryCode, item.equipmentType, item.location]
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      return matchesState && matchesSearch;
    });
  }, [query.data, query.status, search, stateFilter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Оборудование"
        description="Паспорт, регламенты и принятая история — в одном месте. Только оборудование доступного объекта."
        actions={(profile?.role === "admin" || profile?.role === "dispatcher") ? <Link className={buttonClassName("secondary")} to="/settings/equipment">
          <Icon name="plus" size={18} />
          Добавить
        </Link> : undefined}
      />

      <div className="equipment-toolbar">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_15rem]">
          <FormField label="Поиск" htmlFor="equipment-search">
            <Input
              id="equipment-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Название, номер, тип или расположение"
              leadingIcon={<Icon name="search" size={17} />}
            />
          </FormField>
          <FormField label="Состояние" htmlFor="equipment-state">
            <Select
              id="equipment-state"
              value={stateFilter}
              onChange={(event) =>
                setStateFilter(event.target.value as StateFilter)
              }
            >
              <option value="all">Все состояния</option>
              <option value="active">В эксплуатации</option>
              <option value="out_of_service">Выведено из эксплуатации</option>
              <option value="retired">Списано</option>
            </Select>
          </FormField>
        </div>
      </div>

      {query.status === "loading" ? <LoadingState /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}
      {query.status === "success" && items.length === 0 ? (
        <EmptyState
          title={query.data.length?"Оборудование не найдено":"Нет доступного оборудования"}
          description={query.data.length?"Измените поисковый запрос или фильтр состояния.":"В текущем объекте или ваших назначениях нет доступных связей с оборудованием."}
        />
      ) : null}
      {query.status === "success" && items.length > 0 ? (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-5 py-3 sm:px-6">
            <p className="text-xs font-semibold text-muted">
              Найдено: {items.length}
            </p>
            <p className="text-xs text-muted/60">
              Данные текущего объекта
            </p>
          </div>
          <EquipmentTable items={items} />
        </Card>
      ) : null}
    </div>
  );
}
