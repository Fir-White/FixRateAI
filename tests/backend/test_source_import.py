from pathlib import Path

import pytest

from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException

from app.integration.source_import import (
    SourceRow,
    SourceWorkbook,
    export_workbook,
    import_workbook,
    parse_workbook,
    preview,
)


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


def test_export_preserves_original_workbook_bytes() -> None:
    workbook = parse_workbook(SOURCE.read_bytes())

    assert workbook.content == SOURCE.read_bytes()


class _Mappings:
    def mappings(self):
        return self

    def first(self):
        return self._first

    def __init__(self, first):
        self._first = first


class _RepeatSession:
    def execute(self, statement, params=None):
        return _Mappings({
            "source_import_id": uuid4(),
            "source_revision": 1,
            "status": "imported",
            "row_count": 6,
            "system_id": uuid4(),
            "effective_from": date(2026, 11, 18),
        })


def test_repeat_rejects_target_mismatch() -> None:
    workbook = SourceWorkbook(
        "a" * 64,
        "Лист1",
        (SourceRow(6, "1.1", "ТО", "ТО1", "1/день", Decimal("1"), 1, "Лист1!A6:F6", {}),),
        SOURCE.read_bytes(),
    )
    principal = type("Principal", (), {
        "site_id": uuid4(),
        "user_id": uuid4(),
    })()

    with pytest.raises(HTTPException) as exc:
        import_workbook(
            _RepeatSession(),
            principal,
            workbook,
            uuid4(),
            date(2026, 11, 19),
            "source.xlsx",
        )

    assert exc.value.status_code == 409
