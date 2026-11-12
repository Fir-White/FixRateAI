"""Equipment registry input: resource values always carry explicit units and source."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, Field, field_validator, model_validator
from app.schemas.management import Input, NamedReference, Revision

SystemGroup = Literal['electricity', 'water', 'air']
UsageUnit = Literal['hour', 'cycle', 'km']


class SystemCreate(NamedReference):
    system_group: SystemGroup | None = None


class SystemEdit(Revision):
    system_group: SystemGroup | None


class SiteSelection(Input):
    site_id: UUID


class BuildingCreate(Input):
    name: str = Field(min_length=1, max_length=256)
    address: str | None = Field(default=None, max_length=1000)
    timezone: str = Field(min_length=1, max_length=128)

    @field_validator('timezone')
    @classmethod
    def known_timezone(cls, value):
        try: ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError): raise ValueError('Неизвестный часовой пояс') from None
        return value


class ComponentCreate(Input):
    position_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    part_number: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    installed_on: date
    usage_unit: UsageUnit = 'hour'
    initial_usage: Decimal = Field(ge=0, max_digits=15, decimal_places=3)
    resource_limit: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=3)
    resource_basis: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def resource_source(self):
        if self.resource_limit is not None and not self.resource_basis:
            raise ValueError('Для ресурса детали укажите источник норматива')
        return self


class ComponentReplacement(Revision):
    removed_on: date
    reason: str = Field(min_length=1, max_length=2000)
    replacement: ComponentCreate | None = None


class ComponentMetadata(Revision):
    name: str = Field(min_length=1, max_length=256)
    part_number: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    resource_limit: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=3)
    resource_basis: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def resource_source(self):
        if self.resource_limit is not None and not self.resource_basis:
            raise ValueError('Для ресурса детали укажите источник норматива')
        return self


class UsageReading(Revision):
    measured_at: AwareDatetime
    usage_value: Decimal = Field(ge=0, max_digits=15, decimal_places=3)
    note: str = Field(min_length=1, max_length=2000)


REGISTRY_INPUTS = (SystemCreate, SystemEdit, SiteSelection, BuildingCreate, ComponentCreate, ComponentMetadata, ComponentReplacement, UsageReading)
