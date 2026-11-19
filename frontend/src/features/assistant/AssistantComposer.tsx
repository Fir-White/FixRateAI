import { useLayoutEffect, useRef, useState } from 'react';
import type { ChatModelPreference, ChatView } from '@/shared/api/assistant';
import { Icon } from '@/shared/ui/Icon';
import { ChatModelPicker } from './ChatModelPicker';
import './assistant.css';

export type ModelControls={modelPreference?:ChatModelPreference;onModelChange:(value:ChatModelPreference)=>void};
export function AssistantComposer({draft,setDraft,onSend,onUpload,onRemove,onStop,busy,uploading,running,available,attachments,compact=false,showMark=false,entryRect,modelPreference,onModelChange}:{draft:string;setDraft:(s:string)=>void;onSend:()=>void;onUpload:(file:File)=>void;onRemove?:(id:string)=>void;onStop?:()=>void;busy:boolean;uploading:boolean;running:boolean;available:boolean;attachments?:ChatView['attachments'];compact?:boolean;showMark?:boolean;entryRect?:DOMRectReadOnly}&ModelControls){
  const input=useRef<HTMLTextAreaElement>(null);
  const form=useRef<HTMLFormElement>(null);
  useLayoutEffect(() => {
    const element = form.current;
    if (!entryRect || !element?.animate || window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) return;
    const destination = element.getBoundingClientRect();
    const dx = entryRect.left - destination.left;
    const dy = entryRect.top - destination.top;
    const scale = destination.width > 0 ? entryRect.width / destination.width : 1;
    const animation = element.animate([
      { transform: `translate(${dx}px, ${dy}px) scaleX(${scale})`, opacity: .78 },
      { transform: 'none', opacity: 1 },
    ], { duration: 300, easing: 'cubic-bezier(.22,.61,.36,1)' });
    return () => animation.cancel();
  }, [entryRect]);
  const [modelSaving,setModelSaving]=useState(false);
  const canSend=(modelPreference?.available??available)&&!modelSaving&&!busy&&!running&&!uploading&&(!!draft.trim()||!!attachments?.length);
  useLayoutEffect(()=>{const el=input.current;if(el){el.style.height='auto';el.style.height=`${Math.min(Math.max(el.scrollHeight,compact?32:64),180)}px`;}},[draft,compact]);
  return <div className="assistant-composer-wrap">
    <form ref={form} className="assistant-composer" onSubmit={e=>{e.preventDefault();if(canSend)onSend();}} aria-label="Написать помощнику">
      {showMark && <div className="assistant-composer-mark"><Icon name="assistant" size={20}/>FixRate AI</div>}
      {(attachments?.length??0)>0&&<ul aria-label="Вложения к сообщению" className="assistant-attachments">{attachments?.map(file=><li key={file.attachment_id}><a href={`/api/v1/assistant/attachments/${encodeURIComponent(file.attachment_id)}`} target="_blank" rel="noreferrer">{file.original_name}</a><span>{Math.ceil(file.size_bytes/1024)} КБ</span>{onRemove&&<button type="button" aria-label={`Убрать файл ${file.original_name}`} disabled={busy} onClick={()=>onRemove(file.attachment_id)}><Icon name="close" size={14}/></button>}</li>)}</ul>}
      <label className="sr-only" htmlFor="assistant-message">Сообщение помощнику</label><textarea ref={input} id="assistant-message" value={draft} maxLength={12000} rows={compact?1:2} placeholder={compact?"Сообщение помощнику":"Что нужно сделать сегодня?"} disabled={busy} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(canSend)onSend();}}}/>
      <div className="assistant-composer-actions"><label className={`assistant-attach ${busy||uploading||running||modelSaving?'is-disabled':''}`} title="XLSX, JPEG, PNG, WebP до 10 МиБ"><Icon name="plus" size={20}/><span>{uploading?'Загрузка…':'Файл или фото'}</span><input className="sr-only" type="file" accept=".xlsx,.png,.jpg,.jpeg,.webp" aria-label="Прикрепить файл" disabled={busy||uploading||running||modelSaving} onChange={e=>{const file=e.target.files?.[0];if(file)onUpload(file);e.currentTarget.value='';}}/></label><ChatModelPicker preference={modelPreference} disabled={busy||uploading||running} onChange={onModelChange} onBusy={setModelSaving}/>{running?<button className="assistant-send" type="button" aria-label="Остановить ответ" title="Остановить ответ" disabled={busy} onClick={onStop}><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg></button>:<button className="assistant-send" type="submit" aria-label="Отправить" disabled={!canSend} title="Отправить сообщение"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button>}</div>
    </form><p className="assistant-disclaimer">Изменения — только после вашего подтверждения. Проверяйте ответы ИИ.</p>
  </div>;
}
