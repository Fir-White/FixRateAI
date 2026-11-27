"""Order-table routes and write boundaries."""
from datetime import datetime, time, timedelta
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import io
from uuid import uuid4
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, text

from app.integration.demo import demo_id
from app.main import create_app
from app.manage import seed_demo
from tests.backend.test_installation_bootstrap import installation

BASE = "/api/v1/maintenance/planning/order-table"
API = "/api/v1/maintenance"
TASK = str(demo_id("assignment-order"))
PASSWORD = "Synthetic-order-table-fixture-2026!"


def test_order_table_contract_is_registered():
    app = create_app()
    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert {(BASE, "GET"), (BASE + "/bindings", "GET"), (BASE + "/preview", "POST"),
            (BASE + "/apply", "POST"), (BASE + "/export.xlsx", "GET")} <= routes


@pytest.fixture
def lab(installation, monkeypatch):
    engine, _ = installation
    for name in ("FIXRATE_ACTIVE_ROLES", "FIXRATE_DEMO_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    seed_demo(engine, PASSWORD)
    with engine.begin() as conn:
        conn.execute(text("""UPDATE maintenance_rules SET schedule_parameters =
            schedule_parameters || '{"methodology_ref":"TEST: проверенный регламент"}'::jsonb
            WHERE maintenance_rule_id=:id"""), dict(id=demo_id("assignment-rule")))
        day, tz = conn.execute(text("""
            SELECT e.planned_date,s.timezone FROM schedule_entries e JOIN sites s USING(site_id)
            WHERE e.schedule_entry_id=:id"""), dict(id=demo_id("assignment-entry"))).one()
    app = create_app(engine)
    with TestClient(app) as chief:
        sign_in(chief, "chief_engineer")
        yield engine, app, chief, day, ZoneInfo(tz)


def sign_in(client, role):
    auth = client.post("/api/v1/auth/login", json=dict(email=f"fixrate-demo-{role}@example.test", password=PASSWORD))
    assert auth.status_code == 200
    client.headers["X-CSRF-Token"] = auth.json()["csrfToken"]


def local(day, hour=10):
    return datetime.combine(day, time(hour)).isoformat(timespec="minutes")


def preview(client, *changes):
    request = dict(changes=list(changes), reason="TEST: проверка рабочего окна")
    reply = client.post(BASE + "/preview", json=request)
    assert reply.status_code == 200
    return request, reply.json()


def apply_data(request, plan, **kwargs):
    return dict(request, preview_digest=plan["preview_digest"], idempotency_key=str(uuid4()), **kwargs)


def test_preview_apply_replay_and_xlsx_without_rewriting_norm(lab):
    engine, _, chief, day, _ = lab
    task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    assert TASK in {row["task_id"] for row in chief.get(BASE, params=dict(month=str(day)[:7])).json()["items"]}
    binding = str(demo_id("assignment-binding"))
    assert binding in {item["binding_id"] for item in chief.get(BASE + "/bindings", params=dict(q="ALG03")).json()["items"]}
    request, plan = preview(chief, dict(kind="existing", task_id=TASK, expected_revision=task["revision"],
        planned_start=local(day), note="=1+1", planned_person_hours="2.50"),
        dict(kind="new", binding_id=binding, planned_start=local(day + timedelta(days=1)), due_date=str(day + timedelta(days=1))))
    assert plan["can_apply"] and [item["action"] for item in plan["items"]] == ["update", "create"], plan
    assert chief.get(f"{API}/ui/tasks/{TASK}").json()["task"] == task
    new_id = plan["items"][1]["task_id"]
    assert chief.get(f"{API}/ui/tasks/{new_id}").status_code == 404
    command = apply_data(request, plan)
    saved = chief.post(BASE + "/apply", json=command)
    assert saved.status_code == 200, saved.text
    assert not saved.json()["replayed"]
    assert chief.post(BASE + "/apply", json=command).json() == dict(saved.json(), replayed=True)
    assert chief.post(BASE + "/apply", json=dict(command, reason="Другой запрос")).status_code == 409
    current = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    assert current["scheduledStart"][:16] == local(day)
    assert current["normHours"] == task["normHours"]
    assert current["plannedPersonHours"] == "2.5" and current["planningNote"] == "=1+1"
    added = chief.get(f"{API}/ui/tasks/{new_id}").json()["task"]
    assert added["state"] == "draft" and not added["assignees"]
    assert added["mandatoryDueDate"] == str(day + timedelta(days=1))
    again = preview(chief, request["changes"][1])[1]
    assert not again["can_apply"]
    xlsx = chief.get(BASE + "/export.xlsx", params=dict(month=str(day)[:7]))
    assert xlsx.status_code == 200
    with ZipFile(io.BytesIO(xlsx.content)) as book:
        xml = book.read("xl/worksheets/sheet1.xml")
        assert b'<f>' not in xml and b'=1+1' in xml
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM work_orders WHERE work_order_id=:id"), dict(id=new_id)) == 1
        assert conn.scalar(text("SELECT revision FROM schedule_entries WHERE schedule_entry_id=:id"),
                           dict(id=demo_id("assignment-entry"))) == 2


def test_assigned_requires_own_confirmation_retains_workers_and_notifies(lab):
    engine, _, chief, day, _ = lab
    task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    crew_id = str(demo_id("assignment-crew"))
    search = chief.post(f"{API}/tasks/{TASK}/assignment-preview",
        json=dict(expected_revision=task["revision"], start_local=local(day, 9), end_local=local(day, 11), crew_id=crew_id))
    initial = search.json()["command"]
    assert initial
    assigned = chief.post(f"{API}/tasks/{TASK}/assign", json=dict(initial, crew_id=crew_id, reason="TEST: исходное назначение"))
    assert assigned.status_code == 200
    old = assigned.json()["task"]
    row = dict(kind="existing", task_id=TASK, expected_revision=old["revision"], planned_start=local(day, 13))
    request, plan = preview(chief, row)
    assert plan["can_apply"] and plan["requires_assigned_confirmation"], plan
    assert chief.post(BASE + "/apply", json=apply_data(request, plan)).status_code == 409
    assert chief.get(f"{API}/ui/tasks/{TASK}").json()["task"] == old
    assert not preview(chief, dict(row, planned_start=local(day, 18)))[1]["can_apply"]
    assert not preview(chief, row, row)[1]["can_apply"]
    command = apply_data(request, plan, confirm_assigned=True)
    reply = chief.post(BASE + "/apply", json=command)
    assert reply.status_code == 200, reply.text
    assert chief.post(BASE + "/apply", json=command).json()["replayed"]
    new = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    assert new["revision"] == old["revision"] + 1
    assert new["assignees"] == old["assignees"] and new["scheduledStart"][:16] == local(day, 13)
    with engine.connect() as conn:
        assert conn.scalar(text("""SELECT count(*) FROM maintenance_notifications WHERE work_order_id=:id
            AND event_key LIKE :pattern"""), dict(id=TASK, pattern="%:rescheduled")) == len(old["assignees"])
        assert conn.scalar(text("""SELECT count(*) FROM work_assignments WHERE work_order_id=:id
            AND crew_id=:crew AND status='assigned'"""), dict(id=TASK, crew=crew_id)) == len(old["assignees"])


def test_foreign_role_stale_preview_and_history_block_all_writes(lab):
    engine, app, chief, day, _ = lab
    old = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    row = dict(kind="existing", task_id=TASK, expected_revision=old["revision"], note="TEST")
    request, plan = preview(chief, row)
    with closing(TestClient(app)) as engineer:
        sign_in(engineer, "engineer")
        assert engineer.get(BASE, params=dict(month=str(day)[:7])).status_code == 403
        assert engineer.post(BASE + "/preview", json=request).status_code == 403
        assert engineer.post(BASE + "/apply", json=apply_data(request, plan)).status_code == 403
    assert not preview(chief, dict(row, task_id=str(uuid4())))[1]["can_apply"]
    assert not preview(chief, dict(row, planned_start=local(day + timedelta(days=1))))[1]["can_apply"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_orders SET status='in_progress', started_at=now(), revision=revision+1 WHERE work_order_id=:id"), dict(id=TASK))
    assert chief.post(BASE + "/apply", json=apply_data(request, plan)).status_code == 409
    assert not preview(chief, dict(row, expected_revision=old["revision"]+1))[1]["can_apply"]


def test_apply_is_atomic_and_parallel_retry_is_single_write(lab):
    engine, app, chief, day, _ = lab
    task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    row = dict(kind="existing", task_id=TASK, expected_revision=task["revision"], note="TEST: параллельный повтор")
    request, plan = preview(chief, row)
    assert plan["can_apply"]
    bad = dict(request, changes=[row, dict(kind="existing", task_id=str(uuid4()), expected_revision=1, note="TEST")])
    assert chief.post(BASE + "/apply", json=apply_data(bad, plan)).status_code == 409
    assert chief.get(f"{API}/ui/tasks/{TASK}").json()["task"] == task
    command = apply_data(request, plan)

    def send(_):
        with closing(TestClient(app)) as same_actor:
            sign_in(same_actor, "chief_engineer")
            response = same_actor.post(BASE + "/apply", json=command)
            assert response.status_code == 200
            return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(send, range(2)))
    assert sorted(item["replayed"] for item in result) == [False, True]
    assert result[0]["items"] == result[1]["items"]
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='worksheet_update'"),
                           dict(id=TASK)) == 1


def test_one_time_order_rechecks_binding_when_moved(lab):
    engine, _, chief, day, _ = lab
    binding = str(demo_id("assignment-binding"))
    new_day, due = day + timedelta(days=1), day + timedelta(days=3)
    command, first = preview(chief, dict(kind="new", binding_id=binding, planned_start=local(new_day), due_date=str(due)))
    assert chief.post(BASE + "/apply", json=apply_data(command, first)).status_code == 200
    identity = first["items"][0]["task_id"]
    task = chief.get(f"{API}/ui/tasks/{identity}").json()["task"]
    command, second = preview(chief, dict(kind="existing", task_id=identity,
        expected_revision=task["revision"], planned_start=local(due)))
    assert second["can_apply"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE rule_equipment SET valid_to=:day, revision=revision+1 WHERE binding_id=:id"),
                     dict(day=new_day, id=binding))
    assert chief.post(BASE + "/apply", json=apply_data(command, second)).status_code == 409
    assert chief.get(f"{API}/ui/tasks/{identity}").json()["task"] == task


def test_move_preview_blocks_calendar_occurrence_collision(lab):
    engine, _, chief, day, tz = lab
    target_day = day + timedelta(days=1)
    entry, deadline = demo_id("assignment-entry"), datetime.combine(target_day + timedelta(days=1), time.min, tz)
    with engine.begin() as conn:
        args = dict(entry=entry, day=target_day, deadline=deadline, task=TASK)
        conn.execute(text("""UPDATE schedule_entries SET regulatory_deadline_on=:day, regulatory_deadline_at=:deadline
            WHERE schedule_entry_id=:entry"""), args)
        conn.execute(text("UPDATE work_orders SET regulatory_deadline_at=:deadline WHERE work_order_id=:task"), args)
        conn.execute(text("""INSERT INTO schedule_entries(site_id,system_id,schedule_plan_id,maintenance_rule_id,
            binding_id,sequence_no,planned_date,earliest_date,regulatory_deadline_on,regulatory_deadline_at)
            SELECT site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,sequence_no,:day,
            earliest_date,:day,:deadline FROM schedule_entries WHERE schedule_entry_id=:entry"""), args)
    task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    _, plan = preview(chief, dict(kind="existing", task_id=TASK, expected_revision=task["revision"],
        planned_start=local(target_day)))
    assert not plan["can_apply"] and "Календарное вхождение" in plan["items"][0]["issue"]


def test_list_pages_search_sql_budget_and_foreign_site(lab):
    engine, _, chief, day, _ = lab
    foreign_site, foreign_system, foreign_order = uuid4(), uuid4(), uuid4()
    month = str(day)[:7]
    statements = []

    def count(_conn, _cursor, sql, _params, _context, _many):
        if sql.lstrip().upper().startswith("SELECT"):
            statements.append(sql)

    def rows(**values):
        statements.clear()
        reply = chief.get(BASE, params=dict(month=month, **values))
        assert reply.status_code == 200, reply.text
        return reply.json(), len(statements)

    event.listen(engine, "before_cursor_execute", count)
    try:
        _, small = rows(q="TEST: строка")
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO work_orders(site_id,system_id,origin,operation_snapshot,planned_start_at,
                regulatory_deadline_at,required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot)
                SELECT site_id,system_id,'manual',jsonb_build_object('title','TEST: строка №'||n,
                    'data_origin','synthetic_demo'),regulatory_deadline_at-interval '5 hours',
                    regulatory_deadline_at,required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot
                FROM work_orders CROSS JOIN generate_series(1,31) n WHERE work_order_id=:task"""), dict(task=TASK))
            args = dict(site=foreign_site, system=foreign_system, id=foreign_order, task=TASK)
            conn.execute(text("INSERT INTO sites(site_id,name) VALUES (:site,'TEST: вне области')"), args)
            conn.execute(text("INSERT INTO engineering_systems(system_id,site_id,code,name) VALUES (:system,:site,'TEST','TEST')"), args)
            conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,operation_snapshot,
                planned_start_at,regulatory_deadline_at,required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot)
                SELECT :id,:site,:system,'manual',jsonb_build_object('title','TEST: строка чужого объекта',
                    'data_origin','synthetic_demo'),regulatory_deadline_at-interval '5 hours',regulatory_deadline_at,
                    required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot
                FROM work_orders WHERE work_order_id=:task"""), args)
        first, large = rows(q="TEST: строка")
        second, _ = rows(q="TEST: строка", offset=25)
        assert small == large and large <= 20
        assert len(first["items"]) == 25 and first["has_more"]
        assert len(second["items"]) == 6 and not second["has_more"]
        assert len({row["task_id"] for row in first["items"] + second["items"]}) == 31
        assert not rows(q="чужого объекта")[0]["items"]
        assert not preview(chief, dict(kind="existing", task_id=str(foreign_order), expected_revision=1, note="TEST"))[1]["can_apply"]
        xlsx = chief.get(BASE + "/export.xlsx", params=dict(month=month, q="TEST: строка"))
        with ZipFile(io.BytesIO(xlsx.content)) as book:
            assert book.read("xl/worksheets/sheet1.xml").count(b"<row ") == 32
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_assistant_prepares_then_confirms_same_order_table_api(lab):
    from tests.backend.test_assistant import confirm, proposal, thread

    _, _, chief, _, _ = lab
    task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    request, plan = preview(chief, dict(kind="existing", task_id=TASK,
        expected_revision=task["revision"], note="TEST: окно проверено"))
    record = proposal(chief, thread(chief), "order_table_apply", {"body": apply_data(request, plan)})
    assert chief.get(f"{API}/ui/tasks/{TASK}").json()["task"] == task
    result = confirm(chief, record)
    assert result.status_code == 200 and result.json()["status"] == "succeeded"
    after = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    assert after["revision"] == task["revision"] + 1 and after["planningNote"] == "TEST: окно проверено"


def test_v4_worksheet_tools_prepare_real_card_without_writing(lab, monkeypatch):
    from dataclasses import replace
    from tests.backend.test_assistant import confirm, thread
    from tests.backend.test_assistant_tool_agent import send

    _, app, chief, day, _ = lab
    before = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
    request = dict(changes=[dict(kind="existing", task_id=TASK, expected_revision=before["revision"],
        note="TEST: правка в чате")], reason="TEST: проверка ТО")

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            names = {spec["function"]["name"] for spec in tools}
            assert {"order_table_read", "order_table_bindings", "order_table_preview", "order_table_export",
                    "propose_order_table_apply"} <= names
            if messages[-1]["role"] != "tool":
                name, args = "order_table_read", {"month": str(day)[:7], "q": TASK}
            else:
                assert TASK in messages[-1]["content"]
                name, args = "propose_order_table_apply", request
            return dict(role="assistant", content="", tool_calls=[dict(id="test", function=dict(name=name, arguments=args))])

    monkeypatch.setitem(app.state._state, "settings", replace(app.state.settings, assistant_agent_version="v4"))
    monkeypatch.setitem(app.state._state, "assistant_provider_factory", Provider)
    view = send(chief, thread(chief), "Уточни примечание указанного наряда в таблице ТО.")
    assert view["turns"][-1]["status"] == "completed"
    action, = view["actions"]
    assert action["tool_name"] == "order_table_apply"
    assert action["before_snapshot"]["preview"]["items"][0]["note"] == "TEST: правка в чате"
    assert chief.get(f"{API}/ui/tasks/{TASK}").json()["task"] == before
    assert confirm(chief, action).json()["status"] == "succeeded"
    assert chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]["planningNote"] == "TEST: правка в чате"
