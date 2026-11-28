"""The release profile equalizes operations, not identities or approval exceptions."""
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from app.assistant.tool_agent_tools import ToolSession
from app.security.sessions import Principal
from tests.backend.test_installation_bootstrap import installation
from tests.backend.test_assistant import B, thread
from tests.backend.test_assistant_tool_agent import send
from tests.backend.test_catalog_decisions import catalog, write
from tests.backend.test_evidence_readiness import job, submit_pair
from tests.backend.test_management import config, equipment, join, managed
from tests.backend.test_order_table import BASE, API, TASK, apply_data, lab, preview, sign_in
from tests.backend.test_runtime_integration import login, runtime
from tests.backend.test_v4_context_reads import call, v4


@pytest.fixture
def mvp(monkeypatch):
    monkeypatch.setenv("FIXRATE_PERMISSION_PROFILE", "mvp")


def test_mvp_shares_work_and_agent_scope_but_not_administration(mvp, lab):
    _, app, chief, day, tz = lab
    with closing(TestClient(app)) as engineer, closing(TestClient(app)) as executor:
        sign_in(engineer, "engineer")
        sign_in(executor, "1")
        scopes = []
        for client, role in ((chief, "chief_engineer"), (engineer, "engineer")):
            response = client.get(BASE, params={"month": str(day)[:7]})
            assert response.status_code == 200, response.text
            assert any(row["task_id"] == TASK for row in response.json()["items"])
            profile = client.get("/api/v1/auth/session").json()["profile"]
            assert profile["role"] == role and profile["permissionProfile"] == "mvp"
            assert client.get(API + "/users").status_code == 403
            assert client.get(API + "/management/enrollment").status_code == 403
            principal = Principal(uuid4(), uuid4(), role, "TEST", "test@example.test", "TEST", tz.key)
            scopes.append(ToolSession(app, principal, {}, uuid4(), {}, [], local_date=day))
        chief_definitions, engineer_definitions = (scope.definition.keys() for scope in scopes)
        assert chief_definitions - engineer_definitions == {
            "find_workbook_issued_orders", "find_workbook_order_rows", "preview_workbook_order",
            "propose_workbook_order", "propose_workbook_write",
        }
        assert engineer_definitions <= chief_definitions
        assert {"find_source_workbooks", "download_source_workbook"} <= engineer_definitions
        chief_registry, engineer_registry = (scope.registry.keys() for scope in scopes)
        assert chief_registry - engineer_registry == {
            "workbook_catalog", "workbook_from_catalog", "workbook_issued_orders", "workbook_order_apply",
            "workbook_order_preview", "workbook_order_rows", "workbook_upload", "workbook_version_from_file",
        }
        assert engineer_registry <= chief_registry
        assert {"workbooks_list", "workbook_versions", "workbook_version", "workbook_download"} <= engineer_registry
        assert {"order_table_apply", "report_review", "task_assign"} <= set(scopes[0].registry)
        assert not ({"late_authorize", "publication_approve", "staff_edit"} & set(scopes[0].registry))
        assert executor.get(BASE, params={"month": str(day)[:7]}).status_code == 403

        task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
        for client in (chief, engineer):
            command, checked = preview(client, dict(kind="existing", task_id=TASK,
                expected_revision=task["revision"], note=f'TEST: ревизия {task["revision"]}'))
            assert client.post(BASE + "/apply", json=apply_data(command, checked)).status_code == 200
            task = chief.get(f"{API}/ui/tasks/{TASK}").json()["task"]
        assert task["planningNote"].startswith("TEST: ревизия")


def test_mvp_overdue_acceptance_requires_a_separate_grant_and_audits_actual_reviewer(mvp, job):
    engine, app, task, report = job
    params = dict(task=task, report=report, deadline=datetime.now(timezone.utc) - timedelta(minutes=1))
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_orders SET status='in_review', regulatory_deadline_at=:deadline WHERE work_order_id=:task"), params)
        conn.execute(text("UPDATE work_reports SET status='submitted', submitted_at=now() WHERE work_report_id=:report"), params)
    url = f'{API}/tasks/{task}'
    body = dict(expected_revision=1, execution_id=str(report), verdict='accepted', reason='Учебное решение')
    for role in ('chief_engineer', 'engineer', 'executor'):
        with closing(login(app, role)) as client:
            assert client.post(url + '/late-authorization', json=dict(expected_revision=1, reason='Ошибка срока')).status_code == 403
            blocked = client.post(url + '/review', json=body | dict(late_reason='Не заменяет согласование'))
            assert blocked.status_code == (403 if role == 'executor' else 409), blocked.text
    with engine.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM acceptance_reviews WHERE work_order_id=:task"), params) == 0
        conn.execute(text("UPDATE work_orders SET regulatory_deadline_at=now()+interval '1 hour' WHERE work_order_id=:task"), params)
    with closing(login(app, 'engineer')) as client:
        reviewed = client.post(url + '/review', json=body)
        assert reviewed.status_code == 200, reviewed.text
        assert client.post(url + '/review', json=body).status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT after_snapshot->>'actor_role' FROM audit_events WHERE entity_id=:task AND action='review'"), params) == 'engineer'
        assert conn.scalar(text("SELECT count(*) FROM acceptance_reviews WHERE work_order_id=:task"), params) == 1


def test_mvp_cannot_replace_published_regulation_with_a_draft(managed, monkeypatch):
    engine, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    url = f"{API}/equipment/{eq['equipment_id']}/service-configurations"
    body = config(date.today())
    published = admin.chief.post(url, json=body)
    assert published.status_code == 201, published.text
    binding = published.json()['binding_id']
    monkeypatch.setenv('FIXRATE_PERMISSION_PROFILE', 'mvp')
    for actor in (admin, admin.chief):
        denied = actor.put(f'{url}/{binding}', json=body | dict(enabled=False, expected_revision=1))
        assert denied.status_code == 403, denied.text
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT publication_status FROM maintenance_rules WHERE site_id=:site"), ids).scalars().all()
    assert rows == ['published']


def test_mvp_catalog_drafts_work_for_both_engineers_but_confirmation_does_not(managed, monkeypatch):
    _, _, admin, login_user, _ = managed
    _, address = join(managed, 'engineer')
    identity, rows, _ = catalog(admin)
    monkeypatch.setenv('FIXRATE_PERMISSION_PROFILE', 'mvp')
    with closing(login_user(address)) as engineer:
        for revision, client in enumerate((admin.chief, engineer)):
            result = write(client, identity, rows[0], {'semantics_note': 'Подготовка строки'}, revision)
            assert result.status_code == 200, result.text
            assert not result.json()['confirmed']
            assert write(client, identity, rows[0], {}, revision + 1, True).status_code == 403


@pytest.mark.parametrize('role', ['engineer', 'chief_engineer'])
def test_mvp_v4_report_review_requires_click_and_preserves_actor(mvp, job, monkeypatch, role):
    from app.integration.projections import Views

    engine, app, task, report = job
    bundle = submit_pair(job)
    payload = dict(task_id=str(task), expected_revision=bundle['task']['revision'], execution_id=str(report),
                   verdict='accepted', reason='Снимки и чек-лист проверены')
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_orders SET regulatory_deadline_at=now()+interval '1 hour' WHERE work_order_id=:id"),
                     dict(id=task))

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] != 'tool':
                return call('read_work_order', task_id=str(task))
            return call('propose_report_review', **payload)

    v4(monkeypatch, app, Provider)
    with closing(login(app, role)) as client:
        chat = thread(client)
        result = send(client, chat, 'Подготовь приёмку наряда: снимки и чек-лист проверены.')
        proposals = [a for a in result['actions'] if a['tool_name'] == 'report_review']
        assert len(proposals) == 1 and proposals[0]['status'] == 'proposed'
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM acceptance_reviews WHERE work_order_id=:id"), dict(id=task)) == 0
        action = proposals[0]
        endpoint = f"{B}/actions/{action['action_id']}/confirm"
        confirmation = {'payload_sha256': action['payload_sha256'], 'confirmed': True}
        with closing(login(app, 'executor')) as executor:
            assert executor.post(endpoint, json=confirmation).status_code == 404
        # The DB is free to return the same evidence rows in a different order.
        rows = Views.rows
        def reversed_evidence(self, table, **filters):
            values = rows(self, table, **filters)
            if table == 'evidence_files' and filters.get('work_report_id') == report:
                return list(reversed(values))
            return values
        monkeypatch.setattr(Views, 'rows', reversed_evidence)
        for _ in range(2):
            response = client.post(endpoint, json=confirmation)
            assert response.status_code == 200 and response.json()['status'] == 'succeeded', response.text
    with engine.connect() as conn:
        found = conn.execute(text("SELECT decision_context->>'actor_role' FROM acceptance_reviews WHERE work_order_id=:id"),
                             dict(id=task)).scalars().all()
        assert found == [role]


def forecast_candidate(admin, eq, day, **settings):
    configured = admin.chief.post(f"{API}/equipment/{eq['equipment_id']}/service-configurations",
                                 json=config(day, **settings))
    assert configured.status_code == 201, configured.text
    preview = admin.chief.get(f'{API}/ui/calendar/preview?year={day.year}&month={day.month}').json()
    generated = admin.chief.post(f'{API}/calendar/generate', json=dict(
        year=day.year, month=day.month, preview_token=preview['generationToken'], idempotency_key=str(uuid4())))
    assert generated.status_code == 200, generated.text
    return generated.json()['items'][0]


def test_forecast_confirmation_rechecks_snapshot_after_waiting_for_decision_lock(managed):
    engine, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    day = date.today() + timedelta(days=2)
    item = forecast_candidate(admin, eq, day)
    edited = []

    def concurrent_change(connection, cursor, statement, parameters, context, executemany):
        if not edited and 'orchestration_decisions' in statement and 'FOR UPDATE' in statement:
            edited.append(True)
            with engine.begin() as other:
                other.execute(text("UPDATE equipment SET revision=revision+1 WHERE equipment_id=:id"),
                              dict(id=eq['equipment_id']))

    event.listen(engine, 'before_cursor_execute', concurrent_change)
    try:
        response = admin.chief.post(f"{API}/comparisons/{item['comparison']['runId']}/confirm",
                                    json=dict(selected_date=str(day), reason='Учебная проверка даты'))
    finally:
        event.remove(engine, 'before_cursor_execute', concurrent_change)
    assert edited and response.status_code == 409 and 'STALE_SNAPSHOT' in response.text, response.text
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM audit_events WHERE action='confirm_forecast' AND site_id=:site"), ids) == 0


def test_forecast_confirmation_holds_diagnostic_report_row_until_commit(managed):
    engine, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    past_order, report = uuid4(), uuid4()
    fixture = dict(ids, order=past_order, report=report, asset=eq['equipment_id'])
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO work_orders
            (work_order_id, site_id, system_id, origin, status, required_people_snapshot, norm_hours_snapshot)
            VALUES (:order,:site,:system,'manual','in_review',1,1)"""), fixture)
        conn.execute(text("""INSERT INTO work_order_equipment (site_id,system_id,work_order_id,equipment_id)
            VALUES (:site,:system,:order,:asset)"""), fixture)
        conn.execute(text("""INSERT INTO work_reports (work_report_id,site_id,work_order_id,submitted_by,status,comment,submitted_at)
            VALUES (:report,:site,:order,:user,'submitted','Учебная диагностика',now()-interval '1 day')"""), fixture)
    due = date.today() + timedelta(days=2)
    item = forecast_candidate(admin, eq, due)
    observed = []

    def check_lock(connection, cursor, statement, parameters, context, executemany):
        if 'INSERT INTO audit_events' not in statement:
            return
        with engine.connect() as other:
            try:
                other.execute(text("SELECT 1 FROM work_reports WHERE work_report_id=:report FOR UPDATE NOWAIT"), fixture)
            except OperationalError as exc:
                assert exc.orig.sqlstate == '55P03'
                observed.append('locked')
            else:
                observed.append('unlocked')

    event.listen(engine, 'before_cursor_execute', check_lock)
    try:
        result = admin.chief.post(f"{API}/comparisons/{item['comparison']['runId']}/confirm",
                                  json=dict(selected_date=str(due), reason='Учебная проверка блокировки'))
    finally:
        event.remove(engine, 'before_cursor_execute', check_lock)
    assert result.status_code == 200, result.text
    assert observed == ['locked']


def test_forecast_does_not_move_a_draft_with_a_saved_interval(managed, monkeypatch):
    from app.integration import planning
    from app.integration.forecasting import calculate
    from app.orchestrator.forecast import forecast_result

    engine, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    due = date.today() + timedelta(days=3)
    proposed = due - timedelta(days=1)

    def comparison(snapshot, item, forecaster, **kwargs):
        return calculate(snapshot, item, forecaster, provider=lambda value: forecast_result(
            value, uuid4(), 'ai', status='ok', day=proposed,
            explanation='Учебный вход проверки интервала', model_ref='test-fixture:interval'))

    monkeypatch.setattr(planning, 'calculate', comparison)
    item = forecast_candidate(admin, eq, due, valid_from=str(proposed), allowed_lead_days=1)
    task = item['taskId']
    with engine.begin() as conn:
        tz = ZoneInfo(conn.scalar(text('SELECT timezone FROM sites WHERE site_id=:site'), ids))
        start = datetime.combine(due, time(10), tz)
        conn.execute(text("""UPDATE work_orders SET planned_start_at=:start,planned_end_at=:finish
            WHERE work_order_id=:id"""), dict(start=start, finish=start + timedelta(hours=1), id=task))
    denied = admin.chief.post(f"{API}/comparisons/{item['comparison']['runId']}/confirm",
                              json=dict(selected_date=str(proposed), reason='Учебная проверка интервала'))
    assert denied.status_code == 409, denied.text
    with engine.connect() as conn:
        assert conn.scalar(text("""SELECT planned_date FROM schedule_entries
            JOIN work_orders USING(schedule_entry_id) WHERE work_order_id=:id"""), dict(id=task)) == due


@pytest.mark.parametrize('role', ['engineer', 'chief_engineer', 'executor'])
def test_v4_catalog_draft_does_not_change_saved_row_until_confirmation(managed, monkeypatch, role):
    _, app, admin, login_user, _ = managed
    _, address = join(managed, role) if role != 'chief_engineer' else (None, None)
    identity, rows, _ = catalog(admin)
    row = rows[0]
    url = f'{API}/catalog-imports/{identity}/operations/{row}/decision'
    monkeypatch.setenv('FIXRATE_PERMISSION_PROFILE', 'mvp')
    assert write(admin, identity, row, {'semantics_note': 'Сохранённая заметка'}).status_code == 200

    available = []

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            available.append('propose_catalog_draft' in {item['function']['name'] for item in tools})
            if messages[-1]['role'] == 'tool':
                return dict(content='Изменение не подготовлено.')
            return call('propose_catalog_draft', catalog_id=identity, row_number=row,
                        decision={'policy_note': 'Уточнить смену'}, reason='Учебное уточнение')

    v4(monkeypatch, app, Provider)
    with closing(admin.chief if address is None else login_user(address)) as engineer:
        chat = thread(engineer)
        try:
            result = send(engineer, chat, f'Подготовь черновик {identity}, строка {row}: уточнить смену.')
            proposals = [a for a in result['actions'] if a['tool_name'] == 'catalog_decision']
            assert admin.get(url).json()['revision'] == 1
            if role == 'executor':
                assert available and not any(available)
                assert not proposals
                return
            assert available and all(available)
            action, = proposals
            assert action['status'] == 'proposed' and action['arguments']['body']['confirm'] is False
            endpoint = f"{B}/actions/{action['action_id']}/confirm"
            confirmation = {'payload_sha256': action['payload_sha256'], 'confirmed': True}
            assert admin.post(endpoint, json=confirmation).status_code == 404
            response = engineer.post(endpoint, json=confirmation)
            assert response.status_code == 200 and response.json()['status'] == 'succeeded', response.text
            assert response.json()['result']['verification']['status'] == 'confirmed'
            replay = engineer.post(endpoint, json=confirmation)
            assert replay.status_code == 200 and replay.json()['status'] == 'succeeded'
            saved = engineer.get(url).json()
            assert saved['revision'] == 2 and not saved['confirmed']
            assert saved['decision']['policy_note'] == 'Уточнить смену'
            assert saved['decision']['semantics_note'] == 'Сохранённая заметка'

            result = send(engineer, chat, f'Снова подготовь черновик {identity}, строка {row}.')
            stale = next(a for a in result['actions'] if a['status'] == 'proposed')
            assert write(admin, identity, row, {'policy_note': 'Другая правка'}, 2).status_code == 200
            denied = engineer.post(f"{B}/actions/{stale['action_id']}/confirm",
                                   json={'payload_sha256': stale['payload_sha256'], 'confirmed': True})
            assert denied.status_code == 409, denied.text
            latest = engineer.get(url).json()
            assert latest['revision'] == 3 and latest['decision']['policy_note'] == 'Другая правка'
        finally:
            assert engineer.delete(f'{B}/conversations/{chat}').status_code == 200


@pytest.mark.parametrize('kind', ['parent', 'calendar'])
def test_v4_catalog_draft_applies_typed_partial_values_to_the_saved_row(managed, monkeypatch, kind):
    _, app, admin, _, _ = managed
    identity, rows, _ = catalog(admin)
    row = rows[0]
    url = f'{API}/catalog-imports/{identity}/operations/{row}/decision'
    if kind == 'parent':
        previous = dict(frequency_kind='included_in', included_in_row=rows[1])
        changes = dict(included_in_row=rows[2])
    else:
        previous = dict(frequency_kind='week')
        changes = dict(calendar_pattern=dict(frequency='week', anchor_date='2026-11-27'))
    assert write(admin, identity, row, previous).status_code == 200
    monkeypatch.setenv('FIXRATE_PERMISSION_PROFILE', 'mvp')

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'tool':
                return dict(content='Изменение не подготовлено.')
            return call('propose_catalog_draft', catalog_id=identity, row_number=row,
                        decision=changes, reason='Явная учебная правка')

    v4(monkeypatch, app, Provider)
    client = admin.chief
    chat = thread(client)
    try:
        result = send(client, chat, f'Подготовь черновик каталога {identity}, строка {row}: {changes}.')
        action, = [a for a in result['actions'] if a['tool_name'] == 'catalog_decision']
        response = client.post(f"{B}/actions/{action['action_id']}/confirm",
                               json={'payload_sha256': action['payload_sha256'], 'confirmed': True})
        assert response.status_code == 200 and response.json()['status'] == 'succeeded', response.text
        saved = client.get(url).json()
        assert saved['revision'] == 2 and not saved['confirmed']
        assert saved['decision']['frequency_kind'] == previous['frequency_kind']
        if kind == 'parent':
            assert saved['decision']['included_in_row'] == rows[2]
        else:
            assert saved['decision']['calendar_pattern']['interval'] == 1
            assert saved['decision']['calendar_pattern']['anchor_date'] == '2026-11-27'
    finally:
        assert client.delete(f'{B}/conversations/{chat}').status_code == 200
