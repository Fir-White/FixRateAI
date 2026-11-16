"""Actual private workbook evidence and natural-language replies, independent of import."""
import copy,json
import pytest
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
    def __init__(self):self.requests=[];self.output=('## Анализ книги\n\n'+('Содержательный вывод по исходным строкам. '*90)).rstrip()
    def chat(self,messages,schema,tokens):
        self.requests.append((schema.__name__,copy.deepcopy(messages)))
        if schema.__name__=='ToolSelection':
            context=json.loads(messages[-1]['content'])['context']
            files=[file['attachment_id'] for file in context['message_attachments'] if file['mime_type']=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
            goal=dict(id='workbook',title='Проанализировать все исходные строки и листы выбранной книги',tool='attachment_read',kind='read',requires_full_list=True,response_style='analysis') if files else dict(id='conversation',title='Ответить на текущий вопрос пользователя',tool='',kind='conversation')
            return schema(tools=['attachment_read'] if files else [],goals=[goal],workbook_ids=files)
        assert schema.__name__=='FinalReply','Complete server-read file evidence needs one typed natural reply, not guessed tool parameters'
        return schema(answer=self.output)


def send(client,chat,files,content='Проанализируй данные таблицы'):
    return client.post(B+f'/conversations/{chat}/messages',json=dict(content=content,attachment_ids=files,idempotency_key=str(uuid4())))


@pytest.mark.parametrize('transport',['text','typed'])
def test_complete_xlsx_is_read_before_routing_and_answer_is_unabridged_prose(assistant_case,transport):
    engine,app,admin,_,ids=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    model=TextModel();app.state.assistant_provider_factory=lambda:model
    if transport=='text':
        def text_reply(messages,tokens):
            model.requests.append(('text',copy.deepcopy(messages)))
            assert tokens>=6000
            return model.output
        model.text=text_reply
    with engine.connect() as c:before=c.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    view=admin.get(B+'/conversations/'+chat).json();turn=view['turns'][0]
    assert turn['status']=='completed' and model.output in turn['answer'] and not view['actions']
    assert len(model.output)>3000  # The whole natural reply survives any goal-status wrapper.
    assert [kind for kind,_ in model.requests]==['ToolSelection','text' if transport=='text' else 'FinalReply']
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
    source=json.loads(model.requests[0][1][-1]['content'])['context']['workbooks'][0]
    assert source['status']=='unreadable' and source['error']
    turn=admin.get(B+'/conversations/'+chat).json()['turns'][0]
    assert turn['status']=='completed' and turn['workflow']['outcome'] in ('partial','blocked')
    assert 'FinalReply' not in [kind for kind,_ in model.requests]
    assert any(word in turn['answer'].casefold() for word in ('не прочитан','не удалось прочитать','недоступ','не получен','поврежд'))
    assert not any('catalog' in item['tool'] for item in turn['trace'])


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
    assert send(admin,chat,[],content='Расскажи о возможностях помощника FixRate').status_code==202
    assert [kind for kind,_ in model.requests]==['ToolSelection','FinalReply']
    turn=admin.get(B+'/conversations/'+chat).json()['turns'][0]
    assert model.output in turn['answer'] and turn['trace']==[]


def test_latest_question_is_explicit_and_not_duplicated_as_history(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[],content='Расскажи о возможностях помощника FixRate').status_code==202
    model.requests.clear()
    question='Ты кто по жизни?'
    response=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=question,attachment_ids=[],idempotency_key=str(uuid4())))
    assert response.status_code==202
    route=model.requests[0][1];assert route[-1]['role']=='user' and json.loads(route[-1]['content'])['question']==question
    final=json.loads(model.requests[-1][1][-1]['content'])
    assert final['question']==question
    assert final['history']==[]  # An independent identity question needs no prior book or objective.
    assert set(final)=={'question','history','server_context','workbooks','verified_results'}
    assert final['workbooks']==[] and final['verified_results']==[]
    assert final['server_context']['local_date'] and final['server_context']['timezone']
    assert 'workbooks' not in model.requests[-1][1][0]['content']
    assert all(item['user']!=question for item in final['history'])


def test_explicit_followup_preserves_previous_conversation(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);model=TextModel();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[],content='Расскажи о возможностях помощника FixRate').status_code==202
    model.requests.clear()
    response=admin.post(B+f'/conversations/{chat}/messages',json=dict(content='Расскажи об этом подробнее',attachment_ids=[],idempotency_key=str(uuid4())))
    assert response.status_code==202
    final=json.loads(model.requests[-1][1][-1]['content'])
    assert len(final['history'])==1 and final['history'][0]['user']=='Расскажи о возможностях помощника FixRate'


def test_followup_can_analyse_the_previously_sent_workbook_without_reupload(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    first=TextModel();app.state.assistant_provider_factory=lambda:first
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    class Followup(TextModel):
        def chat(self,messages,schema,tokens):
            if schema.__name__!='ToolSelection':return super().chat(messages,schema,tokens)
            self.requests.append((schema.__name__,copy.deepcopy(messages)))
            return schema(tools=['attachment_read'],workbook_ids=[file['attachment_id']],goals=[dict(id='workbook',title='Продолжить анализ ранее отправленной книги',tool='attachment_read',kind='read',requires_full_list=True,response_style='analysis')])
    model=Followup();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[]).status_code==202
    evidence=json.loads(model.requests[-1][1][-1]['content'])['workbooks'][0]
    assert evidence['complete'] and evidence['sheets'][1]['data'][-1][1]['A']=='LAST-ROW-SENTINEL'
    assert [kind for kind,_ in model.requests]==['ToolSelection','FinalReply']
    assert admin.get(B+'/conversations/'+chat).json()['turns'][-1]['attachments']==[]


def test_text_failure_explains_limitation_and_never_reports_fabricated_analysis(assistant_case):
    from ml_service.app.providers.ollama import OllamaFailure
    _,app,admin,_,_=assistant_case;chat=thread(admin);file=upload(admin,chat,book())
    class InterruptedReply(TextModel):
        def chat(self,messages,schema,tokens):
            if schema.__name__=='FinalReply':raise OllamaFailure('OLLAMA_TIMEOUT')
            return super().chat(messages,schema,tokens)
    model=InterruptedReply();app.state.assistant_provider_factory=lambda:model
    assert send(admin,chat,[file['attachment_id']]).status_code==202
    turn=admin.get(B+'/conversations/'+chat).json()['turns'][0]
    assert turn['status']=='failed' and turn['error_code']=='OLLAMA_TIMEOUT'
    assert not turn['answer'].startswith(model.output)
    assert any(word in turn['answer'].casefold() for word in ('прерван','не удалось','не заверш','незаверш','не получен'))
    assert turn['workflow']['outcome'] in ('partial','blocked')


def test_changed_role_stops_plain_text_generation_after_routing(assistant_case):
    engine,app,admin,_,ids=assistant_case;chat=thread(admin)
    class ChangedRole(TextModel):
        def chat(self,messages,schema,tokens):
            with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='engineer' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))
            return super().chat(messages,schema,tokens)
    model=ChangedRole();app.state.assistant_provider_factory=lambda:model
    try:
        assert send(admin,chat,[],content='Расскажи о возможностях помощника FixRate').status_code==202
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
