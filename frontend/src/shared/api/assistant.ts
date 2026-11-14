import {request} from './request';
export type AgentId='assistant'|'planner'|'photo';
export interface ChatTool {name:string;title:string;requires_confirmation:boolean}
export interface ChatCapabilities {available:boolean;model_ref:string|null;prompt_version:string;agents:{id:AgentId;title:string;description:string}[];tools:Record<AgentId,ChatTool[]>}
export interface Conversation {conversation_id:string;title:string;agent:AgentId;created_at:string;updated_at:string}
export interface ChatTurn {turn_id:string;content:string;answer:string;status:'running'|'completed'|'failed';error_code:string|null;trace:{tool:string;status:string;at?:string;code?:number;resource?:{url:string;title:string;mime:string}}[];created_at:string;finished_at?:string|null;model_ref:string|null}
export interface ChatAction {action_id:string;conversation_id:string;turn_id:string|null;tool_name:string;arguments:{path?:Record<string,unknown>;query?:Record<string,unknown>;body?:Record<string,unknown>};payload_sha256:string;secret_fields?:string[];before_snapshot:{sha256:string;preview:unknown}|null;explanation:string;status:'proposed'|'rejected'|'executing'|'succeeded'|'failed'|'uncertain'|'stale';result:{data?:unknown;message?:string;status_code?:number}|null;expires_at:string;created_at:string}
export interface ChatAttachment {attachment_id:string;original_name:string;mime_type:string;size_bytes:number;sha256:string;created_at:string}
export interface ChatView {conversation:Conversation;turns:ChatTurn[];total:number;actions:ChatAction[];attachments?:ChatAttachment[]}
const base='/api/v1/assistant';
export const assistantApi={
  capabilities:()=>request<ChatCapabilities>(base+'/capabilities'),
  list:(offset=0)=>request<{items:Conversation[];total:number}>(base+`/conversations?offset=${offset}`),
  create:(agent:AgentId)=>request<Conversation>(base+'/conversations',{method:'POST',body:JSON.stringify({agent})}),
  read:(id:string,offset=0)=>request<ChatView>(`${base}/conversations/${encodeURIComponent(id)}?offset=${offset}`),
  send:(id:string,content:string,idempotency_key:string)=>request<{turn_id:string;status:string}>(`${base}/conversations/${encodeURIComponent(id)}/messages`,{method:'POST',body:JSON.stringify({content,idempotency_key})}),
  upload:(id:string,file:File)=>{const body=new FormData();body.set('file',file);return request<ChatAttachment>(`${base}/conversations/${encodeURIComponent(id)}/attachments`,{method:'POST',body});},
  confirm:(action:ChatAction,secret_values?:Record<string,string>)=>request<ChatAction>(`${base}/actions/${encodeURIComponent(action.action_id)}/confirm`,{method:'POST',body:JSON.stringify({payload_sha256:action.payload_sha256,confirmed:true,...(secret_values?{secret_values}:{})})}),
  reject:(id:string)=>request<ChatAction>(`${base}/actions/${encodeURIComponent(id)}/reject`,{method:'POST',body:'{}'}),
};
