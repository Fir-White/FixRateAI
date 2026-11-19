import { AnalysisTimerBadge, PhotoReviewCard } from "@/entities/execution/PhotoReviewCard";
import { AttemptHistory } from "@/features/analyst/AnalystPanels";
import { ExecutionProtocol,ActsPanel } from "@/features/analyst/AnalystPanels";
import type { ActualExecution,Reading } from "@/shared/types/domain";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { maintenanceApi, type TaskBundle } from "@/shared/api/maintenance";
import { DEMO_MODE } from "@/shared/api/request";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { formatDate } from "@/shared/lib/format";
import { isTaskOverdue } from "@/shared/lib/operations";
import { useSiteDateTime } from "@/shared/lib/useSiteDateTime";
import { Button } from "@/shared/ui/Button";
import { Callout } from "@/shared/ui/Callout";
import { ErrorState, LoadingState } from "@/shared/ui/States";
import { EvidenceComparison } from "@/entities/execution/EvidenceComparison";
import { PhotoEvidenceUpload, type PhotoUploadRequest } from "@/entities/execution/PhotoEvidenceUpload";
import { photoRequirementProgress } from "@/shared/lib/evidence";
import { ReadOnlyValue } from "@/shared/ui/ContentTheme";
import { answerLabel, attemptStateSummary } from "@/shared/lib/presentation";
import "./execution-redesign.css";
import { TaskStateBadge, OverdueBadge } from "@/shared/ui/StatusBadge";
import { useSession } from "@/shared/session/SessionContext";
import { PageHeader } from "@/shared/ui/PageHeader";
import { FormField, Input, Textarea } from "@/shared/ui/Form";
import { Icon } from "@/shared/ui/Icon";
import { JourneySteps } from '@/shared/ui/JourneySteps';
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
 const navigate=useNavigate();
 const dateTime=useSiteDateTime();const {task,execution,decision}=bundle;
 const allowed=(action:NonNullable<TaskBundle["allowedActions"]>[number])=>!DEMO_MODE&&!!bundle.allowedActions?.includes(action);
 const editable=allowed("edit_report");const canStart=allowed("start");
 const [reportStep,setReportStep]=useState('checklist');
 const [revision,setRevision]=useState(task.revision);const [narrative,setNarrative]=useState(execution?.narrative??"");
 const [protocol,setProtocol]=useState<{actual:ActualExecution|null;readings:Reading[]}>({actual:execution?.actual?{started_at:execution.actual.started_at??"",performed_at:execution.actual.performed_at??"",person_hours:execution.actual.person_hours??""}:null,readings:execution?.readings??[]});
 const [answers,setAnswers]=useState<Record<string,string|null>>(Object.fromEntries(execution?.checklist.map(i=>[i.id,i.answer])??[]));
 const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);const [dirty,setDirty]=useState(false);const [confirmSubmit,setConfirmSubmit]=useState(false);
 const [confirmLeave,setConfirmLeave]=useState(false);
 const [photos,setPhotos]=useState(execution?.photos??[]);const [uploadingPhoto,setUploadingPhoto]=useState(false);const [photoQueueLength,setPhotoQueueLength]=useState(0);
 const revisionRef=useRef(task.revision);const mutating=useRef(false);
 useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
 const required=execution?.checklist.filter(i=>i.required)??[];
 const photosReady=execution?photoRequirementProgress(execution.checklist,photos).ready:false;
 const filled=required.filter(i=>i.answerKind==="boolean"?answers[i.id]==="done":answers[i.id]!==null&&answers[i.id]!==undefined&&String(answers[i.id]).trim()!=="").length;
 const changeAnswer=(id:string,value:string|null)=>{setAnswers(prev=>({...prev,[id]:value}));setDirty(true);};
 const saveDraft=async()=>{const saved=await maintenanceApi.saveReport(task.id,revisionRef.current,narrative,answers,protocol);revisionRef.current=saved.task.revision;setRevision(saved.task.revision);setDirty(false);return saved.task.revision;};
 const act=async(action:()=>Promise<unknown>,refresh=true)=>{if(mutating.current)return;mutating.current=true;setBusy(true);setNotice("");try{await action();if(refresh)reload();}catch(error){setNotice(error instanceof Error?error.message:"Ошибка API");}finally{mutating.current=false;setBusy(false);}};
 const uploadPhoto=async({file,itemId,phase,viewKey}:PhotoUploadRequest)=>{
  if(mutating.current)throw new Error("Дождитесь завершения текущего сохранения.");
  mutating.current=true;setBusy(true);setUploadingPhoto(true);setNotice("");
  try{const saved=dirty?await saveDraft():revisionRef.current;const result=await maintenanceApi.upload(task.id,saved,itemId,phase,viewKey,file);revisionRef.current=result.task.revision;setRevision(result.task.revision);setPhotos(result.execution?.photos??[]);}
  finally{mutating.current=false;setUploadingPhoto(false);setBusy(false);}
 };
 return <div className="space-y-5 executor-editor"><Link to="/executor?queue=active" className="ops-back" onClick={event=>{
   if(dirty||busy||photoQueueLength>0){event.preventDefault();setConfirmLeave(true);}
 }}><Icon name="back" size={17}/>Мои задания</Link>
 <PageHeader title={task.title} description={`${task.code} · ${task.equipmentName}`}/>
 <div className="flex flex-wrap items-center gap-2"><TaskStateBadge state={task.state}/>{isTaskOverdue(task)&&<OverdueBadge/>}<span className="text-xs text-muted">{execution?`Попытка №${execution.attemptNumber}`:"Выполнение ещё не начато"}</span></div>
 <div className="fr-attempt-layout"><aside className="fr-attempt-context"><h2>Текущая попытка</h2><p>{attemptStateSummary(task.state)}</p><div className="execution-deadline"><div><span>Обязательный срок</span><strong>{formatDate(task.mandatoryDueDate)}</strong></div><div><span>Плановое начало</span><strong>{dateTime(task.scheduledStart)}</strong></div>{task.equipmentId&&<Link to={`/equipment/${task.equipmentId}`} className="text-xs text-accent">Паспорт оборудования ↗</Link>}</div></aside><div className="fr-attempt-content space-y-5">
 {task.summary&&<p className="execution-instruction">{task.summary}</p>}
 <details className="execution-section space-y-3" open={!execution} aria-label="Инструкция перед началом работ"><summary className="font-semibold cursor-pointer">Инструкция и безопасность</summary><p className="whitespace-pre-wrap text-sm leading-6">{task.instructions||'Инструкция не указана. Уточните порядок и безопасность работ у инженера.'}</p><p className="text-xs text-muted">Бригада: {task.crewSize??'не указана'} чел. Плановая длительность: {task.durationMinutes??'не указана'} мин.</p></details>
 {decision&&<Callout tone={decision.verdict==="accepted"?"success":"warning"} title={decision.verdict==="accepted"?"Работа принята":"Основание возврата"}><p>{decision.reason}</p><p className="mt-2 text-sm text-muted">Проверяющий: {decision.decidedBy}</p></Callout>}
 {DEMO_MODE&&<Callout tone="neutral">DEMO · Отчёт доступен для просмотра. Начало работ, изменение ответов, загрузка фото и сдача требуют рабочего API.</Callout>}
 {notice&&<div role="alert"><Callout tone="danger">{notice}</Callout></div>}
 {canStart&&<Button disabled={busy} onClick={()=>act(()=>maintenanceApi.start(task.id,revision))}><Icon name="check" size={18}/>{task.state==="rework_required"?"Начать новую попытку":"Приступить к работе"}</Button>}
 {!DEMO_MODE&&task.state==="in_progress"&&!editable&&<Callout tone="neutral">Отчёт текущей попытки ведёт другой участник бригады. Вам доступен просмотр.</Callout>}
 {!execution&&<div className="execution-not-started"><Icon name="tasks" size={25}/><strong>Чек-лист откроется после начала работ</strong><p>Ответы и фотографии будут привязаны к текущей попытке выполнения.</p></div>}
 {execution&&<><JourneySteps label="Выполнение задания" value={reportStep} onChange={setReportStep} steps={[
   {id:'checklist',title:'Выполнить чек-лист',description:'Следуйте инструкции и отметьте результат каждого пункта.',content:()=> <>
 <section id="execution-checklist" className="execution-section"><header><div><h2>Чек-лист</h2></div><span className="execution-progress">{filled} / {required.length}<small>обязательных ответов</small></span></header>
 <div className="execution-progress-track"><span style={{width:`${required.length?filled/required.length*100:0}%`}}/></div>
 <div className="execution-checklist">{execution.checklist.map((item,index)=><div key={item.id} className="execution-check-item"><span className="execution-check-number">{String(index+1).padStart(2,"0")}</span><div className="execution-check-content"><label htmlFor={`answer-${item.id}`} className="execution-item-label">{item.text}{item.required&&<span aria-label="обязательный"> *</span>}</label>{item.photoRequired&&<p className="execution-photo-required"><Icon name="camera" size={13}/>Требуются фотографии до и после</p>}
 {!editable?<ReadOnlyValue label="Сохранённый ответ">{answerLabel(answers[item.id])}{item.unit?` ${item.unit}`:""}</ReadOnlyValue>:item.answerKind==="boolean"?<label className="execution-checkbox"><input id={`answer-${item.id}`} type="checkbox" checked={answers[item.id]==="done"} disabled={!editable||busy} onChange={e=>changeAnswer(item.id,e.target.checked?"done":"not_done")}/><span>{answers[item.id]==="done"?"Выполнено":answers[item.id]==="not_done"?"Не выполнено":answers[item.id]==="not_applicable"?"Не применимо":"Отметить выполнение"}</span></label>:<div className="execution-measurement"><Input id={`answer-${item.id}`} inputMode={item.answerKind==="number"?"decimal":"text"} autoComplete="off" value={answers[item.id]??""} disabled={!editable||busy} onChange={e=>changeAnswer(item.id,e.target.value)} placeholder={item.answerKind==="number"?"Введите показание":"Введите ответ"}/>{item.unit&&<span>{item.unit}</span>}</div>}
 </div></div>)}</div></section>
<div className="journey-footer"><span className="text-sm text-muted">Ответы сохраняются кнопкой «Сохранить» и перед загрузкой фотографий.</span><Button variant="secondary" onClick={()=>setReportStep('photos')}>Далее: фотографии →</Button></div></>},
   {id:'photos',title:'Добавить фотографии',description:'Приложите фотографии к нужным пунктам текущей попытки.',content:()=> <>
 <section id="execution-photos" className="execution-section"><header><div><h2>Фотоотчёт</h2></div><span className="text-xs text-muted">{photos.length} фото</span></header>
 {editable&&allowed("upload_photo")?<PhotoEvidenceUpload checklist={execution.checklist} photos={photos} disabled={busy&&!uploadingPhoto} onUpload={uploadPhoto} onPendingChange={setPhotoQueueLength}/>:<EvidenceComparison photos={photos} checklist={execution.checklist}/>}
 </section>
<div className="journey-footer"><Button variant="ghost" onClick={()=>setReportStep('checklist')}>← К чек-листу</Button><Button variant="secondary" onClick={()=>setReportStep('finish')}>Далее: проверить и сдать →</Button></div></>},
   {id:'finish',title:'Итоговый отчёт',description:'Укажите фактическое время, показания и комментарий. Затем передайте отчёт инженеру.',content:()=> <div className="space-y-5">
<ExecutionProtocol task={task} execution={execution} value={protocol} onChange={v=>{setProtocol(v);setDirty(true);}} disabled={!editable||busy} readOnly={!editable}/><ActsPanel beforeWrite={()=>dirty?saveDraft():Promise.resolve(revisionRef.current)} task={{...task,revision}} execution={execution} editable={editable} disabled={busy||photoQueueLength>0} onBusyChange={value=>{mutating.current=value;setBusy(value);}} onSaved={reload}/> <section id="execution-comment" className="execution-section"><header><div><h2>Комментарий к работе</h2></div></header>{!editable?<ReadOnlyValue label="Что выполнено и какие замечания остались">{narrative||"Комментарий не указан"}</ReadOnlyValue>:<FormField label="Что выполнено и какие замечания остались" htmlFor="executor-narrative"><Textarea id="executor-narrative" rows={4} value={narrative} disabled={!editable||busy} onChange={e=>{setNarrative(e.target.value);setDirty(true);}} placeholder="Укажите обстоятельства, которые не видны на фотографиях"/></FormField>}</section>
{editable&&<div className="journey-next"><div><h3>Готовность отчёта</h3><p>Обязательные ответы: {filled} из {required.length}. {photosReady?'Нужные фотографии приложены.':'Приложите обязательные фотографии.'} Фактические данные и документы также проверяются при сдаче.</p></div><div className="flex flex-wrap gap-2">{filled<required.length&&<Button variant="secondary" onClick={()=>setReportStep('checklist')}>Заполнить ответы</Button>}{!photosReady&&<Button variant="secondary" onClick={()=>setReportStep('photos')}>Добавить фото</Button>}</div></div>}</div>},
 ]}/>
 {editable&&<div className="execution-submit-bar"><div role="status"><strong>{uploadingPhoto?"Загрузка фотографий…":photoQueueLength?`Фотографий в очереди: ${photoQueueLength}`:busy?"Сохранение…":dirty?"Есть несохранённые изменения":"Текущие ответы сохранены"}</strong><span>Ответы сохраняются перед загрузкой фото и сдачей.</span></div><Button variant="secondary" disabled={busy||photoQueueLength>0||!dirty} onClick={()=>act(saveDraft)}>Сохранить</Button>{reportStep==="finish"&&allowed("submit")&&<Button disabled={busy||photoQueueLength>0||filled<required.length||!photosReady} onClick={()=>setConfirmSubmit(true)}>Сдать работу<Icon name="chevron" size={16}/></Button>}</div>}
 {!editable&&<Callout tone="neutral">{attemptStateSummary(task.state)}</Callout>}
 {bundle.photoAnalysisStatus==="pending"&&<Callout tone="neutral"><div className="flex flex-wrap items-center justify-between gap-2"><p role="status">Фотографии анализируются автоматически. Результат появится без обновления страницы.</p><AnalysisTimerBadge active/></div></Callout>}
 {bundle.review&&<PhotoReviewCard review={bundle.review} formatDateTime={dateTime}/>}
 </>}
 </div></div><details className="fr-rule-section"><summary>История выполнения и предыдущие попытки</summary><AttemptHistory taskId={task.id}/></details>
 <Modal open={confirmSubmit} onClose={()=>setConfirmSubmit(false)} title="Передать отчёт инженеру?" description="Ответы будут сохранены. После сдачи эта попытка станет недоступной для редактирования." footer={<><Button variant="secondary" onClick={()=>setConfirmSubmit(false)}>Проверить ещё раз</Button><Button disabled={busy} onClick={()=>{setConfirmSubmit(false);void act(async()=>{const saved=await saveDraft();return maintenanceApi.submit(task.id,saved);});}}>Подтвердить сдачу</Button></>}><p className="text-sm text-ink-soft">Заполнено обязательных ответов: {filled} из {required.length}. Фотографий: {photos.length}. Полноту отчёта проверит сервер.</p></Modal>
 <Modal open={confirmLeave} title={dirty?"Есть несохранённые изменения":"Отчёт сохраняется"}
   onClose={()=>{if(!busy)setConfirmLeave(false);}}
   footer={<>
     <Button variant="secondary" disabled={busy} onClick={()=>setConfirmLeave(false)}>Вернуться к отчёту</Button>
     <Button variant="danger" disabled={busy||photoQueueLength>0} onClick={()=>navigate("/executor?queue=active")}>Выйти без сохранения</Button>
     {dirty&&<Button disabled={busy||photoQueueLength>0} onClick={()=>void act(async()=>{await saveDraft();navigate("/executor?queue=active");},false)}>Сохранить и выйти</Button>}
   </>}>
   <p className="text-ink-soft">{busy||photoQueueLength>0?"Дождитесь окончания сохранения или загрузки фотографий.":"Сохраните ответы и фактические данные перед выходом."}</p>
   {notice&&<Callout tone="danger">{notice}</Callout>}
 </Modal>
 </div>;
}
