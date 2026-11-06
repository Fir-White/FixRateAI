import { useEffect, useState } from "react";
import "./photo-review.css";
import type { PhotoReview } from "@/shared/types/domain";
import { formatDurationMs } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { Card, CardHeader } from "@/shared/ui/Card";
import { Callout } from "@/shared/ui/Callout";
import { Icon } from "@/shared/ui/Icon";
import { EmptyState } from "@/shared/ui/States";
import { ReviewStatusBadge, VerdictBadge } from "@/shared/ui/StatusBadge";

export function AnalysisTimerBadge({ active }: { active: boolean }) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsedMs(0);
      return;
    }
    const startedAt = performance.now();
    setElapsedMs(0);
    const timer = window.setInterval(() => {
      setElapsedMs(Math.max(0, Math.round(performance.now() - startedAt)));
    }, 100);
    return () => window.clearInterval(timer);
  }, [active]);

  if (!active) return null;

  const seconds = (elapsedMs / 1000).toFixed(1);
  return (
    <Badge tone="info" className="font-mono tabular-nums">
      <Icon name="clock" size={13} />
      <span>Ожидание результата: {seconds} сек</span>
    </Badge>
  );
}

function Findings({title,items,empty}:{title:string;items:string[];empty?:string}) {
  return <section className="mt-4"><h4 className="text-sm font-semibold text-ink">{title}</h4>
    {items.length?<ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-ink-soft">{items.map((text,index)=><li key={index}>{text}</li>)}</ul>:empty?<p className="mt-2 text-sm leading-6 text-muted">{empty}</p>:null}</section>;
}

export function PhotoReviewCard({review,formatDateTime,fallbackElapsedMs}:{review:PhotoReview|null;formatDateTime:(value:string)=>string;fallbackElapsedMs?:number|null}) {
  const legacy=review?.modelRef?.includes("clip-")??false;
  const cloud=review?.modelRef?.startsWith("aitunnel:")||review?.errorCode?.startsWith("AITUNNEL_");
  const errorMessage=review?.errorCode==="AITUNNEL_RATE_LIMITED"?"Сервис временно ограничил частоту запросов. Подождите и повторите анализ.":review?.errorCode==="AITUNNEL_QUOTA_EXCEEDED"?"Лимит облачного анализа исчерпан. Обратитесь к администратору стенда.":review?.errorCode==="AITUNNEL_NOT_CONFIGURED"||review?.errorCode==="AITUNNEL_AUTH_FAILED"?"Облачный анализ сейчас не настроен или доступ отклонён. Обратитесь к администратору стенда.":review?.errorCode?.endsWith("TIMEOUT")?"Модель не успела закончить проверку. Повторите анализ через некоторое время.":review?.status==="unavailable"?cloud?"Облачный сервис анализа сейчас недоступен. Повторите запрос позже.":"Локальная модель сейчас недоступна. Запустите сервис анализа и повторите запрос.":"Ответ модели не удалось проверить. Повторите анализ; при повторной ошибке обратитесь к администратору стенда.";
  const hasChanges=review?.items.some(item=>item.verdict==="visible_change");
  const uncertain=review?.status!=="completed"||review.items.some(item=>item.verdict!=="visible_change");
  const title=review?.status==="failed"||review?.status==="unavailable"?"Не удалось выполнить фотоанализ":legacy?"Качество работы по этой проверке не подтверждено":uncertain?"Для приёмки нужны дополнительные подтверждения":hasChanges?"На фото обнаружены видимые изменения":"Данных для вывода недостаточно";
  const resolvedElapsedMs = review?.elapsedMs ?? fallbackElapsedMs ?? null;
  const durationLabel = formatDurationMs(resolvedElapsedMs);
  return <Card><CardHeader title="Разбор фотоотчёта" description="Наблюдения по фотографиям и основания для решения инженера" action={review?<div className="flex flex-wrap items-center gap-2">{durationLabel&&<Badge tone="neutral" className="font-mono tabular-nums"><Icon name="clock" size={13}/><span>Время анализа: {durationLabel}</span></Badge>}<ReviewStatusBadge status={review.status}/></div>:null}/>
    <div className="p-5 sm:p-6">{review?<>
      <Callout tone={uncertain||legacy?"warning":"neutral"} title={title}>
        {legacy?"Сохранённый результат получен прежней моделью CLIP, которая сравнивает сходство с текстовыми описаниями. Для разбора содержимого фотографий запустите новый анализ.":"Вывод модели помогает проверить отчёт. Приёмку и необходимые контрольные измерения выполняет инженер."}
      </Callout>
      {review.classification&&<p className="mt-3 font-semibold">Доказательства: {review.classification==="approved"?"видимая часть подтверждена":review.classification==="rejected"?"фото отклонены — нужны другие снимки":"нужна ручная проверка"}. Окончательное решение принимает контролёр.</p>}
      {!!review.readingComparison?.length&&<div className="mt-3 space-y-2"><h3>Сверка показаний с протоколом</h3>{review.readingComparison.map((r,i)=><p key={i}>{r.parameter_code} ({r.phase==="before"?"До":r.phase==="after"?"После":r.phase}): введено {r.value} {r.unit}; на фото {r.observed??"не читается"}; {r.status==="match"?"совпадает":r.status==="mismatch"?"расхождение — нужна проверка":"автоматическая сверка невозможна"}.</p>)}</div>}
      {(review.status==="unavailable"||review.status==="failed")&&<p className="mt-3 text-sm leading-6 text-ink-soft">{errorMessage}</p>}
      <div className="mt-3 space-y-2 text-sm"><p>Точность прибора и скрытые операции нельзя подтвердить только фотографией.</p>{[...new Set([...review.limitations,...review.items.flatMap(item=>item.assessment?.cannot_confirm??[])])].map(text=><p key={text}>{text}</p>)}<p>Неопределённых пунктов: {review.items.filter(item=>item.verdict==="uncertain").length}; не проверяются по фото: {review.items.filter(item=>item.verdict==="not_verifiable").length}.</p></div>
      <details className="mt-4 fr-ai-details"><summary>Подробности анализа по {review.items.length} пунктам</summary><div className="mt-5 space-y-5">{review.items.map(item=><article key={item.id} className="rounded-xl border border-line p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold text-ink">Проверяемый пункт: {item.label}</h3><VerdictBadge verdict={item.verdict}/></div>
        {item.assessment?<>
          <p className="mt-3 text-sm leading-6 text-ink">{item.note}</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2"><section className="rounded-lg bg-white/[0.03] p-4"><h4 className="text-xs font-semibold uppercase tracking-wider text-muted">Что видно до работы</h4><p className="mt-2 text-sm leading-6 text-ink-soft">{item.assessment.before_description}</p></section><section className="rounded-lg bg-white/[0.03] p-4"><h4 className="text-xs font-semibold uppercase tracking-wider text-muted">Что видно после работы</h4><p className="mt-2 text-sm leading-6 text-ink-soft">{item.assessment.after_description}</p></section></div>
          <Findings title="Видимые изменения" items={item.assessment.visible_changes} empty="Модель не смогла выделить подтверждаемые изменения."/>
          <Findings title="Замечания по доказательствам" items={item.assessment.concerns} empty="Отдельных замечаний модель не выделила. Это не подтверждает отсутствие дефектов."/>
          <Findings title="Что проверить или запросить" items={item.assessment.recommended_actions}/>

        </>:<p className="mt-3 text-sm leading-6 text-muted">{legacy?"Оценки CLIP не позволяют сделать подробное заключение о выполнении этого пункта.":item.note}</p>}
      </article>)}</div></details>
      <details className="mt-5 rounded-xl border border-line p-4"><summary className="cursor-pointer text-sm text-muted">Модель, версия и исходный результат</summary><p className="mt-3 break-all font-mono text-xs text-muted">{review.modelRef??"Модель не применялась"}</p><p className="mt-2 text-xs text-muted">{review.promptSetVersion} · {formatDateTime(review.createdAt)}{durationLabel?` · Время анализа: ${durationLabel} (${Math.round(resolvedElapsedMs!)} мс)`:""}</p>{review.errorCode&&<p className="mt-2 font-mono text-xs text-muted">{review.errorCode}</p>}{legacy&&review.items.map(item=><p key={item.id} className="mt-2 text-xs text-muted">{item.note}</p>)}<ul className="mt-3 list-disc space-y-1 pl-4 text-xs leading-5 text-muted">{review.limitations.map(text=><li key={text}>{text}</li>)}</ul></details>
    </>:<EmptyState title="Фотоанализ ещё не выполнен" description="Отправьте отчёт с фотографиями до и после. Анализ запустится автоматически после сдачи работы."/>}</div>
  </Card>;
}
