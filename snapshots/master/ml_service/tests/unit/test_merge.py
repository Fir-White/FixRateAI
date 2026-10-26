"""Unit-тесты слияния источников данных и сохранения provenance (ML-022)."""
from decimal import Decimal

from app.cv.schemas import BoundingBox, CVInferenceResult, DetectionDTO
from app.llm.mock_provider import MockLLMProvider
from app.llm.schemas import NormalizedDefectDescription
from app.pipeline.merge import merge_defect_sources
from app.schemas.common import SourceType
from app.schemas.request import JobRequestDTO, KnownMeasurementDTO


def _known(parameter_name: str, value: str, unit: str, notes: str | None = None) -> KnownMeasurementDTO:
    return KnownMeasurementDTO(
        parameter_name=parameter_name,
        numeric_value=Decimal(value),
        unit_code=unit,
        source_notes=notes,
    )


def _cv_tile_detection() -> CVInferenceResult:
    return CVInferenceResult(
        image_width=640,
        image_height=480,
        detections=[
            DetectionDTO(
                class_id=1,
                class_name="tile_chip",
                confidence=0.9,
                bbox=BoundingBox(x_min=0.1, y_min=0.1, x_max=0.5, y_max=0.5),
            )
        ],
    )


def test_known_measurements_override_text_and_keep_provenance():
    request = JobRequestDTO(
        description_text="Трещина на фасаде, длина 4.0 метра",
        known_measurements=[_known("length_m", "5.0", "m", notes="акт осмотра")],
    )
    text_norm = MockLLMProvider().complete_structured(
        request.description_text or "", NormalizedDefectDescription
    )

    defects = merge_defect_sources(request, None, text_norm)

    assert len(defects) == 1
    defect = defects[0]
    assert defect.defect_type_code == "facade_crack"
    field = defect.measurements["length_m"]
    assert field.value == Decimal("5.0")
    assert field.source_type == SourceType.USER
    assert field.source_ref == "акт осмотра"


def test_text_measurement_unit_mapping():
    text_norm = NormalizedDefectDescription(
        detected_defect_type="parking_leak",
        extracted_measurements={
            "depth_m": Decimal("0.2"),
            "area_m2": Decimal("10.0"),
        },
    )
    defects = merge_defect_sources(JobRequestDTO(), None, text_norm)

    measurements = defects[0].measurements
    assert measurements["depth_m"].unit == "m"
    assert measurements["area_m2"].unit == "m2"
    assert measurements["area_m2"].source_ref == "user_description_text"


def test_known_area_without_defect_does_not_guess_type():
    request = JobRequestDTO(known_measurements=[_known("area_m2", "10.0", "m2")])

    assert merge_defect_sources(request, None, None) == []


def test_known_leak_area_infers_parking_leak():
    request = JobRequestDTO(known_measurements=[_known("leak_area_m2", "10.0", "m2")])

    defects = merge_defect_sources(request, None, None)

    assert len(defects) == 1
    assert defects[0].defect_type_code == "parking_leak"
    assert defects[0].measurements["leak_area_m2"].value == Decimal("10.0")


def test_known_tile_count_infers_tile_chip():
    request = JobRequestDTO(known_measurements=[_known("count", "3", "pcs")])

    defects = merge_defect_sources(request, None, None)

    assert len(defects) == 1
    assert defects[0].defect_type_code == "tile_chip"
    assert defects[0].measurements["count"].value == Decimal("3")


def test_known_measurement_applies_only_to_compatible_defect():
    request = JobRequestDTO(
        description_text="Трещина на фасаде",
        known_measurements=[_known("count", "2", "pcs")],
    )
    text_norm = NormalizedDefectDescription(detected_defect_type="facade_crack")

    defects = merge_defect_sources(request, _cv_tile_detection(), text_norm)
    by_code = {defect.defect_type_code: defect for defect in defects}

    assert set(by_code) == {"tile_chip", "facade_crack"}
    assert "count" in by_code["tile_chip"].measurements
    assert "count" not in by_code["facade_crack"].measurements
