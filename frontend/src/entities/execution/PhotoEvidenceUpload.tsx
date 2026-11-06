import { useEffect, useRef, useState } from "react";
import type { ChecklistItem, EvidencePhoto } from "@/shared/types/domain";
import { pairEvidence, photoRequirementProgress } from "@/shared/lib/evidence";
import { viewLabel } from "@/shared/lib/presentation";
import { pluralize } from "@/shared/lib/format";
import { Button } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { Input } from "@/shared/ui/Form";
import { EvidenceGallery, EvidencePhotoView } from "./EvidenceGallery";
import "./photo-evidence-upload.css";

type PhotoPhase = "before" | "after";
export interface PhotoUploadRequest { file: File; itemId: string; phase: PhotoPhase; viewKey: string }
interface QueuedPhoto extends PhotoUploadRequest { id: number; status: "queued" | "uploading" | "error"; error?: string }
const phaseLabel = (phase: PhotoPhase) => phase === "before" ? "до" : "после";
const acceptedTypes = ["image/jpeg", "image/png", "image/webp"];

function FilePreview({ file }: { file: File }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const value = URL.createObjectURL(file);
    setUrl(value);
    return () => URL.revokeObjectURL(value);
  }, [file]);
  return url ? <img src={url} alt="" className="fr-photo-local-preview" /> : null;
}

function DropZone({ phase, item, viewKey, disabled, compact, onFiles }: {
  phase: PhotoPhase; item: ChecklistItem; viewKey: string; disabled: boolean; compact: boolean;
  onFiles: (files: File[], itemId: string, phase: PhotoPhase, viewKey: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  return <div className={`fr-photo-drop${compact ? " is-compact" : ""}${dragging ? " is-dragging" : ""}`} data-disabled={disabled || undefined}
    onDragEnter={event => { event.preventDefault(); if (!disabled && ++depth.current === 1) setDragging(true); }}
    onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? "none" : "copy"; }}
    onDragLeave={event => { event.preventDefault(); if (--depth.current <= 0) { depth.current = 0; setDragging(false); } }}
    onDrop={event => { event.preventDefault(); event.stopPropagation(); depth.current = 0; setDragging(false); if (!disabled) onFiles(Array.from(event.dataTransfer.files), item.id, phase, viewKey); }}>
    <button type="button" disabled={disabled} onClick={() => input.current?.click()} aria-label={`Прикрепить фото ${phaseLabel(phase)}: ${item.text}`}>
      <Icon name="camera" size={24} /><strong>{compact ? "Добавить ещё фото" : "Прикрепите фото"} {phaseLabel(phase)}</strong>
      <span className="fr-photo-drop-desktop">Перетащите сюда или выберите файл</span>
      <span className="fr-photo-drop-mobile">Выберите фото или сделайте снимок</span>
      <small>JPEG, PNG, WebP · до 10 МБ на файл</small>
    </button>
    <input ref={input} className="sr-only" tabIndex={-1} aria-label={`Фото ${phaseLabel(phase)}: ${item.text}${viewKey === "front" ? "" : ` · ${viewLabel(viewKey)}`}`} type="file" multiple accept="image/jpeg,image/png,image/webp" disabled={disabled}
      onChange={event => { onFiles(Array.from(event.target.files ?? []), item.id, phase, viewKey); event.target.value = ""; }} />
  </div>;
}

function PhotoItem({ item, number, photos, queue, disabled, onFiles, onRetry, onRemove }: {
  item: ChecklistItem; number: number; photos: EvidencePhoto[]; queue: QueuedPhoto[]; disabled: boolean;
  onFiles: (files: File[], itemId: string, phase: PhotoPhase, viewKey: string) => void;
  onRetry: (id: number) => void; onRemove: (id: number) => void;
}) {
  const existing = pairEvidence(photos.filter(photo => photo.checklistItemId === item.id)).pairs;
  const viewKeys = [...new Set([...existing.map(pair => pair.viewKey), ...queue.filter(row => row.itemId === item.id).map(row => row.viewKey)])];
  if (!viewKeys.length) viewKeys.push("front");
  const [extraOpen, setExtraOpen] = useState(false);
  const [extraView, setExtraView] = useState("");
  const complete = photoRequirementProgress([item], photos).items[0]?.complete;
  const renderView = (viewKey: string, extra = false) => <div key={viewKey} className="fr-photo-view">
    {!extra && viewKeys.length > 1 && <p className="fr-photo-view-label">Ракурс · {viewLabel(viewKey)}</p>}
    <div className="fr-photo-pair-inputs">{(["before", "after"] as const).map(phase => {
      const uploaded = photos.filter(photo => photo.checklistItemId === item.id && photo.viewKey === viewKey && photo.phase === phase);
      const pending = queue.filter(row => row.itemId === item.id && row.viewKey === viewKey && row.phase === phase);
      return <div key={phase} className="fr-photo-phase">
        <div className="fr-photo-phase-heading"><span>{phase === "before" ? "01 / До выполнения" : "02 / После выполнения"}</span>{uploaded.length > 0 && <span><Icon name="check" size={14} />{uploaded.length} загружено</span>}</div>
        {uploaded.map(photo => <EvidencePhotoView key={photo.id} photo={photo} label={phase === "before" ? "До выполнения" : "После выполнения"} />)}
        {pending.map(row => <div key={row.id} className="fr-photo-queued">
          <FilePreview file={row.file} /><div><strong>{row.file.name}</strong><span>{row.status === "uploading" ? "Загружаем…" : row.status === "error" ? "Не загружено" : "В очереди"}</span>
          {row.status === "error" && <p role="alert">{row.error}</p>}
          {row.status !== "uploading" && <div className="fr-photo-queue-actions">{row.status === "error" && <Button variant="secondary" size="sm" disabled={disabled} onClick={() => onRetry(row.id)}>Повторить</Button>}<Button variant="ghost" size="sm" disabled={disabled} onClick={() => onRemove(row.id)}>Убрать из очереди</Button></div>}</div>
        </div>)}
        <DropZone phase={phase} item={item} viewKey={viewKey} compact={uploaded.length > 0 || pending.length > 0} disabled={disabled || !viewKey.trim()} onFiles={onFiles} />
      </div>;
    })}</div>
  </div>;
  return <section className="fr-photo-item" aria-label={`Фотографии: ${item.text}`}>
    <header><span className="fr-photo-item-number">{String(number).padStart(2, "0")}</span><h3>{item.text}</h3><span className={complete ? "fr-photo-item-complete" : "fr-photo-item-requirement"}>{item.photoRequired ? complete ? "Пара загружена" : "Нужны фото до и после" : "Необязательно"}</span></header>
    {viewKeys.map(viewKey => renderView(viewKey))}
    <details className="fr-photo-extra" onToggle={event => setExtraOpen(event.currentTarget.open)}><summary>Дополнительный ракурс</summary>{extraOpen && <>
      <label>Название ракурса<Input maxLength={200} value={extraView} disabled={disabled} onChange={event => setExtraView(event.target.value)} placeholder="Например, вид сбоку" /></label>
      <p>Для новой пары используйте одно название и одинаковый ракурс.</p>
      {extraView.trim() && !viewKeys.includes(extraView.trim()) && renderView(extraView.trim(), true)}
    </>}</details>
  </section>;
}

export function PhotoEvidenceUpload({ checklist, photos, disabled, onUpload, onPendingChange }: {
  checklist: ChecklistItem[]; photos: EvidencePhoto[]; disabled: boolean;
  onUpload: (request: PhotoUploadRequest) => Promise<void>;
  onPendingChange?: (count: number) => void;
}) {
  const [queue, setQueue] = useState<QueuedPhoto[]>([]);
  const queueRef = useRef<QueuedPhoto[]>([]);
  const running = useRef(false);
  const sequence = useRef(0);
  const mounted = useRef(true);
  const callback = useRef(onUpload);
  callback.current = onUpload;
  const [issues, setIssues] = useState<string[]>([]);
  const [feedback, setFeedback] = useState("");
  useEffect(() => { onPendingChange?.(queue.length); }, [queue.length, onPendingChange]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const updateQueue = (update: (rows: QueuedPhoto[]) => QueuedPhoto[]) => {
    queueRef.current = update(queueRef.current);
    if (mounted.current) setQueue(queueRef.current);
  };
  const pump = async () => {
    if (running.current || queueRef.current.some(row => row.status === "error")) return;
    running.current = true;
    try {
      while (mounted.current) {
        const next = queueRef.current.find(row => row.status === "queued");
        if (!next) break;
        updateQueue(rows => rows.map(row => row.id === next.id ? { ...row, status: "uploading" } : row));
        try {
          await callback.current(next);
          updateQueue(rows => rows.filter(row => row.id !== next.id));
          if (mounted.current) setFeedback(`Загружено: ${next.file.name}`);
        } catch (error) {
          updateQueue(rows => rows.map(row => row.id === next.id ? { ...row, status: "error", error: error instanceof Error ? error.message : "Не удалось загрузить фото" } : row));
          break;
        }
      }
    } finally { running.current = false; }
  };
  const addFiles = (files: File[], itemId: string, phase: PhotoPhase, viewKey: string) => {
    if (disabled) return;
    const errors: string[] = [];
    const accepted: QueuedPhoto[] = [];
    for (const file of files) {
      if (!(acceptedTypes.includes(file.type) || (!file.type && /\.(jpe?g|png|webp)$/i.test(file.name)))) { errors.push(`${file.name}: выберите JPEG, PNG или WebP.`); continue; }
      if (file.size === 0 || file.size > 10_485_760) { errors.push(`${file.name}: файл должен быть непустым и не больше 10 МБ.`); continue; }
      accepted.push({ id: ++sequence.current, file, itemId, phase, viewKey, status: "queued" });
    }
    setIssues(errors);
    if (accepted.length) { setFeedback(""); updateQueue(rows => [...rows, ...accepted]); void pump(); }
  };
  const retry = (id: number) => { updateQueue(rows => rows.map(row => row.id === id ? { ...row, status: "queued", error: undefined } : row)); void pump(); };
  const remove = (id: number) => { updateQueue(rows => rows.filter(row => row.id !== id)); void pump(); };
  const progress = photoRequirementProgress(checklist, photos);
  const optional = checklist.filter(item => !item.photoRequired);
  const renderItem = (item: ChecklistItem) => <PhotoItem key={item.id} item={item} number={checklist.indexOf(item) + 1} photos={photos} queue={queue} disabled={disabled} onFiles={addFiles} onRetry={retry} onRemove={remove} />;
  const other = photos.filter(photo => !checklist.some(item => item.id === photo.checklistItemId) || (photo.phase !== "before" && photo.phase !== "after"));
  return <div className="fr-photo-upload">
    <div className="fr-photo-requirements"><div><strong>{progress.minimum ? `По регламенту: ${progress.items.length} ${pluralize(progress.items.length, "пункт", "пункта", "пунктов")} · минимум ${progress.minimum} фото` : "Обязательных фотографий по регламенту нет"}</strong><p>Прикрепляйте снимки к указанному пункту. Для сравнения «до / после» сохраняйте одинаковый ракурс.</p></div>{progress.minimum > 0 && <span>{progress.covered} / {progress.minimum}<small>обязательных фото</small></span>}</div>
    {issues.length > 0 && <div className="fr-photo-errors" role="alert">{issues.map((issue, index) => <p key={index}>{issue}</p>)}</div>}
    <p role="status" className="fr-photo-upload-status">{queue.length ? `Файлов в очереди: ${queue.length}.${queue.some(row => row.status === "error") ? " Загрузка приостановлена. Повторите ошибочный файл или уберите его из очереди." : " Фотографии загружаются автоматически."}` : feedback}</p>
    {progress.items.map(({ item }) => renderItem(item))}
    {optional.length > 0 && <details className="fr-photo-optional"><summary>Фото к другим пунктам · необязательно ({optional.length})</summary>{optional.map(renderItem)}</details>}
    {other.length > 0 && <EvidenceGallery photos={other} />}
  </div>;
}
