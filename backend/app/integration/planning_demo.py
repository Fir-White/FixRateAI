"""Separate synthetic source for the calendar-to-task workflow; no saved tasks."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .demo import demo_id


def add_planning_demo(repo):
    def ensure(table, pk, key, **values):
        return repo.get(table, demo_id(key)) or repo.add(table, **{pk:demo_id(key)}, **values)
    site, system = demo_id("site"), demo_id("system")
    day = datetime.now(ZoneInfo(repo.get("sites",site).timezone)).date()+timedelta(days=1)
    equipment = ensure("equipment","equipment_id","planning-equipment", site_id=site,system_id=system,
        equipment_type_id=repo.get("equipment",demo_id("equipment-2")).equipment_type_id,
        asset_code="DEMO-PIPELINE",name="DEMO — узел сквозного планирования",properties={"data_origin":"synthetic_demo"})
    document = ensure("regulation_documents","regulation_document_id","planning-document",site_id=site,
        title="DEMO — сквозное планирование",source_kind="demo",source_uri="synthetic_demo:planning-v1")
    edition = ensure("regulation_editions","regulation_edition_id","planning-edition",site_id=site,
        regulation_document_id=document.regulation_document_id,edition_code="DEMO-PIPELINE-v1",effective_from=day,
        is_approved=True,approved_by=demo_id("engineer"))
    operation = ensure("operation_templates","operation_template_id","planning-operation",site_id=site,system_id=system,
        code="DEMO-PIPELINE",title="DEMO — сквозное планирование",maintenance_type_id=demo_id("to2"),
        description="Синтетическая работа двух специалистов; длительность 60 минут подтверждена отдельно")
    rule = ensure("maintenance_rules","maintenance_rule_id","planning-rule",site_id=site,system_id=system,
        operation_template_id=operation.operation_template_id,regulation_edition_id=edition.regulation_edition_id,
        period_unit="month",scheduling_mode="fixed_interval",source_text="DEMO: ежемесячно от явной даты",
        source_ref="synthetic_demo:planning-v1",required_people=2,norm_hours=2,norm_hours_basis="total_person_hours",
        active_from=day,publication_status="published",data_origin="synthetic_demo",
        schedule_parameters={"anchor_date":str(day),"basis":"fixed_calendar","norm_unit":"person_hour",
            "planning_duration_minutes":60,"duration_basis":"synthetic_demo: подтверждённые 60 минут"})
    if not repo.get("rule_required_skills",(site,rule.maintenance_rule_id,demo_id("assignment-skill"))):
        repo.add("rule_required_skills",site_id=site,maintenance_rule_id=rule.maintenance_rule_id,
            skill_id=demo_id("assignment-skill"),minimum_holders=2)
    ensure("checklist_templates","checklist_template_id","planning-checklist",site_id=site,
        operation_template_id=operation.operation_template_id,item_code="ready",prompt="Учебная работа выполнена",input_kind="checkbox")
    cls=repo.models["rule_equipment"]
    if not repo.session.query(cls).filter_by(binding_id=demo_id("planning-binding")).first():
        repo.add("rule_equipment",binding_id=demo_id("planning-binding"),site_id=site,system_id=system,
            maintenance_rule_id=rule.maintenance_rule_id,equipment_id=equipment.equipment_id,valid_from=day)
