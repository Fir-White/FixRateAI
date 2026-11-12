"""ALG02: generate draft obligations; never write plans, tasks or assignments."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from app.schemas.maintenance import PlanOccurrence, RecurrenceRule
from app.schemas.maintenance_api import CalendarOccurrence, CalendarResponse
from .schemas import (
    BindingGenerationResult, CalendarGenerationRequest, CalendarGenerationResult,
    GeneratedOccurrence, SchedulingBinding,
)
from .recurrence import occurrence_pairs, pattern_description, shifted_date

METHOD_VERSION = "calendar-rules-v3"
# Stable identity uses the original obligation date, before weekend transfer.
OCCURRENCE_NAMESPACE = UUID("e12253b2-143e-5a55-a4c4-875fdb3a7a3f")


def _add_months(anchor: date, months: int) -> date:
    index = anchor.year * 12 + anchor.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(anchor.day, monthrange(year, month)[1]))


def _fixed_dates(rule: RecurrenceRule, start: date, end: date) -> list[date]:
    anchor, interval = rule.anchor_date, rule.interval
    if anchor > end:
        return []
    if rule.calendar_unit == "day":
        first = max(0, ((start - anchor).days + interval - 1) // interval)
        last = (end - anchor).days // interval
        return [anchor + timedelta(days=n * interval) for n in range(first, last + 1)]
    # Every date is computed from the original anchor: Jan 31 -> Apr 30 -> Jul 31.
    first = max(0, ((start.year - anchor.year) * 12 + start.month - anchor.month) // interval)
    last = ((end.year - anchor.year) * 12 + end.month - anchor.month) // interval
    return [day for n in range(first, last + 1)
            if start <= (day := _add_months(anchor, n * interval)) <= end]


def _person_hours(item: SchedulingBinding) -> Decimal | None:
    op = item.operation
    if op.raw_norm_value is None or op.norm_unit == "unconfirmed":
        return None
    if op.norm_unit == "person_hour":
        return op.raw_norm_value
    # Preserve Decimal precision even if a caller changed the process-wide context.
    with localcontext() as ctx:
        ctx.prec = max(28, len(str(op.crew_size)) + 12)
        return op.raw_norm_value * op.crew_size


def _generate_binding(item: SchedulingBinding, start: date, end: date,
                      as_of: datetime, tz: ZoneInfo) -> BindingGenerationResult:
    rule, op, binding = item.rule, item.operation, item.binding
    today = as_of.astimezone(tz).date()
    synthetic = item.equipment.data_origin == "synthetic_demo"
    warnings = ["SYNTHETIC_DATA"] if synthetic else []
    is_assumption = synthetic or bool(item.assumptions)
    next_due = None
    pairs = None

    def result(status, code, explanation, occurrences=None):
        entries = occurrences or []
        known_dates = status in ("ok", "skipped", "manual_review")
        hours = [e.required_person_hours for e in entries]
        minutes = [e.planning_person_minutes for e in entries]
        with localcontext() as ctx:
            ctx.prec = max(28, len(str(op.crew_size)) + 16)
            total_hours = sum(hours, Decimal("0")) if known_dates and all(h is not None for h in hours) else None
        return BindingGenerationResult(
            binding_id=binding.binding_id, status=status, error_code=code,
            explanation=explanation, warnings=warnings.copy(), assumptions=item.assumptions.copy(),
            is_assumption=is_assumption, next_due_date=next_due, occurrences=entries,
            total_person_hours=total_hours,
            total_planning_person_minutes=sum(minutes) if known_dates and all(m is not None for m in minutes) else None,
        )

    if item.equipment.state == "retired":
        return result("skipped", "EQUIPMENT_RETIRED", "Оборудование выведено из эксплуатации.")
    if item.equipment.state == "out_of_service":
        warnings.append("EQUIPMENT_OUT_OF_SERVICE")
    activation_dates = [d for d in (binding.effective_from, item.equipment.commissioned_on) if d is not None]
    if not activation_dates:
        return result("needs_input", "ACTIVATION_DATE_MISSING", "Не задано начало действия привязки или дата ввода оборудования.")
    activation = max(activation_dates)
    active_start = max(start, activation)
    active_end = min(end, binding.effective_to or end)
    if active_start > active_end:
        return result("skipped", "OUTSIDE_ACTIVE_PERIOD", "В выбранном месяце привязка не действует.")
    if op.status != "approved":
        return result("needs_input", "OPERATION_UNAPPROVED", "Версия операции не утверждена.")
    if not rule.confirmed:
        return result("needs_input", "RULE_UNCONFIRMED", "Периодичность не определяет даты без подтверждённых параметров правила.")
    daily = (rule.kind == "calendar_interval" and rule.calendar_unit == "day" and rule.interval == 1) or (rule.kind == "calendar_pattern" and rule.pattern.frequency=="day" and rule.pattern.interval==1)
    if daily and ((rule.kind=="calendar_interval" and rule.basis != "fixed_calendar") or rule.allowed_lead_days != 0):
        return result("needs_input", "INVALID_DAILY_RULE", "Ежедневное ТО требует fixed_calendar и нулевого раннего допуска.")
    if op.norm_unit == "unconfirmed":
        warnings.append("NORM_UNIT_UNCONFIRMED")
    if op.raw_norm_value is None:
        warnings.append("NORM_VALUE_MISSING")
    if op.planning_duration_minutes is None:
        warnings.append("DURATION_UNCONFIRMED")
    cutoff = as_of.astimezone(timezone.utc)
    history = [e for e in item.accepted_events if e.accepted_at.astimezone(timezone.utc) <= cutoff]
    if len(history) != len(item.accepted_events):
        warnings.append("HISTORY_AFTER_CUTOFF_IGNORED")
    if rule.kind == "runtime":
        return result("needs_input", "RUNTIME_DATE_UNAVAILABLE", "Наработка задаёт порог в часах; текущий контракт не задаёт режим для расчёта календарной даты.")

    status, code = "ok", None
    if rule.kind == "calendar_pattern":
        try:
            pairs = occurrence_pairs(rule.pattern, active_start, active_end)
            dates = [day for _,day in pairs]
        except ValueError as exc:
            return result('needs_input','CALENDAR_PATTERN_UNSATISFIABLE',str(exc))
        explanation = pattern_description(rule.pattern)
    elif rule.kind == "explicit_dates":
        year_dates = [d for d in rule.explicit_dates if d.year == start.year]
        if not year_dates:
            return result("needs_input", "YEAR_DATES_MISSING", "Для выбранного года не заданы утверждённые даты.")
        dates = [d for d in year_dates if active_start <= d <= active_end]
        explanation = "Явные даты подтверждённого годового правила; равномерный шаг не выводится из частоты."
    elif rule.basis == "fixed_calendar":
        dates = _fixed_dates(rule, active_start, active_end)
        explanation = f"Фиксированный календарь от {rule.anchor_date}: шаг {rule.interval} {rule.calendar_unit}; политика выходных: {rule.weekend_policy}."
    else:
        if history:
            last = max(history, key=lambda e: (e.performed_at.astimezone(timezone.utc), e.service_event_id.int))
            baseline = last.performed_at.astimezone(tz).date()
            try:
                next_due = (baseline + timedelta(days=rule.interval) if rule.calendar_unit == "day"
                            else _add_months(baseline, rule.interval))
            except (ValueError, OverflowError):
                return result("needs_input", "DATE_OUT_OF_RANGE", "Следующая дата выходит за поддерживаемый календарь.")
            explanation = f"Следующее ТО от фактического выполнения {baseline}, принятого до as_of; дата приёмки не сдвигает срок."
        else:
            next_due = rule.anchor_date
            explanation = f"Принятой истории нет; {next_due} — явно заданный первый срок (anchor_date)."
        if next_due < activation:
            return result("needs_input", "DUE_BEFORE_ACTIVATION", "Первый срок раньше начала обслуживания; требуется уточнить опорные данные.")
        # A second rolling occurrence would assume a future completion that has not happened.
        source_due = next_due
        next_due = shifted_date(rule, source_due)
        pairs = [(source_due, next_due)] if active_start <= source_due <= active_end else []
        dates = [effective for _, effective in pairs]
        warnings.append("ROLLING_NEXT_OCCURRENCE_ONLY")
        if next_due < today:
            status, code = "manual_review", "OVERDUE_REQUIRES_REVIEW"
        if not dates:
            warnings.append("NEXT_DUE_OUTSIDE_MONTH")

    hours = _person_hours(item)
    person_minutes = op.planning_duration_minutes * op.crew_size if op.planning_duration_minutes is not None else None
    entries = []
    if pairs is None:
        pairs = [(day, shifted_date(rule, day)) for day in dates]
    for source_day,day in pairs:
        if binding.effective_to is not None and day > binding.effective_to:
            return result("needs_input", "TRANSFER_OUTSIDE_VALIDITY",
                          "Перенос выходит за срок действия привязки. Уточните регламент; задание не создаётся.")
        lead = min(rule.allowed_lead_days, (day - date.min).days)
        occurrence = PlanOccurrence(
            occurrence_id=uuid5(OCCURRENCE_NAMESPACE, f"{binding.binding_id}:{rule.rule_version_id}:{source_day.isoformat()}"),
            binding_id=binding.binding_id, rule_version_id=rule.rule_version_id,
            operation_version_id=op.operation_version_id, source_date=source_day,occurrence_date=day,
            earliest_date=max(activation, day - timedelta(days=lead)), mandatory_due_date=day,
            runtime_due_at_hours=None, status="draft", revision=1, task_id=None,
        )
        entries.append(GeneratedOccurrence(
            occurrence=occurrence, explanation=f"Обязательство за {source_day.isoformat()}, выполнение {day.isoformat()}: {explanation}",
            deadline_passed=day < today, is_assumption=is_assumption,
            required_person_hours=hours, planning_person_minutes=person_minutes,
        ))
    return result(status, code, explanation, entries)


def generate_month(request: CalendarGenerationRequest) -> CalendarGenerationResult:
    """Return deterministic draft dates and per-binding diagnostics, with no I/O.

    Accepted events must already be scoped to this binding/operation by the caller.
    The function filters their acceptance cutoff, but cannot infer resource IDs
    absent from AcceptedEvent. No persisted lifecycle state is inferred or changed.
    """
    query = request.query
    start = date(query.year, query.month, 1)
    end = date(query.year, query.month, monthrange(query.year, query.month)[1])
    tz = ZoneInfo(request.site.timezone)
    results, calendar_items = [], []
    for item in sorted(request.bindings, key=lambda b: b.binding.binding_id.int):
        generated = _generate_binding(item, start, end, request.as_of, tz)
        results.append(generated)
        op = item.operation
        for entry in generated.occurrences:
            occurrence = entry.occurrence
            calendar_items.append(CalendarOccurrence(
                occurrence_id=occurrence.occurrence_id, equipment_id=item.equipment.equipment_id,
                operation_version_id=op.operation_version_id,source_date=occurrence.source_date, occurrence_date=occurrence.occurrence_date,
                maintenance_type=op.maintenance_type, recurrence=item.rule.source_text,
                crew_size=op.crew_size, raw_norm_value=op.raw_norm_value, norm_unit=op.norm_unit,
                planning_duration_minutes=op.planning_duration_minutes,
                source_ref=item.rule.source_ref, planned_task_id=None, actual_execution_id=None,
                status="draft",
            ))
    calendar_items.sort(key=lambda x: (x.occurrence_date, x.equipment_id.int,
                                      x.operation_version_id.int, x.occurrence_id.int))
    return CalendarGenerationResult(
        schema_version="maintenance-0.1", data_origin=request.site.data_origin,
        method_version=METHOD_VERSION, as_of=request.as_of,
        calendar=CalendarResponse(site_id=query.site_id, year=query.year, month=query.month,
                                  timezone=request.site.timezone, items=calendar_items, total=len(calendar_items)),
        bindings=results,
    )
