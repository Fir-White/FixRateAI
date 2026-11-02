"""Build immutable ML inputs from persisted, site-scoped execution facts."""
from __future__ import annotations

import io
import json
from uuid import UUID

from fastapi import Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.maintenance import PhotoReviewRequest


class MLCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0)
    comparability_confirmed: bool = False


def version(v, kind, name, version_name, artifact=None):
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert
    cls = v.models["predictor_versions"]
    v.session.execute(insert(cls.__table__).values(kind=kind, name=name, version=version_name, artifact_ref=artifact)
        .on_conflict_do_nothing(index_elements=["kind", "name", "version"]))
    return v.session.scalar(select(cls).where(cls.kind == kind, cls.name == name, cls.version == version_name))


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
    from .forecasting import task_snapshot
    snapshot, item, entry = task_snapshot(v, order)
    return snapshot, entry, item.rule.confirmed


def forecast_view(result):
    return dict(resultId=str(result.result_id), method=result.method, methodVersion=result.method_version,
                modelRef=result.model_ref, status=result.status, recommendedDate=str(result.recommended_date) if result.recommended_date else None,
                mandatoryDueDate=str(result.mandatory_due_date) if result.mandatory_due_date else None,
                overdue=result.overdue, uncertaintyKind=result.uncertainty.kind, uncertaintyNote=result.uncertainty.note,
                explanation=result.explanation, warnings=result.warnings, errorCode=result.error_code, elapsedMs=result.elapsed_ms)


def register_ml_routes(app, views, photo_path, require_role, check_revision):
    @app.post("/api/v1/maintenance/tasks/{task_id}/forecast")
    def forecast(task_id: UUID, command: MLCommand, v=Depends(views)):
        from .forecasting import forecast_task
        require_role(v.principal, "dispatcher", "engineer")
        return forecast_task(v, task_id, command.expected_revision, app.state.forecaster)

    @app.post("/api/v1/maintenance/tasks/{task_id}/photo-review")
    def photo_review(task_id: UUID, command: MLCommand, v=Depends(views)):
        from ml_service.app.cv.api import invoke_review

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
