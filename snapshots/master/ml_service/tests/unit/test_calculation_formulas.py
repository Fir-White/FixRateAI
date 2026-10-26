"""Unit-тесты библиотеки строительных формул."""
from decimal import Decimal
import pytest
from app.calculation.formulas import (
    calculate_crack_repair_area,
    calculate_crack_linear,
    calculate_tile_replacement_area,
    calculate_parking_waterproofing_area,
)


def test_crack_repair_area_default_width():
    # Длина 4.5 м, стандартная полоса 0.1 м -> 0.45 м2
    res = calculate_crack_repair_area(Decimal("4.5"))
    assert res.quantity == Decimal("0.4500")
    assert res.unit == "m2"
    assert res.formula_id == "FORMULA_CRACK_AREA_V1"
    assert "4.5" in res.trace


def test_crack_repair_area_custom_width():
    # Длина 5.0 м, ширина разделки 0.15 м -> 0.75 м2
    res = calculate_crack_repair_area(Decimal("5.0"), Decimal("0.15"))
    assert res.quantity == Decimal("0.7500")
    assert res.unit == "m2"


def test_crack_repair_area_negative_raises():
    with pytest.raises(ValueError, match="строго положительной"):
        calculate_crack_repair_area(Decimal("-1.0"))


def test_crack_linear():
    res = calculate_crack_linear(Decimal("3.25"))
    assert res.quantity == Decimal("3.2500")
    assert res.unit == "m"
    assert res.formula_id == "FORMULA_CRACK_LINEAR_V1"


def test_tile_replacement_by_count():
    # 4 плитки стандартного размера 0.09 м2 -> 0.36 м2
    res = calculate_tile_replacement_area(damaged_tiles_count=4)
    assert res.quantity == Decimal("0.3600")
    assert res.unit == "m2"
    assert "4 шт" in res.trace


def test_tile_replacement_direct_area():
    res = calculate_tile_replacement_area(direct_area_m2=Decimal("1.2"))
    assert res.quantity == Decimal("1.2000")
    assert res.unit == "m2"


def test_tile_replacement_missing_inputs_raises():
    with pytest.raises(ValueError):
        calculate_tile_replacement_area()


def test_parking_waterproofing_with_leak_area():
    # Пятно 10 м2 * 1.15 = 11.5 м2
    res = calculate_parking_waterproofing_area(leak_area_m2=Decimal("10.0"))
    assert res.quantity == Decimal("11.5000")
    assert res.unit == "m2"


def test_parking_waterproofing_with_dimensions():
    # 2.0 м * 3.0 м = 6.0 м2 * 1.15 = 6.9 м2
    res = calculate_parking_waterproofing_area(length_m=Decimal("2.0"), width_m=Decimal("3.0"))
    assert res.quantity == Decimal("6.9000")
    assert res.unit == "m2"
