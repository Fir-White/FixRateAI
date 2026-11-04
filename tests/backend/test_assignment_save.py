"""BE05 real PostgreSQL transactions, rollback and concurrent HTTP requests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta
import json
from threading import Barrier
import time
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.repository import MaintenanceRepository
from app.integration.demo import demo_id
from app.schemas.maintenance import Assignment
from tests.backend.test_runtime_integration import runtime, login, PREFIX


@pytest.fixture
def jobs(runtime):
    engine, app = runtime
    identities = []
    def create():
        identity = uuid4()
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,maintenance_rule_id,origin,status,
                required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot,regulatory_deadline_at,operation_snapshot)
                SELECT :id,w.site_id,w.system_id,w.maintenance_rule_id,'manual','draft',w.required_people_snapshot,
                w.norm_hours_snapshot,w.norm_hours_basis_snapshot,w.regulatory_deadline_at,
                w.operation_snapshot || jsonb_build_object('earliest_date',e.earliest_date::text)
                FROM work_orders w JOIN schedule_entries e ON e.schedule_entry_id=w.schedule_entry_id
                WHERE w.work_order_id=:source"""), {"id": identity, "source": demo_id("assignment-order")})
            conn.execute(text("""INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
                SELECT site_id,system_id,:id,equipment_id FROM work_order_equipment WHERE work_order_id=:source"""),
                {"id": identity, "source": demo_id("assignment-order")})
        identities.append(identity)
        return identity
    try:
        yield engine, app, create
    finally:
        with engine.begin() as conn:
            for identity in identities:
                for table, column in (("audit_events", "entity_id"), ("work_assignments", "work_order_id"),
                                      ("work_order_equipment", "work_order_id"), ("work_orders", "work_order_id")):
                    conn.execute(text(f"DELETE FROM {table} WHERE {column}=:id"), {"id": identity})


def proposal(client, task):
    context = client.get(PREFIX+f"/ui/tasks/{task}/assignment-context").json()
    assert context["status"] == "ready", context
    response = client.post(PREFIX+f"/tasks/{task}/assignment-preview", json={"expected_revision": context["expectedRevision"],
        "start_local": context["defaultStartLocal"], "end_local": context["defaultEndLocal"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ok", result
    return {**result["command"], "crew_id": result["crewId"]}


def snapshot(engine, task):
    with engine.connect() as conn:
        return dict(order=conn.scalar(text("SELECT to_jsonb(w) FROM work_orders w WHERE work_order_id=:id"), {"id": task}),
            assignments=conn.scalar(text("SELECT jsonb_agg(to_jsonb(a) ORDER BY work_assignment_id) FROM work_assignments a WHERE work_order_id=:id"), {"id": task}),
            audit=conn.scalar(text("SELECT jsonb_agg(to_jsonb(a) ORDER BY audit_event_id) FROM audit_events a WHERE entity_id=:id"), {"id": task}))


def test_assignment_saves_complete_team_times_qualification_facts_and_audit(jobs):
    engine, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as client:
        command = proposal(client, task)
        response = client.post(PREFIX+f"/tasks/{task}/assign", json=command)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        result = response.json()
        assert result["task"]["state"] == "assigned" and result["task"]["revision"] == 2
        assert datetime.fromisoformat(result["task"]["scheduledEnd"]) == datetime.fromisoformat(command["end_at"])
        assert {row["executorId"] for row in result["task"]["assignees"]} == set(command["executor_ids"])
        assert len(result["assignments"]) == 2
        for row in result["assignments"]:
            canonical = Assignment.model_validate_json(json.dumps(row))
            assert canonical.assigned_by == demo_id("dispatcher") and canonical.status == "active"
            assert canonical.qualification_ids == [demo_id("assignment-skill")]
        saved = snapshot(engine, task)
        assert all(row["reason"] == command["reason"] and row["crew_id"] == command["crew_id"] for row in saved["assignments"])
        assert all(row["qualification_snapshot"][0]["verified_at"] for row in saved["assignments"])
        assert saved["audit"][0]["action"] == "assign"
        assert saved["audit"][0]["before_snapshot"]["status"] == "draft"
        assert len(saved["audit"][0]["after_snapshot"]["assignments"]) == 2
        assert client.get(PREFIX+f"/ui/tasks/{task}").json()["task"] == result["task"]
        # A second call cannot create another generation with the old revision.
        assert client.post(PREFIX+f"/tasks/{task}/assign", json=command).status_code == 409
        assert snapshot(engine, task) == saved


def test_assignment_reassignment_releases_old_rows_and_retains_history(jobs):
    engine, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as client:
        command = proposal(client, task)
        first = client.post(PREFIX+f"/tasks/{task}/assign", json=command)
        assert first.status_code == 200, first.text
        old_ids = {row["assignment_id"] for row in first.json()["assignments"]}
        # Reassignment keeps the same workers but creates new IDs and a new interval.
        command.update(expected_revision=2, start_at=command["end_at"],
            end_at=(datetime.fromisoformat(command["end_at"]) + timedelta(hours=1)).isoformat(), reason="Согласованный перенос")
        second = client.post(PREFIX+f"/tasks/{task}/assign", json=command)
        assert second.status_code == 200, second.text
        assert second.json()["task"]["revision"] == 3
        assert not old_ids & {row["assignment_id"] for row in second.json()["assignments"]}
        saved = snapshot(engine, task)
        assert len(saved["assignments"]) == 4 and len(saved["audit"]) == 2
        assert all(row["status"] == "cancelled" and row["released_at"] for row in saved["assignments"] if row["work_assignment_id"] in old_ids)
        assert len(second.json()["task"]["assignees"]) == 2


@pytest.mark.parametrize("state", ["clarification", "in_progress", "in_review", "rework", "completed", "cancelled"])
def test_assignment_cannot_replace_crew_after_work_started_or_in_wrong_state(jobs, state):
    engine, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
        with engine.begin() as conn:
            conn.execute(text("UPDATE work_orders SET status=:status WHERE work_order_id=:id"), {"id": task, "status": state})
        before = snapshot(engine, task)
        response = client.post(PREFIX+f"/tasks/{task}/assign", json=body)
        assert response.status_code == 409, response.text
        assert snapshot(engine, task) == before


@pytest.mark.parametrize("role", ["admin", "engineer", "executor"])
def test_assignment_roles_and_no_changes(jobs, role):
    engine, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as dispatcher:
        body = proposal(dispatcher, task)
    before = snapshot(engine, task)
    with closing(login(app, role)) as client:
        assert client.post(PREFIX+f"/tasks/{task}/assign", json=body).status_code == 403
    assert snapshot(engine, task) == before


@pytest.mark.parametrize("change,expected", [("csrf", 403), ("revision", 409), ("partial", 409), ("duplicate", 422),
    ("duration", 409), ("naive", 422), ("reverse", 422), ("seconds", 422), ("past", 409),
    ("deadline", 409), ("foreign_worker", 404), ("foreign_crew", 404), ("reason", 422), ("principal", 422)])
def test_assignment_rejects_invalid_or_stale_commands_atomically(jobs, change, expected):
    engine, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
        headers = {}
        if change == "csrf": headers = {"X-CSRF-Token": "bad"}
        elif change == "revision": body["expected_revision"] = 99
        elif change == "partial": body["executor_ids"] = body["executor_ids"][:1]
        elif change == "duplicate": body["executor_ids"] = [body["executor_ids"][0]] * 2
        elif change == "duration": body["end_at"] = (datetime.fromisoformat(body["end_at"]) + timedelta(minutes=1)).isoformat()
        elif change == "naive": body["start_at"] = datetime.fromisoformat(body["start_at"]).replace(tzinfo=None).isoformat()
        elif change == "reverse": body["end_at"] = body["start_at"]
        elif change == "seconds": body["start_at"] = datetime.fromisoformat(body["start_at"]).replace(second=1).isoformat()
        elif change == "past":
            body.update(start_at="2000-01-01T09:00:00Z", end_at="2000-01-01T10:00:00Z")
        elif change == "deadline":
            day = datetime.fromisoformat(body["start_at"]) + timedelta(days=2)
            body.update(start_at=day.isoformat(), end_at=(day+timedelta(hours=1)).isoformat())
        elif change == "foreign_worker": body["executor_ids"][0] = str(uuid4())
        elif change == "foreign_crew": body["crew_id"] = str(uuid4())
        elif change == "reason": body["reason"] = "  "
        else: body["assigned_by"] = str(demo_id("admin"))
        before = snapshot(engine, task)
        response = client.post(PREFIX+f"/tasks/{task}/assign", json=body, headers=headers)
        assert response.status_code == expected, response.text
        assert snapshot(engine, task) == before


@pytest.mark.parametrize("table,column,value,key", [
    ("users", "is_active", False, "assignment-worker-2"),
    ("site_memberships", "is_active", False, "assignment-worker-2"),
    ("site_memberships", "role", "engineer", "assignment-worker-2"),
    ("user_skills", "verified_at", None, "assignment-worker-2"),
    ("user_skills", "valid_until", "2000-01-01", "assignment-worker-2"),
    ("availability_slots", "status", "unavailable", "assignment-worker-2"),
    ("crew_members", "valid_to", "2000-01-01", "assignment-worker-2"),
    ("crews", "is_active", False, "assignment-crew"),
    ("maintenance_rules", "publication_status", "draft", "assignment-rule"),
    ("maintenance_rules", "active_from", "2090-01-01", "assignment-rule"),
    ("regulation_editions", "is_approved", False, "assignment-edition"),
    ("equipment", "status", "retired", "assignment-equipment"),
])
def test_assignment_revalidates_changed_facts_after_preview(jobs, table, column, value, key):
    engine, app, create = jobs
    task = create()
    key_column = {"crews": "crew_id", "maintenance_rules": "maintenance_rule_id", "regulation_editions": "regulation_edition_id", "equipment": "equipment_id"}.get(table, "user_id")
    if table == "crew_members":
        # Membership has not begun by the proposed interval.
        column, value = "valid_from", "2090-01-01"
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
        before = snapshot(engine, task)
        with engine.begin() as conn:
            old = conn.scalar(text(f"SELECT {column} FROM {table} WHERE {key_column}=:id"), {"id": demo_id(key)})
            conn.execute(text(f"UPDATE {table} SET {column}=:value WHERE {key_column}=:id"), {"id": demo_id(key), "value": value})
        try:
            response = client.post(PREFIX+f"/tasks/{task}/assign", json=body)
            assert response.status_code == 409, response.text
            assert snapshot(engine, task) == before
        finally:
            with engine.begin() as conn:
                conn.execute(text(f"UPDATE {table} SET {column}=:value WHERE {key_column}=:id"), {"id": demo_id(key), "value": old})


@pytest.mark.parametrize("failure", ["second_worker", "audit"])
def test_assignment_failure_rolls_back_released_members_new_rows_task_and_audit(jobs, monkeypatch, failure):
    engine, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
        assert client.post(PREFIX+f"/tasks/{task}/assign", json=body).status_code == 200
        body["expected_revision"] = 2
        before = snapshot(engine, task)
        original = MaintenanceRepository.add
        calls = 0
        def broken(repo, table, **values):
            nonlocal calls
            if table == "work_assignments": calls += 1
            if (failure == "audit" and table == "audit_events") or (failure == "second_worker" and table == "work_assignments" and calls == 2):
                raise RuntimeError("injected assignment transaction failure")
            return original(repo, table, **values)
        monkeypatch.setattr(MaintenanceRepository, "add", broken)
        response=client.post(PREFIX+f"/tasks/{task}/assign", json=body)
        assert response.status_code==500
        assert response.json()["error"]["code"]=="INTERNAL_ERROR"
        assert "injected" not in response.text
        assert snapshot(engine, task) == before


@pytest.fixture
def second_dispatcher(runtime):
    engine, app = runtime
    identity, email = uuid4(), f"{uuid4()}@example.test"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users(user_id,full_name,email,password_hash) SELECT :id,'Second dispatcher',:email,password_hash FROM users WHERE user_id=:source"),
                     {"id": identity, "email": email, "source": demo_id("dispatcher")})
        conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:id,'dispatcher')"), {"id": identity, "site": demo_id("site")})
    from fastapi.testclient import TestClient
    import os
    client = TestClient(app)
    result = client.post("/api/v1/auth/login", json={"email": email, "password": os.environ["FIXRATE_TEST_PASSWORD"]})
    assert result.status_code == 200
    client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
    try:
        yield client
    finally:
        client.close()
        # Keep the actor if a successful audited assignment references it.
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM fixrate_sessions WHERE user_id=:id"), {"id": identity})


@pytest.mark.parametrize("scenario", ["same_task", "overlap", "adjacent"])
def test_assignment_concurrent_requests_never_double_book_or_partially_assign(jobs, second_dispatcher, scenario):
    engine, app, create = jobs
    first = create()
    second = first if scenario == "same_task" else create()
    with closing(login(app, "dispatcher")) as client:
        one = proposal(client, first)
        two = deepcopy(one)
        two["executor_ids"].reverse()  # HTTP list order must not influence lock order.
        if scenario == "adjacent":
            two.update(start_at=one["end_at"], end_at=(datetime.fromisoformat(one["end_at"])+timedelta(hours=1)).isoformat())
        barrier = Barrier(2)
        def send(connection, task, body):
            barrier.wait(timeout=10)
            return connection.post(PREFIX+f"/tasks/{task}/assign", json=body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(send, client, first, one)
            b = pool.submit(send, second_dispatcher, second, two)
            replies = [a.result(timeout=20), b.result(timeout=20)]
        assert sorted(r.status_code for r in replies) == ([200, 200] if scenario == "adjacent" else [200, 409]), [r.text for r in replies]
        saved = [snapshot(engine, identity) for identity in {first, second}]
        assert sum(len(row["assignments"] or []) for row in saved) == (4 if scenario == "adjacent" else 2)
        assert sum(len(row["audit"] or []) for row in saved) == (2 if scenario == "adjacent" else 1)
        assert all(row["order"]["revision"] == (2 if row["assignments"] else 1) for row in saved)


def test_assignment_reloads_qualification_after_waiting_for_worker_lock(jobs):
    engine, app, create = jobs
    task, user = create(), demo_id("assignment-worker-2")
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
        before = snapshot(engine, task)
        with engine.connect() as blocker:
            transaction = blocker.begin()
            pid = blocker.scalar(text("SELECT pg_backend_pid()"))
            original = blocker.scalar(text("SELECT verified_at FROM user_skills WHERE user_id=:id"), {"id": user})
            blocker.execute(text("SELECT user_id FROM users WHERE user_id=:id FOR UPDATE"), {"id": user})
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(client.post, PREFIX+f"/tasks/{task}/assign", json=body)
                try:
                    deadline = time.monotonic()+10
                    while time.monotonic() < deadline:
                        with engine.connect() as observer:
                            waiting = observer.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)))"), {"pid": pid})
                        if waiting: break
                        time.sleep(0.02)
                    assert waiting, "Assignment never waited for the worker lock"
                    blocker.execute(text("UPDATE user_skills SET verified_at=NULL WHERE user_id=:id"), {"id": user})
                    transaction.commit()
                    response = pending.result(timeout=15)
                    assert response.status_code == 409, response.text
                    assert snapshot(engine, task) == before
                finally:
                    if transaction.is_active: transaction.rollback()
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE user_skills SET verified_at=:verified WHERE user_id=:id"), {"id": user, "verified": original})


def test_assignment_checks_global_worker_bookings_without_exposing_foreign_site(jobs):
    engine, app, create = jobs
    task, foreign_site, foreign_system, foreign_task = create(), uuid4(), uuid4(), uuid4()
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO sites(site_id,name) VALUES (:id,'Private foreign site')"), {"id": foreign_site})
            conn.execute(text("INSERT INTO engineering_systems(system_id,site_id,code,name) VALUES (:id,:site,'private','Private system')"), {"id": foreign_system, "site": foreign_site})
            conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,'technician')"), {"site": foreign_site, "user": demo_id("assignment-worker-1")})
            conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,required_people_snapshot,norm_hours_snapshot)
                VALUES (:id,:site,:system,'manual','assigned',1,1)"""), {"id": foreign_task, "site": foreign_site, "system": foreign_system})
            conn.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at)
                VALUES (:site,:task,:user,:actor,:start,:end)"""), {"site": foreign_site, "task": foreign_task,
                "user": demo_id("assignment-worker-1"), "actor": demo_id("assignment-worker-1"), "start": datetime.fromisoformat(body["start_at"]), "end": datetime.fromisoformat(body["end_at"])})
        try:
            before = snapshot(engine, task)
            response = client.post(PREFIX+f"/tasks/{task}/assign", json=body)
            assert response.status_code == 409, response.text
            assert "Private" not in response.text and str(foreign_task) not in response.text
            assert snapshot(engine, task) == before
            assert client.post(PREFIX+f"/tasks/{foreign_task}/assign", json=body).status_code == 404
            assert client.get(PREFIX+f"/ui/tasks/{foreign_task}").status_code == 404
        finally:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM work_assignments WHERE work_order_id=:id"), {"id": foreign_task})
                conn.execute(text("DELETE FROM work_orders WHERE work_order_id=:id"), {"id": foreign_task})
                conn.execute(text("DELETE FROM site_memberships WHERE site_id=:id"), {"id": foreign_site})
                conn.execute(text("DELETE FROM engineering_systems WHERE site_id=:id"), {"id": foreign_site})
                conn.execute(text("DELETE FROM sites WHERE site_id=:id"), {"id": foreign_site})


def test_assignment_requires_a_session(jobs):
    from fastapi.testclient import TestClient
    _, app, create = jobs
    task = create()
    with closing(login(app, "dispatcher")) as client:
        body = proposal(client, task)
    with closing(TestClient(app)) as anonymous:
        assert anonymous.post(PREFIX+f"/tasks/{task}/assign", json=body).status_code == 401
