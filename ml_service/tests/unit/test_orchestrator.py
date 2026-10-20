"""Unit-тесты оркестратора сквозного пайплайна PipelineOrchestrator."""
from decimal import Decimal
import pytest

from app.cv.mock_detector import MockYoloDetector
from app.cv.service import CVService
from app.llm.gateway import LLMGateway
from app.llm.mock_provider import MockLLMProvider
from app.pipeline.orchestrator import PipelineOrchestrator
from app.schemas.common import PipelineStatus
from app.schemas.request import FileInputDTO, JobRequestDTO, KnownMeasurementDTO


@pytest.fixture
def orchestrator():
    cv = CVService(detector=MockYoloDetector())
    llm = LLMGateway(provider=MockLLMProvider())
    return PipelineOrchestrator(cv_service=cv, llm_gateway=llm)


def test_orchestrator_needs_clarification_when_no_measurements(orchestrator):
    # Запрос с фото, но без указания длины трещины
    req = JobRequestDTO(
        description_text="Трещина на фасаде здания",
        files=[
            FileInputDTO(file_id="f1", file_type="image", mime_type="image/jpeg")
        ],
    )
    res = orchestrator.process_job(req)

    assert res.status == PipelineStatus.NEEDS_CLARIFICATION
    assert len(res.clarification_questions) == 1
    assert res.clarification_questions[0].field_name == "length_m"
    assert res.total_cost is None
    assert len(res.estimate_items) == 0


def test_orchestrator_success_with_text_measurements(orchestrator):
    # Запрос с длиной трещины, указанной в тексте
    req = JobRequestDTO(
        description_text="Вертикальная трещина на кирпичном фасаде, длина 4.0 метра",
        files=[
            FileInputDTO(file_id="f1", file_type="image", mime_type="image/jpeg")
        ],
    )
    res = orchestrator.process_job(req)

    assert res.status == PipelineStatus.COMPLETED
    assert len(res.estimate_items) == 1
    item = res.estimate_items[0]
    assert item.rate_code == "DEMO-FACADE-CRACK-01"
    # S = 4.0 * 0.1 = 0.4 m2; 0.4 * 850.00 = 340.00 RUB
    assert item.quantity == Decimal("0.4000")
    assert item.line_total == Decimal("340.00")
    assert res.total_cost == Decimal("340.00")
    assert res.currency == "RUB"
    assert len(res.clarification_questions) == 0


def test_orchestrator_success_with_known_measurements(orchestrator):
    # Запрос с явно переданными измерениями
    req = JobRequestDTO(
        description_text="Трещина на фасаде",
        files=[
            FileInputDTO(file_id="f1", file_type="image", mime_type="image/jpeg")
        ],
        known_measurements=[
            KnownMeasurementDTO(
                parameter_name="length_m",
                numeric_value=Decimal("5.0"),
                unit_code="m",
            )
        ],
    )
    res = orchestrator.process_job(req)

    assert res.status == PipelineStatus.COMPLETED
    assert len(res.estimate_items) == 1
    # 5.0 * 0.1 = 0.5 m2; 0.5 * 850.00 = 425.00 RUB
    assert res.estimate_items[0].line_total == Decimal("425.00")
    assert res.total_cost == Decimal("425.00")


def test_orchestrator_tile_chip_scenario(orchestrator):
    # Сценарий скола плитки
    mock_cv = MockYoloDetector()
    mock_cv.set_scenario("tile_chip")
    orch = PipelineOrchestrator(cv_service=CVService(detector=mock_cv))

    req = JobRequestDTO(
        description_text="На крыльце откололось 3 плитки",
        files=[FileInputDTO(file_id="f2", file_type="image", mime_type="image/jpeg")],
    )
    res = orch.process_job(req)

    assert res.status == PipelineStatus.COMPLETED
    assert len(res.estimate_items) == 1
    item = res.estimate_items[0]
    assert item.rate_code == "DEMO-TILE-CHIP-01"
    # 3 шт * 0.09 м2 = 0.27 м2; 0.27 * 1200.00 = 324.00 RUB
    assert item.quantity == Decimal("0.2700")
    assert item.line_total == Decimal("324.00")
    assert res.total_cost == Decimal("324.00")
