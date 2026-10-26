"""Контракты запуска и просмотра предварительной сметы."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EstimateRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    request_id: UUID
    status: str
    pipeline_version: str
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class EstimateItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    work_name: str
    quantity: Decimal | None
    unit_code: str | None
    unit_price: Decimal | None
    coefficient: Decimal
    base_cost: Decimal | None
    additional_materials_cost: Decimal | None
    total_cost: Decimal | None
    calculation_details: dict[str, Any]
    validation_status: str
    source_snapshot: dict[str, Any] | None


class EstimateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estimate_id: UUID
    request_id: UUID
    version: int
    based_on_run_id: UUID | None
    status: Literal["draft", "needs_review", "approved", "rejected", "superseded"]
    input_snapshot: dict[str, Any]
    total_cost: Decimal | None
    currency: str
    created_at: datetime
    items: list[EstimateItemOut] = Field(default_factory=list)


class EstimateRunResult(BaseModel):
    run: EstimateRunOut
    estimate: EstimateOut | None = None
    clarification_questions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_trail: list[str] = Field(default_factory=list)
