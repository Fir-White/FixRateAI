"""Unit-тесты LLM Gateway и эвристического нормализатора описаний."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.llm.gateway import LLMGateway
from app.llm.mock_provider import MockLLMProvider
from app.llm.schemas import NormalizedDefectDescription


def test_mock_provider_facade_crack():
    provider = MockLLMProvider()
    res = provider.complete_structured(
        "На кирпичном фасаде обнаружена вертикальная трещина, длина 4.5 метра",
        NormalizedDefectDescription,
    )
    assert res.detected_defect_type == "facade_crack"
    assert "кирпич" in res.materials
    assert res.extracted_measurements.get("length_m") == Decimal("4.5")
    assert res.location_details == "наружная стена фасада"


def test_mock_provider_tile_chip():
    provider = MockLLMProvider()
    res = provider.complete_structured(
        "На крыльце откололось 3 плитки из керамогранита",
        NormalizedDefectDescription,
    )
    assert res.detected_defect_type == "tile_chip"
    assert "плитка" in res.materials or "керамогранит" in res.materials
    assert res.extracted_measurements.get("count") == Decimal("3")
    assert res.location_details == "крыльцо входной группы"


def test_mock_provider_parking_leak():
    provider = MockLLMProvider()
    res = provider.complete_structured(
        "В подземном паркинге протечка, мокрое пятно на потолке площадью 6.2 м2",
        NormalizedDefectDescription,
    )
    assert res.detected_defect_type == "parking_leak"
    assert res.extracted_measurements.get("area_m2") == Decimal("6.2")
    # «м2» не должно интерпретироваться как длина в метрах
    assert "length_m" not in res.extracted_measurements
    assert res.location_details == "подземный паркинг"


def test_llm_gateway_empty_text():
    gateway = LLMGateway()
    res = gateway.normalize_user_text("")
    assert res.defect_description == ""
    assert res.detected_defect_type is None


def test_llm_gateway_anti_hallucination_guarantee():
    # Гарантируем, что выходная схема не содержит финансовой информации
    gateway = LLMGateway()
    res = gateway.normalize_user_text("Трещина фасада 5 метров, ремонт стоит 10000 рублей")
    data = res.model_dump()
    assert "price" not in data
    assert "cost" not in data
    assert "total" not in data


def test_llm_schema_rejects_financial_measurement_keys():
    with pytest.raises(ValidationError, match="Недопустимые параметры измерений"):
        NormalizedDefectDescription(
            extracted_measurements={"price": Decimal("10000"), "cost_rub": Decimal("500")}
        )


def test_llm_schema_rejects_non_physical_measurement_keys():
    with pytest.raises(ValidationError, match="Недопустимые параметры измерений"):
        NormalizedDefectDescription(extracted_measurements={"coefficient": Decimal("1.5")})


def test_llm_schema_rejects_non_positive_measurements():
    with pytest.raises(ValidationError, match="должно быть положительным"):
        NormalizedDefectDescription(extracted_measurements={"length_m": Decimal("0")})


class _SmugglingProvider:
    """Провайдер, пытающийся протащить финансовое поле в обход схемы."""

    def complete_structured(self, prompt: str, schema_cls: type) -> NormalizedDefectDescription:
        return NormalizedDefectDescription.model_construct(
            detected_defect_type="facade_crack",
            extracted_measurements={"price": Decimal("10000")},
        )


def test_gateway_revalidates_provider_output_and_falls_back():
    gateway = LLMGateway(provider=_SmugglingProvider())
    res = gateway.normalize_user_text("Трещина на фасаде длиной 3 метра")

    assert res.detected_defect_type == "facade_crack"
    assert res.extracted_measurements.get("length_m") == Decimal("3")
    assert "price" not in res.extracted_measurements
