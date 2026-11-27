import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.integration.source_import import (
    SourceRow,
    SourceWorkbook,
    export_workbook,
    import_workbook,
    parse_workbook,
    preview,
)
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
    assert chief.post(source_url + "/import", data=request | {"effective_from": "2026-11-20"}, files=files).status_code == 409

    exported = chief.get(source_url + "/export", params={"source_sha256": digest})
    assert exported.status_code == 200, exported.text
    assert exported.content == blob and "filename*=UTF-8''" in exported.headers["content-disposition"]
    assert preview(parse_workbook(exported.content))["rows"] == metadata["rows"]
    assert chief.get(source_url + "/export", params={"source_sha256": "0" * 64}).status_code == 404
    search_url = PREFIX + "/source/search"
    word = metadata["rows"][0]["title"].split()[0]
    assert chief.get(search_url, params={"q": " "}).status_code == 422
    found = chief.get(search_url, params={"q": word}).json()
    assert found and {row["source_sha256"] for row in found} == {digest}
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

    with engine.begin() as db:
        db.execute(text("DELETE FROM source_catalog_index WHERE site_id=:site"), ids)
        db.execute(text("""
            UPDATE source_imports SET system_id=NULL,effective_from=NULL,source_workbook=NULL WHERE site_id=:site
        """), ids)
        migration = SOURCE.parents[2] / "database/migrations/029_source_catalog_legacy_index.sql"
        db.exec_driver_sql(migration.read_text(encoding="utf-8").removeprefix("BEGIN;").removesuffix("\nCOMMIT;\n"))
        restored = db.execute(text("SELECT system_id,effective_from,source_workbook FROM source_imports WHERE site_id=:site"), ids).one()
        assert restored == (ids["system"], date(2026, 11, 19), None)
    assert chief.get(search_url, params={"q": word}).json() == found
    assert chief.post(source_url + "/import", data=request, files=files).json()["repeated"]
    assert chief.get(source_url + "/export", params={"source_sha256": digest}).content == blob


def test_revision_worker_keeps_external_and_other_events_separate(assistant_case):
    from app.integration.source_import import next_revision
    from app.integration.source_revision_worker import process_pending_revisions

    engine, app, admin, _, ids = assistant_case
    manual, missing = uuid4(), uuid4()
    with engine.begin() as db:
        db.execute(text("""
            INSERT INTO source_revision_events (event_id,site_id,scope,source_revision,entity_type,change_type,payload)
            VALUES (:manual,:site,'maintenance_catalog',7,'equipment','updated','{}'),
                   (:missing,:site,'maintenance_catalog',8,'source_import','source_revision','{}')
        """), dict(ids, manual=manual, missing=missing))
    with app.state.factory() as session:
        assert next_revision(session, site_id=ids["site"]) == 9
    endpoint = PREFIX + "/source/revisions"
    assert admin.chief.post(f"{endpoint}/{manual}/published").json()["status"] == "published"
    assert {event["event_id"] for event in admin.chief.get(endpoint).json()} == {str(missing)}
    assert process_pending_revisions(app) == 0
    failed = admin.chief.get(endpoint, params={"status":"failed"}).json()
    assert [(event["event_id"], event["published_at"]) for event in failed] == [(str(missing), None)]


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
