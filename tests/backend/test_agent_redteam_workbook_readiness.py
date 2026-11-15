"""Independent unknown-norm oracle on genuine uploaded XLSX, with inference forbidden."""
from uuid import uuid4
import re
import pytest
from app.catalog_excel import write_workbook
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,B,thread
from tests.backend.test_agent_redteam_matrix import fingerprint
from tests.backend.test_catalog_imports import replace_xml

@pytest.mark.parametrize('kind,value',[
    ('missing',None),('zero','0'),('negative','-1'),('text','unknown'),('nonfinite','NaN'),('formula','2'),('positive_unconfirmed','3'),
])
def test_raw_quantity_is_not_a_confirmed_staffing_norm(assistant_case,kind,value):
    _,app,client,_,_=assistant_case;chat=thread(client);calls=[]
    content=write_workbook({'Audit':[['operation','person_hours','quantity'],['TO2',value,'7']]})
    if kind=='formula':
        content=replace_xml(content,lambda xml:re.sub(r'<c r="B2".*?</c>','<c r="B2"><f>D2</f><v>2</v></c>',xml))
    uploaded=client.post(B+f'/conversations/{chat}/attachments',files={'file':('Norm.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert uploaded.status_code==201,uploaded.text
    before=fingerprint(assistant_case[0])
    class NoInference:
        def chat(self,*args):calls.append('chat');raise AssertionError('Source readiness must precede generated staffing')
        def text(self,*args):calls.append('text');raise AssertionError('Do not turn quantity into hours')
    app.state.assistant_provider_factory=NoInference
    try:
        response=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Сколько человек нужно для выполнения операций из этого Excel? Не выдумывай нормативов.',attachment_ids=[uploaded.json()['attachment_id']],idempotency_key=str(uuid4())))
        assert response.status_code==202,response.text
        view=client.get(B+'/conversations/'+chat).json();turn=view['turns'][-1]
        assert turn['status']=='completed',turn
        assert 'Численность не рассчитана' in turn['answer'] and not view['actions'] and not calls
        facts=[row for row in turn['trace'] if row['tool']=='__workbook_readiness']
        assert len(facts)==1 and facts[0]['result']['can_calculate_real_staffing'] is False
        assert facts[0]['result']['unknown_norm_fields']==(0 if kind=='positive_unconfirmed' else 1)
        if kind!='positive_unconfirmed':assert 'Audit!B2' in turn['answer']
        clean=turn['answer'].replace('*','')
        assert not re.search(r'(?:нужно|требуется|потребуется)\s+[237]\s+(?:человек|сотрудник)',clean,re.I)
        assert fingerprint(assistant_case[0])==before
    finally:del app.state.assistant_provider_factory

@pytest.mark.parametrize('question',[
    'Сколько сотрудников перечислено в файле?',
    'Сколько человек пришло за смену?',
    'Импортируй этот Excel, потом рассчитай потребность в сотрудниках.',
    'Покажи код и показание из этого файла.',
    'Кто ты и какие у тебя возможности?',
])
def test_readiness_does_not_capture_unrelated_counts_or_explicit_import(question):
    from app.assistant.workbook_readiness import requested
    assert not requested(question)

def test_missing_norm_column_stays_null_and_never_shifts_quantity():
    from app.catalog_excel import read_workbook
    from app.assistant.workbook_readiness import quality,preserve_missing_norms
    from app.assistant.workbooks import evidence_cells
    sheet=read_workbook(write_workbook({'Audit':[['operation','person_hours','quantity'],['TO2',None,'2']]}),provenance=True)
    diagnostics=quality(sheet);row,values=sheet['Audit'][1]
    actual=preserve_missing_norms(row,evidence_cells(values),diagnostics,'Audit')
    assert actual=={'A':'TO2','B':None,'C':'2'}
    assert diagnostics['tables'][0]['issues'][0]['cell']=='B2'

def test_very_wide_norm_header_is_explicitly_unresolved_not_quadratic():
    from app.catalog_excel import read_workbook
    from app.assistant.workbook_readiness import quality
    sheet=read_workbook(write_workbook({'Audit':[['person_hours']*17,['1']*17]}),provenance=True)
    actual=quality(sheet)['tables'][0]
    assert actual['layout_too_wide'] and actual['unknown_norm_fields'] is None and actual['issues_truncated']

def test_quality_metadata_cannot_bypass_the_workbook_context_budget():
    from app.catalog_excel import read_workbook
    from app.assistant.workbook_readiness import quality
    sheet=read_workbook(write_workbook({'Audit':[['operation','person_hours','quantity'],['TO2',None,'9'*10000]]}),provenance=True)
    actual=quality(sheet)['tables'][0]['issues'][0]['quantity_cells'][0]
    assert actual['value'] is None and actual['value_truncated'] and actual['cell']=='C2'

def test_old_workbook_readiness_is_enforced_after_router_selection(assistant_case):
    from app.schemas.assistant import ToolSelection
    _,app,client,_,_=assistant_case;chat=thread(client)
    content=write_workbook({'Audit':[['operation','person_hours','quantity'],['TO2',None,'2']]})
    uploaded=client.post(B+f'/conversations/{chat}/attachments',files={'file':('prior.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}).json()
    class RouterOnly:
        def chat(self,messages,schema,tokens):
            assert schema is ToolSelection
            return ToolSelection(tools=[],workbook_ids=[uploaded['attachment_id']])
        def text(self,*args):raise AssertionError('Direct-answer generation must not overwrite the readiness answer')
    app.state.assistant_provider_factory=RouterOnly
    try:
        first=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Сколько человек нужно для выполнения операций из Excel?',attachment_ids=[uploaded['attachment_id']],idempotency_key=str(uuid4())))
        assert first.status_code==202
        second=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Тогда сколько человек нужно для выполнения операций?',attachment_ids=[],idempotency_key=str(uuid4())))
        assert second.status_code==202
        turn=client.get(B+'/conversations/'+chat).json()['turns'][-1]
        assert turn['status']=='completed' and 'Численность не рассчитана' in turn['answer'] and 'Audit!B2' in turn['answer'],turn
    finally:del app.state.assistant_provider_factory

@pytest.mark.parametrize('chosen,expected_unknown',[('first.xlsx',1),('second.xlsx',0)])
def test_explicit_prior_filename_wins_over_last_upload(assistant_case,chosen,expected_unknown):
    _,app,client,_,_=assistant_case;chat=thread(client);files=[]
    for name,value in [('first.xlsx',None),('second.xlsx','3')]:
        content=write_workbook({'Audit':[['operation','person_hours','quantity'],['TO2',value,'7']]})
        uploaded=client.post(B+f'/conversations/{chat}/attachments',files={'file':(name,content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        assert uploaded.status_code==201
        files.append(uploaded.json()['attachment_id'])
    class NoInference:
        def chat(self,*args):raise AssertionError('The explicitly named sent workbook is selected by server metadata')
    app.state.assistant_provider_factory=NoInference
    try:
        first=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Сколько человек нужно для выполнения операций из файлов?',attachment_ids=files,idempotency_key=str(uuid4())))
        assert first.status_code==202
        second=client.post(B+f'/conversations/{chat}/messages',json=dict(content=f'Сколько человек нужно для выполнения операций из {chosen}?',attachment_ids=[],idempotency_key=str(uuid4())))
        assert second.status_code==202
        turn=client.get(B+'/conversations/'+chat).json()['turns'][-1]
        assert turn['status']=='completed',turn
        assert [r for r in turn['trace'] if r['tool']=='__workbook_readiness'][0]['result']['unknown_norm_fields']==expected_unknown
        assert not client.get(B+'/conversations/'+chat).json()['actions']
    finally:del app.state.assistant_provider_factory
