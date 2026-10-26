"""Схемы данных нормативно-справочной базы и RAG."""
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field


class NormSourceDTO(BaseModel):
    """Источник нормативов / сборник расценок."""
    source_id: str
    source_type: str = "DEMO"  # "DEMO" | "FER" | "TER" | "COMMERCIAL"
    title: str
    edition: str = "2026.1"
    region: str | None = "Свердловская область"
    document_reference: str | None = None
    is_verified: bool = False


class RateItem(BaseModel):
    """Позиция расценки из нормативного справочника."""
    rate_id: str
    rate_code: str
    work_name: str
    description: str
    unit_code: str = "m2"
    rate_unit_multiplier: Decimal = Decimal("1")
    base_price: Decimal
    currency: str = "RUB"
    price_basis: str = "demo"
    cost_scope: str = "work_only"
    applicable_defects: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class NormativeChunkDTO(BaseModel):
    """Текстовый фрагмент нормативного документа для RAG."""
    chunk_id: str
    source_id: str
    rate_id: str | None = None
    content: str
    source_locator: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
