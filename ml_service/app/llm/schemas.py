"""Схемы структурированного вывода языковой модели (LLM).

Ключевой принцип FixRate AI: схема нормализации текста содержит только факты
о дефекте и физические параметры. Поля цен, расценок и итоговых сумм категорически
отсутствуют, исключая риск галлюцинаций финансовой информации.
"""
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

# Единственные параметры, которые LLM разрешено извлекать. Любые финансовые
# или вымышленные ключи отклоняются на уровне валидации схемы.
ALLOWED_MEASUREMENT_KEYS = frozenset(
    {
        "length_m",
        "width_m",
        "depth_m",
        "height_m",
        "thickness_m",
        "perimeter_m",
        "area_m2",
        "tile_area_m2",
        "leak_area_m2",
        "volume_m3",
        "count",
        "damaged_tiles_count",
    }
)


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

    @field_validator("extracted_measurements")
    @classmethod
    def validate_measurements(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        """Пропускает только положительные физические величины из allowlist."""
        invalid_keys = sorted(set(value) - ALLOWED_MEASUREMENT_KEYS)
        if invalid_keys:
            raise ValueError(
                "Недопустимые параметры измерений: "
                f"{invalid_keys}. Разрешены только физические величины "
                f"{sorted(ALLOWED_MEASUREMENT_KEYS)}"
            )

        for key, measurement in value.items():
            if not measurement.is_finite() or measurement <= Decimal("0"):
                raise ValueError(
                    f"Измерение '{key}' должно быть положительным конечным числом"
                )
        return value
