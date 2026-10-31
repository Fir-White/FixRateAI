"""Build immutable ML inputs from persisted, site-scoped execution facts."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import io
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.maintenance import ForecastSnapshot, ForecastResult, PhotoReviewRequest
from ml_service.app.forecast.synthetic import compute_snapshot_hash


class MLCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0)
    comparability_confirmed: bool = False


def version(v, kind, name, version_name, artifact=None):
    cls = v.models["predictor_versions"]
    from sqlalchemy import select
    obj = v.session.scalar(select(cls).where(cls.kind == kind, cls.name == name, cls.version == version_name))
    return obj or v.repo.add("predictor_versions", kind=kind, name=name, version=version_name, artifact_ref=artifact)


def operation_payload(order, rule, checklist):
    if not rule or not checklist:
        raise HTTPException(422, "MISSING_OPERATION: требуется правило и сохранённый чек-лист")
    origin = order.operation_snapshot.get("data_origin") or rule.data_origin
    kind = order.operation_snapshot.get("maintenance_type")
    if not kind:
        raise HTTPException(422, "MISSING_MAINTENANCE_TYPE")
    return dict(schema_version="maintenance-0.1", data_origin=origin,
        operation_id=str(rule.operation_template_id), operation_version_id=str(rule.maintenance_rule_id),
        version=rule.rule_version, code=order.operation_snapshot.get("code", rule.operation.code),
        title=order.operation_snapshot.get("title", rule.operation.title), maintenance_type=kind,
        instructions=rule.operation.description or rule.operation.title,
        crew_size=order.required_people_snapshot, raw_norm_value=str(order.norm_hours_snapshot),
        norm_unit={"total_person_hours": "person_hour"}.get(order.norm_hours_basis_snapshot, "unconfirmed"),
        planning_duration_minutes=None, duration_basis=None, qualification_ids=[],
        checklist=[dict(checklist_item_id=i["id"], text=i["text"], answer_kind=i["answerKind"], unit=i["unit"],
                        required=i["required"], visual_verifiability=i["visualVerifiability"], photo_required=i["photoRequired"])
                   for i in checklist], status="approved" if rule.publication_status == "published" else "draft",
        source_ref=rule.source_ref)


def build_snapshot(v, order):
    rule, _, _, _ = v.operation(order)
    if not order.schedule_entry_id:
        raise HTTPException(422, "MISSING_OCCURRENCE: у задания нет календарного вхождения")
    entry = v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id)
    if not entry.binding_id:
        raise HTTPException(422, "MISSING_BINDING")
    binding = v.one("rule_equipment", binding_id=entry.binding_id)
    equipment = v.one("equipment", equipment_id=binding.equipment_id)
    if equipment.equipment_type_id is None:
        raise HTTPException(422, "MISSING_EQUIPMENT_TYPE")
    site = v.one("sites", site_id=order.site_id)
    op = operation_payload(order, rule, order.operation_snapshot.get("checklist"))
    origin = op["data_origin"]
    now = datetime.now(timezone.utc)
    local_day = now.astimezone(ZoneInfo(site.timezone)).date()
    confirmed = (rule.publication_status == "published" and rule.edition.is_approved
                 and rule.scheduling_mode == "fixed_interval" and rule.occurrences_per_period == 1
                 and bool(rule.schedule_parameters.get("anchor_date")) and rule.period_unit in ("day", "month")
                 and rule.schedule_parameters.get("basis") in ("fixed_calendar", "after_accepted_completion"))
    history = []
    # Evidence must be accepted, before the cutoff and from the same operation and origin.
    for link in v.rows("work_order_equipment", equipment_id=equipment.equipment_id):
        past = v.one("work_orders", work_order_id=link.work_order_id)
        if not past.maintenance_rule_id or not past.completed_at:
            continue
        past_rule = v.one("maintenance_rules", maintenance_rule_id=past.maintenance_rule_id)
        past_origin = past.operation_snapshot.get("data_origin") or past_rule.data_origin
        if past_rule.operation_template_id != rule.operation_template_id or past_origin != origin:
            continue
        for review in v.rows("acceptance_reviews", work_order_id=past.work_order_id):
            if review.decision == "accepted" and past.completed_at <= review.reviewed_at <= now:
                history.append(dict(service_event_id=str(review.acceptance_review_id), performed_at=past.completed_at.isoformat(),
                    accepted_at=review.reviewed_at.isoformat(), runtime_hours=None, observed_need_date=None))
    payload = dict(schema_version="maintenance-0.1", data_origin=origin, snapshot_id=str(uuid4()), content_sha256="0"*64,
        binding_id=str(binding.binding_id), binding_revision=binding.revision,
        site=dict(schema_version="maintenance-0.1", data_origin=origin, site_id=str(site.site_id), name=site.name,
                  address=site.address or "Адрес не указан", timezone=site.timezone),
        equipment=dict(schema_version="maintenance-0.1", data_origin=origin, equipment_id=str(equipment.equipment_id),
            site_id=str(site.site_id), equipment_type_id=str(equipment.equipment_type_id), inventory_code=equipment.asset_code,
            name=equipment.name, commissioned_on=equipment.commissioned_on.isoformat() if equipment.commissioned_on else None,
            state={"under_repair": "out_of_service"}.get(equipment.status, equipment.status), revision=equipment.revision),
        operation=op,
        rule=dict(schema_version="maintenance-0.1", data_origin=origin, rule_version_id=str(rule.maintenance_rule_id),
            regulation_version_id=str(rule.regulation_edition_id), source_text=rule.source_text, kind="calendar_interval",
            confirmed=confirmed, interval=rule.period_count if rule.period_unit in ("day", "month") else None,
            calendar_unit=rule.period_unit if rule.period_unit in ("day", "month") else None,
            anchor_date=rule.schedule_parameters.get("anchor_date"), basis=rule.schedule_parameters.get("basis"),
            explicit_dates=[], yearly_count=None, runtime_interval_hours=None, allowed_lead_days=0, source_ref=rule.source_ref),
        as_of=now.isoformat(), horizon_end=(local_day+timedelta(days=366)).isoformat(),
        earliest_date=entry.earliest_date.isoformat() if entry.earliest_date else None,
        mandatory_due_date=entry.regulatory_deadline_on.isoformat(), runtime_due_at_hours=None,
        accepted_events=history, runtime_reading=None, feature_schema_version="rf-features-v1")
    from pydantic import ValidationError
    try:
        snapshot = ForecastSnapshot.model_validate_json(json.dumps(payload))
    except ValidationError:
        raise HTTPException(422, "INVALID_PERSISTED_INPUT: данные БД не соответствуют контракту прогноза") from None
    # Hash the normalized canonical JSON, matching the standalone ML boundary.
    normalized = json.loads(snapshot.model_dump_json())
    return snapshot.model_copy(update={"content_sha256": compute_snapshot_hash(normalized)}), entry, confirmed


def forecast_view(result):
    return dict(resultId=str(result.result_id), method=result.method, methodVersion=result.method_version,
                modelRef=result.model_ref, status=result.status, recommendedDate=str(result.recommended_date) if result.recommended_date else None,
                mandatoryDueDate=str(result.mandatory_due_date) if result.mandatory_due_date else None,
                overdue=result.overdue, uncertaintyKind=result.uncertainty.kind, uncertaintyNote=result.uncertainty.note,
                explanation=result.explanation, warnings=result.warnings, errorCode=result.error_code, elapsedMs=result.elapsed_ms)


def register_ml_routes(app, views, photo_path, require_role, check_revision):
    # Imported lazily by create_app; the ML namespace never shadows backend app.
    from ml_service.app.forecast.client import predict_maintenance_ai
    from ml_service.app.forecast.backend_adapter import predict_condition_for_snapshot
    from ml_service.app.cv.api import invoke_review

    @app.post("/api/v1/maintenance/tasks/{task_id}/forecast")
    def forecast(task_id: UUID, command: MLCommand, v=Depends(views)):
        require_role(v.principal, "dispatcher", "engineer")
        order = v.task(task_id, lock=True)
        check_revision(order, command.expected_revision)
        snapshot, entry, confirmed = build_snapshot(v, order)
        run_id = uuid4()
        ai = predict_maintenance_ai(snapshot, forecaster=app.state.forecaster,
                                    use_active_model=False).model_copy(update={"run_id": run_id})
        condition = predict_condition_for_snapshot(snapshot)
        algo_payload = json.loads(ai.model_dump_json())
        algo_payload.update(result_id=str(uuid4()), method="algorithmic", method_version="persisted-calendar-v1",
            model_ref=None, status="ok" if confirmed else "needs_input", recommended_date=str(entry.planned_date) if confirmed else None,
            error_code=None if confirmed else "UNCONFIRMED_RULE", warnings=[] if confirmed else ["UNCONFIRMED_RULE"],
            explanation="Дата из сохранённого календарного вхождения; генератор календаря не реализован." if confirmed else "Правило или редакция не подтверждены; дата не назначается автоматически.",
            uncertainty=dict(kind="deterministic", lower_date=None, upper_date=None, calibrated=False, note="Сохранённый календарь, не оценка вероятности"))
        algo = ForecastResult.model_validate_json(json.dumps(algo_payload))
        reasons = []
        selected = None
        status = "needs_input"
        if algo.status == "ok":
            selected, status = algo.recommended_date, "fallback"
            if ai.status == "ok":
                candidate = ai.recommended_date
                if candidate > snapshot.mandatory_due_date:
                    reasons.append("AI_AFTER_DEADLINE")
                elif snapshot.earliest_date and candidate < snapshot.earliest_date:
                    reasons.append("AI_BEFORE_WINDOW")
                    selected = min(selected, snapshot.earliest_date)
                else:
                    selected, status = min(selected, candidate), "selected"
                    reasons.append("EARLIEST_VALID_DATE")
            else:
                reasons.append("AI_UNAVAILABLE")
        else:
            reasons.append("UNCONFIRMED_RULE")
        saved = []
        for result, sql_method in ((algo, "rule"), (ai, "ai")):
            predictor = version(v, sql_method, result.method_version, result.model_ref or result.method_version, result.model_ref)
            row = v.repo.add("forecast_runs", forecast_run_id=result.result_id, site_id=v.principal.site_id, system_id=order.system_id,
                maintenance_rule_id=order.maintenance_rule_id, equipment_id=snapshot.equipment.equipment_id,
                predictor_version_id=predictor.predictor_version_id, method=sql_method,
                status={"needs_input": "insufficient_data"}.get(result.status, result.status),
                input_snapshot=json.loads(snapshot.model_dump_json()),
                proposal_at=datetime.combine(result.recommended_date, time.min, ZoneInfo(snapshot.site.timezone)) if result.recommended_date else None,
                regulatory_deadline_at=entry.regulatory_deadline_at, rationale=result.explanation,
                output_snapshot={"canonical": json.loads(result.model_dump_json()), "condition": json.loads(condition.model_dump_json()) if sql_method == "ai" else None})
            saved.append(row)
        decision_id = uuid4()
        ui = dict(runId=str(run_id), snapshotId=str(snapshot.snapshot_id), snapshotHash=snapshot.content_sha256,
            asOf=snapshot.as_of.isoformat(), horizonEnd=str(snapshot.horizon_end),
            earliestDate=str(snapshot.earliest_date) if snapshot.earliest_date else None, mandatoryDueDate=str(snapshot.mandatory_due_date),
            equipmentId=str(snapshot.equipment.equipment_id), equipmentName=snapshot.equipment.name,
            operationTitle=snapshot.operation.title, dataOrigin=snapshot.data_origin, createdAt=datetime.now(timezone.utc).isoformat(),
            algorithmic=forecast_view(algo), ai=forecast_view(ai), decision=dict(orchestrationId=str(decision_id), status=status,
                selectedDate=str(selected) if selected else None, policyVersion="persisted-calendar-v1", reasons=reasons))
        orchestrator = version(v, "orchestrator", "integration", "persisted-calendar-v1")
        v.repo.add("orchestration_decisions", orchestration_decision_id=decision_id, site_id=v.principal.site_id,
            system_id=order.system_id, maintenance_rule_id=order.maintenance_rule_id, rule_forecast_id=saved[0].forecast_run_id,
            ai_forecast_id=saved[1].forecast_run_id, orchestrator_version_id=orchestrator.predictor_version_id,
            selected_method="manual_review" if selected is None else "rule" if status == "selected" else "conservative_fallback",
            selected_at=datetime.combine(selected, time.min, ZoneInfo(snapshot.site.timezone)) if selected else None,
            regulatory_deadline_at=entry.regulatory_deadline_at, reason="; ".join(reasons), comparison_snapshot={"ui": ui})
        v.session.commit()
        return {"run": ui}

    @app.post("/api/v1/maintenance/tasks/{task_id}/photo-review")
    def photo_review(task_id: UUID, command: MLCommand, v=Depends(views)):
        require_role(v.principal, "engineer")
        order = v.task(task_id, lock=True)
        check_revision(order, command.expected_revision)
        reports = v.rows("work_reports", work_order_id=task_id)
        report = max(reports, key=lambda r: r.revision_no) if reports else None
        if not report or report.status != "submitted" or order.status != "in_review":
            raise HTTPException(409, "Фотоанализ требует замороженную отправленную попытку")
        rule, _, _, _ = v.operation(order)
        op = operation_payload(order, rule, report.checklist_snapshot)
        rows = [p for p in v.rows("evidence_files", work_report_id=report.work_report_id)
                if p.stage in ("before", "after") and p.checklist_item_id and p.equipment_id and p.view_key]
        if len(rows) < 2:
            raise HTTPException(422, "Недостаточно фото с привязками для анализа")
        payload_photos = []
        blobs = {}
        for p in rows:
            path = photo_path(p)
            if not path.is_file():
                raise HTTPException(422, "Фотография отсутствует в хранилище")
            blob = path.read_bytes()
            blobs[p.evidence_file_id] = blob
            with Image.open(io.BytesIO(blob)) as img:
                width, height = img.size
            payload_photos.append(dict(schema_version="maintenance-0.1", data_origin=op["data_origin"],
                photo_id=str(p.evidence_file_id), execution_id=str(report.work_report_id), equipment_id=str(p.equipment_id),
                checklist_item_id=str(p.checklist_item_id), phase=p.stage, view_key=p.view_key, mime_type=p.mime_type,
                file_size_bytes=p.file_size, width=width, height=height, original_sha256=p.sha256.strip(),
                captured_at=p.captured_at.isoformat() if p.captured_at else None, uploaded_at=p.uploaded_at.isoformat(),
                uploaded_by=str(p.uploaded_by), content_url=f"/api/v1/maintenance/photos/{p.evidence_file_id}/content"))
        answers = {str(a.checklist_template_id): a.response_value.get("answer") for a in v.rows("checklist_results", work_report_id=report.work_report_id)}
        request = dict(schema_version="maintenance-0.1", data_origin=op["data_origin"], execution_id=str(report.work_report_id),
            operation=op, photos=payload_photos, prompt_set_version="demo-clean-pairs-v1", report=dict(
                schema_version="maintenance-0.1", data_origin=op["data_origin"], execution_id=str(report.work_report_id),
                task_id=str(task_id), attempt_number=report.revision_no, state="submitted", performed_at=order.completed_at.isoformat(),
                submitted_at=report.submitted_at.isoformat(), submitted_by=str(report.submitted_by), narrative=report.comment or "Отчёт без комментария",
                answers=[dict(checklist_item_id=i["id"], status="done" if answers.get(i["id"]) == "done" else "not_done",
                    value=answers.get(i["id"]), unit=i["unit"], comment=None, completed_at=report.submitted_at.isoformat()) for i in report.checklist_snapshot],
                photo_ids=[p["photo_id"] for p in payload_photos]))
        result = invoke_review(PhotoReviewRequest.model_validate_json(json.dumps(request)), blobs.__getitem__,
                               comparability_confirmed=lambda b, a: command.comparability_confirmed)
        ui = dict(id=str(result.ai_review_id), executionId=str(result.execution_id), status=result.status,
            modelRef=result.model_ref, promptSetVersion=result.prompt_set_version, createdAt=result.created_at.isoformat(),
            items=[dict(id=str(i.checklist_item_id), label=next(c["text"] for c in report.checklist_snapshot if c["id"] == str(i.checklist_item_id)),
                        verdict=i.verdict, note=i.observation) for i in result.item_results],
            limitations=result.limitations, errorCode=result.error_code)
        predictor = version(v, "vision", "clip", result.model_ref or "unavailable", result.model_ref)
        v.repo.add("ai_quality_checks", ai_quality_check_id=result.ai_review_id, site_id=v.principal.site_id,
            work_order_id=task_id, work_report_id=report.work_report_id, predictor_version_id=predictor.predictor_version_id,
            status="failed" if result.status == "failed" else "ok" if result.status == "completed" else "inconclusive",
            assessment="inconclusive", findings={"canonical": json.loads(result.model_dump_json()), "ui": ui})
        v.session.commit()
        return ui
