import {request} from './request';
export type AgentId='assistant'|'planner'|'photo';
export interface ChatModelChoice {provider:'ollama'|'aitunnel';model:string;digest?:string;is_alias?:boolean}
export interface ChatModelPreference {selection:ChatModelChoice|null;revision:number;is_default:boolean;available:boolean}
export interface ChatModelCatalog {providers:{id:'ollama'|'aitunnel';name:string;status:'ready'|'not_configured'|'unavailable';error_code:string|null;models:{id:string;name:string;description:string;selectable:boolean;digest?:string}[]}[]}
export interface ChatTool {name:string;title:string;requires_confirmation:boolean}
export interface ChatCapabilities {available:boolean;model_ref:string|null;prompt_version:string;agents:{id:AgentId;title:string;description:string}[];tools:Record<AgentId,ChatTool[]>;model_preference?:ChatModelPreference}
export interface Conversation {conversation_id:string;title:string;agent:AgentId;created_at:string;updated_at:string;subject_task_id?:string|null;pinned_at?:string|null}
export interface ChatWorkflow {answer_format?:'facts';kind?:'task_execution';root_turn_id?:string;display_plan?:boolean;outcome:string;goals:{id:string;title:string;status:string;reason?:string|null;message?:string|null;action_id?:string|null}[];metrics?:{llm_calls:number;llm_seconds:number;tool_calls:number;tool_seconds:number};stop_reason?:string|null;revision?:number}
export interface ChatTurn {turn_id:string;content:string;answer:string;status:'running'|'completed'|'failed';error_code:string|null;workflow?:ChatWorkflow|null;trace:{tool:string;status:string;at?:string;code?:number;fact?:{total?:number;shown?:number;ready?:boolean};resource?:{url:string;title:string;mime:string}}[];created_at:string;finished_at?:string|null;model_ref:string|null;attachments?:ChatAttachment[]}
export interface ChatAction {action_id:string;conversation_id:string;turn_id:string|null;tool_name:string;arguments:{path?:Record<string,unknown>;query?:Record<string,unknown>;body?:Record<string,unknown>};payload_sha256:string;secret_fields?:string[];before_snapshot:{sha256:string;preview:unknown;assignment?:{taskTitle:string;taskCode:string;timezone:string;workers:string[];crewName:string|null}}|null;explanation:string;status:'proposed'|'rejected'|'executing'|'succeeded'|'failed'|'uncertain'|'stale';result:{data?:unknown;message?:string;status_code?:number;verification?:{status:'confirmed'|'failed'|'unverified';summary:string;reason?:string}}|null;expires_at:string;created_at:string}
export interface ChatAttachment {attachment_id:string;original_name:string;mime_type:string;size_bytes:number;sha256:string;created_at:string}
export interface ChatView {conversation:Conversation;turns:ChatTurn[];total:number;actions:ChatAction[];attachments?:ChatAttachment[];pending_attachments?:ChatAttachment[]}
export interface ActionHistoryItem {
  action_id: string;
  conversation_id: string;
  conversation_title: string;
  title: string;
  target_id: string | null;
  status: ChatAction['status'] | 'expired';
  created_at: string;
  confirmed_at: string | null;
  finished_at: string | null;
  verification: 'confirmed' | 'failed' | 'unverified' | null;
  failure_code: number | null;
}
export interface ActionHistoryPage {items: ActionHistoryItem[]; total: number; offset: number; limit: number; actor: string}
const base='/api/v1/assistant';
export const assistantApi={
  capabilities:()=>request<ChatCapabilities>(base+'/capabilities'),
  models:(refresh=false)=>request<ChatModelCatalog>(base+'/models'+(refresh?'?refresh=true':'')),
  modelPreference:()=>request<ChatModelPreference>(base+'/model-preference'),
  selectModel:(choice:ChatModelChoice,expected_revision:number)=>request<ChatModelPreference>(base+'/model-preference',{method:'POST',body:JSON.stringify({provider:choice.provider,model:choice.model,expected_revision})}),
  list:(offset=0)=>request<{items:Conversation[];total:number}>(base+`/conversations?offset=${offset}`),
  actionHistory:(offset:number)=>request<ActionHistoryPage>(base+`/actions?offset=${offset}`),
  create:(agent:AgentId,subject_task_id?:string)=>request<Conversation>(base+'/conversations',{method:'POST',body:JSON.stringify({agent,...(subject_task_id?{subject_task_id}:{})})}),
  read:(id:string,offset=0)=>request<ChatView>(`${base}/conversations/${encodeURIComponent(id)}?offset=${offset}`),
  update:(id:string,changes:{title?:string;pinned?:boolean})=>request<Conversation>(`${base}/conversations/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify(changes)}),
  stop:(id:string,turn:string)=>request<{stopped:boolean}>(`${base}/conversations/${encodeURIComponent(id)}/turns/${encodeURIComponent(turn)}/stop`,{method:'POST'}),
  remove:(id:string)=>request<{deleted:boolean}>(`${base}/conversations/${encodeURIComponent(id)}`,{method:'DELETE'}),
  send:(id:string,content:string,idempotency_key:string,attachment_ids:string[]=[],model_preference_revision?:number,resume_turn_id?:string)=>request<{turn_id:string;status:string}>(`${base}/conversations/${encodeURIComponent(id)}/messages`,{method:'POST',body:JSON.stringify({content,idempotency_key,attachment_ids,...(model_preference_revision!==undefined?{model_preference_revision}:{}),...(resume_turn_id?{resume_turn_id}:{})})}),
  upload:(id:string,file:File)=>{const body=new FormData();body.set('file',file);return request<ChatAttachment>(`${base}/conversations/${encodeURIComponent(id)}/attachments`,{method:'POST',body});},
  confirm:(action:ChatAction,secret_values?:Record<string,string>)=>request<ChatAction>(`${base}/actions/${encodeURIComponent(action.action_id)}/confirm`,{method:'POST',body:JSON.stringify({payload_sha256:action.payload_sha256,confirmed:true,...(secret_values?{secret_values}:{})})}),
  reject:(id:string)=>request<ChatAction>(`${base}/actions/${encodeURIComponent(id)}/reject`,{method:'POST',body:'{}'}),
};
