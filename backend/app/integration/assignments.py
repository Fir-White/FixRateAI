"""BE05 transaction: lock, revalidate the exact proposal, reserve and audit."""
from datetime import datetime, timedelta, timezone
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.assignment import AssignmentRequest, select_crew
from app.db.session import service_transaction
from app.schemas.maintenance import Assignment
from .assignment import _job, _workers
from .calendar import _json_value


def _lock(v, table, *, read=False, **filters):
    cls = v.models[table]
    query = select(cls)
    if hasattr(cls, "site_id"):
        query = query.where(cls.site_id == v.principal.site_id)
    for key, value in filters.items():
        column = getattr(cls, key)
        query = query.where(column.in_(value) if isinstance(value, (set, list)) else column == value)
    return v.session.scalars(query.order_by(*cls.__table__.primary_key.columns)
        .with_for_update(read=read).execution_options(populate_existing=True)).all()


def lock_workers(v, worker_ids, *, actor=False):
    """Every assignment writer acquires the same global user order, then memberships.

    UPDATE on membership also blocks FK inserts of new availability/skills until
    commit. Existing child rows are separately locked before reading their facts.
    """
    identifiers = set(worker_ids) | ({v.principal.user_id} if actor else set())
    for table in ("users", "site_memberships"):
        for identity in sorted(identifiers, key=lambda value: value.int):
            rows = _lock(v, table, user_id=identity, read=identity not in worker_ids)
            if not rows:
                raise HTTPException(404, "Работник не найден в объекте")


def _lock_context(v, order, worker_ids, crew_id):
    _lock(v, "work_order_equipment", work_order_id=order.work_order_id)
    for link in v.rows("work_order_equipment", work_order_id=order.work_order_id):
        _lock(v, "equipment", read=True, equipment_id=link.equipment_id)
    if order.maintenance_rule_id:
        rule = _lock(v, "maintenance_rules", maintenance_rule_id=order.maintenance_rule_id)[0]
        _lock(v, "regulation_editions", read=True, regulation_edition_id=rule.regulation_edition_id)
        _lock(v, "operation_templates", read=True, operation_template_id=rule.operation_template_id)
        _lock(v, "rule_required_skills", read=True, maintenance_rule_id=rule.maintenance_rule_id)
    if order.schedule_entry_id:
        entry = _lock(v, "schedule_entries", read=True, schedule_entry_id=order.schedule_entry_id)[0]
        if entry.binding_id:
            _lock(v, "rule_equipment", read=True, binding_id=entry.binding_id)
    if crew_id:
        if not _lock(v, "crews", crew_id=crew_id):
            raise HTTPException(404, "Бригада не найдена")
        _lock(v, "crew_members", read=True, crew_id=crew_id)
    _lock(v, "availability_slots", read=True, user_id=worker_ids)
    records = _lock(v, "user_skills", read=True, user_id=worker_ids)
    if records:
        _lock(v, "skills", read=True, skill_id={record.skill_id for record in records})


def _assignment_json(row, order):
    payload = dict(schema_version="maintenance-0.1", data_origin=order.operation_snapshot["data_origin"],
        assignment_id=row.work_assignment_id, task_id=row.work_order_id, executor_id=row.user_id,
        start_at=row.start_at, end_at=row.end_at, qualification_ids=[fact["skill_id"] for fact in row.qualification_snapshot],
        status="active", assigned_by=row.assigned_by)
    return json.loads(Assignment.model_validate_json(json.dumps(payload, default=_json_value)).model_dump_json())


def save_assignment(v, task_id, command, crew_id=None):
    """Own the auth-started transaction; never return success before commit."""
    if v.principal.role != "dispatcher":
        raise HTTPException(403, "Действие недоступно для текущей роли")
    with service_transaction(v.session):
        order = v.task(task_id, lock=True)
        if order.revision != command.expected_revision:
            raise HTTPException(409, "REVISION_CONFLICT: обновите данные и повторите подбор")
        ids = set(command.executor_ids)
        if len(ids) != len(command.executor_ids):
            raise HTTPException(422, "Исполнитель указан несколько раз")
        if len(ids) != order.required_people_snapshot:
            raise HTTPException(409, "INSUFFICIENT_CAPACITY: нужен полный состав бригады")
        begin, end = command.start_at.astimezone(timezone.utc), command.end_at.astimezone(timezone.utc)
        if end <= begin or end - begin > timedelta(days=32) or any(value.second or value.microsecond for value in (begin, end)):
            raise HTTPException(422, "Нужен положительный интервал в целых минутах не более 32 суток")
        if not command.reason.strip():
            raise HTTPException(422, "Укажите основание назначения")
        previous = _lock(v, "work_assignments", work_order_id=task_id)
        active = [row for row in previous if row.status not in ("cancelled", "declined")]
        lock_workers(v, ids | {row.user_id for row in active}, actor=True)
        _lock(v, "sites", read=True, site_id=v.principal.site_id)
        actor = v.one("users", user_id=v.principal.user_id)
        membership = v.one("site_memberships", user_id=v.principal.user_id)
        if not actor.is_active or not membership.is_active or membership.role != "dispatcher" or not v.one("sites").is_active:
            raise HTTPException(403, "Доступ диспетчера отозван")
        _lock_context(v, order, ids, crew_id)
        # Reads after potentially waiting for locks must not reuse ORM identity-cache facts.
        v.session.expire_all()
        context = _job(v, order)
        if context["status"] != "ready":
            raise HTTPException(409, f"{context['code']}: {context['explanation']}")
        if end - begin != timedelta(minutes=context["durationMinutes"]):
            raise HTTPException(409, "DURATION_CONFLICT: длительность предложения расходится с заданием")
        now = datetime.now(timezone.utc)
        workers = _workers(v, order, begin, end, now, ids)
        crews = []
        if crew_id:
            crew = v.one("crews", crew_id=crew_id)
            crews = [dict(crew_id=crew.crew_id, site_id=crew.site_id, name=crew.name, active=crew.is_active,
                members=[dict(worker_id=m.user_id, valid_from=m.valid_from, valid_to=m.valid_to)
                         for m in v.rows("crew_members", crew_id=crew_id)])]
        payload = dict(schema_version="maintenance-0.1", data_origin=context["dataOrigin"], task_id=task_id,
            site_id=order.site_id, expected_revision=order.revision, timezone=context["timezone"], as_of=now,
            window=dict(start_at=begin, end_at=end), earliest_at=context["earliestAt"], deadline_at=context["deadlineAt"],
            duration_minutes=context["durationMinutes"], duration_basis=context["durationBasis"],
            crew_size=context["crewSize"], qualification_ids=context["qualificationIds"], workers=workers, crews=crews, crew_id=crew_id)
        try:
            selection = select_crew(AssignmentRequest.model_validate_json(json.dumps(payload, default=_json_value)))
        except ValidationError:
            raise HTTPException(409, "INVALID_PERSISTED_INPUT: уточните доступность и допуски") from None
        if (not selection.command or set(selection.command.executor_ids) != ids
                or selection.command.start_at.astimezone(timezone.utc) != begin
                or selection.command.end_at.astimezone(timezone.utc) != end):
            raise HTTPException(409, "INSUFFICIENT_CAPACITY: состав или интервал больше недоступны; повторите подбор")
        before = dict(status=order.status, revision=order.revision, start_at=_json_value(order.planned_start_at) if order.planned_start_at else None,
            end_at=_json_value(order.planned_end_at) if order.planned_end_at else None,
            assignment_ids=[str(row.work_assignment_id) for row in active])
        for row in active:
            row.status, row.released_at = "cancelled", now
        v.session.flush()  # Release the partial unique keys before inserting the new generation.
        assigned = []
        for worker in sorted(workers, key=lambda item: item["worker_id"].int):
            facts = [dict(skill_id=str(q["skill_id"]), verified_at=_json_value(q["verified_at"]),
                          valid_until=_json_value(q["valid_until"]) if q["valid_until"] else None,
                          validity_required=q["validity_required"]) for q in worker["qualifications"] if str(q["skill_id"]) in context["qualificationIds"]]
            assigned.append(v.repo.add("work_assignments", site_id=order.site_id, work_order_id=task_id,
                user_id=worker["worker_id"], crew_id=crew_id, assigned_by=v.principal.user_id, assigned_at=now,
                start_at=begin, end_at=end, qualification_snapshot=facts, reason=command.reason.strip(), status="assigned"))
        order.status, order.planned_start_at, order.planned_end_at = "assigned", begin, end
        order.revision += 1
        v.session.flush()
        assignments = [_assignment_json(row, order) for row in assigned]
        v.repo.add("audit_events", site_id=order.site_id, actor_type="user", actor_user_id=v.principal.user_id,
            entity_type="work_orders", entity_id=task_id, action="assign", before_snapshot=before,
            after_snapshot=dict(status=order.status, revision=order.revision, assignments=assignments,
                                crew_id=str(crew_id) if crew_id else None, reason=command.reason.strip()))
        result = dict(**v.bundle(order), assignments=assignments)
    return result
