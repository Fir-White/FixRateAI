import { memo, useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { orderTableApi, type AddedEdit, type ExistingEdit, type OrderRow, type SheetEdit, type WorksheetPreview, type WorksheetRequest } from '@/shared/api/orderTable';
import { ApiError } from '@/shared/api/request';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button, buttonClassName } from '@/shared/ui/Button';
import { Input } from '@/shared/ui/Form';
import { Modal } from '@/shared/ui/Modal';
import { OrderTablePreview, formatOrderTime, orderNormUnits } from '@/shared/ui/OrderTablePreview';
import { LoadingState } from '@/shared/ui/States';

const PAGE=25, LIMIT=12;
const stateNames:Record<string,string>={draft:'Черновик',assigned:'Назначено',in_progress:'В работе',in_review:'На проверке',completed:'Принято',cancelled:'Отменено',rework:'На доработке',clarification:'Уточнение'};
const cell='border-b border-line px-3 py-2 align-top';
const empty=() : AddedEdit => ({kind:'new',binding_id:'',planned_start:'',due_date:'',planned_person_hours:null,note:''});
const failure=(error:unknown)=>error instanceof Error?error.message:'Не удалось выполнить действие';
type Changes=Record<string,{change:ExistingEdit;assigned:boolean}>;
type NewDraft={id:string;change:AddedEdit};
type Pending={request:WorksheetRequest;result:WorksheetPreview;key:string;added:string[]};

const WorkRow=memo(function WorkRow({row,change,busy,allowMove,edit,reset,move}:{
  row:OrderRow;change?:ExistingEdit;busy:boolean;allowMove:boolean;
  edit:(row:OrderRow,patch:Partial<ExistingEdit>)=>void;reset:(id:string)=>void;move:(change:ExistingEdit)=>void;
}){
  const assigned=row.state==='assigned', stale=Boolean(change&&change.expected_revision!==row.revision);
  const locked=row.locked_reason||stale, code=row.task_id.slice(0,8);
  const start=change?.planned_start??row.planned_start??'';
  const hours=change && 'planned_person_hours' in change ? change.planned_person_hours : row.planned_person_hours;
  return <tr>
    <th scope="row" className={`${cell} text-left font-normal`}><Link className="fr-text-link font-semibold" to={`/tasks/${row.task_id}`}>{row.title}</Link><p className="text-xs text-muted">{code} · {row.equipment}</p><p className="text-xs">{stateNames[row.state]??row.state}</p></th>
    <td className={cell}>{locked?<span>{formatOrderTime(row.planned_start)}</span>:<Input type="datetime-local" aria-label={`Плановое начало · ${code}`} value={start} disabled={busy} onChange={e=>edit(row,{planned_start:e.target.value})}/>}</td>
    <td className={cell}><p>{row.due_date??'—'}</p><p className="text-xs text-muted">{row.normative_hours} {row.normative_unit?orderNormUnits[row.normative_unit]??'': ''}</p></td>
    <td className={cell}>{locked||assigned?<span>{row.planned_person_hours??'—'}</span>:<Input type="number" min="0.01" max="9999" step="0.01" aria-label={`План, чел.-ч · ${code}`} value={hours??''} disabled={busy} onChange={e=>edit(row,{planned_person_hours:e.target.value||null})}/>}</td>
    <td className={cell}>{locked||assigned?<span className="break-words">{row.note||'—'}</span>:<Input aria-label={`Примечание · ${code}`} maxLength={500} value={change?.note??row.note} disabled={busy} onChange={e=>edit(row,{note:e.target.value})}/>}</td>
    <td className={cell}>{stale?<p className="text-xs text-danger">Наряд изменился. Сверьте сохранённые данные и введите правку заново.</p>:row.locked_reason?<p className="text-xs text-muted">{row.locked_reason}</p>:assigned&&change?<Button size="sm" variant="secondary" disabled={busy||!allowMove||!start} onClick={()=>move(change)}>Проверить перенос</Button>:null}
      {locked&&change&&<div className="mt-2 max-w-xs space-y-1 break-words text-xs">
        <p className="font-semibold">Несохранённые правки</p>
        {change.planned_start&&<p>Начало: {formatOrderTime(change.planned_start)}</p>}
        {'planned_person_hours' in change&&<p>План, чел.-ч: {change.planned_person_hours??'очистить'}</p>}
        {'note' in change&&<p>Примечание: {change.note||'очистить'}</p>}
      </div>}
      {change&&<Button size="sm" variant="ghost" disabled={busy} onClick={()=>reset(row.task_id)} aria-label={`Сбросить правку · ${code}`}>Сбросить</Button>}</td>
  </tr>;
});

function NewRows({items,change,remove,disabled}:{items:NewDraft[];change:(id:string,patch:Partial<AddedEdit>)=>void;remove:(id:string)=>void;disabled:boolean}){
  const [input,setInput]=useState(''),[q,setQ]=useState(''),[offset,setOffset]=useState(0);
  const found=useApiQuery(()=>orderTableApi.bindings(q,offset),[q,offset],undefined,`order-table:bindings:${q}:${offset}`);
  const bindings=found.data?.items??[];
  return <section aria-label="Новые строки" className="space-y-3 rounded-2xl border border-line p-4">
    <h3 className="font-semibold">Новые разовые наряды</h3>
    <form className="flex flex-wrap items-end gap-2" onSubmit={e=>{e.preventDefault();setQ(input.trim());setOffset(0);}}>
      <label className="min-w-0 flex-1 text-sm">Поиск регламента или оборудования<Input type="search" maxLength={120} value={input} onChange={e=>setInput(e.target.value)}/></label>
      <Button type="submit" variant="secondary">Найти привязки</Button>
    </form>
    {found.status==='error'&&<p role="alert">{found.error}</p>}
    {found.status==='success'&&bindings.length===0&&<p className="text-sm text-muted">Нет подходящих утверждённых привязок.</p>}
    <div className="flex gap-2">
      <Button size="sm" variant="ghost" disabled={!offset} onClick={()=>setOffset(n=>n-PAGE)}>Назад по привязкам</Button>
      <Button size="sm" variant="ghost" disabled={!found.data?.has_more} onClick={()=>setOffset(n=>n+PAGE)}>Дальше по привязкам</Button>
    </div>
    {items.map(({id,change:row},index)=><fieldset key={id} disabled={disabled} className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-2 xl:grid-cols-3">
      <legend className="px-2 text-sm font-semibold">Строка {index+1}</legend>
      <label className="min-w-0 text-sm">Регламент и оборудование
        <select className="mt-1 w-full rounded-lg border border-line bg-surface p-2" value={row.binding_id} onChange={e=>change(id,{binding_id:e.target.value})}>
          <option value="">Выберите привязку</option>
          {row.binding_id&&!bindings.some(item=>item.binding_id===row.binding_id)&&<option value={row.binding_id}>Выбранная привязка</option>}
          {bindings.map(item=><option key={item.binding_id} value={item.binding_id}>{item.asset_code} · {item.equipment} — {item.title}</option>)}
        </select>
      </label>
      <label className="min-w-0 text-sm">Плановое начало<Input type="datetime-local" value={row.planned_start} onChange={e=>change(id,{planned_start:e.target.value})}/></label>
      <label className="min-w-0 text-sm">Обязательный срок<Input type="date" value={row.due_date} onChange={e=>change(id,{due_date:e.target.value})}/></label>
      <label className="min-w-0 text-sm">План, чел.-ч<Input type="number" min="0.01" max="9999" step="0.01" value={row.planned_person_hours??''} onChange={e=>change(id,{planned_person_hours:e.target.value||null})}/></label>
      <label className="min-w-0 text-sm">Примечание<Input maxLength={500} value={row.note??''} onChange={e=>change(id,{note:e.target.value})}/></label>
      <div className="self-end"><Button variant="ghost" onClick={()=>remove(id)}>Убрать новую строку</Button></div>
    </fieldset>)}
  </section>;
}

export function OrderTable({month,onMonth,timezone}:{month:string;onMonth:(value:string)=>void;timezone:string}){
  const [needle,setNeedle]=useState(''),[q,setQ]=useState(''),[offset,setOffset]=useState(0),[reload,setReload]=useState(0);
  const [edits,setEdits]=useState<Changes>({}),[added,setAdded]=useState<NewDraft[]>([]),[reason,setReason]=useState('');
  const [pending,setPending]=useState<Pending|null>(null),[agreed,setAgreed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[finish,setFinish]=useState<{task_id:string}[]>([]);
  const rows=useApiQuery(()=>orderTableApi.rows(month,q,offset),[month,q,offset,reload],undefined,`order-table:${month}:${q}:${offset}`);
  const draftChanges=Object.values(edits).filter(item=>!item.assigned).map(item=>item.change);
  const total=draftChanges.length+added.length;
  const moveCount=Object.values(edits).filter(item=>item.assigned).length;
  const edit=useCallback((row:OrderRow,patch:Partial<ExistingEdit>)=>setEdits(prev=>{
    const old=prev[row.task_id];
    if(old&&old.change.expected_revision!==row.revision)return prev;
    const change:ExistingEdit={...old?.change,...patch,kind:'existing',task_id:row.task_id,expected_revision:row.revision};
    if(change.planned_start===row.planned_start||change.planned_start==='')delete change.planned_start;
    if(change.planned_person_hours===row.planned_person_hours)delete change.planned_person_hours;
    if(change.note===row.note)delete change.note;
    if(Object.keys(change).length>3)return {...prev,[row.task_id]:{change,assigned:row.state==='assigned'}};
    const copy={...prev};delete copy[row.task_id];return copy;
  }),[]);
  const reset=useCallback((id:string)=>setEdits(prev=>{const next={...prev};delete next[id];return next;}),[]);

  const check=useCallback(async (changes:SheetEdit[],ids:string[]=[])=>{
    if(!reason.trim()||!changes.length)return;
    if(changes.length>LIMIT){setError(`За один раз можно применить не больше ${LIMIT} строк.`);return;}
    if(changes.some(item=>item.kind==='new'&&(!item.binding_id||!item.planned_start||!item.due_date))){
      setError('Укажите регламент, начало и срок для каждой новой строки.');return;
    }
    setBusy(true);setError('');setFinish([]);setAgreed(false);
    const request={changes,reason:reason.trim()};
    try{setPending({request,result:await orderTableApi.preview(request),key:crypto.randomUUID(),added:ids});}
    catch(err){setError(failure(err));}
    finally{setBusy(false);}
  },[reason]);
  const move=useCallback((change:ExistingEdit)=>{void check([change]);},[check]);
  const apply=async()=>{
    if(!pending?.result.preview_digest||!agreed||busy)return;
    const {request,result,key,added:ids}=pending;
    setBusy(true);setError('');
    try{
      const saved=await orderTableApi.apply({...request,preview_digest:result.preview_digest!,idempotency_key:key,
        confirm_assigned:result.requires_assigned_confirmation});
      const changed=new Set(saved.items.map(item=>item.task_id));
      setEdits(prev=>Object.fromEntries(Object.entries(prev).filter(([id])=>!changed.has(id))));
      setAdded(prev=>prev.filter(row=>!ids.includes(row.id)));
      setPending(null);setFinish(saved.items);setReload(n=>n+1);
    }catch(err){
      setError(failure(err));
      if(err instanceof ApiError&&err.status===409){setPending(null);setReload(n=>n+1);}
    }finally{setBusy(false);}
  };
  const assigned=pending?.result.requires_assigned_confirmation??false;
  const close=()=>{if(!busy){setPending(null);setAgreed(false);}};
  return <section aria-label="Таблица нарядов ТО" className="min-w-0 space-y-4">
    <header><h2 className="text-xl font-semibold">Таблица нарядов ТО</h2><p className="mt-1 text-sm text-muted">Правки в ячейках не записываются до подтверждения. Плановое окно меняется в пределах регламента; нормы, исходный Excel и история сохраняются.</p></header>
    <form className="flex flex-wrap items-end gap-2" onSubmit={e=>{e.preventDefault();setQ(needle.trim());setOffset(0);}}>
      <label className="text-sm">Месяц<Input type="month" min="2000-01" max="2099-12" value={month} onChange={e=>{if(/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(e.target.value)){setOffset(0);onMonth(e.target.value);}}}/></label>
      <label className="min-w-0 flex-1 text-sm">Поиск по нарядам<Input type="search" maxLength={120} value={needle} onChange={e=>setNeedle(e.target.value)}/></label>
      <Button type="submit" variant="secondary">Найти</Button>
      <a className={buttonClassName('secondary')} href={orderTableApi.export(month,q)}>Скачать сохранённое XLSX</a>
    </form>
    <p className="text-xs text-muted">Время объекта: {rows.data?.timezone??timezone}. Для назначенного наряда перенос проверяется отдельно с прежним составом.</p>
    {rows.status==='loading'&&<LoadingState label="Загрузка нарядов"/>}
    {rows.status==='error'&&<div><p role="alert">{rows.error}</p><Button variant="secondary" onClick={()=>setReload(n=>n+1)}>Повторить загрузку</Button></div>}
    {rows.data?.items.length===0&&<p className="text-sm text-muted">Нет нарядов по этому месяцу и фильтру. Можно добавить новый разовый наряд.</p>}
    {Boolean(rows.data?.items.length)&&<div className="max-w-full overflow-x-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label="Прокручиваемые строки таблицы">
      <table className="w-full min-w-[880px] text-sm"><thead><tr className="text-left text-muted">
        {['Наряд и оборудование','Плановое начало','Обязательный срок и норма','План, чел.-ч','Примечание','Действия'].map(label=><th className={cell} key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{rows.data!.items.map(row=><WorkRow key={row.task_id} row={row} change={edits[row.task_id]?.change} busy={busy} allowMove={Boolean(reason.trim())} edit={edit} reset={reset} move={move}/>)}</tbody>
      </table>
    </div>}
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="ghost" disabled={!offset||rows.status==='loading'} onClick={()=>setOffset(n=>n-PAGE)}>Предыдущие наряды</Button>
      <Button size="sm" variant="ghost" disabled={!rows.data?.has_more} onClick={()=>setOffset(n=>n+PAGE)}>Следующие наряды</Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={()=>setReload(n=>n+1)}>Обновить таблицу</Button>
    </div>
    {added.length>0&&<NewRows items={added} disabled={busy} change={(id,patch)=>setAdded(prev=>prev.map(item=>item.id===id?{...item,change:{...item.change,...patch}}:item))}
      remove={id=>setAdded(prev=>prev.filter(item=>item.id!==id))}/>}
    <Button variant="secondary" disabled={busy||total>=LIMIT} onClick={()=>setAdded(prev=>[...prev,{id:crypto.randomUUID(),change:empty()}])}>Добавить строку</Button>
    <label className="block max-w-xl text-sm">Основание изменения<Input maxLength={1000} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
    <p className="text-sm text-muted">Обычных правок: {total}. Переносов на отдельную проверку: {moveCount}.</p>
    <Button disabled={busy||!total||total>LIMIT||!reason.trim()} onClick={()=>void check([...draftChanges,...added.map(row=>row.change)],added.map(row=>row.id))}>Проверить изменения</Button>
    {error&&!pending&&<p role="alert" className="text-danger">{error}</p>}
    {finish.length>0&&<div aria-live="polite"><p>Изменения сохранены.</p><ul className="space-y-1 text-sm">{finish.map(item=><li key={item.task_id}><Link className="fr-text-link" to={`/tasks/${item.task_id}`}>Открыть наряд {item.task_id.slice(0,8)}</Link></li>)}</ul></div>}
    <Modal open={Boolean(pending)} title={assigned?'Отдельное подтверждение переноса':'Предпросмотр изменений'} onClose={close} size="wide"
      description={assigned?'Бригада остаётся прежней. После сохранения исполнители получат уведомление.':'Сверьте список. Предпросмотр еще не сохраняет изменения.'}
      footer={<><Button variant="secondary" disabled={busy} onClick={close}>Вернуться к таблице</Button>
        <Button disabled={busy||!agreed||!pending?.result.can_apply} onClick={()=>void apply()}>{assigned?'Подтвердить перенос':'Применить изменения'}</Button></>}>
      {pending&&<OrderTablePreview items={pending.result.items}/>}
      {pending?.result.can_apply&&<label className="mt-4 flex items-start gap-2 text-sm"><input type="checkbox" checked={agreed} disabled={busy} onChange={e=>setAgreed(e.target.checked)}/>{assigned?'Подтверждаю перенос этой бригады в указанный интервал':'Подтверждаю перечисленные изменения нарядов'}</label>}
      {error&&<p role="alert" className="mt-3 text-danger">{error}</p>}
    </Modal>
  </section>;
}
