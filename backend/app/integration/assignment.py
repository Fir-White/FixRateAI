"""Site-scoped, read-only ALG03 boundary; input facts come from PostgreSQL."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select

from app.assignment import AssignmentRequest, select_crew
from .calendar import _json_value


def local_time(value, tz):
    """Reject DST gaps/folds instead of guessing which local instant was intended."""
    if value.tzinfo is not None:
        raise HTTPException(422, "Введите местное время объекта без смещения UTC")
    possible = {}
    for fold in (0, 1):
        aware = value.replace(tzinfo=tz, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == value:
            possible[utc] = aware
    if len(possible) != 1:
        raise HTTPException(422, "Местное время не существует или неоднозначно при переводе часов. Выберите другое время.")
    return next(iter(possible.values()))


def _job(v, order):
    if order.operation_snapshot.get('catalog_publication_id'):
        return dict(taskId=str(order.work_order_id),expectedRevision=order.revision,timezone=v.principal.timezone,
            status='needs_input',code='PUBLISHED_PLAN_IMMUTABLE',explanation='Назначение утверждено в составе плана. Перенос требует нового предложения.',
            crewSize=order.required_people_snapshot,durationMinutes=order.operation_snapshot.get('planning_duration_minutes'),
            durationBasis=order.operation_snapshot.get('duration_basis'),rawNormValue=str(order.norm_hours_snapshot),
            earliestAt=None,deadlineAt=None,qualificationIds=[],requiredQualifications=[],dataOrigin=order.operation_snapshot.get('data_origin'),crewChoices=[])
    site = v.one("sites", site_id=order.site_id)
    tz = ZoneInfo(site.timezone)
    snapshot = order.operation_snapshot
    origin = snapshot.get("data_origin")
    result = dict(taskId=str(order.work_order_id), expectedRevision=order.revision, timezone=site.timezone,
        status="ready", code=None, explanation="", crewSize=order.required_people_snapshot,
        durationMinutes=snapshot.get("planning_duration_minutes"), durationBasis=snapshot.get("duration_basis"),
        rawNormValue=str(order.norm_hours_snapshot) if order.norm_hours_snapshot is not None else None,
        earliestAt=None, deadlineAt=None, qualificationIds=[], requiredQualifications=[], dataOrigin=origin,
        crewChoices=[dict(id=str(crew.crew_id), name=crew.name) for crew in v.rows("crews") if crew.is_active])

    def stop(code, explanation):
        result.update(status="needs_input", code=code, explanation=explanation)
        return result

    if order.status not in ("draft", "assigned", "in_progress", "rework"):
        return stop("TASK_NOT_ASSIGNABLE", "Подбор доступен для чернового или назначенного задания до начала работы.")
    if origin not in ("customer", "synthetic_demo"):
        return stop("ORIGIN_UNCONFIRMED", "Не указано происхождение исходных данных задания.")
    links = v.rows("work_order_equipment", work_order_id=order.work_order_id)
    if len(links) != 1:
        return stop("EQUIPMENT_CONTEXT_INVALID", "Задание должно быть связано с одной единицей оборудования.")
    equipment = v.one("equipment", equipment_id=links[0].equipment_id)
    if equipment.status != "active":
        return stop("EQUIPMENT_UNAVAILABLE", "Оборудование недоступно для планового выполнения работы.")
    if equipment.properties.get("data_origin") != origin:
        return stop("DATA_ORIGIN_MISMATCH", "Происхождение оборудования и задания различается.")
    rule = v.one("maintenance_rules", maintenance_rule_id=order.maintenance_rule_id) if order.maintenance_rule_id else None
    if rule and rule.data_origin != origin:
        return stop("DATA_ORIGIN_MISMATCH", "Происхождение задания расходится с версией регламента.")
    if rule and (rule.publication_status != "published" or not rule.edition.is_approved or not rule.operation.is_active):
        return stop("RULE_UNCONFIRMED", "Регламент или его редакция не утверждены.")
    if rule and rule.required_people != order.required_people_snapshot:
        return stop("CREW_SIZE_CONFLICT", "Численность в задании расходится с версией регламента. Требуется сверка.")
    if "qualification_ids" in snapshot:
        try:
            if not isinstance(snapshot["qualification_ids"], list):
                raise ValueError("qualification list required")
            qualifications = [UUID(value) for value in snapshot["qualification_ids"]]
        except (ValueError, TypeError, AttributeError):
            return stop("QUALIFICATIONS_UNCONFIRMED", "Некорректный список требований к квалификации в задании.")
        required = v.rows("rule_required_skills", maintenance_rule_id=rule.maintenance_rule_id) if rule else []
        if any(skill.skill_id not in qualifications or skill.minimum_holders > order.required_people_snapshot for skill in required):
            return stop("QUALIFICATION_SNAPSHOT_CONFLICT", "Допуски в снимке задания не покрывают требования версии регламента.")
    else:
        skills = v.rows("rule_required_skills", maintenance_rule_id=rule.maintenance_rule_id) if rule else []
        if not skills and not (rule and rule.schedule_parameters.get("qualifications_confirmed") is True):
            return stop("QUALIFICATIONS_UNCONFIRMED", "Требования к допускам не определены. Пустой список нужно подтвердить явно.")
        if any(skill.minimum_holders > order.required_people_snapshot for skill in skills):
            return stop("CREW_SIZE_CONFLICT", "Требуемое число держателей допуска превышает размер бригады.")
        qualifications = [skill.skill_id for skill in skills]
    result["qualificationIds"] = [str(skill) for skill in qualifications]
    for skill in qualifications:
        records = v.rows("skills", skill_id=skill)
        if not records:
            return stop("QUALIFICATIONS_UNCONFIRMED", "В снимке задания указан неизвестный допуск.")
        result["requiredQualifications"].append(records[0].name)
    if order.schedule_entry_id:
        entry = v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id)
        earliest = entry.earliest_date or entry.regulatory_deadline_on
        if not entry.binding_id or rule is None:
            return stop("MAINTENANCE_WINDOW_UNCONFIRMED", "У календарного задания нет подтверждённой привязки и версии регламента.")
        binding = v.one("rule_equipment", binding_id=entry.binding_id)
        if (entry.maintenance_rule_id != rule.maintenance_rule_id
                or binding.maintenance_rule_id != rule.maintenance_rule_id
                or binding.equipment_id != equipment.equipment_id):
            return stop("MAINTENANCE_CONTEXT_CONFLICT", "Привязка оборудования и версия регламента расходятся с заданием.")
        earliest = max(earliest, binding.valid_from, rule.active_from, rule.edition.effective_from)
        if equipment.commissioned_on:
            earliest = max(earliest, equipment.commissioned_on)
        result["earliestAt"] = datetime.combine(earliest, time.min, tz).isoformat()
        deadlines = [datetime.combine(entry.regulatory_deadline_on + timedelta(days=1), time.min, tz), entry.regulatory_deadline_at]
        if order.regulatory_deadline_at:
            deadlines.append(order.regulatory_deadline_at)
        for day in (binding.valid_to, rule.active_until, rule.edition.effective_to):
            if day is not None:
                deadlines.append(datetime.combine(day + timedelta(days=1), time.min, tz))
        result["deadlineAt"] = min(deadlines).isoformat()
    else:
        try:
            earliest = date.fromisoformat(snapshot["earliest_date"])
        except (KeyError, ValueError, TypeError):
            return stop("MAINTENANCE_WINDOW_UNCONFIRMED", "Не задано начало допустимого окна обслуживания.")
        result["earliestAt"] = datetime.combine(earliest, time.min, tz).isoformat()
        result["deadlineAt"] = order.regulatory_deadline_at.isoformat() if order.regulatory_deadline_at else None
        if equipment.commissioned_on:
            earliest = max(earliest, equipment.commissioned_on)
        if rule:
            earliest = max(earliest, rule.active_from, rule.edition.effective_from)
            ends = [order.regulatory_deadline_at] if order.regulatory_deadline_at else []
            for day in (rule.active_until, rule.edition.effective_to):
                if day is not None:
                    ends.append(datetime.combine(day + timedelta(days=1), time.min, tz))
            result["deadlineAt"] = min(ends).isoformat() if ends else None
        if binding_id := snapshot.get("table_binding_id"):
            bindings = v.rows("rule_equipment", binding_id=UUID(binding_id))
            binding = bindings[0] if bindings else None
            if (not binding or not rule or binding.maintenance_rule_id != rule.maintenance_rule_id
                    or binding.equipment_id != equipment.equipment_id):
                return stop("MAINTENANCE_CONTEXT_CONFLICT", "Привязка разового наряда больше не соответствует регламенту и оборудованию.")
            earliest = max(earliest, binding.valid_from)
            if binding.valid_to is not None:
                bound = datetime.combine(binding.valid_to + timedelta(days=1), time.min, tz)
                deadline = result["deadlineAt"]
                result["deadlineAt"] = min(datetime.fromisoformat(deadline), bound).isoformat() if deadline else bound.isoformat()
        result["earliestAt"] = datetime.combine(earliest, time.min, tz).isoformat()
    if result["deadlineAt"] is None:
        return stop("MAINTENANCE_WINDOW_UNCONFIRMED", "Не задан обязательный срок завершения работы.")
    if (not isinstance(result["durationMinutes"], int) or isinstance(result["durationMinutes"], bool)
            or not 0 < result["durationMinutes"] <= 46080 or not isinstance(result["durationBasis"], str)
            or not result["durationBasis"].strip()):
        return stop("DURATION_UNCONFIRMED", "Нужна подтверждённая длительность в снимке задания. Исходная норма не заменяет длительность.")
    grant=getattr(order,"exception_context",{}).get("late_execution",{})
    if grant.get("approved_by") and grant.get("reason") and grant.get("until"):
        try:
            permitted=datetime.fromisoformat(grant["until"]).astimezone(tz)
            ends=[permitted]
            if rule:
                for day in (rule.active_until,rule.edition.effective_to):
                    if day:ends.append(datetime.combine(day+timedelta(days=1),time.min,tz))
            result["deadlineAt"]=min(ends).isoformat()
            result["explanation"]="Просрочка сохранена. Работа разрешена главным инженером в отдельном окне; SLA не переносится."
        except (ValueError,TypeError): return stop("INVALID_LATE_AUTHORIZATION","Проверьте разрешение главного инженера")
    now = datetime.now(tz)
    deadline = datetime.fromisoformat(result["deadlineAt"]).astimezone(tz)
    if deadline <= now:
        return stop("DEADLINE_EXCEEDED", "Обязательный срок прошёл. Нужен ручной разбор без переноса срока.")
    earliest = datetime.fromisoformat(result["earliestAt"]).astimezone(tz)
    if earliest.astimezone(timezone.utc) >= deadline.astimezone(timezone.utc):
        return stop("MAINTENANCE_WINDOW_EMPTY", "Сроки действия оборудования и регламента не оставляют допустимого окна работы.")
    chosen_day = max(earliest.date(), now.date())
    default_start = max(earliest, now, datetime.combine(chosen_day, time(9), tz))
    default_start = default_start.replace(second=0, microsecond=0) + (timedelta(minutes=1) if default_start.second or default_start.microsecond else timedelta())
    default_end = min(deadline, max(datetime.combine(chosen_day, time(17), tz), default_start + timedelta(hours=1)))
    result.update(defaultStartLocal=default_start.replace(tzinfo=None).isoformat(timespec="minutes"),
                  defaultEndLocal=default_end.replace(tzinfo=None).isoformat(timespec="minutes"))
    return result


def assignment_context(v, order):
    return _job(v, order)


def _workers(v, order, start, end, now, worker_ids=None):
    return workers_for_period(v, order.site_id, start, end, now,
                              excluded_task_id=order.work_order_id, worker_ids=worker_ids)


def workers_for_period(v, site_id, start, end, now, *, excluded_task_id=None, worker_ids=None, qualifications=True):
    """Copy resource facts for calculations without requiring a persisted task."""
    from app.scheduling.shifts import expand_shift, employment_availability
    tz = ZoneInfo(v.one("sites", site_id=site_id).timezone)
    day_start = datetime.combine(start.astimezone(tz).date(), time.min, tz)
    last_day = (end.astimezone(timezone.utc) - timedelta(microseconds=1)).astimezone(tz).date()
    day_end = datetime.combine(last_day + timedelta(days=1), time.min, tz)
    member_model, users = v.models["site_memberships"], v.models["users"]
    members_query = (select(member_model, users).join(users, users.user_id == member_model.user_id)
                     .where(member_model.site_id == site_id, member_model.role.in_(("technician", "executor"))))
    if worker_ids is not None:
        members_query = members_query.where(member_model.user_id.in_(worker_ids))
    members = v.session.execute(members_query).all()
    ids = [member.user_id for member, _ in members]
    if not ids:
        return []

    def by_worker(rows, key):
        groups = defaultdict(list)
        for row in rows:
            groups[key(row)].append(row)
        return groups

    def site_rows(table, *filters):
        model = v.models[table]
        return v.session.scalars(select(model).where(model.site_id == site_id, model.user_id.in_(ids), *filters))

    slot = v.models["availability_slots"]
    slots = by_worker(site_rows("availability_slots", slot.starts_at < day_end, slot.ends_at > day_start),
                      lambda row: row.user_id)
    shifts = by_worker(site_rows("employee_shift_rules"), lambda row: row.user_id) if "employee_shift_rules" in v.models.classes else {}
    skills = {}
    if qualifications:
        record, skill = v.models["user_skills"], v.models["skills"]
        facts = v.session.execute(select(record, skill).join(skill, skill.skill_id == record.skill_id)
            .where(record.site_id == site_id, record.user_id.in_(ids)))
        skills = by_worker(facts, lambda row: row[0].user_id)

    # Read other sites' booking intervals for these workers only. Never expose the
    # other site, order or assignment to the consumer of a workload summary.
    assignment, order = v.models["work_assignments"], v.models["work_orders"]
    facts = (select(assignment, order).join(order, and_(order.site_id == assignment.site_id,
             order.work_order_id == assignment.work_order_id))
             .where(assignment.user_id.in_(ids), assignment.status.not_in(("cancelled", "declined")),
                    order.status != "cancelled",
                    or_(order.status == "in_progress", assignment.start_at.is_(None), assignment.end_at.is_(None),
                        and_(order.status.in_(("completed", "in_review")), order.completed_at.is_not(None)),
                        and_(assignment.start_at < day_end, assignment.end_at > day_start))))
    if excluded_task_id is not None:
        facts = facts.where(assignment.work_order_id != excluded_task_id)
    bookings = by_worker(v.session.execute(facts), lambda row: row[0].user_id)
    result = []
    for member, user in members:
        worker = dict(worker_id=user.user_id, site_id=member.site_id, name=user.full_name,
            active=user.is_active, membership_active=member.is_active, can_execute=True,
            booking_data_complete=True, workload_data_complete=True, qualifications=[],
            availability=[dict(start_at=slot.starts_at, end_at=slot.ends_at, status=slot.status)
                          for slot in slots[user.user_id] if getattr(slot,'is_active',True)], bookings=[])
        worker['availability_data_complete'] = bool(worker['availability'])
        for shift in shifts.get(user.user_id, ()):
            if shift.is_active:
                worker['availability_data_complete'] = True
            intervals, _ = expand_shift(shift, day_start.date(), day_end.date(), str(tz))
            worker["availability"].extend(intervals)
        worker["availability"] = employment_availability(worker["availability"],
            getattr(member,"employed_from",None),getattr(member,"employed_until",None),str(tz))
        for record, skill in skills.get(user.user_id, ()):
            worker["qualifications"].append(dict(skill_id=skill.skill_id, verified_at=record.verified_at,
                                                valid_until=record.valid_until, validity_required=skill.validity_required))
        for assignment, other in bookings[user.user_id]:
            completed = other.completed_at is not None and other.status in ("completed", "in_review")
            if completed and other.started_at:
                begin, finish = other.started_at, other.completed_at
            elif other.status != "in_progress" and assignment.start_at is not None and assignment.end_at is not None:
                begin, finish = assignment.start_at, assignment.end_at
            else:
                duration = other.operation_snapshot.get("planning_duration_minutes")
                basis = other.operation_snapshot.get("duration_basis")
                begin = other.started_at if other.status == "in_progress" else other.planned_start_at
                if (begin is None or not isinstance(duration, int) or isinstance(duration, bool) or not 0 < duration <= 46080
                        or not isinstance(basis, str) or not basis.strip()):
                    if completed:
                        if day_start <= other.completed_at < day_end:
                            worker["workload_data_complete"] = False
                    elif assignment.status == "finished":
                        worker["workload_data_complete"] = False
                    else:
                        worker["booking_data_complete"] = False
                    continue
                finish = begin + timedelta(minutes=duration)
            if finish <= begin:
                worker["workload_data_complete"] = False
                continue
            if other.status == "in_progress" and other.completed_at is None and finish <= now:
                worker["booking_data_complete"] = False
            if finish > day_start and begin < day_end:
                worker["bookings"].append(dict(task_id=other.work_order_id, start_at=begin, end_at=finish,
                                                blocks_time=not completed and assignment.status != "finished"))
        result.append(worker)
    return result


def workforce_load(v, day, window_start, window_end, offset, limit):
    from app.assignment.schemas import Worker
    from app.assignment.selection import daily_load

    site_id = v.principal.site_id
    tz = ZoneInfo(v.principal.timezone)
    if (window_start is None) != (window_end is None) or day in (date.min, date.max):
        raise HTTPException(422, "Укажите допустимый день и обе границы окна либо не указывайте окно")
    start = datetime.combine(day, time.min, tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tz)
    window = None
    if window_start is not None:
        window = tuple(local_time(datetime.combine(day, edge), tz) for edge in (window_start, window_end))
        if window[0] >= window[1]:
            raise HTTPException(422, "Конец окна должен быть позже начала")

    member, users = v.models["site_memberships"], v.models["users"]
    candidates = (select(users.user_id).join(member, member.user_id == users.user_id)
                  .where(member.site_id == site_id, member.role.in_(("technician", "executor")),
                         member.is_active.is_(True), users.is_active.is_(True)))
    total = v.session.scalar(select(func.count()).select_from(candidates.subquery()))
    ids = v.session.scalars(candidates.order_by(users.full_name, users.user_id).offset(offset).limit(limit)).all()
    facts = {worker['worker_id']: worker for worker in workers_for_period(v, site_id, start, end,
             datetime.now(timezone.utc), worker_ids=ids, qualifications=False)}
    items = []
    for identity in ids:
        try:
            worker = Worker.model_validate(facts[identity])
        except ValidationError:
            items.append(dict(executorId=identity,name=facts[identity]['name'],loadMinutes=None,windowAvailable=None,
                              reasons=['Некорректные сохранённые рабочие интервалы.']))
            continue
        minutes, available, reasons = daily_load(worker, start, tz, window)
        items.append(dict(executorId=identity, name=worker.name, loadMinutes=minutes, windowAvailable=available, reasons=reasons))
    complete = offset == 0 and len(items) == total
    window_counts = None if window is None else dict(
        available=sum(row['windowAvailable'] is True for row in items),
        unavailable=sum(row['windowAvailable'] is False for row in items),
        unknown=sum(row['windowAvailable'] is None for row in items),
        complete=complete,
    )
    return dict(day=day, timezone=str(tz), windowStart=window[0] if window else None, windowEnd=window[1] if window else None,
                qualificationChecked=False, items=items, total=total, offset=offset, limit=limit,
                page_complete=complete, windowCounts=window_counts)


def assignment_preview(v, order, start_local, end_local, crew_id=None, executor_ids=None, individual_only=False,
                       prefer_low_load=False):
    context = _job(v, order)
    base = dict(context=context, status="needs_input", code=context["code"], explanation=context["explanation"],
                recommendationMode='manual' if executor_ids is not None else 'automatic',
                selectedWorkers=[], workers=[], crews=[], startAt=None, endAt=None, crewId=None,
                crewName=None, planningPersonMinutes=None, command=None)
    if context["status"] != "ready":
        return base
    tz = ZoneInfo(context["timezone"])
    start, end = local_time(start_local, tz), local_time(end_local, tz)
    if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        raise HTTPException(422, "Конец окна должен быть позже начала")
    if (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() > 32 * 86400:
        raise HTTPException(422, "Окно поиска не должно превышать 32 дня")
    crews = [dict(crew_id=crew.crew_id, site_id=crew.site_id, name=crew.name, active=crew.is_active,
        members=[dict(worker_id=member.user_id, valid_from=member.valid_from, valid_to=member.valid_to)
                 for member in v.rows("crew_members", crew_id=crew.crew_id)]) for crew in v.rows("crews")]
    if crew_id is not None and not any(crew["crew_id"] == crew_id for crew in crews):
        raise HTTPException(404, "Бригада не найдена")
    if individual_only:
        if crew_id is not None: raise HTTPException(422,'Выберите бригаду либо индивидуальных работников')
        crews=[]
    now = datetime.now(timezone.utc)
    payload = dict(schema_version="maintenance-0.1", data_origin=context["dataOrigin"],
        task_id=order.work_order_id, site_id=order.site_id, expected_revision=order.revision,
        timezone=context["timezone"], as_of=now, window=dict(start_at=start, end_at=end),
        earliest_at=context["earliestAt"], deadline_at=context["deadlineAt"],
        duration_minutes=context["durationMinutes"], duration_basis=context["durationBasis"],
        crew_size=context["crewSize"], qualification_ids=context["qualificationIds"],
        workers=_workers(v, order, start, end, now), crews=crews, crew_id=crew_id,requested_worker_ids=executor_ids,
        prefer_low_load=prefer_low_load)
    if executor_ids is not None:
        if len(executor_ids) != context['crewSize'] or len(set(executor_ids)) != len(executor_ids):
            raise HTTPException(422, 'Выберите полный состав без повторов по требуемой численности')
        if not set(executor_ids) <= {worker['worker_id'] for worker in payload['workers']}:
            raise HTTPException(404, 'Работник не найден среди исполнителей объекта')
    try:
        result = select_crew(AssignmentRequest.model_validate_json(json.dumps(payload, default=_json_value)))
    except ValidationError:
        base.update(code="INVALID_PERSISTED_INPUT", explanation="Некорректные сведения о длительности, доступности или допусках. Уточните исходные данные.")
        return base
    command = result.command
    base.update(status=result.status, code=result.error_code, explanation=result.explanation,
        planningPersonMinutes=result.planning_person_minutes,
        startAt=command.start_at.isoformat() if command else None,
        endAt=command.end_at.isoformat() if command else None,
        command=json.loads(command.model_dump_json()) if command else None,
        crewId=str(result.crew_id) if result.crew_id else None,
        crewName=next((crew["name"] for crew in crews if crew["crew_id"] == result.crew_id), None),
        workers=[dict(executorId=str(worker.worker_id), name=worker.name, status=worker.status,
            reasons=worker.reasons, explanation=worker.explanation, loadMinutes=worker.load_minutes,
            earliestStart=worker.earliest_start.isoformat() if worker.earliest_start else None) for worker in result.workers],
        crews=[dict(id=str(crew.crew_id), name=crew.name, available=crew.available, explanation=crew.explanation) for crew in result.crews])
    base["selectedWorkers"] = [worker for worker in base["workers"] if worker["status"] == "selected"]
    base["workers"].sort(key=lambda worker:(0 if worker['status']=='selected' else 1 if worker['status']=='available' else 2,
        worker['earliestStart'] or '9999',worker['loadMinutes'] if worker['loadMinutes'] is not None else float('inf'),worker['executorId']))
    return base
