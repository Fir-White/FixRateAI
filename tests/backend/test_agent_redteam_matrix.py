"""Real MCP -> backend -> PostgreSQL security/contract matrix, not simulated successful results."""
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID,uuid5
import json,os
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime,login
from tests.backend.test_assistant import B,thread,rpc

ROOT=Path(__file__).resolve().parents[2]
CORPUS=json.loads((ROOT/'tests/fixtures/assistant/red_team_cases.json').read_text(encoding='utf-8'))
ROLES=('director','chief_engineer','engineer','dispatcher','admin','executor')
DOMAIN=('sites','users','site_memberships','engineering_systems','equipment','maintenance_rules','rule_equipment',
        'schedule_plans','schedule_entries','work_orders','work_assignments','work_reports','acceptance_reviews',
        'employee_shift_rules','availability_slots','planning_draft_versions','draft_publication_proposals','assistant_actions')

def fingerprint(engine):
    with engine.connect() as db:
        return {table:db.scalar(text("SELECT md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY md5(to_jsonb(t)::text)),'')) FROM "+table+' t')) for table in DOMAIN}

@pytest.fixture(scope='module')
def matrix(runtime):
    engine,app=runtime;clients={};chats={};schemas={}
    for role in ROLES:
        clients[role]=login(app,role);chats[role]=thread(clients[role])
        response=rpc(clients[role],'tools/list')
        assert response.status_code==200,response.text
        schemas[role]={tool['name']:tool for tool in response.json()['result']['tools']}
    out=Path(os.environ.get('FIXRATE_AGENT_AUDIT_OUTPUT',ROOT/'reports/agent-audit-matrix'))
    out.mkdir(parents=True,exist_ok=True)
    try:
        with (out/'capability-matrix.jsonl').open('w',encoding='utf-8') as stream:
            yield engine,app,clients,chats,schemas,stream
    finally:
        for client in clients.values():client.close()

def value_for(schema,key):
    if 'enum' in schema:return schema['enum'][0]
    if 'anyOf' in schema:return value_for(next(v for v in schema['anyOf'] if v.get('type')!='null'),key)
    if schema.get('type')=='integer':return max(1,schema.get('minimum',1))
    if schema.get('format')=='date':return '2030-01-01'
    return str(uuid5(UUID('c163b240-44cc-4d97-8b45-51f491c28b8a'),key))

def references(schema):
    def walk(node):
        if isinstance(node,dict):
            if '$ref' in node:
                ref=node['$ref'];assert ref.startswith('#/'),f'External or unsupported reference {ref}'
                target=schema
                for part in ref[2:].split('/'):
                    key=part.replace('~1','/').replace('~0','~')
                    assert isinstance(target,dict) and key in target,f'Dangling schema reference {ref}'
                    target=target[key]
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(schema)

@pytest.mark.parametrize('case',CORPUS['cases'],ids=[c['id'] for c in CORPUS['cases']])
def test_registered_capability_boundary(matrix,case):
    engine,app,clients,chats,schemas,stream=matrix
    before=fingerprint(engine);start=perf_counter();record={**case,'at':datetime.now(timezone.utc).isoformat(),'llm_called':False,'retries':0}
    try:
        role=case['role'];name=case['tool'];kind=case['kind'];client=clients[role]
        if kind=='schema_refs':
            schema=schemas[role][name]['inputSchema'];references(schema)
            assert schema.get('additionalProperties') is False
            record['schema_checked']=True
        else:
            args={}
            if kind=='invalid_root':args={'audit_unexpected_root':True,'conversation_id':chats[role]}
            elif kind=='foreign_conversation':args={'conversation_id':chats['admin' if role!='admin' else 'chief_engineer']}
            elif kind=='invalid_query':
                path=schemas[role][name]['inputSchema']['properties'].get('path',{})
                args=dict(path={key:value_for(path['properties'][key],key) for key in path.get('required',[])},query={'audit_unknown_filter':True},conversation_id=chats[role])
            response=rpc(client,'tools/call',dict(name=name,arguments=args))
            assert response.status_code==200,response.text
            payload=response.json();record['http']=response.status_code
            record['error']=payload.get('error') or payload.get('result',{}).get('isError')
            assert 'error' in payload or payload.get('result',{}).get('isError') is True,payload
            if kind=='forbidden_role':assert payload.get('error',{}).get('code')==-32602,payload
            if kind=='foreign_conversation':assert 'Диалог не найден' in str(payload),payload
            if kind=='invalid_root':assert 'Неизвестные разделы аргументов' in str(payload),payload
            if kind=='invalid_query':assert 'Неизвестные параметры query' in str(payload),payload
        after=fingerprint(engine)
        assert before==after,'A rejected or metadata-only call mutated domain data'
        record['outcome']='passed';record['domain_unchanged']=True
    except BaseException as error:
        record['outcome']='failed';record['error_type']=type(error).__name__
        raise
    finally:
        record['latency_seconds']=round(perf_counter()-start,5)
        stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush()
