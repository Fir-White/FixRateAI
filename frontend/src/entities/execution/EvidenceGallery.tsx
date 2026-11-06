import { useEffect, useState } from "react";
import type { EvidencePhoto } from "@/shared/types/domain";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { Badge } from "@/shared/ui/Badge";
import { Icon } from "@/shared/ui/Icon";
import { Modal } from "@/shared/ui/Modal";
import { Button } from "@/shared/ui/Button";
import { viewLabel } from "@/shared/lib/presentation";
const PHASE_LABELS = { before: "До", after: "После", issue: "Замечание", other: "Приложение" } as const;
export function EvidencePhotoView({photo,label}:{photo:EvidencePhoto;label?:string}) {
  const formatDateTime=useSiteDateTime();
  const displayLabel=label??PHASE_LABELS[photo.phase];
  const [failed,setFailed]=useState(false);
  const [expanded,setExpanded]=useState(false);
  useEffect(()=>{setFailed(false);setExpanded(false);},[photo.id,photo.url]);
  const usable=!!photo.url && !failed;
  return <figure className="evidence-photo"><div className="evidence-photo-stage">
    {usable ? <button type="button" onClick={()=>setExpanded(true)} aria-label={`Увеличить фото: ${displayLabel}`}><img src={photo.url} alt={displayLabel} onError={()=>setFailed(true)} loading="lazy"/><span className="evidence-enlarge">Открыть фото ↗</span></button>
      : <div className="evidence-unavailable"><Icon name="camera" size={27}/><span>{failed?"Не удалось загрузить фото":photo.status==="processing"?"Фотография обрабатывается":"Изображение недоступно"}</span><small>{failed?"Возможно, истёк доступ или файл недоступен.":"Метаданные сохранены. Изображение не подменяется иллюстрацией."}</small>{failed&&<Button variant="ghost" size="sm" onClick={()=>setFailed(false)}>Повторить загрузку</Button>}</div>}
  </div><figcaption><div><Badge tone={photo.phase==="after"?"success":"neutral"}>{PHASE_LABELS[photo.phase]}</Badge>{photo.status==="rejected"&&<Badge tone="danger">Отклонено</Badge>}{photo.status==="processing"&&<Badge tone="warning">Обработка</Badge>}</div><strong>{displayLabel}</strong><details><summary>Реквизиты фотографии</summary><small>{photo.label} · {photo.id}</small></details><small>Ракурс: {viewLabel(photo.viewKey)} · {photo.capturedAt ? `Снято ${formatDateTime(photo.capturedAt)}` : `Загружено ${formatDateTime(photo.uploadedAt)}`}</small></figcaption>
  <Modal size="wide" open={expanded} onClose={()=>setExpanded(false)} title={displayLabel} description={`${PHASE_LABELS[photo.phase]} · ракурс ${viewLabel(photo.viewKey)}`}><img src={photo.url} alt={displayLabel} className="evidence-full" onError={()=>{setFailed(true);setExpanded(false);}}/></Modal></figure>;
}
export function EvidenceGallery({photos,emptyText="Фотографии к этой попытке отсутствуют"}:{photos:EvidencePhoto[];emptyText?:string}) {
  return photos.length ? <div className="evidence-gallery">{photos.map(photo=><EvidencePhotoView key={photo.id} photo={photo}/>)}</div> : <div className="evidence-empty"><Icon name="camera" size={24}/><p>{emptyText}</p></div>;
}
