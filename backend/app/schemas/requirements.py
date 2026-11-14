"""Read-only common obligation ledger; not a staffing or published-plan DTO."""
from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from app.schemas.draft_plans import Model,GenerationInput,AllowedInterval

class RequirementsRequest(Model):
    starts_on: date
    ends_on: date
    include_regulations: bool = True
    binding_ids: list[UUID] = Field(default_factory=list,max_length=500)
    catalog: GenerationInput | None = None
    offset: int = Field(default=0,ge=0,le=1000000)
    issue_offset: int = Field(default=0,ge=0,le=1000000)
    q: str = Field(default='',max_length=320)
    state: Literal['all','new','existing','fulfilled','review'] = 'all'

    @model_validator(mode='after')
    def coherent(self):
        if not date(2000,1,1)<=self.starts_on<=self.ends_on<=date(2200,12,31) or (self.ends_on-self.starts_on).days>365:
            raise ValueError('Выберите горизонт от одного дня до 366 дней')
        if len(set(self.binding_ids))!=len(self.binding_ids):raise ValueError('Привязки не должны повторяться')
        if not self.include_regulations and (self.binding_ids or self.catalog is None):raise ValueError('Выберите хотя бы один источник обязательств')
        if self.catalog and (self.catalog.starts_on,self.catalog.ends_on)!=(self.starts_on,self.ends_on):raise ValueError('Источники должны использовать один горизонт')
        return self

class RequirementIssue(Model):
    source_kind: Literal['regulation','catalog']
    code: str
    message: str
    source_label: str = ''
    binding_id: UUID | None = None
    import_id: UUID | None = None
    source_row: int | None = None

class Requirement(Model):
    requirement_id: UUID
    source_kind: Literal['regulation','catalog']
    binding_id: UUID | None = None
    rule_id: UUID | None = None
    regulation_id: UUID | None = None
    source_revision: int
    import_id: UUID | None = None
    source_row: int | None = None
    source_ref: str
    equipment_ids: list[UUID]
    equipment_labels: list[str]
    operation_code: str
    title: str
    maintenance_type: str
    source_date: date
    source_slot: Literal['whole_day','day','night'] = 'whole_day'
    earliest_date: date
    due_date: date
    allowed_intervals: list[AllowedInterval] = Field(default_factory=list,max_length=366)
    person_hours: Decimal | None
    crew_size: int
    qualification_ids: list[UUID]
    state: Literal['new','existing','fulfilled','review']
    task_ids: list[UUID] = Field(default_factory=list)
    explanation: str
    issues: list[str] = Field(default_factory=list)
    synthetic: bool

class RequirementsSummary(Model):
    total: int
    known_person_hours: Decimal
    total_person_hours: Decimal | None
    new_person_hours: Decimal | None
    unknown_hours_count: int
    state_counts: dict[str,int]
    source_counts: dict[str,int]
    binding_count: int
    selected_catalog_rows: int
    unselected_catalog_rows: int
    complete: bool

class RequirementsPreview(Model):
    method_version: str = 'requirements-v1'
    starts_on: date
    ends_on: date
    timezone: str
    calculated_at: datetime
    source_sha256: str
    summary: RequirementsSummary
    months: list[dict]
    items: list[Requirement]
    total: int
    issues: list[RequirementIssue]
    total_issues: int
    ready_for_real_plan: Literal[False] = False

REQUIREMENTS_CONTRACTS=(RequirementsRequest,RequirementsPreview)
