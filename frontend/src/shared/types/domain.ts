export type Role = "admin" | "dispatcher" | "engineer" | "executor";

export type DataOrigin = "customer" | "synthetic_demo";

export interface SessionProfile {
  userId: string;
  name: string;
  email: string;
  role: Role;
  siteName: string;
  timezone: string;
}

export type EquipmentState = "active" | "out_of_service" | "retired";

export interface Equipment {
  id: string;
  siteId: string;
  siteName: string;
  equipmentType: string;
  inventoryCode: string;
  name: string;
  location: string;
  commissionedOn: string | null;
  state: EquipmentState;
  revision: number;
  dataOrigin: DataOrigin;
  nextDueDate: string | null;
  lastServiceAt: string | null;
  activeOperation: string | null;
}

export interface ServiceHistoryItem {
  id: string;
  equipmentId: string;
  performedAt: string;
  acceptedAt: string;
  operation: string;
  engineer: string;
  taskCode: string;
  runtimeHours: string | null;
}

export type TaskState =
  | "draft"
  | "assigned"
  | "in_progress"
  | "submitted"
  | "rework_required"
  | "accepted"
  | "cancelled";

export type MaintenanceType = "ТО1" | "ТО2";

export interface Assignee {
  executorId: string;
  name: string;
  qualifications: string[];
}

export interface MaintenanceTask {
  id: string;
  code: string;
  title: string;
  equipmentId: string;
  equipmentName: string;
  operationCode: string;
  maintenanceType: MaintenanceType;
  state: TaskState;
  isOverdue: boolean;
  deadlineBreached: boolean;
  mandatoryDueDate: string;
  scheduledStart: string;
  scheduledEnd: string;
  crewSize: number;
  assignees: Assignee[];
  activeExecutionId: string | null;
  revision: number;
  dataOrigin: DataOrigin;
  summary: string;
}

export interface CalendarOccurrence {
  id: string;
  occurrenceDate: string;
  equipmentId: string;
  equipmentName: string;
  operationCode: string;
  operationTitle: string;
  maintenanceType: MaintenanceType;
  status: "draft" | "planned" | "fulfilled" | "cancelled";
  isOverdue: boolean;
  requiresInput: boolean;
  taskId: string | null;
}

export type AnswerKind = "boolean" | "number" | "text";

export type VisualVerifiability = "visible" | "partial" | "not_verifiable";

export interface ChecklistItem {
  id: string;
  text: string;
  answerKind: AnswerKind;
  unit: string | null;
  required: boolean;
  visualVerifiability: VisualVerifiability;
  photoRequired: boolean;
  answer: string | null;
}

export interface EvidencePhoto {
  id: string;
  phase: "before" | "after";
  viewKey: string;
  label: string;
  capturedAt: string;
  uploadedAt: string;
  checklistItemId: string;
  status: "uploaded" | "processing" | "rejected";
}

export interface ExecutionReport {
  id: string;
  taskId: string;
  attemptNumber: number;
  state: "draft" | "submitted";
  narrative: string;
  checklist: ChecklistItem[];
  photos: EvidencePhoto[];
  submittedAt: string | null;
}

export type ForecastStatus = "ok" | "needs_input" | "unavailable" | "failed";

export interface ForecastResult {
  resultId: string;
  method: "algorithmic" | "ai";
  methodVersion: string;
  modelRef: string | null;
  status: ForecastStatus;
  recommendedDate: string | null;
  mandatoryDueDate: string | null;
  overdue: boolean;
  uncertaintyKind: "deterministic" | "tree_dispersion" | "unknown";
  uncertaintyNote: string;
  explanation: string;
  warnings: string[];
  errorCode: string | null;
  elapsedMs: number;
}

export interface OrchestrationDecision {
  orchestrationId: string;
  status: "selected" | "fallback" | "needs_input" | "manual_review";
  selectedDate: string | null;
  policyVersion: string;
  reasons: string[];
}

export interface ComparisonRun {
  runId: string;
  snapshotId: string;
  snapshotHash: string;
  asOf: string;
  horizonEnd: string;
  earliestDate: string | null;
  mandatoryDueDate: string | null;
  equipmentId: string;
  equipmentName: string;
  operationTitle: string;
  dataOrigin: DataOrigin;
  createdAt: string;
  algorithmic: ForecastResult;
  ai: ForecastResult;
  decision: OrchestrationDecision;
}

export type PhotoReviewStatus =
  | "completed"
  | "uncertain"
  | "not_verifiable"
  | "unavailable"
  | "failed";

export type PhotoVerdict =
  | "visible_change"
  | "no_visible_change"
  | "uncertain"
  | "not_verifiable";

export interface PhotoReviewItem {
  id: string;
  label: string;
  verdict: PhotoVerdict;
  note: string;
}

export interface PhotoReview {
  id: string;
  executionId: string;
  status: PhotoReviewStatus;
  modelRef: string;
  promptSetVersion: string;
  createdAt: string;
  items: PhotoReviewItem[];
  limitations: string[];
}

export interface EngineerDecision {
  id: string;
  taskId: string;
  executionId: string;
  verdict: "accepted" | "rejected";
  reason: string;
  decidedAt: string;
  decidedBy: string;
}
