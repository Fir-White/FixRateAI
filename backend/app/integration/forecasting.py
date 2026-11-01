"""Server snapshots and persistence for independent ALG04 forecasts."""
from datetime import datetime, time, timedelta, timezone
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError

from app.orchestrator import compare_forecasts
from app.schemas.maintenance import ForecastSnapshot
from app.scheduling.schemas import SchedulingBinding
from .calendar import _binding_payload, _json_value
from .ml import forecast_view, version


def binding_input(v, binding, *, as_of=None):
    site = v.one("sites", site_id=v.principal.site_id)
    payload, code, message = _binding_payload(v, binding, binding.rule, binding.equipment, site)
    if payload is None:
        raise HTTPException(422, f"{code}: {message}")
    payload["rule"]["confirmed"] = binding.rule.publication_status == "published" and binding.rule.edition.is_approved
    payload["operation"]["status"] = "approved" if payload["rule"]["confirmed"] and binding.rule.operation.is_active else "draft"
    now = as_of or datetime.now(timezone.utc)
    payload["accepted_events"] = [e for e in payload["accepted_events"] if e["performed_at"] <= e["accepted_at"] <= now]
    try:
        return SchedulingBinding.model_validate_json(json.dumps(payload, default=_json_value))
    except ValidationError:
        raise HTTPException(422, "INVALID_PERSISTED_INPUT: проверьте правило, сроки и ресурсы операции") from None


def make_snapshot(v, item, earliest, due, *, as_of=None, snapshot_id=None):
    from ml_service.app.forecast.synthetic import compute_snapshot_hash
    now = as_of or datetime.now(timezone.utc)
    site = v.one("sites", site_id=v.principal.site_id)
    origin = item.equipment.data_origin
    payload = dict(schema_version="maintenance-0.1", data_origin=origin, snapshot_id=snapshot_id or uuid4(), content_sha256="0"*64,
        binding_id=item.binding.binding_id, binding_revision=item.binding.revision,
        site=dict(schema_version="maintenance-0.1", data_origin=origin, site_id=site.site_id, name=site.name,
                  address=site.address or "Адрес не указан", timezone=site.timezone), equipment=item.equipment.model_dump(),
        operation=item.operation.model_dump(), rule=item.rule.model_dump(), as_of=now,
        horizon_end=max(due or now.date(), now.astimezone(ZoneInfo(site.timezone)).date())+timedelta(days=366),
        earliest_date=earliest, mandatory_due_date=due, runtime_due_at_hours=None, accepted_events=[e.model_dump() for e in item.accepted_events],
        runtime_reading=None, feature_schema_version="rf-features-v1")
    try:
        snapshot = ForecastSnapshot.model_validate_json(json.dumps(payload, default=_json_value))
    except ValidationError:
        raise HTTPException(422, "INVALID_PERSISTED_INPUT: снимок прогноза противоречит контракту") from None
    return snapshot.model_copy(update={"content_sha256": compute_snapshot_hash(json.loads(snapshot.model_dump_json()))})


def task_snapshot(v, order, *, as_of=None, snapshot_id=None):
    if not order.schedule_entry_id:
        raise HTTPException(422, "MISSING_OCCURRENCE: у задания нет календарного вхождения")
    entry = v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id)
    if not entry.binding_id:
        raise HTTPException(422, "MISSING_BINDING")
    binding = v.one("rule_equipment", binding_id=entry.binding_id)
    item = binding_input(v, binding, as_of=as_of)
    if order.operation_snapshot.get("data_origin", item.equipment.data_origin) != item.equipment.data_origin:
        raise HTTPException(422, "DATA_ORIGIN_MISMATCH: происхождение задания и оборудования различается")
    frozen_version = order.operation_snapshot.get("operation_version")
    if frozen_version is not None and frozen_version != item.operation.version:
        raise HTTPException(409, "OPERATION_VERSION_CHANGED: требуется сверка задания с регламентом")
    if entry.rule_snapshot.get("operation") and entry.rule_snapshot["operation"] != json.loads(item.operation.model_dump_json()):
        raise HTTPException(409, "OPERATION_SNAPSHOT_CHANGED: параметры сохранённого задания и регламента расходятся")
    due = entry.regulatory_deadline_on
    earliest = max(item.binding.effective_from, item.equipment.commissioned_on or item.binding.effective_from,
        due-timedelta(days=item.rule.allowed_lead_days), entry.earliest_date or item.binding.effective_from)
    snapshot = make_snapshot(v, item, earliest, due, as_of=as_of, snapshot_id=snapshot_id)
    return snapshot, item, entry


def calculate(snapshot, item, forecaster, *, timeout_seconds=2, provider=None):
    from ml_service.app.forecast.client import predict_maintenance_ai
    chosen = provider or (lambda value: predict_maintenance_ai(value, forecaster=forecaster, use_active_model=False))
    return compare_forecasts(snapshot, item, chosen, timeout_seconds=timeout_seconds)


def persist_comparison(v, snapshot, algorithmic, ai, decision, *, system_id, deadline_at, condition=None):
    saved = []
    for result, kind in ((algorithmic, "rule"), (ai, "ai")):
        predictor = version(v, kind, result.method_version, result.model_ref or result.method_version, result.model_ref)
        saved.append(v.repo.add("forecast_runs", forecast_run_id=result.result_id, site_id=v.principal.site_id,
            system_id=system_id, maintenance_rule_id=snapshot.rule.rule_version_id, equipment_id=snapshot.equipment.equipment_id,
            predictor_version_id=predictor.predictor_version_id, method=kind,
            status={"needs_input": "insufficient_data"}.get(result.status, result.status), input_snapshot=json.loads(snapshot.model_dump_json()),
            proposal_at=datetime.combine(result.recommended_date, time.min, ZoneInfo(snapshot.site.timezone)) if result.recommended_date else None,
            regulatory_deadline_at=deadline_at, rationale=result.explanation,
            output_snapshot={"canonical": json.loads(result.model_dump_json()), "condition": condition if kind == "ai" else None}))
    ui = dict(runId=str(decision.run_id), snapshotId=str(snapshot.snapshot_id), snapshotHash=snapshot.content_sha256,
        asOf=snapshot.as_of.isoformat(), horizonEnd=str(snapshot.horizon_end), earliestDate=str(snapshot.earliest_date) if snapshot.earliest_date else None,
        mandatoryDueDate=str(snapshot.mandatory_due_date) if snapshot.mandatory_due_date else None,
        equipmentId=str(snapshot.equipment.equipment_id), equipmentName=snapshot.equipment.name,
        operationTitle=snapshot.operation.title, dataOrigin=snapshot.data_origin, createdAt=decision.created_at.isoformat(),
        algorithmic=forecast_view(algorithmic), ai=forecast_view(ai), decision=dict(orchestrationId=str(decision.orchestration_id),
            status=decision.status, selectedDate=str(decision.selected_date) if decision.selected_date else None,
            policyVersion=decision.policy_version, reasons=decision.reasons))
    policy = version(v, "orchestrator", "maintenance", decision.policy_version)
    selected_method = ("manual_review" if decision.selected_date is None else "conservative_fallback" if decision.status == "fallback"
                       else "ai" if ai.status == "ok" and decision.selected_date == ai.recommended_date and ai.recommended_date < algorithmic.recommended_date else "rule")
    row = v.repo.add("orchestration_decisions", orchestration_decision_id=decision.orchestration_id,
        site_id=v.principal.site_id, system_id=system_id, maintenance_rule_id=snapshot.rule.rule_version_id,
        rule_forecast_id=saved[0].forecast_run_id, ai_forecast_id=saved[1].forecast_run_id,
        orchestrator_version_id=policy.predictor_version_id, selected_method=selected_method,
        selected_at=datetime.combine(decision.selected_date, time.min, ZoneInfo(snapshot.site.timezone)) if decision.selected_date else None,
        regulatory_deadline_at=deadline_at, reason="; ".join(decision.reasons), comparison_snapshot={"ui": ui, "canonical": json.loads(decision.model_dump_json())})
    return ui, row


def forecast_task(v, task_id, revision, forecaster):
    from ml_service.app.forecast.backend_adapter import predict_condition_for_snapshot
    order = v.task(task_id)
    if order.revision != revision:
        raise HTTPException(409, "REVISION_CONFLICT: обновите данные")
    snapshot, item, entry = task_snapshot(v, order)
    values = calculate(snapshot, item, forecaster)
    condition = predict_condition_for_snapshot(snapshot)
    v.session.expire_all()
    order = v.task(task_id, lock=True)
    if order.revision != revision:
        raise HTTPException(409, "REVISION_CONFLICT: задание изменилось во время расчёта")
    current, _, entry = task_snapshot(v, order, as_of=snapshot.as_of, snapshot_id=snapshot.snapshot_id)
    if current.content_sha256 != snapshot.content_sha256:
        raise HTTPException(409, "STALE_SNAPSHOT: исходные данные изменились; повторите расчёт")
    ui, _ = persist_comparison(v, snapshot, *values, system_id=order.system_id, deadline_at=entry.regulatory_deadline_at,
                               condition=json.loads(condition.model_dump_json()))
    v.session.commit()
    return {"run": ui}
