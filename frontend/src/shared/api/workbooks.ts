import { request } from './request';

const root = '/api/v1/maintenance/workbooks';
const book = (id: string) => `${root}/${encodeURIComponent(id)}`;
const versions = (id: string) => `${book(id)}/versions`;
const ver = (id: string, version: number) => `${versions(id)}/${version}`;
const editor = (id: string, session = '') => `${book(id)}/editor-sessions${session ? `/${encodeURIComponent(session)}` : ''}`;
const post = (value: object): RequestInit => ({method:'POST',body:JSON.stringify(value)});

export interface WorkbookVersion {
  book_id: string;
  version: number;
  filename: string;
  sha256: string;
  size_bytes: number;
  created_at: string;
}
interface WorkbookPage {items: WorkbookVersion[]; total: number}
export interface EditorStatus {
  session_id: string;
  state: 'editing'|'pending'|'ready'|'unchanged'|'failed'|'saved';
  snapshot_request_id: string|null;
  snapshot_sha256: string|null;
}
export interface EditorSession extends EditorStatus {api_url: string; document_config: Record<string, unknown>; detached_connections: boolean}
export interface VersionCommit {session_id: string; expected_version: number; snapshot_sha256: string; idempotency_key: string}

type OrderChange = {
  action: 'update'|'reschedule'; task_id: string; title: string; equipment: string|null;
  before_start: string|null; before_end: string|null; before_hours: string|null; before_note: string;
  planned_start: string|null; planned_end: string|null; planned_person_hours: string|null; note: string;
  due_date: string; worker_names: string[];
} | {action: 'blocked'; issue: string};
export interface OrderPreview {
  items: OrderChange[];
  can_apply: boolean;
  requires_assigned_confirmation: boolean;
  preview_digest: string|null;
}
interface OrderInput {row_number: number; reason: string}
export interface WorkbookOrderRow {row_number: number; task_id: string|null; title: string|null; issue: string|null}
interface OrderRows {items: WorkbookOrderRow[]; total: number; has_sheet: boolean; issue: string|null}
interface IssuedOrders {
  items: {task_id: string; title: string|null; planned_start_at: string|null; asset_code: string|null}[];
  has_more: boolean;
}

export const workbooks = {
  list: (offset: number) => request<WorkbookPage>(`${root}?offset=${offset}`),
  details: (id: string, version: number) => request<WorkbookVersion>(ver(id,version)),
  versions: (id: string, offset: number, signal?:AbortSignal) => request<WorkbookPage>(`${versions(id)}?offset=${offset}`,{signal}),
  download: (id: string, version: number) => `${ver(id,version)}/xlsx`,
  upload: (file: File) => {
    const body = new FormData(); body.append('file',file);
    return request<WorkbookVersion>(root,{method:'POST',body});
  },
  fromCatalog: (id: string, signal?:AbortSignal) =>
    request<WorkbookVersion>(`${root}/from-catalog/${encodeURIComponent(id)}`,{method:'POST',signal}),
  catalog: (id: string, version: number) => request<{import_id: string}>(`${ver(id,version)}/catalog`,{method:'POST'}),
  start: (id: string, version: number, signal?:AbortSignal) =>
    request<EditorSession>(editor(id),{...post({expected_version:version}),signal},{readOnly:true}),
  snapshot: (id: string, session: string, request_id: string) =>
    request<EditorStatus>(`${editor(id,session)}/snapshot`,post({request_id}),{readOnly:true}),
  status: (id: string, session: string, signal: AbortSignal) => request<EditorStatus>(editor(id,session),{signal}),
  commit: (id: string, command: VersionCommit) => request<WorkbookVersion>(versions(id),post(command)),
  issuedOrders: (q: string, offset: number) => request<IssuedOrders>(`${root}/issued-orders?${new URLSearchParams({q,offset:String(offset)})}`),
  orderRows: (id: string, version: number, offset: number) => request<OrderRows>(`${ver(id,version)}/order-changes?offset=${offset}`),
  orderPreview: (id: string, version: number, body: OrderInput) =>
    request<OrderPreview>(`${ver(id,version)}/order-changes/preview`,post(body),{readOnly:true}),
  orderApply: (id: string, version: number, body: OrderInput & {preview_digest: string; idempotency_key: string; confirm_assigned: boolean}) =>
    request<{items:{task_id:string;revision:number}[]}>(`${ver(id,version)}/order-changes/apply`,post(body)),
};
