"""ALG02 library boundary composed from the maintenance-0.1 contracts."""
from __future__ import annotations

from datetime import date, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.maintenance import (
    AcceptedEvent, Contract, Equipment, NonNegativeInt, OperationVersion,
    PlanOccurrence, RecurrenceRule, Site, Text, Value, Versioned,
)
from app.schemas.maintenance_api import (
    CalendarQuery, CalendarResponse, EquipmentOperationBindingResponse,
)

PersonHours = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class SchedulingBinding(Value):
    binding: EquipmentOperationBindingResponse
    equipment: Equipment
    operation: OperationVersion
    rule: RecurrenceRule
    accepted_events: list[AcceptedEvent] = Field(default_factory=list)
    assumptions: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_binding(self):
        if (self.binding.equipment_id != self.equipment.equipment_id
                or self.binding.operation_version_id != self.operation.operation_version_id
                or self.binding.rule_version_id != self.rule.rule_version_id
                or self.binding.regulation_version_id != self.rule.regulation_version_id):
            raise ValueError("binding references do not match equipment/operation/rule")
        if len({x.data_origin for x in (self.binding, self.equipment, self.operation, self.rule)}) != 1:
            raise ValueError("mixed binding data origins")
        if len({e.service_event_id for e in self.accepted_events}) != len(self.accepted_events):
            raise ValueError("duplicate accepted event")
        if any(e.performed_at.astimezone(timezone.utc) > e.accepted_at.astimezone(timezone.utc)
               for e in self.accepted_events):
            raise ValueError("performed_at must not follow accepted_at")
        return self


class CalendarGenerationRequest(Versioned):
    site: Site
    query: CalendarQuery
    as_of: AwareDatetime
    bindings: list[SchedulingBinding]

    @model_validator(mode="after")
    def consistent_site(self):
        try:
            ZoneInfo(self.site.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown site timezone") from exc
        if self.query.site_id != self.site.site_id:
            raise ValueError("query belongs to another site")
        if self.query.include_cancelled:
            raise ValueError("generation does not load cancelled persisted occurrences")
        if len({b.binding.binding_id for b in self.bindings}) != len(self.bindings):
            raise ValueError("duplicate binding")
        for item in self.bindings:
            if item.equipment.site_id != self.site.site_id:
                raise ValueError("equipment belongs to another site")
            if item.equipment.data_origin != self.site.data_origin:
                raise ValueError("mixed site data origins")
        return self


class GeneratedOccurrence(Value):
    occurrence: PlanOccurrence
    explanation: Text
    deadline_passed: bool
    is_assumption: bool
    required_person_hours: PersonHours | None
    planning_person_minutes: NonNegativeInt | None


class BindingGenerationResult(Value):
    binding_id: UUID
    status: Literal["ok", "needs_input", "manual_review", "skipped"]
    error_code: Text | None
    explanation: Text
    warnings: list[Text]
    assumptions: list[Text]
    is_assumption: bool
    next_due_date: date | None
    occurrences: list[GeneratedOccurrence]
    total_person_hours: PersonHours | None
    total_planning_person_minutes: NonNegativeInt | None


class CalendarGenerationResult(Contract):
    method_version: Text
    as_of: AwareDatetime
    calendar: CalendarResponse
    bindings: list[BindingGenerationResult]
