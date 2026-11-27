import json
from uuid import uuid4

from sqlalchemy import text

from app.catalog_excel import write_workbook
from app.assistant.tools import available
from tests.backend.test_assistant import assistant_case, confirm, proposal, rpc, thread
from tests.backend.test_assistant_capabilities import upload as attach
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_workbooks import BASE, workbook_site


def test_mvp_exposes_workbook_writes_only_to_chief_engineer(assistant_case, monkeypatch):
    _, app, _, _, _ = assistant_case
    monkeypatch.setenv("FIXRATE_PERMISSION_PROFILE", "mvp")
    writes = {"workbook_upload", "workbook_version_from_file", "workbook_order_apply"}
    assert writes <= set(available(app, "chief_engineer"))
    assert writes.isdisjoint(available(app, "engineer"))
    assert writes.isdisjoint(available(app, "admin"))
    assert "workbook_download" in available(app, "engineer")


def test_workbook_assistant_cannot_bypass_role_or_confirmation(assistant_case, workbook_site):
    engine, _, admin, _, ids = workbook_site
    chief = admin.chief
    chief_chat, other_chat = thread(chief), thread(admin)
    original = write_workbook({"Тест": [["Исходник", 1]]})
    revised = write_workbook({"Тест": [["Правка", 2]]})
    foreign = attach(admin, other_chat, original)
    assert chief.get("/api/v1/assistant/attachments/" + foreign["attachment_id"]).status_code == 404
    forbidden = rpc(admin, "tools/call", dict(name="workbooks_list", arguments={})).json()
    assert "error" in forbidden
    file = attach(chief, chief_chat, original)
    action = proposal(chief, chief_chat, "workbook_upload", dict(body=dict(file=file["attachment_id"])))
    assert chief.get(BASE).json()["total"] == 0
    assert confirm(admin, action).status_code == 404
    confirmed = confirm(chief, action)
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "succeeded", confirmed.text
    book = chief.get(BASE).json()["items"][0]["book_id"]
    version_path = f"{BASE}/{book}/versions"
    file = attach(chief, chief_chat, revised)
    action = proposal(chief, chief_chat, "workbook_version_from_file",
                      dict(path=dict(book_id=book), body=dict(file=file["attachment_id"], expected_version=1,
                                                              idempotency_key=str(uuid4()))))
    assert chief.get(version_path).json()["total"] == 1
    result = confirm(chief, action)
    assert result.status_code == 200 and result.json()["status"] == "succeeded", result.text
    confirm(chief, action)  # Replayed confirmation does not append a version.
    assert chief.get(version_path).json()["total"] == 2
    assert chief.get(version_path + "/1/xlsx").content == original
    assert chief.get(version_path + "/2/xlsx").content == revised
    result = rpc(chief, "tools/call", dict(name="workbook_download", arguments=dict(path=dict(book_id=book, version=2)))).json()["result"]
    resource = json.loads(result["content"][0]["text"])["resource"]
    assert resource["url"] == version_path + "/2/xlsx" and resource["size_bytes"] == len(revised)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM work_orders WHERE site_id=:site"), ids) == 0
