import { request } from "./request";
import type { WorkloadResponse } from "@/shared/types/planning";

export const planningApi = {
  workload: (year: number, month: number, capacity: string) => request<WorkloadResponse>(
    `/api/v1/maintenance/planning/workload?year=${year}&month=${month}&capacity_hours_per_24h=${encodeURIComponent(capacity)}`,
  ),
};
