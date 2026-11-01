"""Read-only PostgreSQL boundary for the ALG02 calendar preview."""
from calendar import monthrange
from datetime import date, datetime, timezone
import json

from pydantic import ValidationError

from app.scheduling import CalendarGenerationRequest, generate_month


def _json_value(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def _binding_payload(v, binding, rule, equipment, site):
    op, edition = rule.operation, rule.edition
    parameters = rule.schedule_parameters
    origin = rule.data_origin
    checks = {}
    for check in v.rows("checklist_templates", operation_template_id=op.operation_template_id):
        prior = checks.get(check.item_code)
        if prior is None or check.template_version > prior.template_version:
            checks[check.item_code] = check
    if not checks:
        return None, "CHECKLIST_MISSING", "У операции не задан чек-лист. Завершите описание регламента."
    if any(check.input_kind not in ("checkbox", "number", "text") for check in checks.values()):
        return None, "CHECKLIST_TYPE_UNSUPPORTED", "Тип пункта чек-листа требует согласования с контрактом операции."
    if not equipment.equipment_type_id:
        return None, "EQUIPMENT_TYPE_MISSING", "Для оборудования не задан тип."
    if equipment.properties.get("data_origin") != origin:
        return None, "DATA_ORIGIN_MISMATCH", "Происхождение оборудования и регламента различается. Проверьте привязку."

    if rule.period_unit == "year" and rule.period_count == 1:
        recurrence = dict(kind="explicit_dates", interval=None, calendar_unit=None, anchor_date=None,
                          basis=None, explicit_dates=parameters.get("explicit_dates", []),
                          yearly_count=rule.occurrences_per_period)
    elif (rule.scheduling_mode == "fixed_interval" and rule.occurrences_per_period == 1
          and rule.period_unit in ("day", "month", "quarter")):
        recurrence = dict(kind="calendar_interval", interval=rule.period_count * (3 if rule.period_unit == "quarter" else 1),
                          calendar_unit="day" if rule.period_unit == "day" else "month",
                          anchor_date=parameters.get("anchor_date"), basis=parameters.get("basis"),
                          explicit_dates=[], yearly_count=None)
    else:
        return None, "RULE_PARAMETERS_MISSING", "Частота не определяет точные даты. Уточните способ отсчёта и календарные параметры."
    starts = [binding.valid_from, rule.active_from, edition.effective_from]
    ends = [day for day in (binding.valid_to, rule.active_until, edition.effective_to) if day is not None]
    history = []
    for link in v.rows("work_order_equipment", equipment_id=equipment.equipment_id):
        order = v.one("work_orders", work_order_id=link.work_order_id)
        if not order.completed_at or not order.maintenance_rule_id:
            continue
        past_rule = v.one("maintenance_rules", maintenance_rule_id=order.maintenance_rule_id)
        past_origin = order.operation_snapshot.get("data_origin") or past_rule.data_origin
        if past_rule.operation_template_id != op.operation_template_id or past_origin != origin:
            continue
        for review in v.rows("acceptance_reviews", work_order_id=order.work_order_id):
            if review.decision == "accepted":
                history.append(dict(service_event_id=review.acceptance_review_id, performed_at=order.completed_at,
                                    accepted_at=review.reviewed_at, runtime_hours=None, observed_need_date=None))
    typ = v.one("maintenance_types", maintenance_type_id=op.maintenance_type_id)
    norm_unit = parameters.get("norm_unit", {"total_person_hours": "person_hour"}.get(rule.norm_hours_basis, "unconfirmed"))
    payload = dict(
        binding=dict(schema_version="maintenance-0.1", data_origin=origin, source_ref=rule.source_ref,
            binding_id=binding.binding_id, revision=binding.revision, equipment_id=equipment.equipment_id,
            operation_version_id=rule.maintenance_rule_id, rule_version_id=rule.maintenance_rule_id,
            regulation_version_id=edition.regulation_edition_id, effective_from=max(starts),
            effective_to=min(ends) if ends else None, baseline_runtime_hours=binding.baseline_runtime_hours),
        equipment=dict(schema_version="maintenance-0.1", data_origin=origin, equipment_id=equipment.equipment_id,
            site_id=site.site_id, equipment_type_id=equipment.equipment_type_id, inventory_code=equipment.asset_code,
            name=equipment.name, commissioned_on=equipment.commissioned_on,
            state={"under_repair": "out_of_service"}.get(equipment.status, equipment.status), revision=equipment.revision),
        operation=dict(schema_version="maintenance-0.1", data_origin=origin, operation_id=op.operation_template_id,
            operation_version_id=rule.maintenance_rule_id, version=rule.rule_version, code=op.code,
            title=op.title, maintenance_type=typ.name, instructions=op.description or op.title,
            crew_size=rule.required_people, raw_norm_value=rule.norm_hours, norm_unit=norm_unit,
            planning_duration_minutes=parameters.get("planning_duration_minutes"), duration_basis=parameters.get("duration_basis"),
            qualification_ids=sorted([row.skill_id for row in v.rows("rule_required_skills", maintenance_rule_id=rule.maintenance_rule_id)], key=lambda value:value.int),
            checklist=[dict(checklist_item_id=check.checklist_template_id, text=check.prompt,
                answer_kind={"checkbox": "boolean", "number": "number", "text": "text"}[check.input_kind],
                unit=check.unit_code, required=check.is_required,
                visual_verifiability="not_verifiable", photo_required=False)
                for check in sorted(checks.values(), key=lambda c: (c.position, c.item_code))],
            status="approved", source_ref=rule.source_ref),
        rule=dict(schema_version="maintenance-0.1", data_origin=origin, rule_version_id=rule.maintenance_rule_id,
            regulation_version_id=edition.regulation_edition_id, source_text=rule.source_text,
            confirmed=True, runtime_interval_hours=None, allowed_lead_days=parameters.get("allowed_lead_days", 0),
            source_ref=rule.source_ref, **recurrence),
        accepted_events=sorted(history, key=lambda event:(event["performed_at"],event["accepted_at"],event["service_event_id"].int)), assumptions=parameters.get("assumptions", []),
    )
    return payload, None, None


def preview_calendar(v, year, month, *, as_of=None):
    """Build inputs on the server; do not trust client-supplied rules or approvals."""
    now = as_of or datetime.now(timezone.utc)
    site = v.one("sites", site_id=v.principal.site_id)
    first, last = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    items, diagnostics = [], []
    for binding in sorted(v.rows("rule_equipment"), key=lambda b: b.binding_id.int):
        rule, equipment = binding.rule, binding.equipment
        op = rule.operation
        diagnostic = dict(bindingId=str(binding.binding_id), equipmentName=equipment.name,
            operationCode=op.code, operationTitle=op.title, dataOrigin=rule.data_origin,
            status="needs_input", code=None, explanation="", warnings=[], isAssumption=rule.data_origin == "synthetic_demo",
            occurrencesCount=0, totalPersonHours=None, totalPlanningPersonMinutes=None, nextDueDate=None)
        diagnostics.append(diagnostic)
        ends = [d for d in (binding.valid_to, rule.active_until, rule.edition.effective_to) if d is not None]
        starts = [binding.valid_from, rule.active_from, rule.edition.effective_from]
        if (equipment.status == "retired" or not op.is_active or rule.publication_status == "archived"
                or max(starts) > last or (ends and min(ends) < first)):
            diagnostic.update(status="skipped", code="OUTSIDE_ACTIVE_PERIOD", explanation="В выбранном месяце обслуживание по этой привязке не действует.")
            continue
        if rule.publication_status != "published" or not rule.edition.is_approved:
            diagnostic.update(code="RULE_UNCONFIRMED", explanation="Регламент или его редакция не утверждены. Подтвердите параметры и даты перед расчётом.")
            continue
        payload, code, explanation = _binding_payload(v, binding, rule, equipment, site)
        if payload is None:
            diagnostic.update(code=code, explanation=explanation)
            continue
        origin = rule.data_origin
        request = dict(schema_version="maintenance-0.1",
            site=dict(schema_version="maintenance-0.1", data_origin=origin, site_id=site.site_id,
                      name=site.name, address=site.address or "Адрес не указан", timezone=site.timezone),
            query=dict(site_id=site.site_id, year=year, month=month, include_cancelled=False),
            as_of=now, bindings=[payload])
        try:
            result = generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(request, default=_json_value)))
        except ValidationError:
            diagnostic.update(code="INVALID_PERSISTED_INPUT", explanation="Параметры регламента неполные или противоречат контракту. Проверьте даты, способ отсчёта, длительность и годовой список.")
            continue
        generated = result.bindings[0]
        diagnostic.update(status=generated.status, code=generated.error_code, explanation=generated.explanation,
            warnings=generated.warnings, isAssumption=generated.is_assumption,
            occurrencesCount=len(generated.occurrences),
            totalPersonHours=str(generated.total_person_hours) if generated.total_person_hours is not None else None,
            totalPlanningPersonMinutes=generated.total_planning_person_minutes,
            nextDueDate=generated.next_due_date.isoformat() if generated.next_due_date else None)
        for calendar_item, detail in zip(result.calendar.items, generated.occurrences, strict=True):
            occurrence = detail.occurrence
            items.append(dict(id=str(calendar_item.occurrence_id), bindingId=str(binding.binding_id), occurrenceDate=calendar_item.occurrence_date.isoformat(),
                equipmentId=str(equipment.equipment_id), equipmentName=equipment.name, operationCode=op.code,
                operationTitle=op.title, maintenanceType=calendar_item.maintenance_type, status="draft",
                isOverdue=False, requiresInput=False, taskId=None,
                explanation=detail.explanation, earliestDate=occurrence.earliest_date.isoformat(),
                mandatoryDueDate=occurrence.mandatory_due_date.isoformat(), deadlinePassed=detail.deadline_passed,
                crewSize=calendar_item.crew_size, rawNormValue=str(calendar_item.raw_norm_value) if calendar_item.raw_norm_value is not None else None,
                normUnit=calendar_item.norm_unit, planningDurationMinutes=calendar_item.planning_duration_minutes,
                requiredPersonHours=str(detail.required_person_hours) if detail.required_person_hours is not None else None,
                dataOrigin=origin, isAssumption=detail.is_assumption))
    items.sort(key=lambda item: (item["occurrenceDate"], item["equipmentId"], item["operationCode"], item["id"]))
    from .planning import source_token
    return dict(year=year, month=month, timezone=site.timezone, calculatedAt=now.isoformat(), items=items, diagnostics=diagnostics,
                generationToken=source_token(v, year, month, now))
