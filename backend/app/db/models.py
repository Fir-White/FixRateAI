"""ORM mappings of the physical PostgreSQL schema.

Mappings are reflected from an already migrated database, never created with
metadata.create_all(). Call map_schema once at application startup.
"""
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType
from typing import Mapping

from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import registry, relationship, foreign


TABLES = (
    "sites", "users", "site_memberships", "engineering_systems", "equipment_types",
    "equipment", "skills", "user_skills", "availability_slots", "crews", "crew_members",
    "maintenance_types", "operation_templates", "regulation_documents", "regulation_editions",
    "maintenance_rules", "rule_equipment", "rule_required_skills", "schedule_plans",
    "schedule_entries", "incident_reports", "work_orders", "work_order_equipment",
    "work_assignments", "checklist_templates", "work_reports", "checklist_results",
    "work_readings", "evidence_files", "acceptance_reviews", "predictor_versions",
    "forecast_runs", "orchestration_decisions", "ai_quality_checks", "audit_events",
)


def _class_name(table: str) -> str:
    # Explicit names prevent incorrect English singularisation of e.g. "equipment".
    names = {"sites": "Site", "users": "User", "engineering_systems": "EngineeringSystem",
             "equipment": "Equipment", "maintenance_rules": "MaintenanceRule",
             "rule_equipment": "RuleEquipment", "schedule_entries": "ScheduleEntry",
             "work_orders": "WorkOrder", "work_reports": "WorkReport",
             "evidence_files": "EvidenceFile", "acceptance_reviews": "AcceptanceReview",
             "forecast_runs": "ForecastRun", "orchestration_decisions": "OrchestrationDecision"}
    return names.get(table, "".join(part.capitalize() for part in table.split("_")))


@dataclass(frozen=True)
class Mappings:
    registry: registry
    classes: Mapping[str, type]

    def __getitem__(self, table: str) -> type:
        return self.classes[table]


_lock = Lock()


def map_schema(engine: Engine, schema: str | None = None) -> Mappings:
    """Reflect and map schema 001–004. Instances are scoped to this registry.

    Reflection preserves actual FK, checks and server defaults, including the
    NOT VALID constraint. It does not validate old rows. Multiple registries
    are independent, useful for separately migrated test databases.
    """
    if engine.dialect.name != "postgresql":
        raise ValueError("The maintenance schema requires PostgreSQL")
    metadata = MetaData(schema=schema)
    names = list(TABLES)
    for optional in ("planning_runs", "employee_shift_rules", "site_join_codes", "employment_applications", "maintenance_notifications"):
        if inspect(engine).has_table(optional, schema=schema):
            names.append(optional)
    metadata.reflect(bind=engine, only=names)
    tables = {name: metadata.tables[f"{schema}.{name}" if schema else name] for name in names}
    norm = tables["work_orders"].c.norm_hours_snapshot.type
    fks = inspect(engine).get_foreign_keys("work_orders", schema=schema)
    if (getattr(norm, "precision", None), getattr(norm, "scale", None)) != (13, 3):
        raise RuntimeError("Migration 004 is missing: incorrect work order norm type")
    expected_cols = ["site_id", "system_id", "schedule_entry_id", "maintenance_rule_id"]
    if not any(fk["name"] == "fk_work_orders_entry_rule" and
               fk["constrained_columns"] == expected_cols and
               fk["referred_table"] == "schedule_entries" and
               fk["referred_columns"] == expected_cols and
               fk.get("options", {}).get("ondelete", "").upper() == "RESTRICT"
               for fk in fks):
        raise RuntimeError("Migration 004 is missing: work order/entry FK")

    mapper_registry = registry(metadata=metadata)
    classes = {name: type(_class_name(name), (), {"__module__": __name__}) for name in names}

    # Relationships are intentionally read-only: writes use explicit FK values,
    # avoiding ambiguous overlapping composite keys and implicit cascades.
    links = {
        "engineering_systems": {"site": ("sites", [("site_id", "site_id")])},
        "equipment": {"system": ("engineering_systems", [("site_id", "site_id"), ("system_id", "system_id")]),
                      "equipment_type": ("equipment_types", [("equipment_type_id", "equipment_type_id")])},
        "maintenance_rules": {"operation": ("operation_templates", [("site_id", "site_id"), ("system_id", "system_id"), ("operation_template_id", "operation_template_id")]),
                              "edition": ("regulation_editions", [("site_id", "site_id"), ("regulation_edition_id", "regulation_edition_id")])},
        "rule_equipment": {"equipment": ("equipment", [("site_id", "site_id"), ("system_id", "system_id"), ("equipment_id", "equipment_id")]),
                           "rule": ("maintenance_rules", [("site_id", "site_id"), ("system_id", "system_id"), ("maintenance_rule_id", "maintenance_rule_id")])},
        "schedule_entries": {"rule": ("maintenance_rules", [("site_id", "site_id"), ("system_id", "system_id"), ("maintenance_rule_id", "maintenance_rule_id")]),
                             "plan": ("schedule_plans", [("site_id", "site_id"), ("schedule_plan_id", "schedule_plan_id")]),
                             "binding": ("rule_equipment", [("site_id", "site_id"), ("system_id", "system_id"), ("maintenance_rule_id", "maintenance_rule_id"), ("binding_id", "binding_id")])},
        "work_orders": {"entry": ("schedule_entries", [("site_id", "site_id"), ("system_id", "system_id"), ("schedule_entry_id", "schedule_entry_id"), ("maintenance_rule_id", "maintenance_rule_id")]),
                        "rule": ("maintenance_rules", [("site_id", "site_id"), ("system_id", "system_id"), ("maintenance_rule_id", "maintenance_rule_id")])},
        "work_reports": {"order": ("work_orders", [("site_id", "site_id"), ("work_order_id", "work_order_id")])},
        "work_assignments": {"order": ("work_orders", [("site_id", "site_id"), ("work_order_id", "work_order_id")]),
                             "user": ("users", [("user_id", "user_id")]),
                             "crew": ("crews", [("site_id", "site_id"), ("crew_id", "crew_id")])},
        "evidence_files": {"report": ("work_reports", [("site_id", "site_id"), ("work_order_id", "work_order_id"), ("work_report_id", "work_report_id")])},
        "acceptance_reviews": {"report": ("work_reports", [("site_id", "site_id"), ("work_order_id", "work_order_id"), ("work_report_id", "work_report_id")])},
        "forecast_runs": {"predictor": ("predictor_versions", [("predictor_version_id", "predictor_version_id")])},
    }
    from sqlalchemy import and_
    with _lock:
        for name in names:
            props = {}
            for attr, (target, columns) in links.get(name, {}).items():
                join = and_(*(foreign(tables[name].c[local]) == tables[target].c[remote]
                              for local, remote in columns))
                props[attr] = relationship(classes[target], primaryjoin=join, viewonly=True, uselist=False)
            mapper_registry.map_imperatively(classes[name], tables[name], properties=props)
        mapper_registry.configure()
    return Mappings(mapper_registry, MappingProxyType(classes))
