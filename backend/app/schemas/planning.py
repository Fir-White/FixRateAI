"""Read-only workload contracts. A staffing lower bound never reserves a worker."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, model_validator

from app.assignment.schemas import Worker
from app.schemas.maintenance import Digest, Origin, Text, Value

PersonHours = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
CapacityHours = Annotated[Decimal, Field(gt=0, le=24, decimal_places=3, allow_inf_nan=False)]


class WorkloadDemand(Value):
    occurrence_id: UUID
    date: date
    equipment_name: Text
    operation_title: Text
    data_origin: Origin
    person_hours: PersonHours | None
    crew_size: int = Field(ge=1)
    state: Literal['unassigned', 'assigned', 'reported', 'incomplete'] = 'unassigned'
    assigned_worker_ids: list[UUID] = Field(default_factory=list)


class WorkloadRequest(Value):
    site_id: UUID
    timezone: Text
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    as_of: AwareDatetime
    capacity_hours_per_24h: CapacityHours
    demands: list[WorkloadDemand]
    workers: list[Worker]
    source_incomplete: bool = False

    @model_validator(mode='after')
    def unique_context(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('unknown site timezone') from exc
        for rows, key in ((self.demands, 'occurrence_id'), (self.workers, 'worker_id')):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError('duplicate workload input')
        if any(worker.site_id != self.site_id for worker in self.workers):
            raise ValueError('worker belongs to another site')
        return self


class DailyWorkload(Value):
    date: date
    occurrences: list[WorkloadDemand]
    total_person_hours: PersonHours | None
    known_person_hours: PersonHours
    unassigned_person_hours: PersonHours | None
    required_workers_lower_bound: int | None
    free_workers: int
    assigned_workers: int
    free_person_hours: PersonHours | None
    known_free_person_hours: PersonHours
    deficit_person_hours: PersonHours | None
    unknown_norms: int
    unknown_workers: int
    status: Literal['hours_deficit', 'hours_sufficient', 'incomplete', 'no_work']


class WorkloadResponse(Value):
    method_version: str = 'workload-lower-bound-v1'
    site_id: UUID
    year: int
    month: int
    timezone: Text
    calculated_at: AwareDatetime
    capacity_hours_per_24h: CapacityHours
    policy_status: Literal['provisional'] = 'provisional'
    snapshot_sha256: Digest
    source_incomplete: bool
    total_occurrences: int
    unassigned_occurrences: int
    deficit_days: int
    incomplete_days: int
    diagnostics: list[Text]
    days: list[DailyWorkload]
