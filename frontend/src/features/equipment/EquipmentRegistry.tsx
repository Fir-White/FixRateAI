import { useDeferredValue, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { registryApi } from '@/shared/api/registry';
import { readQueries } from '@/shared/api/readQueries';
import { isShortString, useWorkspaceState } from '@/shared/lib/workspaceState';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { useSession } from '@/shared/session/SessionContext';
import { canOpenSection } from '@/shared/lib/roles';
import { Button, buttonClassName } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { PageHeader } from '@/shared/ui/PageHeader';
import { FieldCaption, Input, Select } from '@/shared/ui/Form';
import { Callout } from '@/shared/ui/Callout';
import { LoadingState, ErrorState, EmptyState } from '@/shared/ui/States';
import { systemGroups, usageUnits, type RegistryItem, type RegistrySystem, type SystemGroup } from '@/shared/types/registry';
import { ComponentPanel } from './ComponentPanel';
import { RegistryExcel } from './RegistryExcel';
import './registry.css';

const failure = (error: unknown) => error instanceof Error ? error.message : 'Не удалось сохранить';
export function EquipmentRegistry() {
  const {profile, switchSite} = useSession();
  const [refresh, setRefresh] = useState(0);
  const [group, setGroup] = useWorkspaceState<SystemGroup | 'unclassified' | 'all'>('registry.group', 'all', (value): value is SystemGroup | 'unclassified' | 'all' => typeof value === 'string' && ['electricity','water','air','unclassified','all'].includes(value));
  const [page, setPage] = useWorkspaceState('registry.page', 1, (value): value is number => Number.isSafeInteger(value) && Number(value) > 0 && Number(value) <= 100_000);
  const [search, setSearch] = useWorkspaceState('registry.search', '', isShortString); const [selected, setSelected] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const mayEdit = profile?.role === 'chief_engineer' || profile?.role === 'admin';
  const query = useApiQuery(readQueries.registry.load, [profile?.siteId, refresh], undefined, readQueries.registry.key);
  const systems = query.data?.registry.systems ?? [];
  const all = query.data?.registry.items ?? [];
  const needle = useDeferredValue(search.trim().toLocaleLowerCase('ru'));
  const systemIndex = useMemo(() => new Map(systems.map(system => [system.id, system])), [systems]);
  const indexed = useMemo(() => all.map(item => ({item,
    group: systemIndex.get(item.system_id)?.system_group ?? ('unclassified' as const),
    text: [item.name, item.asset_code, item.location, ...item.services.map(service => service.title),
      ...item.components.map(part => part.name)].join(' ').toLocaleLowerCase('ru'),
  })), [all, systemIndex]);
  const counts = useMemo(() => {
    const counts = {electricity: 0, water: 0, air: 0, unclassified: 0};
    indexed.forEach(row => { counts[row.group]++; });
    return counts;
  }, [indexed]);
  const items = useMemo(() => indexed.filter(row => (group === 'all' || row.group === group) && (!needle || row.text.includes(needle))).map(row => row.item), [indexed, group, needle]);
  const pages = Math.max(1, Math.ceil(items.length / 25));
  const currentPage = Math.min(page, pages);
  const visible = items.slice((currentPage - 1) * 25, currentPage * 25);
  const active = all.find(row => row.equipment_id === selected);
  return <div className="space-y-6 registry-page"><PageHeader title="Оборудование" description="Реестр, инженерные системы и наработка деталей по зданиям." actions={mayEdit ? <Link to="/settings/equipment" className={buttonClassName('primary')}>Добавить оборудование</Link> : undefined}/>
    {error && <p role="alert"><Callout tone="danger">{error}</Callout></p>}
    {query.status === 'loading' && <LoadingState/>}{query.status === 'error' && <ErrorState description={query.error}/>}
    {query.status === 'success' && <>
      <Card className="space-y-4 p-5"><div className="registry-tools"><label className="space-y-1 text-sm"><FieldCaption>Здание</FieldCaption><Select aria-label="Здание" value={query.data.registry.site_id} disabled={busy} onChange={async e => {setBusy(true); setError(''); try{await switchSite(e.target.value);}catch(error){setError(failure(error));setBusy(false);}}}>{query.data.sites.map(site => <option key={site.site_id} value={site.site_id}>{site.name}</option>)}</Select></label><label className="space-y-1 text-sm"><FieldCaption>Поиск оборудования, работы или детали</FieldCaption><Input aria-label="Поиск по реестру" value={search} onChange={e => {setSearch(e.target.value);setPage(1);setSelected('');}} placeholder="Название, номер или расположение"/></label></div>
        {mayEdit && <BuildingForm timezone={profile?.timezone ?? 'Asia/Yekaterinburg'} onSaved={() => setRefresh(n => n+1)}/>}
        <div className="registry-tabs" role="tablist" aria-label="Инженерные системы"><Button role="tab" id="registry-tab-all" aria-controls="registry-table-panel" aria-selected={group==='all'} variant={group==='all'?'primary':'ghost'} onClick={()=>{setGroup('all');setPage(1);setSelected('');}}>Все системы <span>{all.length}</span></Button>{(Object.entries(systemGroups) as [SystemGroup, string][]).map(([key, label]) => <Button key={key} role="tab" id={`registry-tab-${key}`} aria-controls="registry-table-panel" aria-selected={group === key} variant={group === key ? 'primary' : 'ghost'} onClick={() => {setGroup(key);setPage(1);setSelected('');}}>{label} <span>{counts[key]}</span></Button>)}<Button role="tab" id="registry-tab-unclassified" aria-controls="registry-table-panel" aria-selected={group === 'unclassified'} variant={group === 'unclassified' ? 'primary' : 'ghost'} onClick={() => {setGroup('unclassified');setPage(1);setSelected('');}}>Без группы <span>{counts.unclassified}</span></Button></div>
      </Card>
      {systems.some(system => !system.system_group) && <Callout>Есть системы без группы. Их оборудование сохранено во вкладке «Без группы». {mayEdit ? 'Укажите группу ниже, чтобы распределить его по таблицам.' : 'Главный инженер может указать группу системы.'}</Callout>}
      {mayEdit && <SystemGroups systems={systems} onSaved={() => setRefresh(n => n+1)}/>}
      <div id="registry-table-panel" role="tabpanel" aria-labelledby={`registry-tab-${group}`}>
        {!items.length ? <EmptyState title="В этой таблице пока нет оборудования" description={search ? 'Измените поисковый запрос.' : 'Добавьте оборудование или укажите группу существующей системы.'}/> : <Card className="overflow-hidden"><div className="registry-scroll"><table className="registry-table" aria-label={`${group === 'all' ? 'Все системы' : group === 'unclassified' ? 'Без группы' : systemGroups[group]} — работы и оборудование`}><thead><tr><th>Оборудование</th><th>Работы и периодичность</th><th>Трудозатраты на одно ТО</th><th>Детали и наработка</th><th><span className="sr-only">Действия</span></th></tr></thead><tbody>{visible.map(item => <RegistryRow key={item.equipment_id} item={item} system={systemIndex.get(item.system_id)} selected={selected === item.equipment_id} canConfigure={canOpenSection(profile?.role,'service_settings')} onSelect={() => setSelected(selected === item.equipment_id ? '' : item.equipment_id)}/>)}</tbody></table></div></Card>}
      </div>
      {items.length > 25 && <nav aria-label="Страницы оборудования" className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted" aria-live="polite">{(currentPage-1)*25+1}–{Math.min(currentPage*25,items.length)} из {items.length} · Страница {currentPage} из {pages}</p>
        <div className="flex gap-2"><Button variant="secondary" disabled={currentPage === 1} onClick={() => {setPage(currentPage-1);setSelected('');}}>Предыдущая страница оборудования</Button><Button variant="secondary" disabled={currentPage === pages} onClick={() => {setPage(currentPage+1);setSelected('');}}>Следующая страница оборудования</Button></div>
      </nav>}
      {active && <section className="space-y-4" aria-label={`Детали: ${active.name}`}><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">{active.name} · {active.asset_code}</h2>{mayEdit && <Link to={`/settings/equipment?equipment=${encodeURIComponent(active.equipment_id)}`} className={buttonClassName('secondary')}>Настроить оборудование и работы</Link>}</div><ComponentPanel equipmentId={active.equipment_id} onChanged={() => setRefresh(n => n+1)}/></section>}
      <RegistryExcel mayImport={mayEdit} onSaved={() => setRefresh(n => n+1)}/>
      {canOpenSection(profile?.role,"planning")&&<Link to="/planning" className={buttonClassName('ghost')}>Перейти в планирование →</Link>}
    </>}
  </div>;
}

function RegistryRow({item, system, selected, canConfigure, onSelect}: {item: RegistryItem; system?: RegistrySystem; selected: boolean; canConfigure: boolean; onSelect: () => void}) {
  const totals = new Map<string, {hours: number; incomplete: boolean}>();
  for(const service of item.services) { const total = totals.get(service.maintenance_type) ?? {hours: 0, incomplete: false};
    if(service.norm_unit === 'person_hour' && service.norm_value !== null) total.hours += Number(service.norm_value); else total.incomplete = true;
    totals.set(service.maintenance_type, total);
  }
  return <tr><td><Link className="font-semibold text-accent" to={`/equipment/${encodeURIComponent(item.equipment_id)}`}>{item.name}</Link><p className="font-mono">{item.asset_code}</p><p>{system?.name} · {item.location || 'Расположение не указано'}</p>{item.status !== 'active' && <p>{item.status === 'retired' ? 'Списано' : 'В ремонте'}</p>}</td>
    <td>{!item.services.length ? 'Регламенты не заданы' : item.services.map(service => <div key={service.binding_id} className="registry-operation"><strong>{service.maintenance_type} · {service.title}</strong><p>{service.source_text || 'Периодичность не указана'}</p><p>{service.norm_value ?? 'Нет нормы'} {service.norm_unit === 'person_hour' ? 'чел.-ч' : service.norm_unit === 'elapsed_hour' ? 'ч длительности' : '(единица не подтверждена)'} · {service.crew_size} чел. · {service.enabled ? 'Действует' : 'Черновик'}</p></div>)}</td>
    <td>{[...totals].map(([type, value]) => <p key={type}><strong>{type}: {value.hours.toLocaleString('ru-RU')} чел.-ч</strong>{value.incomplete && <small>Известная часть; есть неподтверждённые нормы</small>}</p>)}{!totals.size && 'Нет данных'}<small>Дневная и месячная нагрузка — в календаре.</small></td>
    <td>{item.components.filter(part => !part.removed_on).map(part => <p key={part.component_id}><strong>{part.name}</strong><br/>{Number(part.current_usage).toLocaleString('ru-RU')} {usageUnits[part.usage_unit]} · {part.remaining_usage === null ? 'Ресурс не задан' : `остаток ${Number(part.remaining_usage).toLocaleString('ru-RU')} ${usageUnits[part.usage_unit]}`}</p>)}{!item.components.some(part => !part.removed_on) && 'Не внесены'}</td>
    <td><Button variant="secondary" aria-expanded={selected} onClick={onSelect}>{selected ? 'Скрыть детали' : 'Детали и наработка'}</Button>{canConfigure && <Link className="mt-3 block text-accent underline" to={`/settings/equipment?equipment=${encodeURIComponent(item.equipment_id)}`}>Работы и регламенты</Link>}</td></tr>;
}

function SystemGroups({systems, onSaved}: {systems: RegistrySystem[]; onSaved: () => void}) {
  const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  return <details className="fr-rule-section"><summary>Группы инженерных систем</summary><div className="space-y-3 p-4">{systems.map(system => <label className="registry-tools text-sm" key={system.id}><span>{system.name} · {system.code}{!system.is_active ? ' (неактивна)' : ''}</span><Select aria-label={`Группа системы ${system.name}`} value={system.system_group ?? ''} disabled={!!busy} onChange={async e => {setBusy(system.id);setError('');try{await registryApi.classify(system.id, system.revision, (e.target.value || null) as SystemGroup | null);onSaved();}catch(error){setError(failure(error));}finally{setBusy('');}}}><option value="">Без группы</option>{Object.entries(systemGroups).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></label>)}{error && <p role="alert">{error}</p>}</div></details>;
}

function BuildingForm({timezone, onSaved}: {timezone: string; onSaved: () => void}) {
  const [name, setName] = useState(''); const [address, setAddress] = useState(''); const [zone, setZone] = useState(timezone);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  return <details><summary className="cursor-pointer text-sm text-accent">Добавить здание</summary><form className="mt-4 space-y-3" onSubmit={async e => {e.preventDefault();if(busy)return;setBusy(true);setError('');try{await registryApi.createBuilding({name,address: address || null,timezone: zone});setName('');setAddress('');setNotice('Здание создано и доступно в списке. Доступ сотрудников настраивается отдельно.');onSaved();}catch(error){setError(failure(error));}finally{setBusy(false);}}}><p className="text-sm text-muted">Создатель и действующие администраторы текущего здания получат доступ к новому. Роли остальных сотрудников не переносятся.</p><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3"><label className="text-sm"><FieldCaption>Название здания</FieldCaption><Input aria-label="Название здания" required value={name} onChange={e => setName(e.target.value)}/></label><label className="text-sm"><FieldCaption>Адрес здания</FieldCaption><Input aria-label="Адрес здания" value={address} onChange={e => setAddress(e.target.value)}/></label><label className="text-sm"><FieldCaption>Часовой пояс здания</FieldCaption><Input aria-label="Часовой пояс здания" required value={zone} onChange={e => setZone(e.target.value)}/></label></fieldset>{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}<Button variant="secondary" type="submit" disabled={busy}>Создать здание</Button></form></details>;
}
