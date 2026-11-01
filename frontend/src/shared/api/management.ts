import { request } from "./request";
import type { EquipmentRecord, EquipmentInput, ManagementCatalog, ServiceConfiguration, ShiftRule, Workforce,CalendarPattern } from "@/shared/types/management";
import type { Role } from "@/shared/types/domain";

const base = "/api/v1/maintenance";
const id = encodeURIComponent;
const send = <T>(url: string, method: string, body: unknown) => request<T>(base + url, {method, body: JSON.stringify(body)});
export const managementApi = {
  previewPattern:(pattern:CalendarPattern,year:number,month:number)=>send<{dates:string[];explanation:string;timezone:string}>("/management/calendar-pattern/preview","POST",{pattern,year,month}),
  catalog: () => request<ManagementCatalog>(base + "/management/catalog"),
  equipment: () => request<{items: EquipmentRecord[]; total: number}>(base + "/equipment?limit=100"),
  getEquipment: (key: string) => request<EquipmentRecord>(`${base}/equipment/${id(key)}`),
  saveEquipment: (body: EquipmentInput, key?: string) => send<EquipmentRecord>(`/equipment${key ? "/"+id(key) : ""}`,key ? "PATCH" : "POST",body),
  createReference: (kind: "systems" | "equipment-types" | "skills", body: {code: string; name: string; validity_required?: boolean}) => send<{id: string}>(`/management/${kind}`,"POST",body),
  services: (key: string) => request<ServiceConfiguration[]>(`${base}/equipment/${id(key)}/service-configurations`),
  saveService: (key: string, body: ServiceConfiguration, binding?: string) => {
    const {binding_id: _binding,revision: _revision,rule_version: _version,source_text: _source,...input}=body;
    return send<ServiceConfiguration>(`/equipment/${id(key)}/service-configurations${binding ? "/"+id(binding) : ""}`,binding ? "PUT" : "POST",input);
  },
  workforce: () => request<Workforce>(base + "/management/workforce"),
  enrollment: () => request<{code: string | null}>(base + "/management/enrollment"),
  createEnrollment: () => send<{code: string}>("/management/enrollment","POST",{}),
  decideApplication: (key: string, revision: number, role: Role, decision: "accepted" | "rejected", employedFrom: string) => send(`/management/applications/${id(key)}/decision`,"POST",{
    expected_revision: revision, role, decision, is_active: true, employed_from: employedFrom,
  }),
  saveStaff: (key: string, body: {expected_revision: number; role: Role; is_active: boolean; employed_from: string | null; employed_until: string | null}) => send(`/management/staff/${id(key)}`,"PUT",body),
  saveShift: (user: string, body: ShiftRule) => {
    const {shift_rule_id: key, revision: _revision, ...input}=body;
    return send(`/management/staff/${id(user)}/shifts${key ? "/"+id(key) : ""}`,key ? "PUT" : "POST",input);
  },
  availability: (user: string, body: {start_local: string; end_local: string; status: "available" | "unavailable"; reason: string}) => send(`/management/staff/${id(user)}/availability`,"POST",body),
  qualification: (user: string, skill: string, body: {verified_local: string; valid_until: string | null;expected_revision?:number}) => send(`/management/staff/${id(user)}/qualifications/${id(skill)}`,"PUT",body),
  revokeQualification:(user:string,skill:string,revision:number)=>send(`/management/staff/${id(user)}/qualifications/${id(skill)}/revoke`,"POST",{expected_revision:revision}),
  cancelAvailability: (user:string,key:string,revision:number) => send(`/management/staff/${id(user)}/availability/${id(key)}/cancel?expected_revision=${revision}`,"POST",{}),
  saveCrew: (body: Omit<import("@/shared/types/management").CrewRecord,"id" | "revision"> & {expected_revision?: number}, key?: string) => send(`/management/crews${key ? "/"+id(key) : ""}`,key ? "PUT" : "POST",body),
  workerCalendar: (key: string, start: string, end: string) => request<{intervals: {start_at: string; end_at: string; status: string}[]; diagnostics: {date: string; explanation: string}[]}>(`${base}/management/staff/${id(key)}/calendar?start=${start}&end=${end}`),
  register: (body: {full_name: string; email: string; password: string; company_code: string}) => request<{message: string}>("/api/v1/auth/register",{method: "POST",body: JSON.stringify(body)}),
};
