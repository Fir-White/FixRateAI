import { AnalysisTimerBadge, PhotoReviewCard } from "@/entities/execution/PhotoReviewCard";
import { AttemptHistory } from "@/features/analyst/AnalystPanels";
import { ExecutionProtocol,ActsPanel } from "@/features/analyst/AnalystPanels";
import type { ActualExecution,Reading } from "@/shared/types/domain";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { maintenanceApi, type TaskBundle } from "@/shared/api/maintenance";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { isTaskOverdue } from "@/shared/lib/operations";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { Button } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { EvidenceGallery } from "@/entities/execution/EvidenceGallery";
import { TaskStateBadge, OverdueBadge } from "@/shared/ui/StatusBadge";
import { useSession } from "@/shared/session/SessionContext";
import { PageHeader } from "@/shared/ui/PageHeader";
import { FormField, Input, Select, Textarea } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { Modal } from "@/shared/ui/Modal";

export function ExecutorTaskPage(){
 const {taskId=""}=useParams();const [refresh,setRefresh]=useState(0);
 const query=useApiQuery(()=>maintenanceApi.getExecutorTask(taskId),[taskId,refresh],bundle=>!DEMO_MODE&&bundle.photoAnalysisStatus==="pending");const {profile}=useSession();
 if(query.status==="loading")return <LoadingState label="Загрузка задания"/>;
 if(query.status==="error")return <ErrorState description={query.error}/>;
 if(!query.data.task.assignees.some(a=>a.executorId===profile?.userId))return <ErrorState title="Задание назначено другому исполнителю" description="Доступ проверяется сервером."/>;
 return <ExecutionEditor key={`${query.data.task.id}:${query.data.task.revision}`} bundle={query.data} reload={()=>setRefresh(n=>n+1)}/>;
}
function ExecutionEditor({bundle,reload}:{bundle:TaskBundle;reload:()=>void}){
 const dateTime=useSiteDateTime();const {task,execution,decision}=bundle;
 const allowed=(action:NonNullable<TaskBundle["allowedActions"]>[number])=>!DEMO_MODE&&!!bundle.allowedActions?.includes(action);
 const editable=allowed("edit_report");const canStart=allowed("start");
 const [revision,setRevision]=useState(task.revision);const [narrative,setNarrative]=useState(execution?.narrative??"");
 const [protocol,setProtocol]=useState<{actual:ActualExecution|null;readings:Reading[]}>({actual:execution?.actual?{started_at:execution.actual.started_at??"",performed_at:execution.actual.performed_at??"",person_hours:execution.actual.person_hours??""}:null,readings:execution?.readings??[]});
 const [answers,setAnswers]=useState<Record<string,string|null>>(Object.fromEntries(execution?.checklist.map(i=>[i.id,i.answer])??[]));
 const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);const [dirty,setDirty]=useState(false);const [confirmSubmit,setConfirmSubmit]=useState(false);
 const [itemId,setItemId]=useState(execution?.checklist[0]?.id??"");const [phase,setPhase]=useState("before");const [viewKey,setViewKey]=useState("front");const [file,setFile]=useState<File|null>(null);
 useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
 const required=execution?.checklist.filter(i=>i.required)??[];
 const photosReady=execution?.checklist.every(i=>!i.photoRequired||execution.photos.some(p=>p.checklistItemId===i.id&&p.phase==="before"&&execution.photos.some(a=>a.checklistItemId===i.id&&a.phase==="after"&&a.viewKey===p.viewKey)))??false;
 const filled=required.filter(i=>i.answerKind==="boolean"?answers[i.id]==="done":answers[i.id]!==null&&answers[i.id]!==undefined&&String(answers[i.id]).trim()!=="").length;
 const changeAnswer=(id:string,value:string|null)=>{setAnswers(prev=>({...prev,[id]:value}));setDirty(true);};
 const saveDraft=async()=>{const saved=await maintenanceApi.saveReport(task.id,revision,narrative,answers,protocol);setRevision(saved.task.revision);setDirty(false);return saved.task.revision;};
 const act=async(action:()=>Promise<unknown>)=>{if(busy)return;setBusy(true);setNotice("");try{await action();reload();}catch(error){setNotice(error instanceof Error?error.message:"Ошибка API");}finally{setBusy(false);}};
 return <div className="space-y-5 executor-editor"><Link to="/executor" className="ops-back" onClick={e=>{if(dirty&&!window.confirm("Есть несохранённые ответы. Вернуться к заданиям без сохранения?"))e.preventDefault();}}><Icon name="back" size={17}/>Мои задания</Link>
 <AttemptHistory taskId={task.id}/><PageHeader eyebrow={task.code} title={task.title} description={task.equipmentName}/>
 <div className="flex flex-wrap items-center gap-2"><TaskStateBadge state={task.state}/>{isTaskOverdue(task)&&<OverdueBadge/>}<span className="text-xs text-muted">{execution?`Попытка №${execution.attemptNumber}`:"Выполнение ещё не начато"}</span></div>
 <div className="execution-deadline"><div><span>Обязательный срок</span><strong>{formatDate(task.mandatoryDueDate)}</strong></div><div><span>Плановое начало</span><strong>{dateTime(task.scheduledStart)}</strong></div>{task.equipmentId&&<Link to={`/equipment/${task.equipmentId}`} className="text-xs text-accent">Паспорт оборудования ↗</Link>}</div>
 {task.summary&&<p className="execution-instruction">{task.summary}</p>}
 {decision&&<Callout tone={decision.verdict==="accepted"?"success":"warning"} title={decision.verdict==="accepted"?"Работа принята":"Основание возврата"}>{decision.reason} · {decision.decidedBy}</Callout>}
 {DEMO_MODE&&<Callout tone="neutral">DEMO · Отчёт доступен для просмотра. Начало работ, изменение ответов, загрузка фото и сдача требуют рабочего API.</Callout>}
 {notice&&<div role="alert"><Callout tone="danger">{notice}</Callout></div>}
 {canStart&&<Button disabled={busy} onClick={()=>act(()=>maintenanceApi.start(task.id,revision))}><Icon name="check" size={18}/>{task.state==="rework_required"?"Начать новую попытку":"Приступить к работе"}</Button>}
 {!DEMO_MODE&&task.state==="in_progress"&&!editable&&<Callout tone="neutral">Отчёт текущей попытки ведёт другой участник бригады. Вам доступен просмотр.</Callout>}
 {!execution&&<div className="execution-not-started"><Icon name="tasks" size={25}/><strong>Чек-лист откроется после начала работ</strong><p>Ответы и фотографии будут привязаны к текущей попытке выполнения.</p></div>}
 {execution&&<><ExecutionProtocol task={task} execution={execution} value={protocol} onChange={v=>{setProtocol(v);setDirty(true);}} disabled={!editable||busy}/><ActsPanel task={task} execution={execution} editable={editable} onSaved={reload}/><nav className="execution-section-nav" aria-label="Разделы отчёта"><a href="#execution-checklist">01 Чек-лист</a><a href="#execution-photos">02 Фотоотчёт</a><a href="#execution-comment">03 Комментарий</a></nav>
 <section id="execution-checklist" className="execution-section"><header><div><span className="ops-kicker">01 / Выполнение</span><h2>Чек-лист</h2></div><span className="execution-progress">{filled} / {required.length}<small>обязательных ответов</small></span></header>
 <div className="execution-progress-track"><span style={{width:`${required.length?filled/required.length*100:0}%`}}/></div>
 <div className="execution-checklist">{execution.checklist.map((item,index)=><div key={item.id} className="execution-check-item"><span className="execution-check-number">{String(index+1).padStart(2,"0")}</span><div className="execution-check-content"><label htmlFor={`answer-${item.id}`} className="execution-item-label">{item.text}{item.required&&<span aria-label="обязательный"> *</span>}</label>{item.photoRequired&&<p className="execution-photo-required"><Icon name="camera" size={13}/>Требуются фотографии до и после</p>}
 {item.answerKind==="boolean"?<label className="execution-checkbox"><input id={`answer-${item.id}`} type="checkbox" checked={answers[item.id]==="done"} disabled={!editable||busy} onChange={e=>changeAnswer(item.id,e.target.checked?"done":"not_done")}/><span>{answers[item.id]==="done"?"Выполнено":answers[item.id]==="not_done"?"Не выполнено":answers[item.id]==="not_applicable"?"Не применимо":"Отметить выполнение"}</span></label>:<div className="execution-measurement"><Input id={`answer-${item.id}`} inputMode={item.answerKind==="number"?"decimal":"text"} autoComplete="off" value={answers[item.id]??""} disabled={!editable||busy} onChange={e=>changeAnswer(item.id,e.target.value)} placeholder={item.answerKind==="number"?"Введите показание":"Введите ответ"}/>{item.unit&&<span>{item.unit}</span>}</div>}
 </div></div>)}</div></section>
 <section id="execution-photos" className="execution-section"><header><div><span className="ops-kicker">02 / Доказательства</span><h2>Фотоотчёт</h2></div><span className="text-xs text-muted">{execution.photos.length} фото</span></header><EvidenceGallery photos={execution.photos}/>
 {editable&&allowed("upload_photo")&&<fieldset disabled={busy} className="execution-upload"><legend>Добавить фотографию</legend><p>Для пары «до / после» выбирайте один пункт и одинаковый ракурс.</p><div className="execution-upload-fields"><FormField label="Пункт чек-листа" htmlFor="photo-item"><Select id="photo-item" value={itemId} onChange={e=>setItemId(e.target.value)}>{execution.checklist.map(i=><option key={i.id} value={i.id}>{i.text}</option>)}</Select></FormField><FormField label="Этап" htmlFor="photo-phase"><Select id="photo-phase" value={phase} onChange={e=>setPhase(e.target.value)}><option value="before">До выполнения</option><option value="after">После выполнения</option></Select></FormField><FormField label="Ракурс" htmlFor="photo-view"><Input id="photo-view" value={viewKey} onChange={e=>setViewKey(e.target.value)}/></FormField></div>
 <label className="execution-file"><Icon name="camera" size={22}/><span>{file?file.name:"Выберите или снимите фото"}<small>JPEG, PNG или WebP</small></span><input aria-label="Файл фото" type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{const selected=e.target.files?.[0]??null;if(selected&&!['image/jpeg','image/png','image/webp'].includes(selected.type)){setNotice("Выберите JPEG, PNG или WebP.");setFile(null);return;}setFile(selected);setNotice("");}}/></label>
 <Button variant="secondary" disabled={busy||!file||!viewKey.trim()||!itemId} onClick={()=>file&&act(async()=>{const saved=await saveDraft();return maintenanceApi.upload(task.id,saved,itemId,phase,viewKey.trim(),file);})}><Icon name="upload" size={16}/>Загрузить фото</Button></fieldset>}
 </section>
 <section id="execution-comment" className="execution-section"><header><div><span className="ops-kicker">03 / Передача инженеру</span><h2>Комментарий к работе</h2></div></header><FormField label="Что выполнено и какие замечания остались" htmlFor="executor-narrative"><Textarea id="executor-narrative" rows={4} value={narrative} disabled={!editable||busy} onChange={e=>{setNarrative(e.target.value);setDirty(true);}} placeholder="Укажите обстоятельства, которые не видны на фотографиях"/></FormField></section>
 {editable&&<div className="execution-submit-bar"><div role="status"><strong>{busy?"Сохранение…":dirty?"Есть несохранённые изменения":"Текущие ответы сохранены"}</strong><span>Ответы сохраняются перед загрузкой фото и сдачей.</span></div><Button variant="secondary" disabled={busy||!dirty} onClick={()=>act(saveDraft)}>Сохранить</Button>{allowed("submit")&&<Button disabled={busy||filled<required.length||!photosReady} onClick={()=>setConfirmSubmit(true)}>Сдать работу<Icon name="chevron" size={16}/></Button>}</div>}
 {!editable&&execution.state==="submitted"&&<Callout tone="neutral">Отчёт отправлен. Изменения недоступны до решения инженера.</Callout>}
 {bundle.photoAnalysisStatus==="pending"&&<Callout tone="neutral"><div className="flex flex-wrap items-center justify-between gap-2"><p role="status">Фотографии анализируются автоматически. Результат появится без обновления страницы.</p><AnalysisTimerBadge active/></div></Callout>}
 {bundle.review&&<PhotoReviewCard review={bundle.review} formatDateTime={dateTime}/>}
 </>}
 <Modal open={confirmSubmit} onClose={()=>setConfirmSubmit(false)} title="Передать отчёт инженеру?" description="Ответы будут сохранены. После сдачи эта попытка станет недоступной для редактирования." footer={<><Button variant="secondary" onClick={()=>setConfirmSubmit(false)}>Проверить ещё раз</Button><Button disabled={busy} onClick={()=>{setConfirmSubmit(false);void act(async()=>{const saved=await saveDraft();return maintenanceApi.submit(task.id,saved);});}}>Подтвердить сдачу</Button></>}><p className="text-sm text-ink-soft">Заполнено обязательных ответов: {filled} из {required.length}. Фотографий: {execution?.photos.length??0}. Полноту отчёта проверит сервер.</p></Modal>
 </div>;
}
