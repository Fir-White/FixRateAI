"""Схемы выходных данных и результатов ML Service."""
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field
from app.schemas.common import ExtractedField, PipelineStatus


class ClarificationQuestionDTO(BaseModel):
    """Вопрос для уточнения недостающих параметров."""
    code: str  # e.g. "MISSING_LENGTH"
    field_name: str  # e.g. "length_m"
    question_text: str
    expected_unit: str | None = None
    allowed_options: list[str] = Field(default_factory=list)
    severity: str = "blocking"  # "blocking" | "advisory"


class EstimateItemDTO(BaseModel):
    """Позиция предварительной сметы / ВОР."""
    item_id: str
    rate_code: str  # e.g. "DEMO-FACADE-CRACK-01"
    work_name: str
    quantity: Decimal
    unit: str
    base_price: Decimal
    line_total: Decimal
    source_ref: str  # e.g. "DEMO-2026.1"
    formula_id: str | None = None
    calculation_trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DetectedDefectDTO(BaseModel):
    """Обнаруженный и подтверждённый дефект объекта."""
    defect_id: str
    defect_type_code: str  # "facade_crack", "tile_chip", "parking_leak"
    defect_type_name: str
    confidence: float | None = None
    location_description: str | None = None
    measurements: dict[str, ExtractedField[Any]] = Field(default_factory=dict)


class JobResponseDTO(BaseModel):
    """Итоговый структурированный ответ ML Service."""
    job_id: str
    request_id: str
    status: PipelineStatus
    pipeline_version: str
    processing_time_ms: int = 0
    defects: list[DetectedDefectDTO] = Field(default_factory=list)
    estimate_items: list[EstimateItemDTO] = Field(default_factory=list)
    total_cost: Decimal | None = None
    currency: str = "RUB"
    clarification_questions: list[ClarificationQuestionDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_trail: list[str] = Field(default_factory=list)
