"""Analyst corrections: real HTTP/PostgreSQL, isolated TEST fixtures only."""
from datetime import date,datetime,timedelta,timezone
from contextlib import closing
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from app.security.sessions import SQL_ROLES,has_role
from app.schemas.maintenance import CalendarPattern
from app.schemas.management import ServiceConfiguration
from app.scheduling.recurrence import occurrence_dates
from app.integration.analyst import workbook,ExecutionInput
from tests.backend.test_management import managed,join,equipment,config
from tests.backend.test_runtime_integration import runtime,PREFIX,login,TASK


def pattern(**kwargs):return CalendarPattern.model_validate_json(json.dumps(kwargs))

def test_four_business_roles_are_not_collapsed_into_administrator():
    assert SQL_ROLES['director']=='director'
    assert SQL_ROLES['executive']=='director'
    assert SQL_ROLES['chief_engineer']=='chief_engineer'
    assert has_role('engineer',('dispatcher',))
    assert has_role('chief_engineer',('engineer',))
    assert not has_role('director',('admin','dispatcher','engineer','executor'))
    assert not has_role('admin',('chief_engineer',))


def test_rolling_quarter_has_real_calendar_arithmetic_and_explicit_weekend_policy():
    p=pattern(frequency='quarter',anchor_date='2026-09-30',quarter_policy='rolling_months',weekend_policy='none')
    assert occurrence_dates(p,date(2026,12,1),date(2026,12,31))==[date(2026,12,30)]
    p=pattern(frequency='dates',anchor_date='2026-10-01',dates=['2026-10-04'],weekend_policy='next_workday')
    assert occurrence_dates(p,date(2026,10,4),date(2026,10,5))==[date(2026,10,5)]


def test_five_per_year_starts_at_commissioning_and_crosses_new_year():
    p=pattern(frequency='yearly_count',anchor_date='2026-10-01',count_per_year=5,annual_policy='from_anchor')
    assert occurrence_dates(p,date(2026,10,1),date(2027,9,30))==[date(2026,10,1)+timedelta(days=i*365//5) for i in range(5)]


def test_publication_rejects_unknown_norms_and_daily_advance():
    raw=config(date(2026,11,5));raw.update(enabled=False,norm_value=None,norm_unit='unconfirmed',duration_minutes=None,methodology_ref=None)
    draft=ServiceConfiguration.model_validate(raw)
    assert draft.norm_value is None
    assert draft.pattern.weekend_policy=='none' # explicit fixture policy survives
    with pytest.raises(ValidationError):ServiceConfiguration.model_validate(raw|dict(enabled=True))
    raw=config(date(2026,11,5));raw['pattern']=dict(frequency='day',anchor_date='2026-11-05')
    with pytest.raises(ValidationError):ServiceConfiguration.model_validate(raw|dict(allowed_lead_days=1))
    raw['code']='1.4'
    with pytest.raises(ValidationError):ServiceConfiguration.model_validate(raw|dict(crew_size=1))


def test_xlsx_is_real_xml_workbook_and_formula_text_stays_text():
    payload=workbook([['Операция','Показание'],['=HYPERLINK("bad")','<unsafe>']])
    with ZipFile(BytesIO(payload)) as z:
        for name in z.namelist():ElementTree.fromstring(z.read(name))
        xml=z.read('xl/worksheets/sheet1.xml').decode()
        assert '<f>' not in xml and 'inlineStr' in xml and '&lt;unsafe&gt;' in xml


def test_real_norms_need_separate_chief_approval_and_templates_have_46_items(managed):
    _,_,admin,login_user,ids=managed;eq=equipment(admin,ids);day=date.today()
    draft=admin.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(day,enabled=False,norm_value=None,norm_unit='unconfirmed',duration_minutes=None,methodology_ref=None))
    assert draft.status_code==201,draft.text
    assert draft.json()['enabled'] is False and draft.json()['norm_value'] is None
    assert admin.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(day,code='DENIED')).status_code==403
    accepted=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(day,code='CHIEF-APPROVED'))
    assert accepted.status_code==201 and accepted.json()['enabled'],accepted.text
    catalog=admin.chief.get(PREFIX+'/checklist-catalog')
    assert catalog.status_code==200,catalog.text
    assert [len(p['items']) for p in catalog.json()['profiles']]==[9,7,7,8,7,8]


def test_executive_readonly_and_cross_site_overview_requires_membership(managed):
    engine,_,admin,login_user,ids=managed
    user,address=join(managed,'director')
    with closing(login_user(address)) as director:
        assert director.get(PREFIX+'/ui/equipment').status_code==200
        assert director.get(PREFIX+'/overview').status_code==200
        assert director.post(PREFIX+'/management/systems',json=dict(code='DENIED',name='DENIED')).status_code==403
        assert director.get(PREFIX+'/overview').json()[0]['siteId']==str(ids['site'])


def test_incident_ai_unavailable_keeps_editable_draft_and_unknown_norms_block_task(managed):
    _,_,admin,login_user,ids=managed;eq=equipment(admin,ids)
    response=admin.chief.post(PREFIX+'/incidents',data=dict(equipment_id=eq['equipment_id'],description='TEST ONLY: inspection request'))
    assert response.status_code==201,response.text
    identity=response.json()['id']
    result=admin.chief.post(PREFIX+f'/incidents/{identity}/analyze')
    assert result.status_code==200 and result.json()['analysis']['status']=='unavailable',result.text
    draft=admin.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(date.today(),enabled=False,norm_value=None,norm_unit='unconfirmed',duration_minutes=None,methodology_ref=None)).json()
    result=admin.chief.post(PREFIX+f'/incidents/{identity}/create-task',json=dict(binding_id=draft['binding_id'],planned_date=date.today().isoformat(),reason='TEST ONLY'))
    assert result.status_code==422 and 'MISSING_APPROVED_METHOD' in result.text


def test_early_start_rejected_before_new_report_is_created(runtime):
    engine,app=runtime
    with engine.begin() as c:
        row=c.execute(text('SELECT status,revision,started_at FROM work_orders WHERE work_order_id=:id'),{'id':TASK}).mappings().one()
        entry=c.scalar(text('SELECT schedule_entry_id FROM work_orders WHERE work_order_id=:id'),{'id':TASK})
        prior=c.execute(text('SELECT earliest_date,planned_date,regulatory_deadline_on,regulatory_deadline_at FROM schedule_entries WHERE schedule_entry_id=:id'),{'id':entry}).mappings().one()
        report_ids=list(c.scalars(text('SELECT work_report_id FROM work_reports WHERE work_order_id=:id'),{'id':TASK}))
        count=c.scalar(text('SELECT count(*) FROM work_reports WHERE work_order_id=:id'),{'id':TASK})
        c.execute(text("UPDATE work_orders SET status='assigned' WHERE work_order_id=:id"),{'id':TASK})
        c.execute(text("UPDATE schedule_entries SET earliest_date=:future,planned_date=:future,regulatory_deadline_on=:future,regulatory_deadline_at=:end WHERE schedule_entry_id=:id"),dict(id=entry,future=date.today()+timedelta(days=3),end=datetime.now(timezone.utc)+timedelta(days=4)))
    try:
        with closing(login(app,'executor')) as client:
            response=client.post(PREFIX+f'/tasks/{TASK}/start',json={'expected_revision':row['revision']})
            assert response.status_code==409 and 'MAINTENANCE_WINDOW_NOT_OPEN' in response.text,response.text
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_reports WHERE work_order_id=:id'),{'id':TASK})==count
    finally:
        with engine.begin() as c:
            for identity in c.scalars(text('SELECT work_report_id FROM work_reports WHERE work_order_id=:id'),{'id':TASK}).all():
                if identity not in report_ids:c.execute(text('DELETE FROM work_reports WHERE work_report_id=:id'),dict(id=identity))
            c.execute(text('UPDATE work_orders SET status=:status,revision=:revision,started_at=:started WHERE work_order_id=:id'),dict(id=TASK,status=row['status'],revision=row['revision'],started=row['started_at']))
            c.execute(text('UPDATE schedule_entries SET earliest_date=:earliest_date,planned_date=:planned_date,regulatory_deadline_on=:regulatory_deadline_on,regulatory_deadline_at=:regulatory_deadline_at WHERE schedule_entry_id=:id'),dict(id=entry,**prior))


def test_failed_assignment_is_audited_without_creating_assignments(runtime):
    engine,app=runtime
    from tests.backend.test_runtime_integration import ASSIGNMENT_TASK
    with closing(login(app,'executor')) as client:
        result=client.post(PREFIX+f'/tasks/{ASSIGNMENT_TASK}/assign',json=dict(expected_revision=1,executor_ids=[str(__import__('uuid').uuid4())],start_at='2026-11-05T10:00:00+05:00',end_at='2026-11-05T11:00:00+05:00',reason='TEST forbidden request'))
        assert result.status_code==403,result.text
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='denied'"),dict(id=ASSIGNMENT_TASK))>=1


def test_incident_execution_measurements_acts_acceptance_and_reopen_keep_history(managed):
    engine,app,admin,login_user,ids=managed
    # The isolated TEST site uses a real IANA offset with enough time remaining in the local day.
    # This lifecycle case must not turn into WINDOW_TOO_SHORT late at night;
    # expiry/short-window rejection has separate tests and remains unchanged.
    from zoneinfo import ZoneInfo
    day=date.today()
    offsets=[('Etc/GMT'+('+' if offset<0 else '-')+str(abs(offset))) for offset in range(-12,15)]
    zone=next(name for name in offsets if datetime.now(ZoneInfo(name)).date()==day and 6<=datetime.now(ZoneInfo(name)).hour<=18)
    with engine.begin() as c:
        c.execute(text('UPDATE sites SET timezone=:zone WHERE site_id=:site'),dict(zone=zone,site=ids['site']))
    eq=equipment(admin,ids)
    # Norms are explicit TEST fixtures in a disposable database, never customer data.
    settings=config(day,code='TEST-PROTOCOL',required_acts=['instrument_comparison'],measurement_requirements=[dict(parameter_code='pressure',unit='bar',required=True,phases=['before','after'],minimum='0',maximum='10')],checklist=[dict(text='TEST visible inspection',photo_required=True,visual_verifiability='visible')])
    configured=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=settings)
    assert configured.status_code==201,configured.text
    people=[join(managed) for _ in range(2)]
    for person,_ in people:
        shift=admin.post(PREFIX+f'/management/staff/{person}/shifts',json=dict(label='TEST full-day shift',pattern=dict(frequency='day',anchor_date=day.isoformat()),valid_from=day.isoformat(),starts_local='00:00',ends_local='23:59'))
        assert shift.status_code==201,shift.text
    _,engineer_email=join(managed,'engineer')
    incident=admin.chief.post(PREFIX+'/incidents',data=dict(equipment_id=eq['equipment_id'],description='TEST ONLY controlled execution')).json()
    body=dict(binding_id=configured.json()['binding_id'],planned_date=day.isoformat(),reason='TEST ONLY approved method')
    created=admin.chief.post(PREFIX+f"/incidents/{incident['id']}/create-task",json=body)
    assert created.status_code==200,created.text
    task_id=created.json()['taskId']
    assert admin.chief.post(PREFIX+f"/incidents/{incident['id']}/create-task",json=body).json()['replayed'] is True
    with closing(login_user(engineer_email)) as engineer,closing(login_user(people[0][1])) as executor:
        context=engineer.get(PREFIX+f'/ui/tasks/{task_id}/assignment-context').json()
        preview=engineer.post(PREFIX+f'/tasks/{task_id}/assignment-preview',json=dict(expected_revision=context['expectedRevision'],start_local=context['defaultStartLocal'],end_local=context['defaultEndLocal']))
        assert preview.status_code==200 and preview.json()['status']=='ok',preview.text
        assigned=engineer.post(PREFIX+f'/tasks/{task_id}/assign',json=preview.json()['command'])
        assert assigned.status_code==200,assigned.text
        started=executor.post(PREFIX+f'/tasks/{task_id}/start',json=dict(expected_revision=assigned.json()['task']['revision']))
        assert started.status_code==200,started.text
        bundle=started.json();check=bundle['execution']['checklist'][0]['id']
        assert bundle['task']['instructions']=='Inspect configured pump'
        now=datetime.now(timezone.utc);begin=now-timedelta(minutes=1)
        actual=dict(started_at=begin.isoformat(),performed_at=now.isoformat(),person_hours='0.033')
        readings=[dict(equipment_id=eq['equipment_id'],parameter_code='pressure',value='3.2',unit='bar',measured_at=now.isoformat(),phase=p) for p in ('before','after')]
        payload=dict(expected_revision=bundle['task']['revision'],narrative='TEST ONLY factual protocol',answers={check:'done'},actual=actual,readings=readings)
        invalid=executor.put(PREFIX+f'/tasks/{task_id}/report',json=payload|dict(readings=[readings[0]|dict(unit='guessed_unit')]))
        assert invalid.status_code==422,invalid.text
        saved=executor.put(PREFIX+f'/tasks/{task_id}/report',json=payload)
        assert saved.status_code==200,saved.text
        bundle=saved.json();assert len(bundle['execution']['readings'])==2
        from tests.backend.test_runtime_integration import image_bytes
        for phase,seed in [('before',851),('after',852)]:
            uploaded=executor.post(PREFIX+f'/tasks/{task_id}/photos',data=dict(expected_revision=bundle['task']['revision'],checklist_item_id=check,phase=phase,view_key='TEST same view'),files={'file':('proof.png',image_bytes(seed),'image/png')})
            assert uploaded.status_code==200,uploaded.text
            bundle=uploaded.json()
        blocked=executor.post(PREFIX+f'/tasks/{task_id}/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert blocked.status_code==422 and 'акт' in blocked.text,blocked.text
        uploaded=executor.post(PREFIX+f'/tasks/{task_id}/acts',data=dict(expected_revision=bundle['task']['revision'],kind='instrument_comparison'),files={'file':('act.png',image_bytes(853),'image/png')})
        assert uploaded.status_code==200,uploaded.text
        bundle=uploaded.json()
        submitted=executor.post(PREFIX+f'/tasks/{task_id}/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert submitted.status_code==200,submitted.text
        bundle=submitted.json();report_id=bundle['execution']['id'];act=bundle['execution']['acts'][0]['id']
        assert executor.get(PREFIX+f'/photos/{act}').status_code==200
        reviewed=engineer.post(PREFIX+f'/tasks/{task_id}/review',json=dict(expected_revision=bundle['task']['revision'],execution_id=report_id,verdict='accepted',reason='TEST reviewed'))
        assert reviewed.status_code==422 and 'акт' in reviewed.text,reviewed.text
        verified=engineer.post(PREFIX+f'/tasks/{task_id}/acts/{act}/verify',json=dict(expected_revision=bundle['task']['revision'],reason='TEST inspected original instrument protocol'))
        assert verified.status_code==200,verified.text
        bundle=verified.json()
        accepted=engineer.post(PREFIX+f'/tasks/{task_id}/review',json=dict(expected_revision=bundle['task']['revision'],execution_id=report_id,verdict='accepted',reason='TEST reviewed',additional_evidence_refs=[act]))
        assert accepted.status_code==200,accepted.text
        old=accepted.json();assert old['task']['state']=='accepted'
        dashboard=engineer.get(PREFIX+'/overview')
        assert dashboard.status_code==200,dashboard.text
        summary=dashboard.json()[0]
        assert summary['jobs']==summary['accepted']==summary['slaEligible']==summary['slaOnTime']==1
        assert Decimal(summary['actualPersonHours'])==Decimal('0.033')
        assert Decimal(summary['plannedNormPersonHours'])==Decimal('2.000')
        assert sum(summary['loadPersonMinutes'].values())==120
        for kind in ('schedule','orders'):
            exported=engineer.get(PREFIX+f'/export.xlsx?year={day.year}&month={day.month}&kind={kind}')
            assert exported.status_code==200 and 'spreadsheetml.sheet' in exported.headers['content-type']
            with ZipFile(BytesIO(exported.content)) as archive:
                assert archive.testzip() is None and 'xl/worksheets/sheet1.xml' in archive.namelist()
        assert executor.get(PREFIX+f'/export.xlsx?year={day.year}&month={day.month}').status_code==403
        assert engineer.get(PREFIX+f'/export.xlsx?year={day.year}&month=13').status_code==422
        assert engineer.post(PREFIX+f'/tasks/{task_id}/reopen',json=dict(expected_revision=old['task']['revision'],reason='TEST denied')).status_code==403
        reopened=admin.chief.post(PREFIX+f'/tasks/{task_id}/reopen',json=dict(expected_revision=old['task']['revision'],reason='TEST controlled reopening'))
        assert reopened.status_code==200 and reopened.json()['task']['state']=='rework_required',reopened.text
        attempts=executor.get(PREFIX+f'/tasks/{task_id}/attempts').json()
        assert len(attempts)==1 and attempts[0]['id']==report_id and len(attempts[0]['photos'])==2
        with engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM acceptance_reviews WHERE work_order_id=:id AND decision='accepted'"),dict(id=task_id))==1
            assert c.scalar(text('SELECT completed_at FROM work_orders WHERE work_order_id=:id'),dict(id=task_id))==datetime.fromisoformat(actual['performed_at'])


def test_background_calendar_uses_approved_catalog_and_is_restart_idempotent(managed):
    engine,app,admin,_,ids=managed;eq=equipment(admin,ids);day=date.today()
    configured=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(day,code='TEST-DAILY',pattern=dict(frequency='day',anchor_date=day.isoformat(),weekend_policy='none')))
    assert configured.status_code==201,configured.text
    from uuid import uuid4
    identity=uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO schedule_plans(schedule_plan_id,site_id,period_year,period_month,created_by) VALUES (:id,:site,:year,:month,:user)"),dict(id=identity,site=ids['site'],year=day.year,month=day.month,user=ids['user']))
    # A draft approval is an explicit fixture; publication/approval still pass through the actual API.
    denied=admin.post(PREFIX+f'/plans/{identity}/approve',json=dict(expected_revision=1,reason='TEST denied'))
    assert denied.status_code==403
    approved=admin.chief.post(PREFIX+f'/plans/{identity}/approve',json=dict(expected_revision=1,reason='TEST approved catalog'))
    assert approved.status_code==200,approved.text
    from app.integration.scheduler import tick
    tick(app)
    with engine.connect() as c:
        before=list(c.scalars(text('SELECT work_order_id FROM work_orders WHERE site_id=:site ORDER BY work_order_id'),dict(site=ids['site'])))
        ai=list(c.scalars(text("SELECT output_snapshot->'canonical'->>'error_code' FROM forecast_runs WHERE site_id=:site AND method='ai'"),dict(site=ids['site'])))
        assert before and ai and set(ai)=={'AI_NOT_REQUESTED_AUTOMATIC_RUN'}
        assert c.scalar(text("SELECT count(*) FROM schedule_entries WHERE site_id=:site AND schedule_plan_id<>:id"),dict(site=ids['site'],id=identity))==0
    tick(app)
    with engine.connect() as c:assert list(c.scalars(text('SELECT work_order_id FROM work_orders WHERE site_id=:site ORDER BY work_order_id'),dict(site=ids['site'])))==before



from tests.backend.test_evidence_readiness import job


def test_overdue_events_are_durable_and_late_acceptance_requires_chief(job):
    engine,app,task,report=job
    deadline=datetime.now(timezone.utc)-timedelta(minutes=1)
    with engine.begin() as c:
        c.execute(text("UPDATE work_orders SET status='in_review',regulatory_deadline_at=:deadline WHERE work_order_id=:id"),dict(id=task,deadline=deadline))
        c.execute(text("UPDATE work_reports SET status='submitted',submitted_at=now() WHERE work_report_id=:id"),dict(id=report))
    from app.integration.scheduler import tick
    tick(app);tick(app)
    with engine.connect() as c:
        assert c.scalar(text('SELECT overdue_since_at FROM work_orders WHERE work_order_id=:id'),dict(id=task))==deadline
        assert c.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='overdue'"),dict(id=task))==1
        assert c.scalar(text("SELECT count(*) FROM maintenance_notifications n JOIN site_memberships m ON m.site_id=n.site_id AND m.user_id=n.user_id WHERE n.work_order_id=:id AND m.role='director'"),dict(id=task))==1
    with closing(login(app,'engineer')) as engineer,closing(login(app,'chief_engineer')) as chief:
        body=dict(expected_revision=1,execution_id=str(report),verdict='accepted',reason='TEST late acceptance')
        blocked=engineer.post(PREFIX+f'/tasks/{task}/review',json=body)
        assert blocked.status_code==409 and 'LATE_ACCEPTANCE_REQUIRES_CHIEF' in blocked.text,blocked.text
        authorized=chief.post(PREFIX+f'/tasks/{task}/late-authorization',json=dict(expected_revision=1,reason='TEST documented delay'))
        assert authorized.status_code==200,authorized.text
        accepted=engineer.post(PREFIX+f'/tasks/{task}/review',json=body|dict(expected_revision=authorized.json()['task']['revision']))
        assert accepted.status_code==200 and accepted.json()['task']['deadlineBreached'],accepted.text
        with engine.connect() as c:assert c.scalar(text('SELECT regulatory_deadline_at FROM work_orders WHERE work_order_id=:id'),dict(id=task))==deadline
    with closing(login(app,'director')) as director,closing(login(app,'engineer')) as engineer:
        own=director.get(PREFIX+'/notifications')
        assert own.status_code==200,own.text
        event=next(row for row in own.json() if row['taskId']==str(task))
        assert director.post(PREFIX+f"/notifications/{event['id']}/read").status_code==200
        assert director.post(PREFIX+f"/notifications/{event['id']}/read").status_code==200
        assert engineer.post(PREFIX+f"/notifications/{event['id']}/read").status_code==404
        assert next(row for row in director.get(PREFIX+'/notifications').json() if row['id']==event['id'])['readAt']


def test_contract_stub_early_ai_requires_chief_and_keeps_original_obligation(managed,monkeypatch):
    """Real HTTP/PostgreSQL; the AI proposal here is an explicit contract stub, not ML evidence."""
    engine,app,admin,login_user,ids=managed;eq=equipment(admin,ids)
    from zoneinfo import ZoneInfo
    with engine.connect() as connection:
        site_timezone=connection.scalar(text('SELECT timezone FROM sites WHERE site_id=:site'),dict(site=ids['site']))
    today=datetime.now(ZoneInfo(site_timezone)).date();due=today+timedelta(days=1)
    settings=config(today,code='TEST-EARLY',pattern=dict(frequency='dates',anchor_date=today.isoformat(),dates=[due.isoformat()],weekend_policy='none'))
    configured=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=settings)
    assert configured.status_code==201,configured.text
    import app.integration.planning as routes
    from app.integration.forecasting import calculate
    from app.orchestrator.forecast import forecast_result
    from uuid import uuid4
    def fixture(snapshot):
        return forecast_result(snapshot,uuid4(),'ai',status='ok',day=today,explanation='TEST CONTRACT STUB; not a real model prediction',model_ref='test-fixture:uncalibrated-v1')
    def comparison(snapshot,item,forecaster,**kwargs):return calculate(snapshot,item,forecaster,provider=fixture)
    monkeypatch.setattr(routes,'calculate',comparison)
    preview=admin.chief.get(PREFIX+f'/ui/calendar/preview?year={due.year}&month={due.month}').json()
    generated=admin.chief.post(PREFIX+'/calendar/generate',json=dict(year=due.year,month=due.month,preview_token=preview['generationToken'],idempotency_key=str(uuid4())))
    assert generated.status_code==200 and generated.json()['createdCount']==1,generated.text
    original=generated.json()['items'][0];run_id=original['comparison']['runId'];body=dict(selected_date=today.isoformat(),reason='TEST explicit preventive approval')
    _,address=join(managed,'engineer')
    with closing(login_user(address)) as engineer:
        assert engineer.post(PREFIX+f'/comparisons/{run_id}/confirm',json=body).status_code==403
    assert admin.chief.post(PREFIX+f'/comparisons/{run_id}/confirm',json=body|dict(selected_date=(due+timedelta(days=1)).isoformat())).status_code==422
    confirmed=admin.chief.post(PREFIX+f'/comparisons/{run_id}/confirm',json=body)
    assert confirmed.status_code==200 and confirmed.json()['extra_maintenance'],confirmed.text
    repeat=admin.chief.post(PREFIX+f'/comparisons/{run_id}/confirm',json=body)
    assert repeat.status_code==200 and repeat.json()['replayed'],repeat.text
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))==2
        assert c.scalar(text('SELECT regulatory_deadline_on FROM schedule_entries WHERE site_id=:site'),dict(site=ids['site']))==due
        assert c.scalar(text('SELECT work_order_id FROM work_orders WHERE schedule_entry_id IS NOT NULL AND site_id=:site'),dict(site=ids['site']))==__import__('uuid').UUID(original['taskId'])


def test_persisted_weekend_transfers_keep_all_source_dates_and_replay_without_duplicates(managed):
    engine,_,admin,_,ids=managed;eq=equipment(admin,ids);first=date(2027,1,1)
    configured=admin.chief.post(PREFIX+f"/equipment/{eq['equipment_id']}/service-configurations",json=config(first,code='TEST-TRANSFER',pattern=dict(frequency='day',anchor_date=str(first),weekend_policy='next_workday')))
    assert configured.status_code==201,configured.text
    preview=admin.chief.get(PREFIX+'/ui/calendar/preview?year=2027&month=1').json()
    rows=[r for r in preview['items'] if r['operationCode']=='TEST-TRANSFER']
    assert len(rows)==31 and len({r['id'] for r in rows})==31
    monday=[r for r in rows if r['occurrenceDate']=='2027-01-04']
    assert {r['sourceDate'] for r in monday}=={'2027-01-02','2027-01-03','2027-01-04'}
    from uuid import uuid4
    command=dict(year=2027,month=1,preview_token=preview['generationToken'],idempotency_key=str(uuid4()))
    generated=admin.chief.post(PREFIX+'/calendar/generate',json=command)
    assert generated.status_code==200 and generated.json()['createdCount']==31,generated.text
    repeated=admin.chief.post(PREFIX+'/calendar/generate',json=command|dict(idempotency_key=str(uuid4())))
    assert repeated.status_code==200 and repeated.json()['createdCount']==0 and repeated.json()['existingCount']==31,repeated.text
    with engine.connect() as c:
        records=c.execute(text('SELECT source_date,planned_date,sequence_no FROM schedule_entries WHERE site_id=:site ORDER BY source_date'),dict(site=ids['site'])).all()
        assert len(records)==31 and len({r.source_date for r in records})==31
        assert len({r.sequence_no for r in records if r.planned_date==date(2027,1,4)})==3
        assert records[-1].source_date==date(2027,1,31) and records[-1].planned_date==date(2027,2,1)
    matrix=admin.chief.get(PREFIX+'/schedule-matrix?year=2027&month=1').json()['rows'][0]
    assert matrix['transfers']['2027-01-31']=='2027-02-01'
    assert any(r['sourceDate']=='2027-01-31' for r in admin.chief.get(PREFIX+'/ui/calendar?year=2027&month=2').json())


def test_late_execution_requires_chief_and_preserves_original_deadline(job):
    engine,app,task,_=job
    deadline=datetime.now(timezone.utc)-timedelta(minutes=1)
    with engine.begin() as c:
        c.execute(text("UPDATE work_orders SET regulatory_deadline_at=:deadline WHERE work_order_id=:id"),dict(id=task,deadline=deadline))
        revision=c.scalar(text('SELECT revision FROM work_orders WHERE work_order_id=:id'),dict(id=task))
    body=dict(expected_revision=revision,until=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),reason='TEST chief-approved late execution')
    with closing(login(app,'engineer')) as engineer,closing(login(app,'chief_engineer')) as chief:
        assert engineer.post(PREFIX+f'/tasks/{task}/late-execution',json=body).status_code==403
        assert chief.post(PREFIX+f'/tasks/{task}/late-execution',json=body|dict(until=(datetime.now(timezone.utc)+timedelta(days=31)).isoformat())).status_code==422
        allowed=chief.post(PREFIX+f'/tasks/{task}/late-execution',json=body)
        assert allowed.status_code==200,allowed.text
        assert chief.post(PREFIX+f'/tasks/{task}/late-execution',json=body).status_code==409
    with engine.connect() as c:
        row=c.execute(text('SELECT regulatory_deadline_at,overdue_since_at,exception_context FROM work_orders WHERE work_order_id=:id'),dict(id=task)).one()
        assert row.regulatory_deadline_at==row.overdue_since_at==deadline
        assert row.exception_context['late_execution']['reason']==body['reason']


def test_bulk_read_all_notifications_is_scoped_idempotent_and_not_limited_to_page(managed):
    engine,app,admin,login_user,ids=managed
    user,address=join(managed,'director')
    with engine.begin() as c:
        c.execute(text("""INSERT INTO maintenance_notifications(site_id,user_id,event_key,message)
            SELECT :site,:user,'bulk-fixture-'||g,'TEST notification' FROM generate_series(1,125) g"""),dict(site=ids['site'],user=user))
        c.execute(text("""INSERT INTO maintenance_notifications(site_id,user_id,event_key,message)
            VALUES (:site,:user,'bulk-other-user','TEST other user')"""),dict(site=ids['site'],user=ids['user']))
    with closing(login_user(address)) as director:
        assert len(director.get(PREFIX+'/notifications').json())==100
        response=director.post(PREFIX+'/notifications/read-all')
        assert response.status_code==200, response.text
        assert response.json()=={'read':True,'count':125}
        assert director.post(PREFIX+'/notifications/read-all').json()=={'read':True,'count':0}
        director.headers.pop('X-CSRF-Token')
        assert director.post(PREFIX+'/notifications/read-all').status_code==403
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM maintenance_notifications WHERE site_id=:site AND user_id=:user AND read_at IS NULL'),dict(site=ids['site'],user=user))==0
        assert c.scalar(text("SELECT count(*) FROM maintenance_notifications WHERE site_id=:site AND user_id=:user AND read_at IS NULL"),dict(site=ids['site'],user=ids['user']))==1


def test_clear_all_notifications_is_scoped_idempotent_and_not_limited_to_page(managed):
    engine,app,admin,login_user,ids=managed
    user,address=join(managed,'director')
    with engine.begin() as c:
        c.execute(text("""INSERT INTO maintenance_notifications(site_id,user_id,event_key,message)
            SELECT :site,:user,'clear-fixture-'||g,'TEST notification' FROM generate_series(1,125) g"""),dict(site=ids['site'],user=user))
        c.execute(text("""INSERT INTO maintenance_notifications(site_id,user_id,event_key,message)
            VALUES (:site,:user,'clear-other-user','TEST other user')"""),dict(site=ids['site'],user=ids['user']))
    with closing(login_user(address)) as director:
        assert len(director.get(PREFIX+'/notifications').json())==100
        response=director.post(PREFIX+'/notifications/clear')
        assert response.status_code==200, response.text
        assert response.json()=={'cleared':True,'count':125}
        assert director.post(PREFIX+'/notifications/clear').json()=={'cleared':True,'count':0}
        director.headers.pop('X-CSRF-Token')
        assert director.post(PREFIX+'/notifications/clear').status_code==403
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM maintenance_notifications WHERE site_id=:site AND user_id=:user'),dict(site=ids['site'],user=user))==0
        assert c.scalar(text('SELECT count(*) FROM maintenance_notifications WHERE site_id=:site AND user_id=:user'),dict(site=ids['site'],user=ids['user']))==1


def test_delete_notification_restricts_owner_and_requires_csrf(managed):
    engine,app,admin,login_user,ids=managed
    user,address=join(managed,'director')
    with engine.begin() as c:
        identity=c.scalar(text("""INSERT INTO maintenance_notifications(site_id,user_id,event_key,message)
            VALUES (:site,:user,'delete-single-fixture','TEST notification') RETURNING notification_id"""),dict(site=ids['site'],user=user))
    with closing(login_user(address)) as director:
        assert admin.post(PREFIX+f'/notifications/{identity}/delete').status_code==404
        director.headers.pop('X-CSRF-Token')
        assert director.post(PREFIX+f'/notifications/{identity}/delete').status_code==403
        with closing(login_user(address)) as authenticated:
            result=authenticated.post(PREFIX+f'/notifications/{identity}/delete')
            assert result.status_code==200 and result.json()=={'deleted':True}
            assert authenticated.post(PREFIX+f'/notifications/{identity}/delete').status_code==404
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM maintenance_notifications WHERE notification_id=:id'),dict(id=identity))==0


def test_account_email_and_password_change_are_verified_and_scoped(managed):
    import os
    from fastapi.testclient import TestClient
    engine,app,admin,login_user,ids=managed
    user,address=join(managed,'director')
    old=os.environ['FIXRATE_TEST_PASSWORD']; new='New-password-for-test-123'
    with closing(login_user(address)) as director, closing(login_user(address)) as other_session:
        assert director.patch(PREFIX+'/users/me',json={'name':'Changed'}).status_code in (404,405)
        assert director.patch(PREFIX+'/users/me/email',json={'email':'bad','current_password':old}).status_code==422
        assert director.patch(PREFIX+'/users/me/email',json={'email':'new@example.test','current_password':'wrong'}).status_code==400
        other_email=admin.get('/api/v1/auth/session').json()['profile']['email']
        assert director.patch(PREFIX+'/users/me/email',json={'email':other_email,'current_password':old}).status_code==409
        changed=director.patch(PREFIX+'/users/me/email',json={'email':'new-'+ids['marker']+'@example.test','current_password':old})
        assert changed.status_code==200,changed.text
        assert director.get('/api/v1/auth/session').json()['profile']['email']==changed.json()['email']
        endpoint=PREFIX+'/users/me/password'
        assert director.post(endpoint,json={'current_password':'wrong','new_password':new,'password_confirmation':new}).status_code==400
        assert director.post(endpoint,json={'current_password':old,'new_password':new,'password_confirmation':'different'}).status_code==422
        assert director.post(endpoint,json={'current_password':old,'new_password':'short','password_confirmation':'short'}).status_code==422
        updated=director.post(endpoint,json={'current_password':old,'new_password':new,'password_confirmation':new})
        assert updated.status_code==200,updated.text
        assert director.get('/api/v1/auth/session').status_code==200
        assert other_session.get('/api/v1/auth/session').status_code==401
        director.headers.pop('X-CSRF-Token')
        assert director.patch(PREFIX+'/users/me/email',json={'email':'another@example.test','current_password':new}).status_code==403
        with TestClient(app) as fresh:
            assert fresh.post('/api/v1/auth/login',json={'email':changed.json()['email'],'password':old}).status_code==401
            assert fresh.post('/api/v1/auth/login',json={'email':changed.json()['email'],'password':new}).status_code==200
    with engine.connect() as c:
        assert c.scalar(text('SELECT full_name FROM users WHERE user_id=:id'),dict(id=ids['user']))=='Managed admin'
