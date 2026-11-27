import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useBeforeUnload, useBlocker } from 'react-router-dom';
import { workbooks, type EditorSession, type VersionCommit, type WorkbookVersion } from '@/shared/api/workbooks';
import { Button } from '@/shared/ui/Button';
import { ApiError } from '@/shared/api/request';
import { WorkbookOrderTemplate } from './WorkbookOrderTemplate';
import { localEditorOrigin } from './officeOrigin';

type Props = {
  book?: WorkbookVersion; session?: EditorSession; timezone: string;
  open?:boolean; inline?:boolean; filename?: string; provisionalOrigin?:string; openingError?:string; retry?:()=>void;
  onClose: (keepWarm?: boolean) => void; onSaved: (book: WorkbookVersion) => void;
};

function delay(signal: AbortSignal) {
  return new Promise<void>((resolve,reject)=>{
    const cancel = () => {window.clearTimeout(timer); reject(signal.reason);};
    const timer = window.setTimeout(()=>{signal.removeEventListener('abort',cancel);resolve();},1000);
    if (signal.aborted) cancel(); else signal.addEventListener('abort',cancel,{once:true});
  });
}

export function WorkbookEditor({book, session, timezone, open=true, inline=false, filename, provisionalOrigin, openingError, retry, onClose, onSaved}: Props) {
  const frame = useRef<HTMLIFrameElement>(null), dialog = useRef<HTMLDialogElement>(null), title = useId();
  const loadedFrame = useRef<HTMLIFrameElement|null>(null);
  const [ready,setReady] = useState(false), [syncing,setSyncing] = useState(false);
  const [dirty,setDirty] = useState(false), [busy,setBusy] = useState(false);
  const [error,setError] = useState(''), [notice,setNotice] = useState('');
  const [commit,setCommit] = useState<VersionCommit|null>(null);
  const [capture,setCaptureId] = useState<string|null>();
  const captureId = capture === undefined
    ? session?.state==='pending'||session?.state==='ready'?session.snapshot_request_id:null
    : capture;
  const capturePending = captureId!==null, leaving = useRef(false);
  const [templateOpen,setTemplateOpen] = useState(false), [templateVisited,setTemplateVisited] = useState(false);
  const running = useRef<AbortController|null>(null), synced = useRef(true);
  const office = localEditorOrigin(session?.api_url ?? provisionalOrigin);
  const parentOrigin = window.location.origin;
  const guard = useBlocker(()=>!leaving.current && (dirty||busy||capturePending||commit!==null));
  useBeforeUnload(event=>{
    if (dirty || busy || capturePending || commit) {event.preventDefault(); event.returnValue='';}
  });
  useEffect(()=>{
    if (guard.state!=='blocked') return;
    if (busy) {guard.reset();return;}
    if (window.confirm('Новая версия не сохранена. Выйти из редактора?')) {
      onClose();guard.proceed();
    } else guard.reset();
  },[guard,busy,onClose]);
  useEffect(()=>{
    if (!open || inline) return;
    const current = dialog.current!;
    if (!current.open && typeof current.showModal==='function') current.showModal();
    return ()=>{
      running.current?.abort(); running.current=null;
      if (current.open && typeof current.close==='function') current.close();
    };
  },[open,inline]);
  useEffect(()=>{
    if (!session || !office) return;
    const fail = () => {setReady(false);setError('Не удалось открыть книгу в ONLYOFFICE. Закройте редактор и попробуйте снова.');};
    const timeout = window.setTimeout(fail,40000);
    const receive = (message: MessageEvent) => {
      if (message.origin!==office||message.source!==frame.current?.contentWindow||message.data?.bridge!=='fixrate-office') return;
      if (message.data.event==='ready') {window.clearTimeout(timeout);setError('');setReady(true);}
      if (message.data.event==='error') {window.clearTimeout(timeout);fail();}
      if (message.data.event==='sync'&&typeof message.data.syncing==='boolean') {
        synced.current=!message.data.syncing;setSyncing(message.data.syncing);if (message.data.syncing) setDirty(true);
      }
    };
    window.addEventListener('message',receive);
    const current = frame.current;
    if (current && loadedFrame.current===current) {
      current.contentWindow?.postMessage({bridge:'fixrate-office',event:'init',config:session.document_config},office);
    }
    return ()=>{
      window.removeEventListener('message',receive);
      window.clearTimeout(timeout);
    };
  },[office,session]);
  useEffect(()=>{
    if (!open && (dirty || error)) onClose();
  },[open,dirty,error,onClose]);

  const close = () => {
    if (running.current) return;
    if ((dirty || capturePending || commit) && !window.confirm('Новая версия не сохранена. Выйти из редактора?')) return;
    if (dialog.current?.open) dialog.current.close();
    onClose(inline && ready && session?.state==='editing' && !error && !dirty && !capturePending && commit===null);
  };

  async function save() {
    if (!book || !session || running.current || !synced.current) return;
    const operation = new AbortController();
    running.current=operation;
    setBusy(true);setError('');setNotice('');
    try {
      let command = commit;
      if (!command) {
        const requested=captureId??crypto.randomUUID();
        setCaptureId(requested);
        let status=await workbooks.snapshot(book.book_id,session.session_id,requested);
        if (status.snapshot_request_id!==requested) throw new Error('Редактор вернул другой снимок. Переоткройте книгу.');
        for (let retries=0;status.state==='pending' && retries<48;retries++) {
          await delay(operation.signal);
          status=await workbooks.status(book.book_id,session.session_id,operation.signal);
          if (status.snapshot_request_id!==requested) throw new Error('В другой вкладке запрошено сохранение. Проверьте версию.');
        }
        if (operation.signal.aborted) return;
        if (status.state!=='pending') setCaptureId(null);
        if (status.state==='unchanged') {setNotice('Редактор не вернул новых изменений. Версия книги не создана.');return;}
        if (status.state!=='ready'||!status.snapshot_sha256) throw new Error('Редактор не подготовил XLSX. Книга не сохранена; попробуйте снова.');
        command={session_id:session.session_id,expected_version:book.version,snapshot_sha256:status.snapshot_sha256,idempotency_key:crypto.randomUUID()};
        setCommit(command);
      }
      const saved=await workbooks.commit(book.book_id,command);
      if (!operation.signal.aborted) {
        setCommit(null);setDirty(false);
        if (saved.version===book.version) setNotice('Книга не изменилась. Новая версия не создана.');
        else {leaving.current=true;onSaved(saved);}
      }
    } catch (reason) {
      if (!operation.signal.aborted) setError(reason instanceof Error?reason.message:'Не удалось сохранить версию.');
    } finally {
      if (running.current===operation) {running.current=null;setBusy(false);}
    }
  }

  const content =
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-line p-3">
        <h3 id={title} className="mr-auto min-w-0 break-all font-semibold">{book?`${book.filename} · версия ${book.version}`:filename}</h3>
        {!openingError&&<><Button disabled={(!ready&&!commit&&!capturePending)||syncing||busy} onClick={()=>void save()}>{busy?'Сохранение…':commit||capturePending?'Завершить сохранение':'Сохранить новую версию'}</Button>
          <Button variant="secondary" disabled={!ready||busy||!!commit||capturePending} aria-expanded={templateOpen}
            onClick={()=>{setTemplateOpen(value=>!value);setTemplateVisited(true);}}>Правки наряда</Button></>}
        <Button variant="secondary" disabled={busy} onClick={close}>Закрыть редактор</Button>
        {(!openingError&&(!ready&&!error||syncing||notice||capturePending&&!busy))&&<p role="status" className="w-full text-sm text-muted">{notice || (capturePending&&!busy?'Завершите прежнее сохранение, прежде чем продолжить правку.':syncing?'Редактор передаёт изменения…':'Открываем локальный редактор…')}</p>}
        {session?.detached_connections&&<p className="w-full text-sm text-muted">Подключения к внешним данным отключены в редакторе и не попадут в новую версию. Оригинал сохранён целиком.</p>}
        {(openingError||error||session&&!office)&&<p role="alert" className="w-full text-sm">{openingError||error||'Откройте FixRate по адресу http://127.0.0.1, чтобы включить локальный редактор.'}</p>}
        {openingError&&retry&&<Button variant="secondary" onClick={retry}>Повторить открытие</Button>}
      </header>
      {templateVisited&&<div hidden={!templateOpen} inert={!templateOpen||busy} className="max-h-[42dvh] overflow-auto">
        <WorkbookOrderTemplate timezone={timezone}/>
      </div>}
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {office&&!openingError&&<iframe key={office} ref={frame} title="Локальный редактор Excel" className="block h-full w-full border-0"
          sandbox="allow-scripts allow-same-origin allow-downloads"
          allow="clipboard-read 'src'; clipboard-write 'src'"
          inert={busy||!!commit||capturePending}
          src={`${office}/fixrate-office/#${parentOrigin}`}
          onLoad={event=>{
            const current=loadedFrame.current=event.currentTarget;
            if (session) current.contentWindow?.postMessage({bridge:'fixrate-office',event:'init',config:session.document_config},office);
          }}/>}
        {(busy||commit||capturePending)&&<div className="absolute inset-0" aria-hidden="true"/>}
      </div>
    </div>;
  if (inline) return <section hidden={!open} aria-label={`Редактор Excel: ${filename??book?.filename??''}`}
    className="h-[clamp(960px,100dvh,1200px)] overflow-hidden rounded-xl border border-line bg-surface text-ink">{content}</section>;
  return <dialog ref={dialog} hidden={!open} aria-labelledby={title} onCancel={event=>{event.preventDefault();close();}}
    className="fixed inset-0 m-auto h-[min(78dvh,760px)] w-[calc(100vw-16px)] max-w-none overflow-hidden rounded-xl border border-line bg-surface p-0 text-ink sm:w-[min(86vw,1240px)]">{content}</dialog>;
}

export function CatalogWorkbookEditor({catalog,filename,origin,timezone,onClose,onSaved,request}:{
  catalog:string;filename:string;origin?:string;timezone:string;request?:number;
  onClose:(keepWarm?:boolean)=>void;onSaved:(book:WorkbookVersion)=>void;
}) {
  const [attempt,setAttempt]=useState(0);
  const retry=useCallback(()=>setAttempt(value=>value+1),[]);
  return <CatalogWorkbookAttempt key={attempt} catalog={catalog} filename={filename} origin={origin}
    timezone={timezone} request={request} onClose={onClose} onSaved={onSaved} retry={retry}/>;
}

function CatalogWorkbookAttempt({catalog,filename,origin,timezone,onClose,onSaved,retry,request}:{
  catalog:string;filename:string;origin?:string;timezone:string;onClose:(keepWarm?:boolean)=>void;request?:number;
  onSaved:(book:WorkbookVersion)=>void;retry:()=>void;
}) {
  const [opened,setOpened]=useState<{book:WorkbookVersion;session:EditorSession}>();
  const [validated,setValidated]=useState<number>();
  const [error,setError]=useState('');
  const previous=useRef(opened);
  useEffect(()=>{
    if (request===undefined) return;
    const controller=new AbortController(), {signal}=controller;
    async function open() {
      try {
        if (signal.aborted) return;
        const current=previous.current;
        if (current) {
          const checking=AbortSignal.any([signal,AbortSignal.timeout(8_000)]);
          const [versions,status]=await Promise.all([
            workbooks.versions(current.book.book_id,0,checking),
            workbooks.status(current.book.book_id,current.session.session_id,checking),
          ]);
          if (signal.aborted) return;
          if (versions.items[0]?.version!==current.book.version) {retry();return;}
          if (status.state!=='editing') throw new Error('Сессия книги изменилась. Откройте редактор заново.');
          setValidated(request);
          return;
        }
        const book=await workbooks.fromCatalog(catalog,signal);
        if (signal.aborted) return;
        const session=await workbooks.start(book.book_id,book.version,signal);
        if (!signal.aborted) {
          previous.current={book,session};
          setOpened(previous.current);
          setValidated(request);
        }
      } catch (error) {
        if (signal.aborted) return;
        if (previous.current && error instanceof ApiError && error.status===409) {retry();return;}
        previous.current=undefined;
        setOpened(undefined);
        setError(error instanceof Error && error.name!=='TimeoutError'?error.message:'Не удалось вовремя открыть книгу.');
      }
    }
    void Promise.resolve().then(open);
    return ()=>controller.abort();
  },[catalog,request,retry]);
  const checking=!!opened && request!==undefined && validated!==request;
  return <>
    {checking&&<p role="status" className="sr-only">Проверяем версию книги…</p>}
    <WorkbookEditor open={request!==undefined&&!checking} inline book={opened?.book} session={opened?.session} filename={filename}
    provisionalOrigin={origin} timezone={timezone} openingError={error} retry={retry}
    onClose={onClose} onSaved={onSaved}/>
  </>;
}
