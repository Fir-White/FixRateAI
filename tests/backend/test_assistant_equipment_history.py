"""Independent equipment service history oracles over disposable PostgreSQL.

Synthetic records are explicit reports/acceptance facts, not generated model
answers. The real endpoint performs authorization, period filtering and paging.
"""
from contextlib import closing
from uuid import uuid4
import json

import pytest
from sqlalchemy import event, text

from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed, equipment, join

BASE='/api/v1/assistant/workspace/equipment'
ACTUAL='2026-01-01T20:30:00+00:00'  # January 2 in Asia/Yekaterinburg.
SUBMITTED='2026-01-02T10:00:00+00:00'


@pytest.fixture
def history_case(managed):
    engine,_,client,_,ids=managed
    with engine.begin() as db:
        db.execute(text("UPDATE sites SET timezone='Asia/Yekaterinburg' WHERE site_id=:site"),dict(site=ids['site']))
    asset=equipment(client,{**ids,'marker':uuid4().hex})
    return managed,asset


def add_report(case,asset,*,task=None,attempt=1,actual=ACTUAL,submitted=SUBMITTED,
               acceptance='accepted',decision_actual=None,order_started='2030-01-01T00:00:00+00:00'):
    engine,_,_,_,ids=case;identity=uuid4()
    with engine.begin() as db:
        if task is None:
            task=uuid4()
            db.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
                required_people_snapshot,norm_hours_snapshot,operation_snapshot,started_at)
                VALUES (:task,:site,:system,'manual',:state,1,1,'{}',:started)"""),
                dict(task=task,site=ids['site'],system=ids['system'],state='completed' if acceptance=='accepted' else 'in_review',started=order_started))
            db.execute(text('''INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
                VALUES (:site,:system,:task,:asset)'''),dict(site=ids['site'],system=ids['system'],task=task,asset=asset['equipment_id']))
        context={'performed_at':actual} if actual is not None else {}
        db.execute(text('''INSERT INTO work_reports(work_report_id,site_id,work_order_id,revision_no,submitted_by,
            status,submitted_at,execution_context) VALUES (:report,:site,:task,:attempt,:user,:state,:submitted,CAST(:context AS jsonb))'''),
            dict(report=identity,site=ids['site'],task=task,attempt=attempt,user=ids['user'],
                 state='reviewed' if acceptance else 'submitted',submitted=submitted,context=json.dumps(context)))
        if acceptance:
            reviewer=db.scalar(text("SELECT user_id FROM site_memberships WHERE site_id=:site AND role='chief_engineer'"),dict(site=ids['site']))
            db.execute(text('''INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,
                decision,reviewed_at,decision_context) VALUES (:site,:task,:report,:reviewer,:decision,
                '2026-01-03T12:00:00+00:00',CAST(:context AS jsonb))'''),
                dict(site=ids['site'],task=task,report=identity,reviewer=reviewer,decision=acceptance,
                     context=json.dumps({'performed_at':decision_actual} if decision_actual is not None else {})))
    return task,str(identity)


def history(client,asset,**params):
    response=client.get(BASE+f"/{asset['equipment_id']}/history",params={
        'starts_on':'2026-01-02','ends_on':'2026-01-02',**params})
    assert response.status_code==200,response.text
    return response.json()


def test_actual_report_date_uses_object_timezone_and_acceptance_for_exact_attempt(history_case):
    case,asset=history_case;client=case[2]
    _,expected=add_report(case,asset)
    # Earlier local day: excluded even when submitted during the requested day.
    add_report(case,asset,actual='2026-01-01T18:59:59+00:00')
    # The next local day starts at 19:00 UTC, not midnight UTC.
    add_report(case,asset,actual='2026-01-02T19:00:00+00:00')
    result=history(client,asset)
    assert result['total']==1 and [row['report_id'] for row in result['items']]==[expected]
    assert result['timezone']=='Asia/Yekaterinburg' and result['complete'] is True
    assert result['items'][0]['accepted_at'] is not None
    assert result['manufacturer_unverified'] is True


def test_mutable_task_start_never_moves_prior_report_attempts_between_periods(history_case):
    case,asset=history_case;engine,_,client,_,ids=case
    task,first=add_report(case,asset,actual='2025-01-02T06:00:00+00:00',submitted='2025-01-03T06:00:00+00:00')
    _,second=add_report(case,asset,task=task,attempt=2,actual=ACTUAL)
    result=history(client,asset)
    assert result['total']==1 and result['items'][0]['report_id']==second
    prior=history(client,asset,starts_on='2025-01-02',ends_on='2025-01-02')
    assert prior['total']==1 and prior['items'][0]['report_id']==first
    with engine.begin() as db:
        db.execute(text("UPDATE work_orders SET started_at='2040-01-01T00:00:00Z' WHERE site_id=:site AND work_order_id=:task"),dict(site=ids['site'],task=task))
    changed=history(client,asset)
    assert [row['report_id'] for row in changed['items']]==[second]


def test_rework_attempt_does_not_inherit_acceptance_from_later_attempt(history_case):
    case,asset=history_case;client=case[2]
    task,rejected=add_report(case,asset,acceptance='rework')
    _,accepted=add_report(case,asset,task=task,attempt=2)
    result=history(client,asset)
    assert result['total']==1 and result['items'][0]['report_id']==accepted
    all_reports=history(client,asset,only_accepted=False)
    assert all_reports['total']==2
    assert {row['report_id'] for row in all_reports['items']}=={accepted,rejected}
    rejected_row=next(row for row in all_reports['items'] if row['report_id']==rejected)
    assert rejected_row['accepted_at'] is None
    assert len({row['report_id'] for row in all_reports['items']})==len(all_reports['items'])


def test_other_equipment_and_unaccepted_reports_are_not_certified_as_accepted(history_case):
    case,asset=history_case;client=case[2]
    _,expected=add_report(case,asset)
    _,unaccepted=add_report(case,asset,acceptance=None)
    other=equipment(client,{**case[4],'marker':uuid4().hex})
    _,foreign_report=add_report(case,other)
    accepted=history(client,asset)
    assert [row['report_id'] for row in accepted['items']]==[expected]
    all_reports=history(client,asset,only_accepted=False)
    assert {row['report_id'] for row in all_reports['items']}=={expected,unaccepted}
    assert foreign_report not in json.dumps(all_reports)


def test_submission_only_and_undated_records_remain_explicitly_partial(history_case):
    case,asset=history_case;client=case[2]
    _,fallback=add_report(case,asset,actual=None)
    _,undated=add_report(case,asset,actual=None,submitted=None,order_started=None)
    result=history(client,asset)
    assert result['total']==1 and result['items'][0]['report_id']==fallback
    assert result['undated_count']==1 and result['complete'] is False
    assert result['items'][0]['actual_date_verified'] is False
    assert result['items'][0]['date_basis']=='submission_only'
    assert undated not in {row['report_id'] for row in result['items']}


def test_acceptance_execution_date_can_prove_missing_report_actual_date(history_case):
    case,asset=history_case;client=case[2]
    _,expected=add_report(case,asset,actual=None,decision_actual=ACTUAL,
                          submitted='2026-02-01T10:00:00+00:00')
    result=history(client,asset)
    assert result['total']==1 and result['items'][0]['report_id']==expected
    assert result['items'][0]['actual_date_verified'] is True and result['complete'] is True


@pytest.mark.parametrize('invalid_actual',['not-a-time','2026-99-99T25:61:00Z','2026-02-30T10:00:00Z',
                                         {'unexpected':'object'},'2026-01-02T10:00:00'])
def test_malformed_actual_context_falls_back_without_false_verification_or_500(history_case,invalid_actual):
    case,asset=history_case;client=case[2]
    _,expected=add_report(case,asset,actual=invalid_actual)
    result=history(client,asset)
    assert result['total']==1 and result['items'][0]['report_id']==expected
    assert result['items'][0]['actual_date_verified'] is False
    assert result['complete'] is False


def test_history_pagination_has_no_missing_or_duplicate_reports(history_case):
    case,asset=history_case;client=case[2]
    expected={add_report(case,asset)[1] for _ in range(31)}
    first=history(client,asset);second=history(client,asset,offset=25)
    assert first['total']==second['total']==31
    assert len(first['items'])==25 and len(second['items'])==6
    assert first['complete'] is False and first['page_complete'] is False
    found=[row['report_id'] for row in first['items']+second['items']]
    assert len(found)==len(set(found))==31 and set(found)==expected


def test_executor_only_sees_reports_of_own_active_assignments(history_case):
    case,asset=history_case;engine,_,client,login,ids=case
    own_task,own_report=add_report(case,asset)
    _,other_report=add_report(case,asset)
    other_asset=equipment(client,{**ids,'marker':uuid4().hex})
    add_report(case,other_asset)
    worker,address=join(case)
    with engine.begin() as db:
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            VALUES (:site,:task,:worker,:actor)'''),dict(site=ids['site'],task=own_task,worker=worker,actor=ids['user']))
    with closing(login(address)) as executor:
        result=history(executor,asset)
        assert result['total']==1 and result['items'][0]['report_id']==own_report
        assert other_report not in json.dumps(result)
        denied=executor.get(BASE+f"/{other_asset['equipment_id']}/history",params=dict(starts_on='2026-01-02',ends_on='2026-01-02'))
        assert denied.status_code==404,denied.text
        with engine.begin() as db:
            db.execute(text("UPDATE work_assignments SET status='cancelled' WHERE site_id=:site AND work_order_id=:task"),dict(site=ids['site'],task=own_task))
        denied=executor.get(BASE+f"/{asset['equipment_id']}/history",params=dict(starts_on='2026-01-02',ends_on='2026-01-02'))
        assert denied.status_code==404,denied.text


def test_foreign_site_uuid_cannot_expand_history_scope(history_case):
    case,asset=history_case;engine,_,client,_,ids=case
    add_report(case,asset)
    with engine.connect() as db:
        foreign=db.scalar(text('SELECT equipment_id FROM equipment WHERE site_id<>:site LIMIT 1'),dict(site=ids['site']))
    assert foreign is not None
    response=client.get(BASE+f'/{foreign}/history',params=dict(starts_on='2026-01-02',ends_on='2026-01-02'))
    assert response.status_code==404,response.text
    injected=client.get(BASE+f"/{asset['equipment_id']}/history",params=dict(
        starts_on='2026-01-02',ends_on='2026-01-02',site_id=str(uuid4())))
    assert injected.status_code in (200,422),injected.text
    if injected.status_code==200:
        assert injected.json()['equipment_id']==asset['equipment_id'] and injected.json()['total']==1


def test_history_read_has_fixed_query_count_and_no_domain_writes(history_case):
    case,asset=history_case;engine,_,client,_,ids=case
    add_report(case,asset)
    def capture():
        queries=[]
        def before(conn,cursor,statement,parameters,context,many):
            if statement.lstrip().upper().startswith(('SELECT','WITH')):
                queries.append(statement)
        event.listen(engine,'before_cursor_execute',before)
        try:result=history(client,asset)
        finally:event.remove(engine,'before_cursor_execute',before)
        return len(queries),result
    small,_=capture()
    for _ in range(30):add_report(case,asset)
    def fingerprints():
        with engine.connect() as db:
            return {table:db.scalar(text('SELECT md5(string_agg(to_jsonb(row)::text,\'|\' ORDER BY to_jsonb(row)::text)) FROM '+table+' row WHERE site_id=:site'),dict(site=ids['site']))
                    for table in ('equipment','work_orders','work_reports','acceptance_reviews','work_order_equipment')}
    before=fingerprints();large,result=capture();after=fingerprints()
    assert large==small and large<=7,(small,large)
    assert result['total']==31 and before==after


@pytest.mark.parametrize('query',[
    {'starts_on':'2026-02-01','ends_on':'2026-01-01'},
    {'starts_on':'2000-01-01','ends_on':'2026-01-01'},
    {'starts_on':'2026-01-02','ends_on':'2026-01-02','offset':-1},
    {'starts_on':'2026-01-02','ends_on':'2026-01-02','only_accepted':'invalid'},
])
def test_invalid_history_period_and_pagination_are_rejected(history_case,query):
    case,asset=history_case
    response=case[2].get(BASE+f"/{asset['equipment_id']}/history",params=query)
    assert response.status_code==422,response.text
