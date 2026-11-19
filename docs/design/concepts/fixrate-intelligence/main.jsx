import React,{useState,useRef,useEffect,useLayoutEffect} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import './refinements.css';

const q=new URLSearchParams(location.search),storeKey='fixrate-intelligence-demo-v1';
const roleName={chief:'Главный инженер',executor:'Исполнитель'};
const menus={chief:[['Обзор','home'],['График ТО','planning'],['Задания','tasks'],['Оборудование','equipment'],['Команда','team'],['Отчёты','reports']],executor:[['Мой день','home'],['Задания','task'],['Инструкции','instructions'],['Мои отчёты','report']]};
const prompts={chief:['Составить план ТО','Проверить загрузку','Найти оборудование','Подготовить отчёт'],executor:['Инструкция','Проверить отчёт','Загрузить фото','Статус работы']};
const requests={chief:'Составь план обслуживания на следующую неделю',executor:'Проверь мой отчёт перед отправкой'};
const paths={assistant:<><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H5l-3 2V11.5a8.5 8.5 0 1 1 19 0Z"/><path d="m12 6 1.2 3.3L16.5 11l-3.3 1.4L12 16l-1.3-3.6L7.5 11l3.2-1.7L12 6Z"/></>,plus:<path d="M12 5v14M5 12h14"/>,arrow:<path d="m7 12 5-5 5 5M12 7v12"/>,menu:<path d="M4 6h16M4 12h16M4 18h16"/>,clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01"/></>,tasks:<><path d="M9 6h11M9 12h11M9 18h11"/><path d="m3.5 6 1.5 1.5L7.5 5M3.5 12l1.5 1.5L7.5 11"/></>};
function Icon({name,size=20}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.tasks}</svg>}
function Pill({children,tone=''}){return <span className={'pill '+tone}>{children}</span>}
function Button({children,primary=false,...props}){return <button className={primary?'button primary':'button'} {...props}>{children}</button>}
function readSaved(){try{const a=JSON.parse(localStorage.getItem(storeKey)||'[]');return Array.isArray(a)?a:[]}catch{return []}}
function seed(role){return {id:crypto.randomUUID(),role,title:requests[role],draft:'',status:'ready',messages:[{id:crypto.randomUUID(),type:'user',text:requests[role],files:[]},{id:crypto.randomUUID(),type:'assistant',kind:role==='chief'?'plan':'report'}]}}

function Composer({boxRef,inputRef,text,setText,files,setFiles,send,pending,role,mode,attachRef}){
 return <form className="composer" ref={boxRef} onSubmit={e=>{e.preventDefault();send()}} aria-label="Сообщение FixRate Intelligence">
  <div className="composer-brand"><Icon name="assistant"/><span>FixRate Intelligence</span></div>
  <label className="sr" htmlFor="message">Сообщение AI-помощнику</label>
  <textarea id="message" ref={inputRef} value={text} onChange={e=>setText(e.target.value)} placeholder={mode==='chat'?'Уточните задачу или прикрепите файл':role==='chief'?'Какую инженерную задачу разберём?':'Нужна помощь с заданием?'} rows="2" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send()}}}/>
  {files.length>0&&<div className="attachments">{files.map((f,i)=><span className="attachment" key={i}>{f.name}<button type="button" onClick={()=>setFiles(files.filter((_,k)=>k!==i))} aria-label={'Убрать '+f.name}>×</button></span>)}</div>}
  <div className="composer-tools"><button className="file-pick" type="button" onClick={()=>attachRef.current.click()}><Icon name="plus" size={22}/><span>Файл или фото</span></button><span className="context-note">{files.length?'Локальный выбор · загрузки нет':'Контекст: текущий объект и ваша роль'}</span><button type="submit" className="send" disabled={pending||(!text.trim()&&!files.length)} aria-label="Отправить сообщение"><Icon name="arrow" size={22}/></button></div>
  <input type="file" ref={attachRef} hidden multiple accept="image/*,.pdf,.xlsx,.xls,.csv,.txt,.docx" onChange={e=>{setFiles([...files,...e.target.files].slice(0,10));e.target.value=''}}/>
 </form>
}

function Home({role,gui,fill,attach}){
 return <div className={'home-content '+(role==='executor'?'executor-home':'')}>
  <div className="site-context"><strong>ЖК «Сосновый парк» <span aria-hidden="true">⌄</span></strong><Pill>{roleName[role]}</Pill><span className="date">Вторник, 17 ноября 2026</span></div>
  <h1>{role==='chief'?<><span className="desktop-copy">Рабочий день под контролем.</span><span className="mobile-copy">Ваш рабочий день.</span></>:<>Сначала — текущее задание.</>}</h1>
  {role==='chief'&&<p className="mobile-lead">Планы и решения — в одном контексте.</p>}
  <div className="composer-space"/>
  <div className="quick-actions"><span>Поручить AI</span>{prompts[role].map(p=><button key={p} onClick={()=>p==='Загрузить фото'?attach():fill(p)}>{p} <span aria-hidden="true">↗</span></button>)}</div>
  {role==='chief'?<div className="engineer-context">
   <section className="priorities"><h2>Требует решения</h2><article className="priority-card"><h3>3 работы просрочены</h3><strong>Проверка управляющего<br/>модуля</strong><p>Срок — 16 ноября · На доработке</p><button className="link" onClick={()=>gui('tasks')}>Разобрать очередь →</button><div className="mobile-priority"><strong>Требуют решения</strong><p>3 просрочены · 42 без исполнителя</p><button className="link" onClick={()=>gui('tasks')}>Разобрать очередь →</button></div></article><button className="unassigned" onClick={()=>gui('tasks')}>42 без исполнителя <span>Назначить →</span></button></section>
   <section className="schedule"><div className="section-title"><h2>Сегодня, 17 ноября</h2><button className="link" onClick={()=>gui('planning')}>6 работ · Открыть график ↗</button></div>
    {[['09:00','Контроль параметров показаний приборов','Индивидуальный тепловой пункт','Не назначен'],['10:00','Протоколирование показаний счётчиков','Алексей Морозов','Назначено'],['11:00','Проверка приборов температуры и давления','Алексей Морозов','В работе']].map(([time,title,who,status])=><button className="schedule-row" key={time} onClick={()=>gui('task')}><strong className="time">{time}</strong><span className="work"><strong>{title}</strong><span>{who}</span></span><Pill tone={status==='Не назначен'?'amber':''}>{status}</Pill></button>)}
    <div className="utility-links"><button className="link" onClick={()=>gui('quality')}>Приёмка · 0 новых отчётов ↗</button><button className="link" onClick={()=>gui('equipment')}>Оборудование и ресурс деталей ↗</button></div>
   </section>
  </div>:<div className="executor-context"><section className="current-work"><h2><span className="desktop-copy">Продолжить выполнение</span><span className="mobile-copy">Сейчас — ваше задание</span></h2><article className="current-card"><div><Pill>В работе</Pill><span className="desktop-copy">Сегодня, 11:00 · Алексей Морозов</span><span className="mobile-copy">11:00</span></div><h3><span className="desktop-copy">Проверка приборов измерения температуры и давления на повреждения и точность показаний</span><span className="mobile-copy">Проверка приборов температуры и давления</span></h3><p>Манометр контура отопления</p><div className="actions"><Button primary onClick={()=>gui('task')}>Продолжить работу →</Button><button className="link" onClick={()=>gui('task')}>Открыть мои задания ↗</button></div></article></section><section className="work-support"><h2>Инструкции и результат</h2><h3>Утверждённый регламент</h3><p>Порядок работ и примечания инженера</p><button className="link" onClick={()=>gui('instructions')}>Открыть инструкцию →</button><hr/><h3>Отчёт и фото</h3><p>Отправка на проверку — после заполнения.</p><Button onClick={attach}>Выбрать фотографии</Button></section></div>}
  <p className="fixture-note">Демонстрационный срез · Категории пересекаются · Решения и подтверждения остаются за человеком</p>
 </div>
}

function Result({kind,role,gui}){
 if(kind==='equipment')return <><p>В демонстрационном срезе есть оборудование из текущей работы.</p><article className="result-card"><Pill>Оборудование</Pill><h2>Манометр контура отопления</h2><p>Связанная работа: проверка приборов измерения температуры и давления.</p><Button primary onClick={()=>gui('equipment')}>Открыть оборудование →</Button></article></>;
 if(role==='executor')return <><p>Для проверки нужны фото и заполненный чек-лист. Выберите доступное задание.</p><article className="result-card"><Pill tone="amber">Нужны материалы</Pill><h2>Проверка отчёта перед отправкой</h2><p>Фото до / после, заполненный чек-лист, материалы и примечания.<br/>AI не подтверждает выполнение всех операций по фотографиям.</p><div className="actions"><Button primary onClick={()=>gui('task')}>Открыть моё задание →</Button><span className="result-hint">Приёмка — за главным инженером</span></div></article></>;
 return <><p>Подготовлю предложение на 23–29 ноября. Сначала проверим исходные данные.</p><article className="result-card"><Pill tone="amber">Предварительный план</Pill><h2>23–29 ноября 2026 · План обслуживания</h2><p>Электрика · Вода · Воздух. Состав работ, часы и загрузка ещё не рассчитаны.<br/>План не создан. Данные в системе не изменены.</p><div className="actions"><Button primary onClick={()=>gui('plan')}>Проверить параметры →</Button><button className="link" onClick={()=>gui('planning')}>Открыть графический редактор ↗</button></div></article></>;
}

function App(){
 const [role,setRole]=useState(q.get('role')==='executor'?'executor':'chief');
 const [threads,setThreads]=useState(()=>{const old=readSaved();if(q.get('screen')==='chat'){const t=seed(q.get('role')==='executor'?'executor':'chief');return [t,...old]}return old});
 const [active,setActive]=useState(()=>q.get('screen')==='chat'?0:null),[mode,setMode]=useState(q.get('screen')==='chat'?'chat':'home');
 const [text,setText]=useState(''),[files,setFiles]=useState([]),[pending,setPending]=useState(false),[error,setError]=useState(false),[scenario,setScenario]=useState('normal');
 const [search,setSearch]=useState(''),[menu,setMenu]=useState(false),[dialog,setDialog]=useState(null),[notice,setNotice]=useState(''),[leaving,setLeaving]=useState(false);
 const [plan,setPlan]=useState({period:'23–29 ноября 2026',systems:'Электрика, Вода, Воздух'});
 const composerRef=useRef(),inputRef=useRef(),attachRef=useRef(),startRef=useRef(),chatRef=useRef(),modal=useRef(),version=useRef(0),pendingRef=useRef(false),activeAnimations=useRef([]),reduced=useRef(false),threadRef=useRef(null);
 const thread=active===null?null:threads[active];threadRef.current=thread;
 const cancelMotion=()=>{activeAnimations.current.forEach(a=>a.cancel());activeAnimations.current=[];setLeaving(false)};
 useEffect(()=>{try{localStorage.setItem(storeKey,JSON.stringify(threads))}catch{}},[threads]);
 useEffect(()=>{const m=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>{reduced.current=m.matches;if(m.matches)cancelMotion()};update();m.addEventListener('change',update);const viewport=()=>{document.documentElement.style.setProperty('--vvh',(visualViewport?.height||innerHeight)+'px');cancelMotion()};visualViewport?.addEventListener('resize',viewport);window.addEventListener('resize',viewport);viewport();return()=>{m.removeEventListener('change',update);visualViewport?.removeEventListener('resize',viewport);window.removeEventListener('resize',viewport)}},[]);
 useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),4200);return()=>clearTimeout(t)},[notice]);
 useEffect(()=>{if(dialog&&!modal.current.open)modal.current.showModal();if(!dialog&&modal.current.open)modal.current.close()},[dialog]);
 useEffect(()=>{if(!menu)return;const previous=document.activeElement;const drawer=document.querySelector('.drawer');drawer?.querySelector('button,input')?.focus();const key=e=>{if(e.key==='Escape'){setMenu(false);return}if(e.key!=='Tab'||!drawer)return;const items=[...drawer.querySelectorAll('button,input')].filter(e=>!e.disabled);const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}};document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);if(previous?.isConnected)previous.focus()}},[menu]);
 useLayoutEffect(()=>{
  if(mode!=='chat'||!startRef.current)return;const from=startRef.current;startRef.current=null;
  if(reduced.current){setLeaving(false);return}
  const to=composerRef.current.getBoundingClientRect();const a=composerRef.current.animate([{transform:`translate(${from.x-to.x}px,${from.y-to.y}px) scale(${from.width/to.width},${from.height/to.height})`},{transform:'none'}],{duration:400,easing:'cubic-bezier(.22,1,.36,1)'});
  const b=chatRef.current.animate([{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'none'}],{duration:180,delay:140,easing:'ease-out'});activeAnimations.current=[a,b];a.finished.catch(()=>{}).then(()=>{activeAnimations.current=[];setLeaving(false)});
 },[mode]);
 function updateThread(id,fn){setThreads(ts=>ts.map(t=>t.id===id?fn(t):t))}
 function route(id,replace=false,r=role){const u=new URL(location.href);u.searchParams.set('role',r);u.searchParams.delete('screen');id?u.searchParams.set('chat',id):u.searchParams.delete('chat');history[replace?'replaceState':'pushState'](null,'',u)}
 function saveDraft(){if(thread)updateThread(thread.id,t=>({...t,draft:text}))}
 function stop(){version.current++;pendingRef.current=false;setPending(false);if(thread)updateThread(thread.id,t=>({...t,status:t.status==='pending'?'interrupted':t.status}))}
 function home(push=true){saveDraft();stop();cancelMotion();setMode('home');setActive(null);setText('');setFiles([]);setError(false);setMenu(false);if(push)route(null)}
 function openThread(id,push=true){saveDraft();stop();cancelMotion();const i=threads.findIndex(t=>t.id===id&&t.role===role);if(i<0)return home(push);setActive(i);setText(threads[i].draft||'');setFiles([]);setError(threads[i].status==='error'||threads[i].status==='interrupted');setMode('chat');setMenu(false);if(push)route(id)}
 useEffect(()=>{const pop=()=>{const u=new URL(location.href);const r=u.searchParams.get('role')==='executor'?'executor':'chief';const id=u.searchParams.get('chat');version.current++;pendingRef.current=false;setPending(false);cancelMotion();setRole(r);const i=threads.findIndex(t=>t.id===id&&t.role===r);if(i<0){setMode('home');setActive(null);setText('')}else{setActive(i);setMode('chat');setText(threads[i].draft||'');setError(threads[i].status==='error')}};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[threads]);
 useEffect(()=>{const id=q.get('chat');if(id){const i=threads.findIndex(t=>t.id===id&&t.role===role);if(i>=0){setActive(i);setMode('chat');setText(threads[i].draft||'');setError(threads[i].status==='error')}}},[]);
 function changeRole(r){saveDraft();stop();cancelMotion();setRole(r);setMode('home');setActive(null);setText('');setFiles([]);setError(false);setMenu(false);setDialog(null);route(null,false,r)}
 async function answer(id,message,token){
  await new Promise(r=>setTimeout(r,scenario==='slow'?3500:500));if(version.current!==token)return;
  pendingRef.current=false;setPending(false);
  if(scenario==='error'){updateThread(id,t=>({...t,status:'error'}));setError(true);return}
  updateThread(id,t=>({...t,status:'ready',messages:[...t.messages,{id:crypto.randomUUID(),type:'assistant',kind:/оборудован|манометр/i.test(message)?'equipment':role==='executor'?'report':'plan'}]}));
 }
 function send(){
  const message=text.trim()||(files.length?'Проверь выбранные вложения':'');if(!message||pendingRef.current)return;
  pendingRef.current=true;setPending(true);setError(false);const token=++version.current;
  const m={id:crypto.randomUUID(),type:'user',text:message,files:files.map(f=>f.name)};let id;
  if(mode==='home'){
   startRef.current=composerRef.current.getBoundingClientRect();setLeaving(true);const t={id:crypto.randomUUID(),role,title:message,draft:'',status:'pending',messages:[m]};id=t.id;setThreads(ts=>[t,...ts]);setActive(0);setMode('chat');
  }else{id=thread.id;updateThread(id,t=>({...t,draft:'',status:'pending',messages:[...t.messages,m]}))}
  setText('');setFiles([]);route(id);answer(id,message,token);
 }
 function retry(){if(pendingRef.current||!thread)return;pendingRef.current=true;setPending(true);setError(false);const token=++version.current;updateThread(thread.id,t=>({...t,status:'pending'}));answer(thread.id,thread.messages.filter(m=>m.type==='user').at(-1)?.text||'',token)}
 function fill(value){setText(value);inputRef.current?.focus()}
 function gui(kind){setMenu(false);setDialog({kind})}
 function onText(value){setText(value);if(thread)updateThread(thread.id,t=>({...t,draft:value}))}
 const isChat=mode==='chat';
 return <>
  <a className="skip" href="#workspace">Перейти к содержимому</a>
  <header className="topbar" inert={menu?true:undefined}><button className="brand" onClick={()=>home()}>FixRate AI</button><nav aria-label="Основная навигация">{menus[role].map(([n,k],i)=><button key={k} className={i===0?'active':''} onClick={()=>k==='home'?home():gui(k)}>{n}</button>)}</nav><button className="profile" onClick={()=>gui('demo')}>Личный кабинет ↗</button><button className="mobile-menu" onClick={()=>setMenu(true)} aria-label="Открыть меню"><Icon name="menu" size={24}/></button></header>
  <div className={'workspace '+(isChat?'chat':'home')+(leaving?' leaving':'')+' '+role} data-mode={mode} inert={menu?true:undefined}>
   <main id="workspace">
    <div className="home-wrap" aria-hidden={isChat} inert={isChat?true:undefined}><Home role={role} gui={gui} fill={fill} attach={()=>attachRef.current.click()}/></div>
    {isChat&&<aside className={'history '+(menu?'open':'')} aria-label="История диалогов"><h2>Диалоги</h2><Button onClick={()=>home()}>+ Новый диалог</Button><label className="sr" htmlFor="search-dialogues">Поиск по беседам</label><input id="search-dialogues" type="search" placeholder="Поиск по беседам" value={search} onChange={e=>setSearch(e.target.value)}/><span className="history-day">Сегодня</span><div className="history-items">{threads.filter(t=>t.role===role&&t.title.toLowerCase().includes(search.toLowerCase())).map(t=><button className={t.id===thread?.id?'selected':''} key={t.id} onClick={()=>openThread(t.id)}>{t.title}</button>)}</div><div className="history-context"><span>Контекст диалога</span><strong>ЖК «Сосновый парк»</strong><span>{roleName[role]}</span></div></aside>}
    <section className="conversation" ref={chatRef} hidden={!isChat} aria-label="Текущий диалог"><div className="chat-heading"><h1>{thread?.title}</h1><p>Личный диалог · ЖК «Сосновый парк»</p><button className="link mobile-dialogs" onClick={()=>setMenu(true)}>‹ Диалоги · + Новый</button></div><div className="messages" role="log" aria-live="polite" aria-relevant="additions">
     {thread?.messages.map(m=>m.type==='user'?<div className="user-message" key={m.id}>{m.text}{m.files.length>0&&<small>{m.files.join(' · ')} · локальный выбор</small>}</div>:<div className="assistant-message" key={m.id}><strong className="assistant-label">FixRate Intelligence</strong><Result kind={m.kind} role={role} gui={gui}/></div>)}
     {pending&&<div className="pending" role="status"><span className="activity-dot"/> Подготовка примера ответа… {scenario==='slow'&&<span>Ответ занимает больше времени.</span>}<button className="link" onClick={stop}>Остановить</button></div>}
     {(error||thread?.status==='interrupted')&&!pending&&<div className="error" role="alert"><strong>{thread?.status==='interrupted'?'Ответ остановлен':'Не удалось получить ответ'}</strong><p>Ваш запрос сохранён. Повтор не отправляет его вторым сообщением.</p><Button onClick={retry}>Повторить ответ</Button></div>}
    </div></section>
    <Composer boxRef={composerRef} inputRef={inputRef} attachRef={attachRef} text={text} setText={onText} files={files} setFiles={setFiles} send={send} pending={pending} role={role} mode={mode}/>
    {isChat&&<p className="chat-disclaimer">Предложение AI не меняет данные. Запись — после проверки прав и вашего подтверждения.</p>}
   </main>
  </div>
  {!isChat&&<nav className="bottom-nav" aria-label="Мобильная навигация">{[['Главная','home','assistant'],['Задания',role==='chief'?'tasks':'task','tasks'],[role==='chief'?'График ТО':'Инструкция',role==='chief'?'planning':'instructions','calendar'],['Ещё','more','menu']].map(([n,k,i])=><button className={k==='home'?'active':''} key={k} onClick={()=>k==='home'?home():k==='more'?setMenu(true):gui(k)}><Icon name={i} size={20}/>{n}</button>)}</nav>}
  {menu&&<div className="drawer-backdrop" onClick={()=>setMenu(false)}><aside className="drawer" role="dialog" aria-modal="true" aria-label={isChat?'Диалоги и разделы':'Разделы'} onClick={e=>e.stopPropagation()}><div className="drawer-heading"><h2>{isChat?'Диалоги и разделы':'Разделы'}</h2><button aria-label="Закрыть меню" onClick={()=>setMenu(false)}>×</button></div>{isChat&&<><Button onClick={()=>home()}>+ Новый диалог</Button><label className="sr" htmlFor="mobile-search-dialogues">Поиск по беседам</label><input id="mobile-search-dialogues" type="search" placeholder="Поиск по беседам" value={search} onChange={e=>setSearch(e.target.value)}/>{threads.filter(t=>t.role===role&&t.title.toLowerCase().includes(search.toLowerCase())).map(t=><button className="drawer-item" key={t.id} onClick={()=>openThread(t.id)}>{t.title}</button>)}</>}{menus[role].map(([n,k])=><button className="drawer-item" key={k} onClick={()=>k==='home'?home():gui(k)}>{n}</button>)}{role==='chief'&&<button className="drawer-item" onClick={()=>gui('quality')}>Приёмка работ</button>}<button className="drawer-item" onClick={()=>gui('demo')}>Настройки демонстрации</button></aside></div>}
  <dialog ref={modal} onCancel={()=>setDialog(null)} onClose={()=>setDialog(null)}><div className="modal-top"><span>КОНЦЕПТ D · ПРЕДПРОСМОТР GUI</span><button onClick={()=>setDialog(null)} aria-label="Закрыть диалог">×</button></div>
   {dialog?.kind==='demo'?<><h2>Демонстрация концепции</h2><p>Ответы заданы сценарием. LLM, серверная загрузка файлов и запись в систему не вызываются.</p><label>Роль<select aria-label="Роль демонстрации" value={role} onChange={e=>changeRole(e.target.value)}><option value="chief">Главный инженер</option><option value="executor">Исполнитель</option></select></label><label>Режим ответа<select aria-label="Режим ответа" value={scenario} onChange={e=>setScenario(e.target.value)}><option value="normal">Обычный ответ</option><option value="slow">Медленный ответ</option><option value="error">Ошибка ответа</option></select></label><Button onClick={()=>setDialog(null)}>Продолжить</Button></>:dialog?.kind==='plan'&&role==='chief'?<><h2>Параметры плана ТО</h2><label>Период<input value={plan.period} onChange={e=>setPlan(p=>({...p,period:e.target.value}))}/></label><label>Системы<select value={plan.systems} onChange={e=>setPlan(p=>({...p,systems:e.target.value}))}><option>Электрика, Вода, Воздух</option><option>Электрика</option><option>Вода</option><option>Воздух</option></select></label><p>Для создания плана backend должен проверить нормы, сроки, доступность сотрудников и права.</p><Button primary disabled={!plan.period.trim()} onClick={()=>setDialog({kind:'confirm'})}>Проверить перед подтверждением</Button></>:dialog?.kind==='confirm'&&role==='chief'?<><h2>Подтверждение действия</h2><p><strong>Создать план ТО</strong><br/>{plan.period}<br/>{plan.systems}<br/>ЖК «Сосновый парк»</p><p>Расчёт в этом концепте не выполняется. Проверяется только шаг подтверждения.</p><div className="actions"><Button primary onClick={()=>{setDialog(null);setNotice('Подтверждение показано. Записи в backend нет.')}}>Подтвердить в демо</Button><Button onClick={()=>setDialog(null)}>Отмена</Button></div></>:dialog?.kind==='equipment'?<><h2>Манометр контура отопления</h2><p>ЖК «Сосновый парк» · Система отопления</p><p>GUI и AI работают с тем же разрешённым контекстом. Здесь показана точка перехода.</p><Button primary onClick={()=>{setDialog(null);fill('Объясни регламент для манометра контура отопления');setNotice('Контекст: манометр контура отопления')}}>Спросить AI о приборе</Button></>:dialog?.kind==='task'?<><Pill>В работе</Pill><h2>Проверка приборов измерения температуры и давления</h2><p>Манометр контура отопления · Алексей Морозов</p><p>В задании доступны инструкция, чек-лист, фото до / после, материалы и отчёт. Анализ фотографий здесь не выполняется.</p><div className="actions"><Button primary onClick={()=>{setDialog(null);fill('Помоги с отчётом по моему текущему заданию')}}>Спросить AI по заданию</Button><Button onClick={()=>{setDialog(null);attachRef.current.click()}}>Выбрать фото</Button></div></>:<><h2>{({planning:'График и планирование ТО',tasks:'Очередь заданий',quality:'Приёмка работ',instructions:'Утверждённые инструкции',team:'Команда и смены',reports:'Отчёты',report:'Мои отчёты'})[dialog?.kind]||'Рабочий раздел'}</h2><p>Точка входа в обычный графический интерфейс. Полный редизайн этого раздела в концепцию восьми экранов не входит.</p><p>Окончательное решение о приёмке всегда принимает главный инженер.</p><Button onClick={()=>setDialog(null)}>Вернуться к работе</Button></>}
  </dialog>
  {notice&&<div className="toast" role="status">{notice}</div>}
 </>
}
createRoot(document.getElementById('root')).render(<App/>);
