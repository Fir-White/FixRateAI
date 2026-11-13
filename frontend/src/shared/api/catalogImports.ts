import { request } from './request';

export interface RawCatalogCell {address:string;present:boolean;text:string|null;raw_value:string|null;cell_type:string|null;style:string|null;formula:string|null}
export interface CatalogSummary {operation_count:number;group_count:number;top_level_group_count:number;maintenance_types:Record<string,number>;empty_duration_count:number;mark_count:number;readiness_counts:Record<string,number>;ready_count:number;ready_for_real_plan:false;issue_count:number}
export interface CatalogGroup {id:string;code:string;title:string;parent_id:string|null;row:number}
export interface CatalogIssue {code:string;sheet:string;cell:string;message:string}
export interface CatalogOperation {row:number;code:string;title:string;maintenance_type:string;frequency_raw:string;group_id:string|null;quality_flags:string[];interpretation:'UNKNOWN';mark_count:number;source_cells:Record<string,string>;ready_for_real_plan:false}
export interface CatalogRowDetail extends CatalogOperation {raw_cells:Record<string,RawCatalogCell>;calendar_marks:(RawCatalogCell & {day:number})[]}
export interface CatalogPreview {format:'hvac_catalog';preview_token:string;can_save_draft:boolean;source_sha256:string;summary:CatalogSummary;groups:CatalogGroup[];issues:CatalogIssue[];operations:CatalogOperation[];total:number;sheet2_diagnostic:RawCatalogCell[]}
export interface CatalogRecord {import_id:string;filename:string;source_sha256:string;parser_version:string;status:'draft';created_at:string;summary:CatalogSummary}
export interface CatalogDetail extends CatalogRecord {groups:CatalogGroup[];issues:CatalogIssue[];sheet2_diagnostic:RawCatalogCell[];header_context:RawCatalogCell[]}
const base='/api/v1/maintenance/catalog-imports';
export const catalogImportsApi={
  preview:(file:File)=>{const body=new FormData();body.set('file',file);return request<CatalogPreview>(base+'/preview',{method:'POST',body},{readOnly:true});},
  save:(file:File,token:string)=>{const body=new FormData();body.set('file',file);body.set('preview_token',token);return request<{import_id:string;already_saved:boolean;summary:CatalogSummary}>(base,{method:'POST',body});},
  list:(offset=0)=>request<{items:CatalogRecord[];total:number}>(`${base}?offset=${offset}&limit=25`),
  detail:(id:string)=>request<CatalogDetail>(`${base}/${encodeURIComponent(id)}`),
  operations:(id:string,offset:number,q:string,group:string,kind:string)=>request<{items:CatalogOperation[];total:number}>(`${base}/${encodeURIComponent(id)}/operations?${new URLSearchParams({offset:String(offset),limit:'25',q,group_id:group,kind})}`),
  operation:(id:string,row:number)=>request<CatalogRowDetail>(`${base}/${encodeURIComponent(id)}/operations/${row}`),
  source:(id:string)=>`${base}/${encodeURIComponent(id)}/source`,
  decision:(id:string,row:number)=>request<CatalogDecisionRecord>(`${base}/${encodeURIComponent(id)}/operations/${row}/decision`),
  saveDecision:(id:string,row:number,body:{expected_revision:number;confirm:boolean;reason:string;decision:CatalogDecision})=>request<CatalogDecisionRecord>(`${base}/${encodeURIComponent(id)}/operations/${row}/decision`,{method:'POST',body:JSON.stringify(body)}),
  preparation:(id:string)=>request<CatalogPreparation>(`${base}/${encodeURIComponent(id)}/preparation`),
  bindingOptions:(id:string,q:string,offset:number)=>request<{items:CatalogBinding[];total:number}>(`${base}/${encodeURIComponent(id)}/binding-options?${new URLSearchParams({q,offset:String(offset)})}`),
  history:(id:string,row:number,offset:number)=>request<{items:CatalogDecisionHistory[];total:number}>(`${base}/${encodeURIComponent(id)}/operations/${row}/decision/history?offset=${offset}`),
};

export interface CatalogDecision {
  interpretation:'UNKNOWN'|'FIXED_EXECUTION'|'ALLOWED_WINDOW'|'CONTINUOUS_WORK'|'EQUIPMENT_BATCH';
  calendar_year:number|null;mark_slots:'unconfirmed'|'one_per_mark'|'day_night';semantics_note:string;
  frequency_kind:'unconfirmed'|'day'|'week'|'month'|'quarter'|'year'|'yearly_count'|'daily_events'|'event'|'included_in';
  frequency_interval:number|null;included_in_row:number|null;equipment_ids:string[];
  norm_value:string|null;norm_unit:'unconfirmed'|'person_hour'|'elapsed_hour';norm_scope:'unconfirmed'|'per_asset'|'whole_binding';
  crew_size:number|null;norm_ref:string;splittable:boolean|null;min_segment_minutes:number|null;policy_note:string;
}
export interface CatalogBinding {equipment_id:string;asset_code:string;name:string;status:string;revision:number}
export interface CatalogDecisionRecord {row_number:number;revision:number;created_by:string|null;author_name?:string|null;created_at:string|null;confirmed:boolean;reason:string;decision:CatalogDecision;equipment:CatalogBinding[];blockers:string[];prepared:boolean;total_person_hours:string|null;elapsed_hours:string|null;ready_for_real_plan:false}
export interface CatalogDecisionHistory extends Pick<CatalogDecisionRecord,'revision'|'created_by'|'author_name'|'created_at'|'confirmed'|'reason'|'decision'|'equipment'> {parent_revision:number|null}
export interface CatalogPreparation {total:number;prepared_count:number;confirmed_count:number;blocker_counts:Record<string,number>;items:Pick<CatalogDecisionRecord,'row_number'|'revision'|'confirmed'|'prepared'|'blockers'>[];ready_for_real_plan:false}
