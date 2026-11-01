"""ALG04: deterministic policy; evidence and deadline outrank model preference."""
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.maintenance import OrchestrationDecision

POLICY_VERSION = "maintenance-orchestrator-v1"


def decide(snapshot, algorithmic, ai):
    today = snapshot.as_of.astimezone(ZoneInfo(snapshot.site.timezone)).date()
    def result(status, day, reason):
        return OrchestrationDecision(schema_version=snapshot.schema_version, data_origin=snapshot.data_origin,
            orchestration_id=uuid4(), run_id=algorithmic.run_id, snapshot_id=snapshot.snapshot_id,
            algorithmic_result_id=algorithmic.result_id, ai_result_id=ai.result_id,
            status=status, selected_date=day, policy_version=POLICY_VERSION, reasons=[reason],
            created_at=datetime.now(timezone.utc))
    for value, method in ((algorithmic, "algorithmic"), (ai, "ai")):
        if (value.method != method or value.snapshot_id != snapshot.snapshot_id
                or value.snapshot_sha256 != snapshot.content_sha256 or value.binding_id != snapshot.binding_id
                or value.equipment_id != snapshot.equipment.equipment_id or value.as_of != snapshot.as_of
                or value.data_origin != snapshot.data_origin or value.mandatory_due_date != snapshot.mandatory_due_date
                or value.run_id != algorithmic.run_id):
            return result("manual_review", None, "SNAPSHOT_MISMATCH: результаты относятся к разным входам; требуется проверка.")
    due, earliest = snapshot.mandatory_due_date, snapshot.earliest_date
    if due is None or not snapshot.rule.confirmed or algorithmic.status != "ok":
        return result("needs_input", None, "RULE_INPUT_REQUIRED: нет подтверждённого алгоритмического срока.")
    if due < today:
        return result("manual_review", None, "DEADLINE_EXCEEDED: срок прошёл; автоматический перенос запрещён.")
    day = algorithmic.recommended_date
    if day > due or day < today or (earliest and day < earliest):
        return result("manual_review", None, "INVALID_RULE_DATE: алгоритмический срок вне допустимого окна.")
    if ai.status != "ok":
        return result("fallback", day, f"AI_UNAVAILABLE: {ai.error_code}; используем подтверждённый регламент.")
    candidate = ai.recommended_date
    if candidate > due:
        return result("fallback", day, "AI_AFTER_DEADLINE: предложение AI позже обязательного срока; используем регламент.")
    if candidate < today or (earliest and candidate < earliest):
        return result("fallback", day, "AI_BEFORE_WINDOW: предложение AI вне допустимого окна; используем регламент.")
    if candidate >= day:
        return result("selected", day, "RULE_EARLIER_OR_EQUAL: регламентный срок не позже предложения AI.")
    evidence = ai.uncertainty
    supported = (evidence.calibrated and evidence.lower_date is not None and evidence.upper_date is not None
                 and evidence.lower_date <= candidate <= evidence.upper_date < day)
    demo = snapshot.data_origin == "synthetic_demo" and evidence.kind != "unknown"
    if supported or demo:
        reason = ("AI_EARLY_EVIDENCE: подтверждённый интервал модели указывает на более раннее обслуживание."
                  if supported else "DEMO_EARLY_DATE: более ранняя дата разрешена только в синтетическом сценарии; точность на заказчике не установлена.")
        return result("selected", candidate, reason)
    return result("fallback", day, "AI_EARLY_UNSUPPORTED: для раннего обслуживания нет подтверждённой оценки риска; используем регламент.")
