"""QA02: real ASGI HTTP + disposable PostgreSQL; no mock role directory.

Requires the isolated database provisioned by scripts/verify.py. Standalone pytest
without INTEGRATION_DATABASE_URL skips this module's runtime fixture explicitly.
"""
from contextlib import closing
from datetime import date, timedelta
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from tests.backend.test_runtime_integration import runtime, PREFIX
from tests.backend.test_management import managed, equipment, join, config


def service_state(engine, site):
    values={}
    for table,pk in [('maintenance_rules','maintenance_rule_id'),('rule_equipment','binding_id'),
                     ('operation_templates','operation_template_id'),('audit_events','audit_event_id')]:
        with engine.connect() as connection:
            values[table]=connection.scalar(text(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY {pk}), '[]'::jsonb) FROM {table} t WHERE site_id=:site"),{'site':site})
    return values


@pytest.mark.parametrize('role',['engineer','executor'])
@pytest.mark.parametrize('method',['POST','PUT'])
def test_qa02_forbidden_service_edits_leave_database_unchanged(managed,role,method):
    engine,app,admin,login,ids=managed
    eq=equipment(admin,ids)
    day=date.today()+timedelta(days=1)
    url=PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations"
    created=admin.chief.post(url,json=config(day))
    assert created.status_code==201,created.text
    _,address=join(managed,role)
    with closing(login(address)) as client:
        read=client.get(url)
        assert read.status_code==(200 if role=='engineer' else 404)
        before=service_state(engine,ids['site'])
        target=url if method=='POST' else url+'/'+created.json()['binding_id']
        response=client.request(method,target,json=config(day,expected_revision=1,title='Forbidden change'))
        assert response.status_code==403,response.text
        assert response.json()['error']['code']=='ACCESS_DENIED'
        assert response.json()['error']['request_id']==response.headers['X-Request-ID']
        assert service_state(engine,ids['site'])==before


@pytest.mark.parametrize('identity',['role','user_id','assigned_by'])
def test_qa02_real_login_dto_rejects_client_identity(managed,identity):
    _,app,admin,_,_=managed
    profile=admin.get('/api/v1/auth/session').json()['profile']
    payload={'email':profile['email'],'password':os.environ['FIXRATE_TEST_PASSWORD'],
             identity:'engineer' if identity=='role' else str(uuid4())}
    with closing(TestClient(app)) as anonymous:
        response=anonymous.post('/api/v1/auth/login',json=payload)
        assert response.status_code==422,response.text
        assert response.json()['error']['code']=='VALIDATION_ERROR'
        assert any(detail['field']=='body.'+identity for detail in response.json()['error']['details'])
        assert anonymous.get('/api/v1/auth/session').status_code==401


@pytest.mark.parametrize('mode',['expired','disabled_user','disabled_membership','disabled_site'])
def test_qa02_invalid_principal_cannot_read_or_mutate_with_forged_role_header(managed,mode):
    engine,app,admin,_,ids=managed
    if mode=='expired':
        table,column,predicate='fixrate_sessions','expires_at','user_id=:identity'
        identity=ids['user'];replacement="now()-interval '1 second'"
    elif mode=='disabled_user':
        table,column,predicate='users','is_active','user_id=:identity'
        identity=ids['user'];replacement='false'
    elif mode=='disabled_membership':
        table,column,predicate='site_memberships','is_active','user_id=:identity AND site_id=:site'
        identity=ids['user'];replacement='false'
    else:
        table,column,predicate='sites','is_active','site_id=:identity'
        identity=ids['site'];replacement='false'
    params={'identity':identity,'site':ids['site']}
    with engine.begin() as connection:
        original=connection.scalar(text(f'SELECT {column} FROM {table} WHERE {predicate}'),params)
        connection.execute(text(f'UPDATE {table} SET {column}={replacement} WHERE {predicate}'),params)
    try:
        for response in [admin.get(PREFIX+'/ui/tasks',headers={'X-Role':'admin','X-User-Id':str(ids['user'])}),
                         admin.post(PREFIX+'/calendar/generate',json={'year':2026,'month':11,'idempotency_key':str(uuid4()),'preview_token':'a'*64},headers={'X-Role':'admin'})]:
            assert response.status_code==401,response.text
            assert response.json()['error']['code']=='UNAUTHENTICATED'
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'UPDATE {table} SET {column}=:original WHERE {predicate}'),dict(params,original=original))


def test_qa02_unknown_session_token_cannot_be_replaced_by_identity_headers(managed):
    _,app,_,_,ids=managed
    with closing(TestClient(app)) as anonymous:
        anonymous.cookies.set('fixrate_session','qa02-invalid-token')
        response=anonymous.get(PREFIX+'/ui/tasks',headers={'X-Role':'admin','X-User-Id':str(ids['user'])})
        assert response.status_code==401
        assert response.json()['error']['code']=='UNAUTHENTICATED'
