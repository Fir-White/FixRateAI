"""Canonical maintenance API projections.

The UI endpoints intentionally expose a compact camelCase view.  These routes
expose the versioned REST contract directly while keeping all date generation
in the scheduling service.
"""
from __future__ import annotations
from app.security.sessions import has_role

from datetime import date
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import Field

from app.schemas.maintenance_api import OperationCreate

PREFIX = "/api/v1/maintenance"


class OperationUpdate(OperationCreate):
    expected_revision: int = Field(gt=0)


def _guard(v, *roles: str) -> None:
    if not has_role(v.principal.role,roles):
        raise HTTPException(403, "Действие недоступно для текущей роли")


def _operation(v, operation_id: UUID):
    row = v.one("operation_templates", operation_template_id=operation_id)
    rules = sorted(
        v.rows("maintenance_rules", operation_template_id=operation_id),
        key=lambda item: item.rule_version,
        reverse=True,
    )
    return row, rules[0] if rules else None


def _operation_payload(v, operation, rule=None) -> dict:
    maintenance_type = v.one(
        "maintenance_types", maintenance_type_id=operation.maintenance_type_id
    )
    parameters = rule.schedule_parameters if rule else {}
    checks = []
    for item in v.rows(
        "checklist_templates", operation_template_id=operation.operation_template_id
    ):
        checks.append(
            {
                "checklist_item_id": item.checklist_template_id,
                "text": item.prompt,
                "answer_kind": {"checkbox": "boolean", "number": "number", "text": "text"}.get(
                    item.input_kind, "text"
                ),
                "unit": item.unit_code,
                "required": item.is_required,
                "visual_verifiability": parameters.get("checklist_metadata", {})
                .get(str(item.checklist_template_id), {})
                .get("visual_verifiability", "not_verifiable"),
                "photo_required": parameters.get("checklist_metadata", {})
                .get(str(item.checklist_template_id), {})
                .get("photo_required", False),
            }
        )
    checks.sort(key=lambda item: str(item["checklist_item_id"]))
    return {
        "schema_version": "maintenance-0.1",
        "data_origin": rule.data_origin if rule else None,
        "operation_id": operation.operation_template_id,
        "operation_version_id": rule.maintenance_rule_id if rule else operation.operation_template_id,
        "version": rule.rule_version if rule else 1,
        "code": operation.code,
        "title": operation.title,
        "maintenance_type": maintenance_type.name,
        "instructions": operation.description or operation.title,
        "crew_size": rule.required_people if rule else None,
        "raw_norm_value": rule.norm_hours if rule else None,
        "norm_unit": parameters.get("norm_unit", "unconfirmed"),
        "planning_duration_minutes": parameters.get("planning_duration_minutes"),
        "duration_basis": parameters.get("duration_basis"),
        "qualification_ids": [
            item.skill_id
            for item in (v.rows("rule_required_skills", maintenance_rule_id=rule.maintenance_rule_id) if rule else [])
        ],
        "checklist": checks,
        "status": (
            "approved"
            if rule and rule.publication_status == "published"
            else "retired"
            if not operation.is_active
            else "draft"
        ),
        "source_ref": rule.source_ref if rule else None,
    }


def _calendar_response(v, year: int, month: int) -> dict:
    from app.integration.calendar import preview_calendar

    preview = preview_calendar(v, year, month)
    items = []
    for item in preview["items"]:
        binding = v.one("rule_equipment", binding_id=UUID(item["bindingId"]))
        rule = binding.rule
        operation = rule.operation
        typ = v.one("maintenance_types", maintenance_type_id=operation.maintenance_type_id)
        occurrence_date = date.fromisoformat(item["occurrenceDate"])
        planned = []
        for entry in v.rows("schedule_entries", binding_id=binding.binding_id):
            if entry.planned_date == occurrence_date:
                planned.extend(v.rows("work_orders", schedule_entry_id=entry.schedule_entry_id))
        status = "planned"
        if planned and planned[0].status == "completed":
            status = "fulfilled"
        elif planned and planned[0].status == "cancelled":
            status = "cancelled"
        actual_execution_id = None
        if planned and planned[0].status == "completed":
            reviews = v.rows("acceptance_reviews", work_order_id=planned[0].work_order_id)
            accepted = [review for review in reviews if review.decision == "accepted"]
            if accepted:
                actual_execution_id = max(accepted, key=lambda review: review.reviewed_at).work_report_id
        items.append(
            {
                "occurrence_id": UUID(item["id"]),
                "equipment_id": binding.equipment_id,
                "operation_version_id": rule.maintenance_rule_id,
                "occurrence_date": occurrence_date,
                "maintenance_type": typ.name,
                "recurrence": rule.source_text,
                "crew_size": rule.required_people,
                "raw_norm_value": rule.norm_hours,
                "norm_unit": rule.schedule_parameters.get("norm_unit", "unconfirmed"),
                "planning_duration_minutes": rule.schedule_parameters.get("planning_duration_minutes"),
                "source_ref": rule.source_ref,
                "planned_task_id": planned[0].work_order_id if planned else None,
                "actual_execution_id": actual_execution_id,
                "status": status,
            }
        )
    return {
        "schema_version": "maintenance-0.1",
        "site_id": v.principal.site_id,
        "year": year,
        "month": month,
        "timezone": v.principal.timezone,
        "items": items,
        "total": len(items),
    }


def _execution_payload(v, report, order, equipment_id: UUID) -> dict:
    answers = []
    for result in v.rows("checklist_results", work_report_id=report.work_report_id):
        answers.append(
            {
                "checklist_item_id": result.checklist_template_id,
                "status": "done",
                "value": result.response_value.get("answer"),
                "unit": None,
                "comment": None,
                "completed_at": result.recorded_at,
            }
        )
    photos = [
        item.evidence_file_id
        for item in v.rows("evidence_files", work_report_id=report.work_report_id)
    ]
    return {
        "schema_version": "maintenance-0.1",
        "data_origin": order.operation_snapshot.get("data_origin"),
        "execution_id": report.work_report_id,
        "task_id": order.work_order_id,
        "attempt_number": report.revision_no,
        "state": "submitted" if report.status != "draft" else "draft",
        "performed_at": order.started_at,
        "submitted_at": report.submitted_at,
        "submitted_by": report.submitted_by,
        "narrative": report.comment or "",
        "answers": answers,
        "photo_ids": photos,
        "equipment_id": equipment_id,
    }


def register_routes(app, views) -> None:
    @app.get(PREFIX + "/operations")
    def operations(v=Depends(views)):
        _guard(v, "director", "admin", "dispatcher", "engineer")
        rows = []
        for operation in v.rows("operation_templates"):
            rules = sorted(
                v.rows("maintenance_rules", operation_template_id=operation.operation_template_id),
                key=lambda item: item.rule_version,
                reverse=True,
            )
            rows.append(_operation_payload(v, operation, rules[0] if rules else None))
        return rows

    @app.get(PREFIX + "/operations/{operation_id}")
    def operation(operation_id: UUID, v=Depends(views)):
        _guard(v, "director", "admin", "dispatcher", "engineer")
        return _operation_payload(v, *_operation(v, operation_id))

    @app.post(PREFIX + "/operations", status_code=201)
    def operation_create(
        command: OperationCreate,
        system_id: UUID = Query(..., description="Инженерная система операции"),
        v=Depends(views),
    ):
        _guard(v, "chief_engineer")
        typ = next(
            (item for item in v.rows("maintenance_types") if item.name == command.maintenance_type),
            None,
        )
        if typ is None:
            raise HTTPException(422, "Не задан вид обслуживания")
        v.one("engineering_systems", system_id=system_id)
        operation = v.repo.add(
            "operation_templates",
            site_id=v.principal.site_id,
            system_id=system_id,
            code=command.code,
            title=command.title,
            description=command.instructions,
            maintenance_type_id=typ.maintenance_type_id,
            is_active=command.status != "retired",
        )
        for position, item in enumerate(command.checklist, 1):
            v.repo.add(
                "checklist_templates",
                site_id=v.principal.site_id,
                operation_template_id=operation.operation_template_id,
                item_code=f"api-{position}",
                prompt=item.text,
                input_kind={"boolean": "checkbox", "number": "number", "text": "text"}[item.answer_kind],
                unit_code=item.unit,
                is_required=item.required,
                position=position,
            )
        return _operation_payload(v, operation)

    @app.patch(PREFIX + "/operations/{operation_id}")
    def operation_update(operation_id: UUID, command: OperationUpdate, v=Depends(views)):
        _guard(v, "chief_engineer")
        operation, rule = _operation(v, operation_id)
        current_revision = rule.rule_version if rule else 1
        if command.expected_revision != current_revision:
            raise HTTPException(409, "REVISION_CONFLICT: данные операции изменились")
        if rule and v.rows("schedule_entries", maintenance_rule_id=rule.maintenance_rule_id):
            raise HTTPException(409, "Операция используется в графике; создайте новую версию")
        typ = next(item for item in v.rows("maintenance_types") if item.name == command.maintenance_type)
        operation.code, operation.title, operation.description = command.code, command.title, command.instructions
        operation.maintenance_type_id = typ.maintenance_type_id
        operation.is_active = command.status != "retired"
        return _operation_payload(v, operation, rule)

    @app.delete(PREFIX + "/operations/{operation_id}", status_code=204)
    def operation_delete(
        operation_id: UUID,
        expected_revision: int = Query(..., gt=0),
        v=Depends(views),
    ):
        _guard(v, "chief_engineer")
        operation, rule = _operation(v, operation_id)
        if expected_revision != (rule.rule_version if rule else 1):
            raise HTTPException(409, "REVISION_CONFLICT: данные операции изменились")
        if rule and v.rows("schedule_entries", maintenance_rule_id=rule.maintenance_rule_id):
            raise HTTPException(409, "Операция используется в графике; история не удаляется")
        operation.is_active = False

    @app.get(PREFIX + "/regulations")
    def regulations(v=Depends(views)):
        _guard(v, "director", "admin", "dispatcher", "engineer")
        result = []
        for edition in v.rows("regulation_editions"):
            document = v.one(
                "regulation_documents",
                regulation_document_id=edition.regulation_document_id,
            )
            result.append(
                {
                    "schema_version": "maintenance-0.1",
                    "source_ref": document.source_uri or document.external_reference or document.title,
                    "data_origin": "customer" if document.source_kind != "demo" else "synthetic_demo",
                    "regulation_id": document.regulation_document_id,
                    "regulation_version_id": edition.regulation_edition_id,
                    "name": document.title,
                    "version": edition.edition_code,
                    "status": "approved" if edition.is_approved else "draft",
                    "effective_from": edition.effective_from,
                    "supersedes_version_id": None,
                }
            )
        return result

    @app.get(PREFIX + "/tasks")
    def planned_tasks(status: str | None = None, v=Depends(views)):
        _guard(v, "director", "admin", "dispatcher", "engineer", "executor")
        orders = v.repo.orders(
            v.principal.site_id,
            status=status,
            user_id=v.principal.user_id if v.principal.role == "executor" else None,
        )
        return [v.task_view(order) for order in orders]

    @app.get(PREFIX + "/calendar")
    def calendar(year: int, month: int, v=Depends(views)):
        _guard(v, "director", "admin", "dispatcher", "engineer", "executor")
        if not 2000 <= year <= 2100 or not 1 <= month <= 12:
            raise HTTPException(422, "Некорректный месяц")
        return _calendar_response(v, year, month)

    @app.get(PREFIX + "/equipment/{equipment_id}/executions")
    def executions(
        equipment_id: UUID,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        v=Depends(views),
    ):
        _guard(v, "director", "admin", "dispatcher", "engineer", "executor")
        v.one("equipment", equipment_id=equipment_id)
        reports = []
        visible_order = False
        for link in v.rows("work_order_equipment", equipment_id=equipment_id):
            order = v.one("work_orders", work_order_id=link.work_order_id)
            if v.principal.role == "executor":
                try:
                    v.task(order.work_order_id)
                except HTTPException as exc:
                    if exc.status_code == 404:
                        continue
                    raise
            visible_order = True
            reports.extend(
                _execution_payload(v, report, order, equipment_id)
                for report in v.rows("work_reports", work_order_id=order.work_order_id)
            )
        if v.principal.role == "executor" and not visible_order:
            raise HTTPException(404, "Оборудование не найдено")
        reports.sort(
            key=lambda item: (item["submitted_at"] or item["performed_at"]).isoformat()
            if item["submitted_at"] or item["performed_at"]
            else "",
            reverse=True,
        )
        return {
            "schema_version": "maintenance-0.1",
            "items": reports[offset : offset + limit],
            "total": len(reports),
            "limit": limit,
            "offset": offset,
        }
