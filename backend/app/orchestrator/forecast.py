"""Independent ALG02 forecast and bounded, validated provider execution (ALG08)."""
from datetime import timezone
import json
import logging
import math
import time as timer
from queue import Queue, Empty
from threading import BoundedSemaphore, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.maintenance import ForecastResult, Uncertainty
from app.scheduling import CalendarGenerationRequest, generate_month
from app.scheduling.generator import METHOD_VERSION
from .decision import decide

logger = logging.getLogger(__name__)
_slots = BoundedSemaphore(2)


def forecast_result(snapshot, run_id, method, *, status, day=None, error=None, explanation, warnings=None, model_ref=None):
    today = snapshot.as_of.astimezone(ZoneInfo(snapshot.site.timezone)).date()
    return ForecastResult(schema_version=snapshot.schema_version, data_origin=snapshot.data_origin,
        result_id=uuid4(), run_id=run_id, snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.content_sha256, equipment_id=snapshot.equipment.equipment_id,
        binding_id=snapshot.binding_id, as_of=snapshot.as_of, method=method,
        method_version=METHOD_VERSION if method == "algorithmic" else "bounded-ai-v1", model_ref=model_ref,
        status=status, recommended_date=day, mandatory_due_date=snapshot.mandatory_due_date,
        runtime_due_at_hours=snapshot.runtime_due_at_hours,
        overdue=bool(snapshot.mandatory_due_date and snapshot.mandatory_due_date < today),
        uncertainty=Uncertainty(kind="deterministic" if method == "algorithmic" else "unknown",
            lower_date=None, upper_date=None, calibrated=False, note="Расчёт по регламенту" if method == "algorithmic" else "Оценка модели недоступна"),
        explanation=explanation, warnings=warnings or [], error_code=error, elapsed_ms=0)


def algorithmic_forecast(snapshot, binding, run_id):
    due = snapshot.mandatory_due_date
    if due is None:
        return forecast_result(snapshot, run_id, "algorithmic", status="needs_input", error="MISSING_DEADLINE", explanation="Не задан обязательный срок.")
    if (binding.binding.binding_id != snapshot.binding_id or binding.binding.revision != snapshot.binding_revision
            or binding.rule != snapshot.rule or binding.operation != snapshot.operation
            or binding.equipment != snapshot.equipment or binding.accepted_events != snapshot.accepted_events):
        return forecast_result(snapshot, run_id, "algorithmic", status="failed", error="BINDING_MISMATCH", explanation="Правило и снимок расходятся.")
    request = CalendarGenerationRequest(schema_version=snapshot.schema_version,
        site=snapshot.site, query=dict(site_id=snapshot.site.site_id, year=due.year, month=due.month, include_cancelled=False),
        as_of=snapshot.as_of, bindings=[binding])
    generated = generate_month(request).bindings[0]
    occurrence = next((item for item in generated.occurrences if item.occurrence.mandatory_due_date == due), None)
    if occurrence is None or generated.status not in ("ok", "manual_review"):
        return forecast_result(snapshot, run_id, "algorithmic", status="needs_input",
            error=generated.error_code or "OCCURRENCE_NOT_IN_RULE", explanation=generated.explanation, warnings=generated.warnings)
    return forecast_result(snapshot, run_id, "algorithmic", status="ok", day=occurrence.occurrence.occurrence_date,
        explanation=occurrence.explanation, warnings=generated.warnings)


def bounded_ai(snapshot, run_id, provider, *, timeout_seconds=2):
    started = timer.monotonic()
    def failed(code, status="unavailable"):
        logger.warning("forecast_provider_rejected run=%s snapshot=%s code=%s", run_id, snapshot.snapshot_id, code)
        result = forecast_result(snapshot, run_id, "ai", status=status, error=code,
            explanation="AI не дал пригодный результат. Планирование продолжится по подтверждённому регламенту.")
        return result.model_copy(update={"elapsed_ms": int((timer.monotonic()-started)*1000)})
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        return failed("REQUEST_BUDGET_EXHAUSTED")
    slots = _slots
    if not slots.acquire(blocking=False):
        return failed("AI_BUSY")
    output = Queue(maxsize=1)
    def invoke():
        try:
            output.put((True, provider(snapshot.model_copy(deep=True))))
        except BaseException:
            output.put((False, None))
        finally:
            slots.release()
    # At most two daemon workers can outlive their deadline; no DB session is shared.
    try:
        Thread(target=invoke, daemon=True, name="maintenance-ai").start()
    except Exception:
        slots.release()
        return failed("PROVIDER_ERROR", "failed")
    try:
        ok, raw = output.get(timeout=min(timeout_seconds, 5))
    except Empty:
        return failed("TIMEOUT")
    if not ok:
        return failed("PROVIDER_ERROR", "failed")
    try:
        value = ForecastResult.model_validate_json(raw if isinstance(raw, str) else raw.model_dump_json() if isinstance(raw, ForecastResult) else json.dumps(raw))
        if (value.method != "ai" or value.snapshot_id != snapshot.snapshot_id or value.snapshot_sha256 != snapshot.content_sha256
                or value.binding_id != snapshot.binding_id or value.equipment_id != snapshot.equipment.equipment_id
                or value.as_of.astimezone(timezone.utc) != snapshot.as_of.astimezone(timezone.utc)
                or value.data_origin != snapshot.data_origin or value.mandatory_due_date != snapshot.mandatory_due_date):
            return failed("AI_SNAPSHOT_MISMATCH", "failed")
        return value.model_copy(update={"run_id": run_id, "result_id": uuid4()})
    except (ValueError, TypeError, AttributeError):
        return failed("INVALID_AI_JSON", "failed")


def compare_forecasts(snapshot, binding, provider, *, timeout_seconds=2):
    from ml_service.app.forecast.synthetic import compute_snapshot_hash
    if compute_snapshot_hash(json.loads(snapshot.model_dump_json())) != snapshot.content_sha256:
        raise ValueError("snapshot content hash does not match")
    run_id = uuid4()
    algorithmic = algorithmic_forecast(snapshot, binding, run_id)
    ai = bounded_ai(snapshot, run_id, provider, timeout_seconds=timeout_seconds)
    return algorithmic, ai, decide(snapshot, algorithmic, ai)
