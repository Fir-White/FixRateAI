"""Application service for the maintenance_jobs resource."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException

from app.maintenance_jobs import (
    InvalidJobTransition,
    ensure_transition,
    internal_status,
    public_status,
)


def _active_assignments(v, job_id: UUID):
    return [
        row
        for row in v.rows("work_assignments", work_order_id=job_id)
        if row.status not in ("cancelled", "declined")
    ]


def _job_payload(v, order):
    entry = v.one("schedule_entries", schedule_entry_id=order.schedule_entry_id)
    link = v.one("work_order_equipment", work_order_id=order.work_order_id)
    return {
        "schema_version": "maintenance-0.1",
        "job_id": order.work_order_id,
        "schedule_entry_id": entry.schedule_entry_id,
        "equipment_id": link.equipment_id,
        "maintenance_rule_id": order.maintenance_rule_id,
        "planned_date": entry.planned_date,
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


def transition_job(v, job_id: UUID, target: str, expected_revision: int, reason: str | None):
    order = v.task(job_id, lock=True)
    if order.revision != expected_revision:
        raise HTTPException(409, "REVISION_CONFLICT: обновите задание")
    current = public_status(order.status)
    try:
        ensure_transition(current, target)
    except InvalidJobTransition as exc:
        raise HTTPException(409, f"INVALID_STATUS_TRANSITION: {exc}") from None

    active = _active_assignments(v, job_id)
    if target == "assigned" and not active:
        raise HTTPException(409, "ASSIGNMENT_REQUIRED: сначала назначьте исполнителя")
    if target in ("in_progress", "submitted") and not any(
        row.user_id == v.principal.user_id for row in active
    ):
        raise HTTPException(403, "Задание доступно только назначенному исполнителю")
    if target in ("accepted", "rework") and v.principal.role != "engineer":
        raise HTTPException(403, "Приёмка доступна инженеру")

    before = {"status": current, "revision": order.revision}
    order.status = internal_status(target)
    now = datetime.now(timezone.utc)
    if target == "in_progress" and order.started_at is None:
        order.started_at = now
    if target == "accepted":
        order.completed_at = now
    order.revision += 1
    v.session.flush()
    v.repo.add(
        "audit_events",
        site_id=v.principal.site_id,
        actor_type="user",
        actor_user_id=v.principal.user_id,
        entity_type="maintenance_jobs",
        entity_id=job_id,
        action="status_changed",
        before_snapshot=before,
        after_snapshot={
            "status": target,
            "revision": order.revision,
            "reason": reason,
        },
    )
    return order


def job_history(v, job_id: UUID):
    v.task(job_id)
    events = v.rows("audit_events", entity_id=job_id)
    result = []
    for event in sorted(events, key=lambda item: item.occurred_at):
        before = event.before_snapshot or {}
        after = event.after_snapshot or {}
        result.append(
            {
                "event_id": event.audit_event_id,
                "from_status": before.get("status"),
                "to_status": after.get("status"),
                "action": event.action,
                "reason": after.get("reason"),
                "changed_at": event.occurred_at,
            }
        )
    return result
