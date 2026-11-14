import { request } from './request';
import type { DraftRecord,PlanIssue,PlanValidation,WorkSegment } from './draftPlans';

export interface OptimizationOptions {grid_minutes:15|30|60;time_limit_seconds:number;replan_existing:boolean;start_buffer_minutes:number;random_seed:number;weights:{daily_peak:number;worker_spread:number;changes:number;earliness:number}}
export interface OptimizationVariant {
  kind:'baseline'|'optimized';method_version:string;solver_status:string;coverage_status:string;optimality_proven:boolean;optimality_scope:'discrete_candidate_model';model_complete:boolean;duration_seconds:number;applicable:boolean;
  metrics:{total_occurrences:number;covered_occurrences:number;mandatory_work_coverage:string;total_person_hours:string;placed_person_hours:string;unplaced_segments:number;peak_daily_person_hours:string;peak_daily_utilization:string|null;daily_load_balance:string|null;staff_utilization:string|null;fairness_spread:string|null;changed_assignments:number;unfilled_slots:number};validation:PlanValidation;
}
export interface OptimizationRun {
  run_id:string;draft_id:string;base_revision:number;created_at:string;state:'queued'|'running'|'cancel_requested'|'cancelled'|'succeeded'|'failed';options:OptimizationOptions;error_code:string|null;applied_revision:number|null;applied_kind:'baseline'|'optimized'|null;
  result:{completion_reason:string;model_complete:boolean;candidate_count:number;variable_count:number;diagnostics:PlanIssue[];diagnostic_counts:Record<string,number>;baseline:OptimizationVariant|null;optimized:OptimizationVariant|null}|null;
}
const base='/api/v1/maintenance/optimization-runs';
export const optimizationApi={
  start:(id:string,expected_revision:number,idempotency_key:string,options:OptimizationOptions)=>request<OptimizationRun>(`/api/v1/maintenance/draft-plans/${encodeURIComponent(id)}/optimization-runs`,{method:'POST',body:JSON.stringify({expected_revision,idempotency_key,options})}),
  list:(id:string,offset:number)=>request<{items:OptimizationRun[];total:number}>(`/api/v1/maintenance/draft-plans/${encodeURIComponent(id)}/optimization-runs?offset=${offset}`),
  get:(id:string)=>request<OptimizationRun>(`${base}/${encodeURIComponent(id)}`),
  cancel:(id:string)=>request<OptimizationRun>(`${base}/${encodeURIComponent(id)}/cancel`,{method:'POST'}),
  placements:(id:string,kind:'baseline'|'optimized',offset:number)=>request<{items:WorkSegment[];worker_labels:Record<string,string>;occurrence_labels:Record<string,string>;total:number}>(`${base}/${encodeURIComponent(id)}/placements?${new URLSearchParams({kind,offset:String(offset)})}`),
  apply:(id:string,expected_revision:number,kind:'baseline'|'optimized',reason:string)=>request<DraftRecord>(`${base}/${encodeURIComponent(id)}/apply`,{method:'POST',body:JSON.stringify({expected_revision,kind,reason})}),
};
