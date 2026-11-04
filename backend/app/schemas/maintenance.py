"""Проектные DTO maintenance-0.1. Не являются реализацией сервера или ORM."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Hours = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1)]
Origin = Literal["customer", "synthetic_demo"]


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CalendarPattern(Value):
    """Shared local-date recurrence for equipment maintenance and employee shifts."""
    frequency: Literal["day", "week", "month", "quarter", "year", "yearly_count", "dates"]
    anchor_date: date
    interval: Annotated[int, Field(ge=1, le=10000)] = 1
    weekdays: list[Annotated[int, Field(ge=1, le=7)]] = Field(default_factory=list)
    week_parity: Literal["any", "even", "odd"] = "any"
    month_days: list[Annotated[int, Field(ge=-1, le=31)]] = Field(default_factory=list)
    months: list[Annotated[int, Field(ge=1, le=12)]] = Field(default_factory=list)
    period_edge: Literal["start", "end"] = "end"
    short_month: Literal["last_day", "skip"] = "last_day"
    count_per_year: Annotated[int, Field(ge=1, le=366)] | None = None
    dates: list[date] = Field(default_factory=list)
    excluded_dates: list[date] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_pattern(self):
        for key in ("weekdays", "month_days", "months", "dates", "excluded_dates"):
            values = getattr(self, key)
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {key}")
        if any(day in (0, -0) for day in self.month_days):
            raise ValueError("month day must be 1..31 or -1 for the last day")
        if self.frequency == "yearly_count":
            if self.count_per_year is None:
                raise ValueError("annual count is required")
        elif self.count_per_year is not None:
            raise ValueError("count_per_year requires yearly_count")
        if self.frequency == "dates" and not self.dates:
            raise ValueError("explicit calendar needs dates")
        if self.frequency=='dates' and (self.interval!=1 or self.weekdays or self.week_parity!='any'):
            raise ValueError('explicit dates cannot have interval or week filters')
        if self.frequency != "dates" and self.dates:
            raise ValueError("dates require dates frequency")
        if self.frequency in ("day", "week", "dates") and (self.months or self.month_days):
            raise ValueError("month selectors require month, quarter or year frequency")
        if self.frequency not in ("year","yearly_count") and self.months:
            raise ValueError("months selector requires annual frequency")
        return self


class Versioned(Value):
    schema_version: Literal["maintenance-0.1"]


class Contract(Versioned):
    data_origin: Origin


class Site(Contract):
    site_id: UUID
    name: Text
    address: Text
    timezone: Text


class Equipment(Contract):
    equipment_id: UUID
    site_id: UUID
    equipment_type_id: UUID
    inventory_code: Text
    name: Text
    commissioned_on: date | None
    state: Literal["active", "out_of_service", "retired"]
    revision: PositiveInt


class ChecklistItem(Value):
    checklist_item_id: UUID
    text: Text
    answer_kind: Literal["boolean", "number", "text"]
    unit: Text | None
    required: bool
    visual_verifiability: Literal["visible", "partial", "not_verifiable"]
    photo_required: bool


class OperationVersion(Contract):
    operation_id: UUID
    operation_version_id: UUID
    version: PositiveInt
    code: Text
    title: Text
    maintenance_type: Literal["ТО1", "ТО2"]
    instructions: Text
    crew_size: PositiveInt
    raw_norm_value: Hours | None
    norm_unit: Literal["unconfirmed", "person_hour", "elapsed_hour"]
    planning_duration_minutes: PositiveInt | None
    duration_basis: Text | None
    qualification_ids: list[UUID]
    checklist: Annotated[list[ChecklistItem], Field(min_length=1)]
    status: Literal["draft", "approved", "retired"]
    source_ref: Text

    @model_validator(mode="after")
    def duration_has_basis(self):
        if self.planning_duration_minutes is not None and not self.duration_basis:
            raise ValueError("confirmed planning duration requires duration_basis")
        ids = [x.checklist_item_id for x in self.checklist]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate checklist item")
        return self


class RecurrenceRule(Contract):
    rule_version_id: UUID
    regulation_version_id: UUID
    source_text: Text
    kind: Literal["calendar_interval", "explicit_dates", "runtime", "calendar_pattern"]
    confirmed: bool
    interval: PositiveInt | None
    calendar_unit: Literal["day", "month"] | None
    anchor_date: date | None
    basis: Literal["fixed_calendar", "after_accepted_completion"] | None
    explicit_dates: list[date]
    yearly_count: PositiveInt | None
    runtime_interval_hours: Hours | None
    allowed_lead_days: NonNegativeInt
    source_ref: Text
    pattern: CalendarPattern | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def confirmed_rule_is_explicit(self):
        if len(set(self.explicit_dates)) != len(self.explicit_dates):
            raise ValueError("duplicate recurrence date")
        if self.explicit_dates != sorted(self.explicit_dates):
            raise ValueError("explicit dates must be sorted")
        if not self.confirmed:
            return self
        if self.kind == "calendar_pattern":
            if self.pattern is None:
                raise ValueError("calendar pattern needs pattern settings")
            if self.explicit_dates or any(x is not None for x in (self.interval, self.calendar_unit, self.anchor_date, self.basis, self.yearly_count, self.runtime_interval_hours)):
                raise ValueError("incompatible pattern rule fields")
            return self
        if self.pattern is not None:
            raise ValueError("pattern settings require calendar_pattern kind")
        if self.kind == "calendar_interval":
            if None in (self.interval, self.calendar_unit, self.anchor_date, self.basis):
                raise ValueError("calendar rule needs interval/unit/anchor/basis")
            if self.explicit_dates or self.yearly_count or self.runtime_interval_hours is not None:
                raise ValueError("incompatible calendar rule fields")
        elif self.kind == "explicit_dates":
            if not self.explicit_dates or self.yearly_count is None:
                raise ValueError("explicit annual rule needs dates and count")
            for year in {d.year for d in self.explicit_dates}:
                if sum(d.year == year for d in self.explicit_dates) != self.yearly_count:
                    raise ValueError("annual date count does not match yearly_count")
            if any(x is not None for x in (self.interval, self.calendar_unit, self.anchor_date, self.basis, self.runtime_interval_hours)):
                raise ValueError("incompatible explicit rule fields")
        else:
            if self.runtime_interval_hours is None or self.runtime_interval_hours <= 0:
                raise ValueError("runtime rule needs positive hour interval")
            if self.explicit_dates or any(x is not None for x in (self.interval, self.calendar_unit, self.anchor_date, self.basis, self.yearly_count)):
                raise ValueError("incompatible runtime rule fields")
        return self


class AcceptedEvent(Value):
    service_event_id: UUID
    performed_at: AwareDatetime
    accepted_at: AwareDatetime
    runtime_hours: Hours | None
    observed_need_date: date | None


class RuntimeReading(Value):
    reading_id: UUID
    measured_at: AwareDatetime
    value_hours: Hours
    meter_epoch: PositiveInt
    verified: bool


class ForecastSnapshot(Contract):
    snapshot_id: UUID
    content_sha256: Digest
    binding_id: UUID
    binding_revision: PositiveInt
    site: Site
    equipment: Equipment
    operation: OperationVersion
    rule: RecurrenceRule
    as_of: AwareDatetime
    horizon_end: date
    earliest_date: date | None
    mandatory_due_date: date | None
    runtime_due_at_hours: Hours | None
    accepted_events: list[AcceptedEvent]
    runtime_reading: RuntimeReading | None
    feature_schema_version: Text

    @model_validator(mode="after")
    def snapshot_is_consistent(self):
        from zoneinfo import ZoneInfo
        local_day = self.as_of.astimezone(ZoneInfo(self.site.timezone)).date()
        if self.horizon_end < local_day:
            raise ValueError("horizon ends before as_of")
        if self.equipment.site_id != self.site.site_id:
            raise ValueError("equipment belongs to another site")
        if any(x.data_origin != self.data_origin for x in (self.site, self.equipment, self.operation, self.rule)):
            raise ValueError("mixed snapshot data origins")
        if self.earliest_date and self.mandatory_due_date and self.earliest_date > self.mandatory_due_date:
            raise ValueError("empty permitted maintenance window")
        for e in self.accepted_events:
            if not e.performed_at <= e.accepted_at <= self.as_of:
                raise ValueError("future or inconsistent accepted history")
            if e.observed_need_date and e.observed_need_date > local_day:
                raise ValueError("future target leaked into inference snapshot")
        if self.runtime_reading and self.runtime_reading.measured_at > self.as_of:
            raise ValueError("future runtime reading")
        return self


class Uncertainty(Value):
    kind: Literal["deterministic", "tree_dispersion", "unknown"]
    lower_date: date | None
    upper_date: date | None
    calibrated: bool
    note: Text

    @model_validator(mode="after")
    def interval_is_valid(self):
        if (self.lower_date is None) != (self.upper_date is None):
            raise ValueError("both interval bounds must be null or set")
        if self.lower_date and self.lower_date > self.upper_date:
            raise ValueError("inverted uncertainty interval")
        if self.kind == "tree_dispersion" and self.calibrated:
            raise ValueError("tree dispersion is not calibrated confidence")
        return self


class ForecastResult(Contract):
    result_id: UUID
    run_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Digest
    equipment_id: UUID
    binding_id: UUID
    as_of: AwareDatetime
    method: Literal["algorithmic", "ai"]
    method_version: Text
    model_ref: Text | None
    status: Literal["ok", "needs_input", "unavailable", "failed"]
    recommended_date: date | None
    mandatory_due_date: date | None
    runtime_due_at_hours: Hours | None
    overdue: bool
    uncertainty: Uncertainty
    explanation: Text
    warnings: list[Text]
    error_code: Text | None
    elapsed_ms: NonNegativeInt

    @model_validator(mode="after")
    def status_has_payload(self):
        if self.status == "ok":
            if self.recommended_date is None or self.error_code is not None:
                raise ValueError("ok needs a date and no error_code")
        elif self.recommended_date is not None or self.error_code is None:
            raise ValueError("non-ok needs null date and an error_code")
        if self.method == "ai" and self.status == "ok" and not self.model_ref:
            raise ValueError("successful ai needs a versioned model_ref")
        return self


class OrchestrationDecision(Contract):
    orchestration_id: UUID
    run_id: UUID
    snapshot_id: UUID
    algorithmic_result_id: UUID
    ai_result_id: UUID
    status: Literal["selected", "fallback", "needs_input", "manual_review"]
    selected_date: date | None
    policy_version: Text
    reasons: Annotated[list[Text], Field(min_length=1)]
    created_at: AwareDatetime

    @model_validator(mode="after")
    def selection_has_date(self):
        if (self.status in ("selected", "fallback")) != (self.selected_date is not None):
            raise ValueError("date only for selected/fallback")
        return self


class PlanOccurrence(Value):
    occurrence_id: UUID
    binding_id: UUID
    rule_version_id: UUID
    operation_version_id: UUID
    occurrence_date: date
    earliest_date: date | None
    mandatory_due_date: date | None
    runtime_due_at_hours: Hours | None
    status: Literal["draft", "planned", "fulfilled", "cancelled"]
    revision: PositiveInt
    task_id: UUID | None


class Schedule(Contract):
    plan_id: UUID
    site_id: UUID
    period_start: date
    period_end: date
    status: Literal["draft", "approved"]
    revision: PositiveInt
    occurrences: list[PlanOccurrence]

    @model_validator(mode="after")
    def period_contains_occurrences(self):
        if self.period_end < self.period_start:
            raise ValueError("inverted plan period")
        if any(not self.period_start <= x.occurrence_date <= self.period_end for x in self.occurrences):
            raise ValueError("occurrence outside plan period")
        return self


class Assignment(Contract):
    assignment_id: UUID
    task_id: UUID
    executor_id: UUID
    start_at: AwareDatetime
    end_at: AwareDatetime
    qualification_ids: list[UUID]
    status: Literal["active", "released"]
    assigned_by: UUID

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_at <= self.start_at:
            raise ValueError("empty assignment interval")
        return self


class Task(Contract):
    task_id: UUID
    occurrence_id: UUID
    equipment_id: UUID
    operation_version_id: UUID
    state: Literal["draft", "assigned", "in_progress", "submitted", "rework_required", "accepted", "cancelled"]
    revision: PositiveInt
    scheduled_start: AwareDatetime | None
    scheduled_end: AwareDatetime | None
    assignment_ids: list[UUID]
    active_execution_id: UUID | None
    deadline_breached: bool

    @model_validator(mode="after")
    def schedule_is_valid(self):
        if (self.scheduled_start is None) != (self.scheduled_end is None):
            raise ValueError("both scheduled interval bounds are required")
        if self.scheduled_start and self.scheduled_end <= self.scheduled_start:
            raise ValueError("empty task interval")
        return self


class ChecklistAnswer(Value):
    checklist_item_id: UUID
    status: Literal["done", "not_done", "not_applicable"]
    value: bool | Decimal | str | None
    unit: Text | None
    comment: Text | None
    completed_at: AwareDatetime | None


class ExecutionReport(Contract):
    execution_id: UUID
    task_id: UUID
    attempt_number: PositiveInt
    state: Literal["draft", "submitted"]
    performed_at: AwareDatetime | None
    submitted_at: AwareDatetime | None
    submitted_by: UUID
    narrative: Text
    answers: Annotated[list[ChecklistAnswer], Field(min_length=1)]
    photo_ids: list[UUID]

    @model_validator(mode="after")
    def submitted_has_times(self):
        if self.state == "submitted" and (self.performed_at is None or self.submitted_at is None):
            raise ValueError("submitted report needs performed/submitted times")
        if self.performed_at and self.submitted_at and self.performed_at > self.submitted_at:
            raise ValueError("performed_at after submission")
        return self


class PhotoReport(Contract):
    photo_id: UUID
    execution_id: UUID
    equipment_id: UUID
    checklist_item_id: UUID
    phase: Literal["before", "after"]
    view_key: Text
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    file_size_bytes: Annotated[int, Field(gt=0, le=10485760)]
    width: PositiveInt
    height: PositiveInt
    original_sha256: Digest
    captured_at: AwareDatetime | None
    uploaded_at: AwareDatetime
    uploaded_by: UUID
    content_url: Annotated[str, Field(pattern=r"^/api/v1/maintenance/photos/[0-9a-f-]+/content$")]

    @model_validator(mode="after")
    def safe_dimensions_and_times(self):
        if self.width * self.height > 20_000_000:
            raise ValueError("photo exceeds pixel limit")
        if self.captured_at and self.captured_at > self.uploaded_at:
            raise ValueError("capture time after upload")
        return self


class PhotoReviewRequest(Contract):
    execution_id: UUID
    operation: OperationVersion
    photos: Annotated[list[PhotoReport], Field(min_length=2)]
    report: ExecutionReport
    prompt_set_version: Text

    @model_validator(mode="after")
    def same_execution(self):
        if self.report.execution_id != self.execution_id or any(p.execution_id != self.execution_id for p in self.photos):
            raise ValueError("photo/report execution mismatch")
        if self.report.state != "submitted":
            raise ValueError("only frozen submitted reports can be reviewed")
        if any(p.photo_id not in self.report.photo_ids for p in self.photos):
            raise ValueError("photo absent from report")
        if any(p.checklist_item_id not in {c.checklist_item_id for c in self.operation.checklist} for p in self.photos):
            raise ValueError("photo belongs to another checklist version")
        if len({p.equipment_id for p in self.photos}) != 1:
            raise ValueError("mixed equipment photos")
        return self


class ImageLabelScore(Value):
    photo_id: UUID
    label: Text
    score: Annotated[float, Field(ge=0, le=1)]


class VisualAssessment(Value):
    """Observed photo content, separate from an engineer's acceptance decision."""
    subject_matches_task: Literal["yes", "no", "uncertain"]
    same_subject: Literal["yes", "no", "uncertain"]
    comparable: Literal["yes", "no", "uncertain"]
    before_description: Annotated[str, Field(min_length=1, max_length=2000)]
    after_description: Annotated[str, Field(min_length=1, max_length=2000)]
    visible_changes: Annotated[list[Annotated[str, Field(min_length=1, max_length=800)]], Field(max_length=8)]
    concerns: Annotated[list[Annotated[str, Field(min_length=1, max_length=800)]], Field(max_length=8)]
    recommended_actions: Annotated[list[Annotated[str, Field(min_length=1, max_length=800)]], Field(max_length=8)]
    cannot_confirm: Annotated[list[Annotated[str, Field(min_length=1, max_length=800)]], Field(min_length=1, max_length=8)]
    conclusion: Literal["visible_improvement", "no_clear_improvement", "insufficient_evidence"]
    summary: Annotated[str, Field(min_length=1, max_length=2000)]


class ItemPhotoReview(Value):
    checklist_item_id: UUID
    verdict: Literal["visible_change", "no_visible_change", "uncertain", "not_verifiable"]
    before_photo_id: UUID | None
    after_photo_id: UUID | None
    observation: Text
    scores: list[ImageLabelScore]
    visual_assessment: VisualAssessment | None = None


class PhotoReviewResult(Contract):
    ai_review_id: UUID
    execution_id: UUID
    operation_version_id: UUID
    status: Literal["completed", "uncertain", "not_verifiable", "unavailable", "failed"]
    model_ref: Text | None
    prompt_set_version: Text
    input_photo_ids: list[UUID]
    item_results: list[ItemPhotoReview]
    limitations: Annotated[list[Text], Field(min_length=1)]
    error_code: Text | None
    elapsed_ms: NonNegativeInt
    created_at: AwareDatetime


class EngineerDecision(Contract):
    decision_id: UUID
    execution_id: UUID
    engineer_id: UUID
    verdict: Literal["accepted", "rejected"]
    reason: Text
    reviewed_ai_result_id: UUID | None
    additional_evidence_refs: list[Text]
    decided_at: AwareDatetime


class AssignmentCommand(Versioned):
    expected_revision: PositiveInt
    executor_ids: Annotated[list[UUID], Field(min_length=1)]
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: Text


class ReviewCommand(Versioned):
    expected_revision: PositiveInt
    execution_id: UUID
    verdict: Literal["accepted", "rejected"]
    reason: Text
    reviewed_ai_result_id: UUID | None
    additional_evidence_refs: list[Text]


class ErrorDetail(Value):
    field: Text
    issue: Text


class ErrorInfo(Value):
    code: Text
    message: Text
    details: list[ErrorDetail]
    request_id: Text


class ErrorResponse(Versioned):
    error: ErrorInfo
    detail: Text | None = Field(default=None, exclude_if=lambda value: value is None)


# Канонические имена $defs. Для обоих методов используется один ForecastResult.
CONTRACTS = {c.__name__: c for c in (
    Site, Equipment, OperationVersion, RecurrenceRule, ForecastSnapshot,
    ForecastResult, OrchestrationDecision, Schedule, Assignment, Task,
    ExecutionReport, PhotoReport, PhotoReviewRequest, PhotoReviewResult,
    EngineerDecision, AssignmentCommand, ReviewCommand, ErrorResponse,
)}
