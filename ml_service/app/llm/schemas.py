"""Схемы структурированного вывода языковой модели (LLM).

Ключевой принцип FixRate AI: схема нормализации текста содержит только факты
о дефекте и физические параметры. Поля цен, расценок и итоговых сумм категорически
отсутствуют, исключая риск галлюцинаций финансовой информации.
"""
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field


class NormalizedDefectDescription(BaseModel):
    """Структурированная интерпретация пользовательского текста."""
    detected_defect_type: str | None = Field(
        default=None,
        description="Код типа дефекта (facade_crack, tile_chip, parking_leak) или None",
    )
    defect_description: str = Field(
        default="",
        description="Краткое стандартизированное описание повреждения",
    )
    location_details: str | None = Field(
        default=None,
        description="Локализация (например, 'цоколь здания', 'крыльцо входной группы')",
    )
    materials: list[str] = Field(
        default_factory=list,
        description="Материалы конструкции (кирпич, бетон, плитка)",
    )
    extracted_measurements: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Явно упомянутые физические измерения (length_m, width_m, area_m2, count)",
    )
    unclear_aspects: list[str] = Field(
        default_factory=list,
        description="Неясности или противоречия в описании",
    )
