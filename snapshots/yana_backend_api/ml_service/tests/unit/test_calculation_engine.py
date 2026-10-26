"""Unit-тесты расчётного движка CalculationEngine."""
from decimal import Decimal
import pytest
from app.calculation.engine import CalculationEngine


def test_calculate_work_quantity_facade_crack():
    measurements = {"length_m": Decimal("4.0")}
    res = CalculationEngine.calculate_work_quantity("facade_crack", measurements)
    assert res.quantity == Decimal("0.4000")
    assert res.unit == "m2"
    assert res.formula_id == "FORMULA_CRACK_AREA_V1"


def test_calculate_work_quantity_facade_crack_missing_raises():
    with pytest.raises(ValueError, match="требуется измерение длины"):
        CalculationEngine.calculate_work_quantity("facade_crack", {})


def test_calculate_work_quantity_tile_chip():
    measurements = {"count": 5}
    res = CalculationEngine.calculate_work_quantity("tile_chip", measurements)
    # 5 * 0.09 = 0.45 m2
    assert res.quantity == Decimal("0.4500")
    assert res.unit == "m2"


def test_calculate_work_quantity_parking_leak():
    measurements = {"area_m2": Decimal("8.0")}
    res = CalculationEngine.calculate_work_quantity("parking_leak", measurements)
    # 8.0 * 1.15 = 9.2000 m2
    assert res.quantity == Decimal("9.2000")
    assert res.unit == "m2"


def test_create_estimate_item():
    item = CalculationEngine.create_estimate_item(
        rate_code="DEMO-FACADE-CRACK-01",
        work_name="Заделка трещин фасада",
        quantity=Decimal("0.4500"),
        unit="m2",
        base_price=Decimal("850.00"),
        source_ref="DEMO-2026.1",
        formula_id="FORMULA_CRACK_AREA_V1",
        quantity_trace="S = 4.5m * 0.1m = 0.45 m2",
    )
    # 0.45 * 850.00 = 382.50
    assert item.line_total == Decimal("382.50")
    assert item.quantity == Decimal("0.4500")
    assert item.unit == "m2"
    assert len(item.calculation_trace) == 2
    assert "382.50 RUB" in item.calculation_trace[1]


def test_calculate_total_cost():
    item1 = CalculationEngine.create_estimate_item(
        rate_code="DEMO-1",
        work_name="Работа 1",
        quantity=Decimal("1.0"),
        unit="m2",
        base_price=Decimal("100.50"),
        source_ref="DEMO",
    )
    item2 = CalculationEngine.create_estimate_item(
        rate_code="DEMO-2",
        work_name="Работа 2",
        quantity=Decimal("2.0"),
        unit="m2",
        base_price=Decimal("200.25"),
        source_ref="DEMO",
    )
    # 100.50 + 400.50 = 501.00
    total = CalculationEngine.calculate_total_cost([item1, item2])
    assert total == Decimal("501.00")
