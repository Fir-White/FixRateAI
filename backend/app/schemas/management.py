"""Runtime catalog contracts; equipment fields adapted from new_backend c559d27."""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID
import json

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator, field_validator

from app.schemas.maintenance import CalendarPattern


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator('pattern',mode='before',check_fields=False)
    @classmethod
    def parse_calendar_json(cls,value):
        return CalendarPattern.model_validate_json(json.dumps(value)) if isinstance(value,dict) else value


class AccountEmailUpdate(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    current_password: str = Field(min_length=1, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def trim_email(cls, value):
        return value.strip() if isinstance(value, str) else value


class AccountPasswordUpdate(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def confirm_password(self):
        if self.new_password != self.password_confirmation:
            raise ValueError("Passwords do not match")
        return self


class Revision(Input):
    expected_revision: int = Field(gt=0)


class CancelTask(Revision):
    reason: str = Field(min_length=1,max_length=2000)


class EquipmentCreate(Input):
    system_id: UUID
    equipment_type_id: UUID | None = None
    parent_equipment_id: UUID | None = None
    asset_code: str = Field(min_length=1,max_length=128)
    name: str = Field(min_length=1,max_length=256)
    serial_number: str | None = Field(default=None,max_length=128)
    commissioned_on: date | None = None
    location: str | None = Field(default=None,max_length=256)
    status: Literal["active","under_repair","retired"] = "active"
    data_origin: Literal["customer","synthetic_demo"] = "customer"
    properties: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def coherent_origin(self):
        origin=self.properties.get('data_origin')
        if origin is not None:
            if origin not in ('customer','synthetic_demo'):
                raise ValueError('invalid equipment data origin')
            if 'data_origin' not in self.model_fields_set:
                self.data_origin=origin
            elif origin!=self.data_origin:
                raise ValueError('conflicting equipment data origins')
        return self


class EquipmentEdit(Revision):
    system_id: UUID | None = None
    equipment_type_id: UUID | None = None
    parent_equipment_id: UUID | None = None
    asset_code: str | None = Field(default=None,min_length=1,max_length=128)
    name: str | None = Field(default=None,min_length=1,max_length=256)
    serial_number: str | None = Field(default=None,max_length=128)
    commissioned_on: date | None = None
    location: str | None = Field(default=None,max_length=256)
    status: Literal['active','under_repair','retired'] | None = None
    data_origin: Literal['customer','synthetic_demo'] | None = None
    properties: dict | None = None

    @model_validator(mode='after')
    def nonnullable_fields(self):
        for key in ('system_id','asset_code','name','status','data_origin','properties'):
            if key in self.model_fields_set and getattr(self,key) is None:
                raise ValueError(f'{key} cannot be null')
        origin=(self.properties or {}).get('data_origin')
        if origin is not None and (origin not in ('customer','synthetic_demo') or (self.data_origin is not None and origin!=self.data_origin)):
            raise ValueError('conflicting or invalid equipment data origin')
        return self


class NamedReference(Input):
    code: str = Field(min_length=1,max_length=128)
    name: str = Field(min_length=1,max_length=256)


class Registration(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    full_name: str = Field(min_length=1,max_length=256)
    email: str = Field(min_length=3,max_length=320,pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12,max_length=128)
    company_code: str = Field(min_length=16,max_length=128)

    @field_validator("full_name","email","company_code",mode="before")
    @classmethod
    def trim_identity(cls,value):
        return value.strip() if isinstance(value,str) else value


class EmploymentEdit(Revision):
    role: Literal["director","chief_engineer","admin","dispatcher","engineer","executor"]
    is_active: bool
    employed_from: date | None = None
    employed_until: date | None = None

    @model_validator(mode="after")
    def valid_employment(self):
        if self.employed_from and self.employed_until and self.employed_until < self.employed_from:
            raise ValueError("employment ends before it starts")
        return self


class ApplicationDecision(EmploymentEdit):
    decision: Literal["accepted","rejected"] = "accepted"


class ShiftInput(Input):
    label: str = Field(min_length=1,max_length=256)
    pattern: CalendarPattern
    valid_from: date
    valid_until: date | None = None
    starts_local: time
    ends_local: time
    status: Literal["available","unavailable"] = "available"
    is_active: bool = True

    @model_validator(mode="after")
    def valid_shift(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("shift validity ends before it starts")
        if self.starts_local == self.ends_local or self.starts_local.tzinfo or self.ends_local.tzinfo:
            raise ValueError("shift needs two different local times")
        if any(t.second or t.microsecond for t in (self.starts_local,self.ends_local)):
            raise ValueError("shift precision is whole minutes")
        return self


class ShiftEdit(ShiftInput,Revision):
    pass


class PatternPreview(Input):
    pattern: CalendarPattern
    year: int = Field(ge=2000,le=2100)
    month: int = Field(ge=1,le=12)


class AvailabilityInput(Input):
    start_local: datetime
    end_local: datetime
    status: Literal["available","unavailable"]
    reason: str = Field(min_length=1,max_length=1000)


class SkillInput(NamedReference):
    validity_required: bool = False


class QualificationInput(Input):
    expected_revision: int | None = Field(default=None,gt=0)
    verified_at: AwareDatetime | None = None
    verified_local: datetime | None = None
    valid_until: date | None = None

    @model_validator(mode='after')
    def exactly_one_time(self):
        if (self.verified_at is None)==(self.verified_local is None):
            raise ValueError('specify exactly one verification timestamp')
        return self


class CrewMemberInput(Input):
    user_id: UUID
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("crew membership ends before it starts")
        return self


class CrewInput(Input):
    name: str = Field(min_length=1,max_length=256)
    is_active: bool = True
    members: list[CrewMemberInput] = Field(default_factory=list,max_length=100)

    @model_validator(mode="after")
    def unique_workers(self):
        if len({m.user_id for m in self.members}) != len(self.members):
            raise ValueError("duplicate crew member")
        return self


class CrewEdit(CrewInput,Revision):
    pass


class ChecklistSetting(Input):
    source_item_key: str | None = Field(default=None,max_length=128)
    source_refs: list[str] = Field(default_factory=list,max_length=20)
    text: str = Field(min_length=1,max_length=2000)
    answer_kind: Literal['boolean','number','text'] = 'boolean'
    unit: str | None = Field(default=None,max_length=64)
    required: bool = True
    visual_verifiability: Literal['visible','partial','not_verifiable'] = 'not_verifiable'
    photo_required: bool = False


class MeasurementRequirement(Input):
    parameter_code: str = Field(min_length=1,max_length=128)
    unit: str = Field(min_length=1,max_length=64)
    required: bool = True
    phases: list[Literal['before','after']] = Field(default_factory=lambda:['before','after'],min_length=1,max_length=2)
    minimum: Decimal | None = Field(default=None,allow_inf_nan=False)
    maximum: Decimal | None = Field(default=None,allow_inf_nan=False)


class ServiceConfiguration(Input):
    operation_id: UUID | None = None
    expected_revision: int | None = Field(default=None,gt=0)
    code: str = Field(min_length=1,max_length=128)
    title: str = Field(min_length=1,max_length=256)
    instructions: str = Field(min_length=1,max_length=10000)
    maintenance_type: Literal["ТО1","ТО2"]
    pattern: CalendarPattern
    basis: Literal['fixed_calendar','after_accepted_completion'] = 'fixed_calendar'
    valid_from: date
    valid_until: date | None = None
    crew_size: int = Field(ge=1,le=100)
    norm_value: Decimal | None = Field(default=None,ge=0,max_digits=12,decimal_places=3)
    norm_unit: Literal["person_hour","elapsed_hour","unconfirmed"] = "unconfirmed"
    duration_minutes: int | None = Field(default=None,ge=1,le=46080)
    qualification_ids: list[UUID] = Field(default_factory=list,max_length=100)
    checklist: list[ChecklistSetting] = Field(min_length=1,max_length=100)
    allowed_lead_days: int = Field(ge=0,le=366)
    enabled: bool = False
    methodology_ref: str | None = Field(default=None,max_length=2000)
    measurement_requirements: list[MeasurementRequirement] = Field(default_factory=list,max_length=100)
    required_acts: list[str] = Field(default_factory=list,max_length=20)

    @model_validator(mode="after")
    def coherent_configuration(self):
        defaults={"quarter_policy":"rolling_months","annual_policy":"from_anchor","weekend_policy":"next_workday"}
        self.pattern=self.pattern.model_copy(update={k:v for k,v in defaults.items() if k not in self.pattern.model_fields_set})
        if self.pattern.frequency=="day" and self.pattern.interval==1 and self.allowed_lead_days:
            raise ValueError("daily maintenance cannot be performed in advance")
        if self.code=="1.4" and self.crew_size!=2:
            raise ValueError("operation 1.4 requires two workers")
        codes=[r.parameter_code for r in self.measurement_requirements]
        if len(codes)!=len(set(codes)):raise ValueError("duplicate measurement parameter")
        for req in self.measurement_requirements:
            req=req.model_dump()
            if len(req["phases"])!=len(set(req["phases"])):raise ValueError("duplicate measurement phase")
            if not req.get("parameter_code") or not req.get("unit") or not set(req.get("phases",[])).issubset({"before","after"}) or not req.get("phases"):
                raise ValueError("measurement requires parameter, unit and phases")
            for bound in ("minimum","maximum"):
                if req.get(bound) is not None and not Decimal(str(req[bound])).is_finite():
                    raise ValueError("measurement limit must be finite")
            if req.get("minimum") is not None and req.get("maximum") is not None and Decimal(str(req["minimum"]))>Decimal(str(req["maximum"])):
                raise ValueError("reversed measurement limits")
        if len(self.required_acts)!=len(set(self.required_acts)) or any(not a.strip() or len(a)>256 for a in self.required_acts):
            raise ValueError("acts must have unique nonempty titles up to 256 characters")
        if self.enabled and any(c.answer_kind=="number" and not c.unit for c in self.checklist):
            raise ValueError("numeric checklist items require confirmed units")
        if self.enabled and (self.norm_value is None or self.norm_unit=="unconfirmed" or self.duration_minutes is None or not self.methodology_ref):
            raise ValueError("publication requires confirmed norms, duration and methodology")
        if self.basis=='after_accepted_completion':
            if self.pattern.frequency not in ('day','month','year') or self.pattern.weekdays or self.pattern.month_days or self.pattern.months or self.pattern.week_parity!='any' or self.pattern.excluded_dates or self.pattern.short_month!='last_day':
                raise ValueError('completion-based recurrence needs an unfiltered day/month/year interval')
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("configuration ends before it starts")
        if len(self.qualification_ids) != len(set(self.qualification_ids)):
            raise ValueError("duplicate qualification")
        return self
