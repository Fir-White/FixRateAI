import type { Role } from "./domain";

export interface CalendarPattern {
  frequency: "day" | "week" | "month" | "quarter" | "year" | "yearly_count" | "dates";
  anchor_date: string;
  interval: number;
  weekdays: number[];
  week_parity: "any" | "even" | "odd";
  month_days: number[];
  months: number[];
  period_edge: "start" | "end";
  short_month: "last_day" | "skip";
  quarter_policy?: "calendar_edge" | "rolling_months";
  annual_policy?: "calendar_year" | "from_anchor";
  weekend_policy?: "none" | "next_workday";
  count_per_year: number | null;
  dates: string[];
  excluded_dates: string[];
}
export const patternDefaults = (day: string, frequency: CalendarPattern["frequency"] = "week"): CalendarPattern => ({
  frequency, anchor_date: day, interval: 1, weekdays: frequency === "week" ? [1,2,3,4,5] : [],
  week_parity: "any", month_days: [], months: [], period_edge: "end", short_month: "last_day",
  count_per_year: frequency === "yearly_count" ? 5 : null, dates: [], excluded_dates: [],
});
export interface Reference { id: string; code: string; name: string; validity_required?: boolean }
export interface ManagementCatalog { systems: Reference[]; equipment_types: Reference[]; skills: Reference[];
  operations: {id:string;system_id:string;code:string;title:string;instructions:string;maintenance_type:"ТО1"|"ТО2"}[];
}
export interface EquipmentRecord {
  equipment_id: string; site_id: string; system_id: string; equipment_type_id: string | null;
  parent_equipment_id: string | null; asset_code: string; name: string; serial_number: string | null;
  commissioned_on: string | null; location: string | null; status: "active" | "under_repair" | "retired";
  properties: Record<string, unknown>; revision: number;
}
export type EquipmentInput = Omit<EquipmentRecord, "equipment_id" | "site_id" | "revision" | "properties"> & {
  data_origin: "customer" | "synthetic_demo"; expected_revision?: number;
};
export interface ServiceConfiguration {
  binding_id?: string; operation_id?: string; revision?: number; rule_version?: number; expected_revision?: number;
  code: string; title: string; instructions: string; maintenance_type: "ТО1" | "ТО2";
  pattern: CalendarPattern | null; valid_from: string; valid_until: string | null; crew_size: number;
  basis?: "fixed_calendar" | "after_accepted_completion";
  norm_value: string | null; norm_unit: "person_hour" | "elapsed_hour" | "unconfirmed";
  duration_minutes: number | null; qualification_ids: string[]; checklist: ChecklistSetting[]; allowed_lead_days: number;
  enabled: boolean; source_text?: string;
  methodology_ref?:string|null; measurement_requirements?:MeasurementRequirement[]; required_acts?:string[];
}
export interface ChecklistSetting {
  source_item_key?:string|null;source_refs?:string[];
  text:string;answer_kind:"boolean"|"number"|"text";unit:string|null;required:boolean;
  visual_verifiability:"visible"|"partial"|"not_verifiable";photo_required:boolean;
}
export interface ShiftRule {
  shift_rule_id?: string; label: string; pattern: CalendarPattern; valid_from: string; valid_until: string | null;
  starts_local: string; ends_local: string; status: "available" | "unavailable"; is_active: boolean; revision?: number; expected_revision?: number;
}
export interface StaffMember {
  user_id: string; full_name: string; email: string; role: Role; is_active: boolean; revision: number;
  employed_from: string | null; employed_until: string | null; shifts: ShiftRule[];
  qualifications: {skill_id: string; verified_at: string | null; valid_until: string | null;revision:number}[];
  exceptions: {id: string; start_at: string; end_at: string; status: "available" | "unavailable"; reason: string; revision:number}[];
}
export interface CrewRecord {
  id: string; name: string; is_active: boolean; revision: number;
  members: {user_id: string; valid_from: string; valid_to: string | null}[];
}
export interface Workforce {
  staff: StaffMember[]; crews: CrewRecord[]; skills: Reference[]; timezone: string;
  applications: {application_id: string; user_id: string; full_name: string; email: string; revision: number}[];
}

export interface MeasurementRequirement {parameter_code:string;unit:string;required:boolean;phases:("before"|"after")[];minimum?:string|null;maximum?:string|null;}
