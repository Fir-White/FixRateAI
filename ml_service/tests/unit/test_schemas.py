"""Unit-тесты схем данных DTO и валидации происхождения."""
from decimal import Decimal
import json
import pytest
from app.schemas.common import (
    ExtractedField,
    PipelineStatus,
    SourceType,
    UnitCode,
    ValidationStatus,
)
from app.schemas.request import (
    BuildingContextDTO,
    FileInputDTO,
    JobRequestDTO,
    KnownMeasurementDTO,
)
from app.schemas.response import (
    ClarificationQuestionDTO,
    DetectedDefectDTO,
    EstimateItemDTO,
    JobResponseDTO,
)


def test_extracted_field_provenance():
    field = ExtractedField[Decimal](
        field_name="length_m",
        value=Decimal("4.5"),
        unit="m",
        source_type=SourceType.USER,
        source_ref="user_input_form",
        confidence=None,
    )
    assert field.field_name == "length_m"
    assert field.value == Decimal("4.5")
    assert field.source_type == SourceType.USER
    assert field.confidence is None
    assert field.validation_status == ValidationStatus.VALID


def test_job_request_serialization():
    req = JobRequestDTO(
        description_text="Трещина на фасаде 4 метра",
        files=[
            FileInputDTO(
                file_id="f1",
                file_path="/storage/photo.jpg",
                file_type="image",
                mime_type="image/jpeg",
            )
        ],
        known_measurements=[
            KnownMeasurementDTO(
                parameter_name="length",
                numeric_value=Decimal("4.0"),
                unit_code="m",
            )
        ],
        building=BuildingContextDTO(
            building_type="жилое",
            wall_material="панель",
        ),
    )
    
    data = req.model_dump()
    assert data["description_text"] == "Трещина на фасаде 4 метра"
    assert len(data["files"]) == 1
    assert data["known_measurements"][0]["numeric_value"] == Decimal("4.0")
    assert data["building"]["wall_material"] == "панель"


def test_job_response_serialization():
    resp = JobResponseDTO(
        job_id="job-100",
        request_id="req-200",
        status=PipelineStatus.COMPLETED,
        pipeline_version="v2.0",
        processing_time_ms=120,
        defects=[
            DetectedDefectDTO(
                defect_id="def-1",
                defect_type_code="facade_crack",
                defect_type_name="Трещина фасада",
                confidence=0.92,
                measurements={
                    "length_m": ExtractedField[Decimal](
                        field_name="length_m",
                        value=Decimal("4.0"),
                        unit="m",
                        source_type=SourceType.USER,
                    )
                },
            )
        ],
        estimate_items=[
            EstimateItemDTO(
                item_id="item-1",
                rate_code="DEMO-FACADE-CRACK-01",
                work_name="Заделка трещин фасада",
                quantity=Decimal("0.4"),
                unit="m2",
                base_price=Decimal("850.00"),
                line_total=Decimal("340.00"),
                source_ref="DEMO-2026.1",
                formula_id="crack_seal_area_v1",
                calculation_trace=["S = 4.0m * 0.1m = 0.4 m2", "Total = 0.4 m2 * 850.00 = 340.00 RUB"],
            )
        ],
        total_cost=Decimal("340.00"),
        currency="RUB",
    )

    json_str = resp.model_dump_json()
    assert "facade_crack" in json_str
    assert "340.00" in json_str

    restored = JobResponseDTO.model_validate_json(json_str)
    assert restored.status == PipelineStatus.COMPLETED
    assert restored.total_cost == Decimal("340.00")
    assert len(restored.estimate_items) == 1
    assert restored.estimate_items[0].line_total == Decimal("340.00")


def test_clarification_response():
    resp = JobResponseDTO(
        job_id="job-101",
        request_id="req-201",
        status=PipelineStatus.NEEDS_CLARIFICATION,
        pipeline_version="v2.0",
        clarification_questions=[
            ClarificationQuestionDTO(
                code="MISSING_CRACK_LENGTH",
                field_name="length_m",
                question_text="Укажите длину трещины в метрах",
                expected_unit="m",
                severity="blocking",
            )
        ],
    )
    assert resp.status == PipelineStatus.NEEDS_CLARIFICATION
    assert len(resp.clarification_questions) == 1
    assert resp.clarification_questions[0].field_name == "length_m"
