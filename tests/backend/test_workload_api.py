"""Real HTTP/PostgreSQL checks on dedicated TEST objects, never customer records."""
from contextlib import closing
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.backend.test_management import managed, join, equipment, config
from tests.backend.test_runtime_integration import runtime, login, PREFIX


def test_to3_and_full_day_shift_feed_a_read_only_workload_calculation(managed):
    engine, app, admin, login_user, ids = managed
    person, email = join(managed)
    day = date.today() + timedelta(days=7)
    eq = equipment(admin, ids)
    response = admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",
        json=config(day, maintenance_type='ТО3', norm_value='40', duration_minutes=1200))
    assert response.status_code == 201, response.text
    shift = dict(label='TEST 24 hours', pattern=dict(frequency='dates', anchor_date=day.isoformat(), dates=[day.isoformat()]),
        valid_from=day.isoformat(), starts_local='00:00', ends_local='00:00')
    response = admin.post(PREFIX+f'/management/staff/{person}/shifts', json=shift)
    assert response.status_code == 201, response.text
    with engine.connect() as conn:
        before = {table: conn.scalar(text(f'SELECT count(*) FROM {table} WHERE site_id=:site'), ids)
                  for table in ('work_orders', 'work_assignments', 'schedule_plans', 'planning_runs')}
    response = admin.get(PREFIX+f'/planning/workload?year={day.year}&month={day.month}')
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    data = response.json()
    row = next(r for r in data['days'] if r['date'] == day.isoformat())
    assert row['total_person_hours'] == '40.000' or row['total_person_hours'] == '40'
    assert row['required_workers_lower_bound'] == 2
    assert float(row['free_person_hours']) == 24
    assert float(row['deficit_person_hours']) == 16
    assert row['status'] == 'hours_deficit' and len(data['snapshot_sha256']) == 64
    half = admin.get(PREFIX+f'/planning/workload?year={day.year}&month={day.month}&capacity_hours_per_24h=12')
    assert half.status_code == 200, half.text
    assert half.json()['days'][day.day-1]['required_workers_lower_bound'] == 4
    with closing(login_user(email)) as executor:
        assert executor.get(PREFIX+f'/planning/workload?year={day.year}&month={day.month}').status_code == 403
    with engine.connect() as conn:
        after = {table: conn.scalar(text(f'SELECT count(*) FROM {table} WHERE site_id=:site'), ids) for table in before}
    assert before == after
    calendar = admin.chief.get(PREFIX+f'/ui/calendar/preview?year={day.year}&month={day.month}').json()
    assert any(item['maintenanceType'] == 'ТО3' for item in calendar['items'])


@pytest.mark.parametrize('query', ['year=1999&month=1', 'year=2027&month=13',
    'year=2027&month=1&capacity_hours_per_24h=0', 'year=2027&month=1&capacity_hours_per_24h=25',
    'year=2027&month=1&capacity_hours_per_24h=NaN', 'year=2027&month=1&capacity_hours_per_24h=1.0001'])
def test_invalid_workload_query_is_rejected(managed, query):
    _, _, admin, _, _ = managed
    assert admin.get(PREFIX+'/planning/workload?'+query).status_code == 422


@pytest.mark.parametrize('role', ['director', 'chief_engineer', 'engineer', 'dispatcher', 'admin'])
def test_workload_read_role_matrix(runtime, role):
    _, app = runtime
    with closing(login(app, role)) as client:
        response = client.get(PREFIX+'/planning/workload?year=2027&month=1')
        assert response.status_code == 200, response.text


def test_full_day_shift_still_blocks_overlaps_on_other_objects(managed):
    engine, _, admin, _, ids = managed
    person, _ = join(managed)
    day = date.today() + timedelta(days=7)
    eq = equipment(admin, ids)
    response = admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",
        json=config(day, norm_value='24', crew_size=1, duration_minutes=1440))
    assert response.status_code == 201, response.text
    shift = admin.post(PREFIX+f'/management/staff/{person}/shifts', json=dict(label='TEST shift',
        pattern=dict(frequency='dates', anchor_date=day.isoformat(), dates=[day.isoformat()]),
        valid_from=day.isoformat(), starts_local='00:00', ends_local='00:00'))
    assert shift.status_code == 201, shift.text
    # A reservation on another object consumes this person's time globally.
    with engine.begin() as conn:
        foreign = conn.execute(text("SELECT site_id,work_order_id FROM work_orders WHERE site_id<>:site AND status IN ('draft','assigned') LIMIT 1"), ids).one()
        conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:person,'executor')"),
                     dict(site=foreign.site_id, person=person))
        conn.execute(text("INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at) "
            "SELECT :site,:job,:person,user_id,CAST(:begin AS timestamptz),CAST(:finish AS timestamptz) "
            "FROM site_memberships WHERE site_id=:site ORDER BY (role='dispatcher') DESC LIMIT 1"),
            dict(site=foreign.site_id, job=foreign.work_order_id, person=person,
                 begin=f'{day}T00:00:00+05:00', finish=f'{day+timedelta(days=1)}T00:00:00+05:00'))
    try:
        response = admin.get(PREFIX+f'/planning/workload?year={day.year}&month={day.month}')
        assert response.status_code == 200, response.text
        row = response.json()['days'][day.day-1]
        assert float(row['free_person_hours']) == 0 and float(row['deficit_person_hours']) == 24
        assert str(foreign.work_order_id) not in response.text
    finally:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM work_assignments WHERE user_id=:id AND site_id=:site'), dict(id=person, site=foreign.site_id))
            conn.execute(text('DELETE FROM site_memberships WHERE user_id=:id AND site_id=:site'), dict(id=person, site=foreign.site_id))


def test_existing_assignment_without_source_id_is_accounted_for_once(managed):
    engine, _, admin, _, ids = managed
    person, _ = join(managed)
    day = date.today() + timedelta(days=7)
    eq = equipment(admin, ids)
    saved = admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",
        json=config(day, crew_size=1, norm_value='1', duration_minutes=60))
    assert saved.status_code == 201, saved.text
    shift = admin.post(PREFIX+f'/management/staff/{person}/shifts', json=dict(label='TEST full day',
        pattern=dict(frequency='dates', anchor_date=day.isoformat(), dates=[day.isoformat()]),
        valid_from=day.isoformat(), starts_local='00:00', ends_local='00:00'))
    assert shift.status_code == 201, shift.text
    preview = admin.chief.get(PREFIX+f'/ui/calendar/preview?year={day.year}&month={day.month}').json()
    generated = admin.chief.post(PREFIX+'/calendar/generate', json=dict(year=day.year, month=day.month,
        preview_token=preview['generationToken'], idempotency_key=str(uuid4())))
    assert generated.status_code == 200, generated.text
    item = generated.json()['items'][0]
    assert item['assignment']['status'] == 'ok'
    assigned = admin.chief.post(PREFIX+f"/tasks/{item['taskId']}/assign", json=item['assignment']['command'])
    assert assigned.status_code == 200, assigned.text
    with engine.begin() as conn:
        conn.execute(text('UPDATE schedule_entries SET source_occurrence_id=NULL WHERE site_id=:site'), ids)
        conn.execute(text('UPDATE maintenance_rules SET norm_hours=99 WHERE site_id=:site'), ids)
    response = admin.get(PREFIX+f'/planning/workload?year={day.year}&month={day.month}')
    assert response.status_code == 200, response.text
    row = response.json()['days'][day.day-1]
    assert len(row['occurrences']) == 1 and row['occurrences'][0]['state'] == 'assigned'
    assert float(row['total_person_hours']) == 1  # The saved job keeps its original norm.
    assert float(row['unassigned_person_hours']) == 0 and row['assigned_workers'] == 1
    assert float(row['free_person_hours']) == 23 and float(row['deficit_person_hours']) == 0
