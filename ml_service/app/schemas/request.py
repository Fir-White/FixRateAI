"""Схемы входных данных для ML Service."""
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field
from app.schemas.common import UnitCode


class KnownMeasurementDTO(BaseModel):
    """Измерение, явно предоставленное пользователем или инспектором."""
    parameter_name: str  # "length", "width", "depth", "area", "count"
    numeric_value: Decimal
    unit_code: str
    source_notes: str | None = None


class BuildingContextDTO(BaseModel):
    """Контекст и характеристики здания."""
    building_id: str | None = None
    building_type: str | None = None  # "жилое", "коммерческое"
    wall_material: str | None = None  # "панель", "кирпич", "монолит"
    construction_year: int | None = None
    additional_properties: dict[str, Any] = Field(default_factory=dict)


class FileInputDTO(BaseModel):
    """Файл для обработки (фото дефекта или документ)."""
    file_id: str
    file_path: str | None = None
    file_type: str = "image"  # "image" | "document"
    mime_type: str = "image/jpeg"
    file_bytes_base64: str | None = None


class JobRequestDTO(BaseModel):
    """Входной контракт на запуск обработки AI-пайплайна."""
    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    description_text: str | None = None
    files: list[FileInputDTO] = Field(default_factory=list)
    building: BuildingContextDTO | None = None
    known_measurements: list[KnownMeasurementDTO] = Field(default_factory=list)
    pipeline_version: str = "v2.0"
