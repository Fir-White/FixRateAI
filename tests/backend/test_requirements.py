"""A bounded common ledger, real source scope, and no live-schedule writes."""
from contextlib import closing
from datetime import date,datetime,timezone
from decimal import Decimal
import json
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import text,event
from app.scheduling.generator import generate_binding_period
from app.scheduling.schemas import SchedulingBinding
from app.scheduling.recurrence import occurrence_pairs
from app.schemas.maintenance import CalendarPattern
from tests.backend.test_scheduling import payload,event as accepted_event
from tests.backend.test_management import managed,equipment,config
from tests.backend.test_runtime_integration import runtime,login,PREFIX
from tests.backend.test_draft_plans import prepare

PATH=PREFIX+'/planning-requirements/preview'
YEAR=dict(starts_on='2027-01-01',ends_on='2027-12-31')

def setup_rule(managed,**changes):
    _,_,admin,_,ids=managed;eq=equipment(admin,ids)
    response=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(date(2027,1,10),**changes))
    assert response.status_code==201,response.text
    return admin,eq,response.json()

@pytest.mark.parametrize('frequency',['day','week','month','quarter','year','yearly_count','dates'])
def test_period_keeps_the_seven_calendar_semantics_and_stable_source_dates(frequency):
    data=payload();pattern=dict(frequency=frequency,anchor_date='2027-01-01',interval=1,weekend_policy='none')
    if frequency=='yearly_count':pattern['count_per_year']=5
    if frequency=='dates':pattern['dates']=['2027-01-05','2027-12-17']
    data['bindings'][0]['rule'].update(kind='calendar_pattern',interval=None,calendar_unit=None,anchor_date=None,basis=None,
        yearly_count=None,explicit_dates=[],pattern=pattern)
    binding=SchedulingBinding.model_validate_json(json.dumps(data['bindings'][0]))
    start,end=date(2027,1,1),date(2027,12,31);now=datetime(2026,12,1,tzinfo=timezone.utc)
    result=generate_binding_period(binding,start,end,now,ZoneInfo('UTC'))[0]
    expected=occurrence_pairs(CalendarPattern.model_validate_json(json.dumps(pattern)),start,end)
    assert [(x.occurrence.source_date,x.occurrence.occurrence_date) for x in result.occurrences]==expected
    assert result==generate_binding_period(binding,start,end,now,ZoneInfo('UTC'))[0]

def test_period_completion_basis_keeps_only_one_actual_next_due_and_ignores_future_acceptance():
    data=payload(calendar_unit='month',interval=3,basis='after_accepted_completion')
    data['bindings'][0]['accepted_events']=[accepted_event('2026-10-31T09:00:00+05:00','2026-11-02T09:00:00+05:00'),
        accepted_event('2027-01-30T09:00:00+05:00','2027-02-01T09:00:00+05:00')]
    binding=SchedulingBinding.model_validate_json(json.dumps(data['bindings'][0]))
    result=generate_binding_period(binding,date(2027,1,1),date(2027,12,31),datetime(2026,12,1,tzinfo=timezone.utc),ZoneInfo('Asia/Yekaterinburg'))[0]
    assert [x.occurrence.occurrence_date for x in result.occurrences]==[date(2027,1,31)]
    assert 'HISTORY_AFTER_CUTOFF_IGNORED' in result.warnings

def test_common_ledger_combines_catalog_and_active_rules_without_touching_schedule(managed):
    engine,_,_,_,ids=managed;admin,eq,_,_,_,catalog=prepare(managed)
    rule_asset=equipment(admin,ids|dict(marker=ids['marker']+'-rules'))
    configured=admin.chief.post(PREFIX+f"/equipment/{rule_asset['equipment_id']}/service-configurations",json=config(date(2027,2,15)))
    assert configured.status_code==201,configured.text
    tables=('schedule_plans','schedule_entries','work_orders','work_assignments','planning_draft_versions','draft_publication_proposals')
    with engine.connect() as c:before={t:c.scalar(text(f'SELECT count(*) FROM {t} WHERE site_id=:site'),ids) for t in tables}
    body=YEAR|dict(catalog=catalog);response=admin.post(PATH,json=body)
    assert response.status_code==200,response.text
    data=response.json();assert data['summary']['total']==2 and data['summary']['source_counts']==dict(regulation=1,catalog=1)
    assert Decimal(data['summary']['known_person_hours'])==5 and Decimal(data['summary']['total_person_hours'])==5
    assert data['summary']['selected_catalog_rows']==1 and data['summary']['unselected_catalog_rows']==216
    assert {x['source_kind'] for x in data['items']}=={'regulation','catalog'}
    assert data['source_sha256']==admin.post(PATH,json=body|dict(q='pump',offset=0)).json()['source_sha256']
    assert not data['ready_for_real_plan']
    with engine.connect() as c:assert before=={t:c.scalar(text(f'SELECT count(*) FROM {t} WHERE site_id=:site'),ids) for t in tables}

def test_unapproved_or_missing_norm_is_unknown_not_zero_and_changes_the_snapshot(managed):
    engine,_,_,_,ids=managed;admin,_,configured=setup_rule(managed)
    before=admin.post(PATH,json=YEAR).json()
    with engine.begin() as c:c.execute(text('UPDATE maintenance_rules SET norm_hours=NULL WHERE site_id=:site'),ids)
    response=admin.post(PATH,json=YEAR);assert response.status_code==200,response.text
    data=response.json();assert data['summary']['total_person_hours'] is None and data['summary']['unknown_hours_count']==1
    assert any('Managed pump' in x['source_label'] for x in data['issues'])
    assert data['items'][0]['person_hours'] is None and data['source_sha256']!=before['source_sha256']
    with engine.begin() as c:c.execute(text("UPDATE maintenance_rules SET publication_status='draft' WHERE site_id=:site"),ids)
    data=admin.post(PATH,json=YEAR).json()
    assert data['summary']['total']==0 and not data['summary']['complete'] and data['summary']['total_person_hours'] is None
    assert 'RULE_UNCONFIRMED' in {x['code'] for x in data['issues']}

def test_roles_foreign_binding_horizon_and_no_client_history_injection(managed):
    _,app,admin,_,_=managed
    assert admin.post(PATH,json=YEAR).json()['summary']['total_person_hours'] is None
    with closing(login(app,'executor')) as executor:assert executor.post(PATH,json=YEAR).status_code==403
    assert admin.post(PATH,json=YEAR|dict(binding_ids=[str(uuid4())])).status_code==404
    assert admin.post(PATH,json=YEAR|dict(ends_on='2028-01-02')).status_code==422
    assert admin.post(PATH,json=YEAR|dict(as_of='2099-01-01T00:00:00Z')).status_code==422
    assert admin.post(PATH,json=YEAR|dict(include_regulations=False)).status_code==422

def test_paging_search_and_sql_count_do_not_scale_per_binding(managed):
    engine,_,_,_,ids=managed
    admin,_,_=setup_rule(managed,pattern=dict(frequency='day',anchor_date='2027-01-01',interval=1,weekend_policy='none'),
        valid_from='2027-01-01',maintenance_type='ТО1')
    statements=[]
    def count(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:response=admin.post(PATH,json=YEAR)
    finally:event.remove(engine,'before_cursor_execute',count)
    assert response.status_code==200,response.text
    data=response.json();assert data['total']==365 and len(data['items'])==25 and len(statements)<=22,len(statements)
    page=admin.post(PATH,json=YEAR|dict(offset=25)).json()
    assert data['items'][0]['requirement_id']!=page['items'][0]['requirement_id']
    assert data['summary']==page['summary'] and data['source_sha256']==page['source_sha256']
    assert admin.post(PATH,json=YEAR|dict(q='definitely missing')).json()['total']==0

def history_task(managed,binding_id,*,performed='2026-10-31T04:00:00+00:00',accepted='2026-11-02T04:00:00+00:00'):
    engine,_,_,_,ids=managed;task,report,plan,entry=uuid4(),uuid4(),uuid4(),uuid4()
    params=ids|dict(binding=binding_id,task=task,report=report,plan=plan,entry=entry,performed=performed,accepted=accepted)
    with engine.begin() as c:
        rule=c.scalar(text('SELECT maintenance_rule_id FROM rule_equipment WHERE binding_id=:binding'),params);params['rule']=rule
        c.execute(text("UPDATE equipment SET commissioned_on='2026-01-01' WHERE site_id=:site"),ids)
        c.execute(text("INSERT INTO schedule_plans(schedule_plan_id,site_id,period_year,period_month,created_by) VALUES (:plan,:site,2026,10,:user)"),params)
        c.execute(text("""INSERT INTO schedule_entries(schedule_entry_id,site_id,system_id,schedule_plan_id,maintenance_rule_id,binding_id,planned_date,source_date,regulatory_deadline_on,regulatory_deadline_at)
            VALUES (:entry,:site,:system,:plan,:rule,:binding,'2026-10-31','2026-10-31','2026-10-31','2026-11-01T00:00:00Z')"""),params)
        c.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,maintenance_rule_id,schedule_entry_id,status,required_people_snapshot,norm_hours_snapshot,completed_at)
            VALUES (:task,:site,:system,:rule,:entry,'completed',2,2,CAST(:performed AS timestamptz))"""),params)
        c.execute(text('''INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
            SELECT site_id,system_id,:task,equipment_id FROM rule_equipment WHERE binding_id=:binding'''),params)
        c.execute(text("INSERT INTO work_reports(work_report_id,site_id,work_order_id,submitted_by,status) VALUES (:report,:site,:task,:user,'reviewed')"),params)
        c.execute(text("""INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision,reviewed_at,decision_context)
            VALUES (:site,:task,:report,:user,'accepted',CAST(:accepted AS timestamptz),jsonb_build_object('performed_at',CAST(:performed AS text)))"""),params)
    return task

def test_real_accepted_history_drives_only_the_next_rolling_requirement(managed):
    admin,_,configured=setup_rule(managed,pattern=dict(frequency='month',anchor_date='2026-11-30',interval=3,weekend_policy='none'),
        basis='after_accepted_completion',valid_from='2026-01-01')
    history_task(managed,configured['binding_id'])
    response=admin.post(PATH,json=YEAR);assert response.status_code==200,response.text
    data=response.json();assert data['summary']['total']==1 and data['items'][0]['due_date']=='2027-01-31'
    assert data['items'][0]['state']=='new' and '2026-10-31' in data['items'][0]['explanation']
    assert 'ROLLING_NEXT_OCCURRENCE_ONLY' in data['items'][0]['issues']

def test_saved_catalog_tasks_are_not_offered_again_even_when_interpretation_changes(managed):
    from tests.backend.test_publication import prepared,approve,publishing,PATH as PUBLICATIONS
    from tests.backend.test_catalog_decisions import write
    engine,_,_,_,ids=managed;admin,record,proposal,_,_=prepared(managed)
    proposal=approve(admin,proposal)
    assert admin.chief.post(PUBLICATIONS+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    with engine.connect() as c:
        input_data=c.scalar(text("SELECT source_snapshot->'input' FROM planning_draft_versions WHERE draft_id=:id AND revision=:rev"),dict(id=record['draft_id'],rev=record['revision']))
    body=YEAR|dict(include_regulations=False,catalog=input_data)
    data=admin.post(PATH,json=body).json()
    assert data['summary']['total']==1 and data['items'][0]['state']=='existing'
    assert Decimal(data['summary']['new_person_hours'])==0
    all_sources=admin.post(PATH,json=body|dict(include_regulations=True)).json()
    assert all_sources['summary']['binding_count']==0 and all_sources['summary']['total']==1
    old_id=data['items'][0]['requirement_id'];import_id=input_data['import_id'];row=input_data['row_numbers'][0]
    path=PREFIX+f'/catalog-imports/{import_id}/operations/{row}/decision'
    decision=admin.get(path).json()
    response=write(admin.chief,import_id,row,dict(decision['decision'],interpretation='EQUIPMENT_BATCH'),decision['revision'],True)
    assert response.status_code==200,response.text
    response=admin.post(PATH,json=body);assert response.status_code==200,response.text
    updated=response.json();assert updated['items'][0]['requirement_id']!=old_id
    assert updated['items'][0]['state']=='existing' and updated['items'][0]['task_ids']==data['items'][0]['task_ids']

def test_accepted_and_cancelled_entries_are_classified_without_reissuing_work(managed):
    engine,_,_,_,ids=managed
    admin,_,configured=setup_rule(managed,pattern=dict(frequency='dates',anchor_date='2026-10-31',dates=['2026-10-31'],weekend_policy='none'),valid_from='2026-01-01')
    task=history_task(managed,configured['binding_id'])
    body=dict(starts_on='2026-10-01',ends_on='2026-10-31')
    response=admin.post(PATH,json=body);assert response.status_code==200,response.text
    data=response.json();assert data['items'][0]['state']=='fulfilled' and data['items'][0]['task_ids']==[str(task)]
    assert Decimal(data['summary']['new_person_hours'])==0
    with engine.begin() as c:c.execute(text('DELETE FROM acceptance_reviews WHERE site_id=:site'),ids)
    data=admin.post(PATH,json=body).json();assert data['items'][0]['state']=='review'
    assert 'COMPLETION_NOT_ACCEPTED' in data['items'][0]['issues']
    with engine.begin() as c:c.execute(text("UPDATE work_orders SET status='cancelled' WHERE work_order_id=:id"),dict(id=task))
    data=admin.post(PATH,json=body).json();assert data['items'][0]['state']=='review' and data['items'][0]['task_ids']==[str(task)]

def test_select_budget_is_constant_for_one_and_thirty_one_bindings(managed):
    engine,_,_,_,ids=managed;admin,eq,configured=setup_rule(managed)
    def read():
        queries=[]
        def count(conn,cursor,statement,parameters,context,many):
            if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
        event.listen(engine,'before_cursor_execute',count)
        try:response=admin.post(PATH,json=YEAR)
        finally:event.remove(engine,'before_cursor_execute',count)
        assert response.status_code==200,response.text
        return response.json(),len(queries)
    first,small=read()
    with engine.begin() as c:
        for index in range(30):
            asset=uuid4()
            c.execute(text('''INSERT INTO equipment SELECT (jsonb_populate_record(NULL::equipment,to_jsonb(e)||CAST(:overrides AS jsonb))).*
                FROM equipment e WHERE e.equipment_id=:id'''),dict(id=eq['equipment_id'],overrides=json.dumps(dict(equipment_id=str(asset),asset_code=f'TEST-COMMON-{index}'))))
            c.execute(text('''INSERT INTO rule_equipment SELECT (jsonb_populate_record(NULL::rule_equipment,to_jsonb(b)||CAST(:overrides AS jsonb))).*
                FROM rule_equipment b WHERE b.binding_id=:id'''),dict(id=configured['binding_id'],overrides=json.dumps(dict(binding_id=str(uuid4()),equipment_id=str(asset)))))
    large,big=read()
    assert first['summary']['total']==1 and large['summary']['total']==31
    assert big==small and big<=22
