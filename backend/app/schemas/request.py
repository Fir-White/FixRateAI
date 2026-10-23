"""Pydantic-контракты API заявок."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RequestStatus = Literal[
    "created",
    "processing",
    "needs_clarification",
    "ready_for_review",
    "closed",
    "cancelled",
    "failed",
]


class MeasurementInput(BaseModel):
    parameter_code: str = Field(min_length=1, max_length=60)
    value: Decimal = Field(ge=0)
    unit_code: str = Field(min_length=1, max_length=20)
    is_approximate: bool = False

    @field_validator("parameter_code", "unit_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("значение не может быть пустым")
        return value


class PhotoInput(BaseModel):
    storage_key: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1, max_length=100)
    file_size: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[0-9A-Fa-f]{64}$")


class RequestCreate(BaseModel):
    building_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    location_description: str | None = None
    photos: list[PhotoInput] = Field(default_factory=list)
    photo_ids: list[UUID] = Field(default_factory=list)
    measurements: list[MeasurementInput] = Field(default_factory=list)

    @field_validator("title", "description", "location_description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_description_or_photo(self) -> "RequestCreate":
        if not self.description and not self.photos and not self.photo_ids:
            raise ValueError("укажите description или хотя бы одно фото")
        return self


class RequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    location_description: str | None = None
    status: Literal["cancelled"] | None = None
    cancellation_reason: str | None = None
    measurements: list[MeasurementInput] | None = None

    @field_validator("title", "description", "location_description", "cancellation_reason")
    @classmethod
    def strip_update_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_changes(self) -> "RequestUpdate":
        if not self.model_fields_set:
            raise ValueError("тело PATCH не может быть пустым")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title не может быть null")
        if self.status == "cancelled" and not self.cancellation_reason:
            raise ValueError("для отмены укажите cancellation_reason")
        if self.status != "cancelled" and "cancellation_reason" in self.model_fields_set:
            raise ValueError("cancellation_reason допустим только при отмене")
        return self


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    photo_id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    checksum_sha256: str
    storage_key: str
    uploaded_at: datetime


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    measurement_id: UUID
    parameter_code: str
    value: Decimal
    unit_code: str
    source_type: str
    is_approximate: bool
    verification_status: str
    is_current: bool
    created_at: datetime


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    building_id: UUID
    created_by: UUID
    title: str
    description: str | None
    location_description: str | None
    status: RequestStatus
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime
    photos: list[PhotoOut] = Field(default_factory=list)
    measurements: list[MeasurementOut] = Field(default_factory=list)


class RequestListOut(BaseModel):
    items: list[RequestOut]
    total: int
    limit: int
    offset: int
