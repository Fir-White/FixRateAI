import { Badge, type BadgeTone } from "@/shared/ui/Badge";
import type {
  EquipmentState,
  ForecastStatus,
  OrchestrationDecision,
  PhotoReviewStatus,
  PhotoVerdict,
  TaskState,
} from "@/shared/types/domain";

const TASK_LABELS: Record<TaskState, string> = {
  draft: "Черновик",
  assigned: "Назначено",
  in_progress: "В работе",
  submitted: "На проверке",
  rework_required: "На доработке",
  accepted: "Принято",
  cancelled: "Отменено",
};

const TASK_TONES: Record<TaskState, BadgeTone> = {
  draft: "neutral",
  assigned: "info",
  in_progress: "violet",
  submitted: "warning",
  rework_required: "danger",
  accepted: "success",
  cancelled: "neutral",
};

const EQUIPMENT_LABELS: Record<EquipmentState, string> = {
  active: "В эксплуатации",
  out_of_service: "Выведено из эксплуатации",
  retired: "Списано",
};

const EQUIPMENT_TONES: Record<EquipmentState, BadgeTone> = {
  active: "success",
  out_of_service: "warning",
  retired: "neutral",
};

const FORECAST_LABELS: Record<ForecastStatus, string> = {
  ok: "Результат получен",
  needs_input: "Нужны данные",
  unavailable: "Недоступно",
  failed: "Ошибка расчёта",
};

const FORECAST_TONES: Record<ForecastStatus, BadgeTone> = {
  ok: "success",
  needs_input: "warning",
  unavailable: "danger",
  failed: "danger",
};

const DECISION_LABELS: Record<OrchestrationDecision["status"], string> = {
  selected: "Дата выбрана",
  fallback: "Fallback",
  needs_input: "Нужны данные",
  manual_review: "Ручной разбор",
};

const DECISION_TONES: Record<OrchestrationDecision["status"], BadgeTone> = {
  selected: "success",
  fallback: "info",
  needs_input: "warning",
  manual_review: "danger",
};

const REVIEW_LABELS: Record<PhotoReviewStatus, string> = {
  completed: "Анализ выполнен",
  uncertain: "Неуверенный результат",
  not_verifiable: "Не проверяется по фото",
  unavailable: "AI недоступен",
  failed: "Ошибка AI",
};

const REVIEW_TONES: Record<PhotoReviewStatus, BadgeTone> = {
  completed: "success",
  uncertain: "warning",
  not_verifiable: "info",
  unavailable: "danger",
  failed: "danger",
};

const VERDICT_LABELS: Record<PhotoVerdict, string> = {
  visible_change: "Видимое изменение",
  no_visible_change: "Без видимого изменения",
  uncertain: "Неуверенно",
  not_verifiable: "Не проверяется",
};

const VERDICT_TONES: Record<PhotoVerdict, BadgeTone> = {
  visible_change: "success",
  no_visible_change: "warning",
  uncertain: "warning",
  not_verifiable: "info",
};

export function TaskStateBadge({ state }: { state: TaskState }) {
  return <Badge tone={TASK_TONES[state]}>{TASK_LABELS[state]}</Badge>;
}

export function EquipmentStateBadge({ state }: { state: EquipmentState }) {
  return <Badge tone={EQUIPMENT_TONES[state]}>{EQUIPMENT_LABELS[state]}</Badge>;
}

export function ForecastStatusBadge({ status }: { status: ForecastStatus }) {
  return <Badge tone={FORECAST_TONES[status]}>{FORECAST_LABELS[status]}</Badge>;
}

export function DecisionStatusBadge({
  status,
}: {
  status: OrchestrationDecision["status"];
}) {
  return <Badge tone={DECISION_TONES[status]}>{DECISION_LABELS[status]}</Badge>;
}

export function ReviewStatusBadge({ status }: { status: PhotoReviewStatus }) {
  return <Badge tone={REVIEW_TONES[status]}>{REVIEW_LABELS[status]}</Badge>;
}

export function VerdictBadge({ verdict }: { verdict: PhotoVerdict }) {
  return <Badge tone={VERDICT_TONES[verdict]}>{VERDICT_LABELS[verdict]}</Badge>;
}

export function EngineerDecisionBadge({
  verdict,
}: {
  verdict: "accepted" | "rejected";
}) {
  return verdict === "accepted" ? (
    <Badge tone="success">Принято</Badge>
  ) : (
    <Badge tone="danger">Отклонено</Badge>
  );
}

export function OverdueBadge() {
  return <Badge tone="danger">Просрочено</Badge>;
}

export function OriginBadge({
  origin,
}: {
  origin: "customer" | "synthetic_demo" | null;
}) {
  if (!origin) return <Badge tone="neutral">Источник не указан</Badge>;
  return origin === "customer" ? (
    <Badge tone="info">Данные заказчика</Badge>
  ) : (
    <Badge tone="violet">synthetic_demo</Badge>
  );
}
