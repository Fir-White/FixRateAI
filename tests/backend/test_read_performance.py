"""SQL budgets on real PostgreSQL; elapsed-time assertions belong to browser profiling."""
from contextlib import closing
from datetime import date

import pytest
from sqlalchemy import event, text

from tests.backend.test_management import managed, equipment, config
from tests.backend.test_runtime_integration import runtime, login, PREFIX


def counted_get(engine, client, path):
    statements = []
    def count(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(engine, 'before_cursor_execute', count)
    try:
        response = client.get(PREFIX + path)
        assert response.status_code == 200, response.text
        return response.json(), len(statements)
    finally:
        event.remove(engine, 'before_cursor_execute', count)


@pytest.mark.parametrize('path', ['/ui/equipment', '/registry'])
def test_equipment_sql_does_not_grow_per_asset_or_service(managed, path):
    engine, _, admin, _, ids = managed
    first = equipment(admin, ids)
    service = admin.chief.post(PREFIX + f"/equipment/{first['equipment_id']}/service-configurations",
                              json=config(date.today(), enabled=False))
    assert service.status_code == 201, service.text
    _, small_count = counted_get(engine, admin, path)
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO equipment(site_id,system_id,equipment_type_id,asset_code,name)
            SELECT :site,:system,:type,'PERF-'||n,'Performance pump '||n FROM generate_series(1,100) n"""), ids)
        conn.execute(text("""INSERT INTO rule_equipment(site_id,system_id,maintenance_rule_id,equipment_id,valid_from)
            SELECT :site,:system,b.maintenance_rule_id,e.equipment_id,b.valid_from FROM equipment e
            JOIN rule_equipment b ON b.equipment_id=:first AND b.site_id=:site
            WHERE e.site_id=:site AND e.asset_code LIKE 'PERF-%'"""), dict(ids, first=first['equipment_id']))
    data, large_count = counted_get(engine, admin, path)
    rows = data['items'] if path == '/registry' else data
    assert len(rows) == 101
    assert large_count <= small_count + 1
    assert large_count <= 20
    if path == '/registry':
        assert all(len(row['services']) == 1 for row in rows)
        assert all(row['services'][0]['enabled'] is False for row in rows)
    else:
        assert all(row['siteId'] == str(ids['site']) for row in rows)


def test_calendar_sql_is_bounded_and_matches_filtered_persisted_entries(runtime):
    engine, app = runtime
    with closing(login(app, 'chief_engineer')) as client:
        site = client.get('/api/v1/auth/session').json()['profile']['siteId']
        with engine.connect() as conn:
            day = conn.scalar(text('SELECT planned_date FROM schedule_entries WHERE site_id=:site ORDER BY planned_date LIMIT 1'), {'site': site})
        data, count = counted_get(engine, client, f'/ui/calendar?year={day.year}&month={day.month}')
        assert data
        assert count <= 10
        assert all(row['occurrenceDate'][:7] == day.strftime('%Y-%m') or row['sourceDate'][:7] == day.strftime('%Y-%m') for row in data)
