"""Unit-тесты аудитора сметных расчётов."""
from decimal import Decimal
import pytest
from app.calculation.audit import EstimateAuditor
from app.schemas.response import EstimateItemDTO


def test_audit_valid_item():
    item = EstimateItemDTO(
        item_id="item-1",
        rate_code="DEMO-FACADE-CRACK-01",
        work_name="Заделка трещин фасада",
        quantity=Decimal("0.5"),
        unit="m2",
        base_price=Decimal("850.00"),
        line_total=Decimal("425.00"),
        source_ref="DEMO",
    )
    res = EstimateAuditor.audit_item(item)
    assert res.is_valid is True
    assert len(res.errors) == 0
    assert len(res.warnings) == 0


def test_audit_negative_price_error():
    item = EstimateItemDTO(
        item_id="item-2",
        rate_code="DEMO-BAD",
        work_name="Тест",
        quantity=Decimal("1.0"),
        unit="m2",
        base_price=Decimal("-10.00"),
        line_total=Decimal("-10.00"),
        source_ref="DEMO",
    )
    res = EstimateAuditor.audit_item(item)
    assert res.is_valid is False
    assert any("не может быть отрицательной" in err for err in res.errors)


def test_audit_anomaly_volume_warning():
    item = EstimateItemDTO(
        item_id="item-3",
        rate_code="DEMO-BIG",
        work_name="Огромный фасад",
        quantity=Decimal("10000.0"),
        unit="m2",
        base_price=Decimal("100.00"),
        line_total=Decimal("1000000.00"),
        source_ref="DEMO",
    )
    res = EstimateAuditor.audit_item(item)
    assert res.is_valid is True
    assert len(res.warnings) > 0
    assert "аномально большой объём" in res.warnings[0]
