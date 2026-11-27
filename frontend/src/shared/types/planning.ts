export interface WorkloadDemand {
  occurrence_id: string;
  date: string;
  equipment_name: string;
  operation_title: string;
  data_origin: "customer" | "synthetic_demo";
  person_hours: string | null;
  crew_size: number;
  state: "unassigned" | "assigned" | "reported" | "incomplete";
  assigned_worker_ids: string[];
}

export interface DailyWorkload {
  date: string;
  occurrences: WorkloadDemand[];
  total_person_hours: string | null;
  known_person_hours: string;
  unassigned_person_hours: string | null;
  required_workers_lower_bound: number | null;
  free_workers: number;
  assigned_workers: number;
  free_person_hours: string | null;
  known_free_person_hours: string;
  deficit_person_hours: string | null;
  unknown_norms: number;
  unknown_workers: number;
  status: "hours_deficit" | "hours_sufficient" | "incomplete" | "no_work";
}

export interface WorkloadResponse {
  method_version: string;
  site_id: string;
  year: number;
  month: number;
  timezone: string;
  calculated_at: string;
  capacity_hours_per_24h: string;
  policy_status: "provisional";
  snapshot_sha256: string;
  source_incomplete: boolean;
  total_occurrences: number;
  unassigned_occurrences: number;
  deficit_days: number;
  incomplete_days: number;
  diagnostics: string[];
  days: DailyWorkload[];
}
