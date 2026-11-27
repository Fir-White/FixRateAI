import { useState } from 'react';
import { type EditorSession, type WorkbookVersion, workbooks } from '@/shared/api/workbooks';
import { useApiQuery } from '@/shared/lib/useApiQuery';
import { Button } from '@/shared/ui/Button';
import { Callout } from '@/shared/ui/Callout';
import { Card } from '@/shared/ui/Card';
import { FileInput } from '@/shared/ui/FileInput';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { WorkbookEditor } from './WorkbookEditor';
import { WorkbookOrderChanges } from './WorkbookOrderChanges';

const PAGE = 25;
const failure = (error:unknown) => error instanceof Error ? error.message : 'Не удалось выполнить действие.';
type Select = (id: string, version: number) => void;
type Props = {bookId: string; version: number; fromCatalog?: string; mayEdit: boolean; timezone: string; onSelect: Select; onCatalog:(id:string)=>void};

export function WorkbookWorkspace({bookId,version,fromCatalog,mayEdit,timezone,onSelect,onCatalog}: Props) {
  const [notice,setNotice] = useState('');
  const select:Select = (id,next) => {setNotice('');onSelect(id,next);};
  return <div className="space-y-4">
    <h2 className="text-lg font-semibold">Исходные книги Excel</h2>
    <p className="text-sm text-muted">Редактируйте саму книгу. Оригинал хранится отдельно; сохранение новой версии не меняет наряды.</p>
    {notice&&<p role="status"><span>{notice}</span> Если готовили правку наряда, откройте «Применить к выпущенному наряду».</p>}
    {bookId
      ? <SelectedWorkbook key={`${bookId}:${version}`} id={bookId} version={version} timezone={timezone} mayEdit={mayEdit}
          onSelect={select} onCatalog={onCatalog} onSaved={saved=>{setNotice(`Версия ${saved.version} сохранена. Оригинал не изменился.`);onSelect(saved.book_id,saved.version);}}/>
      : <WorkbookList mayEdit={mayEdit} fromCatalog={fromCatalog} select={select}/>}
  </div>;
}

function Pager({offset,total,onChange}:{offset:number;total:number;onChange:(value:number)=>void}) {
  return total>PAGE&&<nav aria-label="Страницы списка" className="flex flex-wrap items-center gap-2">
    <Button variant="secondary" disabled={!offset} onClick={()=>onChange(offset-PAGE)}>Назад</Button>
    <span className="text-sm text-muted">{offset+1}–{Math.min(offset+PAGE,total)} из {total}</span>
    <Button variant="secondary" disabled={offset+PAGE>=total} onClick={()=>onChange(offset+PAGE)}>Далее</Button>
  </nav>;
}

function WorkbookList({mayEdit,fromCatalog,select}:{mayEdit:boolean;fromCatalog?:string;select:Select}) {
  const [offset,setOffset]=useState(0), [file,setFile]=useState<File|null>(null), [error,setError]=useState('');
  const [busy,setBusy]=useState(false), [refresh,reload]=useState(0);
  const list=useApiQuery(()=>workbooks.list(offset),[offset,refresh],undefined,`workbooks:${offset}`);
  async function add(action:()=>Promise<WorkbookVersion>) {
    setBusy(true);setError('');
    try {const saved=await action();select(saved.book_id,saved.version);}
    catch (reason) {setError(failure(reason));}
    finally {setBusy(false);}
  }
  return <>
    {mayEdit&&<Card className="space-y-3 p-4">
      {fromCatalog&&<Button variant="secondary" disabled={busy} onClick={()=>void add(()=>workbooks.fromCatalog(fromCatalog))}>Открыть исходный XLSX из каталога</Button>}
      <label className="block"><span className="mb-2 block font-semibold">Новая исходная книга</span><FileInput aria-label="Исходный XLSX" accept=".xlsx" disabled={busy} onChange={event=>setFile(event.target.files?.[0]??null)}/></label>
      <Button disabled={busy||!file} onClick={()=>{if(file) void add(()=>workbooks.upload(file));}}>Загрузить книгу</Button>
    </Card>}
    {error&&<p role="alert"><Callout tone="danger">{error}</Callout></p>}
    {list.status==='loading'&&<LoadingState/>}
    {list.status==='error'&&<ErrorState description={list.error} action={<Button onClick={()=>reload(value=>value+1)}>Повторить</Button>}/>}
    {list.status==='success'&&(list.data.total===0
      ? <EmptyState title="Книг пока нет" description={mayEdit?'Загрузите .xlsx или откройте исходник из каталога.':'Книги появятся после загрузки главным инженером.'}/>
      : <><ul className="space-y-2">{list.data.items.map(item=><li key={item.book_id}><Button variant="secondary" disabled={busy} onClick={()=>select(item.book_id,item.version)}><span className="break-all">{item.filename} · версия {item.version}</span></Button></li>)}</ul>
          <Pager offset={offset} total={list.data.total} onChange={setOffset}/></>)}
  </>;
}

function SelectedWorkbook({id,version,timezone,mayEdit,onSelect,onCatalog,onSaved}:{
  id:string;version:number;timezone:string;mayEdit:boolean;onSelect:Select;onCatalog:(id:string)=>void;onSaved:(book:WorkbookVersion)=>void;
}) {
  const [offset,setOffset]=useState(0), [refresh,reload]=useState(0), [error,setError]=useState('');
  const [busy,setBusy]=useState(false), [session,setSession]=useState<EditorSession|null>(null);
  const [catalogConfirm,setCatalogConfirm]=useState(false);
  const selected=useApiQuery(()=>workbooks.details(id,version),[id,version,refresh],undefined,`workbook:${id}:${version}`);
  const history=useApiQuery(()=>workbooks.versions(id,offset),[id,offset,refresh],undefined,`workbook-versions:${id}:${offset}`);
  const latest=history.status==='success'&&offset===0?history.data.items[0]?.version:undefined;
  async function run(action:()=>Promise<unknown>) {
    setBusy(true);setError('');
    try {await action();}
    catch (reason) {setError(failure(reason));}
    finally {setBusy(false);}
  }
  return <>
    <Button variant="ghost" disabled={busy} onClick={()=>onSelect('',0)}>← Все книги</Button>
    {selected.status==='loading'&&<LoadingState/>}
    {selected.status==='error'&&<ErrorState description={selected.error} action={<Button onClick={()=>reload(value=>value+1)}>Повторить</Button>}/>}
    {selected.status==='success'&&<Card className="space-y-4 p-4">
      <div><h3 className="break-all font-semibold">{selected.data.filename}</h3><p className="text-sm text-muted">Версия {version}{version===1?' · оригинал':''}</p></div>
      <div className="flex flex-wrap items-center gap-3">
        {mayEdit&&<Button disabled={busy||!!session||(latest!==undefined&&latest!==version)} onClick={()=>void run(async()=>{setSession(await workbooks.start(id,version));})}>Редактировать книгу</Button>}
        <a className="text-accent underline" href={workbooks.download(id,version)}>Скачать XLSX</a>
        {mayEdit&&<Button variant="secondary" disabled={busy} aria-expanded={catalogConfirm} onClick={()=>setCatalogConfirm(value=>!value)}>Подготовить каталог</Button>}
      </div>
      {latest!==undefined&&latest!==version&&mayEdit&&<p className="text-sm text-muted">Для редактирования <button type="button" className="text-accent underline" onClick={()=>onSelect(id,latest)}>откройте последнюю версию</button>.</p>}
      {catalogConfirm&&<div className="space-y-2">
        <p>Создастся черновик из версии {version}. Действующие планы и наряды не изменятся.</p>
        <Button disabled={busy} onClick={()=>void run(async()=>{const result=await workbooks.catalog(id,version);onCatalog(result.import_id);})}>Создать черновик каталога</Button>
      </div>}
      {error&&<p role="alert"><Callout tone="danger">{error}</Callout></p>}
      {session&&<WorkbookEditor book={selected.data} session={session} timezone={timezone} onClose={()=>setSession(null)} onSaved={saved=>{setSession(null);onSaved(saved);}}/>}
      {mayEdit&&<WorkbookOrderChanges book={selected.data} timezone={timezone}/>}
    </Card>}
    <section aria-label="История версий книги" className="space-y-2">
      <h3 className="font-semibold">История версий</h3>
      {history.status==='loading'&&<LoadingState/>}
      {history.status==='error'&&<ErrorState description={history.error} action={<Button onClick={()=>reload(value=>value+1)}>Повторить</Button>}/>}
      {history.status==='success'&&<>
        <ul className="space-y-2">{history.data.items.map(item=><li key={item.version} className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" disabled={busy||item.version===version} onClick={()=>onSelect(id,item.version)}>Версия {item.version}{item.version===1?' · оригинал':''}</Button>
          <time className="text-sm text-muted" dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('ru-RU',{timeZone:timezone,dateStyle:'short',timeStyle:'short'})}</time>
        </li>)}</ul><Pager offset={offset} total={history.data.total} onChange={setOffset}/>
      </>}
    </section>
  </>;
}
