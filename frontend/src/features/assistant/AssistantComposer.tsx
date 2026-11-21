import { useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState, type Ref } from 'react';
import type { ChatModelPreference, ChatView } from '@/shared/api/assistant';
import { Icon } from '@/shared/ui/Icon';
import { ChatModelPicker } from './ChatModelPicker';
import './assistant.css';

export type ModelControls={modelPreference?:ChatModelPreference;onModelChange:(value:ChatModelPreference)=>void};
export type ComposerHandle = { replaceDraft: (text: string) => void; focus: () => void };

export function AssistantComposer({ref,initialDraft='',onDraftChange,onSend,onUpload,onRemove,onStop,busy,uploading,running,available,attachments,compact=false,showMark=false,entryRect,onEntryComplete,modelPreference,onModelChange}:{ref?:Ref<ComposerHandle>;initialDraft?:string;onDraftChange?:(text:string)=>void;onSend:(text:string)=>void;onUpload:(file:File,text:string)=>void;onRemove?:(id:string)=>void;onStop?:()=>void;busy:boolean;uploading:boolean;running:boolean;available:boolean;attachments?:ChatView['attachments'];compact?:boolean;showMark?:boolean;entryRect?:DOMRectReadOnly;onEntryComplete?:()=>void}&ModelControls){
  const input=useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const form=useRef<HTMLFormElement>(null);
  useEffect(() => {
    const picker = fileInput.current;
    const returnToDraft = () => input.current?.focus({ preventScroll: true });
    picker?.addEventListener('cancel', returnToDraft);
    return () => picker?.removeEventListener('cancel', returnToDraft);
  }, []);
  const startingText = useRef(initialDraft);
  const [hasText, setHasText] = useState(() => /\S/.test(initialDraft));
  const resizeFrame = useRef<number | null>(null);
  const resizeFallback = useCallback(() => {
    if (window.CSS?.supports?.('field-sizing', 'content') || resizeFrame.current !== null) return;
    resizeFrame.current = requestAnimationFrame(() => {
      resizeFrame.current = null;
      const element = input.current;
      if (!element) return;
      element.style.height = 'auto';
      element.style.height = `${Math.min(Math.max(element.scrollHeight, compact ? 32 : 64), 180)}px`;
    });
  }, [compact]);
  useLayoutEffect(() => {
    resizeFallback();
    return () => {
      if (resizeFrame.current !== null) cancelAnimationFrame(resizeFrame.current);
      resizeFrame.current = null;
    };
  }, [resizeFallback]);
  const draftChanged = (text: string) => {
    setHasText(/\S/.test(text));
    onDraftChange?.(text);
    resizeFallback();
  };
  useImperativeHandle(ref, () => ({
    replaceDraft(text) {
      if (!input.current) return;
      input.current.value = text;
      draftChanged(text);
    },
    focus: () => input.current?.focus(),
  }));
  useLayoutEffect(() => {
    const element = form.current;
    if (!entryRect) return;
    if (!element?.animate || window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) {
      onEntryComplete?.();
      return;
    }
    const destination = element.getBoundingClientRect();
    const dx = entryRect.left - destination.left;
    const dy = entryRect.top - destination.top;
    const scale = destination.width > 0 ? entryRect.width / destination.width : 1;
    const animation = element.animate([
      { transform: `translate(${dx}px, ${dy}px) scaleX(${scale})`, opacity: .78 },
      { transform: 'none', opacity: 1 },
    ], { duration: 300, easing: 'cubic-bezier(.22,.61,.36,1)' });
    if (onEntryComplete) void animation.finished.then(onEntryComplete, () => {});
    return () => animation.cancel();
  }, [entryRect, onEntryComplete]);
  const [modelSaving,setModelSaving]=useState(false);
  const canSend=(modelPreference?.available??available)&&!modelSaving&&!busy&&!running&&!uploading&&(hasText||!!attachments?.length);
  const submit = () => { if (canSend && input.current) onSend(input.current.value); };
  return <div className="assistant-composer-wrap">
    <form ref={form} className="assistant-composer" onSubmit={e=>{e.preventDefault();submit();}} aria-label="Написать помощнику">
      {showMark && <div className="assistant-composer-mark"><Icon name="assistant" size={20}/>FixRate AI</div>}
      {(attachments?.length??0)>0&&<ul aria-label="Вложения к сообщению" className="assistant-attachments">{attachments?.map(file=><li key={file.attachment_id}><a href={`/api/v1/assistant/attachments/${encodeURIComponent(file.attachment_id)}`} target="_blank" rel="noreferrer">{file.original_name}</a><span>{Math.ceil(file.size_bytes/1024)} КБ</span>{onRemove&&<button type="button" aria-label={`Убрать файл ${file.original_name}`} disabled={busy} onClick={()=>onRemove(file.attachment_id)}><Icon name="close" size={14}/></button>}</li>)}</ul>}
      <label className="sr-only" htmlFor="assistant-message">Сообщение помощнику</label><textarea ref={input} id="assistant-message" defaultValue={startingText.current} maxLength={12000} rows={compact?1:2} placeholder={compact?"Сообщение помощнику":"Что нужно сделать сегодня?"} disabled={busy} onChange={e=>draftChanged(e.currentTarget.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();submit();}}}/>
      <div className="assistant-composer-actions"><label className={`assistant-attach ${busy||uploading||running||modelSaving?'is-disabled':''}`} title="XLSX, JPEG, PNG, WebP до 10 МиБ"><Icon name="plus" size={20}/><span>{uploading?'Загрузка…':'Файл или фото'}</span><input ref={fileInput} className="sr-only" type="file" accept=".xlsx,.png,.jpg,.jpeg,.webp" aria-label="Прикрепить файл" disabled={busy||uploading||running||modelSaving} onChange={e=>{const file=e.target.files?.[0];if(file)onUpload(file,input.current?.value??'');e.currentTarget.value='';}}/></label><ChatModelPicker preference={modelPreference} disabled={busy||uploading||running} onChange={onModelChange} onBusy={setModelSaving}/>{running?<button className="assistant-send" type="button" aria-label="Остановить ответ" title="Остановить ответ" disabled={busy} onClick={onStop}><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg></button>:<button className="assistant-send" type="submit" aria-label="Отправить" disabled={!canSend} title="Отправить сообщение"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button>}</div>
    </form><p className="assistant-disclaimer">Изменения — только после вашего подтверждения. Проверяйте ответы ИИ.</p>
  </div>;
}
