"""Read models for the SPA. Missing persisted facts remain null, never fixtures."""
from __future__ import annotations

from datetime import date, datetime, timezone
from calendar import monthrange
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.orm import joinedload

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
        self._task_rows = {}
        self._task_refs = []
        self._read_rows = {}

    def prefetch(self, table, *keys, options=()):
        """Request-local snapshots for read projections only; never prime a writer."""
        cls = self.models[table]
        query = select(cls).options(*options)
        if hasattr(cls, "site_id"):
            query = query.where(cls.site_id == self.principal.site_id)
        rows = self.session.scalars(query).all()
        self._read_rows[table] = rows
        for key in keys:
            groups = {}
            for row in rows:
                groups.setdefault(getattr(row, key), []).append(row)
            self._task_rows[(table, key)] = groups
        return rows

    def prepare_equipment_views(self):
        """Bound SQL count independently of equipment, entries and history size."""
        equipment = self.prefetch("equipment", "equipment_id")
        self.prefetch("sites", "site_id")
        self.prefetch("equipment_types")
        binding = self.models["rule_equipment"]
        rule = self.models["maintenance_rules"]
        order = self.models["work_orders"]
        self.prefetch("rule_equipment", "equipment_id", options=(joinedload(binding.rule).joinedload(rule.operation),))
        self.prefetch("schedule_entries", "binding_id")
        self.prefetch("work_orders", "schedule_entry_id", "work_order_id", options=(joinedload(order.rule).joinedload(rule.operation),))
        self.prefetch("work_order_equipment", "equipment_id")
        reviews = self.prefetch("acceptance_reviews", "work_order_id")
        if self.principal.role == "executor":
            self.prefetch("work_assignments", "work_order_id")
        users = self.models["users"]
        self._task_refs.extend(self.session.scalars(select(users).where(users.user_id.in_({r.reviewer_user_id for r in reviews}))).all())
        return equipment

    def rows(self, table, **filters):
        if len(filters) == 1:
            key, value = next(iter(filters.items()))
            index = self._task_rows.get((table, key))
            if index is not None:
                return index.get(value, [])
        if table in self._read_rows:
            return [row for row in self._read_rows[table] if all(getattr(row, key) == value for key, value in filters.items())]
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
        cached = self._task_rows.get(("work_orders", "work_order_id")) if not lock else None
        order = (cached.get(task_id) or [None])[0] if cached is not None else self.session.scalar(query)
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
        entries = [e for b in bindings for e in self.rows("schedule_entries", binding_id=b.binding_id)
                   if e.status == "planned" and not any(o.status in ("completed", "cancelled")
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
            kind = typ.name if typ.name in ("ТО1", "ТО2", "ТО3") else None
        return rule, title, code, kind

    def prepare_task_views(self, orders):
        # Only use this request-local index for read-only list projections.
        # The caller has already selected the orders visible to the principal.
        order_ids = [order.work_order_id for order in orders]
        if not order_ids:
            return
        rule = self.models["maintenance_rules"]
        self._task_refs.extend(self.session.scalars(select(rule).where(
            rule.site_id == self.principal.site_id,
            rule.maintenance_rule_id.in_({o.maintenance_rule_id for o in orders if o.maintenance_rule_id}),
        ).options(joinedload(rule.operation))).all())
        self.prefetch("maintenance_types")
        def index(table, key, ids):
            cls = self.models[table]
            query = select(cls).where(cls.site_id == self.principal.site_id, getattr(cls, key).in_(ids))
            groups = {}
            for row in self.session.scalars(query).all():
                groups.setdefault(getattr(row, key), []).append(row)
            self._task_rows[(table, key)] = groups
            return [row for group in groups.values() for row in group]
        links = index("work_order_equipment", "work_order_id", order_ids)
        assignments = index("work_assignments", "work_order_id", order_ids)
        index("work_reports", "work_order_id", order_ids)
        index("acceptance_reviews", "work_order_id", order_ids)
        equipment_ids = {link.equipment_id for link in links}
        entry_ids = {order.schedule_entry_id for order in orders if order.schedule_entry_id}
        user_ids = {assignment.user_id for assignment in assignments}
        index("equipment", "equipment_id", equipment_ids)
        index("schedule_entries", "schedule_entry_id", entry_ids)
        skills = index("user_skills", "user_id", user_ids)
        for table, key, ids in (("users", "user_id", user_ids), ("skills", "skill_id", {skill.skill_id for skill in skills})):
            cls = self.models[table]
            self._task_refs.extend(self.session.scalars(select(cls).where(getattr(cls, key).in_(ids))).all())

    def task_view(self, order, *, checked_at=None):
        from .analyst import late_acceptance_needs_chief

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
        latest = reports[-1] if reports else None
        deadline = order.regulatory_deadline_at
        # A calendar deadline_at is the exclusive end of the due day, often
        # midnight on the following date. Display the persisted normative day.
        entry = self.one("schedule_entries", schedule_entry_id=order.schedule_entry_id) if order.schedule_entry_id else None
        due_date = entry.regulatory_deadline_on if entry else (
            order.operation_snapshot.get("worksheet_due_date") or (deadline.astimezone(tz).date() if deadline else None))
        now = checked_at or datetime.now(timezone.utc)
        open_order = order.status not in ("completed", "cancelled")
        overdue = bool(open_order and deadline is not None and deadline <= now)
        remaining = max(0, int((deadline-now).total_seconds()//60)) if open_order and deadline is not None else None
        return dict(id=str(order.work_order_id), code=str(order.work_order_id)[:8], title=title,
             equipmentId=str(eq.equipment_id) if eq else None, equipmentIds=[str(link.equipment_id) for link in links],
             equipmentName=eq.name if eq else "Не указано",
            operationCode=code, maintenanceType=kind, state=TASK_STATES.get(order.status, order.status),
             isOverdue=overdue, deadlineBreached=bool(deadline and any(r.decision=="accepted" and r.reviewed_at>=deadline for r in self.rows("acceptance_reviews",work_order_id=order.work_order_id))),
             mandatoryDueDate=iso(due_date),sourceDate=iso(entry.source_date or entry.regulatory_deadline_on) if entry else None,
             mandatoryDeadlineAt=iso(deadline.astimezone(tz)) if deadline else None,
             plannedWindowEnded=order.planned_end_at <= now if order.planned_end_at is not None else None,
             deadlineRemainingMinutes=remaining,
             lateAcceptanceBlocked=bool(order.status == "in_review" and latest and latest.status == "submitted"
                                        and late_acceptance_needs_chief(order, latest.work_report_id, now)),
            scheduledStart=iso(order.planned_start_at.astimezone(tz)) if order.planned_start_at else None,
            scheduledEnd=iso(order.planned_end_at.astimezone(tz)) if order.planned_end_at else None,
            closedAt=iso(order.completed_at.astimezone(tz)) if order.status == "completed" and order.completed_at else None,
            crewSize=order.required_people_snapshot, assignees=assignees,
             activeExecutionId=str(latest.work_report_id) if latest else None,
            revision=order.revision, dataOrigin=order.operation_snapshot.get("data_origin") or (rule.data_origin if rule else None),
            summary=order.operation_snapshot.get("label", ""),instructions=order.operation_snapshot.get("instructions") or (rule.operation.description if rule else None),
             normHours=str(order.norm_hours_snapshot),normUnit=order.operation_snapshot.get("norm_unit","unconfirmed"),
             **{field: order.operation_snapshot[key] for field, key in (
                 ("plannedPersonHours", "planned_person_hours"), ("planningNote", "worksheet_note"))
                 if key in order.operation_snapshot},
            durationMinutes=order.operation_snapshot.get("planning_duration_minutes"),overdueSince=iso(order.overdue_since_at),
            requiredActs=order.operation_snapshot.get("required_acts",[]),measurementRequirements=order.operation_snapshot.get("measurement_requirements",[]))

    def report_view(self, report):
        answers = {str(r.checklist_template_id): r.response_value.get("answer")
                   for r in self.rows("checklist_results", work_report_id=report.work_report_id)}
        checklist = [{**item, "answer": answers.get(item["id"])} for item in report.checklist_snapshot]
        photos = [dict(id=str(p.evidence_file_id), phase=p.stage, viewKey=p.view_key or "",
                       label=p.storage_key.rsplit("/", 1)[-1], capturedAt=iso(p.captured_at),
                       uploadedAt=iso(p.uploaded_at), checklistItemId=str(p.checklist_item_id) if p.checklist_item_id else "",
                       equipmentId=str(p.equipment_id) if p.equipment_id else None,
                       status="uploaded", url=f"/api/v1/maintenance/photos/{p.evidence_file_id}")
                  for p in self.rows("evidence_files", work_report_id=report.work_report_id) if p.stage in ("before","after")]
        return dict(id=str(report.work_report_id), taskId=str(report.work_order_id), attemptNumber=report.revision_no,
                    state="draft" if report.status == "draft" else "submitted", narrative=report.comment or "",
                    checklist=checklist, photos=photos, submittedAt=iso(report.submitted_at),actual=report.execution_context,
                    readings=[dict(equipment_id=str(r.equipment_id),parameter_code=r.parameter_code,value=str(r.numeric_value),unit=r.unit_code,measured_at=iso(r.measured_at),phase=r.phase) for r in self.rows("work_readings",work_report_id=report.work_report_id)],
                    consumptions=[dict(id=str(r.consumption_id), materialName=r.material_name, quantity=str(r.quantity), unit=r.unit,
                                       equipmentId=str(r.equipment_id) if r.equipment_id else None, authorId=str(r.recorded_by),
                                       taskRevision=r.task_revision, status=r.status, idempotencyKey=str(r.idempotency_key),
                                       supersedesId=str(r.supersedes_consumption_id) if r.supersedes_consumption_id else None,
                                       supersededById=str(r.superseded_by_consumption_id) if r.superseded_by_consumption_id else None,
                                       correctionReason=r.correction_reason, createdAt=iso(r.created_at))
                                  for r in self.session.execute(
                                      text("SELECT * FROM work_consumptions WHERE site_id=:site AND work_order_id=:task AND work_report_id=:report ORDER BY created_at,consumption_id"),
                                      dict(site=self.principal.site_id, task=report.work_order_id, report=report.work_report_id)
                                  ).mappings()],
                    acts=[dict(id=str(p.evidence_file_id),kind=p.verification_context.get("kind"),verified=bool(p.verification_context.get("verified_by")),
                        url=f"/api/v1/maintenance/photos/{p.evidence_file_id}") for p in self.rows("evidence_files",work_report_id=report.work_report_id) if p.stage=="other"])

    def bundle(self, order):
        checked_at = datetime.now(ZoneInfo(self.principal.timezone))
        task = self.task_view(order, checked_at=checked_at)
        task["maintenanceRuleId"] = str(order.maintenance_rule_id) if order.maintenance_rule_id else None
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
        latest_check = max(checks, key=lambda c: c.created_at) if checks else None
        review = None
        if latest_check and latest_check.findings.get("ui"):
            review = dict(latest_check.findings["ui"])
            if review.get("elapsedMs") is None:
                canonical_elapsed = (latest_check.findings.get("canonical") or {}).get("elapsed_ms")
                if canonical_elapsed is not None:
                    review["elapsedMs"] = canonical_elapsed
        actions = []
        if has_role(self.principal.role,("chief_engineer",),exact=True) and order.status=="completed": actions.append("reopen")
        role = self.principal.role
        if has_role(role,("dispatcher", "engineer")) and not order.operation_snapshot.get('catalog_publication_id'):
            actions.append("forecast")
        if has_role(role,('dispatcher',)) and order.status in ('draft','clarification','assigned') and not reports and not order.operation_snapshot.get('catalog_publication_id'):
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
            if has_role(role,('chief_engineer',),exact=True,permission='review_report') and report.submitted_by != self.principal.user_id and not any(
                    a.user_id == self.principal.user_id for a in self.rows("work_assignments", work_order_id=order.work_order_id)):
                actions.append("review")
        analysis_status=("failed" if review.get("status") in ("failed","unavailable") else "ready") if review else (
            "pending" if report and report.status=="submitted" and order.status=="in_review" and report.execution_context.get("photo_analysis_requested_at") else "not_requested")
        return dict(task=task, timingCheckedAt=iso(checked_at), execution=self.report_view(report) if report else None, review=review,
                    plannedChecklist=order.operation_snapshot.get("checklist", []) if report is None else [],
                    decision=decision_view, allowedActions=actions, photoAnalysisStatus=analysis_status,
                    actualRequired=bool(order.operation_snapshot.get('methodology_ref')))

    def calendar(self, year, month):
        today = datetime.now(ZoneInfo(self.principal.timezone)).date()
        items = []
        visible_orders = None
        if self.principal.role == "executor":
            visible_orders = {assignment.work_order_id for assignment in self.rows("work_assignments", user_id=self.principal.user_id)
                              if assignment.status not in ("cancelled", "declined")}
        entry_type = self.models["schedule_entries"]
        rule_type = self.models["maintenance_rules"]
        binding_type = self.models["rule_equipment"]
        first, last = date(year, month, 1), date(year, month, monthrange(year, month)[1])
        entries = self.session.scalars(select(entry_type).where(
            entry_type.site_id == self.principal.site_id,
            or_(entry_type.planned_date.between(first, last), entry_type.source_date.between(first, last)),
        ).options(joinedload(entry_type.rule).joinedload(rule_type.operation),
                  joinedload(entry_type.binding).joinedload(binding_type.equipment))).all()
        order_type = self.models["work_orders"]
        orders_by_entry = {}
        for order in self.session.scalars(select(order_type).where(
            order_type.site_id == self.principal.site_id,
            order_type.schedule_entry_id.in_([entry.schedule_entry_id for entry in entries]),
        )).all():
            orders_by_entry.setdefault(order.schedule_entry_id, []).append(order)
        self.prefetch("maintenance_types")
        for entry in entries:
            orders = orders_by_entry.get(entry.schedule_entry_id, [])
            if visible_orders is not None and (not orders or orders[0].work_order_id not in visible_orders):
                continue
            rule = entry.rule
            operation_snapshot = entry.rule_snapshot.get('operation', {})
            binding = entry.binding
            catalog=entry.rule_snapshot.get('catalog_publication_id')
            eq = binding.equipment if binding else None
            kind = None
            if rule.operation.maintenance_type_id:
                typ = self.session.get(self.models["maintenance_types"], rule.operation.maintenance_type_id)
                kind = typ.name if catalog or typ.name in ("ТО1", "ТО2", "ТО3") else None
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
