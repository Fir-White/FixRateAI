"""Real HTTP + PostgreSQL + filesystem + ML tests against a disposable database."""
from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import closing
from uuid import UUID, uuid4

import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db.session import make_engine
from app.integration.demo import demo_id
from app.main import create_app

PREFIX = "/api/v1/maintenance"
TASK = str(demo_id("runtime-order"))


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    url = os.environ.get("INTEGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Run scripts/verify.py to provision an isolated runtime database")
    parsed = make_url(url)
    assert parsed.database.startswith("fixrate_test_")
    engine = make_engine(url)
    # The runner sets a private temporary storage root, separate from real photos.
    assert os.environ.get("PHOTO_STORAGE_ROOT")
    with TestClient(create_app(engine)) as client:
        yield engine, client.app
    engine.dispose()


def login(app, role):
    client = TestClient(app)
    emails = {"executor": "fixrate-demo-1@example.test", "engineer": "fixrate-demo-engineer@example.test",
              "dispatcher": "fixrate-demo-dispatcher@example.test", "admin": "fixrate-demo-admin@example.test"}
    result = client.post("/api/v1/auth/login", json={"email": emails[role], "password": os.environ["FIXRATE_TEST_PASSWORD"]})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
    assert result.json()["profile"]["role"] == role
    return client


def test_sessions_authentication_and_revocation(runtime):
    engine, app = runtime
    from ml_service.app.forecast.client import get_active_forecaster
    assert get_active_forecaster() is None, "API startup must not mutate the standalone ML cache"
    client = TestClient(app)
    assert client.get(PREFIX + "/ui/tasks").status_code == 401
    assert client.get(PREFIX + "/ui/tasks", headers={"X-Role": "admin", "X-User-Id": TASK}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "fixrate-demo-engineer@example.test", "password": "wrong"}).status_code == 401
    client = login(app, "engineer")
    assert client.get("/api/v1/auth/session").status_code == 200
    old_cookie = client.cookies.get("fixrate_session")
    with engine.connect() as conn:
        hashes = conn.execute(text("SELECT token_hash FROM fixrate_sessions")).scalars().all()
        assert hashlib.sha256(old_cookie.encode()).hexdigest() in hashes
        assert old_cookie not in hashes
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401
    client.cookies.set("fixrate_session", old_cookie)
    assert client.get("/api/v1/auth/session").status_code == 401


@pytest.mark.parametrize("role,equipment_code,quality_code", [
    ("admin", 200, 403), ("dispatcher", 200, 403), ("engineer", 200, 200), ("executor", 200, 403)])
def test_real_http_role_matrix(runtime, role, equipment_code, quality_code):
    _, app = runtime
    with closing(login(app, role)) as client:
        assert client.get(PREFIX + "/ui/equipment").status_code == equipment_code
        assert client.get(PREFIX + "/ui/quality").status_code == quality_code
        assert client.get(PREFIX + "/ui/tasks").status_code == 200
        assert client.get(PREFIX + f"/ui/tasks/{TASK}").status_code == 200
        assert client.get(PREFIX + "/ui/calendar?year=2026&month=10").status_code == (403 if role == "admin" else 200)
        assert client.get(PREFIX + "/ui/comparisons").status_code == (403 if role == "executor" else 200)
        if role != "executor":
            assert client.post(PREFIX + f"/tasks/{TASK}/start", json={"expected_revision": 1}).status_code == 403
        if role != "engineer":
            assert client.post(PREFIX + f"/tasks/{TASK}/review", json={"expected_revision": 1,
                "execution_id": str(uuid4()), "verdict": "accepted", "reason": "test"}).status_code == 403


def test_scope_unassigned_and_disabled_membership(runtime):
    engine, app = runtime
    client = login(app, "executor")
    assert client.get(PREFIX + f"/ui/tasks/{uuid4()}").status_code == 404
    assert client.get(PREFIX + f"/ui/equipment/{uuid4()}").status_code == 404
    # Unassigned but real task remains invisible, including photos.
    other_id = uuid4()
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,required_people_snapshot,norm_hours_snapshot)
            VALUES (:id,:site,:system,'manual',1,1)"""), {"id": other_id, "site": demo_id("site"), "system": demo_id("system")})
    assert client.get(PREFIX + f"/ui/tasks/{other_id}").status_code == 404
    assert str(other_id) not in [t["id"] for t in client.get(PREFIX + "/ui/tasks").json()]
    with engine.begin() as conn:
        conn.execute(text("UPDATE site_memberships SET is_active=false WHERE user_id=:id"), {"id": demo_id("user-1")})
    try:
        assert client.get(PREFIX + "/ui/tasks").status_code == 401
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE site_memberships SET is_active=true WHERE user_id=:id"), {"id": demo_id("user-1")})
    client.close()


def test_real_cross_site_resources_are_hidden(runtime):
    engine, app = runtime
    site, system, order, photo, uploader = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sites(site_id,name) VALUES (:id,'Other isolated site')"), {"id": site})
        conn.execute(text("INSERT INTO users(user_id,full_name,email) VALUES (:id,'Other uploader',:email)"),
                     {"id": uploader, "email": f"{uploader}@example.test"})
        conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,'executor')"),
                     {"site": site, "user": uploader})
        conn.execute(text("INSERT INTO engineering_systems(system_id,site_id,code,name) VALUES (:id,:site,'other','Other')"), {"id": system, "site": site})
        conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,required_people_snapshot,norm_hours_snapshot)
            VALUES (:id,:site,:system,'manual',1,1)"""), {"id": order, "site": site, "system": system})
        conn.execute(text("""INSERT INTO evidence_files(evidence_file_id,site_id,work_order_id,uploaded_by,stage,storage_key,mime_type,file_size,sha256)
            VALUES (:id,:site,:task,:user,'other',:key,'image/png',1,:hash)"""),
            {"id": photo, "site": site, "task": order, "user": uploader, "key": str(photo), "hash": "a"*64})
    for role in ("admin", "dispatcher", "engineer", "executor"):
        with closing(login(app, role)) as client:
            assert client.get(PREFIX+f"/ui/tasks/{order}").status_code == 404
            assert client.get(PREFIX+f"/photos/{photo}/content").status_code == 404
            assert str(order) not in [t["id"] for t in client.get(PREFIX+"/ui/tasks").json()]


def test_customer_forecast_returns_real_unavailable_and_calendar_fallback(runtime):
    engine, app = runtime
    # Explicit test fixtures change the domain flags only inside the disposable DB.
    with engine.begin() as conn:
        prior = conn.execute(text("SELECT operation_snapshot FROM work_orders WHERE work_order_id=:id"), {"id": UUID(TASK)}).scalar_one()
        conn.execute(text("UPDATE work_orders SET operation_snapshot=jsonb_set(operation_snapshot,'{data_origin}','\"customer\"') WHERE work_order_id=:id"), {"id": UUID(TASK)})
        conn.execute(text("UPDATE maintenance_rules SET publication_status='published',data_origin='customer',schedule_parameters=schedule_parameters || '{\"basis\":\"fixed_calendar\"}' WHERE maintenance_rule_id=:id"), {"id": demo_id("runtime-rule")})
        conn.execute(text("UPDATE regulation_editions SET is_approved=true WHERE regulation_edition_id=:id"), {"id": demo_id("edition")})
    try:
        with closing(login(app, "engineer")) as client:
            task = client.get(PREFIX+f"/ui/tasks/{TASK}").json()["task"]
            reply = client.post(PREFIX+f"/tasks/{TASK}/forecast", json={"expected_revision": task["revision"]})
            assert reply.status_code == 200, reply.text
            run = reply.json()["run"]
            assert run["dataOrigin"] == "customer"
            assert run["ai"]["status"] == "unavailable"
            assert run["ai"]["recommendedDate"] is None
            assert run["ai"]["errorCode"] in ("MODEL_NOT_READY", "INSUFFICIENT_HISTORY")
            assert run["algorithmic"]["status"] == "ok"
            assert run["decision"]["status"] == "fallback"
            assert run["decision"]["selectedDate"] <= run["mandatoryDueDate"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE work_orders SET operation_snapshot=CAST(:snapshot AS jsonb) WHERE work_order_id=:id"), {"id": UUID(TASK), "snapshot": json.dumps(prior)})
            conn.execute(text("UPDATE maintenance_rules SET publication_status='draft',data_origin='synthetic_demo' WHERE maintenance_rule_id=:id"), {"id": demo_id("runtime-rule")})
            conn.execute(text("UPDATE regulation_editions SET is_approved=false WHERE regulation_edition_id=:id"), {"id": demo_id("edition")})


def test_forecast_http_uses_identical_persisted_snapshot_and_honest_status(runtime):
    engine, app = runtime
    with closing(login(app, "dispatcher")) as client:
        task = client.get(PREFIX + f"/ui/tasks/{TASK}").json()["task"]
        response = client.post(PREFIX + f"/tasks/{TASK}/forecast", json={"expected_revision": task["revision"]})
        assert response.status_code == 200, response.text
        run = response.json()["run"]
        assert run["algorithmic"]["status"] == "needs_input"
        assert run["algorithmic"]["recommendedDate"] is None
        assert run["ai"]["status"] == "ok"
        assert run["ai"]["modelRef"].startswith("synthetic_demo:rf:")
        assert run["decision"]["selectedDate"] is None
        assert run["decision"]["status"] == "needs_input"
        assert client.get(PREFIX + "/ui/comparisons/"+run["runId"]).json()["run"] == run
        assert client.get(PREFIX + "/ui/comparisons").json()[0] == run
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT input_snapshot,output_snapshot FROM forecast_runs WHERE forecast_run_id IN (:a,:b)"),
            {"a": UUID(run["algorithmic"]["resultId"]), "b": UUID(run["ai"]["resultId"])}).all()
        assert len(rows) == 2 and rows[0][0] == rows[1][0]
        assert all(r[1]["canonical"]["snapshot_sha256"] == run["snapshotHash"] for r in rows)
        assert any(r[1].get("condition", {}).get("error_code") in ("INSUFFICIENT_DATA", "MODEL_NOT_READY") for r in rows if r[1].get("condition"))


def image_bytes(seed):
    data = np.random.default_rng(seed).integers(20, 235, (256, 256, 3), dtype=np.uint8)
    stream = io.BytesIO()
    Image.fromarray(data).save(stream, format="PNG")
    return stream.getvalue()


def test_execution_photo_rework_acceptance_preserves_attempts(runtime):
    engine, app = runtime
    executor, engineer = login(app, "executor"), login(app, "engineer")
    task = executor.get(PREFIX+f"/ui/tasks/{TASK}").json()["task"]
    assert executor.get(PREFIX+f"/ui/tasks/{TASK}").json()["allowedActions"] == ["start"]
    assert executor.post(PREFIX+f"/tasks/{TASK}/start", json={"expected_revision": task["revision"]},
                         headers={"X-CSRF-Token": "invalid"}).status_code == 403
    response = executor.post(PREFIX+f"/tasks/{TASK}/start", json={"expected_revision": task["revision"]})
    assert response.status_code == 200, response.text
    bundle = response.json()
    assert set(bundle["allowedActions"]) == {"edit_report", "upload_photo", "submit"}
    first_report = bundle["execution"]["id"]
    assert executor.post(PREFIX+f"/tasks/{TASK}/start", json={"expected_revision": task["revision"]}).status_code == 409
    photo_ids = []
    for attempt in (1, 2):
        revision = bundle["task"]["revision"]
        report = bundle["execution"]
        assert report["attemptNumber"] == attempt
        assert executor.post(PREFIX+f"/tasks/{TASK}/submit", json={"expected_revision": revision}).status_code == 422
        item_id = report["checklist"][0]["id"]
        response = executor.put(PREFIX+f"/tasks/{TASK}/report", json={"expected_revision": revision,
            "narrative": f"Attempt {attempt}", "answers": {item_id: "done"}})
        assert response.status_code == 200, response.text
        bundle = response.json()
        for phase, seed in (("before", 10+attempt), ("after", 20+attempt)):
            blob = image_bytes(seed)
            fields = {"expected_revision": bundle["task"]["revision"], "checklist_item_id": item_id, "phase": phase, "view_key": "front"}
            if phase == "before":
                assert executor.post(PREFIX+f"/tasks/{TASK}/photos", data=fields,
                                     files={"file": ("bad.png", b"not an image", "image/png")}).status_code == 422
            response = executor.post(PREFIX+f"/tasks/{TASK}/photos", data=fields, files={"file": (phase+".png", blob, "image/png")})
            assert response.status_code == 200, response.text
            bundle = response.json()
            photo = bundle["execution"]["photos"][-1]
            # Find by phase because DB retrieval order is intentionally not relied upon.
            photo = next(p for p in bundle["execution"]["photos"] if p["phase"] == phase)
            photo_ids.append(photo["id"])
            stored = executor.get(photo["url"])
            assert stored.status_code == 200 and stored.content == blob
            assert stored.headers["cache-control"] == "private, no-store"
        response = executor.post(PREFIX+f"/tasks/{TASK}/submit", json={"expected_revision": bundle["task"]["revision"]})
        assert response.status_code == 200, response.text
        bundle = response.json()
        assert bundle["task"]["state"] == "submitted"
        assert executor.put(PREFIX+f"/tasks/{TASK}/report", json={"expected_revision": bundle["task"]["revision"], "narrative": "tampered", "answers": {}}).status_code == 409
        if attempt == 1:
            response = engineer.post(PREFIX+f"/tasks/{TASK}/photo-review", json={"expected_revision": bundle["task"]["revision"]})
            assert response.status_code == 200, response.text
            assert response.json()["status"] in ("uncertain", "unavailable")
            if os.environ.get("FIXRATE_REQUIRE_CLIP") == "1":
                assert response.json()["status"] == "uncertain"
                assert response.json()["modelRef"].startswith("openai/clip-vit-base-patch32@")
            assert executor.get(PREFIX+f"/ui/tasks/{TASK}").json()["task"]["state"] == "submitted"
        review = {"expected_revision": bundle["task"]["revision"], "execution_id": bundle["execution"]["id"],
                  "verdict": "rejected" if attempt == 1 else "accepted", "reason": "Verified by engineer"}
        # Current membership is authoritative even for an existing session.
        with engine.begin() as conn:
            conn.execute(text("UPDATE site_memberships SET role='engineer' WHERE user_id=:id"), {"id": demo_id("user-1")})
        try:
            assert "review" not in executor.get(PREFIX+f"/ui/tasks/{TASK}").json()["allowedActions"]
            assert executor.post(PREFIX+f"/tasks/{TASK}/review", json=review).status_code == 403
        finally:
            with engine.begin() as conn:
                conn.execute(text("UPDATE site_memberships SET role='technician' WHERE user_id=:id"), {"id": demo_id("user-1")})
        response = engineer.post(PREFIX+f"/tasks/{TASK}/review", json=review)
        assert response.status_code == 200, response.text
        bundle = response.json()
        if attempt == 1:
            assert bundle["task"]["state"] == "rework_required"
            assert "review" not in bundle["allowedActions"]
            assert executor.get(PREFIX+f"/ui/tasks/{TASK}").json()["allowedActions"] == ["start"]
            response = executor.post(PREFIX+f"/tasks/{TASK}/start", json={"expected_revision": bundle["task"]["revision"]})
            assert response.status_code == 200, response.text
            bundle = response.json()
            assert bundle["execution"]["id"] != first_report
    assert bundle["task"]["state"] == "accepted"
    assert bundle["allowedActions"] == ["forecast"]
    assert executor.get(PREFIX+f"/ui/tasks/{TASK}").json()["allowedActions"] == []
    assert engineer.post(PREFIX+f"/tasks/{TASK}/review", json=review).status_code == 409
    assert all(executor.get(PREFIX+f"/photos/{identity}").status_code == 200 for identity in photo_ids)
    with engine.connect() as conn:
        reports = conn.execute(text("SELECT status,comment FROM work_reports WHERE work_order_id=:id ORDER BY revision_no"), {"id": UUID(TASK)}).all()
        assert reports == [("reviewed", "Attempt 1"), ("reviewed", "Attempt 2")]
        assert conn.scalar(text("SELECT count(*) FROM acceptance_reviews WHERE work_order_id=:id"), {"id": UUID(TASK)}) == 2
        assert conn.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND actor_type='user'"), {"id": UUID(TASK)}) >= 10
    history = engineer.get(PREFIX+f"/ui/equipment/{demo_id('equipment-2')}").json()["history"]
    assert len(history) == 1
    assert engineer.get(PREFIX+f"/ui/equipment/{demo_id('equipment-2')}").json()["equipment"]["nextDueDate"] is None
    executor.close()
    engineer.close()


def isolated_order(engine, state, *, report_author=None):
    """Independent workflow fixture; never alters the shared end-to-end task."""
    order, report = uuid4(), uuid4()
    with engine.begin() as conn:
        snapshot = conn.scalar(text("SELECT operation_snapshot FROM work_orders WHERE work_order_id=:id"), {"id": UUID(TASK)})
        conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
            required_people_snapshot,norm_hours_snapshot,operation_snapshot)
            VALUES (:id,:site,:system,'manual',:state,1,1,CAST(:snapshot AS jsonb))"""),
            dict(id=order, site=demo_id("site"), system=demo_id("system"), state=state, snapshot=json.dumps(snapshot)))
        conn.execute(text("""INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
            VALUES (:site,:system,:task,:equipment)"""), dict(site=demo_id("site"), system=demo_id("system"), task=order, equipment=demo_id("equipment-2")))
        conn.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            VALUES (:site,:task,:user,:dispatcher)"""), dict(site=demo_id("site"), task=order, user=demo_id("user-1"), dispatcher=demo_id("dispatcher")))
        if state in ("in_progress", "in_review", "rework", "completed"):
            conn.execute(text("""INSERT INTO work_reports(work_report_id,site_id,work_order_id,submitted_by,status,
                checklist_snapshot,submitted_at) VALUES (:id,:site,:task,:author,:status,CAST(:checklist AS jsonb),
                CASE WHEN :status='draft' THEN NULL ELSE now() END)"""), dict(id=report, site=demo_id("site"), task=order,
                    author=report_author or demo_id("user-1"), status="draft" if state == "in_progress" else "submitted" if state == "in_review" else "reviewed",
                    checklist=json.dumps(snapshot["checklist"])))
    return order, report


@pytest.mark.parametrize("state", ["draft", "clarification", "assigned", "in_progress", "in_review", "rework", "completed", "cancelled"])
def test_invalid_transitions_leave_state_revision_and_audit_unchanged(runtime, state):
    engine, app = runtime
    order, report = isolated_order(engine, state)
    endpoint = PREFIX + f"/tasks/{order}"
    with closing(login(app, "executor")) as executor, closing(login(app, "engineer")) as engineer:
        replies = []
        if state not in ("assigned", "rework"):
            replies.append(executor.post(endpoint+"/start", json={"expected_revision": 1}))
        if state != "in_progress":
            replies.append(executor.put(endpoint+"/report", json={"expected_revision": 1, "narrative": "Forbidden edit", "answers": {}}))
            replies.append(executor.post(endpoint+"/submit", json={"expected_revision": 1}))
            replies.append(executor.post(endpoint+"/photos", data={"expected_revision": 1,
                "checklist_item_id": str(demo_id("runtime-checklist")), "phase": "before", "view_key": "front"},
                files={"file": ("photo.png", image_bytes(87), "image/png")}))
        if state != "in_review":
            replies.append(engineer.post(endpoint+"/review", json={"expected_revision": 1, "execution_id": str(report), "verdict": "accepted", "reason": "Invalid transition"}))
            replies.append(engineer.post(endpoint+"/photo-review", json={"expected_revision": 1}))
        assert replies and all(r.status_code == 409 for r in replies), [(r.status_code, r.text) for r in replies]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status,revision FROM work_orders WHERE work_order_id=:id"), {"id": order}).one() == (state, 1)
        assert conn.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id"), {"id": order}) == 0


@pytest.mark.parametrize("role", ["admin", "dispatcher", "engineer", "executor"])
def test_every_workflow_mutation_enforces_role_before_state(runtime, role):
    _, app = runtime
    with closing(login(app, role)) as client:
        commands = [
            ("start", {"executor"}, {"expected_revision": 1}),
            ("submit", {"executor"}, {"expected_revision": 1}),
            ("review", {"engineer"}, {"expected_revision": 1, "execution_id": str(uuid4()), "verdict": "accepted", "reason": "Role test"}),
            ("photo-review", {"engineer"}, {"expected_revision": 1}),
            ("forecast", {"dispatcher", "engineer"}, {"expected_revision": 1}),
        ]
        for action, allowed, payload in commands:
            if role not in allowed:
                assert client.post(PREFIX+f"/tasks/{TASK}/{action}", json=payload).status_code == 403
        if role != "executor":
            assert client.put(PREFIX+f"/tasks/{TASK}/report", json={"expected_revision": 1, "narrative": "", "answers": {}}).status_code == 403
            assert client.post(PREFIX+f"/tasks/{TASK}/photos", data={"expected_revision": 1,
                "checklist_item_id": str(demo_id("runtime-checklist")), "phase": "before", "view_key": "front"},
                files={"file": ("photo.png", image_bytes(88), "image/png")}).status_code == 403


def test_other_crew_member_is_read_only_and_revoked_assignment_hides_task(runtime):
    engine, app = runtime
    other = uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users(user_id,full_name,email) VALUES (:id,'Other executor',:email)"), {"id": other, "email": f"{other}@example.test"})
        conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:id,'executor')"), {"site": demo_id("site"), "id": other})
    order, _ = isolated_order(engine, "in_progress", report_author=other)
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            VALUES (:site,:task,:user,:dispatcher)"""), dict(site=demo_id("site"), task=order, user=other, dispatcher=demo_id("dispatcher")))
    with closing(login(app, "executor")) as client:
        endpoint = PREFIX+f"/tasks/{order}"
        assert client.get(PREFIX+f"/ui/tasks/{order}").json()["allowedActions"] == []
        assert client.put(endpoint+"/report", json={"expected_revision": 1, "narrative": "", "answers": {}}).status_code == 409
        assert client.post(endpoint+"/submit", json={"expected_revision": 1}).status_code == 409
        with engine.begin() as conn:
            conn.execute(text("UPDATE work_assignments SET status='cancelled' WHERE work_order_id=:task AND user_id=:user"), {"task": order, "user": demo_id("user-1")})
        assert client.get(PREFIX+f"/ui/tasks/{order}").status_code == 404
        assert str(order) not in [t["id"] for t in client.get(PREFIX+"/ui/tasks").json()]
        assert client.post(endpoint+"/start", json={"expected_revision": 1}).status_code == 404
