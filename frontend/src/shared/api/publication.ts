import { request } from './request';
import type { DraftPolicy,PlanIssue,PlanValidation } from './draftPlans';

export interface ExecutionCheck {text:string;answer_kind:'boolean'|'number'|'text';unit?:string|null;required:boolean;visual_verifiability:'visible'|'partial'|'not_verifiable';photo_required:boolean}
export interface ExecutionProfile {row_number:number;instructions:string;safety_notes:string;methodology_ref:string;engineer_note:string;checklist:ExecutionCheck[]}
export interface PublicationSummary {added_tasks:number;changed_tasks:0;cancelled_tasks:0;occurrences:number;segments:number;total_person_hours:string;selected_rows:number;unselected_rows:number;months:string[]}
export interface PublicationProposal {planning_policy?:DraftPolicy|null;proposal_id:string;draft_id:string;base_revision:number;state:'prepared'|'approved'|'rejected'|'published';created_at:string;expires_at:string;reason:string;scope_note:string;proposal_digest:string;summary:PublicationSummary;validation:PlanValidation;blockers:PlanIssue[];blocker_count:number;can_approve:boolean;decided_by:string|null;decision_reason:string|null;approval_token:string|null;publication_id:string|null;published_at:string|null}
export type PublicationHistoryItem=Pick<PublicationProposal,'proposal_id'|'draft_id'|'base_revision'|'state'|'created_at'|'expires_at'|'summary'|'blocker_count'>;
export interface PublicationChange {item_id:string;occurrence_id:string;segment_ids:string[];depends_on_item_ids:string[];row_number:number;operation_code:string;title:string;equipment_ids:string[];worker_ids:string[];start_at:string|null;end_at:string|null;person_hours:string;execution:ExecutionProfile;kind:'create';previous:null}
const base='/api/v1/maintenance/publication-proposals';
export const publicationApi={
  profiles:(id:string,revision:number,offset:number)=>request<{items:{row_number:number;code:string;title:string;included_rows:number[]}[];total:number}>(`/api/v1/maintenance/draft-plans/${encodeURIComponent(id)}/publication-profiles?${new URLSearchParams({revision:String(revision),offset:String(offset)})}`),
  prepare:(id:string,body:{expected_revision:number;idempotency_key:string;reason:string;scope_note:string;profiles:ExecutionProfile[]})=>request<PublicationProposal>(`/api/v1/maintenance/draft-plans/${encodeURIComponent(id)}/publication-proposals`,{method:'POST',body:JSON.stringify(body)}),
  list:(id:string,offset:number)=>request<{items:PublicationHistoryItem[];total:number}>(`/api/v1/maintenance/draft-plans/${encodeURIComponent(id)}/publication-proposals?offset=${offset}`),
  get:(id:string)=>request<PublicationProposal>(`${base}/${encodeURIComponent(id)}`),
  changes:(id:string,offset:number)=>request<{items:PublicationChange[];total:number;worker_labels:Record<string,string>;equipment_labels:Record<string,string>}>(`${base}/${encodeURIComponent(id)}/changes?offset=${offset}`),
  approve:(id:string,expected_digest:string,reason:string)=>request<PublicationProposal>(`${base}/${encodeURIComponent(id)}/approve`,{method:'POST',body:JSON.stringify({expected_digest,reason})}),
  reject:(id:string,expected_digest:string,reason:string)=>request<PublicationProposal>(`${base}/${encodeURIComponent(id)}/reject`,{method:'POST',body:JSON.stringify({expected_digest,reason})}),
  publish:(id:string,expected_digest:string,approval_token:string,idempotency_key:string)=>request<PublicationProposal>(`${base}/${encodeURIComponent(id)}/publish`,{method:'POST',body:JSON.stringify({expected_digest,approval_token,idempotency_key})}),
};
