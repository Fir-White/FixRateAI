"""Unit-тесты LLM Gateway и эвристического нормализатора описаний."""
from decimal import Decimal
import pytest
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
