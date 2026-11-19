from pathlib import Path

import pytest

from app.integration.source_import import export_workbook, parse_workbook, preview


SOURCE = Path(__file__).parents[2] / "data" / "customer" / "techical_service_schedule.xlsx"


def test_customer_xlsx_preview_preserves_source_rows_and_unknown_columns() -> None:
    workbook = parse_workbook(SOURCE.read_bytes())
    result = preview(workbook)

    assert result["sheet"] == "Лист1"
    assert result["rowCount"] == 6
    assert result["rows"][0]["code"] == "1.1"
    assert result["rows"][-1]["code"] == "1.6"
    assert result["rows"][0]["sourceRef"] == "Лист1!A6:F6"
    assert result["rows"][0]["unknown"]["G"] == "ТО1"


def test_source_export_round_trips_unknown_columns() -> None:
    original = parse_workbook(SOURCE.read_bytes())
    exported = export_workbook(preview(original))

    round_tripped = preview(parse_workbook(exported))

    assert round_tripped["rowCount"] == 6
    assert round_tripped["rows"][0]["code"] == "1.1"
    assert round_tripped["rows"][0]["unknown"]["G"] == "ТО1"


def test_xlsx_parser_rejects_non_xlsx_payload() -> None:
    with pytest.raises(ValueError, match="корректный XLSX"):
        parse_workbook(b"not an xlsx")
