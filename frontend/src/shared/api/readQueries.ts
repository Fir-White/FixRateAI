import { maintenanceApi } from "./maintenance";
import { managementApi } from "./management";
import { request } from "./request";

/** Keys describe returned data, so pages can share identical list reads. */
export const readQueries = {
  tasks: { key: "tasks", load: () => maintenanceApi.listTasks() },
  equipment: { key: "equipment", load: () => maintenanceApi.listEquipment() },
  comparisons: { key: "comparisons", load: () => maintenanceApi.listComparisons() },
  quality: { key: "quality", load: () => maintenanceApi.listQualityQueue() },
  workforce: { key: "workforce", load: () => managementApi.workforce() },
  overview: { key: "overview", load: () => request<unknown[]>("/api/v1/maintenance/overview") },
  calendarMonth: (year: number, month: number) => ({ key: `calendar-month:${year}:${month}`, load: () => maintenanceApi.listCalendar(year, month) }),
  serviceIndex: { key: "service-index", load: () => Promise.all([managementApi.catalog(), maintenanceApi.listEquipment()]) },
};
