import { useEffect, useRef, useState, type InputHTMLAttributes, type ChangeEvent } from "react";
import { Icon } from "./Icon";
import "./file-input.css";

function accepts(file: File, accept: string) {
  if (!accept) return true;
  const inferred = /\.jpe?g$/i.test(file.name) ? "image/jpeg" : /\.png$/i.test(file.name) ? "image/png" : /\.webp$/i.test(file.name) ? "image/webp" : "";
  const mime = file.type || inferred;
  return accept.split(",").some(part => {
    const type = part.trim().toLowerCase();
    return type.startsWith(".") ? file.name.toLowerCase().endsWith(type) : type.endsWith("/*") ? mime.startsWith(type.slice(0,-1)) : mime === type;
  });
}

export function FileInput({ className = "", onChange, disabled, multiple, accept = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  const input = useRef<HTMLInputElement>(null);
  const [files,setFiles] = useState<File[]>([]);
  const [dragging,setDragging] = useState(false);
  const [error,setError] = useState("");
  const [preview,setPreview] = useState("");
  const depth = useRef(0);
  const images = accept.includes("image/");
  useEffect(()=>{
    const file=files[0];
    if(!file || !(file.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(file.name))){setPreview("");return;}
    const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url);
  },[files]);
  const change = (event: ChangeEvent<HTMLInputElement>) => {
    const selected=Array.from(event.target.files??[]);
    const invalid=selected.find(file=>!accepts(file,accept));
    if(invalid){event.target.value="";setFiles([]);setError(`Файл ${invalid.name} не подходит. Выберите ${images?"изображение JPEG, PNG или WebP":"файл разрешённого формата"}.`);}
    else {setFiles(selected);setError("");}
    onChange?.(event);
  };
  return <div className={`fr-file-field ${className}`}>
    <div className={`fr-file-target ${dragging?"is-dragging":""}`} data-disabled={disabled||undefined}
      onDragEnter={event=>{event.preventDefault();if(!input.current?.matches(":disabled")&&++depth.current===1)setDragging(true);}}
      onDragOver={event=>{event.preventDefault();event.dataTransfer.dropEffect=input.current?.matches(":disabled")?"none":"copy";}}
      onDragLeave={event=>{event.preventDefault();if(--depth.current<=0){depth.current=0;setDragging(false);}}}
      onDrop={event=>{event.preventDefault();event.stopPropagation();depth.current=0;setDragging(false);const field=input.current;if(!field||field.matches(":disabled"))return;const transfer=new DataTransfer();const dropped=Array.from(event.dataTransfer.files);for(const file of multiple?dropped:dropped.slice(0,1))transfer.items.add(file);field.files=transfer.files;field.dispatchEvent(new Event("change",{bubbles:true}));}}>
      <Icon name={images?"camera":"upload"} size={24}/>
      <strong>{files.length?"Выбрать другой файл":images?"Прикрепить фото":"Прикрепить файл"}</strong>
      <span className="fr-file-desktop">Перетащите сюда или нажмите для выбора</span>
      <span className="fr-file-touch">Нажмите, чтобы выбрать файл</span>
      {images&&<small>JPEG, PNG или WebP</small>}
      <input {...props} ref={input} type="file" accept={accept} multiple={multiple} disabled={disabled} className="fr-file-native" aria-label={props["aria-label"]??"Выберите файл"} onChange={change}/>
    </div>
    {files.length>0&&<div className="fr-file-selection">{preview&&<img src={preview} alt="Выбранное изображение"/>}<div>{files.map((file,index)=><p key={index}><strong>{file.name}</strong><span>{file.size<1048576?`${Math.max(1,Math.round(file.size/1024))} КБ`:`${(file.size/1048576).toFixed(1)} МБ`}</span></p>)}</div><button type="button" disabled={disabled} aria-label="Убрать выбранный файл" onClick={()=>{const field=input.current;if(field){field.value="";field.dispatchEvent(new Event("change",{bubbles:true}));}}}><Icon name="close" size={17}/></button></div>}
    {error&&<p className="fr-file-error" role="alert">{error}</p>}
  </div>;
}
