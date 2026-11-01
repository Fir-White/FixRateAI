"""Explicit synthetic ALG03 scenario; never alters customer rules or existing work."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .demo import demo_id


def add_assignment_demo(repo):
    def ensure(table, pk, key, **values):
        identity = demo_id(key)
        return repo.get(table, identity) or repo.add(table, **{pk: identity}, **values)

    site, system = demo_id("site"), demo_id("system")
    tz = ZoneInfo(repo.get("sites", site).timezone)
    existing = repo.get("schedule_entries", demo_id("assignment-entry"))
    day = existing.planned_date if existing else datetime.now(tz).date() + timedelta(days=1)
    begin = datetime.combine(day, time(9), tz)
    end = datetime.combine(day, time(17), tz)
    deadline = datetime.combine(day + timedelta(days=1), time.min, tz)
    verified = datetime.combine(day - timedelta(days=1), time.min, tz)
    equipment = ensure("equipment", "equipment_id", "assignment-equipment", site_id=site, system_id=system,
        asset_code="DEMO-ALG03", name="DEMO — учебный узел планирования", location="Учебный стенд ALG03",
        properties={"data_origin": "synthetic_demo", "label": "Отдельное оборудование для проверки подбора бригады"})
    skill = ensure("skills", "skill_id", "assignment-skill", code="DEMO-ALG03", name="DEMO: допуск к учебному узлу")
    crew = ensure("crews", "crew_id", "assignment-crew", site_id=site, name="DEMO — бригада теплового пункта")
    for number in (1, 2, 3):
        user = ensure("users", "user_id", f"assignment-worker-{number}", full_name=f"DEMO — работник планирования {number}",
                      email=f"fixrate-assignment-{number}@example.test")
        if not repo.get("site_memberships", (site, user.user_id)):
            repo.add("site_memberships", site_id=site, user_id=user.user_id, role="technician")
        if not repo.get("user_skills", (site, user.user_id, skill.skill_id)):
            repo.add("user_skills", site_id=site, user_id=user.user_id, skill_id=skill.skill_id, verified_at=verified)
        ensure("availability_slots", "availability_id", f"assignment-availability-{number}",
               site_id=site, user_id=user.user_id, starts_at=begin, ends_at=end, status="available")
        if number <= 2:
            ensure("crew_members", "crew_member_id", f"assignment-crew-member-{number}",
                   site_id=site, crew_id=crew.crew_id, user_id=user.user_id, valid_from=day)
    document = ensure("regulation_documents", "regulation_document_id", "assignment-document", site_id=site,
                      title="DEMO — правила подбора бригады", source_kind="demo", source_uri="synthetic_demo:alg03-v1")
    edition = ensure("regulation_editions", "regulation_edition_id", "assignment-edition", site_id=site,
                     regulation_document_id=document.regulation_document_id, edition_code="DEMO-ALG03-v1",
                     effective_from=day, is_approved=True, approved_by=demo_id("engineer"))
    operation = ensure("operation_templates", "operation_template_id", "assignment-operation", site_id=site, system_id=system,
                       code="DEMO-ALG03", title="DEMO — подбор бригады", description="Явно синтетическая работа двух человек длительностью 60 минут",
                       maintenance_type_id=demo_id("to2"))
    rule = ensure("maintenance_rules", "maintenance_rule_id", "assignment-rule", site_id=site, system_id=system,
        operation_template_id=operation.operation_template_id, regulation_edition_id=edition.regulation_edition_id,
        period_unit="month", scheduling_mode="fixed_interval", source_text="DEMO: ежемесячно", source_ref="synthetic_demo:alg03-v1",
        required_people=2, norm_hours=2, norm_hours_basis="total_person_hours", active_from=day,
        publication_status="published", data_origin="synthetic_demo", schedule_parameters={
            "anchor_date": day.isoformat(), "basis": "fixed_calendar", "planning_duration_minutes": 60,
            "duration_basis": "synthetic_demo: явно заданные 60 минут", "norm_unit": "person_hour"})
    if not repo.get("rule_required_skills", (site, rule.maintenance_rule_id, skill.skill_id)):
        repo.add("rule_required_skills", site_id=site, maintenance_rule_id=rule.maintenance_rule_id, skill_id=skill.skill_id, minimum_holders=2)
    checklist = ensure("checklist_templates", "checklist_template_id", "assignment-checklist", site_id=site,
                       operation_template_id=operation.operation_template_id, item_code="ready", prompt="Учебная работа выполнена бригадой", input_kind="checkbox")
    binding = next(iter(repo.session.query(repo.models["rule_equipment"]).filter_by(binding_id=demo_id("assignment-binding"))), None)
    if binding is None:
        binding = repo.add("rule_equipment", binding_id=demo_id("assignment-binding"), site_id=site, system_id=system,
                           maintenance_rule_id=rule.maintenance_rule_id, equipment_id=equipment.equipment_id, valid_from=day)
    plan = ensure("schedule_plans", "schedule_plan_id", "assignment-plan", site_id=site, period_year=day.year,
                  period_month=day.month, revision=200, created_by=demo_id("dispatcher"), source_snapshot={"data_origin": "synthetic_demo"})
    entry = ensure("schedule_entries", "schedule_entry_id", "assignment-entry", site_id=site, system_id=system,
        schedule_plan_id=plan.schedule_plan_id, maintenance_rule_id=rule.maintenance_rule_id, binding_id=binding.binding_id,
        planned_date=day, earliest_date=day, regulatory_deadline_on=day, regulatory_deadline_at=deadline)
    snapshot = dict(data_origin="synthetic_demo", title=operation.title, code=operation.code, maintenance_type="ТО2",
        planning_duration_minutes=60, duration_basis="synthetic_demo: явно заданные 60 минут", qualification_ids=[str(skill.skill_id)],
        label="DEMO: два работника, 60 минут, доступность и загрузка заданы для проверки ALG03.",
        checklist=[dict(id=str(checklist.checklist_template_id), text=checklist.prompt, answerKind="boolean", unit=None,
                        required=True, visualVerifiability="not_verifiable", photoRequired=False)])
    order = ensure("work_orders", "work_order_id", "assignment-order", site_id=site, system_id=system,
        maintenance_rule_id=rule.maintenance_rule_id, schedule_entry_id=entry.schedule_entry_id, status="draft",
        required_people_snapshot=2, norm_hours_snapshot=2, norm_hours_basis_snapshot="total_person_hours",
        regulatory_deadline_at=deadline, created_by=demo_id("dispatcher"), operation_snapshot=snapshot)
    busy = ensure("work_orders", "work_order_id", "assignment-busy-order", site_id=site, system_id=system, origin="manual",
        status="assigned", required_people_snapshot=1, norm_hours_snapshot=1, planned_start_at=begin,
        regulatory_deadline_at=deadline, operation_snapshot={**snapshot, "code": "DEMO-BUSY", "title": "DEMO — запланированная занятость",
            "label": "DEMO: занятость одного работника на 60 минут.", "earliest_date": day.isoformat()})
    for job in (order, busy):
        if not repo.get("work_order_equipment", (site, job.work_order_id, equipment.equipment_id)):
            repo.add("work_order_equipment", site_id=site, system_id=system, work_order_id=job.work_order_id,
                     equipment_id=equipment.equipment_id, asset_snapshot={"data_origin": "synthetic_demo"})
    ensure("work_assignments", "work_assignment_id", "assignment-busy-worker", site_id=site,
           work_order_id=busy.work_order_id, user_id=demo_id("assignment-worker-3"), assigned_by=demo_id("dispatcher"))
