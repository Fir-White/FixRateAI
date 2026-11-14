"""Common obligations and segments shared by year/month projections and edits."""
from datetime import date, datetime
from datetime import date as Date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator, model_serializer

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class ServiceWindow(Model):
    weekday: int = Field(ge=1,le=7,strict=True)
    start_minute: int = Field(ge=0,le=1439,strict=True)
    end_minute: int = Field(ge=1,le=2879,strict=True)

    @model_validator(mode='after')
    def coherent(self):
        if not self.start_minute<self.end_minute<=self.start_minute+1440:
            raise ValueError('Окно должно длиться от одной минуты до 24 часов; ночное окончание относится к следующим суткам')
        return self

class DraftPolicy(Model):
    format_version: Literal[1,2] = 1
    capacity_hours_per_24h: Decimal | None = Field(default=None,gt=0,le=24,decimal_places=3,allow_inf_nan=False)
    capacity_confirmed: bool = False
    capacity_ref: str = Field(default='',max_length=2000)
    day_start_minute: int | None = Field(default=None,ge=0,le=1439)
    night_start_minute: int | None = Field(default=None,ge=0,le=1439)
    capacity_status: Literal['unknown','provisional','confirmed'] | None = None
    access_status: Literal['unknown','provisional','confirmed'] = 'unknown'
    access_mode: Literal['unrestricted','weekly'] | None = None
    access_ref: str = Field(default='',max_length=2000)
    service_windows: list[ServiceWindow] = Field(default_factory=list,max_length=28)

    @model_serializer(mode='wrap')
    def stable_legacy_snapshot(self,handler):
        value=handler(self)
        if self.format_version==1:
            # Existing signatures/idempotency keys and approved snapshots retain
            # precisely their original representation after schema evolution.
            for field in ('format_version','capacity_status','access_status','access_mode','access_ref','service_windows'):
                value.pop(field,None)
        return value

    @model_validator(mode='after')
    def coherent(self):
        if self.format_version==1:
            if self.capacity_status is not None or self.access_status!='unknown' or self.access_mode is not None or self.access_ref or self.service_windows:
                raise ValueError('Для статусов и окон доступа используйте версию параметров 2')
        else:
            if self.capacity_status is None or self.capacity_confirmed!=(self.capacity_status=='confirmed'):
                raise ValueError('Статус ёмкости должен соответствовать её подтверждению')
            if self.capacity_status!='unknown' and self.capacity_hours_per_24h is None:
                raise ValueError('Для предварительной или подтверждённой ёмкости укажите значение')
            if self.access_status=='confirmed' and (not self.access_ref or self.access_mode is None):
                raise ValueError('Укажите режим доступа и основание подтверждения окон')
            if self.access_mode=='weekly' and not self.service_windows:
                raise ValueError('Для недельного режима добавьте хотя бы одно окно доступа')
            if self.access_mode!='weekly' and self.service_windows:
                raise ValueError('Окна задаются только для недельного режима доступа')
            canonical=sorted(self.service_windows,key=lambda w:(w.weekday,w.start_minute,w.end_minute))
            spans=[]
            for window in canonical:
                left=(window.weekday-1)*1440+window.start_minute;right=(window.weekday-1)*1440+window.end_minute
                for offset in (-10080,0,10080):spans.append((left+offset,right+offset))
            spans.sort()
            if any(left<previous_end for (_,previous_end),(left,_) in zip(spans,spans[1:])):
                raise ValueError('Недельные окна доступа не должны пересекаться, включая переход воскресенье/понедельник')
            self.service_windows=canonical
        if (self.day_start_minute is None)!=(self.night_start_minute is None):
            raise ValueError('Задайте обе границы дневного и ночного события')
        if self.day_start_minute is not None and self.day_start_minute>=self.night_start_minute:
            raise ValueError('Начало ночного события должно следовать после начала дневного')
        if self.capacity_confirmed and (not self.capacity_ref or self.capacity_hours_per_24h is None):
            raise ValueError('Укажите источник полезной ёмкости')
        return self

class ChangeDraftPolicy(Model):
    expected_revision: int = Field(ge=1)
    idempotency_key: UUID
    reason: str = Field(min_length=1,max_length=2000)
    policy: DraftPolicy

    @model_validator(mode='after')
    def coherent(self):
        if self.policy.format_version!=2:raise ValueError('Новые параметры сохраняются в формате версии 2')
        return self

class GenerationInput(Model):
    import_id: UUID
    starts_on: date
    ends_on: date
    row_numbers: list[int] = Field(min_length=1,max_length=1000)
    expansion: Literal['source_january','confirmed_rule'] = 'source_january'
    policy: DraftPolicy

    @model_validator(mode='after')
    def coherent(self):
        if not date(2000,1,1)<=self.starts_on<=self.ends_on<=date(2200,12,31) or (self.ends_on-self.starts_on).days>365:
            raise ValueError('Горизонт должен покрывать от одного дня до 366 дней')
        if len(set(self.row_numbers))!=len(self.row_numbers) or any(n<1 or n>1048576 for n in self.row_numbers):
            raise ValueError('Выберите неповторяющиеся строки исходника')
        return self

class PlanIssue(Model):
    code: str
    message: str
    row_number: int | None = None
    occurrence_id: UUID | None = None
    segment_id: UUID | None = None
    date: Date | None = None

class AllowedInterval(Model):
    start_at: AwareDatetime
    end_at: AwareDatetime

class WorkOccurrence(Model):
    occurrence_id: UUID
    site_id: UUID
    import_id: UUID | None
    source_sha256: str
    parser_version: str
    source_row: int | None
    decision_revision: int | None
    source_cells: list[str]
    source_date: date
    source_slot: Literal['whole_day','day','night']
    date_basis: Literal['source_january','confirmed_rule','regulation_rule','accepted_history'] = 'source_january'
    source_kind: Literal['catalog','regulation'] = 'catalog'
    binding_id: UUID | None = None
    rule_id: UUID | None = None
    regulation_id: UUID | None = None
    minimum_duration_minutes: int | None = Field(default=None,gt=0,le=46080)
    title: str
    operation_code: str
    maintenance_type: str
    interpretation: Literal['FIXED_EXECUTION','ALLOWED_WINDOW','CONTINUOUS_WORK','EQUIPMENT_BATCH']
    equipment_ids: list[UUID]
    earliest_date: date
    latest_date: date
    allowed_intervals: list[AllowedInterval] = Field(max_length=366)
    total_person_hours: Decimal = Field(gt=0,allow_inf_nan=False)
    crew_size: int = Field(ge=1,le=100)
    splittable: bool
    min_segment_minutes: int | None
    qualification_ids: list[UUID]
    qualifications_confirmed: bool
    included_rows: list[int]
    norm_ref: str
    norm_scope: Literal['per_asset','whole_binding']
    policy_note: str

    @model_validator(mode='after')
    def lineage(self):
        if self.source_kind=='catalog':
            if self.import_id is None or self.source_row is None or self.decision_revision is None or any((self.binding_id,self.rule_id,self.regulation_id)):
                raise ValueError('Каталожная работа должна ссылаться на строку исходного Excel')
        elif self.import_id is not None or self.source_row is not None or self.decision_revision is not None or not all((self.binding_id,self.rule_id,self.regulation_id,self.minimum_duration_minutes)):
            raise ValueError('Регламентная работа должна ссылаться на реальные привязку/правило/редакцию и подтверждённую длительность')
        return self

    @model_serializer(mode='wrap')
    def stable_snapshot(self,handler):
        value=handler(self)
        if self.source_kind=='catalog':
            for key in ('source_kind','binding_id','rule_id','regulation_id'):value.pop(key,None)
        if self.minimum_duration_minutes is None:value.pop('minimum_duration_minutes',None)
        return value

class WorkSegment(Model):
    segment_id: UUID
    occurrence_id: UUID
    equipment_ids: list[UUID] = Field(min_length=1,max_length=100)
    person_hours: Decimal = Field(gt=0,max_digits=20,decimal_places=3,allow_inf_nan=False)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    worker_ids: list[UUID] = Field(default_factory=list,max_length=100)
    locked: bool = False
    depends_on_segment_ids: list[UUID] = Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def coherent(self):
        from datetime import timezone
        if (self.start_at is None)!=(self.end_at is None): raise ValueError('Нужны начало и конец сегмента')
        if self.start_at and self.end_at.astimezone(timezone.utc)<=self.start_at.astimezone(timezone.utc):
            raise ValueError('Конец сегмента должен следовать после начала')
        if len(set(self.equipment_ids))!=len(self.equipment_ids) or len(set(self.worker_ids))!=len(self.worker_ids):
            raise ValueError('Ресурсы сегмента не должны повторяться')
        if len(set(self.depends_on_segment_ids))!=len(self.depends_on_segment_ids) or self.segment_id in self.depends_on_segment_ids:
            raise ValueError('Зависимости не должны повторяться или ссылаться на сам сегмент')
        if self.locked and (not self.start_at or not self.worker_ids): raise ValueError('Закрепите только размещённый сегмент с бригадой')
        return self

class GenerationPreview(Model):
    input_sha256: str
    generator_version: str
    total_occurrences: int
    total_segments: int
    total_person_hours: Decimal
    selected_rows: int
    unselected_rows: int
    can_save: bool
    issues: list[PlanIssue]
    total_issues: int
    items: list[WorkOccurrence]
    ready_for_real_plan: Literal[False] = False

class SaveDraft(Model):
    input: GenerationInput
    preview_sha256: str = Field(pattern='^[0-9a-f]{64}$')
    idempotency_key: UUID
    title: str = Field(min_length=1,max_length=256)
    reason: str = Field(min_length=1,max_length=2000)

class EditSegments(Model):
    expected_revision: int = Field(ge=1)
    occurrence_id: UUID
    segments: list[WorkSegment] = Field(min_length=1,max_length=1000)
    replace_segment_ids: list[UUID] | None = Field(default=None,min_length=1,max_length=1000)
    unlock: bool = False
    reason: str = Field(min_length=1,max_length=2000)

class LocalPlacement(Model):
    expected_revision: int = Field(ge=1)
    segment_id: UUID
    start_local: datetime | None = None
    end_local: datetime | None = None
    worker_ids: list[UUID] = Field(default_factory=list,max_length=100)
    locked: bool = False
    unlock: bool = False
    reason: str = Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def coherent(self):
        if (self.start_local is None)!=(self.end_local is None): raise ValueError('Нужны начало и конец местного интервала')
        if self.start_local and (self.start_local.tzinfo is not None or self.end_local.tzinfo is not None):
            raise ValueError('Введите местное время объекта без смещения UTC')
        if self.start_local and self.end_local<=self.start_local: raise ValueError('Конец должен следовать после начала')
        if len(set(self.worker_ids))!=len(self.worker_ids): raise ValueError('Сотрудник не должен повторяться')
        if self.locked and (not self.start_local or not self.worker_ids): raise ValueError('Закрепите размещение с бригадой')
        return self

class DailyPlanLoad(Model):
    date: Date
    planned_person_hours: Decimal
    reserved_person_hours: Decimal
    available_person_hours: Decimal | None
    deficit_person_hours: Decimal | None

class PlanValidation(Model):
    validator_version: str = 'draft-validator-v2'
    status: Literal['valid','incomplete','invalid']
    checked_at: AwareDatetime
    input_sha256: str
    resource_sha256: str
    total_issues: int
    issue_counts: dict[str,int]
    issues: list[PlanIssue]
    total_person_hours: Decimal
    placed_person_hours: Decimal
    unplaced_segments: int
    days: list[DailyPlanLoad]
    ready_for_real_plan: Literal[False] = False

class DraftRecord(Model):
    draft_id: UUID
    revision: int
    parent_revision: int | None
    import_id: UUID | None
    source_kind: Literal['catalog','portfolio'] = 'catalog'
    title: str
    starts_on: date
    ends_on: date
    created_at: datetime
    created_by: UUID
    author_name: str
    reason: str
    input_sha256: str
    occurrence_count: int
    segment_count: int
    total_person_hours: Decimal
    status: Literal['draft'] = 'draft'
    ready_for_real_plan: Literal[False] = False

class DraftList(Model):
    items: list[DraftRecord]
    total: int

class OccurrencePage(Model):
    items: list[WorkOccurrence]
    total: int

class SegmentPage(Model):
    occurrence: WorkOccurrence
    items: list[WorkSegment]
    total: int
    worker_labels: dict[str,str] = Field(default_factory=dict)

class PlanningChoice(Model):
    id: UUID
    label: str

class PlanningChoices(Model):
    items: list[PlanningChoice]
    total: int

class PreparedSourceChoice(Model):
    row_number: int
    code: str
    title: str
    maintenance_type: str

class PreparedSourceChoices(Model):
    items: list[PreparedSourceChoice]
    total: int

class DraftMonth(Model):
    month: str
    due_person_hours: Decimal
    planned_person_hours: Decimal

class DraftOverview(Model):
    record: DraftRecord
    months: list[DraftMonth]
    validation: PlanValidation

class DraftPolicyView(Model):
    record: DraftRecord
    policy: DraftPolicy

DRAFT_CONTRACTS=(GenerationInput,GenerationPreview,SaveDraft,EditSegments,LocalPlacement,DraftList,OccurrencePage,SegmentPage,DraftOverview,PlanValidation,PlanningChoices,PreparedSourceChoices,ChangeDraftPolicy,DraftPolicyView)
