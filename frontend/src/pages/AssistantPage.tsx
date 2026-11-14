import {useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {useSession} from '@/shared/session/SessionContext';
import {assistantApi as api,type AgentId,type ChatCapabilities,type ChatView} from '@/shared/api/assistant';
import {useApiQuery} from '@/shared/lib/useApiQuery';
import {Button} from '@/shared/ui/Button';
import {Textarea} from '@/shared/ui/Form';
import {PageHeader} from '@/shared/ui/PageHeader';
import {LoadingState,ErrorState} from '@/shared/ui/States';
import {Callout} from '@/shared/ui/Callout';
import {ActionCard} from '@/features/assistant/ActionCard';

const starters:Record<AgentId,string[]>={assistant:['Какие работы требуют внимания?','Помоги найти оборудование','Что ты можешь сделать в моей роли?'],planner:['Покажи сохранённые общие планы','Помоги проверить нагрузку выбранного плана','Каких данных не хватает для планирования?'],photo:['Помоги найти фотоотчёт для анализа','Какие фотографии нужны для проверки?','Объясни ограничения фотоанализа']};

function Chat({identity,capabilities,draft,setDraft,onRefreshList}:{identity:string;capabilities:ChatCapabilities;draft:string;setDraft:(s:string)=>void;onRefreshList:()=>void}){
  const [refresh,setRefresh]=useState(0),[offset,setOffset]=useState(0),[sending,setSending]=useState(false),[error,setError]=useState('');
  const attempt=useRef({text:'',key:crypto.randomUUID()});
  const last=useRef<ChatView|null>(null);
  const query=useApiQuery(()=>api.read(identity,offset),[identity,offset,refresh],data=>data.turns.some(t=>t.status==='running')||data.actions.some(a=>a.status==='executing'),`assistant:thread:${identity}:${offset}`);
  if(query.status==='success')last.current=query.data;
  const data=query.status==='success'?query.data:last.current;
  const bottom=useRef<HTMLDivElement>(null);
  if(!data)return query.status==='error'?<ErrorState description={query.error}/>:<LoadingState label="Загрузка диалога"/>;
  const tools=capabilities.tools[data.conversation.agent]??[];
  const names=Object.fromEntries(tools.map(t=>[t.name,t.title]));
  const running=data.turns.some(t=>t.status==='running');
  const refreshAll=()=>{setRefresh(n=>n+1);onRefreshList();};
  const send=async()=>{
    if(!draft.trim()||sending||running)return;
    const text=draft.trim();if(attempt.current.text!==text)attempt.current={text,key:crypto.randomUUID()};
    setSending(true);setError('');
    try{await api.send(identity,text,attempt.current.key);setDraft('');setOffset(0);refreshAll();}
    catch(e){setError(e instanceof Error?e.message:'Не удалось отправить сообщение');setRefresh(n=>n+1);}
    finally{setSending(false);}
  };
  return <section className="min-w-0 space-y-5" aria-label="Диалог с ИИ">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3"><h2 className="min-w-0 break-words font-semibold">{data.conversation.title}</h2><Button size="sm" variant="ghost" onClick={()=>bottom.current?.scrollIntoView({block:'end'})}>К сообщению</Button></div>
    {data.total>25&&<div className="flex flex-wrap items-center gap-3 text-sm"><Button size="sm" variant="secondary" disabled={offset+25>=data.total} onClick={()=>{last.current=null;setOffset(n=>n+25);}}>Ранее</Button><span>{offset+1}–{Math.min(offset+25,data.total)} из {data.total}</span><Button size="sm" variant="secondary" disabled={offset===0} onClick={()=>{last.current=null;setOffset(n=>Math.max(0,n-25));}}>Позже</Button></div>}
    {!data.turns.length&&<div className="space-y-4 py-8"><h3 className="text-xl font-semibold">С чего начнём?</h3><p className="text-sm text-muted">Опишите задачу обычными словами. Я изучу доступные данные, уточню детали и предложу действие.</p><div className="flex flex-wrap gap-2">{starters[data.conversation.agent].map(text=><Button key={text} variant="secondary" size="sm" className="h-auto whitespace-normal text-left" onClick={()=>setDraft(text)}>{text}</Button>)}</div></div>}
    <div className="space-y-6" aria-label="Сообщения">{data.turns.map(turn=><article key={turn.turn_id} className="min-w-0 space-y-4"><div className="ml-auto max-w-[94%] rounded-2xl rounded-tr-sm bg-accent/10 px-4 py-3"><p className="mb-1 text-xs text-muted">Вы</p><p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{turn.content}</p></div><div className="space-y-3"><p className="text-xs font-semibold text-accent">{capabilities.agents.find(a=>a.id===data.conversation.agent)?.title??'Ассистент'}</p>{turn.status==='running'?<p role="status" className="text-sm text-muted">Изучаю запрос и доступные данные…</p>:<p className="whitespace-pre-wrap break-words leading-relaxed [overflow-wrap:anywhere]">{turn.answer}</p>}{turn.error_code&&<p className="text-xs text-muted">Код: {turn.error_code}</p>}{turn.trace.length>0&&<details className="text-xs text-muted"><summary className="cursor-pointer">Действия помощника · {turn.trace.length}</summary><ul className="mt-2 space-y-1">{turn.trace.map((step,i)=><li key={i}>{names[step.tool]??step.tool}: {step.status==='completed'?'данные получены':step.status==='proposed'?'ожидает подтверждения':'отклонено системой'}</li>)}</ul></details>}{data.actions.filter(a=>a.turn_id===turn.turn_id).map(action=><ActionCard key={action.action_id} action={action} title={names[action.tool_name]??action.tool_name} onChanged={refreshAll}/>)}</div></article>)}</div>
    {data.actions.filter(a=>a.turn_id===null).map(action=><ActionCard key={action.action_id} action={action} title={names[action.tool_name]??action.tool_name} onChanged={refreshAll}/>)}
    <form onSubmit={e=>{e.preventDefault();void send();}} className="space-y-3 rounded-2xl border border-line bg-surface p-3 sm:p-4">
      <label className="sr-only" htmlFor="assistant-message">Сообщение помощнику</label><Textarea id="assistant-message" value={draft} maxLength={12000} rows={3} placeholder="Например: найди просроченные работы и помоги распределить их" onChange={e=>setDraft(e.target.value)} disabled={sending} className="resize-y"/>
      <div className="flex flex-wrap items-center justify-between gap-2"><p className="max-w-lg text-xs text-muted">Изменения выполняются после вашего подтверждения. ИИ может ошибаться — проверяйте данные.</p><Button type="submit" disabled={!capabilities.available||!draft.trim()||running||sending}>{sending?'Отправка…':running?'Ожидаем ответ…':'Отправить'}</Button></div>
    </form>
    {(error||query.status==='error')&&<div role="alert"><Callout tone="danger">{error||(query.status==='error'?query.error:'')}</Callout><Button size="sm" variant="ghost" onClick={()=>setRefresh(n=>n+1)}>Обновить диалог</Button></div>}
    <div ref={bottom}/>
  </section>;
}

function Workspace(){
  const [params,setParams]=useSearchParams(),[refresh,setRefresh]=useState(0),[listOffset,setListOffset]=useState(0),[creating,setCreating]=useState(false),[error,setError]=useState('');
  const [drafts,setDrafts]=useState<Record<string,string>>({});
  const caps=useApiQuery(api.capabilities,[],undefined,'assistant:capabilities');
  const list=useApiQuery(()=>api.list(listOffset),[refresh,listOffset],undefined,`assistant:list:${listOffset}`);
  const identity=params.get('chat')??'';
  const agent:AgentId=['planner','photo'].includes(params.get('agent')??'')?params.get('agent') as AgentId:'assistant';
  const select=(id:string,a:AgentId)=>{const next=new URLSearchParams(params);next.set('chat',id);next.set('agent',a);setParams(next);};
  const create=async(a=agent)=>{setCreating(true);setError('');try{const chat=await api.create(a);select(chat.conversation_id,a);setRefresh(n=>n+1);}catch(e){setError(e instanceof Error?e.message:'Не удалось создать диалог');}finally{setCreating(false);}};
  if(caps.status==='loading')return <LoadingState label="Загрузка помощника"/>;
  if(caps.status==='error')return <ErrorState description={caps.error}/>;
  return <div className="space-y-5"><PageHeader title="ИИ-помощник" description="Поставьте задачу — проверьте предложение — подтвердите действие" actions={<Button disabled={creating} onClick={()=>void create()}>Новый диалог</Button>}/>
    {!caps.data.available&&<Callout tone="warning">ИИ пока не подключён. Нужен серверный ключ AI Tunnel; история диалогов доступна. После настройки обновите страницу.</Callout>}
    <div className="flex flex-wrap gap-2" aria-label="Специализация помощника">{caps.data.agents.map(a=><Button key={a.id} variant={agent===a.id?'primary':'secondary'} size="sm" onClick={()=>{const next=new URLSearchParams(params);next.set('agent',a.id);next.delete('chat');setParams(next);}}>{a.title}</Button>)}</div>
    <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[230px_minmax(0,1fr)]">
      <aside className="min-w-0 space-y-3 rounded-2xl border border-line p-3" aria-label="История диалогов"><h2 className="text-sm font-semibold">Ваши диалоги</h2>{list.status==='loading'?<p className="text-xs text-muted">Загрузка…</p>:list.status==='error'?<ErrorState description={list.error}/>:<><div className="flex max-h-44 gap-1 overflow-auto lg:max-h-[65vh] lg:flex-col">{list.data.items.map(chat=><button key={chat.conversation_id} type="button" aria-current={identity===chat.conversation_id?'true':undefined} className={`min-w-[150px] rounded-lg px-3 py-2 text-left text-sm lg:min-w-0 ${identity===chat.conversation_id?'bg-accent/10 text-accent':'hover:bg-white/5'}`} onClick={()=>select(chat.conversation_id,chat.agent)}><span className="line-clamp-2 break-words">{chat.title}</span><span className="mt-1 block text-xs text-muted">{caps.data.agents.find(a=>a.id===chat.agent)?.title}</span></button>)}</div>{list.data.total===0&&<p className="text-xs text-muted">Создайте первый диалог и опишите задачу.</p>}{list.data.total>25&&<div className="flex gap-2"><Button size="sm" variant="ghost" disabled={listOffset===0} onClick={()=>setListOffset(n=>Math.max(0,n-25))}>Назад</Button><Button size="sm" variant="ghost" disabled={listOffset+25>=list.data.total} onClick={()=>setListOffset(n=>n+25)}>Далее</Button></div>}</>}</aside>
      <main className="min-w-0 rounded-2xl border border-line bg-surface/50 p-4 sm:p-6">{identity?<Chat key={identity} identity={identity} capabilities={caps.data} draft={drafts[identity]??''} setDraft={text=>setDrafts(v=>({...v,[identity]:text}))} onRefreshList={()=>setRefresh(n=>n+1)}/>:<div className="space-y-5 py-8"><h2 className="text-2xl font-semibold">{caps.data.agents.find(a=>a.id===agent)?.title}</h2><p className="text-muted">{caps.data.agents.find(a=>a.id===agent)?.description}. Каждый диалог сохраняется отдельно для вас и текущего объекта.</p><Button disabled={creating} onClick={()=>void create()}>Начать диалог</Button><details className="text-sm"><summary className="cursor-pointer text-muted">Доступные действия · {caps.data.tools[agent]?.length??0}</summary><ul className="mt-3 grid gap-2 sm:grid-cols-2">{caps.data.tools[agent]?.map(tool=><li key={tool.name}>{tool.title}{tool.requires_confirmation&&<span className="text-muted"> · с подтверждением</span>}</li>)}</ul></details></div>}</main>
    </div>{error&&<div role="alert"><Callout tone="danger">{error}</Callout></div>}
  </div>;
}
export function AssistantPage(){const {profile}=useSession();return <Workspace key={`${profile?.userId}:${profile?.siteId}:${profile?.role}`}/>;}
