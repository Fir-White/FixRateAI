"""Unit-тесты загрузки и запросов к каталогу расценок RatesCatalog."""
from decimal import Decimal
from pathlib import Path
import pytest
from app.rag.catalog import RatesCatalog


@pytest.fixture
def catalog():
    path = Path(__file__).resolve().parent.parent.parent / "data" / "demo_rates.json"
    return RatesCatalog.from_json_file(path)


def test_catalog_loads_successfully(catalog):
    assert catalog.source.source_type == "DEMO"
    assert catalog.source.edition == "2026.1"
    assert len(catalog.rates) == 3


def test_catalog_get_by_code(catalog):
    rate = catalog.get_by_code("DEMO-FACADE-CRACK-01")
    assert rate is not None
    assert rate.work_name == "Заделка трещин фасада"
    assert rate.base_price == Decimal("850.00")
    assert rate.currency == "RUB"
    assert "facade_crack" in rate.applicable_defects


def test_catalog_get_by_defect_type(catalog):
    rates = catalog.get_by_defect_type("tile_chip")
    assert len(rates) == 1
    assert rates[0].rate_code == "DEMO-TILE-CHIP-01"
    assert rates[0].base_price == Decimal("1200.00")


def test_catalog_get_unknown_code(catalog):
    assert catalog.get_by_code("UNKNOWN-CODE-999") is None
    assert catalog.get_by_defect_type("unknown_defect") == []


def test_catalog_file_not_found():
    with pytest.raises(FileNotFoundError):
        RatesCatalog.from_json_file("/non/existent/path/rates.json")
