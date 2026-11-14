import { maintenanceApi } from "./maintenance";
import { managementApi } from "./management";
import { request } from "./request";
import { registryApi } from "./registry";
import type { ApiQueryCache } from "@/shared/lib/apiQueryCache";

/** Keys describe returned data, so pages can share identical list reads. */
export const readQueries = {
  tasks: { key: "tasks", load: () => maintenanceApi.listTasks() },
  equipment: { key: "equipment", load: () => maintenanceApi.listEquipment() },
  comparisons: { key: "comparisons", load: () => maintenanceApi.listComparisons() },
  quality: { key: "quality", load: () => maintenanceApi.listQualityQueue() },
  workforce: { key: "workforce", load: () => managementApi.workforce() },
  overview: { key: "overview", load: () => request<unknown[]>("/api/v1/maintenance/overview") },
  registry: { key: "registry-index", load: async () => {
    const [registry, sites] = await Promise.all([registryApi.load(), registryApi.sites()]);
    if (!Array.isArray(registry.items) || !Array.isArray(registry.systems) || !Array.isArray(sites)) throw new Error("Не удалось загрузить реестр оборудования");
    return { registry, sites };
  } },
  calendarMonth: (year: number, month: number) => ({ key: `calendar-month:${year}:${month}`, load: () => maintenanceApi.listCalendar(year, month) }),
  serviceIndex: { key: "service-index", load: (cache?: ApiQueryCache | null) => Promise.all([managementApi.catalog(),
    cache ? cache.load(readQueries.equipment.key, readQueries.equipment.load) : maintenanceApi.listEquipment()]) },
};
