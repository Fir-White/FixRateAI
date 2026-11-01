"""Real HTTP + PostgreSQL + filesystem + ML tests against a disposable database."""
from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import closing
from calendar import monthrange
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
ASSIGNMENT_TASK = str(demo_id("assignment-order"))


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


@pytest.fixture
def confirmed_preview_rule(runtime):
    engine, app = runtime
    with engine.connect() as conn:
        original = conn.execute(text("SELECT publication_status,schedule_parameters,period_unit,period_count,occurrences_per_period,scheduling_mode FROM maintenance_rules WHERE maintenance_rule_id=:id"),
                                {"id": demo_id("runtime-rule")}).mappings().one()
        approved = conn.execute(text("SELECT is_approved FROM regulation_editions WHERE regulation_edition_id=:id"),
                                {"id": demo_id("edition")}).scalar_one()
        start = conn.execute(text("SELECT valid_from FROM rule_equipment WHERE binding_id=:id"),
                             {"id": demo_id("runtime-binding")}).scalar_one()
    parameters = dict(original["schedule_parameters"], anchor_date=start.isoformat(), basis="fixed_calendar",
                      norm_unit="person_hour", planning_duration_minutes=60, duration_basis="synthetic_demo:test-duration")
    with engine.begin() as conn:
        conn.execute(text("UPDATE maintenance_rules SET publication_status='published',schedule_parameters=CAST(:params AS jsonb) WHERE maintenance_rule_id=:id"),
                     {"id": demo_id("runtime-rule"), "params": json.dumps(parameters)})
        conn.execute(text("UPDATE regulation_editions SET is_approved=true WHERE regulation_edition_id=:id"), {"id": demo_id("edition")})
    try:
        yield engine, app, start
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE maintenance_rules SET publication_status=:status,schedule_parameters=CAST(:params AS jsonb),period_unit=:unit,period_count=:period,occurrences_per_period=:count,scheduling_mode=:mode WHERE maintenance_rule_id=:id"),
                         {"id": demo_id("runtime-rule"), "status": original["publication_status"], "params": json.dumps(original["schedule_parameters"]),
                          "unit": original["period_unit"], "period": original["period_count"], "count": original["occurrences_per_period"], "mode": original["scheduling_mode"]})
            conn.execute(text("UPDATE regulation_editions SET is_approved=:approved WHERE regulation_edition_id=:id"),
                         {"id": demo_id("edition"), "approved": approved})


@pytest.mark.parametrize("role,expected", [("admin", 403), ("executor", 403), ("dispatcher", 200), ("engineer", 200)])
def test_calendar_preview_role_matrix(runtime, role, expected):
    _, app = runtime
    with closing(login(app, role)) as client:
        reply = client.get(PREFIX+"/ui/calendar/preview?year=2026&month=10")
        assert reply.status_code == expected


def test_calendar_preview_does_not_publish_unconfirmed_customer_rules(runtime):
    _, app = runtime
    assert TestClient(app).get(PREFIX+"/ui/calendar/preview?year=2026&month=10").status_code == 401
    with closing(login(app, "dispatcher")) as client:
        reply = client.get(PREFIX+"/ui/calendar/preview?year=2026&month=10")
        assert reply.status_code == 200, reply.text
        assert reply.headers["cache-control"] == "private, no-store"
        preview = reply.json()
        assert all(item["dataOrigin"] == "synthetic_demo" for item in preview["items"])
        assert preview["diagnostics"]
        assert all(item["status"] in ("needs_input", "skipped") for item in preview["diagnostics"] if item["dataOrigin"] == "customer")
        assert any(item["code"] == "RULE_UNCONFIRMED" for item in preview["diagnostics"])
        assert client.get(PREFIX+"/ui/calendar/preview?year=2101&month=1").status_code == 422
        assert client.get(PREFIX+"/ui/calendar/preview?year=2026&month=13").status_code == 422


def test_calendar_preview_generates_from_postgresql_without_writing_plans(confirmed_preview_rule):
    engine, app, start = confirmed_preview_rule
    tables = ("work_orders", "schedule_entries", "schedule_plans", "work_assignments", "audit_events")
    def counts():
        with engine.connect() as conn:
            return [conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables]
    before = counts()
    with closing(login(app, "dispatcher")) as client:
        endpoint = PREFIX+f"/ui/calendar/preview?year={start.year}&month={start.month}"
        reply = client.get(endpoint)
        assert reply.status_code == 200, reply.text
        preview = reply.json()
        rows = [item for item in preview["items"] if item["operationCode"] == "DEMO-1.4"]
        expected_count = monthrange(start.year, start.month)[1] - start.day + 1
        assert len(rows) == expected_count
        assert rows[0]["occurrenceDate"] == start.isoformat()
        assert all(item["status"] == "draft" and item["taskId"] is None and not item["isOverdue"] for item in rows)
        assert all(item["dataOrigin"] == "synthetic_demo" and item["isAssumption"] for item in rows)
        assert all(item["crewSize"] == 1 and item["requiredPersonHours"] == "1.000" for item in rows)
        diagnostic = next(item for item in preview["diagnostics"] if item["bindingId"] == str(demo_id("runtime-binding")))
        assert diagnostic["status"] == "ok"
        assert diagnostic["totalPersonHours"] == f"{expected_count}.000"
        assert diagnostic["totalPlanningPersonMinutes"] == expected_count * 60
        repeated = client.get(endpoint).json()
        assert [item["id"] for item in repeated["items"]] == [item["id"] for item in preview["items"]]
    assert counts() == before


def test_calendar_preview_reports_malformed_persisted_parameters(confirmed_preview_rule):
    engine, app, start = confirmed_preview_rule
    with engine.begin() as conn:
        conn.execute(text("UPDATE maintenance_rules SET schedule_parameters=schedule_parameters || '{\"basis\":\"invalid\"}' WHERE maintenance_rule_id=:id"),
                     {"id": demo_id("runtime-rule")})
    with closing(login(app, "engineer")) as client:
        reply = client.get(PREFIX+f"/ui/calendar/preview?year={start.year}&month={start.month}")
        assert reply.status_code == 200
        diagnostic = next(item for item in reply.json()["diagnostics"] if item["bindingId"] == str(demo_id("runtime-binding")))
        assert diagnostic["code"] == "INVALID_PERSISTED_INPUT"
        assert diagnostic["status"] == "needs_input"


@pytest.mark.parametrize("period_unit", ["quarter", "year"])
def test_calendar_preview_maps_quarter_and_explicit_year_rules(confirmed_preview_rule, period_unit):
    engine, app, start = confirmed_preview_rule
    with engine.begin() as conn:
        if period_unit == "year":
            annual_dates = sorted([start.isoformat()] + [f"{start.year}-{month:02d}-01" for month in range(1, 13) if month != start.month][:4])
            conn.execute(text("UPDATE maintenance_rules SET period_unit='year',occurrences_per_period=5,scheduling_mode='explicit_months',schedule_parameters=schedule_parameters || CAST(:extra AS jsonb) WHERE maintenance_rule_id=:id"),
                         {"id": demo_id("runtime-rule"), "extra": json.dumps({"explicit_dates": annual_dates})})
        else:
            conn.execute(text("UPDATE maintenance_rules SET period_unit='quarter' WHERE maintenance_rule_id=:id"), {"id": demo_id("runtime-rule")})
    with closing(login(app, "dispatcher")) as client:
        reply = client.get(PREFIX+f"/ui/calendar/preview?year={start.year}&month={start.month}")
        assert reply.status_code == 200, reply.text
        rows = [item for item in reply.json()["items"] if item["operationCode"] == "DEMO-1.4"]
        assert len(rows) == 1
        assert rows[0]["occurrenceDate"] == start.isoformat()


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
        equipment_prior = conn.execute(text("SELECT properties FROM equipment WHERE equipment_id=:id"), {"id": demo_id("equipment-2")}).scalar_one()
        conn.execute(text("UPDATE equipment SET properties=jsonb_set(properties,'{data_origin}','\"customer\"') WHERE equipment_id=:id"), {"id": demo_id("equipment-2")})
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
            conn.execute(text("UPDATE equipment SET properties=CAST(:properties AS jsonb) WHERE equipment_id=:id"), {"id": demo_id("equipment-2"), "properties": json.dumps(equipment_prior)})


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


def assignment_search(client, **overrides):
    context = client.get(PREFIX+f"/ui/tasks/{ASSIGNMENT_TASK}/assignment-context").json()
    assert context["status"] == "ready", context
    body = dict(expected_revision=context["expectedRevision"], start_local=context["defaultStartLocal"],
                end_local=context["defaultEndLocal"], crew_id=None)
    body.update(overrides)
    return context, body


@pytest.mark.parametrize("role,expected", [("admin", 403), ("executor", 403), ("engineer", 403), ("dispatcher", 200)])
def test_assignment_preview_role_matrix(runtime, role, expected):
    _, app = runtime
    with closing(login(app, role)) as client:
        assert client.get(PREFIX+f"/ui/tasks/{ASSIGNMENT_TASK}/assignment-context").status_code == expected
        reply = client.post(PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview", json={
            "expected_revision": 1, "start_local": "2030-01-01T09:00", "end_local": "2030-01-01T17:00"})
        assert reply.status_code == expected


def test_assignment_preview_real_complete_crew_load_and_no_persistence(runtime):
    from app.schemas.maintenance import AssignmentCommand
    engine, app = runtime
    tables = ("work_orders", "schedule_entries", "schedule_plans", "work_assignments", "audit_events")
    def counts():
        with engine.connect() as conn:
            return [conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables]
    with closing(login(app, "dispatcher")) as client:
        before = counts()
        context, body = assignment_search(client)
        assert context["crewSize"] == 2 and context["durationMinutes"] == 60
        assert context["requiredQualifications"] == ["DEMO: допуск к учебному узлу"]
        endpoint = PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview"
        reply = client.post(endpoint, json=body)
        assert reply.status_code == 200, reply.text
        assert reply.headers["cache-control"] == "private, no-store"
        result = reply.json()
        assert result["status"] == "ok" and result["planningPersonMinutes"] == 120
        assert result["crewId"] == str(demo_id("assignment-crew"))
        assert {w["executorId"] for w in result["selectedWorkers"]} == {str(demo_id(f"assignment-worker-{i}")) for i in (1, 2)}
        assert all(w["loadMinutes"] == 0 for w in result["selectedWorkers"])
        busy = next(w for w in result["workers"] if w["executorId"] == str(demo_id("assignment-worker-3")))
        assert busy["loadMinutes"] == 60 and busy["status"] == "available"
        command = AssignmentCommand.model_validate_json(json.dumps(result["command"]))
        assert command.start_at.hour == 9 and command.end_at.hour == 10
        assert set(command.executor_ids) == {demo_id(f"assignment-worker-{i}") for i in (1, 2)}
        assert client.post(endpoint, json=body).json() == result
        body["crew_id"] = str(demo_id("assignment-crew"))
        assert client.post(endpoint, json=body).json()["status"] == "ok"
        assert counts() == before
        with engine.connect() as conn:
            assert conn.execute(text("SELECT status,revision FROM work_orders WHERE work_order_id=:id"), {"id": ASSIGNMENT_TASK}).one() == ("draft", 1)


def test_assignment_preview_auth_csrf_revision_and_site_scope(runtime):
    _, app = runtime
    endpoint = PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview"
    with closing(TestClient(app)) as anonymous:
        assert anonymous.get(PREFIX+f"/ui/tasks/{ASSIGNMENT_TASK}/assignment-context").status_code == 401
        assert anonymous.post(endpoint, json={"expected_revision": 1, "start_local": "2030-01-01T09:00", "end_local": "2030-01-01T17:00"}).status_code == 401
    with closing(login(app, "dispatcher")) as client:
        _, body = assignment_search(client)
        assert client.post(endpoint, json=body, headers={"X-CSRF-Token": "bad"}).status_code == 403
        assert client.post(endpoint, json={**body, "expected_revision": 999}).status_code == 409
        assert client.post(endpoint, json={**body, "crew_id": str(uuid4())}).status_code == 404
        assert client.post(endpoint, json={**body, "site_id": str(uuid4())}).status_code == 422
        assert client.get(PREFIX+f"/ui/tasks/{uuid4()}/assignment-context").status_code == 404
        assert client.post(PREFIX+f"/tasks/{uuid4()}/assignment-preview", json=body).status_code == 404


@pytest.mark.parametrize("change", ["reversed", "too_long", "offset"])
def test_assignment_preview_validates_local_window(runtime, change):
    from datetime import datetime, timedelta
    _, app = runtime
    with closing(login(app, "dispatcher")) as client:
        _, body = assignment_search(client)
        if change == "reversed":
            body["end_local"] = body["start_local"]
        elif change == "too_long":
            body["end_local"] = (datetime.fromisoformat(body["start_local"]) + timedelta(days=33)).isoformat()
        else:
            body["start_local"] += "+05:00"
        reply = client.post(PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview", json=body)
        assert reply.status_code == 422, reply.text


@pytest.mark.parametrize("table,column,value,reason", [
    ("users", "is_active", False, "INACTIVE_USER"),
    ("site_memberships", "is_active", False, "SITE_ACCESS_MISSING"),
    ("user_skills", "verified_at", None, "QUALIFICATION_UNVERIFIED"),
    ("user_skills", "valid_until", "2000-01-01", "QUALIFICATION_OUTSIDE_WINDOW"),
    ("availability_slots", "status", "unavailable", "NO_AVAILABILITY"),
])
def test_assignment_preview_rechecks_persisted_candidate_facts(runtime, table, column, value, reason):
    engine, app = runtime
    user = demo_id("assignment-worker-2")
    with engine.begin() as conn:
        original = conn.execute(text(f"SELECT {column} FROM {table} WHERE user_id=:user"), {"user": user}).scalar_one()
        conn.execute(text(f"UPDATE {table} SET {column}=:value WHERE user_id=:user"), {"user": user, "value": value})
    try:
        with closing(login(app, "dispatcher")) as client:
            _, body = assignment_search(client, crew_id=str(demo_id("assignment-crew")))
            reply = client.post(PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview", json=body)
            assert reply.status_code == 200, reply.text
            result = reply.json()
            assert result["status"] == "unavailable" and result["selectedWorkers"] == [] and result["command"] is None
            excluded = next(w for w in result["workers"] if w["executorId"] == str(user))
            assert reason in excluded["reasons"]
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE {table} SET {column}=:value WHERE user_id=:user"), {"user": user, "value": original})


@pytest.mark.parametrize("finished,reason", [(False, "BOOKING_UNCONFIRMED"), (True, "WORKLOAD_UNCONFIRMED")])
def test_assignment_preview_unknown_booking_is_not_free_time(runtime, finished, reason):
    engine, app = runtime
    with engine.begin() as conn:
        original = conn.execute(text("SELECT operation_snapshot FROM work_orders WHERE work_order_id=:id"), {"id": demo_id("assignment-busy-order")}).scalar_one()
        conn.execute(text("UPDATE work_orders SET operation_snapshot=operation_snapshot - 'planning_duration_minutes' WHERE work_order_id=:id"), {"id": demo_id("assignment-busy-order")})
        original_status = conn.execute(text("SELECT status FROM work_assignments WHERE work_assignment_id=:id"), {"id": demo_id("assignment-busy-worker")}).scalar_one()
        if finished:
            conn.execute(text("UPDATE work_assignments SET status='finished' WHERE work_assignment_id=:id"), {"id": demo_id("assignment-busy-worker")})
    try:
        with closing(login(app, "dispatcher")) as client:
            _, body = assignment_search(client)
            result = client.post(PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview", json=body).json()
            assert result["status"] == "ok"
            worker = next(w for w in result["workers"] if w["executorId"] == str(demo_id("assignment-worker-3")))
            assert worker["status"] == "excluded" and reason in worker["reasons"]
            assert worker["loadMinutes"] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE work_orders SET operation_snapshot=CAST(:snapshot AS jsonb) WHERE work_order_id=:id"), {"id": demo_id("assignment-busy-order"), "snapshot": json.dumps(original)})
            conn.execute(text("UPDATE work_assignments SET status=:status WHERE work_assignment_id=:id"), {"id": demo_id("assignment-busy-worker"), "status": original_status})


@pytest.mark.parametrize("clock,expected_status", [("10:00", "available"), ("11:00", "excluded")])
def test_assignment_preview_in_progress_uses_actual_start_and_does_not_guess_finish(runtime, monkeypatch, clock, expected_status):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import app.integration.assignment as adapter
    engine, app = runtime
    busy = demo_id("assignment-busy-order")
    with engine.begin() as conn:
        original = conn.execute(text("SELECT status,planned_start_at,started_at FROM work_orders WHERE work_order_id=:id"), {"id": busy}).mappings().one()
        day = original["planned_start_at"].astimezone(ZoneInfo("Asia/Yekaterinburg")).date().isoformat()
        conn.execute(text("UPDATE work_orders SET status='in_progress',started_at=:start WHERE work_order_id=:id"),
                     {"id": busy, "start": datetime.fromisoformat(f"{day}T09:30:00+05:00")})
    instant = datetime.fromisoformat(f"{day}T{clock}:00+05:00")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)
    monkeypatch.setattr(adapter, "datetime", Clock)
    try:
        with closing(login(app, "dispatcher")) as client:
            _, body = assignment_search(client)
            reply = client.post(PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview", json=body)
            assert reply.status_code == 200, reply.text
            result = reply.json()
            assert result["status"] == "ok"
            candidate = next(w for w in result["workers"] if w["executorId"] == str(demo_id("assignment-worker-3")))
            assert candidate["status"] == expected_status
            if expected_status == "available":
                assert datetime.fromisoformat(candidate["earliestStart"]).strftime("%H:%M") == "10:30"
                assert candidate["loadMinutes"] == 60
            else:
                assert "BOOKING_UNCONFIRMED" in candidate["reasons"] and candidate["loadMinutes"] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE work_orders SET status=:status,started_at=:start WHERE work_order_id=:id"),
                         {"id": busy, "status": original["status"], "start": original["started_at"]})


@pytest.mark.parametrize("patch,code", [
    ({"planning_duration_minutes": None}, "DURATION_UNCONFIRMED"),
    ({"qualification_ids": [str(UUID(int=999999))]}, "QUALIFICATION_SNAPSHOT_CONFLICT"),
    ({"data_origin": "customer"}, "DATA_ORIGIN_MISMATCH"),
])
def test_assignment_preview_never_invents_missing_task_facts(runtime, patch, code):
    engine, app = runtime
    with engine.begin() as conn:
        original = conn.execute(text("SELECT operation_snapshot FROM work_orders WHERE work_order_id=:id"), {"id": ASSIGNMENT_TASK}).scalar_one()
        conn.execute(text("UPDATE work_orders SET operation_snapshot=operation_snapshot || CAST(:patch AS jsonb) WHERE work_order_id=:id"), {"id": ASSIGNMENT_TASK, "patch": json.dumps(patch)})
    try:
        with closing(login(app, "dispatcher")) as client:
            context = client.get(PREFIX+f"/ui/tasks/{ASSIGNMENT_TASK}/assignment-context").json()
            assert context["status"] == "needs_input" and context["code"] == code
            reply = client.post(PREFIX+f"/tasks/{ASSIGNMENT_TASK}/assignment-preview", json={
                "expected_revision": 1, "start_local": "2030-01-01T09:00", "end_local": "2030-01-01T17:00"})
            assert reply.status_code == 200 and reply.json()["command"] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE work_orders SET operation_snapshot=CAST(:snapshot AS jsonb) WHERE work_order_id=:id"), {"id": ASSIGNMENT_TASK, "snapshot": json.dumps(original)})
