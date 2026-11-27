from contextlib import closing
from hashlib import sha256
from importlib.util import find_spec
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import text

from app.catalog_excel import write_workbook
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import login, runtime
from tests.backend.test_workbooks import BASE, upload, workbook_site


@pytest.fixture
def office(workbook_site, monkeypatch):
    engine, app, admin, _, ids = workbook_site
    secret = "local-only-workbook-test-secret-" + uuid4().hex
    monkeypatch.setenv("FIXRATE_OFFICE_SECRET", secret)
    monkeypatch.setenv("FIXRATE_OFFICE_BROWSER_ORIGIN", "http://127.0.0.1:8092")
    monkeypatch.setenv("FIXRATE_OFFICE_INTERNAL_ORIGIN", "http://onlyoffice")
    monkeypatch.setenv("FIXRATE_OFFICE_CALLBACK_ORIGIN", "http://app:8000")
    original = write_workbook({"Лист1": [["План", 8]], "Лист2": [["Наряд"]]})
    revised = write_workbook({"Лист1": [["План", 12]], "Лист2": [["Наряд"]]})
    workbook_editor = None
    if find_spec("app.integration.workbook_editor"):
        from app.integration import workbook_editor
        monkeypatch.setattr(workbook_editor, "request_forcesave", lambda *args: True)
        monkeypatch.setattr(workbook_editor, "fetch_snapshot", lambda *args: revised)

    owner = admin.chief
    identity = upload(owner, original).json()["book_id"]
    return workbook_editor, owner, engine, app, ids, secret, identity, original, revised


def start(owner, identity):
    response = owner.post(f"{BASE}/{identity}/editor-sessions", json={"expected_version": 1})
    assert response.status_code == 201, response.text
    return response.json()


def server_post(module, owner, session, secret, payload):
    endpoint = urlsplit(session["document_config"]["editorConfig"]["callbackUrl"]).path
    token = module.sign_office_token(secret, {"operation": "callback", "payload": payload})
    return owner.post(endpoint, json=payload, headers={"Authorization": f"Bearer {token}"})


def request_snapshot(owner, identity, session, request_id=None):
    response = owner.post(f"{BASE}/{identity}/editor-sessions/{session['session_id']}/snapshot",
                          json={"request_id": str(request_id or uuid4())})
    assert response.status_code == 202, response.text
    return response.json()


def ready(module, owner, identity, session, secret):
    requested = request_snapshot(owner, identity, session)
    callback = dict(key=session["document_config"]["document"]["key"], status=6,
                    url="http://onlyoffice/cache/files/workbook.xlsx", userdata=requested["snapshot_request_id"])
    assert server_post(module, owner, session, secret, callback).json() == {"error": 0}
    return callback


def test_workbook_preload_profile_exposes_only_local_browser_origin(monkeypatch):
    from app.security.sessions import Principal

    monkeypatch.setenv("FIXRATE_OFFICE_SECRET", "test-only-workbook-preload-configuration-token")
    monkeypatch.setenv("FIXRATE_OFFICE_BROWSER_ORIGIN", "http://localhost:8092")
    monkeypatch.setenv("FIXRATE_OFFICE_INTERNAL_ORIGIN", "http://onlyoffice")
    monkeypatch.setenv("FIXRATE_OFFICE_CALLBACK_ORIGIN", "http://app:8000")
    chief = Principal(uuid4(),uuid4(),"chief_engineer","Test","test@example.test","Test","UTC")
    assert chief.profile()["workbookEditorOrigin"] == "http://localhost:8092"
    reader = Principal(uuid4(),uuid4(),"engineer","Test","test@example.test","Test","UTC")
    assert "workbookEditorOrigin" not in reader.profile()
    monkeypatch.setenv("FIXRATE_OFFICE_BROWSER_ORIGIN", "https://example.test")
    assert "workbookEditorOrigin" not in chief.profile()


def test_save_requires_snapshot_and_current_role(office):
    module, owner, engine, app, ids, secret, identity, _, _ = office
    with closing(login(app, "chief_engineer")) as other:
        assert other.post(f"{BASE}/{identity}/editor-sessions", json={"expected_version": 1}).status_code == 404
    session = start(owner, identity)
    pending = owner.post(f"{BASE}/{identity}/versions", json={
        "session_id": session["session_id"], "snapshot_sha256": "0"*64,
        "expected_version": 1, "idempotency_key": str(uuid4()),
    })
    assert pending.status_code == 409
    ready(module, owner, identity, session, secret)
    with engine.begin() as conn:
        conn.execute(text("UPDATE site_memberships SET is_active=false WHERE site_id=:site AND user_id=:chief"), ids)
    result = owner.post(f"{BASE}/{identity}/versions", json={
        "session_id": session["session_id"], "snapshot_sha256": sha256(office[-1]).hexdigest(),
        "expected_version": 1, "idempotency_key": str(uuid4()),
    })
    assert result.status_code in (401, 403)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM source_workbook_versions WHERE site_id=:site"), ids) == 1


def test_repeat_commit_creates_one_version(office):
    module, owner, _, _, _, secret, identity, original, revised = office
    session = start(owner, identity)
    callback = ready(module, owner, identity, session, secret)
    assert server_post(module, owner, session, secret, callback).json() == {"error": 0}
    repeated = request_snapshot(owner, identity, session, callback["userdata"])
    assert repeated["state"] == "ready" and repeated["snapshot_request_id"] == callback["userdata"]
    assert owner.post(f"{BASE}/{identity}/editor-sessions/{session['session_id']}/snapshot",
                      json={"request_id": str(uuid4())}).status_code == 409
    status = owner.get(f"{BASE}/{identity}/editor-sessions/{session['session_id']}").json()
    payload = dict(session_id=session["session_id"], expected_version=1, snapshot_sha256=sha256(revised).hexdigest(),
                   idempotency_key=str(uuid4()))
    assert status["state"] == "ready" and status["snapshot_sha256"] == payload["snapshot_sha256"]
    path = f"{BASE}/{identity}/versions"
    saved = owner.post(path, json=payload)
    assert saved.status_code == 201 and saved.json()["version"] == 2, saved.text
    again = owner.post(path, json=payload)
    assert again.status_code == 200 and again.json() == saved.json()
    assert owner.post(path, json=dict(payload, snapshot_sha256="0"*64)).status_code == 409
    assert owner.get(path+"/1/xlsx").content == original
    assert owner.get(path+"/2/xlsx").content == revised
    assert owner.get(path).json()["total"] == 2


def test_editor_retains_late_snapshot_after_transport_timeout(office, monkeypatch):
    module, owner, _, _, _, secret, identity, _, revised = office
    session = start(owner, identity)
    calls = []

    def lost(*args):
        calls.append(args[-1])
        raise httpx.ReadTimeout("Test transport interrupted after command submission")

    monkeypatch.setattr(module, "request_forcesave", lost)
    identity_request = str(uuid4())
    assert request_snapshot(owner, identity, session, identity_request)["state"] == "pending"
    assert request_snapshot(owner, identity, session, identity_request)["state"] == "pending"
    assert calls == [identity_request]
    reopened = start(owner, identity)
    assert reopened["state"] == "pending" and reopened["snapshot_request_id"] == identity_request
    callback = dict(key=session["session_id"], status=6, userdata=identity_request,
                    url="http://onlyoffice/cache/files/workbook.xlsx")
    assert server_post(module, owner, session, secret, callback).json() == {"error": 0}
    reopened = start(owner, identity)
    assert reopened["state"] == "ready" and reopened["snapshot_sha256"] == sha256(revised).hexdigest()


def test_editor_callback_and_download_reject_unrelated_requests(office):
    module, owner, _, app, _, secret, identity, original, _ = office
    session = start(owner, identity)
    from fastapi.testclient import TestClient
    document = session["document_config"]["document"]
    url = document["url"]
    with closing(TestClient(app)) as service:
        assert service.get(urlsplit(url).path).status_code == 403
        token = module.sign_office_token(secret, {"operation": "download", "payload": {"url": url}})
        headers = {"Authorization": "Bearer " + token}
        assert service.get(urlsplit(url).path, headers=headers).content == original
        wrong = url.replace(session["session_id"], str(uuid4()))
        assert service.get(urlsplit(wrong).path, headers=headers).status_code == 403
        callback = urlsplit(session["document_config"]["editorConfig"]["callbackUrl"]).path
        assert service.post(callback, json={"key": document["key"], "status": 6}, headers=headers).status_code == 403


def test_offline_editor_does_not_block_original_download(workbook_site, monkeypatch):
    _, _, admin, _, _ = workbook_site
    monkeypatch.delenv("FIXRATE_OFFICE_SECRET", raising=False)
    owner = admin.chief
    file = write_workbook({"Лист1": [["Данные"]]})
    identity = upload(owner, file).json()["book_id"]
    assert owner.post(f"{BASE}/{identity}/editor-sessions", json={"expected_version": 1}).status_code == 503
    assert owner.get(f"{BASE}/{identity}/versions/1/xlsx").content == file
