"""Bounded OCR and reading validation for technical equipment inspections.

Enforces strict boundary constraints:
- Only explicitly approved equipment classes are eligible for reading extraction:
  1. Analog pressure gauges ('pressure_gauge') -> unit: 'bar'.
  2. Heat meters ('heat_meter', 'vkt7') -> units: 'Gcal', 'm3', 'm3/h', 't/h'.
- All other equipment classes (e.g. control cabinets, mesh filters, manifolds)
  are strictly prohibited from producing measurement readings.
- All extracted readings are candidates for human verification (requires_human_verification=True).
- AI never confirms accuracy, metrological calibration, or hidden operational state.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ReadingValidationStatus(str, Enum):
    CANDIDATE_EXTRACTED = "candidate_extracted"
    UNREADABLE = "unreadable"
    UNSUPPORTED_EQUIPMENT = "unsupported_equipment"
    UNSUPPORTED_UNIT = "unsupported_unit"
    OUT_OF_RANGE = "out_of_range"


# Approved equipment to canonical unit mapping
APPROVED_EQUIPMENT_UNITS: dict[str, dict[str, str]] = {
    "pressure_gauge": {
        "bar": "bar",
        "бар": "bar",
        "mpa": "mpa",
        "мпа": "mpa",
    },
    "heat_meter": {
        "gcal": "Gcal",
        "гкал": "Gcal",
        "m3": "m3",
        "м3": "m3",
        "m3/h": "m3/h",
        "м3/ч": "m3/h",
        "t/h": "t/h",
        "т/ч": "t/h",
    },
    "vkt7": {
        "gcal": "Gcal",
        "гкал": "Gcal",
        "m3": "m3",
        "м3": "m3",
        "m3/h": "m3/h",
        "м3/ч": "m3/h",
        "t/h": "t/h",
        "т/ч": "t/h",
    },
}

# Plausible physical operating ranges for individual heating substations (ITP)
PLAUSIBLE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "pressure_gauge": {
        "bar": (0.0, 16.0),
        "mpa": (0.0, 1.6),
    },
    "heat_meter": {
        "Gcal": (0.0, 100000.0),
        "m3": (0.0, 1000000.0),
        "m3/h": (0.0, 500.0),
        "t/h": (0.0, 500.0),
    },
    "vkt7": {
        "Gcal": (0.0, 100000.0),
        "m3": (0.0, 1000000.0),
        "m3/h": (0.0, 500.0),
        "t/h": (0.0, 500.0),
    },
}

BOUNDED_OCR_DISCLAIMER = (
    "Показания приборов считываются моделью ориентировочно и передаются исключительно как "
    "кандидаты для визуальной сверки главным инженером. Метрологическая точность, скрытая "
    "исправность измерительного тракта и факт поверки по фотографии не подтверждаются."
)


class BoundedReadingCandidate(BaseModel):
    """Candidate reading from bounded OCR pipeline, strictly awaiting human confirmation."""
    model_config = ConfigDict(frozen=True)

    phase: Literal["before", "after", "single"] = Field(
        ..., description="Inspection phase: before or after maintenance"
    )
    label: str = Field(
        ..., description="Observed parameter description (e.g. 'Давление в подающей линии')"
    )
    raw_value: str | None = Field(
        None, description="Raw text token extracted by vision model / OCR"
    )
    parsed_value: float | None = Field(
        None, description="Normalized numeric value"
    )
    unit: str | None = Field(
        None, description="Reported unit of measurement"
    )
    canonical_unit: str | None = Field(
        None, description="Standardized system unit"
    )
    equipment_type: str = Field(
        ..., description="Equipment class (e.g. 'pressure_gauge', 'heat_meter')"
    )
    is_supported: bool = Field(
        ..., description="Whether this equipment + unit combination is within verified OCR scope"
    )
    requires_human_verification: bool = Field(
        default=True, description="Strict safety gate: always True, auto-acceptance forbidden"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    reading_status: ReadingValidationStatus = Field(
        ..., description="Validation outcome status"
    )
    note: str | None = Field(
        None, description="Diagnostic notice or rejection reason"
    )
    disclaimer: str = Field(
        default=BOUNDED_OCR_DISCLAIMER, description="Mandatory legal/safety disclaimer"
    )


class BoundedOCRValidator:
    """Enforces bounded OCR policy across photo assessments."""

    @classmethod
    def is_equipment_supported(cls, equipment_type: str | None) -> bool:
        if not equipment_type:
            return False
        norm = equipment_type.strip().lower()
        return norm in APPROVED_EQUIPMENT_UNITS

    @classmethod
    def canonicalize_unit(cls, equipment_type: str, raw_unit: str | None) -> str | None:
        if not raw_unit:
            return None
        norm_eq = equipment_type.strip().lower()
        norm_unit = raw_unit.strip().lower()
        units_map = APPROVED_EQUIPMENT_UNITS.get(norm_eq, {})
        return units_map.get(norm_unit)

    @classmethod
    def parse_number(cls, raw_value: Any) -> float | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, (int, float)):
            val = float(raw_value)
            return val if (val == val and abs(val) != float("inf")) else None
        s = str(raw_value).strip()
        if not s:
            return None
        # Replace comma with period
        s = s.replace(",", ".")
        # Match numeric pattern
        match = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
        if not match:
            return None
        try:
            d = Decimal(match.group(0))
            if not d.is_finite():
                return None
            return float(d)
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def validate_reading(
        cls,
        reading_dict: dict[str, Any],
        equipment_type: str,
        default_phase: Literal["before", "after", "single"] = "single",
    ) -> BoundedReadingCandidate:
        """Validates a single reading candidate dictionary against equipment-scoped OCR constraints."""
        norm_eq = (equipment_type or "").strip().lower()
        phase = reading_dict.get("phase") or default_phase
        if phase not in ("before", "after", "single"):
            phase = "single"

        label = str(reading_dict.get("label") or reading_dict.get("parameter_code") or "Показание прибора").strip()
        raw_val = reading_dict.get("value")
        raw_val_str = str(raw_val).strip() if raw_val is not None else None
        raw_unit = reading_dict.get("unit")
        raw_unit_str = str(raw_unit).strip() if raw_unit is not None else None
        readable = reading_dict.get("readable", True)

        # 1. Check equipment scope
        if not cls.is_equipment_supported(norm_eq):
            return BoundedReadingCandidate(
                phase=phase,
                label=label,
                raw_value=raw_val_str,
                parsed_value=None,
                unit=raw_unit_str,
                canonical_unit=None,
                equipment_type=equipment_type,
                is_supported=False,
                requires_human_verification=True,
                confidence=0.0,
                reading_status=ReadingValidationStatus.UNSUPPORTED_EQUIPMENT,
                note=(
                    f"Оборудование '{equipment_type}' не входит в утверждённый перечень для OCR. "
                    "Распознавание разрешено только для стрелочных манометров и теплосчетчиков ВКТ-7."
                ),
            )

        # 2. Check readability
        if readable is False or raw_val_str is None or raw_val_str.lower() in ("null", "none", "", "unknown", "?"):
            return BoundedReadingCandidate(
                phase=phase,
                label=label,
                raw_value=raw_val_str,
                parsed_value=None,
                unit=raw_unit_str,
                canonical_unit=cls.canonicalize_unit(norm_eq, raw_unit_str),
                equipment_type=norm_eq,
                is_supported=True,
                requires_human_verification=True,
                confidence=0.0,
                reading_status=ReadingValidationStatus.UNREADABLE,
                note="Показание прибора не читаемо или скрыто на изображении.",
            )

        # 3. Check unit support
        canonical_unit = cls.canonicalize_unit(norm_eq, raw_unit_str)
        if not canonical_unit:
            return BoundedReadingCandidate(
                phase=phase,
                label=label,
                raw_value=raw_val_str,
                parsed_value=None,
                unit=raw_unit_str,
                canonical_unit=None,
                equipment_type=norm_eq,
                is_supported=False,
                requires_human_verification=True,
                confidence=0.0,
                reading_status=ReadingValidationStatus.UNSUPPORTED_UNIT,
                note=(
                    f"Неподдерживаемая единица измерения '{raw_unit_str}' для оборудования '{norm_eq}'. "
                    f"Допустимы: {list(APPROVED_EQUIPMENT_UNITS.get(norm_eq, {}).keys())}"
                ),
            )

        # 4. Parse numeric value
        parsed = cls.parse_number(raw_val_str)
        if parsed is None:
            return BoundedReadingCandidate(
                phase=phase,
                label=label,
                raw_value=raw_val_str,
                parsed_value=None,
                unit=raw_unit_str,
                canonical_unit=canonical_unit,
                equipment_type=norm_eq,
                is_supported=True,
                requires_human_verification=True,
                confidence=0.0,
                reading_status=ReadingValidationStatus.UNREADABLE,
                note=f"Не удалось распознать числовое значение из строки '{raw_val_str}'.",
            )

        # 5. Check plausible operating range
        ranges = PLAUSIBLE_RANGES.get(norm_eq, {}).get(canonical_unit)
        if ranges is not None:
            min_val, max_val = ranges
            if parsed < min_val or parsed > max_val:
                return BoundedReadingCandidate(
                    phase=phase,
                    label=label,
                    raw_value=raw_val_str,
                    parsed_value=parsed,
                    unit=raw_unit_str,
                    canonical_unit=canonical_unit,
                    equipment_type=norm_eq,
                    is_supported=True,
                    requires_human_verification=True,
                    confidence=0.3,
                    reading_status=ReadingValidationStatus.OUT_OF_RANGE,
                    note=(
                        f"Значение {parsed} {canonical_unit} выходит за правдоподобный диапазон "
                        f"[{min_val}, {max_val}] для узла ИТП. Требуется инструментальная проверка."
                    ),
                )

        # 6. Valid candidate extracted
        return BoundedReadingCandidate(
            phase=phase,
            label=label,
            raw_value=raw_val_str,
            parsed_value=parsed,
            unit=raw_unit_str,
            canonical_unit=canonical_unit,
            equipment_type=norm_eq,
            is_supported=True,
            requires_human_verification=True,
            confidence=0.85,
            reading_status=ReadingValidationStatus.CANDIDATE_EXTRACTED,
            note="Кандидат показания успешно выделен; ожидает утверждения инженером.",
        )

    @classmethod
    def filter_and_validate(
        cls,
        raw_readings: list[dict[str, Any]] | None,
        equipment_type: str,
        default_phase: Literal["before", "after", "single"] = "single",
    ) -> list[BoundedReadingCandidate]:
        """Validates a collection of readings and filters out unverified/unsupported anomalies."""
        if not raw_readings:
            return []
        validated: list[BoundedReadingCandidate] = []
        for r in raw_readings:
            if isinstance(r, dict):
                cand = cls.validate_reading(r, equipment_type=equipment_type, default_phase=default_phase)
                validated.append(cand)
        return validated
