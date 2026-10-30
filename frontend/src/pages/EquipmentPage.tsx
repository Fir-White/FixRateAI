import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { maintenanceApi } from "@/shared/api/maintenance";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Card } from "@/shared/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/shared/ui/States";
import { Button, buttonClassName } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { EquipmentTable } from "@/entities/equipment/EquipmentTable";
import type { EquipmentState } from "@/shared/types/domain";

type StateFilter = "all" | EquipmentState;

export function EquipmentPage() {
  const query = useApiQuery(() => maintenanceApi.listEquipment(), []);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState<StateFilter>("all");

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
        eyebrow="Реестр"
        title="Оборудование"
        description="Единицы оборудования в пределах доступного объекта. Инвентарный номер уникален внутри Site."
        actions={
          <>
            <Button variant="secondary" disabled title="API создания ещё не подключён">
              <Icon name="plus" size={18} />
              Добавить
            </Button>
            <Link to="/calendar" className={buttonClassName("primary")}>
              Календарь ТО
            </Link>
          </>
        }
      />

      <Card className="p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative flex-1">
            <span className="sr-only">Поиск оборудования</span>
            <Icon
              name="search"
              size={18}
              className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400"
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Название, инвентарный номер, тип или расположение"
              className="h-10 w-full rounded-xl border border-slate-300 bg-white pr-3 pl-10 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            />
          </label>
          <select
            value={stateFilter}
            onChange={(event) =>
              setStateFilter(event.target.value as StateFilter)
            }
            className="h-10 rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700"
          >
            <option value="all">Все состояния</option>
            <option value="active">В эксплуатации</option>
            <option value="out_of_service">Выведено из эксплуатации</option>
            <option value="retired">Списано</option>
          </select>
        </div>
      </Card>

      {query.status === "loading" ? <LoadingState /> : null}
      {query.status === "error" ? (
        <ErrorState description={query.error} />
      ) : null}
      {query.status === "success" && items.length === 0 ? (
        <EmptyState
          title="Оборудование не найдено"
          description="Измените поисковый запрос или фильтр состояния."
        />
      ) : null}
      {query.status === "success" && items.length > 0 ? (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3 sm:px-6">
            <p className="text-xs font-semibold text-slate-500">
              Найдено: {items.length}
            </p>
            <p className="text-xs text-slate-400">
              Демонстрационный объект · Asia/Yekaterinburg
            </p>
          </div>
          <EquipmentTable items={items} />
        </Card>
      ) : null}
    </div>
  );
}
