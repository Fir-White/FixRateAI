"""Demand is not placement; overlapping jobs are not distinct available workers."""
from contextlib import closing
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text,event
from app.scheduling.draft_validator import validate
from app.scheduling.plan_load import project
from tests.backend.test_draft_plans import pure_case,moment,prepare,save,worker,BASE
from tests.backend.test_portfolio_plans import active_counts
from tests.backend.test_portfolio_publication import prepared_common
from tests.backend.test_publication import approve,publishing,PATH
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login


def pure(roots,segments,people,policy,start=date(2027,1,1),end=date(2027,1,10)):
    report=validate(roots,segments,people,policy,start,end,'UTC',moment(1))
    return project(roots,segments,people,policy,report,start,end,'UTC')


def test_exact_hours_and_concurrent_crews_do_not_add_sequential_headcounts():
    root,segments,people,policy=pure_case();data=pure([root],segments,people,policy)
    day=data['days'][1]
    assert day['planned_person_hours']==48 and day['reserved_person_hours']==48
    assert day['required_people_peak']==2 and day['selected_people_peak']==2 and day['available_people_peak']==2
    assert data['totals']['unplaced_person_hours']==0 and data['totals']['total_person_hours']==48
    assert sum(m['planned_person_hours'] for m in data['months'])==48


def test_overlapping_demands_count_one_selected_worker_only_once():
    root,segments,people,policy=pure_case()
    moved=segments[1].model_copy(update=dict(start_at=segments[0].start_at,end_at=segments[0].end_at))
    data=pure([root],[segments[0],moved],people,policy)
    assert data['days'][1]['required_people_peak']==4 and data['days'][1]['selected_people_peak']==2


def test_unplaced_volume_is_only_a_deadline_bucket_and_unknowns_are_not_zero():
    root,segments,people,policy=pure_case()
    pieces=[s.model_copy(update=dict(start_at=None,end_at=None,worker_ids=[])) for s in segments]
    data=pure([root],pieces,people,policy.model_copy(update=dict(capacity_confirmed=False)))
    assert data['totals']['unplaced_person_hours']==48 and data['totals']['available_person_hours'] is None
    assert sum(d['unplaced_due_person_hours'] for d in data['days'])==48
    assert all(d['required_people_peak']==0 and d['selected_people_peak']==0 and d['available_people_peak'] is None for d in data['days'])
    short=pure([root],pieces,people,policy,end=date(2027,1,5))
    assert short['totals']['unplaced_outside_view_person_hours']==48 and sum(m['due_person_hours'] for m in short['months'])==0


def test_load_reads_one_selected_version_without_live_writes_or_foreign_data(managed):
    engine,app,_,_,_=managed;admin,_,_,_,_,request=prepare(managed);record,_,_=save(admin,request)
    before=active_counts(engine);url=BASE+f"/{record['draft_id']}/load-preview?revision=1"
    response=admin.post(url);assert response.status_code==200,response.text
    data=response.json();assert Decimal(data['totals']['total_person_hours'])==3 and Decimal(data['totals']['unplaced_person_hours'])==3
    assert data['source_state']=='current' and data['published_tasks']==0 and len(data['days'])==365
    assert 'workers' not in data and 'resources' not in data
    assert active_counts(engine)==before
    with closing(login(app,'executor')) as person:assert person.post(url).status_code==403
    with closing(login(app,'chief_engineer')) as person:assert person.post(url).status_code==404


def test_published_plan_is_not_counted_against_its_own_bookings(managed):
    engine,_,_,_,_=managed;admin,record,proposal,_,_,_=prepared_common(managed)
    before=admin.post(BASE+f"/{record['draft_id']}/load-preview?revision={record['revision']}").json()
    proposal=approve(admin,proposal)
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    response=admin.post(BASE+f"/{record['draft_id']}/load-preview?revision={record['revision']}");assert response.status_code==200,response.text
    after=response.json();assert after['source_state']=='published_snapshot' and after['published_tasks']==1
    assert after['totals']==before['totals']
    assert after['validation_status']=='valid'


def test_alternative_plans_are_not_summed_and_select_count_is_constant(managed):
    engine,_,_,_,_=managed
    admin,_,_,_,_,request=prepare(managed,interpretation='FIXED_EXECUTION',calendar_pattern=dict(frequency='month',anchor_date='2027-01-10',interval=1,weekend_policy='none'))
    request['expansion']='confirmed_rule'
    month,_,_=save(admin,dict(request,ends_on='2027-01-31'));year,_,_=save(admin,request)
    def read(record):
        statements=[]
        def count(conn,cursor,statement,parameters,context,many):
            if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
        event.listen(engine,'before_cursor_execute',count)
        try:response=admin.post(BASE+f"/{record['draft_id']}/load-preview?revision=1")
        finally:event.remove(engine,'before_cursor_execute',count)
        assert response.status_code==200,response.text
        return response.json(),len(statements),len(response.content)
    small,n,_=read(month);large,m,size=read(year)
    assert Decimal(small['totals']['total_person_hours'])==3 and Decimal(large['totals']['total_person_hours'])==36
    assert n==m and m<=40,(n,m)
    assert size<200000 and len(large['days'])==365


def test_dst_day_uses_actual_elapsed_hours_without_losing_normative_volume():
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    from app.schemas.draft_plans import AllowedInterval
    from app.assignment.schemas import Availability
    root,segments,people,policy=pure_case();tz=ZoneInfo('Europe/Berlin')
    left=datetime(2027,10,31,tzinfo=tz);right=datetime(2027,11,1,tzinfo=tz);day=left.date()
    root=root.model_copy(update=dict(earliest_date=day,latest_date=day,source_date=day,total_person_hours=Decimal(25),crew_size=1,splittable=False,interpretation='ALLOWED_WINDOW',allowed_intervals=[AllowedInterval(start_at=left,end_at=right)]))
    person=people[0].model_copy(update=dict(availability=[Availability(start_at=left,end_at=right,status='available')]))
    segment=segments[0].model_copy(update=dict(person_hours=Decimal(25),start_at=left,end_at=right,worker_ids=[person.worker_id]))
    report=validate([root],[segment],[person],policy,day,day,str(tz),datetime(2027,10,1,tzinfo=timezone.utc))
    assert report.status=='valid',report
    result=project([root],[segment],[person],policy,report,day,day,str(tz))
    assert len(result['days'])==1 and result['days'][0]['planned_person_hours']==25 and result['days'][0]['available_person_hours']==25


def test_night_after_full_horizon_preserves_hours_and_partial_calendar_months():
    from datetime import datetime,timezone
    from app.schemas.draft_plans import AllowedInterval
    from app.assignment.schemas import Availability
    root,segments,people,policy=pure_case();start=date(2027,1,31);end=date(2028,1,31)
    left=datetime(2028,1,31,20,tzinfo=timezone.utc);right=datetime(2028,2,1,8,tzinfo=timezone.utc)
    root=root.model_copy(update=dict(earliest_date=end,latest_date=end,source_date=end,source_slot='night',total_person_hours=Decimal(4),crew_size=1,splittable=False,
        interpretation='ALLOWED_WINDOW',allowed_intervals=[AllowedInterval(start_at=left,end_at=right)]))
    person=people[0].model_copy(update=dict(availability=[Availability(start_at=datetime(2027,1,31,tzinfo=timezone.utc),end_at=right,status='available')]))
    segment=segments[0].model_copy(update=dict(person_hours=Decimal(4),start_at=left,end_at=right,worker_ids=[person.worker_id]))
    report=validate([root],[segment],[person],policy,start,end,'UTC',moment(1))
    assert report.status=='valid',report
    result=project([root],[segment],[person],policy,report,start,end,'UTC')
    assert len(result['days'])==367 and len(result['months'])==14
    assert result['months'][-1]['month']=='2028-02'
    assert sum(m['planned_person_hours'] for m in result['months'])==4
