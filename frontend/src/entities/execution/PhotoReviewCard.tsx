import { useEffect, useState } from "react";
import "./photo-review.css";
import type { PhotoReview, PhotoReviewItem } from "@/shared/types/domain";
import { formatDurationMs } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { Card, CardBody, CardHeader } from "@/shared/ui/Card";
import { Icon } from "@/shared/ui/Icon";
import { EmptyState } from "@/shared/ui/States";
import { ReviewStatusBadge } from "@/shared/ui/StatusBadge";

const LEGACY_CLIP_RE = /(?:clip|demo-clean-pairs)/i;

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

function isLegacyClipReview(review: PhotoReview): boolean {
  return LEGACY_CLIP_RE.test(review.modelRef ?? "") || LEGACY_CLIP_RE.test(review.promptSetVersion ?? "");
}

function conciseSentences(text: string, maxSentences = 3): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  const parts = cleaned.split(/(?<=[.!?])\s+/).filter(Boolean);
  return parts.slice(0, maxSentences).join(" ");
}

function summarizeItem(item: PhotoReviewItem, legacyClip: boolean): string {
  if (item.verdict === "not_verifiable") {
    return "Этот пункт не проверяется по фотографии.";
  }
  if (legacyClip) {
    return "Сохранена прежняя проверка без текстового описания снимков.";
  }
  const assessment = item.assessment;
  const sentences: string[] = [];
  if (assessment?.summary) {
    sentences.push(conciseSentences(assessment.summary, 2));
  } else if (item.note) {
    sentences.push(conciseSentences(item.note, 2));
  }
  const extraConcern = assessment?.concerns?.find((c) => c && !sentences[0]?.includes(c));
  if (extraConcern && sentences.join(" ").split(/(?<=[.!?])\s+/).length < 3) {
    sentences.push(conciseSentences(extraConcern, 1));
  }
  if (!sentences.length) {
    return item.verdict === "visible_change"
      ? "На фотографиях видны изменения по пункту чек-листа."
      : "По приложенным фотографиям недостаточно данных для вывода.";
  }
  return conciseSentences(sentences.join(" "), 3);
}

function userSafeErrorMessage(errorCode?: string | null): string {
  if (errorCode === "AITUNNEL_NOT_CONFIGURED" || errorCode === "AITUNNEL_AUTH_FAILED") {
    return "Анализ фотографий не настроен на сервере. Проверьте снимки вручную.";
  }
  if (errorCode === "AITUNNEL_TIMEOUT" || errorCode === "TIMEOUT" || errorCode === "LOCAL_VISION_TIMEOUT") {
    return "Анализ не успел завершиться вовремя. Повторите попытку или проверьте снимки вручную.";
  }
  if (errorCode === "AITUNNEL_QUOTA_EXCEEDED" || errorCode === "AITUNNEL_RATE_LIMITED") {
    return "Сервис анализа временно перегружен. Повторите попытку позже.";
  }
  return "Не удалось выполнить анализ фотографий. Повторите попытку позже или проверьте снимки вручную.";
}

export function PhotoReviewCard({
  review,
  formatDateTime,
  fallbackElapsedMs,
}: {
  review: PhotoReview | null;
  formatDateTime: (value: string) => string;
  fallbackElapsedMs?: number | null;
}) {
  if (!review) {
    return (
      <Card>
        <CardHeader title="Анализ фотографий" />
        <CardBody>
          <EmptyState
            title="Анализ фотографий не выполнялся"
            description="Приложите фотографии или запустите анализ по отправленному отчёту. Проверьте фотографии самостоятельно."
          />
        </CardBody>
      </Card>
    );
  }

  const legacyClip = isLegacyClipReview(review);
  const measuredMs = review.elapsedMs ?? fallbackElapsedMs ?? null;
  const durationLabel = measuredMs !== null && measuredMs > 0 ? formatDurationMs(measuredMs) : null;
  const timeText = durationLabel ? `Время анализа: ${durationLabel}` : null;
  const failed = review.status === "failed" || review.status === "unavailable";

  return (
    <Card>
      <CardHeader
        title="Анализ фотографий"
        description={[formatDateTime(review.createdAt), timeText, legacyClip ? "Прежний тип проверки" : null]
          .filter(Boolean)
          .join(" · ")}
        action={<ReviewStatusBadge status={review.status} />}
      />
      <CardBody>
        <div className="space-y-3">
          {failed ? (
            <p className="text-sm text-ink-soft">{userSafeErrorMessage(review.errorCode)}</p>
          ) : (
            review.items.map((item) => (
              <div key={item.id} className="space-y-1.5 rounded-xl border border-line p-3.5">
                <p className="text-sm font-semibold text-ink">{item.label}</p>
                <p className="text-sm leading-6 text-ink-soft">{summarizeItem(item, legacyClip)}</p>
              </div>
            ))
          )}
          {legacyClip && !failed && (
            <p className="text-xs text-muted">
              Этот результат сохранён до обновления анализа фотографий; при необходимости запустите свежую проверку.
            </p>
          )}
          <p className="border-t border-line pt-2 text-xs font-medium text-muted">
            Проверьте фотографии самостоятельно
          </p>
        </div>
      </CardBody>
    </Card>
  );
}
