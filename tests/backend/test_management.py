"""Real PostgreSQL/HTTP coverage of the adapted backend and flexible settings."""
from contextlib import closing
from datetime import date,datetime,timedelta,timezone
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from tests.backend.test_runtime_integration import runtime,PREFIX


@pytest.fixture
def managed(runtime):
    engine,app=runtime
    site,user,system=uuid4(),uuid4(),uuid4()
    marker=uuid4().hex
    email=f'management-{marker}@example.test'
    with engine.begin() as c:
        password=c.scalar(text("SELECT password_hash FROM users WHERE email='fixrate-demo-admin@example.test'"))
        c.execute(text("INSERT INTO sites(site_id,name) VALUES (:id,:name)"),dict(id=site,name='Managed test '+marker))
        c.execute(text('INSERT INTO users(user_id,full_name,email,password_hash) VALUES (:id,:name,:email,:password)'),dict(id=user,name='Managed admin',email=email,password=password))
        c.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,'admin')"),dict(site=site,user=user))
        c.execute(text("INSERT INTO engineering_systems(system_id,site_id,code,name) VALUES (:id,:site,'MANAGED','Managed system')"),dict(id=system,site=site))
        typ=c.scalar(text('SELECT equipment_type_id FROM equipment_types LIMIT 1'))
    def login(address):
        client=TestClient(app)
        response=client.post('/api/v1/auth/login',json=dict(email=address,password=os.environ['FIXRATE_TEST_PASSWORD']))
        assert response.status_code==200,response.text
        client.headers['X-CSRF-Token']=response.json()['csrfToken']
        return client
    admin=login(email)
    try:
        chief_id=uuid4();chief_email=f"chief-{marker}@example.test"
        with engine.begin() as c:
            c.execute(text("INSERT INTO users(user_id,full_name,email,password_hash) VALUES (:id,'Test chief',:email,:password)"),dict(id=chief_id,email=chief_email,password=password))
            c.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:id,'chief_engineer')"),dict(site=site,id=chief_id))
        admin.chief=login(chief_email)
        yield engine,app,admin,login,dict(site=site,system=system,type=typ,marker=marker,user=user)
    finally:
        if hasattr(admin,"chief"):admin.chief.close()
        admin.close()
        with engine.begin() as c:
            users=list(c.scalars(text('SELECT user_id FROM site_memberships WHERE site_id=:site UNION SELECT user_id FROM employment_applications WHERE site_id=:site'),dict(site=site)))
            for table in ['maintenance_notifications','planning_runs','evidence_files','checklist_results','work_readings','acceptance_reviews','ai_quality_checks','work_reports','work_assignments','work_order_equipment','work_orders','schedule_entries','schedule_plans','incident_reports','orchestration_decisions','forecast_runs','rule_equipment','rule_required_skills','maintenance_rules','checklist_templates','regulation_editions','regulation_documents','operation_templates','equipment','engineering_systems','crew_members','crews','availability_slots','employee_shift_rules','user_skills','employment_applications','site_join_codes','fixrate_sessions','audit_events','site_memberships']:
                c.execute(text(f'DELETE FROM {table} WHERE site_id=:site'),dict(site=site))
            c.execute(text('DELETE FROM sites WHERE site_id=:site'),dict(site=site))
            for identity in users: c.execute(text('DELETE FROM users WHERE user_id=:id'),dict(id=identity))


def join(managed,role='executor'):
    engine,app,admin,login,ids=managed
    code=admin.post(PREFIX+'/management/enrollment').json()['code']
    address=f'worker-{uuid4().hex}@example.test'
    response=admin.post('/api/v1/auth/register',json=dict(full_name='Managed worker',email=address,password=os.environ['FIXRATE_TEST_PASSWORD'],company_code=code))
    assert response.status_code==201,response.text
    requests=admin.get(PREFIX+'/management/workforce').json()['applications']
    request=next(r for r in requests if r['email']==address)
    response=admin.post(PREFIX+f"/management/applications/{request['application_id']}/decision",json=dict(expected_revision=1,role=role,is_active=True,employed_from=date.today().isoformat()))
    assert response.status_code==200,response.text
    return request['user_id'],address


def equipment(admin,ids):
    response=admin.post(PREFIX+'/equipment',json=dict(system_id=str(ids['system']),equipment_type_id=str(ids['type']),asset_code='WEB-'+ids['marker'],name='Managed pump',commissioned_on=date.today().isoformat()))
    assert response.status_code==201,response.text
    return response.json()


def config(day,**values):
    return dict(code='WEB-SERVICE',title='Configured maintenance',instructions='Inspect configured pump',maintenance_type='ТО2',
        pattern=dict(frequency='dates',anchor_date=day.isoformat(),dates=[day.isoformat()],weekend_policy='none'),valid_from=day.isoformat(),crew_size=2,
        norm_value='2.000',norm_unit='person_hour',duration_minutes=60,qualification_ids=[],checklist=[dict(text='Inspect pump')],allowed_lead_days=0,enabled=True,methodology_ref='TEST ONLY: approved fixture methodology') | values


def test_registration_waits_for_role_and_rejects_privilege_injection(managed):
    _,app,admin,login,ids=managed
    code=admin.post(PREFIX+'/management/enrollment').json()['code']
    address=f'worker-{uuid4().hex}@example.test'
    payload=dict(full_name='Registered worker',email=address,password=os.environ['FIXRATE_TEST_PASSWORD'],company_code=code)
    invalid=admin.post('/api/v1/auth/register',json=dict(payload,role='admin'))
    assert invalid.status_code==422 and invalid.json()['error']['code']=='VALIDATION_ERROR'
    assert invalid.json()['error']['request_id']==invalid.headers['X-Request-ID']
    assert invalid.json()['error']['details'][0]['field']=='body.role'
    assert admin.post('/api/v1/auth/register',json=payload).status_code==201
    assert TestClient(app).post('/api/v1/auth/login',json=dict(email=address,password=os.environ['FIXRATE_TEST_PASSWORD'])).status_code==403
    assert admin.post('/api/v1/auth/register',json=payload).status_code==409
    request=admin.get(PREFIX+'/management/workforce').json()['applications'][0]
    approve=admin.post(PREFIX+f"/management/applications/{request['application_id']}/decision",json=dict(expected_revision=1,role='executor',is_active=True))
    assert approve.status_code==200,approve.text
    with closing(login(address)) as worker:
        assert worker.get('/api/v1/auth/session').json()['profile']['role']=='executor'
        assert worker.get(PREFIX+'/management/workforce').status_code==403
        assert worker.get(PREFIX+'/users').status_code==403
        assert worker.get(PREFIX+'/users/me').status_code==200


def test_equipment_crud_has_real_scope_role_csrf_and_revision_checks(managed):
    _,app,admin,login,ids=managed
    eq=equipment(admin,ids)
    edit={k:eq[k] for k in ('system_id','equipment_type_id','asset_code','name','commissioned_on','location','serial_number','parent_equipment_id','status')}
    edit.update(expected_revision=1,name='Renamed pump')
    response=admin.patch(PREFIX+f"/equipment/{eq['equipment_id']}",json=edit)
    assert response.status_code==200 and response.json()['revision']==2,response.text
    assert admin.patch(PREFIX+f"/equipment/{eq['equipment_id']}",json=edit).status_code==409
    assert admin.patch(PREFIX+f"/equipment/{eq['equipment_id']}",json=dict(edit,expected_revision=2),headers={'X-CSRF-Token':'bad'}).status_code==403
    partial=admin.patch(PREFIX+f"/equipment/{eq['equipment_id']}",json=dict(expected_revision=2,name='Partially edited',properties={'manufacturer':'Example','data_origin':'customer'}))
    assert partial.status_code==200 and partial.json()['asset_code']==eq['asset_code'],partial.text
    assert partial.json()['properties']['manufacturer']=='Example' and partial.json()['revision']==3
    user,address=join(managed)
    with closing(login(address)) as worker:
        assert worker.get(PREFIX+f"/equipment/{eq['equipment_id']}").status_code==404
        assert worker.post(PREFIX+'/equipment',json={k:v for k,v in edit.items() if k!='expected_revision'}).status_code==403
    assert admin.delete(PREFIX+f"/equipment/{eq['equipment_id']}?expected_revision=3").status_code==204
    assert admin.get(PREFIX+f"/equipment/{eq['equipment_id']}").json()['status']=='retired'


def test_configured_calendar_shifts_proposal_confirmation_and_conflict_protection(managed):
    engine,_,admin,login,ids=managed
    eq=equipment(admin,ids)
    day=date.today()+timedelta(days=1)
    people=[join(managed) for _ in range(3)]
    skill=admin.post(PREFIX+'/management/skills',json=dict(code='PERMIT-'+ids['marker'],name='Configured permit',validity_required=True)).json()['id']
    for identity,_ in people:
        qualified=admin.put(PREFIX+f'/management/staff/{identity}/qualifications/{skill}',json=dict(verified_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),valid_until=(day+timedelta(days=30)).isoformat()))
        assert qualified.status_code==200,qualified.text
    crew=admin.post(PREFIX+'/management/crews',json=dict(name='Existing permanent team',members=[dict(user_id=person[0],valid_from=date.today().isoformat()) for person in people[:2]]))
    assert crew.status_code==201,crew.text
    for identity,_ in people:
        response=admin.post(PREFIX+f'/management/staff/{identity}/shifts',json=dict(label='Day shift',pattern=dict(frequency='week',anchor_date=date.today().isoformat(),weekdays=[1,2,3,4,5,6,7]),valid_from=date.today().isoformat(),starts_local='09:00',ends_local='17:00'))
        assert response.status_code==201,response.text
    off=admin.post(PREFIX+f'/management/staff/{people[0][0]}/availability',json=dict(start_local=f'{day}T09:00',end_local=f'{day}T10:00',status='unavailable',reason='Time off'))
    assert off.status_code==201,off.text
    configured=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(day,qualification_ids=[skill]))
    assert configured.status_code==201,configured.text
    dispatcher,address=join(managed,'dispatcher')
    with closing(login(address)) as dispatch:
        preview=dispatch.get(PREFIX+f'/ui/calendar/preview?year={day.year}&month={day.month}')
        assert preview.status_code==200,preview.text
        assert len(preview.json()['items'])==1,preview.text
        request=dict(year=day.year,month=day.month,preview_token=preview.json()['generationToken'],idempotency_key=str(uuid4()))
        generated=dispatch.post(PREFIX+'/calendar/generate',json=request)
        assert generated.status_code==200,generated.text
        row=generated.json()['items'][0]
        assert len(row['assignment']['selectedWorkers'])==2 and row['assignment']['startAt'].endswith('09:00:00+05:00')
        with engine.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM work_assignments WHERE work_order_id=:id'),dict(id=row['taskId']))==0
        manual=dispatch.post(PREFIX+f"/tasks/{row['taskId']}/assignment-preview",json=dict(expected_revision=1,start_local=f'{day}T09:00',end_local=f'{day}T17:00',executor_ids=[p[0] for p in people[:2]],individual_only=True))
        assert manual.status_code==200 and manual.json()['status']=='ok',manual.text
        assert manual.json()['startAt'].endswith('10:00:00+05:00')
        assert manual.json()['crewId'] is None
        selected=manual.json()
        saved=dispatch.post(PREFIX+f"/tasks/{row['taskId']}/assign",json=dict(selected['command'],crew_id=selected['crewId']))
        assert saved.status_code==200,saved.text
        assert saved.json()['task']['revision']==2 and len(saved.json()['task']['assignees'])==2
        revoke_path=PREFIX+f'/management/staff/{people[0][0]}/qualifications/{skill}/revoke'
        assert admin.post(revoke_path,json=dict(expected_revision=1)).status_code==409
        block=admin.post(PREFIX+f'/management/staff/{people[0][0]}/availability',json=dict(start_local=f'{day}T10:00',end_local=f'{day}T11:00',status='unavailable',reason='Conflicting absence'))
        assert block.status_code==409,block.text
        newer=config(day+timedelta(days=1),expected_revision=1,operation_id=configured.json()['operation_id'])
        changed=admin.chief.put(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations/{configured.json()['binding_id']}",json=newer)
        assert changed.status_code==200,changed.text
        persisted=dispatch.get(PREFIX+f"/ui/tasks/{row['taskId']}").json()['task']
        assert persisted['revision']==2 and len(persisted['assignees'])==2
        cancellation=dict(expected_revision=2,reason='Replace future service configuration')
        assert admin.post(PREFIX+f"/tasks/{row['taskId']}/cancel",json=cancellation).status_code==403
        cancelled=dispatch.post(PREFIX+f"/tasks/{row['taskId']}/cancel",json=cancellation)
        assert cancelled.status_code==200,cancelled.text
        assert cancelled.json()['task']['state']=='cancelled' and cancelled.json()['task']['revision']==3
        revoked=admin.post(revoke_path,json=dict(expected_revision=1))
        assert revoked.status_code==200 and revoked.json()['revision']==2,revoked.text
        assert admin.post(revoke_path,json=dict(expected_revision=1)).status_code==409
        assert dispatch.post(PREFIX+f"/tasks/{row['taskId']}/cancel",json=cancellation).status_code==409
        with engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM work_assignments WHERE work_order_id=:id AND status='cancelled' AND released_at IS NOT NULL"),dict(id=row['taskId']))==2


def test_last_admin_and_stale_staff_edit_are_protected(managed):
    _,_,admin,_,ids=managed
    command=dict(expected_revision=1,role='executor',is_active=True)
    assert admin.put(PREFIX+f"/management/staff/{ids['user']}",json=command).status_code==409
    identity,_=join(managed)
    response=admin.put(PREFIX+f'/management/staff/{identity}',json=dict(command,role='engineer'))
    assert response.status_code==200,response.text
    assert admin.put(PREFIX+f'/management/staff/{identity}',json=command).status_code==409


def test_crew_membership_is_independent_from_shifts_and_individual_assignment(managed):
    _,_,admin,_,_=managed
    identities=[join(managed)[0] for _ in range(2)]
    body=dict(name='Configured crew',members=[dict(user_id=i,valid_from=date.today().isoformat()) for i in identities])
    created=admin.post(PREFIX+'/management/crews',json=body)
    assert created.status_code==201,created.text
    team=admin.get(PREFIX+'/management/workforce').json()
    assert len(team['crews'][0]['members'])==2
    assert all(not person['shifts'] for person in team['staff'] if person['user_id'] in identities)
    assert admin.put(PREFIX+f"/management/crews/{created.json()['id']}",json=dict(body,expected_revision=1,name='Updated crew')).status_code==200


def test_shared_operation_keeps_per_equipment_versions_and_typed_checklists(managed):
    _,_,admin,login,ids=managed
    first=equipment(admin,ids)
    second=equipment(admin,dict(ids,marker=ids['marker']+'-2'))
    day=date.today()+timedelta(days=2)
    first_config=admin.chief.post(PREFIX+f"/equipment/{first['equipment_id']}/service-configurations",json=config(day,
        title='First equipment service',checklist=[dict(text='Pressure',answer_kind='number',unit='bar',required=True,photo_required=True,visual_verifiability='partial')]))
    assert first_config.status_code==201,first_config.text
    op=first_config.json()['operation_id']
    second_config=admin.chief.post(PREFIX+f"/equipment/{second['equipment_id']}/service-configurations",json=config(day,
        operation_id=op,title='Second equipment service',norm_value='3.250',checklist=[dict(text='Describe condition',answer_kind='text',required=False)]))
    assert second_config.status_code==201,second_config.text
    assert second_config.json()['operation_id']==op
    for eq,title,kind in [(first,'First equipment service','number'),(second,'Second equipment service','text')]:
        row=admin.get(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations").json()[0]
        assert row['title']==title and row['checklist'][0]['answer_kind']==kind
    _,address=join(managed,'dispatcher')
    with closing(login(address)) as dispatch:
        preview=dispatch.get(PREFIX+f'/ui/calendar/preview?year={day.year}&month={day.month}').json()
        assert {row['operationTitle'] for row in preview['items']}=={'First equipment service','Second equipment service'}
        generated=dispatch.post(PREFIX+'/calendar/generate',json=dict(year=day.year,month=day.month,preview_token=preview['generationToken'],idempotency_key=str(uuid4())))
        assert generated.status_code==200,generated.text
        saved=dispatch.get(PREFIX+f'/ui/calendar?year={day.year}&month={day.month}').json()
        assert {row['operationTitle'] for row in saved}=={'First equipment service','Second equipment service'}
