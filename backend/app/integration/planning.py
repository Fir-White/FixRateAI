"""ALG05/06: preview-confirmed, idempotent generation; no implicit assignment."""
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import time as timer
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, text

from app.db.session import service_transaction
from .assignment import assignment_preview
from .calendar import _json_value, preview_calendar
from .forecasting import binding_input, make_snapshot, calculate, persist_comparison

NAMESPACE = UUID("36322ca8-1c5f-46d1-a23c-b09d47d1a090")
SOURCE_TABLES = ("equipment", "maintenance_rules", "regulation_editions", "operation_templates",
                 "rule_equipment", "checklist_templates", "rule_required_skills")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=_json_value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def source_token(v, year, month, now):
    site = v.one("sites", site_id=v.principal.site_id)
    facts = dict(year=year, month=month, day=str(now.astimezone(ZoneInfo(site.timezone)).date()), timezone=site.timezone,
                 site=str(site.site_id), name=site.name, address=site.address, active=site.is_active)
    for name in SOURCE_TABLES:
        cls = v.models[name]
        rows = v.rows(name)
        facts[name] = sorted([{column.name: getattr(row, column.name) for column in cls.__table__.columns} for row in rows], key=digest)
    reviews = [row for row in v.rows("acceptance_reviews") if row.decision == "accepted" and row.reviewed_at <= now]
    ids = {row.work_order_id for row in reviews}
    facts["accepted"] = sorted([(str(row.acceptance_review_id), str(row.work_order_id), row.reviewed_at) for row in reviews])
    facts["completed"] = sorted([(str(row.work_order_id), str(row.maintenance_rule_id), row.completed_at,
        row.operation_snapshot.get("data_origin")) for row in v.rows("work_orders") if row.work_order_id in ids])
    facts["history_equipment"] = sorted([(str(row.work_order_id), str(row.equipment_id)) for row in v.rows("work_order_equipment") if row.work_order_id in ids])
    return digest(facts)


def _stored(v, key, request_hash):
    rows = v.rows("planning_runs", idempotency_key=key)
    if not rows:
        return None
    if rows[0].request_sha256 != request_hash:
        raise HTTPException(409, "IDEMPOTENCY_CONFLICT: ключ уже использован с другими параметрами")
    return dict(rows[0].response_snapshot, replayed=True)


def _lock_sources(v):
    for name in SOURCE_TABLES:
        cls = v.models[name]
        v.session.scalars(select(cls).where(cls.site_id == v.principal.site_id)
            .order_by(*cls.__table__.primary_key.columns).with_for_update(read=True)
            .execution_options(populate_existing=True)).all()


def generate_tasks(v, year, month, key, token, forecaster, *, forecast_timeout_seconds=2):
    if v.principal.role != "dispatcher":
        raise HTTPException(403, "Сохранение плана доступно диспетчеру")
    request_hash = digest(dict(year=year, month=month, token=token))
    old = _stored(v, key, request_hash)
    if old:
        return old
    now = datetime.now(timezone.utc)
    if source_token(v, year, month, now) != token:
        raise HTTPException(409, "STALE_PREVIEW: данные или локальная дата изменились; пересчитайте график")
    preview = preview_calendar(v, year, month, as_of=now)
    if len(preview["items"]) > 500:
        raise HTTPException(422, "GENERATION_LIMIT: за один запуск поддерживается до 500 вхождений")
    site = v.one("sites", site_id=v.principal.site_id)
    tz, prepared, warnings = ZoneInfo(site.timezone), [], []
    budget_end = timer.monotonic()+8
    # Pure calculations and AI happen before write locks. Providers never see the Session.
    for row in preview["items"]:
        if row["deadlinePassed"]:
            warnings.append(dict(occurrenceId=row["id"], code="DEADLINE_EXCEEDED", explanation="Прошедшее обязательство требует ручной проверки; новое задание не создано."))
            continue
        if row["rawNormValue"] is None:
            warnings.append(dict(occurrenceId=row["id"], code="NORM_VALUE_MISSING", explanation="Не задана исходная норма для снимка задания."))
            continue
        binding = v.one("rule_equipment", binding_id=UUID(row["bindingId"]))
        item = binding_input(v, binding, as_of=now)
        snapshot = make_snapshot(v, item, date.fromisoformat(row["earliestDate"]), date.fromisoformat(row["mandatoryDueDate"]), as_of=now)
        values = calculate(snapshot, item, forecaster, timeout_seconds=min(forecast_timeout_seconds, budget_end-timer.monotonic()))
        prepared.append((row, binding.binding_id, item, snapshot, values))
    lock_key = int.from_bytes(sha256(f"{site.site_id}:{year}:{month}".encode()).digest()[:8], "big", signed=True)
    with service_transaction(v.session):
        v.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        v.session.expire_all()
        old = _stored(v, key, request_hash)
        if old:
            return old
        # Recheck actor membership after calculation and any lock wait.
        users, members, sites = v.models["users"], v.models["site_memberships"], v.models["sites"]
        actor = v.session.scalar(select(users).where(users.user_id == v.principal.user_id).with_for_update(read=True).execution_options(populate_existing=True))
        member = v.session.scalar(select(members).where(members.site_id == site.site_id, members.user_id == v.principal.user_id).with_for_update(read=True).execution_options(populate_existing=True))
        active_site = v.session.scalar(select(sites).where(sites.site_id == site.site_id).with_for_update(read=True).execution_options(populate_existing=True))
        if not actor or not actor.is_active or not member or not member.is_active or member.role != "dispatcher" or not active_site or not active_site.is_active:
            raise HTTPException(403, "Доступ диспетчера отозван")
        _lock_sources(v)
        if source_token(v, year, month, datetime.now(timezone.utc)) != token:
            raise HTTPException(409, "STALE_PREVIEW: исходные данные изменились во время расчёта")
        run_id, plan, results = uuid4(), None, []
        for row, binding_id, item, snapshot, values in prepared:
            algorithmic, ai, decision = values
            due = date.fromisoformat(row["mandatoryDueDate"])
            existing = [entry for entry in v.rows("schedule_entries", binding_id=binding_id) if entry.regulatory_deadline_on == due]
            if len(existing) > 1:
                raise HTTPException(409, "EXISTING_OCCURRENCE_CONFLICT: несколько сохранённых вхождений одного обязательства")
            if existing:
                entry = existing[0]
                orders = v.rows("work_orders", schedule_entry_id=entry.schedule_entry_id)
                if not orders or entry.status != "planned" or orders[0].status == "cancelled":
                    warnings.append(dict(occurrenceId=row["id"], code="EXISTING_OCCURRENCE_REVIEW", explanation="Существующее вхождение требует ручной проверки; дубликат не создаётся."))
                    continue
                order, created, comparison = orders[0], False, None
                frozen = entry.rule_snapshot
                if (entry.maintenance_rule_id != item.rule.rule_version_id
                        or (frozen.get("operation") and frozen["operation"] != json.loads(item.operation.model_dump_json()))
                        or (frozen.get("rule") and frozen["rule"] != json.loads(item.rule.model_dump_json()))):
                    warnings.append(dict(occurrenceId=row["id"], code="EXISTING_VERSION_CHANGED",
                        explanation="Для этого обязательства уже есть задание с другим снимком регламента. Требуется ручная сверка; дубликат не создан."))
                    continue
                if order.orchestration_decision_id:
                    stored = v.one("orchestration_decisions", orchestration_decision_id=order.orchestration_decision_id)
                    comparison = stored.comparison_snapshot.get("ui")
            else:
                deadline_at = datetime.combine(due+timedelta(days=1), time.min, tz)
                # Store both results even when policy refuses to create a task.
                binding_row = v.one("rule_equipment", binding_id=binding_id)
                comparison, saved_decision = persist_comparison(v, snapshot, *values, system_id=binding_row.system_id, deadline_at=deadline_at)
                if decision.selected_date is None:
                    warnings.append(dict(occurrenceId=row["id"], code=decision.status.upper(), explanation="; ".join(decision.reasons), comparisonRunId=comparison["runId"]))
                    continue
                if plan is None:
                    revision = max((p.revision for p in v.rows("schedule_plans", period_year=year, period_month=month)), default=0)+1
                    plan = v.repo.add("schedule_plans", site_id=site.site_id, period_year=year, period_month=month, revision=revision,
                        created_by=actor.user_id, source_snapshot={"planning_run_id":str(run_id), "token":token, "policy":"maintenance-orchestrator-v1"})
                occurrence_id = UUID(row["id"])
                entry = v.repo.add("schedule_entries", schedule_entry_id=occurrence_id, source_occurrence_id=occurrence_id,
                    site_id=site.site_id, system_id=binding_row.system_id, schedule_plan_id=plan.schedule_plan_id,
                    maintenance_rule_id=item.rule.rule_version_id, binding_id=binding_id, planned_date=decision.selected_date,
                    earliest_date=snapshot.earliest_date, regulatory_deadline_on=due, regulatory_deadline_at=deadline_at,
                    orchestration_decision_id=saved_decision.orchestration_decision_id, rule_snapshot=json.loads(item.model_dump_json()))
                op = item.operation
                frozen = dict(data_origin=op.data_origin, code=op.code, title=op.title, maintenance_type=op.maintenance_type,
                    operation_version=op.version, norm_unit=op.norm_unit, planning_duration_minutes=op.planning_duration_minutes, duration_basis=op.duration_basis,
                    qualification_ids=[str(skill) for skill in op.qualification_ids], label="Создано из подтверждённого расчёта календаря",
                    planning_run_id=str(run_id), checklist=[dict(id=str(check.checklist_item_id), text=check.text, answerKind=check.answer_kind,
                        unit=check.unit, required=check.required, visualVerifiability=check.visual_verifiability, photoRequired=check.photo_required) for check in op.checklist])
                order = v.repo.add("work_orders", work_order_id=uuid5(NAMESPACE, str(occurrence_id)), site_id=site.site_id,
                    system_id=binding_row.system_id, maintenance_rule_id=item.rule.rule_version_id, schedule_entry_id=entry.schedule_entry_id,
                    required_people_snapshot=op.crew_size, norm_hours_snapshot=op.raw_norm_value,
                    norm_hours_basis_snapshot=binding_row.rule.norm_hours_basis,
                    operation_snapshot=frozen, regulatory_deadline_at=deadline_at, orchestration_decision_id=saved_decision.orchestration_decision_id,
                    status="draft", created_by=actor.user_id)
                v.repo.add("work_order_equipment", site_id=site.site_id, system_id=binding_row.system_id,
                    work_order_id=order.work_order_id, equipment_id=item.equipment.equipment_id,
                    asset_snapshot=json.loads(item.equipment.model_dump_json()))
                v.repo.add("audit_events", site_id=site.site_id, actor_type="user", actor_user_id=actor.user_id,
                    entity_type="work_orders", entity_id=order.work_order_id, action="generate",
                    after_snapshot={"planning_run_id":str(run_id),"source_occurrence_id":str(occurrence_id),"revision":1,"status":"draft"})
                created = True
            selected_day = entry.planned_date
            begin = datetime.combine(selected_day, time(9), tz)
            end = min(datetime.combine(selected_day, time(17), tz), entry.regulatory_deadline_at)
            proposal = assignment_preview(v, order, begin.replace(tzinfo=None), end.astimezone(tz).replace(tzinfo=None)) if order.status in ("draft", "assigned") else None
            results.append(dict(occurrenceId=row["id"],taskId=str(order.work_order_id),equipmentName=item.equipment.name,
                operationTitle=item.operation.title,created=created,state=order.status,plannedDate=str(entry.planned_date),
                mandatoryDueDate=str(due),comparison=comparison,assignment=proposal))
        response = dict(runId=str(run_id), year=year,month=month,timezone=site.timezone,calculatedAt=now.isoformat(),
            replayed=False,createdCount=sum(r["created"] for r in results),existingCount=sum(not r["created"] for r in results),
            items=results,warnings=warnings,diagnostics=preview["diagnostics"])
        v.repo.add("planning_runs", planning_run_id=run_id,site_id=site.site_id,idempotency_key=key,request_sha256=request_hash,
            period_year=year,period_month=month,created_by=actor.user_id,response_snapshot=response)
    return response
