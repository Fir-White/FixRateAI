"""Application service for the maintenance_jobs resource."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException

from app.maintenance_jobs import public_status


def _job_payload(v, order):
    entry = v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id) if order.schedule_entry_id else None
    link = v.one("work_order_equipment", work_order_id=order.work_order_id)
    return {
        "schema_version": "maintenance-0.1",
        "job_id": order.work_order_id,
        "schedule_entry_id": entry.schedule_entry_id if entry else None,
        "equipment_id": link.equipment_id,
        "maintenance_rule_id": order.maintenance_rule_id,
        "planned_date": entry.planned_date if entry else order.operation_snapshot.get("earliest_date"),
        "regulatory_deadline_at": order.regulatory_deadline_at,
        "status": public_status(order.status),
        "revision": order.revision,
        "created_at": order.created_at,
    }


def create_job(v, schedule_entry_id: UUID, equipment_id: UUID, maintenance_rule_id: UUID | None,
               planned_start_at: datetime | None):
    entry = v.one("schedule_entries", schedule_entry_id=schedule_entry_id)
    if entry.status != "planned":
        raise HTTPException(409, "SCHEDULE_ENTRY_NOT_PLANNED: вхождение уже закрыто")
    binding = v.one("rule_equipment", binding_id=entry.binding_id) if entry.binding_id else None
    if binding is None or binding.equipment_id != equipment_id:
        raise HTTPException(422, "EQUIPMENT_BINDING_MISMATCH: оборудование не связано с вхождением")
    if maintenance_rule_id is not None and maintenance_rule_id != entry.maintenance_rule_id:
        raise HTTPException(422, "RULE_MISMATCH: регламент не соответствует вхождению")
    equipment = v.one("equipment", equipment_id=equipment_id)
    if equipment.system_id != entry.system_id:
        raise HTTPException(422, "SYSTEM_MISMATCH: оборудование относится к другой системе")
    existing = v.rows("work_orders", schedule_entry_id=schedule_entry_id)
    if any(order.status != "cancelled" for order in existing):
        raise HTTPException(409, "JOB_ALREADY_EXISTS: для регламентной даты уже есть задание")
    rule = v.one("maintenance_rules", maintenance_rule_id=entry.maintenance_rule_id)
    if rule.norm_hours is None:
        raise HTTPException(422, "NORM_VALUE_MISSING: у регламента нет подтверждённой нормы")
    order = v.repo.add(
        "work_orders",
        site_id=v.principal.site_id,
        system_id=entry.system_id,
        maintenance_rule_id=entry.maintenance_rule_id,
        schedule_entry_id=entry.schedule_entry_id,
        status="draft",
        required_people_snapshot=rule.required_people,
        norm_hours_snapshot=rule.norm_hours,
        operation_snapshot=entry.rule_snapshot or {},
        planned_start_at=planned_start_at or entry.planned_at,
        regulatory_deadline_at=entry.regulatory_deadline_at,
        created_by=v.principal.user_id,
    )
    v.repo.add(
        "work_order_equipment",
        site_id=v.principal.site_id,
        system_id=entry.system_id,
        work_order_id=order.work_order_id,
        equipment_id=equipment_id,
    )
    v.repo.add(
        "audit_events",
        site_id=v.principal.site_id,
        actor_type="user",
        actor_user_id=v.principal.user_id,
        entity_type="maintenance_jobs",
        entity_id=order.work_order_id,
        action="created",
        after_snapshot={"status": "planned", "revision": order.revision},
    )
    return order


def job_history(v, job_id: UUID):
    v.task(job_id)
    events = v.rows("audit_events", entity_id=job_id)
    result = []
    for event in sorted(events, key=lambda item: item.occurred_at):
        before = event.before_snapshot or {}
        after = event.after_snapshot or {}
        from_status, to_status = before.get("status"), after.get("status")
        result.append(
            {
                "event_id": event.audit_event_id,
                "from_status": public_status(from_status) if from_status else None,
                "to_status": public_status(to_status) if to_status else None,
                "action": event.action,
                "reason": after.get("reason"),
                "changed_at": event.occurred_at,
            }
        )
    return result
