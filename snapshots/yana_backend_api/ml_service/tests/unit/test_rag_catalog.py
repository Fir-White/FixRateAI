"""Unit-тесты загрузки и запросов к каталогу расценок RatesCatalog."""
from decimal import Decimal
from pathlib import Path
import pytest
from app.rag.catalog import RatesCatalog

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "ml_service" / "data" / "demo_rates.json"
SEED_PATH = REPO_ROOT / "db" / "002_seed_demo.sql"


@pytest.fixture
def catalog():
    return RatesCatalog.from_json_file(CATALOG_PATH)


def _extract_parenthesized(text: str) -> list[str]:
    """Извлекает содержимое групп в скобках верхнего уровня с учётом кавычек."""
    groups: list[str] = []
    depth = 0
    start: int | None = None
    in_quote = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quote:
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                in_quote = False
        elif ch == "'":
            in_quote = True
        elif ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(text[start:i])
                start = None
        i += 1
    return groups


def _split_sql_values(raw: str) -> list[str]:
    """Делит строку значений SQL-кортежа по запятым вне строковых литералов."""
    values: list[str] = []
    buf: list[str] = []
    in_quote = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if in_quote:
            if ch == "'":
                if i + 1 < len(raw) and raw[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_quote = False
            else:
                buf.append(ch)
        elif ch == "'":
            in_quote = True
        elif ch == ",":
            values.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    values.append("".join(buf).strip())
    return values


def _parse_insert_rows(sql: str, table: str) -> list[dict[str, str]]:
    """Парсит простые INSERT ... VALUES из seed-файла в список словарей."""
    marker = f"INSERT INTO {table} ("
    if marker not in sql:
        raise AssertionError(f"В seed-файле нет INSERT INTO {table}")

    block = sql.split(marker, 1)[1]
    columns_part, rest = block.split(")", 1)
    columns = [c.strip() for c in columns_part.split(",")]
    values_block = rest.split("ON CONFLICT", 1)[0]

    rows = []
    for group in _extract_parenthesized(values_block):
        values = _split_sql_values(group)
        assert len(values) == len(columns), f"Несовпадение колонок для {table}"
        rows.append(dict(zip(columns, values)))
    return rows


def _as_bool(value: str) -> bool:
    return value.strip().upper() == "TRUE"


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


def test_catalog_matches_seed_sql(catalog):
    """JSON-каталог должен совпадать с эталонным DEMO-сидом БД (ML-015)."""
    sql = SEED_PATH.read_text(encoding="utf-8")

    source_rows = _parse_insert_rows(sql, "norm_sources")
    assert len(source_rows) == 1
    seed_source = source_rows[0]
    assert seed_source["source_id"] == catalog.source.source_id
    assert seed_source["source_type"] == catalog.source.source_type
    assert seed_source["title"] == catalog.source.title
    assert seed_source["edition"] == catalog.source.edition
    assert seed_source["region"] == catalog.source.region
    assert seed_source["document_reference"] == catalog.source.document_reference
    assert _as_bool(seed_source["is_verified"]) is catalog.source.is_verified

    seed_rates = {row["rate_code"]: row for row in _parse_insert_rows(sql, "rates")}
    json_rates = {rate.rate_code: rate for rate in catalog.list_all()}

    assert set(seed_rates) == set(json_rates)
    for rate_code, seed_rate in seed_rates.items():
        rate = json_rates[rate_code]
        assert seed_rate["rate_id"] == rate.rate_id
        assert seed_rate["source_id"] == catalog.source.source_id
        assert seed_rate["work_name"] == rate.work_name
        assert seed_rate["description"] == rate.description
        assert seed_rate["unit_code"] == rate.unit_code
        assert Decimal(seed_rate["rate_unit_multiplier"]) == rate.rate_unit_multiplier
        assert Decimal(seed_rate["base_price"]) == rate.base_price
        assert seed_rate["currency"] == rate.currency
        assert seed_rate["price_basis"] == rate.price_basis
        assert seed_rate["cost_scope"] == rate.cost_scope
