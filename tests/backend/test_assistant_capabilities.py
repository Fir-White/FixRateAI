"""Every user-facing API has a tool or an explicit infrastructure/alias exclusion."""
import io,json,os
from contextlib import closing
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text
from app.assistant.tools import TOOLS,available,describe,file_fields
from app.assistant.capabilities import excluded_routes
from app.assistant.service import compact,dump
from tests.backend.test_assistant import assistant_case,managed,runtime,rpc,thread,proposal,confirm

B='/api/v1/assistant';P='/api/v1/maintenance'

def test_entire_authenticated_business_api_is_accounted_for(assistant_case):
    _,app,_,_,_=assistant_case
    actual={(m,r.path) for r in app.routes if isinstance(r,APIRoute) and r.include_in_schema and r.path.startswith('/api/') for m in r.methods}
    registered={(t.method,t.path) for t in TOOLS}
    assert actual-registered-set(excluded_routes())==set()
    assert len({t.name for t in TOOLS})==len(TOOLS)
    assert not any('/password' in t.path for t in TOOLS)
    for tool in TOOLS:
        assert (tool.method,tool.path) in {(m,r.path) for r in app.routes if isinstance(r,APIRoute) for m in r.methods}
        schema=describe(app,tool)
        if file_fields(app,tool):
            for name in file_fields(app,tool):assert schema['inputSchema']['properties']['body']['properties'][name]['format']=='uuid'
    assert all(t.mode=='read' or t.name.startswith(('notification','profile_email','site_switch','session_logout')) for t in available(app,'director').values())
    assert 'staff_edit' in available(app,'admin') and 'staff_edit' not in available(app,'engineer')
    assert 'operation_edit' in available(app,'chief_engineer') and 'operation_edit' not in available(app,'executor')
    assert 'photo_upload' in available(app,'executor') and 'photo_upload' not in available(app,'director')
    from scripts.assistant_capabilities import manifest
    assert json.loads((Path(__file__).resolve().parents[2]/'contracts/assistant-tools.json').read_text(encoding='utf-8'))==manifest(app)

def upload(client,chat,content,name='TEST.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    response=client.post(B+f'/conversations/{chat}/attachments',files={'file':(name,content,mime)})
    assert response.status_code==201,response.text
    return response.json()

def test_excel_preview_import_export_use_same_file_and_explicit_approval(assistant_case):
    from app.catalog_excel import write_workbook
    from tests.backend.test_registry_excel import book
    engine,_,admin,_,ids=assistant_case;chat=thread(admin)
    blob=write_workbook(book(ids));file=upload(admin,chat,blob)
    assert upload(admin,chat,blob)['attachment_id']==file['attachment_id']
    assert admin.get(B+'/attachments/'+file['attachment_id']).content==blob
    result=rpc(admin,'tools/call',dict(name='registry_import_preview',arguments=dict(conversation_id=chat,body=dict(file=file['attachment_id'])))).json()['result']
    assert not result['isError'],result
    preview=json.loads(result['content'][0]['text']);assert preview['can_import'],preview
    record=proposal(admin,chat,'registry_import',dict(body=dict(file=file['attachment_id'],preview_token=preview['preview_token'])))
    with engine.connect() as c:assert c.scalar(text("SELECT count(*) FROM equipment WHERE site_id=:site AND asset_code='XLS-1'"),dict(site=ids['site']))==0
    response=confirm(admin,record);assert response.status_code==200 and response.json()['status']=='succeeded',response.text
    with engine.connect() as c:assert c.scalar(text("SELECT count(*) FROM equipment WHERE site_id=:site AND asset_code='XLS-1'"),dict(site=ids['site']))==1
    export=rpc(admin,'tools/call',dict(name='registry_export',arguments={})).json()['result']
    assert not export['isError']
    resource=json.loads(export['content'][0]['text'])['resource']
    assert resource['url']==P+'/registry/excel' and 'spreadsheet' in resource['mime']
    assert admin.get(resource['url']).content.startswith(b'PK')

def test_attachments_do_not_cross_owner_chat_or_role_and_must_keep_hash(assistant_case):
    from app.catalog_excel import write_workbook
    from app.storage import safe_storage_path
    engine,app,admin,_,_=assistant_case;chat=thread(admin);other=thread(admin)
    file=upload(admin,chat,write_workbook({'TEST':[['TEST ONLY']]}))
    assert admin.chief.get(B+'/attachments/'+file['attachment_id']).status_code==404
    result=rpc(admin,'tools/call',dict(name='registry_import_preview',arguments=dict(conversation_id=other,body=dict(file=file['attachment_id'])))).json()['result']
    assert result['isError']
    with engine.connect() as c:key=c.scalar(text('SELECT storage_key FROM assistant_attachments WHERE attachment_id=:id'),dict(id=file['attachment_id']))
    path=safe_storage_path(app.state.settings.photo_storage_root,key);path.write_bytes(b'TAMPERED TEST')
    assert admin.get(B+'/attachments/'+file['attachment_id']).status_code==409
    assert admin.post(B+f'/conversations/{chat}/attachments',files={'file':('bad.exe',b'bad','application/octet-stream')}).status_code==422

def test_email_confirmation_keeps_password_out_of_proposal_history_and_audit(assistant_case):
    engine,_,admin,_,_=assistant_case;chat=thread(admin);email='assistant-'+uuid4().hex+'@example.test'
    record=proposal(admin,chat,'profile_email',dict(body=dict(email=email)))
    assert record['secret_fields']==['current_password']
    assert record['arguments']['body']['current_password']=='__human_secret__'
    assert confirm(admin,record).status_code==422
    response=confirm(admin,record,secret_values=dict(current_password=os.environ['FIXRATE_TEST_PASSWORD']))
    assert response.status_code==200 and response.json()['status']=='succeeded',response.text
    assert admin.get(P+'/users/me').json()['email']==email
    with engine.connect() as c:
        content=c.scalar(text('SELECT row_to_json(a)::text FROM assistant_actions a WHERE action_id=:id'),dict(id=record['action_id']))
        audit=c.scalar(text("SELECT string_agg(after_snapshot::text,'') FROM audit_events WHERE entity_id=:id"),dict(id=record['action_id']))
    assert os.environ['FIXRATE_TEST_PASSWORD'] not in content+audit

def test_switch_site_and_logout_forward_real_session_cookies(assistant_case):
    _,_,admin,_,ids=assistant_case;chat=thread(admin)
    # A second membership is created through the same existing building endpoint.
    new=admin.post(P+'/registry/buildings',json=dict(name='TEST ONLY switch destination',timezone='UTC'))
    assert new.status_code==201,new.text
    site=new.json()['site_id'];record=proposal(admin,chat,'site_switch',dict(body=dict(site_id=site)))
    result=confirm(admin,record);assert result.status_code==200 and result.json()['status']=='succeeded',result.text
    assert len(result.headers.get_list('set-cookie'))==2
    assert 'csrfToken' not in result.text
    assert admin.get('/api/v1/auth/session').json()['profile']['siteId']==site
    assert admin.get(B+'/conversations/'+chat).status_code==404
    csrf=admin.cookies.get('fixrate_csrf');admin.headers['X-CSRF-Token']=csrf
    new_chat=thread(admin);logout=proposal(admin,new_chat,'session_logout',{})
    response=confirm(admin,logout);assert response.json()['status']=='succeeded',response.text
    assert admin.get('/api/v1/auth/session').status_code==401
    # The managed fixture owns and cleans only the original site; remove its new TEST-only site.
    engine=assistant_case[0]
    with engine.begin() as c:
        c.execute(text('DELETE FROM assistant_actions WHERE conversation_id=:id'),dict(id=new_chat))
        c.execute(text('DELETE FROM assistant_conversations WHERE conversation_id=:id'),dict(id=new_chat))
        c.execute(text('DELETE FROM audit_events WHERE site_id=:id'),dict(id=site))
        c.execute(text('DELETE FROM site_memberships WHERE site_id=:id'),dict(id=site))
        c.execute(text('DELETE FROM sites WHERE site_id=:id'),dict(id=site))

def test_tool_responses_remain_valid_bounded_json():
    value=[dict(id=str(uuid4()),title='TEST ONLY '*1000,items=list(range(100))) for _ in range(100)]
    result=compact(value,12000)
    assert len(dump(result))<=12000
    assert json.loads(dump(result))==result
    assert result.get('truncated')

def test_assignment_proposal_is_rechecked_by_real_preview_without_writing_assignments(runtime):
    from tests.backend.test_runtime_integration import login,assignment_search,ASSIGNMENT_TASK
    engine,app=runtime
    with closing(login(app,'chief_engineer')) as client:
        context,body=assignment_search(client)
        preview=client.post(P+f'/tasks/{ASSIGNMENT_TASK}/assignment-preview',json=body).json()
        assert preview['status']=='ok',preview
        command={k:preview['command'][k] for k in ('expected_revision','executor_ids','start_at','end_at')}
        command['reason']='TEST ONLY proposal from validated preview'
        chat=thread(client)
        with engine.connect() as c:before=c.scalar(text('SELECT count(*) FROM work_assignments WHERE work_order_id=:id'),dict(id=ASSIGNMENT_TASK))
        record=proposal(client,chat,'task_assign',dict(path=dict(task_id=ASSIGNMENT_TASK),body=command))
        assert record['status']=='proposed'
        bad=dict(command,executor_ids=[str(uuid4()),str(uuid4())])
        result=rpc(client,'tools/call',dict(name='task_assign',arguments=dict(conversation_id=chat,path=dict(task_id=ASSIGNMENT_TASK),body=bad))).json()['result']
        assert result['isError']
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_assignments WHERE work_order_id=:id'),dict(id=ASSIGNMENT_TASK))==before

def test_nearest_tasks_are_scoped_sorted_and_bounded(runtime):
    from tests.backend.test_runtime_integration import login
    from datetime import datetime
    _,app=runtime
    with closing(login(app,'chief_engineer')) as client:
        for period in ('upcoming','overdue','undated','all'):
            result=client.get(B+'/workspace/tasks',params=dict(period=period))
            assert result.status_code==200,result.text
            data=result.json();assert len(data['items'])<=25 and data['total']>=len(data['items'])
            dates=[datetime.fromisoformat(item['scheduledStart']) for item in data['items'] if item['scheduledStart']]
            if period=='upcoming':assert dates==sorted(dates)
            if period=='overdue':assert dates==sorted(dates,reverse=True)

def test_executor_stages_and_uploads_real_photo_only_after_confirmation(runtime):
    from tests.backend.test_runtime_integration import login,isolated_order,image_bytes
    engine,app=runtime;order,report=isolated_order(engine,'in_progress')
    with closing(login(app,'executor')) as client:
        chat=thread(client);blob=image_bytes(115)
        file=upload(client,chat,blob,'TEST.png','image/png')
        bundle=client.get(P+f'/ui/tasks/{order}').json()
        record=proposal(client,chat,'photo_upload',dict(path=dict(task_id=str(order)),body=dict(expected_revision=1,checklist_item_id=bundle['execution']['checklist'][0]['id'],phase='before',view_key='TEST front',file=file['attachment_id'])))
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM evidence_files WHERE work_report_id=:id'),dict(id=report))==0
        response=confirm(client,record);assert response.status_code==200 and response.json()['status']=='succeeded',response.text
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM evidence_files WHERE work_report_id=:id'),dict(id=report))==1

def test_optional_provider_key_is_replaced_before_persistence(runtime):
    from tests.backend.test_runtime_integration import login,TASK
    engine,app=runtime
    with closing(login(app,'chief_engineer')) as client:
        chat=thread(client)
        record=proposal(client,chat,'photo_review',dict(path=dict(task_id=TASK),body=dict(expected_revision=1,api_key='TEST-SHOULD-NEVER-BE-STORED')))
        assert record['secret_fields']==['api_key']
        assert record['arguments']['body']['api_key']=='__human_secret__'
        with engine.connect() as c:assert 'TEST-SHOULD-NEVER-BE-STORED' not in c.scalar(text('SELECT row_to_json(a)::text FROM assistant_actions a WHERE action_id=:id'),dict(id=record['action_id']))

def test_full_search_and_projection_do_not_hide_items_after_first_page(assistant_case):
    _,_,admin,_,ids=assistant_case
    last=None
    for i in range(28):
        response=admin.post(P+'/equipment',json=dict(system_id=str(ids['system']),asset_code=f'TEST-PAGER-{i:02d}',name='TEST ONLY target beyond page' if i==27 else f'TEST ONLY {i}',properties=dict(note='A'*9000) if i==27 else {}))
        assert response.status_code==201,response.text
        last=response.json()
    page=rpc(admin,'tools/call',dict(name='equipment_list',arguments={})).json()['result']
    data=json.loads(page['content'][0]['text']);assert data['limit']==25 and len(data['items'])==25 and data['total']==28
    found=admin.get(B+'/workspace/equipment',params=dict(q='target beyond page')).json();assert found['total']==1 and found['items'][0]['equipment_id']==last['equipment_id']
    staff=admin.get(B+'/workspace/staff',params=dict(q='Test chief'));assert staff.status_code==200,staff.text
    selected=staff.json()['items'][0];assert admin.get(B+'/workspace/staff/'+selected['user_id']).status_code==200
    result=rpc(admin,'tools/call',dict(name='workforce_read',arguments=dict(view=dict(path=['staff'],q='Test chief')))).json()['result']
    assert not result['isError'];assert json.loads(result['content'][0]['text'])['total']==1
    result=rpc(admin,'tools/call',dict(name='equipment_read',arguments=dict(path=dict(equipment_id=last['equipment_id']),view=dict(path=['properties','note'],text_offset=3000,text_limit=6000)))).json()['result']
    assert not result['isError'];text=json.loads(result['content'][0]['text']);assert ''.join(text['text_parts'])=='A'*6000 and text['returned_characters']==6000

def test_usage_reading_accepts_typed_payload_and_photo_with_human_confirmation(assistant_case):
    from datetime import datetime,timedelta,timezone
    from tests.backend.test_registry import equipment,install
    from tests.backend.test_runtime_integration import image_bytes
    _,_,admin,_,ids=assistant_case;part=install(admin,equipment(admin,ids));chat=thread(admin)
    file=upload(admin,chat,image_bytes(116),'TEST.png','image/png')
    body=dict(payload=dict(expected_revision=part['revision'],usage_value='120',measured_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),note='TEST ONLY verified reading'),photo=file['attachment_id'])
    record=proposal(admin,chat,'component_reading',dict(path=dict(component_id=part['component_id']),body=body))
    assert isinstance(record['arguments']['body']['payload'],str)
    response=confirm(admin,record);assert response.status_code==200 and response.json()['status']=='succeeded',response.text
    assert response.json()['result']['data']['current_usage']=='120.000'
