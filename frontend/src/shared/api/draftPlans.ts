import { request } from './request';

export interface DraftPolicy {capacity_hours_per_24h:string|null;capacity_confirmed:boolean;capacity_ref:string;day_start_minute:number|null;night_start_minute:number|null}
export interface GenerationInput {import_id:string;starts_on:string;ends_on:string;row_numbers:number[];expansion:'source_january'|'confirmed_rule';policy:DraftPolicy}
export interface PlanIssue {code:string;message:string;row_number:number|null;occurrence_id:string|null;segment_id:string|null;date:string|null}
export interface WorkOccurrence {occurrence_id:string;site_id:string;import_id:string;source_sha256:string;parser_version:string;source_row:number;decision_revision:number;source_cells:string[];source_date:string;source_slot:'whole_day'|'day'|'night';date_basis?:'source_january'|'confirmed_rule';title:string;operation_code:string;maintenance_type:string;interpretation:string;equipment_ids:string[];earliest_date:string;latest_date:string;allowed_intervals:{start_at:string;end_at:string}[];total_person_hours:string;crew_size:number;splittable:boolean;min_segment_minutes:number|null;qualification_ids:string[];qualifications_confirmed:boolean;included_rows:number[];norm_ref:string;norm_scope:'per_asset'|'whole_binding';policy_note:string}
export interface WorkSegment {segment_id:string;occurrence_id:string;equipment_ids:string[];person_hours:string;start_at:string|null;end_at:string|null;worker_ids:string[];locked:boolean;depends_on_segment_ids:string[]}
export interface GenerationPreview {input_sha256:string;generator_version:string;total_occurrences:number;total_segments:number;total_person_hours:string;selected_rows:number;unselected_rows:number;can_save:boolean;total_issues:number;issues:PlanIssue[];items:WorkOccurrence[];ready_for_real_plan:false}
export interface DraftRecord {draft_id:string;revision:number;parent_revision:number|null;import_id:string;title:string;starts_on:string;ends_on:string;created_at:string;created_by:string;author_name:string;reason:string;input_sha256:string;occurrence_count:number;segment_count:number;total_person_hours:string;status:'draft';ready_for_real_plan:false}
export interface PlanValidation {validator_version:string;status:'valid'|'incomplete'|'invalid';checked_at:string;input_sha256:string;resource_sha256:string;total_issues:number;issue_counts:Record<string,number>;issues:PlanIssue[];total_person_hours:string;placed_person_hours:string;unplaced_segments:number;days:{date:string;planned_person_hours:string;reserved_person_hours:string;available_person_hours:string|null;deficit_person_hours:string|null}[];ready_for_real_plan:false}
export interface DraftOverview {record:DraftRecord;months:{month:string;due_person_hours:string;planned_person_hours:string}[];validation:PlanValidation}
export interface PlanningChoice {id:string;label:string}
const base='/api/v1/maintenance/draft-plans';
const revisionQuery=(revision:number)=>new URLSearchParams({revision:String(revision)});
export const draftPlansApi={
  sources:(id:string,q:string,offset:number)=>request<{items:{row_number:number;code:string;title:string;maintenance_type:string}[];total:number}>(`${base}/source-choices/${encodeURIComponent(id)}?${new URLSearchParams({q,offset:String(offset)})}`),
  preview:(input:GenerationInput)=>request<GenerationPreview>(base+'/preview',{method:'POST',body:JSON.stringify(input)},{readOnly:true}),
  create:(input:GenerationInput,preview_sha256:string,idempotency_key:string,title:string,reason:string)=>request<DraftRecord>(base,{method:'POST',body:JSON.stringify({input,preview_sha256,idempotency_key,title,reason})}),
  list:(import_id:string,offset=0)=>request<{items:DraftRecord[];total:number}>(`${base}?${new URLSearchParams({import_id,offset:String(offset)})}`),
  overview:(id:string,revision:number)=>request<DraftOverview>(`${base}/${encodeURIComponent(id)}?${revisionQuery(revision)}`),
  versions:(id:string,offset:number)=>request<{items:DraftRecord[];total:number}>(`${base}/${encodeURIComponent(id)}/versions?offset=${offset}`),
  occurrences:(id:string,revision:number,offset:number,q:string,period:string)=>request<{items:WorkOccurrence[];total:number}>(`${base}/${encodeURIComponent(id)}/occurrences?${new URLSearchParams({revision:String(revision),offset:String(offset),q,period})}`),
  segments:(id:string,revision:number,root:string,offset:number)=>request<{occurrence:WorkOccurrence;items:WorkSegment[];total:number;worker_labels:Record<string,string>}>(`${base}/${encodeURIComponent(id)}/occurrences/${encodeURIComponent(root)}/segments?${new URLSearchParams({revision:String(revision),offset:String(offset)})}`),
  validate:(id:string,revision:number)=>request<PlanValidation>(`${base}/${encodeURIComponent(id)}/validate?${revisionQuery(revision)}`,{method:'POST'},{readOnly:true}),
  edit:(id:string,body:{expected_revision:number;occurrence_id:string;segments:WorkSegment[];replace_segment_ids:string[];unlock:boolean;reason:string})=>request<DraftRecord>(`${base}/${encodeURIComponent(id)}/segments`,{method:'POST',body:JSON.stringify(body)}),
  place:(id:string,body:{expected_revision:number;segment_id:string;start_local:string|null;end_local:string|null;worker_ids:string[];locked:boolean;unlock:boolean;reason:string})=>request<DraftRecord>(`${base}/${encodeURIComponent(id)}/placements`,{method:'POST',body:JSON.stringify(body)}),
  choices:(kind:'workers'|'skills',q:string,offset:number)=>request<{items:PlanningChoice[];total:number}>(`${base}/choices/${kind}?${new URLSearchParams({q,offset:String(offset)})}`),
};
