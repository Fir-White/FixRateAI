from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from sqlalchemy import event, text

from app.catalog_import import inspect_catalog
from app.catalog_excel import read_workbook
from tests.fixtures.catalog_source import catalog_book, TYPE_COUNTS, FREQUENCY_COUNTS
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime, login, PREFIX

BASE=PREFIX+'/catalog-imports'

def upload(client,content,path='/preview',token=None):
    return client.post(BASE+path,files={'file':('anonymous.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data={'preview_token':token} if token else {})

def replace_xml(content, transform):
    output=BytesIO()
    with ZipFile(BytesIO(content)) as source, ZipFile(output,'w',ZIP_DEFLATED) as dest:
        for name in source.namelist():
            data=source.read(name)
            if name=='xl/worksheets/sheet1.xml':data=transform(data.decode()).encode()
            dest.writestr(name,data)
    return output.getvalue()

def test_anonymous_catalog_preserves_context_types_frequencies_and_unknowns():
    content=catalog_book();data=inspect_catalog(content)
    assert data==inspect_catalog(content)
    assert data['summary']['operation_count']==217
    assert data['summary']['maintenance_types']==TYPE_COUNTS
    assert data['summary']['frequency_counts']==FREQUENCY_COUNTS
    assert data['summary']['top_level_group_count']==16
    nested=next(g for g in data['groups'] if g['code']=='10.1')
    assert nested['parent_id']==next(g['id'] for g in data['groups'] if g['code']=='10')
    assert data['summary']['empty_duration_count']==217
    assert data['summary']['ready_count']==0
    assert all(o['norm_value'] is None and o['quantity'] is None and not o['ready_for_real_plan'] for o in data['operations'])
    assert all(len(o['quality_flags'])==4 for o in data['operations'])
    monthly=next(o for o in data['operations'] if o['frequency_raw']=='1/мес')
    assert monthly['mark_count']==10 and monthly['interpretation']=='UNKNOWN'
    assert len(monthly['calendar_marks'])==31 and monthly['calendar_year'] is None
    daily=next(o for o in data['operations'] if o['frequency_raw']=='2/сутки')
    assert daily['calendar_marks'][0]['text']=='день\nночь'
    assert any(issue['code']=='NON_NUMERIC_LABOR' and issue['cell']=='I6' for issue in data['issues'])

def test_provenance_keeps_whitespace_formula_and_absent_distinct_from_empty():
    content=catalog_book(1)
    def change(xml):
        import re
        xml=re.sub(r'<c r="F5".*?</c>','',xml)
        return re.sub(r'<c r="E5".*?</c>','<c r="E5"><f>1+1</f><v>2</v></c>',xml)
    data=inspect_catalog(replace_xml(content,change));row=data['operations'][0]
    assert row['raw_cells']['E']['formula']=='1+1' and row['raw_cells']['E']['text']=='2'
    assert row['norm_value'] is None and 'NEEDS_DURATION' in row['quality_flags']
    assert row['raw_cells']['F']['present'] is False
    assert row['raw_cells']['G']['present'] is True and row['raw_cells']['G']['text']==''

def test_duplicate_source_coordinates_are_rejected():
    content=catalog_book(1)
    bad=replace_xml(content,lambda xml:xml.replace('<c r="E5"','<c r="D5"',1))
    with pytest.raises(ValueError,match='Повтор адреса'):read_workbook(bad)

def test_macro_file_is_rejected_independently_of_filename_case():
    output=BytesIO()
    with ZipFile(BytesIO(catalog_book(1))) as source,ZipFile(output,'w',ZIP_DEFLATED) as dest:
        for name in source.namelist():dest.writestr(name,source.read(name))
        dest.writestr('xl/VBAPROJECT.BIN',b'not executed')
    with pytest.raises(ValueError,match='Макросы'):inspect_catalog(output.getvalue())

def test_missing_frequency_is_a_quality_issue_not_a_server_error(managed):
    import re
    _,_,admin,_,_=managed
    content=replace_xml(catalog_book(1),lambda xml:re.sub(r'<c r="D5".*?</c>','',xml))
    response=upload(admin,content)
    assert response.status_code==200,response.text
    row=response.json()['operations'][0]
    assert row['frequency_raw']=='' and not row['ready_for_real_plan']
    assert any(issue['code']=='FREQUENCY_UNKNOWN' for issue in response.json()['issues'])

def test_preview_and_idempotent_save_only_create_private_draft(managed):
    engine,_,admin,_,ids=managed
    content=catalog_book()
    tables=('equipment','maintenance_rules','operation_templates','rule_equipment','schedule_entries','work_orders','work_assignments')
    def counts():
        with engine.connect() as conn:return {name:conn.scalar(text(f'SELECT count(*) FROM {name} WHERE site_id=:site'),ids) for name in tables}
    before=counts()
    preview=upload(admin,content)
    assert preview.status_code==200,preview.text
    payload=preview.json()
    assert payload['total']==217 and len(payload['operations'])==25
    with engine.connect() as conn:assert conn.scalar(text('SELECT count(*) FROM regulation_catalog_imports WHERE site_id=:site'),ids)==0
    assert counts()==before
    saved=upload(admin,content,'',payload['preview_token'])
    assert saved.status_code==201,saved.text
    identity=saved.json()['import_id']
    assert saved.json()['ready_for_real_plan'] is False
    again=upload(admin,content,'',payload['preview_token'])
    assert again.status_code==200 and again.json()['import_id']==identity and again.json()['already_saved']
    assert counts()==before
    listing=admin.get(BASE).json();assert listing['total']==1
    assert 'source_file' not in listing['items'][0] and 'catalog_data' not in listing['items'][0]
    detail=admin.get(BASE+'/'+identity);assert detail.status_code==200 and detail.json()['status']=='draft'
    assert detail.headers['cache-control']=='private, no-store'
    page=admin.get(BASE+'/'+identity+'/operations?offset=25&limit=25').json()
    assert page['total']==217 and len(page['items'])==25
    assert 'raw_cells' not in page['items'][0]
    found=admin.get(BASE+'/'+identity+'/operations?q=0216').json();assert found['total']==1
    source=admin.get(BASE+f"/{identity}/operations/{found['items'][0]['row']}")
    assert source.status_code==200 and len(source.json()['calendar_marks'])==31
    downloaded=admin.get(BASE+'/'+identity+'/source')
    assert sha256(downloaded.content).digest()==sha256(content).digest()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM audit_events WHERE site_id=:site AND entity_type='regulation_catalog_imports'"),ids)==1

def test_concurrent_duplicate_save_has_one_identity(managed):
    engine,_,admin,_,ids=managed;content=catalog_book(5)
    token=upload(admin,content).json()['preview_token']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:upload(admin,content,'',token),range(2)))
    assert sorted(r.status_code for r in responses)==[200,201]
    assert len({r.json()['import_id'] for r in responses})==1
    with engine.connect() as conn:assert conn.scalar(text('SELECT count(*) FROM regulation_catalog_imports WHERE site_id=:site'),ids)==1

def test_site_actor_file_and_role_boundaries(managed):
    _,app,admin,_,_=managed;content=catalog_book(1)
    checked=upload(admin,content).json()
    assert upload(admin,catalog_book(2),'',checked['preview_token']).status_code==409
    assert upload(admin,content,'','т'*64).status_code==422
    assert upload(admin.chief,content,'',checked['preview_token']).status_code==409
    saved=upload(admin,content,'',checked['preview_token']).json()['import_id']
    with closing(login(app,'chief_engineer')) as other:
        for tail in ('','/operations','/source','/operations/5'):
            assert other.get(BASE+'/'+saved+tail).status_code==404
        assert other.get(BASE).json()['total']==0
    with closing(login(app,'director')) as director:
        assert upload(director,content).status_code==403
        assert upload(director,content,'',checked['preview_token']).status_code==403
    with closing(login(app,'executor')) as executor:assert executor.get(BASE).status_code==403

def test_read_queries_and_response_rows_are_bounded(managed):
    engine,_,admin,_,_=managed;content=catalog_book(500)
    token=upload(admin,content).json()['preview_token']
    saved=upload(admin,content,'',token).json()['import_id']
    statements=[]
    def count(conn,cursor,statement,params,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:
        response=admin.get(BASE+'/'+saved+'/operations?offset=450')
        assert response.status_code==200 and len(response.json()['items'])==25
        assert len(statements)<=8
        assert admin.get(BASE+'/'+saved+'/operations?limit=500').status_code==422
        assert admin.get(BASE+'?offset='+('9'*100)).status_code==422
    finally:event.remove(engine,'before_cursor_execute',count)
