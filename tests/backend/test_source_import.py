import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.integration.source_import import export_workbook, parse_workbook, preview
from tests.backend.test_assistant import assistant_case, confirm, managed, proposal, rpc, runtime, thread
from tests.backend.test_assistant_capabilities import upload
from tests.backend.test_runtime_integration import PREFIX


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


def test_confirmed_source_import_round_trip_and_scoped_outbox(assistant_case):
    engine, _, admin, _, ids = assistant_case
    chief = admin.chief
    chat = thread(chief)
    blob = SOURCE.read_bytes()
    attachment = upload(chief, chat, blob, "График ТО.xlsx")
    file_arg = {"file": attachment["attachment_id"]}
    result = rpc(chief, "tools/call", {
        "name": "source_xlsx_preview", "arguments": {"conversation_id": chat, "body": file_arg},
    }).json()["result"]
    assert not result["isError"], result
    metadata = json.loads(result["content"][0]["text"])
    digest = metadata["sourceSha256"]
    assert metadata["rowCount"] == 6

    request = {"system_id": str(ids["system"]), "effective_from": "2026-11-19"}
    record = proposal(chief, chat, "source_xlsx_import", {"body": request | file_arg})
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM source_imports WHERE site_id=:site"), ids) == 0
    response = confirm(chief, record)
    assert response.status_code == 200 and response.json()["status"] == "succeeded", response.text

    source_url = PREFIX + "/source/xlsx"
    files = {"file": ("График ТО.xlsx", blob, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    assert admin.post(source_url + "/import", data=request, files=files).status_code == 403
    repeated = chief.post(source_url + "/import", data=request, files=files)
    assert repeated.status_code == 200 and repeated.json()["repeated"], repeated.text

    exported = chief.get(source_url + "/export", params={"source_sha256": digest})
    assert exported.status_code == 200, exported.text
    assert preview(parse_workbook(exported.content))["rows"] == metadata["rows"]
    assert chief.get(source_url + "/export", params={"source_sha256": "0" * 64}).status_code == 404
    events_url = PREFIX + "/source/revisions"
    events = chief.get(events_url).json()
    assert len(events) == 1
    event = events[0]
    assert event["source_sha256"] == digest
    publication = proposal(chief, chat, "source_revision_publish", {"path": {"event_id": event["event_id"]}})
    assert len(chief.get(events_url).json()) == 1
    response = confirm(chief, publication)
    assert response.status_code == 200 and response.json()["status"] == "succeeded", response.text
    assert chief.get(events_url).json() == []
    assert chief.post(f"{events_url}/{event['event_id']}/published").status_code == 404
