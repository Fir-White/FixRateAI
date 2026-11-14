import {memo,useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {useSearchParams} from 'react-router-dom';
import {useSession} from '@/shared/session/SessionContext';
import {assistantApi as api,type ChatCapabilities,type ChatView,type ChatTurn} from '@/shared/api/assistant';
import {useApiQuery} from '@/shared/lib/useApiQuery';
import {useDialogFocus} from '@/shared/lib/useDialogFocus';
import {Button} from '@/shared/ui/Button';
import {Icon} from '@/shared/ui/Icon';
import {LoadingState,ErrorState} from '@/shared/ui/States';
import {Callout} from '@/shared/ui/Callout';
import {ActionCard} from '@/features/assistant/ActionCard';
import '@/features/assistant/assistant.css';

const starters=['Найди ближайшее ТО и помоги назначить работников','Какие работы требуют внимания?','Помоги разобраться с Excel'];
const safeResource=(url:string)=>/^\/api\/v1\/(maintenance\/|assistant\/attachments\/)/.test(url);
const Timestamp=memo(function Timestamp({at,timezone}:{at:string;timezone:string}){
  const date=new Date(at);if(Number.isNaN(date.getTime()))return null;
  const label=new Intl.DateTimeFormat('ru-RU',{timeZone:timezone,day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
  return <time dateTime={at} title={`${label} · ${timezone}`}>{label}</time>;
});
function activity(tool:string,names:Record<string,string>){
  if(tool==='__routing')return 'Подбираю действия для вашего запроса';
  if(tool==='__responding')return 'Сопоставляю данные и готовлю ответ';
  if(tool==='describe_tool')return 'Уточняю параметры действия';
  if(tool==='tasks_find'||tool==='tasks_list')return 'Ищу подходящие задания и ближайшее ТО';
  if(tool==='assignment_context')return 'Проверяю условия назначения и доступных работников';
  if(tool==='assignment_preview')return 'Проверяю состав бригады, допуски и время';
  if(tool==='task_assign')return 'Готовлю предложение о назначении';
  if(tool==='staff_find'||tool==='staff_read'||tool==='workforce_read')return 'Изучаю сотрудников, смены и квалификации';
  if(tool.includes('import_preview'))return 'Проверяю файл и данные для импорта';
  if(tool==='equipment_find')return 'Ищу оборудование в реестре';
  return names[tool]??'Выполняю проверку данных';
}
const Progress=memo(function Progress({turn,names}:{turn:ChatTurn;names:Record<string,string>}){
  const steps=turn.trace.filter(s=>!s.tool.startsWith('__')),active=[...turn.trace].reverse().find(s=>s.status==='running');
  if(turn.status==='running')return <div className="assistant-progress"><p role="status"><span className="assistant-status-dot"/>{activity(active?.tool??'__routing',names)}…</p>{steps.length>0&&<div className="assistant-progress-recent">{steps.filter(s=>s.status!=='running').slice(-2).map((step,i)=><p key={i}>{activity(step.tool,names)}{step.status==='denied'?' — уточняю параметры':step.status==='proposed'?' — предложение готово':' — проверено'}</p>)}</div>}</div>;
  return steps.length?<details className="assistant-progress"><summary>Ход выполнения · {steps.length}</summary><ol>{steps.map((step,i)=><li key={i}><span aria-hidden="true">{step.status==='denied'?'↳':step.status==='running'?'·':'✓'}</span>{activity(step.tool,names)}{step.status==='denied'&&' — параметры отклонены'}{step.status==='running'&&' — выполнение прервано'}{step.status==='proposed'&&' — нужно подтверждение'}</li>)}</ol></details>:null;
});
function Composer({draft,setDraft,onSend,onUpload,busy,uploading,running,available,attachments}:{draft:string;setDraft:(s:string)=>void;onSend:()=>void;onUpload:(file:File)=>void;busy:boolean;uploading:boolean;running:boolean;available:boolean;attachments?:ChatView['attachments']}){
  const input=useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(()=>{const el=input.current;if(el){el.style.height='auto';el.style.height=`${Math.min(Math.max(el.scrollHeight,64),180)}px`;}},[draft]);
  return <div className="assistant-composer-wrap">
    {(attachments?.length??0)>0&&<ul aria-label="Вложения диалога" className="assistant-attachments">{attachments?.map(file=><li key={file.attachment_id}><a href={`/api/v1/assistant/attachments/${encodeURIComponent(file.attachment_id)}`} target="_blank" rel="noreferrer">{file.original_name}</a><span>{Math.ceil(file.size_bytes/1024)} КБ</span></li>)}</ul>}
    <form className="assistant-composer" onSubmit={e=>{e.preventDefault();onSend();}} aria-label="Написать помощнику">
      <label className="sr-only" htmlFor="assistant-message">Сообщение помощнику</label><textarea ref={input} id="assistant-message" value={draft} maxLength={12000} rows={2} placeholder="Какую задачу решим?" disabled={busy} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(!running&&!busy&&!uploading&&available&&draft.trim())onSend();}}}/>
      <div className="assistant-composer-actions"><label className={`assistant-attach ${busy||uploading?'is-disabled':''}`} title="XLSX, JPEG, PNG, WebP до 10 МиБ"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M8 12.5V7a4 4 0 0 1 8 0v9a6 6 0 0 1-12 0V8m8-1v9a2 2 0 0 1-4 0v-4"/></svg><span>{uploading?'Загрузка…':'Файл'}</span><input className="sr-only" type="file" accept=".xlsx,.png,.jpg,.jpeg,.webp" aria-label="Прикрепить файл" disabled={busy||uploading} onChange={e=>{const file=e.target.files?.[0];if(file)onUpload(file);e.currentTarget.value='';}}/></label><span className="assistant-input-hint">Enter — отправить · Shift+Enter — новая строка</span><button className="assistant-send" type="submit" aria-label="Отправить" disabled={!available||!draft.trim()||busy||running||uploading} title={running?'Помощник работает':'Отправить сообщение'}><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button></div>
    </form><p className="assistant-disclaimer">Изменения — только после вашего подтверждения. Проверяйте ответы ИИ.</p>
  </div>;
}
function Chat({identity,capabilities,draft,setDraft,onRefreshList,timezone}:{identity:string;capabilities:ChatCapabilities;draft:string;setDraft:(s:string)=>void;onRefreshList:()=>void;timezone:string}){
  const [refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0),[sending,setSending]=useState(false),[uploading,setUploading]=useState(false),[error,setError]=useState(''),[atBottom,setAtBottom]=useState(true);
  const attempt=useRef({text:'',key:crypto.randomUUID()}),last=useRef<ChatView|null>(null);
  const scroll=useRef<HTMLDivElement>(null),transcript=useRef<HTMLDivElement>(null),pinned=useRef(true),openedOffset=useRef<number|null>(null),followNext=useRef(false);
  const query=useApiQuery(()=>api.read(identity,offset),[identity,offset,refresh],data=>data.turns.some(t=>t.status==='running')||data.actions.some(a=>a.status==='executing'),`assistant:thread:${identity}:${offset}`);
  const names=useMemo(()=>Object.fromEntries(capabilities.tools.assistant.map(t=>[t.name,t.title])),[capabilities.tools.assistant]);
  if(query.status==='success')last.current=query.data;
  const data=query.status==='success'?query.data:last.current;
  const toBottom=()=>{const el=scroll.current;if(el){el.scrollTop=el.scrollHeight;pinned.current=true;setAtBottom(true);}};
  useLayoutEffect(()=>{const el=scroll.current;if(!el||!data)return;if(openedOffset.current!==offset){el.scrollTop=offset===0?el.scrollHeight:0;openedOffset.current=offset;pinned.current=offset===0;setAtBottom(offset===0);}else if(pinned.current||followNext.current){toBottom();followNext.current=false;}},[data,offset]);
  useEffect(()=>{const el=transcript.current;if(!el||typeof ResizeObserver==='undefined')return;const observer=new ResizeObserver(()=>{if(pinned.current&&scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight;});observer.observe(el);return()=>observer.disconnect();},[!!data]);
  if(!data)return query.status==='error'?<ErrorState description={query.error} action={<Button onClick={()=>setRefresh(n=>n+1)}>Повторить загрузку</Button>}/>:<LoadingState label="Загрузка диалога"/>;
  const running=data.turns.some(t=>t.status==='running');
  const refreshAll=()=>{setRefresh(n=>n+1);onRefreshList();};
  const upload=async(file:File)=>{setUploading(true);setError('');try{await api.upload(identity,file);refreshAll();}catch(e){setError(e instanceof Error?e.message:'Не удалось прикрепить файл');}finally{setUploading(false);}};
  const send=async()=>{if(!draft.trim()||sending||running)return;const text=draft.trim();if(attempt.current.text!==text)attempt.current={text,key:crypto.randomUUID()};setSending(true);setError('');try{await api.send(identity,text,attempt.current.key);attempt.current={text:'',key:crypto.randomUUID()};setDraft('');setOffset(0);followNext.current=true;refreshAll();}catch(e){setError(e instanceof Error?e.message:'Не удалось отправить сообщение');setRefresh(n=>n+1);}finally{setSending(false);}};
  return <section className="assistant-chat" aria-label="Диалог с ИИ"><div className="assistant-body"><div className="assistant-transcript" ref={scroll} role="region" aria-label="Сообщения" tabIndex={0} onScroll={()=>{const el=scroll.current;if(el){const near=el.scrollHeight-el.scrollTop-el.clientHeight<72;pinned.current=near;setAtBottom(near);}}}><div className="assistant-transcript-inner" ref={transcript}>
    {data.total>25&&<div className="assistant-pagination"><Button size="sm" variant="ghost" disabled={offset+25>=data.total} onClick={()=>{last.current=null;setOffset(n=>n+25);}}>Ранее</Button><span>{offset+1}–{Math.min(offset+25,data.total)} из {data.total}</span><Button size="sm" variant="ghost" disabled={offset===0} onClick={()=>{last.current=null;setOffset(0);}}>К последним</Button></div>}
    {!data.turns.length&&<div className="assistant-thread-empty"><Icon name="assistant" size={28}/><h2>С чего начнём?</h2><p>Опишите задачу или прикрепите файл.</p></div>}
    {data.turns.map(turn=><article key={turn.turn_id} className="assistant-turn"><div className="assistant-user-message"><div className="assistant-message-meta"><span>Вы</span><Timestamp at={turn.created_at} timezone={timezone}/></div><p>{turn.content}</p></div><div className="assistant-reply"><div className="assistant-message-meta"><span className="assistant-author"><Icon name="assistant" size={16}/>FixRate AI</span>{turn.status!=='running'&&<Timestamp at={turn.finished_at??turn.created_at} timezone={timezone}/>}</div><Progress turn={turn} names={names}/>{turn.status!=='running'&&<p className="assistant-answer">{turn.answer}</p>}{turn.trace.filter(step=>step.resource&&safeResource(step.resource.url)).map((step,i)=><a key={i} className="assistant-resource" href={step.resource!.url} target="_blank" rel="noreferrer">{step.resource!.title}<span aria-hidden="true"> ↗</span></a>)}{turn.error_code&&<p className="assistant-error-code">Код: {turn.error_code}</p>}{turn.status==='failed'&&<Button size="sm" variant="secondary" onClick={()=>{setDraft(turn.content);toBottom();document.getElementById('assistant-message')?.focus();}}>Повторить запрос</Button>}{data.actions.filter(a=>a.turn_id===turn.turn_id).map(action=><ActionCard key={action.action_id} action={action} title={names[action.tool_name]??action.tool_name} attachments={data.attachments} onChanged={refreshAll}/>)}</div></article>)}
    {data.actions.filter(a=>a.turn_id===null).map(action=><ActionCard key={action.action_id} action={action} title={names[action.tool_name]??action.tool_name} attachments={data.attachments} onChanged={refreshAll}/>)}</div></div>
    {!atBottom&&<button className="assistant-jump" type="button" onClick={toBottom} aria-label="К последним сообщениям">↓ К последним сообщениям</button>}
    </div>
    {(error||query.status==='error')&&<div className="assistant-inline-error" role="alert"><Callout tone="danger">{error||(query.status==='error'?query.error:'')}</Callout><Button size="sm" variant="ghost" onClick={()=>setRefresh(n=>n+1)}>Обновить диалог</Button></div>}
    <Composer draft={draft} setDraft={setDraft} onSend={()=>void send()} onUpload={file=>void upload(file)} busy={sending} uploading={uploading} running={running} available={capabilities.available} attachments={data.attachments}/></section>;
}
function HistoryDrawer({open,onClose,children}:{open:boolean;onClose:()=>void;children:ReactNode}){
  const focus=useDialogFocus<HTMLDivElement>(open,onClose);if(!open)return null;
  return createPortal(<div className="assistant-history-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><div className="assistant-history-drawer" ref={focus} role="dialog" aria-modal="true" aria-label="История диалогов"><button className="assistant-history-close" type="button" aria-label="Закрыть историю" onClick={onClose}><Icon name="close" size={20}/></button>{children}</div></div>,document.querySelector('.workspace-root')??document.body);
}
function Workspace(){
  const {profile}=useSession(),timezone=profile?.timezone??'Asia/Yekaterinburg';
  const [params,setParams]=useSearchParams(),[refresh,setRefresh]=useState(0),[listOffset,setListOffset]=useState(0),[creating,setCreating]=useState(false),[uploading,setUploading]=useState(false),[error,setError]=useState(''),[historyOpen,setHistoryOpen]=useState(false);
  const [narrow,setNarrow]=useState(()=>window.matchMedia?.('(max-width: 1279px)').matches??false),[drafts,setDrafts]=useState<Record<string,string>>({});
  const creation=useRef<Promise<string>|null>(null),pending=useRef<{id:string;text:string;key:string}|null>(null);
  useEffect(()=>{const media=window.matchMedia?.('(max-width: 1279px)');if(!media)return;const update=()=>{setNarrow(media.matches);if(!media.matches)setHistoryOpen(false);};update();media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  const caps=useApiQuery(api.capabilities,[],undefined,'assistant:capabilities'),list=useApiQuery(()=>api.list(listOffset),[refresh,listOffset],undefined,`assistant:list:${listOffset}`);
  const identity=params.get('chat')??'',draft=drafts[identity||'new']??'';
  const setDraft=(text:string)=>setDrafts(v=>({...v,[identity||'new']:text}));
  const select=(id:string)=>{setParams({chat:id});setHistoryOpen(false);setError('');},fresh=()=>{creation.current=null;pending.current=null;setDrafts(v=>({...v,new:''}));setParams({});setHistoryOpen(false);setError('');};
  const ensure=()=>{if(!creation.current)creation.current=api.create('assistant').then(chat=>{setRefresh(n=>n+1);return chat.conversation_id;}).catch(e=>{creation.current=null;throw e;});return creation.current;};
  useEffect(()=>{creation.current=null;pending.current=null;},[identity]);
  const start=async(file?:File)=>{if(creating||uploading||(!file&&!draft.trim()))return;setError('');if(file)setUploading(true);else setCreating(true);let id='';const text=draft.trim();try{id=await ensure();if(file){await api.upload(id,file);setDrafts(v=>({...v,[id]:draft}));}else{if(pending.current?.id!==id||pending.current.text!==text)pending.current={id,text,key:crypto.randomUUID()};await api.send(id,text,pending.current.key);setDrafts(v=>({...v,[id]:'',new:''}));}select(id);setRefresh(n=>n+1);}catch(e){setError(e instanceof Error?e.message:'Не удалось начать диалог');}finally{setCreating(false);setUploading(false);}};
  if(caps.status==='loading')return <LoadingState label="Загрузка помощника"/>;
  if(caps.status==='error')return <ErrorState description={caps.error} action={<Button onClick={()=>window.location.reload()}>Повторить загрузку</Button>}/>;
  const history=<><div className="assistant-history-heading"><h2>История чатов</h2><p>Только ваши диалоги на этом объекте</p></div><button type="button" className="assistant-history-new" onClick={fresh}><span>＋</span>Новый чат</button><div className="assistant-history-list">{list.status==='loading'?<p className="assistant-history-empty">Загрузка…</p>:list.status==='error'?<ErrorState description={list.error} action={<Button size="sm" onClick={()=>setRefresh(n=>n+1)}>Повторить</Button>}/>:<>{list.data.items.map(chat=><button key={chat.conversation_id} type="button" aria-current={identity===chat.conversation_id?'true':undefined} className={`assistant-history-item ${identity===chat.conversation_id?'is-active':''}`} onClick={()=>select(chat.conversation_id)}><span>{chat.title}</span><Timestamp at={chat.updated_at} timezone={timezone}/></button>)}{!list.data.total&&<p className="assistant-history-empty">Здесь появятся ваши переписки. Напишите первое сообщение.</p>}</>}</div>{list.status==='success'&&list.data.total>25&&<div className="assistant-history-pages"><Button size="sm" variant="ghost" disabled={!listOffset} onClick={()=>setListOffset(n=>Math.max(0,n-25))}>Назад</Button><Button size="sm" variant="ghost" disabled={listOffset+25>=list.data.total} onClick={()=>setListOffset(n=>n+25)}>Далее</Button></div>}</>;
  return <div className="assistant-workspace"><div className="assistant-center" inert={narrow&&historyOpen} aria-hidden={narrow&&historyOpen||undefined}><header className="assistant-toolbar"><h1>ИИ-помощник</h1><div>{identity&&<button type="button" onClick={fresh}>＋ Новый чат</button>}{narrow&&<button type="button" aria-label="Открыть историю чатов" aria-expanded={historyOpen} onClick={()=>setHistoryOpen(true)}><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 5h16M4 12h16M4 19h11"/></svg><span>История</span></button>}</div></header>
    {!caps.data.available&&<div className="assistant-inline-error"><Callout tone="warning">ИИ пока не подключён. История доступна; для новых ответов настройте серверный ключ AI Tunnel.</Callout></div>}
    {identity?<Chat key={identity} identity={identity} capabilities={caps.data} draft={draft} setDraft={setDraft} onRefreshList={()=>setRefresh(n=>n+1)} timezone={timezone}/>:<section className="assistant-welcome" aria-label="Новый чат"><div className="assistant-welcome-content"><div className="assistant-greeting"><span className="assistant-mark"><Icon name="assistant" size={32}/></span><h2>Чем могу помочь?</h2></div><p className="assistant-welcome-caption">Работы, оборудование, команда и планы — в одном чате.</p><Composer draft={draft} setDraft={setDraft} onSend={()=>void start()} onUpload={file=>void start(file)} busy={creating} uploading={uploading} running={false} available={caps.data.available}/><div className="assistant-starters">{starters.map(text=><button type="button" key={text} onClick={()=>{setDraft(text);document.getElementById('assistant-message')?.focus();}}>{text}<span aria-hidden="true">↗</span></button>)}</div></div></section>}
    {error&&<div className="assistant-inline-error" role="alert"><Callout tone="danger">{error}</Callout></div>}
  </div>{narrow?<HistoryDrawer open={historyOpen} onClose={()=>setHistoryOpen(false)}>{history}</HistoryDrawer>:<aside className="assistant-history" aria-label="История диалогов">{history}</aside>}</div>;
}
export function AssistantPage(){const {profile}=useSession();return <Workspace key={`${profile?.userId}:${profile?.siteId}:${profile?.role}`}/>;}
