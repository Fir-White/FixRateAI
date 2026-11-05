import type { EquipmentBundle, TaskBundle, ComparisonBundle } from "./maintenance.demo";
import type { Equipment, MaintenanceTask, CalendarOccurrence, CalendarPreview, ComparisonRun, PhotoReview, AssignmentContext, CrewSelection, CrewAssignmentCommand, PlanningRun } from "@/shared/types/domain";
import { request, DEMO_MODE } from "./request";
export type { EquipmentBundle, TaskBundle, ComparisonBundle } from "./maintenance.demo";

const base = "/api/v1/maintenance";
const ui = `${base}/ui`;
const id = encodeURIComponent;
const live = {
  listEquipment: () => request<Equipment[]>(`${ui}/equipment`),
  getEquipment: (equipmentId: string) => request<EquipmentBundle>(`${ui}/equipment/${id(equipmentId)}`),
  listTasks: () => request<MaintenanceTask[]>(`${ui}/tasks`),
  getTask: (taskId: string) => request<TaskBundle>(`${ui}/tasks/${id(taskId)}`),
  listExecutorTasks: (_executorId: string) => request<MaintenanceTask[]>(`${ui}/tasks`),
  getExecutorTask: (taskId: string) => request<TaskBundle>(`${ui}/tasks/${id(taskId)}`),
  listCalendar: (year: number, month: number) => request<CalendarOccurrence[]>(`${ui}/calendar?year=${year}&month=${month}`),
  listComparisons: () => request<ComparisonRun[]>(`${ui}/comparisons`),
  getComparison: (runId: string) => request<ComparisonBundle>(`${ui}/comparisons/${id(runId)}`),
  listQualityQueue: () => request<MaintenanceTask[]>(`${ui}/quality`),
  getQualityBundle: (taskId: string) => request<TaskBundle>(`${ui}/tasks/${id(taskId)}`),
};
// Test fixtures are only loaded in the explicitly selected demo build.
const demo = DEMO_MODE ? {
  listEquipment: async () => (await import("./maintenance.demo")).maintenanceApi.listEquipment(),
  getEquipment: async (equipmentId: string) => (await import("./maintenance.demo")).maintenanceApi.getEquipment(equipmentId),
  listTasks: async () => (await import("./maintenance.demo")).maintenanceApi.listTasks(),
  getTask: async (taskId: string) => (await import("./maintenance.demo")).maintenanceApi.getTask(taskId),
  listExecutorTasks: async (executorId: string) => (await import("./maintenance.demo")).maintenanceApi.listExecutorTasks(executorId),
  getExecutorTask: async (taskId: string) => (await import("./maintenance.demo")).maintenanceApi.getExecutorTask(taskId),
  listCalendar: async (year: number, month: number) => (await import("./maintenance.demo")).maintenanceApi.listCalendar(year, month),
  listComparisons: async () => (await import("./maintenance.demo")).maintenanceApi.listComparisons(),
  getComparison: async (runId: string) => (await import("./maintenance.demo")).maintenanceApi.getComparison(runId),
  listQualityQueue: async () => (await import("./maintenance.demo")).maintenanceApi.listQualityQueue(),
  getQualityBundle: async (taskId: string) => (await import("./maintenance.demo")).maintenanceApi.getQualityBundle(taskId),
} : null;
export const maintenanceApi = {
  ...(demo ?? live),
  previewCalendar: (year: number, month: number) => request<CalendarPreview>(`${ui}/calendar/preview?year=${year}&month=${month}`),
  generateTasks: (year: number, month: number, previewToken: string, key: string) => request<PlanningRun>(`${base}/calendar/generate`, {
    method: "POST", body: JSON.stringify({year, month, preview_token: previewToken, idempotency_key: key})}),
  assignmentContext: (taskId: string) => request<AssignmentContext>(`${ui}/tasks/${id(taskId)}/assignment-context`),
  previewAssignment: (taskId: string, revision: number, startLocal: string, endLocal: string, crewId: string | null, executorIds?: string[], individualOnly=false) =>
    request<CrewSelection>(`${base}/tasks/${id(taskId)}/assignment-preview`, {method: "POST",
      body: JSON.stringify({expected_revision: revision, start_local: startLocal, end_local: endLocal, crew_id: crewId,executor_ids:executorIds,individual_only:individualOnly})}),
  assignCrew: (taskId: string, command: CrewAssignmentCommand, crewId: string | null) =>
    request<TaskBundle>(`${base}/tasks/${id(taskId)}/assign`, {method: "POST", body: JSON.stringify({...command, crew_id: crewId})}),
  start: (taskId: string, revision: number) => request<TaskBundle>(`${base}/tasks/${id(taskId)}/start`, {method: "POST", body: JSON.stringify({expected_revision: revision})}),
  cancel: (taskId:string,revision:number,reason:string) => request<TaskBundle>(`${base}/tasks/${id(taskId)}/cancel`,{method:"POST",body:JSON.stringify({expected_revision:revision,reason})}),
  saveReport: (taskId: string, revision: number, narrative: string, answers: Record<string, string | null>, protocol?:{actual:import("@/shared/types/domain").ActualExecution|null;readings:import("@/shared/types/domain").Reading[]}) => request<TaskBundle>(`${base}/tasks/${id(taskId)}/report`, {method: "PUT", body: JSON.stringify({expected_revision: revision, narrative, answers,...(protocol?{actual:protocol.actual?Object.fromEntries(Object.entries(protocol.actual).map(([k,v])=>[k,v||null])):null,readings:protocol.readings.filter(r=>r.value!==""&&r.measured_at!=="")}:{} )})}),
  submit: (taskId: string, revision: number) => request<TaskBundle>(`${base}/tasks/${id(taskId)}/submit`, {method: "POST", body: JSON.stringify({expected_revision: revision})}),
  review: (taskId: string, revision: number, executionId: string, verdict: "accepted" | "rejected", reason: string, evidence?:{reviewed_ai_result_id?:string;additional_evidence_refs:string[]}) => request<TaskBundle>(`${base}/tasks/${id(taskId)}/review`, {method: "POST", body: JSON.stringify({expected_revision: revision, execution_id: executionId, verdict, reason,...evidence})}),
  forecast: (taskId: string, revision: number) => request<ComparisonBundle>(`${base}/tasks/${id(taskId)}/forecast`, {method: "POST", body: JSON.stringify({expected_revision: revision})}),
  photoReview: (taskId: string, revision: number, confirmed: boolean) => request<PhotoReview>(`${base}/tasks/${id(taskId)}/photo-review`, {method: "POST", body: JSON.stringify({expected_revision: revision, comparability_confirmed: confirmed})}),
  upload: (taskId: string, revision: number, itemId: string, phase: string, viewKey: string, file: File) => {
    const form = new FormData();
    form.set("expected_revision", String(revision)); form.set("checklist_item_id", itemId);
    form.set("phase", phase); form.set("view_key", viewKey); form.set("file", file);
    return request<TaskBundle>(`${base}/tasks/${id(taskId)}/photos`, {method: "POST", body: form});
  },
};
