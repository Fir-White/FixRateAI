import {useEffect,useId,useLayoutEffect,useRef,useState,type CSSProperties} from 'react';
import {createPortal} from 'react-dom';
import {assistantApi as api,type ChatModelCatalog,type ChatModelChoice,type ChatModelPreference} from '@/shared/api/assistant';
import {ApiError} from '@/shared/api/request';
import {useApiQuery} from '@/shared/lib/useApiQuery';
import {useDialogFocus} from '@/shared/lib/useDialogFocus';
import {Icon} from '@/shared/ui/Icon';

type Props={preference?:ChatModelPreference;disabled:boolean;onChange:(value:ChatModelPreference)=>void;onBusy:(value:boolean)=>void};
type Results={status:'loading'}|{status:'ready';data:ChatModelCatalog}|{status:'error';error:string};

export function ChatModelPicker({preference,disabled,onChange,onBusy}:Props){
  const [open,setOpen]=useState(false),[q,setQ]=useState(''),[offset,setOffset]=useState(0),[refresh,setRefresh]=useState(0),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const [position,setPosition]=useState<CSSProperties>({left:12,top:0,width:380,maxHeight:480});
  const id=useId(),trigger=useRef<HTMLButtonElement>(null);
  const selected=preference?.selection;
  const close=()=>{if(!saving)setOpen(false);};
  useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
  useLayoutEffect(() => {
    const button = trigger.current;
    if (!open || !button) return;
    const viewport = window.visualViewport;
    const placeMenu = () => {
      const bounds = button.getBoundingClientRect();
      const viewportTop = viewport?.offsetTop ?? 0;
      const viewportBottom = viewportTop + (viewport?.height ?? window.innerHeight);
      const below = viewportBottom - bounds.bottom - 20;
      const above = bounds.top - viewportTop - 20;
      const opensBelow = below >= 320 || below >= above;
      const width = Math.min(380, window.innerWidth - 24);
      setPosition({
        left: Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12)),
        ...(opensBelow ? { top: bounds.bottom + 8 } : { bottom: window.innerHeight - bounds.top + 8 }),
        width,
        maxHeight: Math.min(480, Math.max(0, opensBelow ? below : above)),
      });
    };
    placeMenu();
    window.addEventListener('resize', placeMenu);
    window.addEventListener('scroll', placeMenu, { passive: true });
    viewport?.addEventListener('resize', placeMenu);
    viewport?.addEventListener('scroll', placeMenu);
    return () => {
      window.removeEventListener('resize', placeMenu);
      window.removeEventListener('scroll', placeMenu);
      viewport?.removeEventListener('resize', placeMenu);
      viewport?.removeEventListener('scroll', placeMenu);
    };
  }, [open]);
  const focus=useDialogFocus<HTMLDivElement>(open,close);
  const name=selected?.model??'Выбрать модель';
  function toggle(){
    if(open){close();return;}
    setOpen(true);setError('');
  }
  async function choose(choice:ChatModelChoice){
    if(!preference||saving)return;
    setSaving(true);onBusy(true);setError('');
    try{const value=await api.selectModel(choice,preference.revision);onChange(value);setOpen(false);trigger.current?.focus();}
    catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить выбор модели');if(e instanceof ApiError&&e.status===409)try{onChange(await api.modelPreference());}catch{/* Keep the previous selection visible. */}}
    finally{setSaving(false);onBusy(false);}
  }
  return <div className="assistant-model-picker">
    <button type="button" ref={trigger} className="assistant-model-trigger" aria-label={selected?`Выбрать модель: ${name}`:"Выбрать модель"} aria-haspopup="dialog" aria-expanded={open} aria-controls={id} disabled={disabled||saving} onClick={toggle} title={selected?`${selected.provider==='ollama'?'Локальная':'AI Tunnel'} · ${name}`:'Выбрать модель чата'}>
      <svg className="assistant-model-chip" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="4"/><path d="M9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/></svg>
      <span className="assistant-model-name">{saving?'Сохраняю…':name}</span>
      <Icon name="chevron" size={14} className="assistant-model-chevron"/>
    </button>
    {open&&createPortal(<><div className="assistant-model-backdrop" onMouseDown={close}/><div className="assistant-model-menu" style={position} ref={focus} id={id} role="dialog" aria-modal="true" aria-labelledby={`${id}-title`}>
      <div className="assistant-model-heading"><strong id={`${id}-title`}>Используемая модель</strong><button type="button" aria-label="Закрыть выбор модели" onClick={close} disabled={saving}>×</button></div>
      <input type="search" value={q} onChange={e=>{setQ(e.target.value);setOffset(0);}} placeholder="Найти модель…" aria-label="Поиск модели"/>
      {error&&<p className="assistant-model-error" role="alert">{error}</p>}
      <Catalog key={refresh} refresh={refresh>0} q={q} offset={offset} selected={selected} disabled={saving||!preference} onChoose={choose} onPage={setOffset}/>
      <footer><span>Выбор сохраняется для вашего аккаунта</span><button type="button" onClick={()=>{setRefresh(n=>n+1);setOffset(0);}} disabled={saving}>Обновить список</button></footer>
    </div></>,document.querySelector('.workspace-root')??document.body)}
  </div>;
}

function Catalog({refresh,q,offset,selected,disabled,onChoose,onPage}:{refresh:boolean;q:string;offset:number;selected:ChatModelChoice|null|undefined;disabled:boolean;onChoose:(choice:ChatModelChoice)=>void;onPage:(offset:number)=>void}){
  const query=useApiQuery(()=>api.models(refresh),[],undefined,refresh?undefined:'assistant:chat-model-catalog');
  const result:Results=query.status==='success'?{status:'ready',data:query.data}:query.status==='error'?{status:'error',error:query.error}:{status:'loading'};
  if(result.status==='loading')return <p className="assistant-model-status" role="status">Загружаю доступные модели…</p>;
  if(result.status==='error')return <p className="assistant-model-error" role="alert">{result.error}</p>;
  const filtered=result.data.providers.map(p=>({...p,models:p.models.filter(m=>m.name.toLocaleLowerCase().includes(q.toLocaleLowerCase()))}));
  const all=filtered.flatMap(p=>p.models.map(model=>({provider:p.id,model}))),visiblePage=all.slice(offset,offset+30),total=all.length;
  return <div className="assistant-model-results">
    {filtered.map(provider=>{
      const visible=visiblePage.filter(row=>row.provider===provider.id).map(row=>row.model);
      if(provider.status==='ready'&&provider.models.length&&!visible.length)return null;
      return <section key={provider.id}><h3>{provider.name}<span>{provider.models.length}</span></h3>
        {provider.status!=='ready'?<p className="assistant-model-status">{provider.status==='not_configured'?'Серверный ключ AI Tunnel не настроен.':'Не удалось получить список. Попробуйте обновить его.'}</p>:!provider.models.length?<p className="assistant-model-status">{q?'Совпадений нет.':provider.id==='ollama'?'Установленных моделей нет.':'Доступных моделей нет.'}</p>:visible.map(model=>{
          const current=selected?.provider===provider.id&&selected.model===model.id;
          return <button type="button" key={model.id} className="assistant-model-option" aria-pressed={current} disabled={disabled||!model.selectable} title={model.description} onClick={()=>onChoose({provider:provider.id,model:model.id})}><span><strong>{model.name}</strong><small>{provider.id==='ollama'?'На этом компьютере':'AI Tunnel'}</small></span>{current&&<span aria-label="Выбрана">✓</span>}</button>;
        })}
      </section>;
    })}
    {total>30&&<div className="assistant-model-pages"><button type="button" disabled={!offset} onClick={()=>onPage(Math.max(0,offset-30))}>Назад</button><span>{offset+1}–{Math.min(offset+30,total)} из {total}</span><button type="button" disabled={offset+30>=total} onClick={()=>onPage(offset+30)}>Далее</button></div>}
  </div>;
}
