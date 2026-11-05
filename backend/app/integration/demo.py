"""Persisted synthetic scenario for end-to-end demonstrations, never customer facts."""
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import UUID


def demo_id(key):
    return UUID(hashlib.md5(("fixrate-demo-" + key).encode()).hexdigest())


def add_runtime_demo(repo, password_hash):
    def ensure(table, pk, key, **values):
        identity = demo_id(key)
        obj = repo.get(table, identity)
        return obj if obj else repo.add(table, **{pk: identity}, **values)

    site, system = demo_id("site"), demo_id("system")
    for role, sql_role, key in (("executive","executive","executive"),("chief_engineer","chief_engineer","chief-engineer"),("dispatcher", "dispatcher", "dispatcher"),
                               ("admin", "admin", "admin"),
                               ("engineer", "engineer", "engineer"),
                               ("executor", "technician", "user-1")):
        user = ensure("users", "user_id", key, full_name=f"DEMO {role}", email=f"fixrate-demo-{role}@example.test")
        # A rerun never replaces an existing password or resets workflow history.
        if not user.password_hash:
            user.password_hash = password_hash
        if not repo.get("site_memberships", (site, user.user_id)):
            repo.add("site_memberships", site_id=site, user_id=user.user_id, role=sql_role)
    # Stable users imported by seed retain their original email addresses.
    now = datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    day = now.astimezone(ZoneInfo(repo.get("sites",site).timezone)).date()
    op = ensure("operation_templates", "operation_template_id", "runtime-operation", site_id=site, system_id=system,
        code="DEMO-1.4", title="DEMO — чистка учебного узла", maintenance_type_id=demo_id("to2"),
        description="Только синтетический сценарий интеграции, не норматив заказчика")
    rule = ensure("maintenance_rules", "maintenance_rule_id", "runtime-rule", site_id=site, system_id=system,
        operation_template_id=op.operation_template_id, regulation_edition_id=demo_id("edition"),
        period_unit="day", scheduling_mode="fixed_interval", source_text="DEMO: ежедневно", source_ref="synthetic_demo:integration",
        required_people=1, norm_hours=1, active_from=day, publication_status="draft", data_origin="synthetic_demo",
        schedule_parameters={"anchor_date": day.isoformat(), "basis": "fixed_calendar"})
    # Deliberately unconfirmed: the application must show needs_input rather than invent approval.
    item = ensure("checklist_templates", "checklist_template_id", "runtime-checklist", site_id=site,
        operation_template_id=op.operation_template_id, item_code="clean", prompt="Поверхность очищена",
        input_kind="checkbox")
    binding = next((b for b in repo.session.query(repo.models["rule_equipment"]).filter_by(binding_id=demo_id("runtime-binding"))), None)
    if not binding:
        binding = repo.add("rule_equipment", site_id=site, system_id=system, maintenance_rule_id=rule.maintenance_rule_id,
                          equipment_id=demo_id("equipment-2"), valid_from=day, binding_id=demo_id("runtime-binding"))
    plan = ensure("schedule_plans", "schedule_plan_id", "runtime-plan", site_id=site,
        period_year=day.year, period_month=day.month, revision=100, created_by=demo_id("dispatcher"),
        source_snapshot={"data_origin": "synthetic_demo"})
    entry = ensure("schedule_entries", "schedule_entry_id", "runtime-entry", site_id=site, system_id=system,
        schedule_plan_id=plan.schedule_plan_id, maintenance_rule_id=rule.maintenance_rule_id,
        binding_id=binding.binding_id, planned_date=day, regulatory_deadline_on=day,
        regulatory_deadline_at=now+timedelta(days=2))
    order = ensure("work_orders", "work_order_id", "runtime-order", site_id=site, system_id=system,
        maintenance_rule_id=rule.maintenance_rule_id, schedule_entry_id=entry.schedule_entry_id,
        status="assigned", required_people_snapshot=1, norm_hours_snapshot=1,
        planned_start_at=now+timedelta(hours=1), regulatory_deadline_at=entry.regulatory_deadline_at,
        operation_snapshot={"data_origin": "synthetic_demo", "title": op.title, "code": "DEMO-1.4", "maintenance_type": "ТО2",
                            "label": "DEMO: синтетический сценарий, нормы и даты не подтверждены",
                            "checklist": [{"id": str(item.checklist_template_id), "text": item.prompt, "answerKind": "boolean",
                                "unit": None, "required": True, "visualVerifiability": "visible", "photoRequired": True}]})
    if not repo.get("work_order_equipment", (site, order.work_order_id, demo_id("equipment-2"))):
        repo.add("work_order_equipment", site_id=site, system_id=system, work_order_id=order.work_order_id, equipment_id=demo_id("equipment-2"))
    ensure("work_assignments", "work_assignment_id", "runtime-assignment", site_id=site,
        work_order_id=order.work_order_id, user_id=demo_id("user-1"), assigned_by=demo_id("dispatcher"))
    from .assignment_demo import add_assignment_demo
    add_assignment_demo(repo, password_hash=password_hash)
    from .planning_demo import add_planning_demo
    add_planning_demo(repo)
