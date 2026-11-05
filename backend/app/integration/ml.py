"""Build immutable ML inputs from persisted, site-scoped execution facts."""
from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.maintenance import PhotoReviewRequest
from app.files import inspect_image, MAX_BYTES


logger = logging.getLogger(__name__)


def logged_error_code(code):
    allowed={"MODEL_NOT_READY","INSUFFICIENT_HISTORY","AI_INFERENCE_FAILED","TIMEOUT","PROVIDER_ERROR",
             "PROVIDER_BUSY","AI_BUSY","INVALID_RESPONSE","INVALID_AI_JSON","AI_SNAPSHOT_MISMATCH",
             "PHOTO_REVIEW_FAILED","INVALID_TIMEOUT","REQUEST_BUDGET_EXHAUSTED",
             "AITUNNEL_NOT_CONFIGURED","AITUNNEL_AUTH_FAILED","AITUNNEL_QUOTA_EXCEEDED","AITUNNEL_RATE_LIMITED",
             "AITUNNEL_MODEL_UNAVAILABLE","AITUNNEL_UNAVAILABLE","AITUNNEL_INVALID_REQUEST","AITUNNEL_INVALID_RESPONSE",
             "AITUNNEL_REDIRECT_REJECTED","AITUNNEL_MODEL_MISMATCH","AITUNNEL_TIMEOUT","AITUNNEL_FAILED","AITUNNEL_DATE_OUT_OF_RANGE","AITUNNEL_INSUFFICIENT_EVIDENCE",
             "LOCAL_VISION_UNAVAILABLE","LOCAL_VISION_MODEL_NOT_READY","LOCAL_VISION_MODEL_CHANGED",
             "LOCAL_VISION_INVALID_RESPONSE","LOCAL_VISION_REDIRECT_REJECTED","LOCAL_VISION_FAILED","LOCAL_VISION_TIMEOUT"}
    return code if code in allowed else "UNCLASSIFIED" if code else "none"


class MLCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0)
    comparability_confirmed: bool = False


PHOTO_REVIEW_TIMEOUT_SECONDS = 20.0


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
    # Imported lazily by create_app; the ML namespace never shadows backend app.
    from ml_service.app.cv.api import invoke_review
    from ml_service.app.core.config import settings as ml_settings

    @app.post("/api/v1/maintenance/tasks/{task_id}/forecast")
    def forecast(task_id: UUID, command: MLCommand, v=Depends(views)):
        from .forecasting import forecast_task
        require_role(v.principal, "dispatcher", "engineer")
        return forecast_task(v, task_id, command.expected_revision, app.state.forecaster,
                             timeout_seconds=app.state.settings.forecast_timeout_seconds)

    def analyze_photo_review(task_id,command,v,automatic=False):
        from ml_service.app.cv.api import invoke_review

        if not automatic: require_role(v.principal, "engineer")
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
        limits = app.state.settings
        if len(rows) > limits.photo_review_max_files or sum(p.file_size for p in rows) > limits.photo_review_max_bytes:
            raise HTTPException(413, "PHOTO_REVIEW_LIMIT_EXCEEDED")
        payload_photos = []
        total_bytes = 0
        blobs = {}
        for p in rows:
            path = photo_path(p)
            if not path.is_file():
                raise HTTPException(422, "Фотография отсутствует в хранилище")
            try:
                with path.open("rb") as stream:
                    blob = stream.read(MAX_BYTES + 1)
            except OSError:
                raise HTTPException(503, "PHOTO_STORAGE_UNAVAILABLE") from None
            total_bytes += len(blob)
            if total_bytes > limits.photo_review_max_bytes:
                raise HTTPException(413, "PHOTO_REVIEW_LIMIT_EXCEEDED")
            try:
                mime, _, width, height = inspect_image(blob)
                if (len(blob) != p.file_size or hashlib.sha256(blob).hexdigest() != p.sha256.strip()
                        or mime != p.mime_type):
                    raise ValueError("Stored evidence changed")
            except Exception:
                raise HTTPException(422, "PHOTO_CONTENT_INVALID") from None
            blobs[p.evidence_file_id] = blob
            payload_photos.append(dict(schema_version="maintenance-0.1", data_origin=op["data_origin"],
                photo_id=str(p.evidence_file_id), execution_id=str(report.work_report_id), equipment_id=str(p.equipment_id),
                checklist_item_id=str(p.checklist_item_id), phase=p.stage, view_key=p.view_key, mime_type=p.mime_type,
                file_size_bytes=p.file_size, width=width, height=height, original_sha256=p.sha256.strip(),
                captured_at=p.captured_at.isoformat() if p.captured_at else None, uploaded_at=p.uploaded_at.isoformat(),
                uploaded_by=str(p.uploaded_by), content_url=f"/api/v1/maintenance/photos/{p.evidence_file_id}/content"))
        answers = {str(a.checklist_template_id): a.response_value.get("answer") for a in v.rows("checklist_results", work_report_id=report.work_report_id)}
        readings=[dict(parameter_code=r.parameter_code,phase=r.phase,value=str(r.numeric_value),unit=r.unit_code,measured_at=r.measured_at.isoformat()) for r in v.rows("work_readings",work_report_id=report.work_report_id)]
        provider = None
        expected_model = f"{ml_settings.clip_model_name}@{ml_settings.clip_revision}"
        prompt_version = ml_settings.prompt_set_version
        predictor_family = "clip"
        if limits.photo_review_provider == "ollama":
            from ml_service.app.cv.local_vision import LocalVisionConfig, PROMPT_VERSION, review_local_photos
            try:
                vision_config = LocalVisionConfig.from_environment()
            except ValueError:
                raise HTTPException(503, "LOCAL_VISION_CONFIGURATION_INVALID") from None
            prompt_version = PROMPT_VERSION
            expected_model = vision_config.model_ref
            predictor_family = "ollama"
            provider = lambda req, loader: review_local_photos(req, loader, config=vision_config,
                comparability_confirmed=lambda b, a: command.comparability_confirmed)
        elif limits.photo_review_provider == "aitunnel":
            from ml_service.app.cv.aitunnel import PROMPT_VERSION, review_cloud_photos
            from ml_service.app.providers.aitunnel import AITunnelConfig
            from dataclasses import replace
            cloud_config = replace(AITunnelConfig.from_environment("vision"),
                timeout=min(110, limits.photo_review_timeout_seconds))
            prompt_version = PROMPT_VERSION
            expected_model = cloud_config.model_ref
            predictor_family = "aitunnel"
            provider = lambda req, loader: review_cloud_photos(req, loader, config=cloud_config,
                comparability_confirmed=lambda b, a: command.comparability_confirmed)
        request = dict(schema_version="maintenance-0.1", data_origin=op["data_origin"], execution_id=str(report.work_report_id),
            operation=op, photos=payload_photos, prompt_set_version=prompt_version, report=dict(
                schema_version="maintenance-0.1", data_origin=op["data_origin"], execution_id=str(report.work_report_id),
                task_id=str(task_id), attempt_number=report.revision_no, state="submitted", performed_at=report.execution_context.get("performed_at") or report.submitted_at.isoformat(),
                submitted_at=report.submitted_at.isoformat(), submitted_by=str(report.submitted_by), narrative=(report.comment or "Отчёт без комментария")+("\nПротокол исполнителя (не результат OCR): "+json.dumps(readings,ensure_ascii=False) if readings else ""),
                answers=[dict(checklist_item_id=i["id"], status="done" if answers.get(i["id"]) == "done" else "not_done",
                    value=answers.get(i["id"]), unit=i["unit"], comment=None, completed_at=report.submitted_at.isoformat()) for i in report.checklist_snapshot],
                photo_ids=[p["photo_id"] for p in payload_photos]))
        result = invoke_review(PhotoReviewRequest.model_validate_json(json.dumps(request)), blobs.__getitem__,
                               comparability_confirmed=lambda b, a: command.comparability_confirmed,
                               timeout_seconds=app.state.settings.photo_review_timeout_seconds,
                               provider=provider, expected_model_ref=expected_model)
        ui = dict(id=str(result.ai_review_id), executionId=str(result.execution_id), status=result.status,
            modelRef=result.model_ref, promptSetVersion=result.prompt_set_version, createdAt=result.created_at.isoformat(),
            items=[dict(id=str(i.checklist_item_id), label=next(c["text"] for c in report.checklist_snapshot if c["id"] == str(i.checklist_item_id)),
                        verdict=i.verdict, note=i.observation,
                        beforePhotoId=str(i.before_photo_id) if i.before_photo_id else None,
                        afterPhotoId=str(i.after_photo_id) if i.after_photo_id else None,
                        assessment=i.visual_assessment.model_dump() if i.visual_assessment else None) for i in result.item_results],
            limitations=result.limitations, errorCode=result.error_code)
        from app.integration.photo_evidence import classify_evidence,compare_readings
        ui["classification"]=classify_evidence(result,manual_evidence_required=bool(order.operation_snapshot.get("required_acts")) or any(i["required"] and i["visualVerifiability"]!="visible" for i in report.checklist_snapshot))
        ui["readingComparison"]=compare_readings(readings,result)
        if any(r["status"]=="mismatch" for r in ui["readingComparison"]): ui["classification"]="manual_review"
        predictor = version(v, "vision", predictor_family, result.model_ref or "unavailable", result.model_ref)
        v.repo.add("ai_quality_checks", ai_quality_check_id=result.ai_review_id, site_id=v.principal.site_id,
            work_order_id=task_id, work_report_id=report.work_report_id, predictor_version_id=predictor.predictor_version_id,
            status="failed" if result.status == "failed" else "ok" if result.status == "completed" else "inconclusive",
            assessment="inconclusive", findings={"canonical": json.loads(result.model_dump_json()), "ui": ui})
        v.session.commit()
        logger.info("ml_result tool=photo-review task=%s review=%s status=%s model=%s code=%s elapsed_ms=%s",
                    task_id, result.ai_review_id, result.status, result.model_ref or "none",
                    logged_error_code(result.error_code), result.elapsed_ms)
        return ui

    @app.post("/api/v1/maintenance/tasks/{task_id}/photo-review")
    def photo_review(task_id: UUID,command:MLCommand,v=Depends(views)):
        return analyze_photo_review(task_id,command,v)

    def automatic_photo_review(task_id,revision,principal):
        from .projections import Views
        with app.state.factory() as session:
            v=Views(session,app.state.models,principal)
            try:
                order=v.task(task_id,lock=True)
                reports=v.rows('work_reports',work_order_id=task_id)
                current=max(reports,key=lambda r:r.revision_no)
                if current.submitted_by!=principal.user_id or v.rows("ai_quality_checks",work_report_id=current.work_report_id):return
                analyze_photo_review(task_id,MLCommand(expected_revision=revision,comparability_confirmed=False),v,automatic=True)
            except Exception as exc:
                session.rollback()
                logger.warning('automatic_photo_review_failed task=%s type=%s',task_id,type(exc).__name__)
                # Unexpected pre-inference errors are persisted as failures, never a fake successful analysis.
                try:
                    order=v.task(task_id,lock=True)
                    reports=v.rows('work_reports',work_order_id=task_id)
                    current=max(reports,key=lambda r:r.revision_no)
                    if current.submitted_by!=principal.user_id or order.status!='in_review':return
                    from datetime import datetime,timezone
                    from uuid import uuid4
                    identity=uuid4()
                    ui=dict(id=str(identity),executionId=str(current.work_report_id),status='failed',modelRef=None,
                        promptSetVersion='automatic-photo-review-v2',createdAt=datetime.now(timezone.utc).isoformat(),
                        items=[],limitations=['Автоматический анализ не завершился. Повторите проверку вручную; работа не принята.'],errorCode='AUTO_PHOTO_REVIEW_FAILED',classification='manual_review')
                    predictor=version(v,'vision','automatic-photo-worker','failed-v2')
                    v.repo.add('ai_quality_checks',ai_quality_check_id=identity,site_id=order.site_id,work_order_id=task_id,
                        work_report_id=current.work_report_id,predictor_version_id=predictor.predictor_version_id,status='failed',assessment='inconclusive',findings={'ui':ui,'failure_code':'AUTO_PHOTO_REVIEW_FAILED'})
                    session.commit()
                except Exception:
                    session.rollback();logger.error('automatic_photo_failure_persistence_unavailable task=%s',task_id)
    app.state.automatic_photo_review=automatic_photo_review
