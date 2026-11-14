"""Engineer decisions are separate from immutable source observations."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
import json
from app.schemas.maintenance import CalendarPattern

class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    interpretation: Literal['UNKNOWN','FIXED_EXECUTION','ALLOWED_WINDOW','CONTINUOUS_WORK','EQUIPMENT_BATCH'] = 'UNKNOWN'
    calendar_year: int | None = Field(default=None, ge=2000, le=2200)
    mark_slots: Literal['unconfirmed','one_per_mark','day_night'] = 'unconfirmed'
    semantics_note: str = Field(default='', max_length=2000)
    frequency_kind: Literal['unconfirmed','day','week','month','quarter','year','yearly_count','dates','daily_events','event','included_in'] = 'unconfirmed'
    frequency_interval: int | None = Field(default=None, ge=1, le=100)
    included_in_row: int | None = Field(default=None, ge=1, le=1048576)
    equipment_ids: list[UUID] = Field(default_factory=list, max_length=100)
    norm_value: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3, allow_inf_nan=False)
    norm_unit: Literal['unconfirmed','person_hour','elapsed_hour'] = 'unconfirmed'
    norm_scope: Literal['unconfirmed','per_asset','whole_binding'] = 'unconfirmed'
    crew_size: int | None = Field(default=None, ge=1, le=100)
    norm_ref: str = Field(default='', max_length=2000)
    splittable: bool | None = None
    min_segment_minutes: int | None = Field(default=None, ge=1, le=46080)
    policy_note: str = Field(default='', max_length=2000)
    calendar_pattern: CalendarPattern | None = None
    allowed_lead_days: int = Field(default=0, ge=0, le=366)
    qualifications_confirmed: bool = False
    qualification_ids: list[UUID] = Field(default_factory=list, max_length=100)
    qualification_note: str = Field(default='', max_length=2000)

    @field_validator('calendar_pattern',mode='before')
    @classmethod
    def calendar_json(cls,value):
        return CalendarPattern.model_validate_json(json.dumps(value)) if isinstance(value,dict) else value

    @model_validator(mode='after')
    def coherent(self):
        if len(self.equipment_ids) != len(set(self.equipment_ids)):
            raise ValueError('Оборудование не должно повторяться')
        if self.frequency_kind != 'included_in' and self.included_in_row is not None:
            raise ValueError('Родительская операция задаётся только для работы в составе ТО')
        if self.frequency_kind == 'included_in' and self.norm_value is not None:
            raise ValueError('Работа в составе ТО не имеет самостоятельной нормы: часы учитываются у родителя')
        if self.splittable is False and self.min_segment_minutes is not None:
            raise ValueError('Минимальный сегмент задаётся только при разрешённом разделении')
        if len(self.qualification_ids) != len(set(self.qualification_ids)):
            raise ValueError('Допуски не должны повторяться')
        if self.qualifications_confirmed and not self.qualification_note:
            raise ValueError('Укажите основание подтверждённых требований к допускам')
        if self.calendar_pattern and self.frequency_kind in ('event','included_in'):
            raise ValueError('Событийная или включённая работа не получает автоматическое календарное правило')
        if self.calendar_pattern and max(len(self.calendar_pattern.dates),len(self.calendar_pattern.excluded_dates))>1000:
            raise ValueError('Календарное правило ограничено 1000 явных дат и исключений')
        if self.calendar_pattern and self.frequency_kind != 'unconfirmed':
            expected='day' if self.frequency_kind=='daily_events' else self.frequency_kind
            step=1 if self.frequency_kind in ('daily_events','yearly_count') else self.frequency_interval
            if self.calendar_pattern.frequency != expected or (step is not None and self.calendar_pattern.interval != step):
                raise ValueError('Календарное правило расходится с подтверждённой периодичностью')
            if self.frequency_kind=='yearly_count' and self.calendar_pattern.count_per_year != self.frequency_interval:
                raise ValueError('Число выполнений за год расходится с подтверждённой периодичностью')
        if self.frequency_kind in ('day','daily_events') and self.allowed_lead_days:
            raise ValueError('Для ежедневных событий не задаётся заблаговременное выполнение')
        return self

class DecisionCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_revision: int = Field(ge=0, le=2147483646)
    confirm: bool = False
    reason: str = Field(min_length=1, max_length=2000)
    decision: DecisionInput

class BindingOption(BaseModel):
    equipment_id: UUID
    asset_code: str
    name: str
    status: str
    revision: int

class BindingOptions(BaseModel):
    items: list[BindingOption]
    total: int

class DecisionRecord(BaseModel):
    row_number: int
    revision: int
    created_by: UUID | None = None
    author_name: str | None = None
    created_at: datetime | None = None
    confirmed: bool
    reason: str
    decision: DecisionInput
    equipment: list[BindingOption]
    qualification_labels: dict[str,str] = Field(default_factory=dict)
    blockers: list[str]
    prepared: bool
    total_person_hours: Decimal | None
    elapsed_hours: Decimal | None
    ready_for_real_plan: Literal[False] = False

class DecisionProgressItem(BaseModel):
    row_number: int
    revision: int
    confirmed: bool
    prepared: bool
    blockers: list[str]

class DecisionProgress(BaseModel):
    total: int
    prepared_count: int
    confirmed_count: int
    blocker_counts: dict[str,int]
    items: list[DecisionProgressItem]
    ready_for_real_plan: Literal[False] = False

class DecisionHistoryItem(BaseModel):
    revision: int
    created_by: UUID
    author_name: str
    created_at: datetime
    confirmed: bool
    reason: str
    decision: DecisionInput
    equipment: list[BindingOption]
    parent_revision: int | None

class DecisionHistory(BaseModel):
    items: list[DecisionHistoryItem]
    total: int

DECISION_CONTRACTS=(DecisionCommand,DecisionRecord,DecisionProgress,DecisionHistory,BindingOptions)
