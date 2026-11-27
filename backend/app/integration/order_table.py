"""Operational order worksheet. Source files and normative versions are not edited."""
from contextlib import nullcontext
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import service_transaction
from app.schemas.draft_plans import DraftPolicy
from app.schemas.maintenance import AssignmentCommand
from app.scheduling.planning_policy import access_intervals
from app.security.permissions import permits
from .analyst import workbook
from .assignment import _job, assignment_preview, local_time
from .assignments import _lock, save_assignment
from .calendar import checklist_for_rule
from .draft_resources import ensure_equipment_free
from .management import _edit
from .planning import digest

BASE = "/api/v1/maintenance/planning/order-table"
CACHE = {"Cache-Control": "private, no-store"}
PAGE = 25
EXPORT_LIMIT = 1000
MONTH = Annotated[str, Query(pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$")]
HOURS = Annotated[Decimal, Field(gt=0, le=9999, decimal_places=2, allow_inf_nan=False)]


class WorksheetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExistingRow(WorksheetModel):
    kind: Literal["existing"]
    task_id: UUID
    expected_revision: int = Field(gt=0)
    planned_start: datetime | None = None
    planned_person_hours: HOURS | None = None
    note: str | None = Field(default=None, max_length=500)


class NewRow(WorksheetModel):
    kind: Literal["new"]
    binding_id: UUID
    planned_start: datetime
    due_date: date
    planned_person_hours: HOURS | None = None
    note: str | None = Field(default=None, max_length=500)


class Preview(WorksheetModel):
    changes: list[Annotated[ExistingRow | NewRow, Field(discriminator="kind")]] = Field(min_length=1, max_length=12)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Укажите основание изменения")
        return value.strip()


class Apply(Preview):
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: UUID
    confirm_assigned: bool = False


def _guard(v):
    if not permits(v.principal.role, "order_table"):
        raise HTTPException(403, "Нет права работы с таблицей нарядов ТО")


def _locked(order, has_report, *, workbook=False):
    if order.operation_snapshot.get("catalog_publication_id") and not workbook:
        return "Выпущенный план: изменение требует нового предложения на утверждение"
    if order.status not in ("draft", "assigned") or order.started_at or has_report:
        return "Работа уже начата, закрыта или имеет историю выполнения"
    return None


LIST_SQL = """
    SELECT w.work_order_id, w.revision, w.status, w.started_at, w.planned_start_at, w.planned_end_at,
           w.operation_snapshot, w.norm_hours_snapshot, w.regulatory_deadline_at,
           coalesce(e.regulatory_deadline_on, (w.operation_snapshot->>'worksheet_due_date')::date,
                    (w.regulatory_deadline_at AT TIME ZONE :tz)::date) AS due,
           s.name AS system_name, a.labels AS equipment,
           coalesce(w.operation_snapshot->>'title', o.title, 'Без названия') AS title,
           EXISTS (SELECT 1 FROM work_reports r WHERE r.site_id=w.site_id AND r.work_order_id=w.work_order_id) AS has_report
    FROM work_orders w
    JOIN engineering_systems s ON s.system_id=w.system_id AND s.site_id=w.site_id
    LEFT JOIN schedule_entries e ON e.schedule_entry_id=w.schedule_entry_id AND e.site_id=w.site_id
    LEFT JOIN maintenance_rules rule ON rule.maintenance_rule_id=w.maintenance_rule_id AND rule.site_id=w.site_id
    LEFT JOIN operation_templates o ON o.operation_template_id=rule.operation_template_id AND o.site_id=w.site_id
    LEFT JOIN LATERAL (
        SELECT string_agg(eq.asset_code || ' · ' || eq.name, ', ' ORDER BY eq.asset_code) AS labels
        FROM work_order_equipment l JOIN equipment eq ON eq.equipment_id=l.equipment_id AND eq.site_id=l.site_id
        WHERE l.site_id=w.site_id AND l.work_order_id=w.work_order_id
    ) a ON true
    WHERE w.site_id=:site
      AND coalesce((w.planned_start_at AT TIME ZONE :tz)::date, e.planned_date,
                   (w.regulatory_deadline_at AT TIME ZONE :tz)::date, (w.created_at AT TIME ZONE :tz)::date)
          >= :first
      AND coalesce((w.planned_start_at AT TIME ZONE :tz)::date, e.planned_date,
                   (w.regulatory_deadline_at AT TIME ZONE :tz)::date, (w.created_at AT TIME ZONE :tz)::date)
          < :last
      AND (:needle='' OR strpos(lower(concat_ws(' ', w.work_order_id, w.operation_snapshot->>'title', o.title, a.labels)), :needle)>0)
    ORDER BY w.planned_start_at NULLS LAST, e.planned_date NULLS LAST, w.work_order_id
    LIMIT :limit OFFSET :offset
"""


def _local(value, tz):
    return value.astimezone(tz).replace(tzinfo=None).isoformat(timespec="minutes") if value else None


def _list(v, month, q, offset=0, limit=PAGE + 1):
    first = date.fromisoformat(month + "-01")
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    tz = ZoneInfo(v.principal.timezone)
    now = datetime.now(timezone.utc)
    rows = v.session.execute(text(LIST_SQL), dict(site=v.principal.site_id, tz=tz.key, first=first, last=last,
                                                 needle=q.strip().lower(), offset=offset, limit=limit))
    return [dict(task_id=str(row.work_order_id), revision=row.revision, state=row.status, title=row.title,
                 system=row.system_name, equipment=row.equipment or "Не указано", due_date=row.due,
                 planned_start=_local(row.planned_start_at, tz), planned_end=_local(row.planned_end_at, tz),
                 normative_hours=str(row.norm_hours_snapshot), normative_unit=row.operation_snapshot.get("norm_unit"),
                 planned_person_hours=row.operation_snapshot.get("planned_person_hours"),
                 note=row.operation_snapshot.get("worksheet_note", ""), locked_reason=_locked(row, row.has_report)
                 or ("У наряда нет будущего подтверждённого срока" if row.regulatory_deadline_at is None
                     or row.regulatory_deadline_at <= now else None))
            for row in rows]


def _bindings(v, q, offset):
    return [dict(row) for row in v.session.execute(text("""
        SELECT b.binding_id, eq.name AS equipment, eq.asset_code,
               coalesce(r.schedule_parameters->'operation_metadata'->>'title',o.title) AS title,
               coalesce(r.schedule_parameters->'operation_metadata'->>'code',o.code) AS code
        FROM rule_equipment b
        JOIN equipment eq ON eq.equipment_id=b.equipment_id AND eq.site_id=b.site_id AND eq.status='active'
        JOIN engineering_systems s ON s.system_id=b.system_id AND s.site_id=b.site_id AND s.is_active
        JOIN maintenance_rules r ON r.maintenance_rule_id=b.maintenance_rule_id AND r.site_id=b.site_id AND r.publication_status='published'
        JOIN regulation_editions ed ON ed.regulation_edition_id=r.regulation_edition_id AND ed.site_id=b.site_id AND ed.is_approved
        JOIN operation_templates o ON o.operation_template_id=r.operation_template_id AND o.site_id=b.site_id AND o.is_active
        WHERE b.site_id=:site AND r.schedule_parameters->>'catalog_publication_id' IS NULL
          AND least(b.valid_to,r.active_until,ed.effective_to, DATE '2099-12-31') >= (now() AT TIME ZONE :tz)::date
          AND nullif(btrim(r.schedule_parameters->>'methodology_ref'),'') IS NOT NULL
          AND r.schedule_parameters->>'norm_unit' IN ('person_hour','elapsed_hour') AND r.norm_hours>0
          AND (:needle='' OR strpos(lower(concat_ws(' ', eq.asset_code, eq.name,
              r.schedule_parameters->'operation_metadata'->>'title', r.schedule_parameters->'operation_metadata'->>'code',
              o.title, o.code)), :needle)>0)
        ORDER BY eq.asset_code, code, b.binding_id LIMIT :size OFFSET :offset
    """), dict(site=v.principal.site_id, tz=v.principal.timezone, needle=q.strip().lower(),
              size=PAGE + 1, offset=offset)).mappings()]


def _moment(value, tz):
    if value.second or value.microsecond or not 2000 <= value.year <= 2099:
        raise HTTPException(422, "Введите дату и время с точностью до минут")
    return local_time(value, tz).astimezone(timezone.utc)


def _future_window(begin, minutes, earliest, deadline, now):
    end = begin + timedelta(minutes=minutes)
    if begin < max(now, earliest) or end > deadline:
        raise HTTPException(422, "Интервал должен быть в будущем и целиком внутри утверждённого окна")
    return end


def _issued_entry(v, order):
    registered = v.session.execute(text("""
        SELECT t.publication_id,p.input_snapshot->'policy' AS policy,p.input_snapshot#>>'{source,timezone}' AS timezone
        FROM published_catalog_tasks t JOIN draft_publications d USING(site_id,publication_id)
        JOIN draft_publication_proposals p USING(site_id,proposal_id)
        WHERE t.site_id=:site AND t.work_order_id=:task AND p.state='published'
    """), dict(site=v.principal.site_id, task=order.work_order_id)).mappings().first()
    if not registered or str(registered["publication_id"]) != order.operation_snapshot.get("catalog_publication_id") or not order.schedule_entry_id:
        raise HTTPException(409, "Наряд не найден в журнале выпущенного плана")
    if registered["timezone"] != v.principal.timezone:
        raise HTTPException(409, "Часовой пояс изменился после выпуска плана; требуется пересогласование")
    return v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id), registered["policy"]


def _check_issued_window(v, order, entry, policy, begin, end, tz, now):
    # Never move out of the approved period, nor reinterpret an ordered chain as independent work.
    if begin.astimezone(tz).date() != entry.planned_date:
        raise HTTPException(409, "Из книги можно перенести выпущенный наряд только внутри его календарного дня")
    intervals = entry.rule_snapshot.get("occurrence", {}).get("allowed_intervals", [])
    try:
        in_scope = any(datetime.fromisoformat(slot["start_at"]) <= begin < end <= datetime.fromisoformat(slot["end_at"])
                       for slot in intervals)
    except (KeyError, TypeError, ValueError):
        in_scope = False
    if not in_scope:
        raise HTTPException(409, "Новое окно выходит за пределы утверждённого интервала")
    try:
        access=access_intervals(DraftPolicy.model_validate(policy),entry.planned_date,entry.planned_date,tz,allow_legacy=True)
        if access is None or not any(a <= begin < end <= b for a,b in access):
            raise ValueError()
    except ValueError:
        raise HTTPException(409, "Новое время выходит за пределы подтверждённого доступа на объект") from None
    if order.operation_snapshot.get("depends_on_task_ids") or v.session.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM work_orders
          WHERE site_id=:site AND jsonb_exists(operation_snapshot->'depends_on_task_ids',:task))
    """), dict(site=v.principal.site_id, task=str(order.work_order_id))):
        raise HTTPException(409, "У наряда есть зависимые работы. Требуется отдельное перепланирование")
    ensure_equipment_free(v, order, begin, end, now)


def _existing(v, change, now, tz, *, workbook=False):
    order = v.task(change.task_id)
    if order.revision != change.expected_revision:
        raise HTTPException(409, "Наряд изменился. Обновите таблицу и повторите проверку")
    if reason := _locked(order, bool(v.rows("work_reports", work_order_id=change.task_id)), workbook=workbook):
        raise HTTPException(409, reason)
    if order.regulatory_deadline_at is None or order.regulatory_deadline_at <= now:
        raise HTTPException(409, "У наряда нет будущего подтверждённого срока")
    issued, policy = _issued_entry(v, order) if workbook else (None, None)
    if issued and issued.status != "planned":
        raise HTTPException(409, "Календарное вхождение закрыто")
    data = dict(order=order, start=order.planned_start_at, end=order.planned_end_at, entry=None, selection=None)
    if change.planned_start is not None:
        context = _job(v, order, workbook_move=workbook)
        if context["status"] != "ready":
            raise HTTPException(409, context["explanation"])
        begin = _moment(change.planned_start, tz)
        end = _future_window(begin, context["durationMinutes"], datetime.fromisoformat(context["earliestAt"]),
                             min(order.regulatory_deadline_at, datetime.fromisoformat(context["deadlineAt"])), now)
        if order.schedule_entry_id:
            entry = issued or v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id)
            if entry.status != "planned":
                raise HTTPException(409, "Календарное вхождение закрыто")
            target_day = begin.astimezone(tz).date()
            if target_day != entry.planned_date and v.rows("schedule_entries", schedule_plan_id=entry.schedule_plan_id,
                    binding_id=entry.binding_id, planned_date=target_day, sequence_no=entry.sequence_no):
                raise HTTPException(409, "Календарное вхождение с тем же номером уже занимает этот день")
            if not workbook or begin != order.planned_start_at or end != order.planned_end_at:
                data["entry"] = entry
            if workbook and data["entry"] is not None:
                _check_issued_window(v, order, entry, policy, begin, end, tz, now)
        data.update(start=begin, end=end)
    moving = data["start"] != order.planned_start_at or data["end"] != order.planned_end_at
    if order.status == "assigned" and (not workbook or moving):
        if change.planned_start is None or (not workbook and {"planned_person_hours", "note"} & change.model_fields_set):
            raise HTTPException(422, "Для назначенного наряда отдельно подтверждается только перенос времени")
        if data["start"] == order.planned_start_at:
            raise HTTPException(422, "Новое время совпадает с текущим")
        active = [row for row in v.rows("work_assignments", work_order_id=change.task_id)
                  if row.status not in ("cancelled", "declined")]
        ids = sorted({row.user_id for row in active}, key=str)
        crews = {row.crew_id for row in active}
        if len(active) != order.required_people_snapshot or len(ids) != len(active) or len(crews) != 1 or any(row.status != "assigned" for row in active):
            raise HTTPException(409, "Состав назначения больше не подходит для переноса")
        crew = next(iter(crews))
        result = assignment_preview(v, order, datetime.fromisoformat(_local(data["start"], tz)),
                                     datetime.fromisoformat(_local(data["end"], tz)), crew, ids,
                                     individual_only=crew is None, workbook_move=workbook)
        selected = result.get("command")
        if not selected or datetime.fromisoformat(selected["start_at"]) != data["start"] or datetime.fromisoformat(selected["end_at"]) != data["end"]:
            raise HTTPException(409, "Прежняя бригада недоступна в новом интервале: " + result["explanation"])
        data["selection"] = (selected, crew)
        data["worker_names"] = [worker["name"] for worker in result["selectedWorkers"]]
    elif not ({"planned_start", "planned_person_hours", "note"} & change.model_fields_set) or (
        change.planned_start is None and not ({"planned_person_hours", "note"} & change.model_fields_set)
    ):
        raise HTTPException(422, "Укажите хотя бы одну правку")
    elif order.status == "draft" and any(row.status not in ("cancelled", "declined") for row in v.rows("work_assignments", work_order_id=change.task_id)):
        raise HTTPException(409, "У черновика есть назначения, требуется сверка")
    snapshot = order.operation_snapshot
    entry = data["entry"] or (v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id)
                              if order.schedule_entry_id else None)
    equipment = v.session.execute(text("""
        SELECT string_agg(e.asset_code || ' · ' || e.name, ', ' ORDER BY e.asset_code)
        FROM work_order_equipment l JOIN equipment e ON e.site_id=l.site_id AND e.equipment_id=l.equipment_id
        WHERE l.site_id=:site AND l.work_order_id=:task
    """), dict(site=v.principal.site_id, task=change.task_id)).scalar_one()
    facts = _facts(change.task_id, v.operation(order)[1], data["start"], data["end"], tz,
                    "reschedule" if data["selection"] else "update",
                    equipment=equipment, due_date=str(entry.regulatory_deadline_on if entry else
                        snapshot.get("worksheet_due_date") or order.regulatory_deadline_at.astimezone(tz).date()),
                    normative_hours=str(order.norm_hours_snapshot), normative_unit=snapshot.get("norm_unit"),
                   planned_person_hours=_hours(change.planned_person_hours) if "planned_person_hours" in change.model_fields_set else snapshot.get("planned_person_hours"),
                   note=(change.note or "").strip() if "note" in change.model_fields_set else snapshot.get("worksheet_note", ""),
                   before_start=_local(order.planned_start_at, tz), before_end=_local(order.planned_end_at, tz),
                   before_hours=snapshot.get("planned_person_hours"), before_note=snapshot.get("worksheet_note", ""),
                   order_revision=order.revision,
                   entry_revision=data["entry"].revision if data["entry"] else None,
                   assigned_workers=[str(x) for x in ids] if data["selection"] else [],
                   worker_names=data.get("worker_names", []),
                   crew_id=str(crew) if data["selection"] and crew else None)
    if (data["start"] == order.planned_start_at and data["end"] == order.planned_end_at
            and facts["planned_person_hours"] == facts["before_hours"] and facts["note"] == facts["before_note"]):
        raise HTTPException(422, "Нет изменений в наряде")
    return data, facts


def _facts(identity, title, start, end, tz, action, **extra):
    return dict(action=action, task_id=str(identity), title=title, planned_start=_local(start, tz),
                planned_end=_local(end, tz), **extra)


def _hours(value):
    return format(value.normalize(), "f") if value is not None else None


def _new(v, change, now, tz):
    binding = v.one("rule_equipment", binding_id=change.binding_id)
    rule, equipment = binding.rule, binding.equipment
    op, edition, params = rule.operation, rule.edition, rule.schedule_parameters
    if (equipment.status != "active" or not v.one("engineering_systems", system_id=binding.system_id).is_active
        or not op.is_active or not edition.is_approved or rule.publication_status != "published"
        or params.get("catalog_publication_id") or not params.get("methodology_ref")
        or params.get("norm_unit") not in ("person_hour", "elapsed_hour")
        or rule.norm_hours is None or not 0 < rule.norm_hours
        or type(params.get("planning_duration_minutes")) is not int or not 0 < params["planning_duration_minutes"] <= 46080
        or rule.data_origin != (equipment.properties.get("data_origin") or "customer")):
        raise HTTPException(422, "Выберите действующий регламент с подтверждённой нормой, длительностью и методикой")
    skills = v.rows("rule_required_skills", maintenance_rule_id=rule.maintenance_rule_id)
    if any(s.minimum_holders > rule.required_people for s in skills):
        raise HTTPException(422, "Допуски регламента не покрываются численностью бригады")
    if not skills and "checklist_ids" not in params and not params.get("qualifications_confirmed"):
        raise HTTPException(422, "В регламенте не подтверждены требования к допускам")
    checks = checklist_for_rule(v, op.operation_template_id, params)
    if not checks:
        raise HTTPException(422, "У регламента нет утверждённого чек-листа")
    begin = _moment(change.planned_start, tz)
    local_day = begin.astimezone(tz).date()
    first = max(local_day, binding.valid_from, rule.active_from, edition.effective_from,
                equipment.commissioned_on or date.min)
    last = min(d for d in (binding.valid_to, rule.active_until, edition.effective_to, change.due_date) if d is not None)
    if change.due_date < local_day or change.due_date > last or change.due_date.year > 2099:
        raise HTTPException(422, "Срок разового наряда должен быть в периоде действия регламента")
    deadline = datetime.combine(change.due_date + timedelta(days=1), time.min, tz)
    end = _future_window(begin, params["planning_duration_minutes"], datetime.combine(first, time.min, tz), deadline, now)
    order_id = uuid5(NAMESPACE_URL, f"fixrate:order-table:{v.principal.site_id}:{binding.binding_id}:{local_day}")
    if v.rows("work_orders", work_order_id=order_id):
        raise HTTPException(409, "Разовый наряд по этой привязке на этот день уже создан")
    metadata = params.get("checklist_metadata", {})
    operation = params.get("operation_metadata", {})
    snapshot = dict(data_origin=rule.data_origin, code=operation.get("code") or op.code,
                    title=operation.get("title") or op.title, instructions=operation.get("instructions") or op.description,
                    maintenance_type=v.one("maintenance_types", maintenance_type_id=op.maintenance_type_id).name,
                    methodology_ref=params["methodology_ref"], norm_unit=params["norm_unit"],
                    planning_duration_minutes=params["planning_duration_minutes"], duration_basis="configured:explicit-duration",
                    earliest_date=str(first), measurement_requirements=params.get("measurement_requirements", []),
                    required_acts=params.get("required_acts", []), operation_version=rule.rule_version,
                    table_binding_id=str(binding.binding_id), worksheet_due_date=str(change.due_date),
                    qualification_ids=sorted(str(skill.skill_id) for skill in skills),
                    checklist=[dict(id=str(c.checklist_template_id), text=c.prompt, unit=c.unit_code, required=c.is_required,
                        answerKind={"checkbox": "boolean", "number": "number", "text": "text"}[c.input_kind],
                        visualVerifiability=metadata.get(str(c.checklist_template_id), {}).get("visual_verifiability", "not_verifiable"),
                        photoRequired=metadata.get(str(c.checklist_template_id), {}).get("photo_required", False)) for c in checks],
                    planned_person_hours=_hours(change.planned_person_hours), worksheet_note=(change.note or "").strip())
    facts = _facts(order_id, snapshot["title"], begin, end, tz, "create", due_date=str(change.due_date),
                    equipment=f"{equipment.asset_code} · {equipment.name}", normative_hours=str(rule.norm_hours),
                    normative_unit=snapshot["norm_unit"], planned_person_hours=snapshot["planned_person_hours"], note=snapshot["worksheet_note"],
                   binding_revision=binding.revision, equipment_revision=equipment.revision, rule_id=str(rule.maintenance_rule_id),
                   source_digest=digest(dict(snapshot=snapshot, norm=rule.norm_hours, crew=rule.required_people,
                                             norm_basis=rule.norm_hours_basis, first=first, last=last)))
    return dict(binding=binding, snapshot=snapshot, start=begin, end=end, deadline=deadline), facts


def _plan(v, request, *, workbook_source=None):
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(v.principal.timezone)
    seen, slots, operations, result = set(), set(), [], []
    for index, change in enumerate(request.changes):
        try:
            data, facts = (_existing(v, change, now, tz, workbook=workbook_source is not None)
                           if isinstance(change, ExistingRow) else _new(v, change, now, tz))
            if facts["task_id"] in seen:
                raise HTTPException(422, "Один наряд не должен встречаться в пакете дважды")
            seen.add(facts["task_id"])
            if data.get("selection") and len(request.changes) != 1:
                raise HTTPException(422, "Проверяйте и подтверждайте перенос назначенного наряда отдельно")
            if entry := data.get("entry"):
                slot = (entry.schedule_plan_id, entry.binding_id, entry.sequence_no, data["start"].astimezone(tz).date())
                if slot in slots:
                    raise HTTPException(409, "Две строки претендуют на одно календарное вхождение")
                slots.add(slot)
        except HTTPException as error:
            result.append(dict(index=index, action="blocked", issue=error.detail))
        else:
            result.append(dict(index=index, **facts))
            operations.append(data)
    blocked = len(operations) != len(request.changes)
    return operations, dict(items=result, can_apply=not blocked,
        requires_assigned_confirmation=any(row["action"] == "reschedule" for row in result),
        preview_digest=None if blocked else digest(dict(site=v.principal.site_id, actor=v.principal.user_id,
            timezone=tz.key, reason=request.reason, changes=[c.model_dump(mode="json", exclude_unset=True) for c in request.changes],
             results=result, **({"workbook": workbook_source} if workbook_source is not None else {}))))


def _event(v, identity, action, reason, before, after):
    v.repo.add("audit_events", site_id=v.principal.site_id, actor_type="user", actor_user_id=v.principal.user_id,
               entity_type="work_orders", entity_id=identity, action=action, before_snapshot=before,
               after_snapshot=dict(after, reason=reason, actor_role=v.principal.role))


def _materialize(v, data, facts, reason, tz, *, workbook_source=None):
    identity = UUID(facts["task_id"])
    if facts["action"] == "create":
        binding = data["binding"]
        rule = binding.rule
        order = v.repo.add("work_orders", work_order_id=identity, site_id=v.principal.site_id,
            system_id=binding.system_id, maintenance_rule_id=rule.maintenance_rule_id, origin="manual", status="draft",
            required_people_snapshot=rule.required_people, norm_hours_snapshot=rule.norm_hours,
            norm_hours_basis_snapshot=rule.norm_hours_basis, operation_snapshot=data["snapshot"],
            planned_start_at=data["start"], planned_end_at=data["end"], regulatory_deadline_at=data["deadline"],
            created_by=v.principal.user_id)
        v.repo.add("work_order_equipment", site_id=order.site_id, system_id=order.system_id,
                   work_order_id=identity, equipment_id=binding.equipment_id)
    else:
        order = data["order"]
        if data["selection"]:
            command, crew = data["selection"]
            command = AssignmentCommand.model_validate_json(json.dumps(dict(command, reason=reason)))
            save_assignment(v, identity, command, crew, worksheet_move=True, workbook_move=workbook_source is not None)
        else:
            if workbook_source is not None and data["entry"]:
                assets={link.equipment_id for link in v.rows("work_order_equipment",work_order_id=identity)}
                if assets:
                    _lock(v, "equipment", equipment_id=assets)
                ensure_equipment_free(v, order, data["start"], data["end"], datetime.now(timezone.utc))
            order.planned_start_at, order.planned_end_at = data["start"], data["end"]
            order.revision += 1
        if not data["selection"] or workbook_source is not None:
            order.operation_snapshot = dict(order.operation_snapshot, planned_person_hours=facts["planned_person_hours"],
                                            worksheet_note=facts["note"])
        if workbook_source is not None and not data["selection"] and order.status == "assigned":
            from .analyst import notify_event
            notify_event(v, order, "order_updated", ("executor", "technician"))
        if entry := data["entry"]:
            if entry.revision != facts["entry_revision"] or entry.status != "planned":
                raise HTTPException(409, "Календарное вхождение изменилось. Повторите проверку")
            entry.planned_date, entry.planned_at = data["start"].astimezone(tz).date(), data["start"]
            entry.revision += 1
    before = {k: value for k, value in facts.items() if k.startswith("before_")}
    provenance = {"workbook": workbook_source} if workbook_source is not None else {}
    _event(v, identity, ("workbook_" if provenance else "worksheet_") + facts["action"], reason,
           before, dict(facts, revision=order.revision, **provenance))
    return dict(task_id=str(identity), revision=order.revision, action=facts["action"])


def _apply(v, command, *, workbook_source=None, workbook_request=None):
    request_hash = digest(command.model_dump(mode="json", exclude_unset=True) if workbook_source is None
                          else {"workbook": workbook_source, "request": workbook_request})
    namespace = "worksheet" if workbook_source is None else "workbook"
    key = uuid5(NAMESPACE_URL, f"fixrate:{namespace}:{v.principal.site_id}:{v.principal.user_id}:{command.idempotency_key}")
    # Lock in the same order as assignment writers (order before worker/membership).
    with service_transaction(v.session):
        v.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": str(key)})
        ids = {change.task_id for change in command.changes if isinstance(change, ExistingRow)}
        orders = _lock(v, "work_orders", work_order_id=ids) if ids else []
        assigned = command.confirm_assigned and len(command.changes) == 1 and bool(ids)
        # _edit normally owns the transaction; its actor check is factored out for this transaction.
        with _edit(v, roles=("chief_engineer",), exact_roles=True, _owns_transaction=False, permission="order_table") if not assigned else nullcontext():
            if assigned:
                # Worker/membership locks must still be acquired in the assignment service's order.
                # The read below is for replay only; a new operation rechecks the actor under those locks.
                actor = v.one("users", user_id=v.principal.user_id)
                member = v.one("site_memberships", user_id=v.principal.user_id)
                if not actor.is_active or not member.is_active or member.role != v.principal.role or not permits(member.role, "order_table"):
                    raise HTTPException(403, "Доступ главного инженера изменился")
            site = v.one("sites") if assigned else _lock(v, "sites", site_id=v.principal.site_id, read=True)[0]
            if not site.is_active or site.timezone != v.principal.timezone:
                raise HTTPException(403, "Объект недоступен")
            stored = v.rows("audit_events", audit_event_id=key)
            if stored:
                with _edit(v, roles=("chief_engineer",), exact_roles=True, _owns_transaction=False, permission="order_table") if assigned else nullcontext():
                    if assigned and not _lock(v, "sites", site_id=v.principal.site_id, read=True)[0].is_active:
                        raise HTTPException(403, "Объект недоступен")
                    saved = stored[0].after_snapshot
                    if saved.get("request_hash") != request_hash:
                        raise HTTPException(409, "Ключ повторной записи использован с другими параметрами")
                    return dict(saved["response"], replayed=True)
            if not assigned:
                v.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                                  {"key": f"catalog:{v.principal.site_id}"})
            v.session.expire_all()
            entries = {order.schedule_entry_id for order in orders if order.schedule_entry_id}
            # Assigned orders take the schedule entry lock after worker locks in the existing service.
            if entries and not assigned:
                _lock(v, "schedule_entries", schedule_entry_id=entries)
            operations, plan = _plan(v, command, workbook_source=workbook_source)
            if not plan["can_apply"] or plan["preview_digest"] != command.preview_digest:
                raise HTTPException(409, "Предпросмотр устарел или содержит блокировки. Проверьте изменения снова")
            if plan["requires_assigned_confirmation"] != assigned or command.confirm_assigned != assigned:
                raise HTTPException(409, "Назначенный наряд требует отдельного подтверждения переноса")
            tz = ZoneInfo(v.principal.timezone)
            result = dict(replayed=False, items=[_materialize(v, data, row, command.reason, tz, workbook_source=workbook_source)
                          for data, row in zip(operations, plan["items"], strict=True)])
            v.repo.add("audit_events", audit_event_id=key, site_id=v.principal.site_id, actor_type="user",
                actor_user_id=v.principal.user_id, entity_type="work_orders", entity_id=UUID(result["items"][0]["task_id"]),
                action=namespace+"_apply", after_snapshot=dict(request_hash=request_hash, response=result))
            return result


def register_routes(app, views):
    @app.get(BASE)
    def rows(month: MONTH, response: Response, offset: int = Query(0, ge=0, le=1_000_000),
             q: str = Query("", max_length=120), v=Depends(views)):
        _guard(v)
        response.headers.update(CACHE)
        items = _list(v, month, q, offset)
        return dict(items=items[:PAGE], has_more=len(items) > PAGE, timezone=v.principal.timezone)

    @app.get(BASE + "/bindings")
    def bindings(response: Response, offset: int = Query(0, ge=0, le=1_000_000),
                 q: str = Query("", max_length=120), v=Depends(views)):
        _guard(v)
        response.headers.update(CACHE)
        items = _bindings(v, q, offset)
        return dict(items=items[:PAGE], has_more=len(items) > PAGE)

    @app.post(BASE + "/preview")
    def preview(command: Preview, response: Response, v=Depends(views)):
        _guard(v)
        response.headers.update(CACHE)
        return _plan(v, command)[1]

    @app.post(BASE + "/apply")
    def apply(command: Apply, response: Response, v=Depends(views)):
        _guard(v)
        response.headers.update(CACHE)
        try:
            return _apply(v, command)
        except IntegrityError as error:
            if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "schedule_entries_binding_occurrence":
                raise HTTPException(409, "Календарное вхождение занято. Повторите проверку") from None
            raise

    @app.get(BASE + "/export.xlsx")
    def export(month: MONTH, q: str = Query("", max_length=120), v=Depends(views)):
        _guard(v)
        rows = _list(v, month, q, limit=EXPORT_LIMIT + 1)
        if len(rows) > EXPORT_LIMIT:
            raise HTTPException(413, "Сузьте фильтр: XLSX поддерживает до 1000 строк")
        fields = ("task_id", "title", "equipment", "state", "planned_start", "planned_end", "due_date",
                  "normative_hours", "normative_unit", "planned_person_hours", "note")
        cells = [["Наряд", "ТО", "Оборудование", "Статус", "Начало", "Конец", "Обязательный срок",
                  "Норма", "Единица нормы", "План, чел.-ч", "Примечание"]]
        cells.extend([[row[key] for key in fields] for row in rows])
        return Response(workbook(cells), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={**CACHE, "Content-Disposition": f'attachment; filename="fixrate-to-{month}.xlsx"'})
