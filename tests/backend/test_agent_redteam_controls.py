"""Real own-chat lifecycle and role boundary checks in a disposable PostgreSQL."""
from contextlib import closing
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime,login
from tests.backend.test_assistant import B,thread,rpc

ROLES=('director','chief_engineer','engineer','dispatcher','admin','executor')

@pytest.mark.parametrize('role',ROLES)
def test_every_role_can_delete_its_own_chat(runtime,role):
    _,app=runtime
    with closing(login(app,role)) as client:
        identity=thread(client)
        response=client.delete(B+'/conversations/'+identity)
        assert response.status_code==200,response.text
        assert response.json()==dict(deleted=True)
        assert client.get(B+'/conversations/'+identity).status_code==404


@pytest.mark.parametrize('role',ROLES)
def test_chat_delete_still_requires_csrf_and_ownership(runtime,role):
    _,app=runtime
    with closing(login(app,role)) as client,closing(login(app,'chief_engineer' if role!='chief_engineer' else 'admin')) as other:
        own=thread(client);foreign=thread(other)
        assert client.delete(B+'/conversations/'+own,headers={'X-CSRF-Token':'wrong'}).status_code==403
        assert client.get(B+'/conversations/'+own).status_code==200
        assert client.delete(B+'/conversations/'+foreign).status_code in (403,404)
        assert other.get(B+'/conversations/'+foreign).status_code==200


@pytest.mark.parametrize('role',ROLES)
def test_claiming_admin_in_headers_does_not_expose_privileged_tools(runtime,role):
    _,app=runtime
    with closing(login(app,role)) as client:
        response=client.post(B+'/mcp',json=dict(jsonrpc='2.0',id=1,method='tools/list',params={}),
                headers={'MCP-Protocol-Version':'2025-06-18','Accept':'application/json, text/event-stream','X-Role':'admin','X-User-Role':'admin'})
        assert response.status_code==200,response.text
        names={t['name'] for t in response.json()['result']['tools']}
        # Only genuine access managers get role-management tools.
        assert ('staff_edit' in names)==(role in ('admin','chief_engineer'))
        assert not any('password' in n for n in names)


def test_unknown_and_url_shaped_tools_never_dispatch(runtime):
    engine,app=runtime
    with closing(login(app,'executor')) as client:
        with engine.connect() as c:before=c.scalar(text('SELECT count(*) FROM work_orders'))
        for name in ('http://127.0.0.1:8000/internal','../../management','sql.execute','confirm_action','password_change','task_assign; DROP TABLE users'):
            response=rpc(client,'tools/call',dict(name=name,arguments={}))
            assert response.status_code==200 and 'error' in response.json(),response.text
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders'))==before


def test_director_chat_exception_does_not_allow_equipment_delete(runtime):
    engine,app=runtime
    with closing(login(app,'director')) as client:
        profile=client.get('/api/v1/auth/session').json()['profile']
        with engine.connect() as c:
            equipment=c.scalar(text('SELECT equipment_id FROM equipment WHERE site_id=:site LIMIT 1'),dict(site=profile['siteId']))
        assert equipment is not None
        response=client.delete('/api/v1/maintenance/equipment/'+str(equipment))
        assert response.status_code==403
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM equipment WHERE equipment_id=:id'),dict(id=equipment))==1
