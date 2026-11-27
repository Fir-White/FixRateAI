import { request } from './request';

const BASE='/api/v1/maintenance/planning/order-table';
export type OrderRow = {
  task_id:string; revision:number; state:string; title:string; equipment:string; system:string;
  due_date:string|null; planned_start:string|null; planned_end:string|null;
  normative_hours:string; normative_unit:string|null; planned_person_hours:string|null;
  note:string; locked_reason:string|null;
};
export type ExistingEdit = {
  kind:'existing'; task_id:string; expected_revision:number;
  planned_start?:string; planned_person_hours?:string|null; note?:string;
};
export type AddedEdit = {
  kind:'new'; binding_id:string; planned_start:string; due_date:string;
  planned_person_hours?:string|null; note?:string;
};
export type SheetEdit = ExistingEdit | AddedEdit;
export type WorksheetRequest = {changes:SheetEdit[]; reason:string};
type Action = 'update'|'create'|'reschedule';
type ChangeResult = {index:number;action:'blocked';issue:string} | {
  index:number;action:Action;task_id:string;title:string;equipment?:string;
  due_date?:string;normative_hours?:string;normative_unit?:string|null;
  planned_start:string|null;planned_end:string|null;before_start?:string|null;before_end?:string|null;
  planned_person_hours?:string|null;before_hours?:string|null;note?:string;before_note?:string;worker_names?:string[];
};
export type WorksheetPreview = {
  can_apply:boolean; requires_assigned_confirmation:boolean; preview_digest:string|null; items:ChangeResult[];
};
type Binding = {binding_id:string; equipment:string; asset_code:string; title:string; code:string};
type Page<T> = {items:T[];has_more:boolean};
const query=(values:Record<string,string|number>)=>new URLSearchParams(Object.entries(values).map(([key,value])=>[key,String(value)])).toString();
const json=(value:object)=>({method:'POST',body:JSON.stringify(value)});

export const orderTableApi={
  rows:(month:string,q:string,offset:number)=>request<Page<OrderRow>&{timezone:string}>(`${BASE}?${query({month,q,offset})}`),
  bindings:(q:string,offset:number)=>request<Page<Binding>>(`${BASE}/bindings?${query({q,offset})}`),
  preview:(body:WorksheetRequest)=>request<WorksheetPreview>(`${BASE}/preview`,json(body),{readOnly:true}),
  apply:(body:WorksheetRequest & {preview_digest:string; idempotency_key:string; confirm_assigned:boolean})=>
    request<{items:{task_id:string;revision:number;action:Action}[];replayed:boolean}>(`${BASE}/apply`,json(body)),
  export:(month:string,q:string)=>`${BASE}/export.xlsx?${query({month,q})}`,
};
