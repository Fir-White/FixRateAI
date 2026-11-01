"""Interval algebra and deterministic complete-crew selection for ALG03."""
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo

from app.schemas.maintenance import AssignmentCommand
from .schemas import AssignmentRequest, AssignmentSelection, CrewDecision, WorkerDecision

METHOD_VERSION = "crew-selection-v1"
REASONS = {
    "INACTIVE_USER": "Учётная запись неактивна.",
    "SITE_ACCESS_MISSING": "Нет действующего доступа к объекту.",
    "EXECUTOR_ROLE_REQUIRED": "Нет роли исполнителя.",
    "BOOKING_UNCONFIRMED": "У действующего назначения не определён интервал занятости.",
    "WORKLOAD_UNCONFIRMED": "Недостаточно данных для оценки загрузки в выбранные дни.",
    "QUALIFICATION_MISMATCH": "Нет требуемой квалификации.",
    "QUALIFICATION_UNVERIFIED": "Квалификация не подтверждена.",
    "QUALIFICATION_EXPIRY_MISSING": "Для допуска не указан обязательный срок действия.",
    "QUALIFICATION_OUTSIDE_WINDOW": "Допуск не действует в требуемом интервале.",
    "NO_AVAILABILITY": "Не заданы доступные рабочие интервалы.",
    "NO_FREE_INTERVAL": "Нет свободного интервала достаточной длительности.",
    "CREW_MEMBERSHIP_OUTSIDE_WINDOW": "Нет подходящего периода участия в выбранной бригаде.",
}


def _utc(value):
    return value.astimezone(timezone.utc)


def _merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _intersect(left, right):
    result = []
    for a, b in left:
        for c, d in right:
            if max(a, c) < min(b, d):
                result.append((max(a, c), min(b, d)))
    return _merge(result)


def _subtract(intervals, exclusions):
    result = intervals
    for start, end in _merge(exclusions):
        updated = []
        for a, b in result:
            if end <= a or start >= b:
                updated.append((a, b))
            else:
                if a < start:
                    updated.append((a, start))
                if end < b:
                    updated.append((end, b))
        result = updated
    return result


def _day_start(day, tz):
    return _utc(datetime.combine(day, time.min, tz))


def _validity(start, end_day, window, tz):
    end = window[1] if end_day is None or end_day == date.max else _day_start(end_day + timedelta(days=1), tz)
    return _intersect([window], [(_utc(start), end)])


def _ceil_minute(value):
    rounded = value.replace(second=0, microsecond=0)
    return rounded if rounded == value else rounded + timedelta(minutes=1)


def _load(worker, start, tz, excluded_task):
    day = start.astimezone(tz).date()
    bounds = [(_day_start(day, tz), _day_start(day + timedelta(days=1), tz))]
    intervals = _intersect(_merge([(_utc(b.start_at), _utc(b.end_at)) for b in worker.bookings if b.task_id != excluded_task]), bounds)
    return ceil(sum((end - begin).total_seconds() for begin, end in intervals) / 60)


def select_crew(request: AssignmentRequest) -> AssignmentSelection:
    """Choose the earliest complete team, then least daily load and stable IDs.

    All work is a recommendation. command is a canonical AssignmentCommand for
    a later transactional revalidation, never a persisted Assignment.
    """
    tz = ZoneInfo(request.timezone)
    decisions, crew_decisions = [], []

    def finish(status, code, explanation, command=None, crew_id=None):
        return AssignmentSelection(schema_version=request.schema_version, data_origin=request.data_origin,
            method_version=METHOD_VERSION, status=status, error_code=code, explanation=explanation,
            command=command, crew_id=crew_id,
            planning_person_minutes=request.crew_size * request.duration_minutes if command else None,
            workers=decisions, crews=crew_decisions)

    if request.duration_minutes is None or not request.duration_basis:
        return finish("needs_input", "DURATION_UNCONFIRMED", "Нужны подтверждённая длительность работы и основание. Нормо-часы не заменяют длительность.")
    if request.earliest_at is None or request.deadline_at is None:
        return finish("needs_input", "MAINTENANCE_WINDOW_UNCONFIRMED", "Не определено допустимое окно обслуживания.")
    if _utc(request.deadline_at) <= _utc(request.as_of):
        return finish("manual_review", "DEADLINE_EXCEEDED", "Обязательный срок прошёл. Требуется ручной разбор, без переноса срока.")
    start = _ceil_minute(max(_utc(request.window.start_at), _utc(request.earliest_at), _utc(request.as_of)))
    end = min(_utc(request.window.end_at), _utc(request.deadline_at))
    duration = timedelta(minutes=request.duration_minutes)
    if end <= start or end - start < duration:
        return finish("unavailable", "WINDOW_TOO_SHORT", "В допустимом окне нет времени для полного выполнения работы.")
    window = (start, end)
    workers = {worker.worker_id: worker for worker in request.workers}
    free, failures = {}, {}
    for worker in sorted(request.workers, key=lambda w: w.worker_id.int):
        reasons = []
        if not worker.active:
            reasons.append("INACTIVE_USER")
        if worker.site_id != request.site_id or not worker.membership_active:
            reasons.append("SITE_ACCESS_MISSING")
        if not worker.can_execute:
            reasons.append("EXECUTOR_ROLE_REQUIRED")
        if not worker.booking_data_complete:
            reasons.append("BOOKING_UNCONFIRMED")
        if not worker.workload_data_complete:
            reasons.append("WORKLOAD_UNCONFIRMED")
        intervals = [window]
        for skill_id in sorted(request.qualification_ids, key=lambda skill: skill.int):
            certificates = [q for q in worker.qualifications if q.skill_id == skill_id]
            if not certificates:
                reasons.append("QUALIFICATION_MISMATCH")
                continue
            valid = []
            for certificate in certificates:
                if certificate.verified_at is None or _utc(certificate.verified_at) > _utc(request.as_of):
                    continue
                if certificate.validity_required and certificate.valid_until is None:
                    continue
                valid.extend(_validity(certificate.verified_at, certificate.valid_until, window, tz))
            if not valid:
                reasons.append("QUALIFICATION_UNVERIFIED" if all(q.verified_at is None or _utc(q.verified_at) > _utc(request.as_of) for q in certificates)
                    else "QUALIFICATION_EXPIRY_MISSING" if all(q.validity_required and q.valid_until is None for q in certificates)
                    else "QUALIFICATION_OUTSIDE_WINDOW")
            intervals = _intersect(intervals, _merge(valid))
        available = _merge([(_utc(slot.start_at), _utc(slot.end_at)) for slot in worker.availability if slot.status == "available"])
        if not available:
            reasons.append("NO_AVAILABILITY")
        intervals = _intersect(intervals, available)
        exclusions = [(_utc(slot.start_at), _utc(slot.end_at)) for slot in worker.availability if slot.status == "unavailable"]
        exclusions += [(_utc(b.start_at), _utc(b.end_at)) for b in worker.bookings if b.blocks_time and b.task_id != request.task_id]
        intervals = _subtract(intervals, exclusions)
        intervals = [(a, b) for a, b in intervals if b - _ceil_minute(a) >= duration]
        if not intervals and not reasons:
            reasons.append("NO_FREE_INTERVAL")
        free[worker.worker_id] = intervals if not reasons else []
        failures[worker.worker_id] = list(dict.fromkeys(reasons))

    def best(pool):
        if request.requested_worker_ids is not None:
            pool={worker_id:intervals for worker_id,intervals in pool.items() if worker_id in request.requested_worker_ids}
        starts = sorted({_ceil_minute(a) for intervals in pool.values() for a, _ in intervals})
        for begin in starts:
            finish_at = begin + duration
            eligible = [worker_id for worker_id, intervals in pool.items() if any(a <= begin and finish_at <= b for a, b in intervals)]
            if len(eligible) >= request.crew_size:
                selected = sorted(eligible, key=lambda worker_id: (_load(workers[worker_id], begin, tz, request.task_id), worker_id.int))[:request.crew_size]
                return begin, finish_at, selected
        return None

    options = []
    if request.crew_id is None:
        option = best(free)
        if option:
            options.append((*option, None))
    for crew in sorted(request.crews, key=lambda c: c.crew_id.int):
        pool = {}
        if crew.active and crew.site_id == request.site_id:
            for member in crew.members:
                membership = _validity(_day_start(member.valid_from, tz), member.valid_to, window, tz)
                pool[member.worker_id] = _merge(pool.get(member.worker_id, []) + _intersect(free.get(member.worker_id, []), membership))
        option = best(pool)
        crew_decisions.append(CrewDecision(crew_id=crew.crew_id, name=crew.name, available=option is not None,
            explanation="Есть полный состав на общем интервале." if option else "Нет полного доступного состава с нужными допусками и периодом участия."))
        if option and (request.crew_id is None or request.crew_id == crew.crew_id):
            options.append((*option, crew.crew_id))
    chosen = min(options, key=lambda option: (option[0], sum(_load(workers[w], option[0], tz, request.task_id) for w in option[2]),
        tuple(sorted(w.int for w in option[2])), 0 if option[3] is not None else 1,
        option[3].int if option[3] is not None else 0)) if options else None
    load_day = chosen[0] if chosen else start
    chosen_ids = set(chosen[2]) if chosen else set()
    for worker in sorted(request.workers, key=lambda w: w.worker_id.int):
        reasons = failures[worker.worker_id]
        intervals = free[worker.worker_id]
        if request.crew_id is not None:
            crew = next((c for c in request.crews if c.crew_id == request.crew_id and c.active and c.site_id == request.site_id), None)
            membership = _merge([interval for member in crew.members if member.worker_id == worker.worker_id
                for interval in _validity(_day_start(member.valid_from, tz), member.valid_to, window, tz)]) if crew else []
            intervals = _intersect(intervals, membership)
            if not any(b - _ceil_minute(a) >= duration for a, b in intervals) and not reasons:
                reasons = ["CREW_MEMBERSHIP_OUTSIDE_WINDOW"]
        selected = worker.worker_id in chosen_ids
        decisions.append(WorkerDecision(worker_id=worker.worker_id, name=worker.name,
            status="selected" if selected else "excluded" if reasons else "available", reasons=reasons,
            explanation=("Выбран диспетчером; доступность и допуски проверены." if request.requested_worker_ids is not None else "Выбран полный состав по времени, дневной загрузке и стабильному порядку ID.") if selected
                else " ".join(REASONS[reason] for reason in reasons) if reasons
                else "Есть допустимое время; другой состав выбран по времени, нагрузке и порядку ID.",
            load_minutes=None if not worker.workload_data_complete or not worker.booking_data_complete else _load(worker, load_day, tz, request.task_id),
            earliest_start=_ceil_minute(intervals[0][0]).astimezone(tz) if intervals else None))
    if chosen is None:
        return finish("unavailable", "INSUFFICIENT_CAPACITY", "Полная бригада на общем допустимом интервале не найдена. Частичный состав не предлагается.")
    begin, finish_at, selected, crew_id = chosen
    reason = ("Состав выбран диспетчером; найден общий допустимый интервал, проверены доступность, допуски и загрузка."
              if request.requested_worker_ids is not None else "Самый ранний общий интервал; среди доступных — минимальная дневная загрузка, затем ID.")
    command = AssignmentCommand(schema_version=request.schema_version, expected_revision=request.expected_revision,
        executor_ids=selected, start_at=begin.astimezone(tz), end_at=finish_at.astimezone(tz), reason=reason)
    return finish("ok", None, reason, command, crew_id)
