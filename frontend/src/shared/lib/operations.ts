import type { MaintenanceTask, TaskState } from "@/shared/types/domain";
import { dateTimeFormatter } from "./dateTimeFormatter";

/** The shipped fixture snapshot is October 2026, not the user's live clock. */
export const DEMO_DATE = "2026-10-30";
export type TaskFilter = "all" | "attention" | "unassigned" | "overdue" | TaskState;
export const TASK_FILTERS: readonly {value: TaskFilter; label: string}[] = [
  {value:"all",label:"Все наряды"}, {value:"attention",label:"Требуют внимания"},
  {value:"unassigned",label:"Без исполнителя"}, {value:"overdue",label:"Просрочено"},
  {value:"draft",label:"Черновик"}, {value:"assigned",label:"Назначено"},
  {value:"in_progress",label:"В работе"}, {value:"submitted",label:"На проверке"},
  {value:"rework_required",label:"На доработке"}, {value:"accepted",label:"Принято"},
  {value:"cancelled",label:"Отменено"},
];
export const isTaskFilter = (value: unknown): value is TaskFilter => TASK_FILTERS.some(item=>item.value===value);
export const isOpenTask = (task: MaintenanceTask) => task.state!=="accepted" && task.state!=="cancelled";
export const isUnassigned = (task: MaintenanceTask) => task.state==="draft" && task.assignees.length===0;
export const isTaskOverdue = (task: MaintenanceTask) => isOpenTask(task) && (task.isOverdue || task.deadlineBreached);
export function matchesTaskFilter(task: MaintenanceTask, filter: TaskFilter): boolean {
  switch(filter) {
    case "all": return true;
    case "unassigned": return isUnassigned(task);
    case "overdue": return isTaskOverdue(task);
    case "attention": return isTaskOverdue(task) || isUnassigned(task) || task.state==="submitted" || task.state==="rework_required";
    default: return task.state===filter;
  }
}
export function isDateKey(value: unknown): value is string {
  if(typeof value!=="string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const date=new Date(`${value}T12:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0,10)===value && +value.slice(0,4)>=2000 && +value.slice(0,4)<=2200;
}
export function dayAt(value: string, timezone: string): string {
  const parts=dateTimeFormatter("en-CA",{timeZone:timezone,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date(value));
  return ["year","month","day"].map(key=>parts.find(part=>part.type===key)!.value).join("-");
}
/** Planned date is displayed as a plan, never as a replacement for mandatoryDueDate. */
export function taskWorkDate(task: MaintenanceTask, timezone: string): string | null {
  return task.scheduledStart ? dayAt(task.scheduledStart,timezone) : task.mandatoryDueDate;
}
export function shiftDay(date: string, delta: number): string {
  const value=new Date(`${date}T12:00:00Z`); value.setUTCDate(value.getUTCDate()+delta); return value.toISOString().slice(0,10);
}
export function weekFor(date: string): string[] {
  const day=new Date(`${date}T12:00:00Z`).getUTCDay();
  const monday=shiftDay(date,-((day+6)%7)); return Array.from({length:7},(_,i)=>shiftDay(monday,i));
}
export function dateLabel(date: string, options: Intl.DateTimeFormatOptions): string {
  return dateTimeFormatter("ru-RU",{...options,timeZone:"UTC"}).format(new Date(`${date}T12:00:00Z`));
}
export function taskPriority(task: MaintenanceTask): number {
  return isTaskOverdue(task)?0:task.state==="rework_required"?1:task.state==="in_progress"?2:isUnassigned(task)?3:task.state==="submitted"?4:5;
}
