import { request } from './request';
import type { DraftPolicy,DraftRecord,GenerationPreview } from './draftPlans';
import type { RequirementsRequest } from './requirements';

export interface PortfolioInput {kind:'portfolio';requirements:RequirementsRequest;policy:DraftPolicy}
export interface PortfolioPreview extends GenerationPreview {excluded_occurrences:number;requirements_sha256:string}
const base='/api/v1/maintenance/portfolio-plans';
export const portfolioPlansApi={
  list:(offset=0)=>request<{items:DraftRecord[];total:number}>(`${base}?offset=${offset}`),
  preview:(input:PortfolioInput)=>request<PortfolioPreview>(`${base}/preview`,{method:'POST',body:JSON.stringify(input)},{readOnly:true}),
  create:(input:PortfolioInput,preview_sha256:string,idempotency_key:string,title:string,reason:string)=>request<DraftRecord>(base,{method:'POST',body:JSON.stringify({input,preview_sha256,idempotency_key,title,reason})}),
};
