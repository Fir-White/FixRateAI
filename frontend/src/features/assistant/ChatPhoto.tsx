import {useState} from 'react';
import {Modal} from '@/shared/ui/Modal';

export const isChatPhoto=(mime:string)=>/^image\/(jpeg|png|webp)(?:;|$)/.test(mime);
export const attachmentUrl=(id:string)=>`/api/v1/assistant/attachments/${encodeURIComponent(id)}`;

export function ChatPhoto({url,title,compact=false}:{url:string;title:string;compact?:boolean}) {
  const [open,setOpen]=useState(false),[broken,setBroken]=useState(false);
  return <>
    <button className={`assistant-photo${compact?' assistant-photo--compact':''}`} type="button"
      aria-label={`Открыть фото: ${title}`} aria-haspopup="dialog" onClick={()=>setOpen(true)}>
      <img src={url} alt="" loading="lazy" decoding="async"/>
      <span title={title}>{title}</span>
    </button>
    {open&&<Modal open title={title} onClose={()=>{setOpen(false);setBroken(false);}} size="wide" instant className="assistant-photo-dialog"
      footer={!broken&&<a className="assistant-resource" href={url} download={title}>Скачать фото</a>}>
      {broken?<p role="status">Снимок недоступен или не удалось его загрузить.</p>:
        <img className="assistant-photo-full" src={url} alt={title} onError={()=>setBroken(true)}/>}
    </Modal>}
  </>;
}
