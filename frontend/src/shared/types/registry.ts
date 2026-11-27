import type { EquipmentRecord, ServiceConfiguration } from './management';
import type { Role } from './domain';
export type SystemGroup = 'electricity' | 'water' | 'air';
export const systemGroups: Record<SystemGroup, string> = { electricity: 'Электрика', water: 'Вода', air: 'Воздух' };
export type UsageUnit = 'hour' | 'cycle' | 'km';
export const usageUnits: Record<UsageUnit, string> = { hour: 'ч', cycle: 'циклов', km: 'км' };
export interface RegistrySystem { id: string; code: string; name: string; system_group: SystemGroup | null; revision: number; is_active: boolean }
export interface Building { site_id: string; name: string; address: string | null; timezone: string; role: Role }
export interface ComponentInput {
  position_code: string; name: string; part_number: string | null; serial_number: string | null;
  installed_on: string; usage_unit: UsageUnit; initial_usage: string; resource_limit: string | null; resource_basis: string | null;
}
export interface InstalledComponent extends ComponentInput {
  component_id: string; equipment_id: string; revision: number; removed_on: string | null; removal_reason: string | null;
  current_usage: string; remaining_usage: string | null; measured_at: string | null;
  resource_state: 'unknown' | 'available' | 'exhausted' | 'removed';
  readings: { reading_id: string; measured_at: string; usage_value: string; note: string; recorded_at: string; recorded_by: string; photo_url: string | null }[];
}
export interface RegistryItem extends EquipmentRecord { services: ServiceConfiguration[]; components: InstalledComponent[] }
export interface EquipmentRegistry { site_id: string; site_name: string; timezone: string; systems: RegistrySystem[]; items: RegistryItem[] }
