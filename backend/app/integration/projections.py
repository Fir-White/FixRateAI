"""Read models for the SPA. Missing persisted facts remain null, never fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from app.db.repository import MaintenanceRepository
from app.security.sessions import has_role

TASK_STATES = {"in_review": "submitted", "rework": "rework_required", "completed": "accepted",
               "clarification": "draft"}


def iso(value):
    return value if isinstance(value,str) else value.isoformat() if value is not None else None


class Views:
    def __init__(self, session, models, principal):
        self.session, self.models, self.principal = session, models, principal
        self.repo = MaintenanceRepository(session, models)

    def rows(self, table, **filters):
        cls = self.models[table]
        query = select(cls)
        if hasattr(cls, "site_id"):
            query = query.where(cls.site_id == self.principal.site_id)
        for key, value in filters.items():
            query = query.where(getattr(cls, key) == value)
        return self.session.scalars(query).all()

    def one(self, table, **filters):
        rows = self.rows(table, **filters)
        if not rows:
            raise HTTPException(404, "Ресурс не найден")
        return rows[0]

    def task(self, task_id, *, lock=False):
        cls = self.models["work_orders"]
        query = select(cls).where(cls.site_id == self.principal.site_id, cls.work_order_id == task_id)
        if lock:
            query = query.with_for_update()
        order = self.session.scalar(query)
        if order is None:
            raise HTTPException(404, "Задание не найдено")
        if self.principal.role == "executor" and not any(
                a.user_id == self.principal.user_id and a.status not in ("cancelled", "declined")
                for a in self.rows("work_assignments", work_order_id=task_id)):
            raise HTTPException(404, "Задание не найдено")
        return order

    def equipment(self, item):
        site = self.one("sites", site_id=item.site_id)
        typ = self.session.get(self.models["equipment_types"], item.equipment_type_id) if item.equipment_type_id else None
        bindings = self.rows("rule_equipment", equipment_id=item.equipment_id)
        entries = [e for e in self.rows("schedule_entries") if any(b.binding_id == e.binding_id for b in bindings)
                   and e.status == "planned" and not any(o.status in ("completed", "cancelled")
                       for o in self.rows("work_orders", schedule_entry_id=e.schedule_entry_id))]
        history = self.history(item.equipment_id)
        return dict(id=str(item.equipment_id), siteId=str(item.site_id), siteName=site.name,
                    equipmentType=typ.name if typ else "Не указан", inventoryCode=item.asset_code,
                    name=item.name, location=item.location or "", commissionedOn=iso(item.commissioned_on),
                    state={"under_repair": "out_of_service"}.get(item.status, item.status),
                    revision=item.revision, dataOrigin=item.properties.get("data_origin"),
                    nextDueDate=iso(min((e.regulatory_deadline_on for e in entries), default=None)),
                    lastServiceAt=history[0]["acceptedAt"] if history else None,
                    activeOperation=None,systemId=str(item.system_id),parentEquipmentId=str(item.parent_equipment_id) if item.parent_equipment_id else None,
                    linkedOperations=[dict(code=b.rule.operation.code,title=b.rule.operation.title,frequency=b.rule.source_text,
                        crewSize=b.rule.required_people,normValue=str(b.rule.norm_hours) if b.rule.norm_hours is not None else None,
                        normUnit=b.rule.schedule_parameters.get("norm_unit","unconfirmed"),published=b.rule.publication_status=="published") for b in bindings if not b.rule.schedule_parameters.get("superseded_binding")])

    def visible_equipment_ids(self):
        orders = {a.work_order_id for a in self.rows("work_assignments", user_id=self.principal.user_id)
                  if a.status not in ("cancelled", "declined")}
        return {link.equipment_id for link in self.rows("work_order_equipment") if link.work_order_id in orders}

    def history(self, equipment_id):
        result = []
        for link in self.rows("work_order_equipment", equipment_id=equipment_id):
            if self.principal.role == "executor":
                try:
                    self.task(link.work_order_id)
                except HTTPException:
                    continue
            order = self.one("work_orders", work_order_id=link.work_order_id)
            rule = self.session.get(self.models["maintenance_rules"], order.maintenance_rule_id) if order.maintenance_rule_id else None
            for review in self.rows("acceptance_reviews", work_order_id=order.work_order_id):
                if review.decision != "accepted" or order.completed_at is None:
                    continue
                user = self.session.get(self.models["users"], review.reviewer_user_id)
                result.append(dict(id=str(review.acceptance_review_id), equipmentId=str(equipment_id),
                    performedAt=review.decision_context.get("performed_at") or iso(order.completed_at), acceptedAt=iso(review.reviewed_at),
                    operation=order.operation_snapshot.get('title') or (rule.operation.title if rule else 'Работа'),
                    engineer=user.full_name, taskCode=str(order.work_order_id)[:8], runtimeHours=None))
        return sorted(result, key=lambda x: x["acceptedAt"], reverse=True)

    def operation(self, order):
        rule = self.session.get(self.models["maintenance_rules"], order.maintenance_rule_id) if order.maintenance_rule_id else None
        snapshot = order.operation_snapshot
        title = snapshot.get("title") or (rule.operation.title if rule else "Работа")
        code = snapshot.get("code") or (rule.operation.code if rule else "")
        kind = snapshot.get("maintenance_type")
        if not kind and rule and rule.operation.maintenance_type_id:
            typ = self.session.get(self.models["maintenance_types"], rule.operation.maintenance_type_id)
            kind = typ.name if typ.name in ("ТО1", "ТО2") else None
        return rule, title, code, kind

    def task_view(self, order):
        tz = ZoneInfo(self.principal.timezone)
        rule, title, code, kind = self.operation(order)
        links = self.rows("work_order_equipment", work_order_id=order.work_order_id)
        eq = self.one("equipment", equipment_id=links[0].equipment_id) if links else None
        assignees = []
        for a in self.rows("work_assignments", work_order_id=order.work_order_id):
            if a.status in ("cancelled", "declined"):
                continue
            user = self.session.get(self.models["users"], a.user_id)
            qualifications = []
            for skill in self.rows("user_skills", user_id=a.user_id):
                qualifications.append(self.session.get(self.models["skills"], skill.skill_id).name)
            assignees.append(dict(executorId=str(a.user_id), name=user.full_name, qualifications=qualifications))
        reports = sorted(self.rows("work_reports", work_order_id=order.work_order_id), key=lambda r: r.revision_no)
        deadline = order.regulatory_deadline_at
        # A calendar deadline_at is the exclusive end of the due day, often
        # midnight on the following date. Display the persisted normative day.
        entry = self.one("schedule_entries", schedule_entry_id=order.schedule_entry_id) if order.schedule_entry_id else None
        due_date = entry.regulatory_deadline_on if entry else order.operation_snapshot.get("earliest_date") or (deadline.astimezone(tz).date() if deadline else None)
        now = datetime.now(timezone.utc)
        overdue = bool(deadline and deadline < now and order.status not in ("completed", "cancelled"))
        return dict(id=str(order.work_order_id), code=str(order.work_order_id)[:8], title=title,
            equipmentId=str(eq.equipment_id) if eq else None, equipmentName=eq.name if eq else "Не указано",
            operationCode=code, maintenanceType=kind, state=TASK_STATES.get(order.status, order.status),
            isOverdue=overdue, deadlineBreached=bool(deadline and any(r.decision=="accepted" and r.reviewed_at>deadline for r in self.rows("acceptance_reviews",work_order_id=order.work_order_id))),
            mandatoryDueDate=iso(due_date),sourceDate=iso(entry.source_date or entry.regulatory_deadline_on) if entry else None,
            scheduledStart=iso(order.planned_start_at.astimezone(tz)) if order.planned_start_at else None,
            scheduledEnd=iso(order.planned_end_at.astimezone(tz)) if order.planned_end_at else None,
            crewSize=order.required_people_snapshot, assignees=assignees,
            activeExecutionId=str(reports[-1].work_report_id) if reports else None,
            revision=order.revision, dataOrigin=order.operation_snapshot.get("data_origin") or (rule.data_origin if rule else None),
            summary=order.operation_snapshot.get("label", ""),instructions=order.operation_snapshot.get("instructions") or (rule.operation.description if rule else None),
            normHours=str(order.norm_hours_snapshot),normUnit=order.operation_snapshot.get("norm_unit","unconfirmed"),
            durationMinutes=order.operation_snapshot.get("planning_duration_minutes"),overdueSince=iso(order.overdue_since_at),
            requiredActs=order.operation_snapshot.get("required_acts",[]),measurementRequirements=order.operation_snapshot.get("measurement_requirements",[]))

    def report_view(self, report):
        answers = {str(r.checklist_template_id): r.response_value.get("answer")
                   for r in self.rows("checklist_results", work_report_id=report.work_report_id)}
        checklist = [{**item, "answer": answers.get(item["id"])} for item in report.checklist_snapshot]
        photos = [dict(id=str(p.evidence_file_id), phase=p.stage, viewKey=p.view_key or "",
                       label=p.storage_key.rsplit("/", 1)[-1], capturedAt=iso(p.captured_at),
                       uploadedAt=iso(p.uploaded_at), checklistItemId=str(p.checklist_item_id) if p.checklist_item_id else "",
                       status="uploaded", url=f"/api/v1/maintenance/photos/{p.evidence_file_id}")
                  for p in self.rows("evidence_files", work_report_id=report.work_report_id) if p.stage in ("before","after")]
        return dict(id=str(report.work_report_id), taskId=str(report.work_order_id), attemptNumber=report.revision_no,
                    state="draft" if report.status == "draft" else "submitted", narrative=report.comment or "",
                    checklist=checklist, photos=photos, submittedAt=iso(report.submitted_at),actual=report.execution_context,
                    readings=[dict(equipment_id=str(r.equipment_id),parameter_code=r.parameter_code,value=str(r.numeric_value),unit=r.unit_code,measured_at=iso(r.measured_at),phase=r.phase) for r in self.rows("work_readings",work_report_id=report.work_report_id)],
                    acts=[dict(id=str(p.evidence_file_id),kind=p.verification_context.get("kind"),verified=bool(p.verification_context.get("verified_by")),
                        url=f"/api/v1/maintenance/photos/{p.evidence_file_id}") for p in self.rows("evidence_files",work_report_id=report.work_report_id) if p.stage=="other"])

    def bundle(self, order):
        task = self.task_view(order)
        reports = self.rows("work_reports", work_order_id=order.work_order_id)
        report = max(reports, key=lambda r: r.revision_no) if reports else None
        reviews = self.rows("acceptance_reviews", work_order_id=order.work_order_id)
        decision = max(reviews, key=lambda r: r.reviewed_at) if reviews else None
        decision_view = None
        if decision:
            reviewer = self.session.get(self.models["users"], decision.reviewer_user_id)
            decision_view = dict(id=str(decision.acceptance_review_id), taskId=str(order.work_order_id),
                executionId=str(decision.work_report_id), verdict="accepted" if decision.decision == "accepted" else "rejected",
                reason=decision.comment or "", decidedAt=iso(decision.reviewed_at), decidedBy=reviewer.full_name)
        checks = self.rows("ai_quality_checks", work_report_id=report.work_report_id) if report else []
        review = max(checks, key=lambda c: c.created_at).findings.get("ui") if checks else None
        actions = []
        if self.principal.role=="chief_engineer" and order.status=="completed": actions.append("reopen")
        role = self.principal.role
        if has_role(role,("dispatcher", "engineer")):
            actions.append("forecast")
        if has_role(role,('dispatcher',)) and order.status in ('draft','clarification','assigned') and not reports:
            actions.append('cancel')
        if role == "executor":
            # bundle is only called after task() has checked the active assignment.
            if order.status in ("assigned", "rework") and order.operation_snapshot.get("checklist"):
                actions.append("start")
            if (order.status == "in_progress" and report and report.status == "draft"
                    and report.submitted_by == self.principal.user_id):
                actions.extend(("edit_report", "upload_photo", "submit"))
        if has_role(role,("engineer",)) and order.status == "in_review" and report and report.status == "submitted":
            actions.append("photo_review")
            if report.submitted_by != self.principal.user_id and not any(
                    a.user_id == self.principal.user_id for a in self.rows("work_assignments", work_order_id=order.work_order_id)):
                actions.append("review")
        return dict(task=task, execution=self.report_view(report) if report else None, review=review,
                    decision=decision_view, allowedActions=actions)

    def calendar(self, year, month):
        today = datetime.now(ZoneInfo(self.principal.timezone)).date()
        items = []
        for entry in self.rows("schedule_entries"):
            if (entry.planned_date.year, entry.planned_date.month) != (year, month) and (entry.source_date is None or (entry.source_date.year,entry.source_date.month)!=(year,month)):
                continue
            orders = self.rows("work_orders", schedule_entry_id=entry.schedule_entry_id)
            if self.principal.role == "executor":
                if not orders:
                    continue
                try:
                    self.task(orders[0].work_order_id)
                except HTTPException:
                    continue
            rule = entry.rule
            operation_snapshot = entry.rule_snapshot.get('operation', {})
            binding = entry.binding
            eq = binding.equipment if binding else None
            kind = None
            if rule.operation.maintenance_type_id:
                typ = self.session.get(self.models["maintenance_types"], rule.operation.maintenance_type_id)
                kind = typ.name if typ.name in ("ТО1", "ТО2") else None
            done = bool(orders and orders[0].status == "completed")
            cancelled = entry.status != "planned" or bool(orders and orders[0].status == "cancelled")
            items.append(dict(id=str(entry.schedule_entry_id), occurrenceDate=iso(entry.planned_date),sourceDate=iso(entry.source_date or entry.regulatory_deadline_on),
                equipmentId=str(eq.equipment_id) if eq else None, equipmentName=eq.name if eq else "Не указано",
                operationCode=operation_snapshot.get('code') or rule.operation.code,
                operationTitle=operation_snapshot.get('title') or rule.operation.title, maintenanceType=kind,
                status="fulfilled" if done else "cancelled" if cancelled else "planned",
                isOverdue=entry.regulatory_deadline_on < today and not done and not cancelled,
                requiresInput=rule.publication_status != "published" or not binding,
                taskId=str(orders[0].work_order_id) if orders else None))
        return items

    def comparisons(self):
        # Only persisted runs with the integrated canonical payload can be shown.
        # Legacy raw rows remain in PostgreSQL and are explicitly distinguishable.
        runs = [d.comparison_snapshot["ui"] for d in self.rows("orchestration_decisions")
                if "ui" in d.comparison_snapshot]
        return sorted(runs, key=lambda run: run["createdAt"], reverse=True)
