from datetime import date, timedelta
from contextlib import closing
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from app.catalog_excel import read_workbook, write_workbook, table
from app.integration.registry_excel import EQ, WORK, PART
from tests.backend.test_registry import managed, equipment
from tests.backend.test_runtime_integration import runtime, PREFIX
from tests.backend.test_runtime_integration import login as runtime_login
from tests.backend.test_management import config


def book(ids, *, works=True, parts=True):
    day=(date.today()-timedelta(days=1)).isoformat()
    eq=dict(zip(EQ,[str(ids['site']),'EXCEL','Система из Excel','Вода','XLS-1','Насос из Excel','Подвал',day,'SN-1','active','','customer']))
    work={'Инвентарный номер':'XLS-1','Код работы':'XLS-TO','Работа':'Осмотр насоса','Вид ТО':'ТО3','Периодичность':'месяц','Интервал':'3','Опорная дата':day,'Начало действия':day,'Часы':'2','Единица часов':'person_hour','Бригада':'1','Длительность, мин':'120','Инструкция':'Проверить по паспорту насоса','Пункты регламента':'Сверить показания\nЗафиксировать состояние'}
    part={'Инвентарный номер':'XLS-1','Позиция':'bearing','Деталь':'Подшипник','Дата установки':day,'Единица наработки':'hour','Начальная наработка':'12','Норматив ресурса':'100','Источник ресурса':'Паспорт'}
    return {'Оборудование':[EQ,[eq.get(k,'') for k in EQ]],'Работы':[WORK]+([[work.get(k,'') for k in WORK]] if works else []),'Детали':[PART]+([[part.get(k,'') for k in PART]] if parts else [])}


def upload(admin, sheets, suffix='/preview', token=None):
    content=write_workbook(sheets) if isinstance(sheets,dict) else sheets
    return admin.post(PREFIX+'/registry/excel'+suffix,files={'file':('registry.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data={'preview_token':token} if token else {})


def test_preview_has_no_writes_and_import_uses_shared_catalog_services(managed):
    _,_,admin,_,ids=managed
    sheets=book(ids)
    preview=upload(admin,sheets)
    assert preview.status_code==200,preview.text
    assert preview.json()['can_import'] and len(preview.json()['rows'])==3
    assert admin.get(PREFIX+'/registry').json()['items']==[]
    response=upload(admin,sheets,'/import',preview.json()['preview_token'])
    assert response.status_code==200,response.text
    row=admin.get(PREFIX+'/registry').json()['items'][0]
    assert row['name']=='Насос из Excel' and row['components'][0]['current_usage']=='12.000'
    assert row['services'][0]['maintenance_type']=='ТО3' and row['services'][0]['enabled'] is False
    assert upload(admin,sheets,'/import',preview.json()['preview_token']).status_code==409


def test_export_roundtrip_preserves_existing_types_properties_and_part_history(managed):
    _,_,admin,_,ids=managed
    eq=equipment(admin,ids)
    response=admin.get(PREFIX+'/registry/excel')
    assert response.status_code==200 and response.content[:2]==b'PK'
    sheets=read_workbook(response.content)
    assert 'Оборудование' in sheets and table(sheets['Оборудование'])[0][1]['ID здания']==str(ids['site'])
    checked=upload(admin,response.content)
    assert checked.status_code==200 and checked.json()['can_import'],checked.text
    imported=upload(admin,response.content,'/import',checked.json()['preview_token'])
    assert imported.status_code==200,imported.text
    current=admin.get(f"{PREFIX}/equipment/{eq['equipment_id']}").json()
    assert current['equipment_type_id']==eq['equipment_type_id'] and current['properties']==eq['properties']


def test_unchanged_legacy_drafts_survive_export_preview_without_invented_defaults(runtime):
    _,app=runtime
    with closing(runtime_login(app,'chief_engineer')) as chief:
        exported=chief.get(PREFIX+'/registry/excel')
        checked=upload(chief,exported.content)
        assert checked.status_code==200,checked.text
        assert checked.json()['errors']==[],checked.text
        assert all(row['action']=='unchanged' for row in checked.json()['rows'] if row['sheet']=='Работы')


def test_visible_excel_columns_edit_recurrence_and_checklist_without_losing_metadata(managed):
    _,_,admin,_,ids=managed
    eq=equipment(admin,ids)
    day=date.today()
    configured=admin.chief.post(f"{PREFIX}/equipment/{eq['equipment_id']}/service-configurations",json=config(day,pattern=dict(frequency='month',anchor_date=day.isoformat(),interval=3,weekend_policy='none'),checklist=[dict(text='Измерение',answer_kind='number',unit='бар',photo_required=True)]))
    assert configured.status_code==201,configured.text
    parsed=read_workbook(admin.get(PREFIX+'/registry/excel').content)
    values={name:[list(row.values()) for _,row in table(rows)] for name,rows in parsed.items() if name in ('Оборудование','Работы','Детали')}
    sheets={name:[headers]+values[name] for name,headers in [('Оборудование',EQ),('Работы',WORK),('Детали',PART)]}
    sheets['Работы'][1][WORK.index('Интервал')]='6'
    sheets['Работы'][1][WORK.index('Пункты регламента')]='Новое название измерения'
    checked=upload(admin,sheets)
    assert checked.status_code==200 and checked.json()['can_import'],checked.text
    imported=upload(admin,sheets,'/import',checked.json()['preview_token'])
    assert imported.status_code==200,imported.text
    current=admin.get(f"{PREFIX}/equipment/{eq['equipment_id']}/service-configurations").json()[0]
    assert current['pattern']['interval']==6 and current['enabled'] is False
    assert current['checklist'][0]['text']=='Новое название измерения'
    assert current['checklist'][0]['answer_kind']=='number' and current['checklist'][0]['unit']=='бар' and current['checklist'][0]['photo_required']


def test_import_allows_no_partial_writes_on_late_validation_error(managed):
    _,_,admin,_,ids=managed
    sheets=book(ids)
    sheets['Детали'][1][PART.index('Дата установки')]=(date.today()-timedelta(days=10)).isoformat()
    checked=upload(admin,sheets)
    assert checked.status_code==200,checked.text
    imported=upload(admin,sheets,'/import',checked.json()['preview_token'])
    assert imported.status_code==422,imported.text
    assert admin.get(PREFIX+'/registry').json()['items']==[]
    assert all(s['code']!='EXCEL' for s in admin.get(PREFIX+'/registry').json()['systems'])


def test_preview_reports_duplicate_asset_wrong_site_and_unconfirmed_resource(managed):
    _,_,admin,_,ids=managed
    sheets=book(ids)
    sheets['Оборудование'].append(sheets['Оборудование'][1][:])
    sheets['Детали'][1][PART.index('Источник ресурса')]=''
    checked=upload(admin,sheets)
    assert checked.status_code==200,checked.text
    assert not checked.json()['can_import'] and len(checked.json()['errors'])==2
    sheets=book(ids);sheets['Оборудование'][1][0]='another-site'
    assert not upload(admin,sheets).json()['can_import']


def test_stale_preview_and_unversioned_overwrite_are_rejected(managed):
    _,_,admin,_,ids=managed
    eq=equipment(admin,ids)
    content=admin.get(PREFIX+'/registry/excel').content
    checked=upload(admin,content).json()
    admin.patch(f"{PREFIX}/equipment/{eq['equipment_id']}",json=dict(expected_revision=eq['revision'],name='Изменено параллельно'))
    assert upload(admin,content,'/import',checked['preview_token']).status_code==409
    tables=read_workbook(content)
    rows=table(tables['Оборудование'])
    rows[0][1]['Ревизия']=''
    content=write_workbook({'Оборудование':[EQ]+[[r.get(k,'') for k in EQ] for _,r in rows]})
    result=upload(admin,content)
    assert result.status_code==200 and not result.json()['can_import'],result.text


def test_original_customer_workbook_is_previewed_without_guessing_norms(managed):
    _,_,admin,_,_=managed
    content=(Path(__file__).resolve().parents[2]/'data/customer/intelligent_planning_2027.xlsx').read_bytes()
    checked=upload(admin,content)
    assert checked.status_code==200,checked.text
    data=checked.json()
    assert data['format']=='customer_schedule' and len(data['rows'])==8 and not data['can_import']
    assert data['warnings'] and admin.get(PREFIX+'/registry').json()['items']==[]


def test_xlsx_reader_bounds_and_inline_formula_like_text():
    content=write_workbook({'Оборудование':[['Название'],['=HYPERLINK("bad")']]})
    assert table(read_workbook(content)['Оборудование'])[0][1]['Название']=='=HYPERLINK("bad")'
    stream=BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as archive:archive.writestr('bomb.xml',b'0'*(21*1024*1024))
    import pytest
    with pytest.raises(ValueError,match='Слишком большой'):read_workbook(stream.getvalue())
    with pytest.raises(ValueError):read_workbook(b'not an xlsx')


def test_xlsx_native_date_cells_are_normalized_without_formula_evaluation():
    content=write_workbook({'Оборудование':[['Дата ввода'],['2026-11-01']]})
    source=ZipFile(BytesIO(content));stream=BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as target:
        for name in source.namelist():
            data=source.read(name)
            if name=='xl/worksheets/sheet1.xml':
                data=data.replace(b'<c r="A2" t="inlineStr"><is><t>2026-11-01</t></is></c>',b'<c r="A2" s="1"><v>46327</v></c>')
            target.writestr(name,data)
        target.writestr('xl/styles.xml','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
    from datetime import datetime
    expected=(datetime(1899,12,30)+timedelta(days=46327)).date().isoformat()
    assert table(read_workbook(stream.getvalue())['Оборудование'])[0][1]['Дата ввода']==expected
