import { useDeferredValue, useRef, useState } from 'react';
import { catalogImportsApi as api, type CatalogPreview, type CatalogSummary, type CatalogOperation, type CatalogIssue, type RawCatalogCell } from '@/shared/api/catalogImports';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { Input, Select, FieldCaption } from '@/shared/ui/Form';
import { FileInput } from '@/shared/ui/FileInput';
import { LoadingState, ErrorState } from '@/shared/ui/States';
import { Callout } from '@/shared/ui/Callout';
import { Drawer } from '@/shared/ui/Drawer';
import { dateTimeFormatter } from '@/shared/lib/dateTimeFormatter';
import './catalog-imports.css';

const message=(error:unknown)=>error instanceof Error?error.message:'Не удалось обработать каталог';
const flags:Record<string,string>={NEEDS_SEMANTICS:'Уточнить смысл отметок',NEEDS_DURATION:'Подтвердить норму времени',NEEDS_ASSET_BINDING:'Привязать оборудование',NEEDS_POLICY:'Подтвердить правила планирования'};

export function CatalogImports({mayImport,siteName,timezone='UTC'}:{mayImport:boolean;siteName?:string;timezone?:string}) {
  const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState<CatalogPreview|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [selected,setSelected]=useState(''),[refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0);
  const version=useRef(0);
  const list=useApiQuery(()=>api.list(offset),[offset,refresh],undefined,`catalog-imports:${offset}`);
  return <div className="catalog-imports space-y-4">
    {siteName&&<p className="text-sm text-muted">Здание: {siteName}</p>}
    <Callout>Каталог содержит шаблоны работ. Смысл календарных отметок, оборудование и нормы подтверждаются отдельно. Сохранение черновика не создаёт наряды и назначения.</Callout>
    {mayImport&&<div className="space-y-3"><p className="text-sm text-muted">Загрузите Excel СВиК с листом «Лист1»: операции A:G и дни января H:AL.</p>
      <FileInput aria-label="Excel каталога СВиК" accept=".xlsx" disabled={busy} onChange={e=>{version.current++;setFile(e.target.files?.[0]??null);setPreview(null);setError('');setNotice('');}}/>
      <Button variant="secondary" disabled={busy||!file} onClick={async()=>{if(!file||busy)return;const current=version.current;setBusy(true);setError('');setPreview(null);try{const result=await api.preview(file);if(current===version.current)setPreview(result);}catch(e){setError(message(e));}finally{setBusy(false);}}}>{busy?'Обработка…':'Проверить каталог'}</Button>
      {preview&&<section className="space-y-4" aria-label="Предпросмотр каталога СВиК"><Summary value={preview.summary}/><Issues issues={preview.issues}/><Diagnostics cells={preview.sheet2_diagnostic}/>
        <p className="text-sm text-muted">Первые {preview.operations.length} из {preview.total} операций. После сохранения черновика доступны все строки, поиск и исходные ячейки.</p>
        <Operations items={preview.operations}/>
        <Button disabled={busy||!preview.can_save_draft} onClick={async()=>{if(!file||busy)return;setBusy(true);setError('');try{const result=await api.save(file,preview.preview_token);setSelected(result.import_id);setNotice(result.already_saved?'Этот источник уже сохранён. Открыт прежний черновик.':'Каталог сохранён как черновик. Действующий план не изменён.');setPreview(null);setOffset(0);setRefresh(n=>n+1);}catch(e){setError(message(e));}finally{setBusy(false);}}}>Сохранить каталог-черновик</Button>
      </section>}
    </div>}
    {error&&<p role="alert"><Callout tone="danger">{error}</Callout></p>}{notice&&<p role="status">{notice}</p>}
    <h3 className="font-semibold">Сохранённые каталоги</h3>
    {list.status==='loading'&&<LoadingState/>}{list.status==='error'&&<ErrorState description={list.error}/>}
    {list.status==='success'&&<><ul className="space-y-2">{list.data.items.map(item=><li key={item.import_id}><Button variant={selected===item.import_id?'primary':'secondary'} onClick={()=>setSelected(item.import_id)}><span>{item.filename} · {item.summary.operation_count} операций · Черновик<small className="block text-xs font-normal">Загружен: {dateTimeFormatter('ru-RU',{timeZone:timezone,dateStyle:'short',timeStyle:'medium'}).format(new Date(item.created_at))}</small></span></Button></li>)}</ul>{!list.data.total&&<p className="text-sm text-muted">Каталоги ещё не загружены.</p>}<Pager offset={offset} total={list.data.total} onChange={setOffset}/></>}
    {selected&&<SavedCatalog key={selected} id={selected}/>}
  </div>;
}

function Summary({value}:{value:CatalogSummary}) {
  return <div className="space-y-2" aria-label="Готовность каталога"><p><strong>{value.operation_count}</strong> шаблонов · {value.top_level_group_count} разделов · {value.mark_count} исходных отметок</p>
    <p>Нормы времени отсутствуют: <strong>{value.empty_duration_count}</strong>. Готово к реальному плану: <strong>{value.ready_count}</strong>.</p>
    <p className="text-sm text-muted">{Object.entries(value.maintenance_types).map(([kind,count])=>`${kind}: ${count}`).join(' · ')}</p>
    <ul className="text-sm text-muted">{Object.entries(value.readiness_counts).map(([flag,count])=><li key={flag}>{flags[flag]??flag}: {count}</li>)}</ul></div>;
}
function Issues({issues}:{issues:CatalogIssue[]}) {
  const [offset,setOffset]=useState(0);
  return <div className="space-y-2">{issues.slice(offset,offset+25).map((issue,index)=><Callout tone="warning" key={index}>{issue.sheet}!{issue.cell}: {issue.message}</Callout>)}<Pager offset={offset} total={issues.length} onChange={setOffset}/></div>;
}
function Diagnostics({cells}:{cells:RawCatalogCell[]}) {return cells.length>0&&<details><summary className="cursor-pointer text-sm">Сверка расчётного листа</summary><dl className="mt-3 space-y-2 text-sm">{cells.map(cell=><div key={cell.address}><dt>Лист2!{cell.address}</dt><dd className="break-words whitespace-pre-wrap">{cell.text??'Нет значения'}{cell.formula&&` · Формула: ${cell.formula}. Показан сохранённый результат Excel.`}</dd></div>)}</dl></details>;}
function Pager({offset,total,onChange}:{offset:number;total:number;onChange:(next:number)=>void}) {return total>25&&<nav className="flex flex-wrap items-center justify-between gap-3" aria-label="Страницы каталога"><span className="text-sm text-muted">{offset+1}–{Math.min(offset+25,total)} из {total}</span><div className="flex gap-2"><Button variant="secondary" disabled={!offset} onClick={()=>onChange(offset-25)}>Предыдущие 25</Button><Button variant="secondary" disabled={offset+25>=total} onClick={()=>onChange(offset+25)}>Следующие 25</Button></div></nav>;}
function Operations({items,onSelect}:{items:CatalogOperation[];onSelect?:(row:number)=>void}) {return <div className="registry-scroll"><table className="registry-table catalog-import-table" aria-label="Операции каталога СВиК"><thead><tr><th>Код и операция</th><th>Вид ТО / частота</th><th>Исходные данные</th><th>Уточнения</th></tr></thead><tbody>{items.map(row=><tr key={row.row}><td data-label="Операция">{onSelect?<Button variant="ghost" onClick={()=>onSelect(row.row)}>{row.code} · {row.title}</Button>:<span>{row.code} · {row.title}</span>}</td><td data-label="Вид ТО / частота">{row.maintenance_type}<br/>{row.frequency_raw}</td><td data-label="Источник">Лист1!{row.source_cells.B}<br/>{row.mark_count} отметок января</td><td data-label="Уточнения">{row.quality_flags.map(flag=><small key={flag}>{flags[flag]??flag}</small>)}</td></tr>)}</tbody></table>{!items.length&&<p className="p-4 text-sm">Операции не найдены.</p>}</div>;}

function SavedCatalog({id}:{id:string}) {
  const [search,setSearch]=useState(''),[group,setGroup]=useState(''),[kind,setKind]=useState(''),[offset,setOffset]=useState(0),[row,setRow]=useState<number|null>(null);
  const needle=useDeferredValue(search);
  const detail=useApiQuery(()=>api.detail(id),[id],undefined,`catalog:${id}`);
  const rows=useApiQuery(()=>api.operations(id,offset,needle,group,kind),[id,offset,needle,group,kind],undefined,`catalog-rows:${JSON.stringify([id,offset,needle,group,kind])}`);
  return <section className="space-y-4 border-t border-line pt-5" aria-label="Сохранённый каталог СВиК">
    {detail.status==='loading'&&<LoadingState/>}{detail.status==='error'&&<ErrorState description={detail.error}/>}
    {detail.status==='success'&&<><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">{detail.data.filename}</h3><a className="text-accent underline" href={api.source(id)}>Скачать исходный Excel</a></div>
      <Summary value={detail.data.summary}/><Issues issues={detail.data.issues}/><Diagnostics cells={detail.data.sheet2_diagnostic}/>
      <details><summary className="cursor-pointer text-sm">Иерархия и источник</summary><p className="mt-3 break-all text-xs text-muted">SHA-256: {detail.data.source_sha256}</p><ul className="mt-3 space-y-1 text-sm">{detail.data.groups.map(item=><li key={item.id} className={item.parent_id?'pl-5':''}>{item.code} · {item.title} · Лист1!B{item.row}</li>)}</ul><p className="mt-4 text-sm">Дополнительные заголовки исходника</p><ul className="mt-2 space-y-1 text-sm">{detail.data.header_context.map(cell=><li key={cell.address}>{cell.address} · {cell.text}</li>)}</ul></details>
      <div className="grid gap-3 sm:grid-cols-3"><label><FieldCaption>Поиск операций каталога</FieldCaption><Input aria-label="Поиск операций каталога" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label>
        <label><FieldCaption>Раздел каталога</FieldCaption><Select aria-label="Раздел каталога" value={group} onChange={e=>{setGroup(e.target.value);setOffset(0);}}><option value="">Все разделы</option>{detail.data.groups.map(item=><option key={item.id} value={item.id}>{item.code} · {item.title}</option>)}</Select></label>
        <label><FieldCaption>Вид ТО каталога</FieldCaption><Select aria-label="Вид ТО каталога" value={kind} onChange={e=>{setKind(e.target.value);setOffset(0);}}><option value="">Все виды</option>{Object.keys(detail.data.summary.maintenance_types).map(item=><option key={item}>{item}</option>)}</Select></label></div>
    </>}
    {rows.status==='loading'&&<LoadingState/>}{rows.status==='error'&&<ErrorState description={rows.error}/>}{rows.status==='success'&&<><Operations items={rows.data.items} onSelect={setRow}/><Pager offset={offset} total={rows.data.total} onChange={setOffset}/></>}
    <Drawer open={row!==null} onClose={()=>setRow(null)} title="Исходная строка каталога">{row!==null&&<SourceRow key={row} id={id} row={row}/>}</Drawer>
  </section>;
}
function SourceRow({id,row}:{id:string;row:number}) {
  const query=useApiQuery(()=>api.operation(id,row),[id,row],undefined,`catalog-source:${id}:${row}`);
  if(query.status==='loading')return <LoadingState/>;if(query.status==='error')return <ErrorState description={query.error}/>;
  const data=query.data;
  const cellText=(cell:RawCatalogCell)=>!cell.present?'Ячейка отсутствует':cell.text===''?'Пустая ячейка':cell.text??'Неизвестно';
  return <div className="space-y-4"><h3 className="font-semibold">{data.code} · {data.title}</h3><Callout>Смысл отметок не подтверждён. Месяц — январь, год не задан. Нормы и численность не рассчитаны.</Callout>
    <dl className="space-y-3 text-sm">{Object.values(data.raw_cells).map(cell=><div key={cell.address}><dt className="text-muted">Лист1!{cell.address}</dt><dd className="whitespace-pre-wrap break-words">{cellText(cell)}</dd>{cell.formula&&<dd>Формула исходника: {cell.formula}; не исполнялась</dd>}</div>)}</dl>
    <h4 className="font-semibold">Все 31 исходная ячейка января</h4><ul className="space-y-2 text-sm">{data.calendar_marks.map(cell=><li key={cell.address} className="whitespace-pre-wrap break-words">{cell.address} · день {cell.day}: {cellText(cell)}</li>)}</ul>
  </div>;
}
