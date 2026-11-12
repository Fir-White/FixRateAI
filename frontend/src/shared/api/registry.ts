import { request } from './request';
import type { Building, ComponentInput, EquipmentRegistry, InstalledComponent, SystemGroup } from '../types/registry';
const base = '/api/v1/maintenance';
const send = <T>(path: string, method: string, body: unknown) => request<T>(base + path, { method, body: JSON.stringify(body) });
export interface ExcelPreview {format: string; preview_token: string; can_import: boolean; warnings: string[]; errors: {sheet: string; row: number; message: string}[]; rows: {sheet: string; row: number; action: string; label: string; changes?: string[]}[]}
export const registryApi = {
  load: () => request<EquipmentRegistry>(base + '/registry', { cache: 'no-store' }),
  sites: () => request<Building[]>('/api/v1/auth/sites', { cache: 'no-store' }),
  createBuilding: (body: {name: string; address: string | null; timezone: string}) => send<Building>('/registry/buildings', 'POST', body),
  classify: (id: string, expected_revision: number, system_group: SystemGroup | null) => send(`/registry/systems/${encodeURIComponent(id)}`, 'PATCH', { expected_revision, system_group }),
  components: (id: string) => request<InstalledComponent[]>(`${base}/equipment/${encodeURIComponent(id)}/components`),
  previewExcel: (file: File) => { const data = new FormData(); data.set('file',file); return request<ExcelPreview>(base+'/registry/excel/preview',{method:'POST',body:data}); },
  importExcel: (file: File, token: string) => { const data = new FormData(); data.set('file',file);data.set('preview_token',token); return request<{imported:number;unchanged:number}>(base+'/registry/excel/import',{method:'POST',body:data}); },
  downloadExcel: async (template = false) => {
    const response = await fetch(base+'/registry/excel'+(template?'?template=true':''), {credentials:'same-origin'});
    if(!response.ok) throw new Error('Не удалось скачать Excel');
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href=url; link.download=template?'fixrate-registry-template.xlsx':'fixrate-registry.xlsx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  },
  install: (id: string, body: ComponentInput) => send<InstalledComponent>(`/equipment/${encodeURIComponent(id)}/components`, 'POST', body),
  updateComponent: (id: string, body: Pick<ComponentInput,'name'|'part_number'|'serial_number'|'resource_limit'|'resource_basis'> & {expected_revision:number}) => send<InstalledComponent>(`/registry/components/${encodeURIComponent(id)}`, 'PATCH', body),
  replace: (id: string, body: {expected_revision: number; removed_on: string; reason: string; replacement: ComponentInput | null}) => send(`/registry/components/${encodeURIComponent(id)}/replace`, 'POST', body),
  reading: (id: string, body: {expected_revision: number; measured_at: string; usage_value: string; note: string}, photo: File | null) => {
    const data = new FormData(); data.set('payload', JSON.stringify(body)); if (photo) data.set('photo', photo);
    return request<InstalledComponent>(`${base}/registry/components/${encodeURIComponent(id)}/readings`, {method: 'POST', body: data});
  },
};
