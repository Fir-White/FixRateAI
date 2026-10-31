"""API request/response schemas for equipment."""
from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EquipmentStatus = Literal["active", "under_repair", "retired"]


class EquipmentCreate(BaseModel):
    """Request body for creating equipment."""

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    system_id: UUID
    equipment_type_id: UUID | None = None
    parent_equipment_id: UUID | None = None
    asset_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    serial_number: str | None = Field(default=None, max_length=128)
    commissioned_on: date | None = None
    location: str | None = Field(default=None, max_length=256)
    properties: dict = Field(default_factory=dict)
    status: EquipmentStatus = "active"


class EquipmentUpdate(BaseModel):
    """Request body for updating equipment."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    serial_number: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=256)
    properties: dict | None = None
    status: EquipmentStatus | None = None
    expected_revision: int | None = Field(default=None, gt=0)


class EquipmentResponse(BaseModel):
    """Equipment data returned by API."""

    model_config = ConfigDict(from_attributes=True)

    equipment_id: UUID
    site_id: UUID
    system_id: UUID
    parent_equipment_id: UUID | None
    equipment_type_id: UUID | None
    asset_code: str
    name: str
    serial_number: str | None
    commissioned_on: date | None
    location: str | None
    properties: dict
    status: EquipmentStatus


class EquipmentListResponse(BaseModel):
    """Paginated list of equipment."""

    items: list[EquipmentResponse]
    total: int
    limit: int
    offset: int
