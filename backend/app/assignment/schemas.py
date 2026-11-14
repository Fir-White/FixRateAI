from datetime import date, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.maintenance import AssignmentCommand, Contract, NonNegativeInt, PositiveInt, Text, Value


class TimeInterval(Value):
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def positive_interval(self):
        if self.end_at.astimezone(timezone.utc) <= self.start_at.astimezone(timezone.utc):
            raise ValueError("interval must have positive duration")
        return self


class Availability(TimeInterval):
    status: Literal["available", "unavailable"]


class Booking(TimeInterval):
    task_id: UUID
    blocks_time: bool = True


class Qualification(Value):
    skill_id: UUID
    verified_at: AwareDatetime | None
    valid_until: date | None
    validity_required: bool


class Worker(Value):
    worker_id: UUID
    site_id: UUID
    name: Text
    active: bool
    membership_active: bool
    can_execute: bool
    booking_data_complete: bool = True
    workload_data_complete: bool = True
    availability_data_complete: bool = True
    qualifications: list[Qualification] = Field(default_factory=list)
    availability: list[Availability] = Field(default_factory=list)
    bookings: list[Booking] = Field(default_factory=list)


class CrewMember(Value):
    worker_id: UUID
    valid_from: date
    valid_to: date | None

    @model_validator(mode="after")
    def positive_membership(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("crew membership ends before it starts")
        return self


class Crew(Value):
    crew_id: UUID
    site_id: UUID
    name: Text
    active: bool
    members: list[CrewMember]


class AssignmentRequest(Contract):
    task_id: UUID
    site_id: UUID
    expected_revision: PositiveInt
    timezone: Text
    as_of: AwareDatetime
    window: TimeInterval
    earliest_at: AwareDatetime | None
    deadline_at: AwareDatetime | None
    duration_minutes: Annotated[int, Field(gt=0, le=46080)] | None
    duration_basis: Text | None
    crew_size: PositiveInt
    qualification_ids: list[UUID]
    workers: list[Worker]
    crews: list[Crew] = Field(default_factory=list)
    crew_id: UUID | None = None
    requested_worker_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def consistent_request(self):
        if self.requested_worker_ids is not None:
            if len(self.requested_worker_ids)!=self.crew_size or len(set(self.requested_worker_ids))!=self.crew_size:
                raise ValueError("requested workers must be a complete distinct team")
            if not set(self.requested_worker_ids).issubset({w.worker_id for w in self.workers}):
                raise ValueError("requested worker is outside the site")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown site timezone") from exc
        if (self.window.end_at.astimezone(timezone.utc) - self.window.start_at.astimezone(timezone.utc)).total_seconds() > 32 * 86400:
            raise ValueError("search window exceeds 32 days")
        for values, key in ((self.workers, "worker_id"), (self.crews, "crew_id")):
            if len({getattr(value, key) for value in values}) != len(values):
                raise ValueError(f"duplicate {key}")
        if len(set(self.qualification_ids)) != len(self.qualification_ids):
            raise ValueError("duplicate required qualification")
        return self


class WorkerDecision(Value):
    worker_id: UUID
    name: Text
    status: Literal["selected", "available", "excluded"]
    reasons: list[Text]
    explanation: Text
    load_minutes: NonNegativeInt | None
    earliest_start: AwareDatetime | None


class CrewDecision(Value):
    crew_id: UUID
    name: Text
    available: bool
    explanation: Text


class AssignmentSelection(Contract):
    method_version: Text
    status: Literal["ok", "needs_input", "unavailable", "manual_review"]
    error_code: Text | None
    explanation: Text
    command: AssignmentCommand | None
    crew_id: UUID | None
    planning_person_minutes: NonNegativeInt | None
    workers: list[WorkerDecision]
    crews: list[CrewDecision]
