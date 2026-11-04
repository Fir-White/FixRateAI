import type { ChecklistItem, EvidencePhoto } from "@/shared/types/domain";
import { pairEvidence } from "@/shared/lib/evidence";
import { EvidenceGallery, EvidencePhotoView } from "./EvidenceGallery";
import { Icon } from "@/shared/ui/Icon";
export function EvidenceComparison({photos,checklist}:{photos:EvidencePhoto[];checklist:ChecklistItem[]}) {
  const {pairs,other}=pairEvidence(photos);
  if(!photos.length) return <div className="evidence-empty"><Icon name="camera" size={27}/><strong>Нет фотографий для сравнения</strong><p>Фото к этой попытке не приложены. Выполнение нельзя подтвердить по отсутствующим изображениям.</p></div>;
  return <div className="evidence-comparison"><p className="evidence-guidance">Сопоставлены только одинаковые пункты чек-листа и ракурсы. Наличие пары само по себе не подтверждает выполнение операции.</p>
  {pairs.map(pair=>{const item=checklist.find(i=>i.id===pair.checklistItemId);return <section key={pair.key} className="evidence-pair"><header><h3>{item?.text || `Пункт ${pair.checklistItemId}`}</h3><span>Ракурс · {pair.viewKey || "не указан"}</span></header>{item?.visualVerifiability==="not_verifiable"&&<p className="evidence-limitation">Эта операция не проверяется по фотографии. Нужны показания или другое подтверждение.</p>}<div className="evidence-pair-grid">{(["before","after"] as const).map(phase=><div key={phase}><div className="evidence-phase-label">{phase==="before"?"01 / До выполнения":"02 / После выполнения"}<span>{pair[phase].length} фото</span></div>{pair[phase].length ? pair[phase].map(photo=><EvidencePhotoView key={photo.id} photo={photo}/>) : <div className="evidence-missing"><Icon name="camera" size={23}/><strong>Нет фото {phase==="before"?"до":"после"}</strong><p>Пара неполная. Для сравнения нужно дополнительное изображение.</p></div>}</div>)}</div></section>;})}
  {other.length>0&&<section className="evidence-other"><h3>Замечания и приложения</h3><EvidenceGallery photos={other}/></section>}</div>;
}
