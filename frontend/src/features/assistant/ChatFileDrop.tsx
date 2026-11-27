import {useRef,useState,type ComponentPropsWithoutRef,type DragEvent} from 'react';

function isFileDrag(event:DragEvent<HTMLElement>) {
  return event.currentTarget.contains(event.target as Node) && event.dataTransfer.types.includes('Files');
}

export function ChatFileDrop({children,blocked,onFiles,className,...section}:ComponentPropsWithoutRef<'section'>&{
  blocked:boolean;
  onFiles:(files:File[])=>void;
}) {
  const depth=useRef(0);
  const [dragging,setDragging]=useState(false);
  return <section {...section} className={`${className} assistant-file-drop`}
    onDragEnter={event=>{
      if(!isFileDrag(event))return;
      event.preventDefault();
      if(depth.current++===0)setDragging(true);
    }}
    onDragOver={event=>{
      if(!isFileDrag(event))return;
      event.preventDefault();
      event.dataTransfer.dropEffect=blocked?'none':'copy';
    }}
    onDragLeave={event=>{
      if(event.currentTarget.contains(event.target as Node)&&depth.current>0&&--depth.current===0)setDragging(false);
    }}
    onDrop={event=>{
      if(!isFileDrag(event))return;
      event.preventDefault();
      depth.current=0;
      setDragging(false);
      const files=Array.from(event.dataTransfer.files);
      if(!blocked&&files.length)onFiles(files);
    }}>
    {children}
    {dragging&&!blocked&&<div className="assistant-file-drop-hint" role="status"><span>Отпустите, чтобы прикрепить файлы</span></div>}
  </section>;
}
