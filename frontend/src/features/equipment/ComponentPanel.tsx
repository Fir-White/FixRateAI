import { useState } from 'react';
import { registryApi } from '@/shared/api/registry';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { useSession } from '@/shared/session/SessionContext';
import { todayAt, formatDate } from '@/shared/lib/format';
import { Button } from '@/shared/ui/Button';
import { Card, CardHeader } from '@/shared/ui/Card';
import { FieldCaption, Input, Select } from '@/shared/ui/Form';
import { FileInput } from '@/shared/ui/FileInput';
import { Callout } from '@/shared/ui/Callout';
import { LoadingState, ErrorState } from '@/shared/ui/States';
import { usageUnits, type ComponentInput, type InstalledComponent } from '@/shared/types/registry';

const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось сохранить';
const blank = (day: string): ComponentInput => ({ position_code: '', name: '', installed_on: day, part_number: null, serial_number: null, usage_unit: 'hour', initial_usage: '', resource_limit: null, resource_basis: null });

export function ComponentPanel({equipmentId, onChanged}: {equipmentId: string; onChanged?: () => void}) {
  const {profile} = useSession();
  const [refresh, setRefresh] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const query = useApiQuery(() => registryApi.components(equipmentId), [equipmentId, refresh]);
  const mayEdit = profile?.role === 'chief_engineer' || profile?.role === 'admin';
  const saved = () => { setRefresh(n => n + 1); setAdding(false); setNotice('Изменения сохранены'); onChanged?.(); };
  const today = todayAt(profile?.timezone ?? 'Asia/Yekaterinburg');
  return <section aria-label="Детали и наработка" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Детали и наработка</h2>{mayEdit && <Button variant="secondary" onClick={() => {setAdding(!adding); setNotice('');}}>Установить деталь</Button>}</div>
    {notice && <Callout tone="success">{notice}</Callout>}
    {adding && <ComponentEditor initial={blank(today)} onCancel={() => setAdding(false)} onSave={async value => {await registryApi.install(equipmentId, value); saved();}}/>}
    {query.status === 'loading' && <LoadingState/>}
    {query.status === 'error' && <ErrorState description={query.error}/>}
    {query.status === 'success' && !query.data.length && <Callout>Детали пока не внесены. Укажите установленную деталь и её известную наработку. Норматив ресурса можно добавить при установке, если есть источник.</Callout>}
    {query.status === 'success' && query.data.map(part => <PartCard key={`${part.component_id}:${part.revision}`} part={part} mayEdit={mayEdit} mayRecord={profile?.role !== 'director'} today={today} onSaved={saved}/>)}
  </section>;
}

function ComponentEditor({initial, onSave, onCancel}: {initial: ComponentInput; onSave: (value: ComponentInput) => Promise<void>; onCancel: () => void}) {
  const [value, setValue] = useState(initial); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const field = (key: keyof ComponentInput, label: string, type = 'text', required = false) => <label className="space-y-1 text-sm"><FieldCaption>{label}</FieldCaption><Input aria-label={label} type={type} required={required} value={value[key] ?? ''} step={type === 'number' ? '0.001' : undefined} min={type === 'number' ? 0 : undefined} onChange={e => setValue({...value, [key]: e.target.value || null})}/></label>;
  return <Card><CardHeader title="Установленная деталь"/><form className="space-y-4 p-5" onSubmit={async e => {e.preventDefault(); if(busy)return; setBusy(true); setError(''); try {await onSave(value);} catch(error){setError(message(error));} finally{setBusy(false);}}}>
    <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
      {field('position_code', 'Позиция в оборудовании', 'text', true)}{field('name', 'Название детали', 'text', true)}
      {field('part_number', 'Артикул детали')}{field('serial_number', 'Серийный номер детали')}{field('installed_on', 'Дата установки', 'date', true)}
      <label className="space-y-1 text-sm"><FieldCaption>Единица наработки</FieldCaption><Select aria-label="Единица наработки" value={value.usage_unit} onChange={e => setValue({...value, usage_unit: e.target.value as ComponentInput['usage_unit']})}><option value="hour">Часы</option><option value="cycle">Циклы</option><option value="km">Километры</option></Select></label>
      {field('initial_usage', 'Наработка при установке', 'number', true)}{field('resource_limit', 'Норматив ресурса, если известен', 'number')}{field('resource_basis', 'Источник норматива ресурса', 'text', value.resource_limit !== null)}
    </fieldset><p className="text-sm text-muted">Позиция обозначает место детали, например «Подшипник двигателя 1». Новое показание — суммарная наработка этой детали, включая начальное значение.</p>
    {error && <p role="alert">{error}</p>}<div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy}>Сохранить деталь</Button><Button variant="ghost" type="button" disabled={busy} onClick={onCancel}>Отмена</Button></div>
  </form></Card>;
}

function PartCard({part, mayEdit, mayRecord, today, onSaved}: {part: InstalledComponent; mayEdit: boolean; mayRecord: boolean; today: string; onSaved: () => void}) {
  const [mode, setMode] = useState<'reading' | 'replace' | 'edit' | null>(null);
  const [reason, setReason] = useState(''); const [date, setDate] = useState(today);
  const unit = usageUnits[part.usage_unit];
  return <Card className="space-y-4 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{part.name}</h3><p className="text-sm text-muted">{part.position_code} · {part.part_number || 'Без артикула'} · установлена {formatDate(part.installed_on)}</p></div><span className="text-sm">{part.removed_on ? `Снята ${formatDate(part.removed_on)}` : 'Установлена'}</span></div>
    <dl className="grid gap-3 sm:grid-cols-3"><div><dt className="text-xs text-muted">Наработка</dt><dd>{Number(part.current_usage).toLocaleString('ru-RU')} {unit}</dd></div><div><dt className="text-xs text-muted">Норматив ресурса</dt><dd>{part.resource_limit === null ? 'Не указан' : `${Number(part.resource_limit).toLocaleString('ru-RU')} ${unit}`}</dd></div><div><dt className="text-xs text-muted">Остаток ресурса</dt><dd className={part.resource_state === 'exhausted' ? 'text-danger' : ''}>{part.remaining_usage === null ? 'Нет норматива' : `${Number(part.remaining_usage).toLocaleString('ru-RU')} ${unit}`}</dd></div></dl>
    {part.resource_basis && <p className="text-xs text-muted">Источник: {part.resource_basis}</p>}
    {part.removal_reason && <p className="text-sm">Причина снятия: {part.removal_reason}</p>}
    {!part.removed_on && <div className="flex flex-wrap gap-2">{mayRecord && <Button variant="secondary" onClick={() => setMode(mode === 'reading' ? null : 'reading')}>Внести наработку</Button>}{mayEdit && <><Button variant="ghost" onClick={() => setMode(mode === 'edit' ? null : 'edit')}>Параметры ресурса</Button><Button variant="ghost" onClick={() => setMode(mode === 'replace' ? null : 'replace')}>Заменить деталь</Button></>}</div>}
    {mode === 'edit' && <ResourceForm part={part} onSaved={onSaved}/>}
    {mode === 'reading' && <ReadingForm part={part} onSaved={onSaved}/>}
    {mode === 'replace' && <div className="space-y-3 border-t border-line pt-4"><label className="block text-sm"><FieldCaption>Дата замены</FieldCaption><Input aria-label="Дата замены" type="date" value={date} max={today} onChange={e => setDate(e.target.value)}/></label><label className="block text-sm"><FieldCaption>Причина замены</FieldCaption><Input aria-label="Причина замены" required value={reason} onChange={e => setReason(e.target.value)}/></label><ComponentEditor key={date} initial={{...blank(date), position_code: part.position_code, name: part.name, part_number: part.part_number, usage_unit: part.usage_unit, resource_limit: part.resource_limit, resource_basis: part.resource_basis}} onCancel={() => setMode(null)} onSave={async replacement => {if(!reason.trim())throw new Error('Укажите причину замены'); await registryApi.replace(part.component_id, {expected_revision: part.revision, removed_on: date, reason, replacement}); onSaved();}}/></div>}
    <details><summary className="cursor-pointer text-sm">История наработки · {part.readings.length}</summary><div className="mt-3 space-y-3">{part.readings.map(reading => <div key={reading.reading_id} className="border-t border-line pt-3 text-sm"><p>{new Date(reading.measured_at).toLocaleString('ru-RU')} · {Number(reading.usage_value).toLocaleString('ru-RU')} {unit}</p><p className="text-muted">{reading.note}</p>{reading.photo_url && <a href={reading.photo_url} target="_blank" rel="noreferrer" className="text-accent underline">Открыть фотографию показания</a>}</div>)}</div></details>
  </Card>;
}

function ResourceForm({part,onSaved}:{part:InstalledComponent;onSaved:()=>void}) {
  const [limit,setLimit]=useState(part.resource_limit??'');const [basis,setBasis]=useState(part.resource_basis??'');const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  return <form className="space-y-3 border-t border-line pt-4" onSubmit={async event=>{event.preventDefault();if(busy)return;setBusy(true);setError('');try{await registryApi.updateComponent(part.component_id,{expected_revision:part.revision,name:part.name,part_number:part.part_number,serial_number:part.serial_number,resource_limit:limit||null,resource_basis:basis||null});onSaved();}catch(error){setError(message(error));}finally{setBusy(false);}}}><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm"><FieldCaption>Норматив ресурса, {usageUnits[part.usage_unit]}</FieldCaption><Input aria-label="Уточнённый норматив ресурса" type="number" min="0.001" step="0.001" value={limit} onChange={event=>setLimit(event.target.value)}/></label><label className="text-sm"><FieldCaption>Источник норматива ресурса</FieldCaption><Input aria-label="Источник уточнённого норматива" required={!!limit} value={basis} onChange={event=>setBasis(event.target.value)}/></label></fieldset>{error&&<p role="alert">{error}</p>}<Button type="submit" disabled={busy}>Сохранить ресурс</Button></form>;
}

function ReadingForm({part, onSaved}: {part: InstalledComponent; onSaved: () => void}) {
  const [value, setValue] = useState(part.current_usage); const [when, setWhen] = useState(() => {const now = new Date(); return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16);});
  const [note, setNote] = useState(''); const [photo, setPhoto] = useState<File | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <form className="space-y-3 border-t border-line pt-4" onSubmit={async e => {e.preventDefault(); if(busy)return; setBusy(true); setError(''); try {await registryApi.reading(part.component_id, {expected_revision: part.revision, measured_at: new Date(when).toISOString(), usage_value: value, note}, photo); onSaved();} catch(error){setError(message(error));} finally{setBusy(false);}}}>
    <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><label className="text-sm"><FieldCaption>Суммарная наработка, {usageUnits[part.usage_unit]}</FieldCaption><Input aria-label="Суммарная наработка" type="number" step="0.001" min={part.current_usage} required value={value} onChange={e => setValue(e.target.value)}/></label><label className="text-sm"><FieldCaption>Время показания по часам устройства</FieldCaption><Input aria-label="Время показания" type="datetime-local" required value={when} onChange={e => setWhen(e.target.value)}/></label><label className="text-sm sm:col-span-2"><FieldCaption>Источник и примечание к показанию</FieldCaption><Input aria-label="Примечание к показанию" required value={note} onChange={e => setNote(e.target.value)}/></label><div className="sm:col-span-2"><FileInput accept="image/jpeg,image/png,image/webp" aria-label="Фотография показания" onChange={e => setPhoto(e.target.files?.[0] ?? null)}/></div></fieldset>
    {error && <p role="alert">{error}</p>}<Button type="submit" disabled={busy}>{busy ? 'Сохранение…' : 'Сохранить показание'}</Button>
  </form>;
}
