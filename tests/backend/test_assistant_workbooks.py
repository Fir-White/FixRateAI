"""Actual private workbook evidence and natural-language replies, independent of import."""
import copy,json
from uuid import uuid4
from sqlalchemy import text
from tests.backend.test_assistant import assistant_case,managed,runtime,thread,B
from tests.backend.test_assistant_capabilities import upload
from app.catalog_excel import write_workbook
from app.assistant.workbooks import context as workbook_context
from app.assistant.attachments import SCOPE


def book(rows=31):
    return write_workbook({'Summary':[['Kind','Hours'],['Pump',12],['Fan',8]],
                           'Details':[['Name','Hours']]+[[f'Row {i}',i] for i in range(rows)]+[['LAST-ROW-SENTINEL',99]]})


class TextModel:
    response_model='TEST-ONLY-natural-prose'
    def __init__(self):self.requests=[];self.output='## Анализ книги\n\n'+('Содержательный вывод по исходным строкам. '*90)
    def chat(self,messages,schema,tokens):
        self.requests.append((schema.__name__,copy.deepcopy(messages)))
        assert schema.__name__=='ToolSelection','Complete data needs no planning JSON'
        return schema(tools=[])
    def text(self,messages,tokens):
        self.requests.append(('text',copy.deepcopy(messages)))
        assert tokens>=6000
        return self.output


def send(client,chat,files):
    return client.post(B+f'/conversations/{chat}/messages',json=dict(content='Проанализируй данные таблицы',attachment_ids=files,idempotency_key=str(uuid4())))


def test_complete_xlsx_is_read_before_routing_and_answer_is_unabridged_prose(assistant_case):
    engine,app,admin,_,ids=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    model=TextModel();app.state.assistant_provider_factory=lambda:model
    with engine.connect() as c:before=c.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    view=admin.get(B+'/conversations/'+chat).json();turn=view['turns'][0]
    assert turn['status']=='completed' and turn['answer']==model.output and not view['actions']
    assert [kind for kind,_ in model.requests]==['ToolSelection','text']
    assert 'LAST-ROW-SENTINEL' in json.dumps(model.requests[0][1])
    final=json.loads(model.requests[-1][1][-1]['content'])
    source=final['workbooks'][0]
    assert source['complete'] and len(source['sheets'])==2
    assert source['sheets'][1]['rows_included']==33
    assert source['sheets'][1]['data'][-1][1]['A']=='LAST-ROW-SENTINEL'
    assert source['sheets'][0]['data'][1][1]['B']=='12'
    assert turn['trace'][0]['tool']=='attachment_read'
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))==before


def test_workbook_pages_are_private_scoped_searchable_and_have_original_row_numbers(assistant_case):
    _,_,admin,_,_=assistant_case;chat=thread(admin);other=thread(admin);file=upload(admin,chat,book())
    url=B+f'/conversations/{chat}/attachments/{file["attachment_id"]}/content'
    r=admin.get(url,params=dict(sheet='Details',offset=25,limit=10));assert r.status_code==200,r.text
    data=r.json();assert len(data['sheets'])==2 and data['total']==33
    assert data['items'][0]['row']==26 and data['items'][-1]['cells']['A']=='LAST-ROW-SENTINEL'
    assert data['next_offset'] is None and r.headers['cache-control']=='private, no-store'
    found=admin.get(url,params=dict(sheet='Details',q='LAST-ROW')).json()
    assert found['total']==1 and found['items'][0]['row']==33
    assert admin.get(url,params=dict(sheet='missing')).status_code==422
    assert admin.get(url,params=dict(limit=100)).status_code==422
    assert admin.chief.get(url).status_code==404
    assert admin.get(url.replace(chat,other)).status_code==404


def test_workbook_budget_is_explicit_and_remaining_rows_can_be_read(assistant_case):
    _,app,admin,_,ids=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    SCOPE.set((uuid4(),ids['user'],ids['site'],'admin'))
    # Use the authenticated endpoint for scope, then construct exactly that owner scope.
    SCOPE.set((chat,ids['user'],ids['site'],'admin'))
    result=workbook_context(app,[file],budget=90)
    assert not result[0]['complete']
    assert any(s['truncated'] for s in result[0]['sheets'])
    assert sum(len(s['data']) for s in result[0]['sheets'])<36
    r=admin.get(B+f'/conversations/{chat}/attachments/{file["attachment_id"]}/content',params=dict(sheet='Details',offset=32))
    assert r.status_code==200 and r.json()['items'][0]['cells']['A']=='LAST-ROW-SENTINEL'


def test_broken_xlsx_reports_read_failure_instead_of_searching_a_catalog(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);file=upload(admin,chat,b'PK-not-an-xlsx')
    model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    source=json.loads(model.requests[-1][1][-1]['content'])['workbooks'][0]
    assert source['status']=='unreadable' and source['error']
    assert admin.get(B+'/conversations/'+chat).json()['turns'][0]['status']=='completed'


def test_unselected_workbook_never_enters_the_model_context(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin)
    chosen=upload(admin,chat,book(),name='chosen.xlsx')
    pending=upload(admin,chat,write_workbook({'Private':[['UNSENT-SECRET-SENTINEL']]}),name='pending.xlsx')
    model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[chosen['attachment_id']]).status_code==202
    assert 'UNSENT-SECRET-SENTINEL' not in json.dumps(model.requests)
    assert pending['attachment_id'] not in json.dumps(model.requests)


def test_plain_conversation_uses_one_natural_reply_without_planning_or_review(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin)
    model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[]).status_code==202
    assert [kind for kind,_ in model.requests]==['ToolSelection','text']
    turn=admin.get(B+'/conversations/'+chat).json()['turns'][0]
    assert turn['answer']==model.output and turn['trace']==[]


def test_latest_question_is_explicit_and_not_duplicated_as_history(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[]).status_code==202
    model.requests.clear()
    question='Ты кто по жизни?'
    response=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=question,attachment_ids=[],idempotency_key=str(uuid4())))
    assert response.status_code==202
    route=model.requests[0][1];assert route[-1]['role']=='user' and route[-1]['content'].endswith(question)
    final=json.loads(model.requests[-1][1][-1]['content'])
    assert final['question']==question and final['history']==[]
    assert set(final)=={'question','history','server_context'}
    assert final['server_context']['local_date'] and final['server_context']['timezone']
    assert 'workbooks' not in model.requests[-1][1][0]['content']
    assert all(item['user']!=question for item in final['history'])


def test_explicit_followup_preserves_previous_conversation(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[]).status_code==202
    model.requests.clear()
    response=admin.post(B+f'/conversations/{chat}/messages',json=dict(content='Расскажи об этом подробнее',attachment_ids=[],idempotency_key=str(uuid4())))
    assert response.status_code==202
    final=json.loads(model.requests[-1][1][-1]['content'])
    assert len(final['history'])==1 and final['history'][0]['user']=='Проанализируй данные таблицы'


def test_followup_can_analyse_the_previously_sent_workbook_without_reupload(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    first=TextModel();app.state.assistant_provider_factory=lambda:first
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    class Followup(TextModel):
        def chat(self,messages,schema,tokens):
            self.requests.append((schema.__name__,copy.deepcopy(messages)))
            assert schema.__name__=='ToolSelection'
            return schema(tools=['attachment_read'],workbook_ids=[file['attachment_id']])
    model=Followup();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[]).status_code==202
    evidence=json.loads(model.requests[-1][1][-1]['content'])['workbooks'][0]
    assert evidence['complete'] and evidence['sheets'][1]['data'][-1][1]['A']=='LAST-ROW-SENTINEL'
    assert [kind for kind,_ in model.requests]==['ToolSelection','text']
    assert admin.get(B+'/conversations/'+chat).json()['turns'][-1]['attachments']==[]


def test_text_failure_explains_limitation_and_never_reports_fabricated_analysis(assistant_case):
    from ml_service.app.providers.aitunnel import AITunnelFailure
    _,app,admin,_,_=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    class InterruptedReply(TextModel):
        def text(self,messages,tokens):
            raise AITunnelFailure('AITUNNEL_TIMEOUT')
    model=InterruptedReply();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    turn=admin.get(B+'/conversations/'+chat).json()['turns'][0]
    assert turn['status']=='failed' and turn['error_code']=='AITUNNEL_TIMEOUT'
    assert not turn['answer'].startswith(model.output)
    assert 'за отведённое время' in turn['answer']


def test_changed_role_stops_plain_text_generation_after_routing(assistant_case):
    engine,app,admin,_,ids=assistant_case;chat=thread(admin)
    class ChangedRole(TextModel):
        def chat(self,messages,schema,tokens):
            with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='engineer' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))
            return super().chat(messages,schema,tokens)
    model=ChangedRole();app.state.assistant_provider_factory=lambda:model
    try:
        assert send(admin,chat,[]).status_code==202
        assert [kind for kind,_ in model.requests]==['ToolSelection']
        with engine.connect() as c:assert c.scalar(text('SELECT status FROM assistant_turns WHERE conversation_id=:id'),dict(id=chat))=='failed'
    finally:
        with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))


def test_repeated_calendar_marks_are_folded_losslessly_and_formula_facts_keep_addresses():
    from app.assistant.workbooks import evidence_cells,findings
    from app.catalog_excel import read_workbook
    sheets=read_workbook(write_workbook({'Calendar':[['x','x','x','y','y','z','x','x','x']]}),provenance=True)
    values=sheets['Calendar'][0][1]
    assert evidence_cells(values)=={'A:C':'x','D':'y','E':'y','F':'z','G:I':'x'}
    formula={'value':'0','formula':True,'formula_text':'G6*F6'}
    text_cell={'value':'8+A6:S33','formula':False,'formula_text':None}
    result=findings({'Sheet':[(6,{'H':formula,'I':text_cell})]})
    assert result[0]['cell']=='H6' and result[0]['empty_cells']==['G6','F6']
    assert result[1]['cell']=='I6' and result[1]['value']=='8+A6:S33'
