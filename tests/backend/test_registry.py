"""Registry behavior on real PostgreSQL, including history, access and rollback."""
from datetime import date, datetime, timedelta, timezone
from contextlib import closing
import io
import json
import os
from uuid import uuid4
from PIL import Image
from sqlalchemy import text
from fastapi.testclient import TestClient
from tests.backend.test_management import managed, equipment as create_equipment, join
from tests.backend.test_runtime_integration import runtime, PREFIX


def equipment(admin, ids):
    row = create_equipment(admin, ids)
    response = admin.patch(f"{PREFIX}/equipment/{row['equipment_id']}", json=dict(expected_revision=1, commissioned_on=(date.today()-timedelta(days=30)).isoformat()))
    assert response.status_code == 200, response.text
    return response.json()


def part(**overrides):
    return dict(position_code='bearing-1', name='Подшипник', installed_on=(date.today()-timedelta(days=3)).isoformat(),
        usage_unit='hour', initial_usage='100', resource_limit='1000', resource_basis='Паспорт детали, раздел 4') | overrides


def install(admin, eq, **overrides):
    response = admin.post(f"{PREFIX}/equipment/{eq['equipment_id']}/components", json=part(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def reading(admin, item, value='120', **overrides):
    payload = dict(expected_revision=item['revision'], measured_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(), usage_value=value, note='Проверено по журналу') | overrides
    return admin.post(f"{PREFIX}/registry/components/{item['component_id']}/readings", data={'payload': json.dumps(payload)})


def test_registry_groups_do_not_guess_or_lose_existing_systems(managed):
    _, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    result = admin.get(PREFIX+'/registry')
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'private, no-store'
    assert result.json()['systems'][0]['system_group'] is None
    assert result.json()['items'][0]['equipment_id'] == eq['equipment_id']
    path = f"{PREFIX}/registry/systems/{ids['system']}"
    response = admin.chief.patch(path, json=dict(expected_revision=1, system_group='water'))
    assert response.status_code == 200, response.text
    assert admin.chief.patch(path, json=dict(expected_revision=1, system_group='air')).status_code == 409
    assert admin.get(PREFIX+'/registry').json()['systems'][0]['system_group'] == 'water'
    assert admin.patch(path, json=dict(expected_revision=2, system_group='wrong')).status_code == 422


def test_parts_require_resource_basis_and_unique_active_position(managed):
    _, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    assert admin.post(f"{PREFIX}/equipment/{eq['equipment_id']}/components", json=part(resource_basis=None)).status_code == 422
    item = install(admin, eq)
    assert item['current_usage'] == '100.000' and item['remaining_usage'] == '900.000'
    assert admin.post(f"{PREFIX}/equipment/{eq['equipment_id']}/components", json=part()).status_code == 409
    unknown = install(admin, eq, position_code='unknown', resource_limit=None, resource_basis=None)
    assert unknown['remaining_usage'] is None and unknown['resource_state'] == 'unknown'


def test_usage_is_append_only_revision_checked_and_resource_units_preserved(managed):
    _, _, admin, _, ids = managed
    item = install(admin, equipment(admin, ids), usage_unit='cycle')
    result = reading(admin, item, '1100')
    assert result.status_code == 201, result.text
    updated = result.json()
    assert updated['remaining_usage'] == '0.000' and updated['resource_state'] == 'exhausted'
    assert updated['usage_unit'] == 'cycle' and len(updated['readings']) == 1
    assert reading(admin, item).status_code == 409
    assert reading(admin, updated, '1099', measured_at=datetime.now(timezone.utc).isoformat()).status_code == 422
    assert reading(admin, updated, '1101', measured_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()).status_code == 422
    assert reading(admin, updated, '1101', measured_at=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()).status_code == 422


def test_resource_can_be_confirmed_later_without_resetting_usage(managed):
    _,_,admin,_,ids=managed
    item=install(admin,equipment(admin,ids),resource_limit=None,resource_basis=None)
    item=reading(admin,item,'150').json()
    path=f"{PREFIX}/registry/components/{item['component_id']}"
    body=dict(expected_revision=item['revision'],name=item['name'],resource_limit='1000',resource_basis='Подтверждённый паспорт')
    assert admin.patch(path,json=body|dict(resource_basis=None)).status_code==422
    updated=admin.patch(path,json=body)
    assert updated.status_code==200,updated.text
    assert updated.json()['current_usage']=='150.000' and updated.json()['remaining_usage']=='850.000'
    assert len(updated.json()['readings'])==1


def test_replacement_is_atomic_and_retains_old_part_readings(managed):
    _, _, admin, _, ids = managed
    eq = equipment(admin, ids)
    item = install(admin, eq)
    updated = reading(admin, item).json()
    path = f"{PREFIX}/registry/components/{item['component_id']}/replace"
    command = dict(expected_revision=updated['revision'], removed_on=date.today().isoformat(), reason='Плановая замена',
        replacement=part(installed_on=date.today().isoformat(), initial_usage='0'))
    bad = admin.post(path, json=dict(command, replacement=part(installed_on=(date.today()-timedelta(days=1)).isoformat())))
    assert bad.status_code == 422, bad.text
    unchanged = admin.get(f"{PREFIX}/equipment/{eq['equipment_id']}/components").json()[0]
    assert unchanged['removed_on'] is None and unchanged['revision'] == updated['revision']
    result = admin.post(path, json=command)
    assert result.status_code == 200, result.text
    old, new = result.json()['removed'], result.json()['installed']
    assert old['current_usage'] == '120.000' and len(old['readings']) == 1 and old['resource_state'] == 'removed'
    assert new['current_usage'] == '0.000' and new['component_id'] != old['component_id']
    assert reading(admin, old, '121').status_code == 409
    assert len(admin.get(f"{PREFIX}/equipment/{eq['equipment_id']}/components").json()) == 2


def test_reading_photos_are_private_and_bad_upload_rolls_back(managed):
    _, app, admin, _, ids = managed
    item = install(admin, equipment(admin, ids))
    payload = json.dumps(dict(expected_revision=1, measured_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(), usage_value='120', note='Фото журнала'))
    path = f"{PREFIX}/registry/components/{item['component_id']}/readings"
    assert admin.post(path, data={'payload': payload}, files={'photo': ('bad.jpg', b'bad', 'image/jpeg')}).status_code == 422
    stream = io.BytesIO(); Image.new('RGB', (80, 80), 'white').save(stream, format='PNG')
    result = admin.post(path, data={'payload': payload}, files={'photo': ('reading.png', stream.getvalue(), 'image/png')})
    assert result.status_code == 201, result.text
    url = result.json()['readings'][0]['photo_url']
    assert admin.get(url).content == stream.getvalue()
    assert TestClient(app).get(url).status_code == 401


def test_executor_cannot_see_unassigned_parts_or_modify_structure(managed):
    _, _, admin, login, ids = managed
    eq = equipment(admin, ids); item = install(admin, eq)
    _, address = join(managed)
    with closing(login(address)) as worker:
        assert worker.get(PREFIX+'/registry').status_code == 403
        assert worker.get(f"{PREFIX}/equipment/{eq['equipment_id']}/components").status_code == 404
        assert reading(worker, item).status_code == 404
        assert worker.post(f"{PREFIX}/equipment/{eq['equipment_id']}/components", json=part()).status_code == 403


def test_building_switch_checks_membership_rotates_session_and_changes_scope(managed):
    engine, app, admin, _, ids = managed
    response = admin.post(PREFIX+'/registry/buildings', json=dict(name='Второй корпус', address='Тестовый адрес', timezone='UTC'))
    assert response.status_code == 201, response.text
    site = response.json()['site_id']
    try:
        assert len(admin.get('/api/v1/auth/sites').json()) == 2
        credentials=dict(email=admin.get('/api/v1/auth/session').json()['profile']['email'],password=os.environ['FIXRATE_TEST_PASSWORD'])
        anonymous=TestClient(app)
        assert anonymous.post('/api/v1/auth/sites',json=credentials|dict(password='wrong')).status_code==401
        choices=anonymous.post('/api/v1/auth/sites',json=credentials)
        assert choices.status_code==200 and len(choices.json())==2
        assert all(set(row)=={'site_id','name'} for row in choices.json())
        assert admin.post('/api/v1/auth/site', json=dict(site_id=str(uuid4()))).status_code == 403
        assert admin.post('/api/v1/auth/site', json=dict(site_id=site), headers={'X-CSRF-Token':'wrong'}).status_code == 403
        old = admin.cookies.get('fixrate_session')
        switched = admin.post('/api/v1/auth/site', json=dict(site_id=site))
        assert switched.status_code == 200, switched.text
        assert switched.json()['profile']['siteId'] == site
        assert switched.json()['profile']['timezone'] == 'UTC'
        admin.headers['X-CSRF-Token'] = switched.json()['csrfToken']
        assert admin.get(PREFIX+'/registry').json()['items'] == []
        with closing(TestClient(app)) as stale:
            stale.cookies.set('fixrate_session', old)
            assert stale.get('/api/v1/auth/session').status_code == 401
    finally:
        with engine.begin() as c:
            c.execute(text('DELETE FROM fixrate_sessions WHERE site_id=:s'), dict(s=site))
            c.execute(text('DELETE FROM site_memberships WHERE site_id=:s'), dict(s=site))
            c.execute(text('DELETE FROM sites WHERE site_id=:s'), dict(s=site))
