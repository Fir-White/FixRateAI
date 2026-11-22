"""Parameters and receipts for read-only analytical dataflow."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


Projection = Literal['equipment_details', 'overdue_tasks', 'latest_maintenance', 'maintenance_history',
                     'active_regulations', 'maintenance_calendar', 'staff_details',
                     'staff_assignments', 'task_details', 'task_materials']
Group = Literal['equipment', 'assignee', 'period', 'task']
Metric = Literal['overdue', 'unfinished', 'planned', 'earliest_overdue', 'missing_materials', 'without_service']
Resource = Literal['equipment', 'assignee', 'task']
MAX_AGGREGATE_ROWS = 100


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Window(AnalyticsModel):
    starts_on: date
    ends_on: date

    @model_validator(mode='after')
    def ordered(self):
        if self.ends_on < self.starts_on or (self.ends_on - self.starts_on).days > 3660:
            raise ValueError('Invalid date range')
        return self


class AggregateQuery(AnalyticsModel):
    group_by: Group
    metric: Metric
    limit: int = Field(default=5, ge=1, le=MAX_AGGREGATE_ROWS)
    offset: int = Field(default=0, ge=0)
    as_of: date | None = None
    windows: list[Window] = Field(default_factory=list, max_length=2)
    include_overdue_tasks: bool = False
    include_assignments: bool = False

    @model_validator(mode='after')
    def supported(self):
        if self.as_of and not 2 <= self.as_of.year <= 9997:
            raise ValueError('As-of date is out of range')
        if self.offset and (self.group_by not in ('equipment', 'assignee') or self.metric not in ('unfinished', 'overdue')):
            raise ValueError('Only rankings support an offset')
        if self.group_by == 'period':
            if self.metric != 'planned' or len(self.windows) != 2 or self.windows[0] == self.windows[1]:
                raise ValueError('Specify two different planning periods')
        elif self.group_by == 'task':
            if self.metric not in ('earliest_overdue', 'missing_materials') or len(self.windows) > 1:
                raise ValueError('Unsupported task selector')
        elif self.metric == 'without_service':
            if self.group_by != 'equipment' or len(self.windows) != 1:
                raise ValueError('Service coverage requires one exact equipment history period')
        elif self.metric not in ('unfinished', 'overdue') or len(self.windows) > 1:
            raise ValueError('Rank by overdue or unfinished work in at most one period')
        if self.include_overdue_tasks and self.group_by != 'equipment':
            raise ValueError('Overdue work details require equipment grouping')
        if self.include_assignments and self.group_by != 'assignee':
            raise ValueError('Assignments require staff grouping')
        return self


class AnalysisRequest(AnalyticsModel):
    source_text: str = Field(min_length=2, max_length=700)
    group_by: Group
    metric: Metric
    limit: int | None = Field(default=None, ge=1, le=MAX_AGGREGATE_ROWS)
    all_groups: bool = False
    as_of: date | None = None
    windows: list[Window] = Field(default_factory=list, max_length=2)
    projections: list[Projection] = Field(default_factory=list, max_length=9)
    history_months: int | None = Field(default=None, ge=1, le=120)
    calendar_months: int | None = Field(default=None, ge=1, le=120)
    compare: bool = False
    recommendations: int | None = Field(default=None, ge=1, le=10)


class OverdueTask(AnalyticsModel):
    task_id: UUID
    title: str
    state: str
    deadline_at: str | None
    deadline_on: date


class AssignmentRow(AnalyticsModel):
    assignment_id: UUID
    task_id: UUID
    title: str
    state: str
    status: str
    start_at: str | None
    end_at: str | None


class AggregateRow(AnalyticsModel):
    id: UUID | None
    label: str
    code: str | None = None
    state: str | None = None
    window: Window | None = None
    unfinished: int = Field(ge=0)
    overdue: int = Field(ge=0)
    planned: int = Field(default=0, ge=0)
    undated: int = Field(ge=0)
    oldest_due: date | None = None
    overdue_tasks: list[OverdueTask] | None = None
    assignments: list[AssignmentRow] | None = None
    assignment_total: int | None = Field(default=None, ge=0)
    deadline_at: AwareDatetime | None = None
    deadline_on: date | None = None


class AggregateResult(AnalyticsModel):
    site_id: UUID
    timezone: str
    as_of: date
    cutoff: str
    historical_cutoff: bool
    query: AggregateQuery
    eligible_groups: int = Field(ge=0)
    groups: list[AggregateRow]
    complete: Literal[True]
    unresolved_groups: int = Field(default=0, ge=0)
    tied_groups: int = Field(default=0, ge=0)


class ResourceRef(AnalyticsModel):
    kind: Resource
    id: UUID
    revision: int | None = Field(default=None, ge=1)
    execution_id: UUID | None = None


class SelectedInput(AnalyticsModel):
    source_goal: str
    projection: Projection
    months: int | None = Field(default=None, ge=1, le=120)
    window: Window | None = None
    resource: Resource | None = None


class TaskAcceptanceReceipt(AnalyticsModel):
    task_id: UUID
    revision: int = Field(ge=1)
    execution_id: UUID | None
    task_state: str
    report_state: Literal['draft','submitted'] | None
    submitted_at: str | None
    checklist: list[dict]
    photos: list[dict]
    missing_materials: list[str]
    acceptance_blocks: list[str]
    saved_photo_analysis: str
    photo_classification: str | None
    ready: bool

    @model_validator(mode='after')
    def consistent(self):
        if self.ready != (not self.missing_materials and not self.acceptance_blocks):
            raise ValueError('Inconsistent acceptance evidence')
        return self
