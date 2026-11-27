"""Unit and safety tests for Bounded OCR and reading extraction (TEAM-ML02 / FRAI-172).

Verifies strict adherence to customer revision CR-17-02 and safety guardrails:
1. Only approved equipment classes ('pressure_gauge', 'heat_meter', 'vkt7') can produce measurement readings.
2. Unapproved classes ('control_cabinet', 'mesh_filter', 'heating_manifold') are strictly rejected.
3. Unsupported units (e.g. 'psi', 'volts', 'kW') are flagged as 'unsupported_unit'.
4. Comma-to-dot parsing and non-numeric value sanitization.
5. Plausible physical range checks (out-of-range values flagged for manual inspection).
6. Mandatory human verification gate: requires_human_verification is ALWAYS True.
7. Disclaimers: AI never confirms metrological accuracy or hidden operational state.
"""
from __future__ import annotations

import pytest

from ml_service.app.cv.ocr import (
    APPROVED_EQUIPMENT_UNITS,
    BOUNDED_OCR_DISCLAIMER,
    BoundedOCRValidator,
    BoundedReadingCandidate,
    ReadingValidationStatus,
)


def test_approved_equipment_unit_registry():
    """Verify registry specifies approved equipment and exact units."""
    assert "pressure_gauge" in APPROVED_EQUIPMENT_UNITS
    assert "heat_meter" in APPROVED_EQUIPMENT_UNITS
    assert "vkt7" in APPROVED_EQUIPMENT_UNITS

    gauge_units = APPROVED_EQUIPMENT_UNITS["pressure_gauge"]
    assert gauge_units["bar"] == "bar"
    assert gauge_units["бар"] == "bar"

    heat_units = APPROVED_EQUIPMENT_UNITS["heat_meter"]
    assert heat_units["gcal"] == "Gcal"
    assert heat_units["m3"] == "m3"
    assert heat_units["m3/h"] == "m3/h"
    assert heat_units["t/h"] == "t/h"


def test_pressure_gauge_valid_reading():
    """Valid pressure reading in bar is successfully extracted with canonical unit."""
    raw = {
        "phase": "after",
        "label": "Давление в подающем трубопроводе",
        "value": "3,4",
        "unit": "бар",
        "readable": True,
    }
    cand = BoundedOCRValidator.validate_reading(raw, equipment_type="pressure_gauge")

    assert cand.reading_status == ReadingValidationStatus.CANDIDATE_EXTRACTED
    assert cand.is_supported is True
    assert cand.parsed_value == 3.4
    assert cand.canonical_unit == "bar"
    assert cand.phase == "after"
    assert cand.requires_human_verification is True
    assert cand.disclaimer == BOUNDED_OCR_DISCLAIMER


def test_pressure_gauge_mpa_canonicalization_to_bar():
    """Pressure readings in MPa are canonicalized to bar (1 MPa = 10 bar)."""
    raw_mpa = {
        "phase": "after",
        "label": "Давление в контуре ГВС",
        "value": "0.35",
        "unit": "МПа",
        "readable": True,
    }
    cand = BoundedOCRValidator.validate_reading(raw_mpa, equipment_type="pressure_gauge")
    assert cand.reading_status == ReadingValidationStatus.CANDIDATE_EXTRACTED
    assert cand.canonical_unit == "bar"
    assert cand.parsed_value == 3.5
    assert cand.requires_human_verification is True


def test_requires_human_verification_cannot_be_disabled():
    """Direct construction with requires_human_verification=False must raise ValueError."""
    with pytest.raises(ValueError, match="requires_human_verification must ALWAYS be True"):
        BoundedReadingCandidate(
            phase="after",
            label="Тест",
            equipment_type="pressure_gauge",
            is_supported=True,
            reading_status=ReadingValidationStatus.CANDIDATE_EXTRACTED,
            requires_human_verification=False,
        )



def test_heat_meter_valid_readings():
    """Valid heat meter readings for Gcal and m3 are extracted properly."""
    raw_gcal = {
        "phase": "single",
        "label": "Тепловая энергия Q",
        "value": "1284.52",
        "unit": "Гкал",
        "readable": True,
    }
    cand_gcal = BoundedOCRValidator.validate_reading(raw_gcal, equipment_type="heat_meter")
    assert cand_gcal.reading_status == ReadingValidationStatus.CANDIDATE_EXTRACTED
    assert cand_gcal.canonical_unit == "Gcal"
    assert cand_gcal.parsed_value == 1284.52
    assert cand_gcal.requires_human_verification is True

    raw_vol = {
        "phase": "after",
        "label": "Объем теплоносителя V1",
        "value": "45210",
        "unit": "м3",
        "readable": True,
    }
    cand_vol = BoundedOCRValidator.validate_reading(raw_vol, equipment_type="vkt7")
    assert cand_vol.reading_status == ReadingValidationStatus.CANDIDATE_EXTRACTED
    assert cand_vol.canonical_unit == "m3"
    assert cand_vol.parsed_value == 45210.0


@pytest.mark.parametrize("unsupported_eq", [
    "control_cabinet",
    "mesh_filter",
    "heating_manifold",
    "pump_station",
    "air_vent",
    "unknown_asset",
])
def test_unsupported_equipment_rejects_ocr(unsupported_eq):
    """Any equipment outside pressure_gauge and heat_meter MUST be rejected from OCR."""
    raw = {
        "phase": "after",
        "label": "Случайный текст или индикатор",
        "value": "12.5",
        "unit": "bar",
        "readable": True,
    }
    cand = BoundedOCRValidator.validate_reading(raw, equipment_type=unsupported_eq)

    assert cand.reading_status == ReadingValidationStatus.UNSUPPORTED_EQUIPMENT
    assert cand.is_supported is False
    assert cand.parsed_value is None
    assert "не входит в утверждённый перечень для OCR" in (cand.note or "")
    assert cand.requires_human_verification is True


@pytest.mark.parametrize("bad_unit,eq_type", [
    ("psi", "pressure_gauge"),
    ("volts", "pressure_gauge"),
    ("kw", "pressure_gauge"),
    ("kw", "heat_meter"),
    ("celsius", "heat_meter"),
    ("rpm", "vkt7"),
])
def test_unsupported_units_are_flagged(bad_unit, eq_type):
    """Unsupported units on approved equipment must be flagged and not accepted."""
    raw = {
        "phase": "before",
        "label": "Показание со странной единицей",
        "value": "50",
        "unit": bad_unit,
        "readable": True,
    }
    cand = BoundedOCRValidator.validate_reading(raw, equipment_type=eq_type)

    assert cand.reading_status == ReadingValidationStatus.UNSUPPORTED_UNIT
    assert cand.is_supported is False
    assert cand.canonical_unit is None
    assert cand.parsed_value is None
    assert "Неподдерживаемая единица измерения" in (cand.note or "")


@pytest.mark.parametrize("out_of_range_val,eq_type,unit", [
    (25.0, "pressure_gauge", "bar"),     # > 16 bar is absurd in standard building ITP
    (-1.5, "pressure_gauge", "bar"),     # Negative gauge pressure is invalid
    (1500000.0, "heat_meter", "Gcal"),   # Absurdly high thermal energy
    (-10.0, "heat_meter", "m3"),         # Negative flow volume
])
def test_out_of_range_readings_flagged_for_manual_inspection(out_of_range_val, eq_type, unit):
    """Values outside plausible physical operating bounds must be flagged out_of_range."""
    raw = {
        "phase": "after",
        "label": "Аномальное показание",
        "value": str(out_of_range_val),
        "unit": unit,
        "readable": True,
    }
    cand = BoundedOCRValidator.validate_reading(raw, equipment_type=eq_type)

    assert cand.reading_status == ReadingValidationStatus.OUT_OF_RANGE
    assert cand.parsed_value == out_of_range_val
    assert cand.confidence <= 0.5
    assert "выходит за правдоподобный диапазон" in (cand.note or "")
    assert cand.requires_human_verification is True


@pytest.mark.parametrize("malformed_str", [
    "норма",
    "в пределах нормы",
    "стрелка на месте",
    "не читается",
    "???",
    "",
    "None",
])
def test_malformed_non_numeric_values_are_unreadable(malformed_str):
    """Non-numeric descriptions must result in unreadable status, never fake numbers."""
    raw = {
        "phase": "after",
        "label": "Давление",
        "value": malformed_str,
        "unit": "bar",
        "readable": True,
    }
    cand = BoundedOCRValidator.validate_reading(raw, equipment_type="pressure_gauge")

    assert cand.reading_status == ReadingValidationStatus.UNREADABLE
    assert cand.parsed_value is None
    assert cand.requires_human_verification is True


def test_batch_filtering_and_validation():
    """Batch validation preserves valid candidates and safely classifies anomalies."""
    readings = [
        {"phase": "before", "label": "Входное давление", "value": "2.2", "unit": "bar", "readable": True},
        {"phase": "after", "label": "Выходное давление", "value": "3.5", "unit": "bar", "readable": True},
        {"phase": "after", "label": "Текст на шильдике", "value": "РосМа", "unit": "bar", "readable": True},
        {"phase": "after", "label": "Ошибочный датчик", "value": "100", "unit": "psi", "readable": True},
    ]

    cands = BoundedOCRValidator.filter_and_validate(readings, equipment_type="pressure_gauge")
    assert len(cands) == 4

    # First two are extracted successfully
    assert cands[0].reading_status == ReadingValidationStatus.CANDIDATE_EXTRACTED
    assert cands[0].parsed_value == 2.2
    assert cands[1].reading_status == ReadingValidationStatus.CANDIDATE_EXTRACTED
    assert cands[1].parsed_value == 3.5

    # Third is unreadable text
    assert cands[2].reading_status == ReadingValidationStatus.UNREADABLE
    assert cands[2].parsed_value is None

    # Fourth is unsupported unit (psi)
    assert cands[3].reading_status == ReadingValidationStatus.UNSUPPORTED_UNIT
    assert cands[3].is_supported is False

    # All must require human verification
    assert all(c.requires_human_verification for c in cands)
