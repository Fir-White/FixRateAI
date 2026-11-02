"""REST request and response models for maintenance-0.1."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .maintenance import (
    Assignment,
    ExecutionReport,
    OperationVersion,
    RecurrenceRule,
    Schedule,
    Task,
)

SCHEMA_VERSION = "maintenance-0.1"
Text = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
Hours = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceRef(ApiModel):
    source_ref: Text
    data_origin: Literal["customer", "synthetic_demo"]


class EquipmentCreate(ApiModel):
    site_id: UUID
    equipment_type_id: UUID
    inventory_code: Text
    name: Text
    commissioned_on: date | None = None
    state: Literal["active", "out_of_service", "retired"] = "active"


class EquipmentResponse(EquipmentCreate, SourceRef):
    schema_version: Literal["maintenance-0.1"] = SCHEMA_VERSION
    equipment_id: UUID
    revision: PositiveInt


class ChecklistItemCreate(ApiModel):
    text: Text
    answer_kind: Literal["boolean", "number", "text"]
    unit: Text | None = None
    required: bool = True
    visual_verifiability: Literal["visible", "partial", "not_verifiable"]
    photo_required: bool = False


class OperationCreate(SourceRef):
    operation_id: UUID | None = None
    code: Text
    title: Text
    maintenance_type: Literal["ТО1", "ТО2"]
    instructions: Text
    crew_size: PositiveInt
    raw_norm_value: Hours | None
    norm_unit: Literal["unconfirmed", "person_hour", "elapsed_hour"]
    planning_duration_minutes: PositiveInt | None = None
    duration_basis: Text | None = None
    qualification_ids: list[UUID] = Field(default_factory=list)
    checklist: Annotated[list[ChecklistItemCreate], Field(min_length=1)]
    status: Literal["draft", "approved", "retired"] = "draft"

    @model_validator(mode="after")
    def duration_has_basis(self) -> "OperationCreate":
        if self.planning_duration_minutes is not None and not self.duration_basis:
            raise ValueError("confirmed planning duration requires duration_basis")
        return self


class OperationResponse(OperationVersion):
    """Versioned operation returned by REST."""


class RegulationCreate(SourceRef):
    regulation_id: UUID | None = None
    name: Text
    version: PositiveInt = 1
    status: Literal["draft", "approved", "retired"] = "draft"
    effective_from: date | None = None
    supersedes_version_id: UUID | None = None


class RegulationResponse(RegulationCreate):
    schema_version: Literal["maintenance-0.1"] = SCHEMA_VERSION
    regulation_id: UUID
    regulation_version_id: UUID


class RecurrenceRuleResponse(RecurrenceRule):
    """Versioned recurrence rule returned by REST."""


class RecurrenceRuleCreate(SourceRef):
    regulation_version_id: UUID
    source_text: Text
    kind: Literal["calendar_interval", "explicit_dates", "runtime"]
    confirmed: bool = False
    interval: PositiveInt | None = None
    calendar_unit: Literal["day", "month"] | None = None
    anchor_date: date | None = None
    basis: Literal["fixed_calendar", "after_accepted_completion"] | None = None
    explicit_dates: list[date] = Field(default_factory=list)
    yearly_count: PositiveInt | None = None
    runtime_interval_hours: Hours | None = None
    allowed_lead_days: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_confirmed_rule(self) -> "RecurrenceRuleCreate":
        if len(set(self.explicit_dates)) != len(self.explicit_dates):
            raise ValueError("duplicate recurrence date")
        if self.explicit_dates != sorted(self.explicit_dates):
            raise ValueError("explicit dates must be sorted")
        if not self.confirmed:
            return self
        if self.kind == "calendar_interval":
            if None in (self.interval, self.calendar_unit, self.anchor_date, self.basis):
                raise ValueError("calendar rule needs interval/unit/anchor/basis")
            if self.explicit_dates or self.yearly_count or self.runtime_interval_hours is not None:
                raise ValueError("incompatible calendar rule fields")
        elif self.kind == "explicit_dates":
            if not self.explicit_dates or self.yearly_count is None:
                raise ValueError("explicit annual rule needs dates and count")
            for year in {item.year for item in self.explicit_dates}:
                if sum(item.year == year for item in self.explicit_dates) != self.yearly_count:
                    raise ValueError("annual date count does not match yearly_count")
            if any(
                item is not None
                for item in (
                    self.interval,
                    self.calendar_unit,
                    self.anchor_date,
                    self.basis,
                    self.runtime_interval_hours,
                )
            ):
                raise ValueError("incompatible explicit rule fields")
        else:
            if self.runtime_interval_hours is None or self.runtime_interval_hours <= 0:
                raise ValueError("runtime rule needs positive hour interval")
            if self.explicit_dates or any(
                item is not None
                for item in (
                    self.interval,
                    self.calendar_unit,
                    self.anchor_date,
                    self.basis,
                    self.yearly_count,
                )
            ):
                raise ValueError("incompatible runtime rule fields")
        return self


class EquipmentOperationBindingCreate(SourceRef):
    equipment_id: UUID
    operation_version_id: UUID
    rule_version_id: UUID
    regulation_version_id: UUID
    effective_from: date | None = None
    effective_to: date | None = None
    baseline_runtime_hours: Hours | None = None

    @model_validator(mode="after")
    def valid_effective_range(self) -> "EquipmentOperationBindingCreate":
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


class EquipmentOperationBindingResponse(EquipmentOperationBindingCreate):
    schema_version: Literal["maintenance-0.1"] = SCHEMA_VERSION
    binding_id: UUID
    revision: PositiveInt


class CalendarQuery(ApiModel):
    site_id: UUID
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    include_cancelled: bool = False


class CalendarOccurrence(ApiModel):
    occurrence_id: UUID
    equipment_id: UUID
    operation_version_id: UUID
    occurrence_date: date
    maintenance_type: Literal["ТО1", "ТО2"]
    recurrence: Text
    crew_size: PositiveInt
    raw_norm_value: Hours | None
    norm_unit: Literal["unconfirmed", "person_hour", "elapsed_hour"]
    planning_duration_minutes: PositiveInt | None
    source_ref: Text
    planned_task_id: UUID | None
    actual_execution_id: UUID | None
    status: Literal["draft", "planned", "fulfilled", "cancelled"]


class CalendarResponse(ApiModel):
    schema_version: Literal["maintenance-0.1"] = SCHEMA_VERSION
    site_id: UUID
    year: int
    month: int
    timezone: Text
    items: list[CalendarOccurrence]
    total: int

    @model_validator(mode="after")
    def total_matches_items(self) -> "CalendarResponse":
        if self.total != len(self.items):
            raise ValueError("total must equal number of returned items")
        return self


class MaintenanceJobCreate(ApiModel):
    schedule_entry_id: UUID
    equipment_id: UUID
    maintenance_rule_id: UUID | None = None
    planned_start_at: AwareDatetime | None = None


class MaintenanceJobTransition(ApiModel):
    expected_revision: PositiveInt
    status: Literal["assigned", "in_progress", "submitted", "accepted", "rework"]
    reason: Text | None = None


class MaintenanceJobResponse(ApiModel):
    schema_version: Literal["maintenance-0.1"] = SCHEMA_VERSION
    job_id: UUID
    schedule_entry_id: UUID
    equipment_id: UUID
    maintenance_rule_id: UUID
    planned_date: date
    regulatory_deadline_at: AwareDatetime
    status: Literal["planned", "assigned", "in_progress", "submitted", "accepted", "rework"]
    revision: PositiveInt
    created_at: AwareDatetime


class MaintenanceJobHistoryItem(ApiModel):
    event_id: UUID
    from_status: str | None = None
    to_status: str | None = None
    action: Text
    reason: str | None = None
    changed_at: AwareDatetime


class AssignmentResponse(Assignment):
    pass


class TaskResponse(Task):
    pass


class ExecutionResponse(ExecutionReport):
    pass


class ExecutionListResponse(ApiModel):
    schema_version: Literal["maintenance-0.1"] = SCHEMA_VERSION
    items: list[ExecutionResponse]
    total: int
    limit: PositiveInt
    offset: int = Field(ge=0)

    @model_validator(mode="after")
    def total_is_non_negative(self) -> "ExecutionListResponse":
        if self.total < len(self.items):
            raise ValueError("total cannot be less than returned items")
        return self


class RolePermissions(ApiModel):
    role: Literal["admin", "dispatcher", "executor", "engineer"]
    permissions: list[Text]


ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": ("reference:read", "reference:write", "users:write"),
    "dispatcher": ("equipment:read", "operation:write", "schedule:write", "task:assign"),
    "executor": ("task:read_assigned", "execution:write", "photo:write"),
    "engineer": ("equipment:read", "execution:read", "execution:accept", "forecast:read"),
}
