import {memo,useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {Link, useSearchParams} from 'react-router-dom';
import {useApiQueryCache} from '@/shared/lib/ApiQueryProvider';
import {assistantTransfer, clearAssistantTransfer, DEFAULT_STARTERS, EXECUTOR_STARTERS} from '@/features/assistant/assistantEntry';
import {useConversationStart} from '@/features/assistant/useConversationStart';
import {useSession} from '@/shared/session/SessionContext';
import {assistantApi as api,type ChatCapabilities,type ChatView,type ChatTurn,type ChatAttachment,type ChatModelPreference} from '@/shared/api/assistant';
import {ApiError} from '@/shared/api/request';
import {AssistantComposer, type ComposerHandle, type ModelControls} from '@/features/assistant/AssistantComposer';
import {isBoolean,useWorkspaceState} from '@/shared/lib/workspaceState';
import {useApiQuery} from '@/shared/lib/useApiQuery';
import {dateTimeFormatter} from '@/shared/lib/dateTimeFormatter';
import {useDialogFocus} from '@/shared/lib/useDialogFocus';
import {Button} from '@/shared/ui/Button';
import {Icon} from '@/shared/ui/Icon';
import {LoadingState,ErrorState} from '@/shared/ui/States';
import {Callout} from '@/shared/ui/Callout';
import {Modal} from '@/shared/ui/Modal';
import {ActionCard} from '@/features/assistant/ActionCard';
import {ActionHistory} from '@/features/assistant/ActionHistory';
import {attachmentUrl,ChatPhoto,isChatPhoto} from '@/features/assistant/ChatPhoto';
import {ChatFileDrop} from '@/features/assistant/ChatFileDrop';
import {SavedAnswer} from '@/features/assistant/SavedAnswer';
import {WorkflowStatus} from '@/features/assistant/WorkflowStatus';
import '@/features/assistant/assistant.css';

const safeResource=(url:string)=>/^\/api\/v1\/(maintenance\/|assistant\/attachments\/)/.test(url);
const safePhoto=(url:string)=>/^\/api\/v1\/(?:maintenance\/photos\/[0-9a-f-]+(?:\/content)?|assistant\/attachments\/[0-9a-f-]+)$/i.test(url);
const Timestamp=memo(function Timestamp({at,timezone}:{at:string;timezone:string}){
  const date=new Date(at);if(Number.isNaN(date.getTime()))return null;
  const label=dateTimeFormatter('ru-RU',{timeZone:timezone,day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
  return <time dateTime={at} title={`${label} · ${timezone}`}>{label}</time>;
});
function activity(tool:string,names:Record<string,string>){
  if(tool==='__planning')return 'Разбираю поручение на пункты';
  if(tool==='__routing')return 'Разбираюсь в запросе';
  if(tool==='__responding')return 'Сопоставляю данные и готовлю ответ';
  if(tool==='__quality_gate')return 'Проверяю выполнение пунктов и источники';
  if(tool==='describe_tool')return 'Уточняю параметры действия';
  if(tool==='tasks_find'||tool==='tasks_list')return 'Ищу подходящие задания и ближайшее ТО';
  if(tool==='assignment_context')return 'Проверяю условия назначения и доступных работников';
  if(tool==='assignment_preview')return 'Проверяю состав бригады, допуски и время';
  if(tool==='task_assign')return 'Готовлю предложение о назначении';
  if(tool==='staff_find'||tool==='staff_read'||tool==='workforce_read')return 'Изучаю сотрудников, смены и квалификации';
  if(tool.includes('import_preview'))return 'Проверяю файл и данные для импорта';
  if(tool==='attachment_read')return 'Читаю листы и строки прикреплённой таблицы';
  if(tool==='equipment_find')return 'Ищу оборудование в реестре';
  return names[tool]??'Выполняю проверку данных';
}
const Progress=memo(function Progress({turn,names}:{turn:ChatTurn;names:Record<string,string>}){
  const [expanded,setExpanded]=useState(turn.status==='running');
  const running=turn.status==='running',active=[...turn.trace].reverse().find(s=>s.status==='running');
  const unique=new Map<string,{label:string;status:string;code?:number;fact?:ChatTurn['trace'][number]['fact']}>();
  for(const step of turn.trace){if(step.tool.startsWith('__')||(running&&step.status==='running'))continue;const label=activity(step.tool,names);unique.set(`${label}:${step.status}`,{label,status:step.status,code:step.code,fact:step.fact});}
  const steps=[...unique.values()].filter(step=>!running||step.status==='denied'||step.label!==activity(active?.tool??'__routing',names));
  const current=activity(active?.tool??'__routing',names);
  return <details className="assistant-progress" open={expanded} onToggle={e=>setExpanded(e.currentTarget.open)}><summary><svg className="assistant-progress-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="5" ry="10" transform="rotate(45 12 12)"/><ellipse cx="12" cy="12" rx="5" ry="10" transform="rotate(-45 12 12)"/></svg><Elapsed start={turn.created_at} end={turn.finished_at} status={turn.status}/><svg className="assistant-progress-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m3 6 5 5 5-5"/></svg></summary><div className="assistant-progress-body"><ol>{steps.map((step,i)=><li key={i}>{step.label}{step.status==='denied'&&(step.code===422?' — один из запросов содержал неверные параметры':step.code===404?' — указанная запись не найдена':step.code===403?' — доступ к этому действию ограничен':' — запрос не выполнен')}{step.status==='running'&&' — выполнение прервано'}{step.status==='proposed'&&' — нужно подтверждение'}{step.status==='completed'&&typeof step.fact?.total==='number'&&` — по условиям найдено ${step.fact.total}${typeof step.fact.shown==='number'&&step.fact.shown<step.fact.total?`, проверено на странице: ${step.fact.shown}`:''}`}{step.status==='completed'&&typeof step.fact?.ready==='boolean'&&(step.fact.ready?' — подходящий вариант найден':' — подходящий вариант пока не подтверждён')}</li>)}{running?<li role="status">{current}…</li>:steps.length===0?<li>{turn.status==='failed'?'Не удалось завершить ответ':'Ответ подготовлен'}</li>:null}</ol></div></details>;
});
const Elapsed=memo(function Elapsed({start,end,status}:{start:string;end?:string|null;status:ChatTurn['status']}){
  const running=status==='running';
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{if(!running)return;setNow(Date.now());const id=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(id);},[running,start]);
  const begin=Date.parse(start),finish=running?now:end?Date.parse(end):NaN;
  if(!Number.isFinite(begin)||!Number.isFinite(finish))return <span>Ход выполнения</span>;
  const seconds=Math.max(0,Math.floor((finish-begin)/1000)),minutes=Math.floor(seconds/60);
  const plural=(n:number,one:string,few:string,many:string)=>{const mod=n%100;return mod>=11&&mod<=14?many:n%10===1?one:n%10>=2&&n%10<=4?few:many;};
  const time=(minutes?`${minutes} ${plural(minutes,'минуту','минуты','минут')} `:'')+`${seconds%60} ${plural(seconds%60,'секунду','секунды','секунд')}`;
  return <span className="assistant-elapsed" aria-label={`Время выполнения: ${minutes} мин ${seconds%60} сек`}>{running?'Работаю':status==='failed'?'Прервано через':'Ответ завершён за'} {time}</span>;
});
function SentFiles({files}:{files?:ChatAttachment[]}){
  if(!files?.length)return null;
  return <ul className="assistant-sent-files" aria-label="Отправленные файлы">{files.map(file=><li key={file.attachment_id}>{isChatPhoto(file.mime_type)?
    <ChatPhoto url={attachmentUrl(file.attachment_id)} title={file.original_name}/>:
    <><a href={attachmentUrl(file.attachment_id)} target="_blank" rel="noreferrer">{file.original_name}</a><span>{Math.ceil(file.size_bytes/1024)} КБ</span></>}</li>)}</ul>;
}
function ChatResources({trace}:{trace:ChatTurn['trace']}){
  const resources=new Map(trace.flatMap(step=>step.resource?[[step.resource.url,step.resource] as const]:[]));
  if(!resources.size)return null;
  return <div className="assistant-chat-resources">{[...resources.values()].filter(resource=>safeResource(resource.url)).map(resource=>
    isChatPhoto(resource.mime)&&safePhoto(resource.url)?
      <ChatPhoto key={resource.url} url={resource.url} title={resource.title}/>:
      <a key={resource.url} className="assistant-resource" href={resource.url} target="_blank" rel="noreferrer">{resource.title}<span aria-hidden="true"> ↗</span></a>)}</div>;
}
// The transcript only changes with the conversation, not with each composer keystroke.
const ChatMessages = memo(function ChatMessages({turns,actions,attachments,names,timezone,busy,onResume,onRetry,onChanged}:{
  turns: ChatView['turns']; actions: ChatView['actions']; attachments: ChatView['attachments'];
  names: Record<string,string>; timezone: string; busy: boolean;
  onResume?: (turn:ChatTurn)=>Promise<void>; onRetry: (content:string)=>void; onChanged: ()=>void;
}){
  const actionsByTurn = useMemo(() => {
    const groups = new Map<string|null, ChatView['actions']>();
    for (const action of actions) {
      const group = groups.get(action.turn_id);
      if (group) group.push(action);
      else groups.set(action.turn_id, [action]);
    }
    return groups;
  }, [actions]);
  return <>
    {turns.map(turn=><article key={turn.turn_id} className="assistant-turn"><div className="assistant-user-message"><div className="assistant-message-meta"><span>Вы</span><Timestamp at={turn.created_at} timezone={timezone}/></div><p>{turn.content}</p><SentFiles files={turn.attachments}/></div><div className="assistant-reply"><div className="assistant-message-meta"><span className="assistant-author"><Icon name="assistant" size={16}/>FixRate AI</span><Timestamp at={turn.finished_at??turn.created_at} timezone={timezone}/></div><Progress turn={turn} names={names}/><WorkflowStatus workflow={turn.workflow} disabled={busy} onResume={onResume?()=>void onResume(turn):undefined}/>{turn.status!=='running'&&<SavedAnswer answer={turn.answer} facts={turn.workflow?.answer_format==='facts'} older={turn!==turns.at(-1)}/>}<ChatResources trace={turn.trace}/>{turn.error_code&&turn.error_code!=='ASSISTANT_STOPPED'&&<details className="assistant-error-code"><summary>Технические сведения</summary><p>Код: {turn.error_code}</p></details>}{turn.status==='failed'&&!turn.workflow&&<Button size="sm" variant="secondary" onClick={()=>onRetry(turn.content)}>Повторить запрос</Button>}{(actionsByTurn.get(turn.turn_id)??[]).map(action=><ActionCard key={action.action_id} action={action} title={names[action.tool_name]??action.tool_name} attachments={attachments} onChanged={onChanged}/>)}</div></article>)}
    {(actionsByTurn.get(null)??[]).map(action=><ActionCard key={action.action_id} action={action} title={names[action.tool_name]??action.tool_name} attachments={attachments} onChanged={onChanged}/>)}
  </>;
});
function Chat({identity,capabilities,initialDraft,initialAttachments,onDraftChange,onRefreshList,timezone,modelPreference,onModelChange,entryRect,onEntryComplete}:{identity:string;capabilities:ChatCapabilities;initialDraft:string;initialAttachments?:ChatAttachment[];onDraftChange:(id:string,text:string)=>void;onRefreshList:()=>void;timezone:string;entryRect?:DOMRectReadOnly;onEntryComplete:()=>void}&ModelControls){
  const toolCalling=capabilities.prompt_version==='fixrate-tool-calling-v4';
  const [refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0),[sending,setSending]=useState(false),[uploading,setUploading]=useState(false),[error,setError]=useState(''),[showJump,setShowJump]=useState(false);
  const composer = useRef<ComposerHandle>(null);
  const uploadInFlight=useRef(false);
  const [localFiles,setLocalFiles]=useState<ChatAttachment[]>(()=>initialAttachments??[]),[excludedFiles,setExcludedFiles]=useState<string[]>([]);
  const attempt=useRef({signature:'',key:crypto.randomUUID()}),last=useRef<ChatView|null>(null);
  const resumeAttempts=useRef(new Map<string,string>());
  const scroll=useRef<HTMLDivElement>(null),transcript=useRef<HTMLDivElement>(null),pinned=useRef(true),jumpVisible=useRef(false),openedOffset=useRef<number|null>(null),followNext=useRef(false);
  const query=useApiQuery(()=>api.read(identity,offset),[identity,offset,refresh],data=>data.turns.some(t=>t.status==='running')||data.actions.some(a=>a.status==='executing'),`assistant:thread:${identity}:${offset}`);
  const names=useMemo(()=>Object.fromEntries(capabilities.tools.assistant.map(t=>[t.name,t.title])),[capabilities.tools.assistant]);
  if(query.status==='success')last.current=query.data;
  const data=query.status==='success'?query.data:last.current;
  const updateJump=(el:HTMLDivElement)=>{const distance=el.scrollHeight-el.scrollTop-el.clientHeight,visible=distance>Math.max(240,Math.min(480,el.clientHeight*.7));if(jumpVisible.current!==visible){jumpVisible.current=visible;setShowJump(visible);}};
  const toBottom=useCallback(()=>{const el=scroll.current;if(el){el.scrollTop=el.scrollHeight;pinned.current=true;jumpVisible.current=false;setShowJump(false);}},[]);
  useLayoutEffect(()=>{const el=scroll.current;if(!el||!data)return;if(openedOffset.current!==offset){el.scrollTop=offset===0?el.scrollHeight:0;openedOffset.current=offset;pinned.current=offset===0;updateJump(el);}else if(pinned.current||followNext.current){toBottom();followNext.current=false;}else updateJump(el);},[data,offset]);
  useEffect(()=>{const el=transcript.current;if(!el||typeof ResizeObserver==='undefined')return;const observer=new ResizeObserver(()=>{const region=scroll.current;if(!region)return;if(pinned.current)region.scrollTop=region.scrollHeight;else updateJump(region);});observer.observe(el);return()=>observer.disconnect();},[!!data]);
  const running=data?.turns.some(t=>t.status==='running')??false;
  const refreshAll=useCallback(()=>{setRefresh(n=>n+1);onRefreshList();},[onRefreshList]);
  const resume=useCallback(async(turn:ChatTurn)=>{if(sending||running||uploading)return;const key=resumeAttempts.current.get(turn.turn_id)??crypto.randomUUID();resumeAttempts.current.set(turn.turn_id,key);setSending(true);setError('');try{await api.send(identity,'Продолжить сохранённое поручение.',key,[],modelPreference?.revision,turn.turn_id);resumeAttempts.current.delete(turn.turn_id);setOffset(0);followNext.current=true;refreshAll();}catch(e){setError(e instanceof Error?e.message:'Не удалось продолжить поручение');}finally{setSending(false);}},[sending,running,uploading,identity,modelPreference?.revision,refreshAll]);
  const retry=useCallback((content:string)=>{
    composer.current?.replaceDraft(content);
    toBottom();
    composer.current?.focus();
  },[toBottom]);
  if(!data)return query.status==='error'?<ErrorState description={query.error} action={<Button onClick={()=>setRefresh(n=>n+1)}>Повторить загрузку</Button>}/>:<LoadingState label="Загрузка диалога"/>;
  const stop=async()=>{const turn=data.turns.find(t=>t.status==='running');if(!turn||sending)return;setSending(true);setError('');try{await api.stop(identity,turn.turn_id);refreshAll();}catch(e){setError(e instanceof Error?e.message:'Не удалось остановить ответ');}finally{setSending(false);}};
  const localFileIds=new Set(localFiles.map(file=>file.attachment_id));
  // The server lists pending files newest first; local additions keep their selection order.
  const savedFiles=(data.pending_attachments??[]).slice().reverse().filter(file=>!localFileIds.has(file.attachment_id));
  const files=[...savedFiles,...localFiles].filter(file=>!excludedFiles.includes(file.attachment_id));
  const upload=async(batch:File[])=>{
    if(uploadInFlight.current||sending||running)return;
    if(files.length+batch.length>20){setError('К одному сообщению можно прикрепить не больше 20 файлов');return;}
    if(files.filter(f=>isChatPhoto(f.mime_type)).length+batch.filter(f=>f.type.startsWith('image/')).length>4){
      setError('К одному сообщению можно отправить не больше четырёх изображений');return;
    }
    uploadInFlight.current=true;setUploading(true);setError('');
    try{
      for(const file of batch){
        const saved=await api.upload(identity,file);
        setLocalFiles(current=>[...current.filter(f=>f.attachment_id!==saved.attachment_id),saved]);
        setExcludedFiles(ids=>ids.filter(id=>id!==saved.attachment_id));
      }
    }catch(e){setError(e instanceof Error?e.message:'Не удалось прикрепить файл');}
    finally{uploadInFlight.current=false;setUploading(false);refreshAll();}
  };
  const send=async(draft:string)=>{
    if((!draft.trim()&&!files.length)||sending||running||uploadInFlight.current)return;
    const text=draft.trim(),ids=files.map(f=>f.attachment_id);
    let resumeTurnId: string | undefined;
    if(!toolCalling&&/^факты\s*:/i.test(text)){
      const workflows = new Map<string,ChatTurn>();
      for(const turn of data.turns){
        const root=turn.workflow?.root_turn_id;
        if(turn.workflow?.kind==='task_execution'&&root)workflows.set(root,turn);
      }
      const targets=[...workflows.values()].filter(turn=>turn.workflow?.goals.some(goal=>goal.id==='draft'&&goal.status==='awaiting_input'));
      if(offset!==0||targets.length!==1){
        setError('Отправка фактов в диалоге доступна для одного открытого отчёта. Внесите данные в карточке нужного задания и продолжите это поручение.');
        return;
      }
      resumeTurnId=targets[0].turn_id;
    }
    const signature=JSON.stringify([text,ids,modelPreference?.revision,resumeTurnId]);
    if(attempt.current.signature!==signature)attempt.current={signature,key:crypto.randomUUID()};
    setLocalFiles(files);setSending(true);setError('');
    try{
      if(resumeTurnId)await api.send(identity,text,attempt.current.key,ids,modelPreference?.revision,resumeTurnId);
      else if(modelPreference)await api.send(identity,text,attempt.current.key,ids,modelPreference.revision);
      else await api.send(identity,text,attempt.current.key,ids);
      attempt.current={signature:'',key:crypto.randomUUID()};setLocalFiles([]);
      setExcludedFiles(current=>[...new Set([...current,...ids])]);composer.current?.replaceDraft('');
      setOffset(0);followNext.current=true;refreshAll();
    }catch(e){
      setError(e instanceof Error?e.message:'Не удалось отправить сообщение');
      if(e instanceof ApiError&&e.status===409&&modelPreference)try{onModelChange(await api.modelPreference());}catch{/* Preserve the draft on a failed refresh. */}
      setRefresh(n=>n+1);
    }finally{setSending(false);}
  };
  return <ChatFileDrop className="assistant-chat" data-composer-entry={entryRect ? "" : undefined} aria-label="Диалог с ИИ" blocked={sending||running||uploading} onFiles={batch=>void upload(batch)}><div className="assistant-body"><div className="assistant-transcript" ref={scroll} role="region" aria-label="Сообщения" tabIndex={0} onScroll={()=>{const el=scroll.current;if(el){pinned.current=el.scrollHeight-el.scrollTop-el.clientHeight<72;updateJump(el);}}}><div className="assistant-transcript-inner" ref={transcript}>
    {data.total>25&&<div className="assistant-pagination"><Button size="sm" variant="ghost" disabled={offset+25>=data.total} onClick={()=>{last.current=null;setOffset(n=>n+25);}}>Ранее</Button><span>{offset+1}–{Math.min(offset+25,data.total)} из {data.total}</span><Button size="sm" variant="ghost" disabled={offset===0} onClick={()=>{last.current=null;setOffset(0);}}>К последним</Button></div>}
    {!data.turns.length&&<div className="assistant-thread-empty"><Icon name="assistant" size={28}/><h2>{data.conversation.subject_task_id?'Вопрос по выбранному наряду':'С чего начнём?'}</h2><p>Опишите задачу или прикрепите файл.</p></div>}
    <ChatMessages turns={data.turns} actions={data.actions} attachments={data.attachments} names={names}
      timezone={timezone} busy={sending||running||uploading} onResume={toolCalling?undefined:resume} onRetry={retry} onChanged={refreshAll}/></div></div>
    {showJump&&<button className="assistant-jump" type="button" onClick={toBottom} aria-label="К последним сообщениям">↓ К последним сообщениям</button>}
    </div>
    {(error||query.status==='error')&&<div className="assistant-inline-error" role="alert"><Callout tone="danger">{error||(query.status==='error'?query.error:'')}</Callout><Button size="sm" variant="ghost" onClick={()=>setRefresh(n=>n+1)}>Обновить диалог</Button></div>}
    <AssistantComposer compact entryRect={entryRect} onEntryComplete={onEntryComplete} ref={composer} initialDraft={initialDraft} onDraftChange={text=>onDraftChange(identity,text)} onSend={text=>void send(text)} onUpload={file=>void upload(file)} onRemove={id=>setExcludedFiles(ids=>[...ids,id])} onStop={()=>void stop()} busy={sending} uploading={uploading} running={running} available={capabilities.available} attachments={files} modelPreference={modelPreference} onModelChange={onModelChange}/></ChatFileDrop>;
}
function HistoryDrawer({open,onClose,children}:{open:boolean;onClose:()=>void;children:ReactNode}){
  const focus=useDialogFocus<HTMLDivElement>(open,onClose);if(!open)return null;
  return createPortal(<div className="assistant-history-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><div id="assistant-history" className="assistant-history-drawer" ref={focus} role="dialog" aria-modal="true" aria-label="История диалогов"><button className="assistant-history-close" type="button" aria-label="Закрыть историю" onClick={onClose}><Icon name="close" size={20}/></button>{children}</div></div>,document.querySelector('.workspace-root')??document.body);
}
function Workspace(){
  const {profile}=useSession(),timezone=profile?.timezone??'Asia/Yekaterinburg';
  const executor = profile?.role === 'executor';
  const starters = executor ? EXECUTOR_STARTERS : DEFAULT_STARTERS;
  const cache=useApiQueryCache();
  const [params,setParams]=useSearchParams(),[refresh,setRefresh]=useState(0),[listOffset,setListOffset]=useState(0),[historyOpen,setHistoryOpen]=useState(false);
  const identity=params.get('chat')??'';
  const subjectTaskId=identity?undefined:params.get('task')??undefined;
  const showActions=params.get('view')==='actions';
  const chatParams=new URLSearchParams(identity ? {chat:identity} : subjectTaskId ? {task:subjectTaskId} : {});
  const actionParams=new URLSearchParams(chatParams);
  actionParams.set('view','actions');
  const [capsRetry, retryCaps]=useState(0);
  const [entry,setEntry]=useState(()=>assistantTransfer(cache, identity));
  const entryRect=entry?.id===identity?entry.rect:undefined;
  const welcome=useRef<HTMLDivElement>(null);
  const completeEntry=useCallback(()=>setEntry(undefined),[]);
  const [narrow,setNarrow]=useState(()=>window.matchMedia?.('(max-width: 1279px)').matches??false);
  const [drafts]=useState(()=>new Map(entry ? [[entry.id,entry.draft]] : []));
  const welcomeDraft = useRef('');
  const welcomeComposer = useRef<ComposerHandle>(null);
  const [deleting,setDeleting]=useState<{id:string;title:string}|null>(null),[deleteBusy,setDeleteBusy]=useState(false),[deleteError,setDeleteError]=useState('');
  const [historyVisible,setHistoryVisible]=useWorkspaceState('assistant.history.visible',true,isBoolean);
  const [welcomeHistory,setWelcomeHistory]=useState(false);
  const showDesktopHistory = identity ? historyVisible : welcomeHistory;
  const inlineHistory = !identity && (narrow || !showDesktopHistory);
  const toggleHistory = () => {
    if (narrow) setHistoryOpen(true);
    else if (identity) setHistoryVisible(value => !value);
    else setWelcomeHistory(value => !value);
  };
  const [modelOverride,setModelOverride]=useState<ChatModelPreference>();
  useEffect(()=>{clearAssistantTransfer(cache);},[cache]);
  useEffect(()=>{const media=window.matchMedia?.('(max-width: 1279px)');if(!media)return;const update=()=>{setNarrow(media.matches);if(!media.matches)setHistoryOpen(false);};update();media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  const caps=useApiQuery(api.capabilities,[capsRetry],undefined,'assistant:capabilities'),list=useApiQuery(()=>api.list(listOffset),[refresh,listOffset],undefined,`assistant:list:${listOffset}`);
  const serverModel=caps.status==='success'?caps.data.model_preference:undefined;
  const modelPreference=modelOverride&&modelOverride.revision>=(serverModel?.revision??0)?modelOverride:serverModel;
  const rememberDraft=useCallback((id:string,text:string)=>{
    if(text)drafts.set(id,text);
    else drafts.delete(id);
  },[drafts]);
  const refreshList=useCallback(()=>setRefresh(n=>n+1),[]);
  const select=(id:string)=>{setParams({chat:id});setHistoryOpen(false);};
  const launch=useConversationStart({
    model:modelPreference,subjectTaskId,onModelChange:setModelOverride,readDraft:()=>welcomeDraft.current,
    onOpen(id,remainingDraft,attachments){
      const rect=welcome.current?.querySelector('form')?.getBoundingClientRect();
      setEntry({id,draft:remainingDraft,rect,attachments});
      rememberDraft(id,remainingDraft);
      welcomeDraft.current = '';
      select(id);setRefresh(n=>n+1);
    },
  });
  useEffect(()=>{
    launch.reset();
    setEntry(current=>current?.id===identity?current:undefined);
  },[identity,subjectTaskId]);
  const fresh=()=>{launch.reset();welcomeDraft.current='';welcomeComposer.current?.replaceDraft('');setParams({});setHistoryOpen(false);};
  const remove=async()=>{if(!deleting||deleteBusy)return;setDeleteBusy(true);setDeleteError('');try{await api.remove(deleting.id);if(identity===deleting.id)fresh();drafts.delete(deleting.id);setDeleting(null);setListOffset(0);setRefresh(n=>n+1);}catch(e){setDeleteError(e instanceof Error?e.message:'Не удалось удалить чат');}finally{setDeleteBusy(false);}};
  const history=<><div className="assistant-history-heading"><h2>{inlineHistory&&!historyOpen?"Недавние диалоги":"История чатов"}</h2></div><button type="button" className="assistant-history-new" onClick={fresh}><span>＋</span>Новый чат</button><div className="assistant-history-list">{list.status==='loading'?<p className="assistant-history-empty">Загрузка…</p>:list.status==='error'?<ErrorState description={list.error} action={<Button size="sm" onClick={()=>setRefresh(n=>n+1)}>Повторить</Button>}/>:<>{list.data.items.map(chat=><div className="assistant-history-row" key={chat.conversation_id}><button type="button" aria-current={identity===chat.conversation_id?'true':undefined} className={`assistant-history-item ${identity===chat.conversation_id?'is-active':''}`} onClick={()=>select(chat.conversation_id)}><span>{chat.title}</span><Timestamp at={chat.updated_at} timezone={timezone}/></button><button type="button" className="assistant-history-delete" title="Удалить чат" aria-label={`Удалить чат ${chat.title}`} onClick={()=>{setDeleteError('');setHistoryOpen(false);setDeleting({id:chat.conversation_id,title:chat.title});}}><Icon name="trash" size={17}/></button></div>)}{!list.data.total&&<p className="assistant-history-empty">Диалогов пока нет.</p>}</>}</div>{list.status==='success'&&list.data.total>25&&<div className="assistant-history-pages"><Button size="sm" variant="ghost" disabled={!listOffset} onClick={()=>setListOffset(n=>Math.max(0,n-25))}>Назад</Button><Button size="sm" variant="ghost" disabled={listOffset+25>=list.data.total} onClick={()=>setListOffset(n=>n+25)}>Далее</Button></div>}</>;
  const drawerOpen=!showActions&&narrow&&historyOpen;
  return <div className="assistant-workspace" data-chat-open={identity&&!showActions ? "" : undefined} data-composer-pending={entryRect ? "" : undefined} data-history-visible={!showActions&&(narrow?historyOpen:showDesktopHistory)}>
    <div className="assistant-center" inert={drawerOpen} aria-hidden={drawerOpen||undefined}>
      <header className="assistant-toolbar">
        <h1 className="sr-only">ИИ-помощник</h1>
        <nav className="assistant-sections" aria-label="Разделы помощника">
          <Link to={{search:chatParams.toString()}} aria-current={showActions?undefined:'page'}>Диалоги</Link>
          <Link to={{search:actionParams.toString()}} aria-current={showActions?'page':undefined}>История действий</Link>
        </nav>
        {!showActions&&caps.status==='success'&&<div className="assistant-toolbar-pill" role="group" aria-label="Управление чатом"><button type="button" aria-label={narrow?'Открыть историю чатов':showDesktopHistory?'Свернуть историю чатов':'Развернуть историю чатов'} title={narrow?'История чатов':showDesktopHistory?'Свернуть историю':'Развернуть историю'} aria-expanded={narrow?historyOpen:showDesktopHistory} aria-controls="assistant-history" onClick={toggleHistory}><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"/><path d="M15 3v18"/></svg></button><button type="button" aria-label="Новый чат" title="Новый чат" onClick={fresh}><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 20l-3 1 1-4a9 9 0 1 1 4 3"/><path d="M12 7v8m-4-4h8"/></svg></button></div>}
      </header>
      {showActions&&<ActionHistory timezone={timezone}/>}
      <div className="assistant-dialog-panel" hidden={showActions}>
      {caps.status==='loading'&&<LoadingState label="Загрузка помощника"/>}
      {caps.status==='error'&&<ErrorState description={caps.error} action={<Button onClick={()=>retryCaps(value=>value+1)}>Повторить загрузку</Button>}/>}
      {caps.status==='success'&&<>
    {!(modelPreference?.available??caps.data.available)&&<div className="assistant-inline-error"><Callout tone="warning">ИИ пока не подключён. История доступна; выберите доступную модель рядом с кнопкой «Файл».</Callout></div>}
    {identity ? <Chat key={identity} identity={identity} entryRect={entryRect} onEntryComplete={completeEntry} capabilities={caps.data} initialDraft={drafts.get(identity)??''} initialAttachments={entry?.id===identity?entry.attachments:undefined} onDraftChange={rememberDraft} onRefreshList={refreshList} timezone={timezone} modelPreference={modelPreference} onModelChange={setModelOverride}/> :
      <ChatFileDrop className="assistant-welcome" aria-label="Новый чат" blocked={!!launch.operation}
        onFiles={files=>void launch.start(welcomeDraft.current,{files})}>
        <div ref={welcome} className="assistant-welcome-content">
          <div className="assistant-greeting"><h2>С чего начнём?</h2></div>
          <p className="assistant-welcome-caption">{subjectTaskId?"Диалог по выбранному наряду: задайте вопрос или приложите фото.":executor?"Инструкции, фото и вопросы по вашим заданиям.":"Работы, оборудование, команда и планы."}</p>
          <AssistantComposer ref={welcomeComposer} showMark initialDraft={welcomeDraft.current} onDraftChange={text=>{welcomeDraft.current=text;}} onSend={text=>void launch.start(text)}
            onUpload={(files,text)=>void launch.start(text,{files})} busy={launch.operation==="send"} uploading={launch.operation==="upload"}
            running={false} available={caps.data.available} modelPreference={modelPreference} onModelChange={setModelOverride}/>
          <div className="assistant-starters">{starters.map(preset=><button type="button" key={preset.label} disabled={!!launch.operation||!(modelPreference?.available??caps.data.available)}
            onClick={()=>void launch.start(preset.prompt,{remainingDraft:welcomeDraft.current})}>{preset.label}</button>)}</div>
          {inlineHistory&&!(narrow&&historyOpen)&&<div className="assistant-recent">{history}</div>}
        </div>
      </ChatFileDrop>}
    {launch.error&&<div className="assistant-inline-error" role="alert"><Callout tone="danger">{launch.error}</Callout></div>}
    </>}
  </div></div>{narrow?<HistoryDrawer open={drawerOpen} onClose={()=>setHistoryOpen(false)}>{history}</HistoryDrawer>:<aside id="assistant-history" className="assistant-history" aria-label="История диалогов" hidden={showActions||!showDesktopHistory}>{history}</aside>}<Modal open={!!deleting&&!showActions} title="Удалить чат?" description="Переписка и прикреплённые файлы будут удалены без возможности восстановления." onClose={()=>{if(!deleteBusy)setDeleting(null);}} tone="danger" instant footer={<><Button variant="secondary" disabled={deleteBusy} onClick={()=>setDeleting(null)}>Отмена</Button><Button disabled={deleteBusy} onClick={()=>void remove()}>{deleteBusy?'Удаление…':'Удалить чат'}</Button></>}><p className="assistant-delete-title">{deleting?.title}</p>{deleteError&&<Callout tone="danger">{deleteError}</Callout>}</Modal></div>;
}
export function AssistantPage(){const {profile}=useSession();return <Workspace key={`${profile?.userId}:${profile?.siteId}:${profile?.role}`}/>;}
