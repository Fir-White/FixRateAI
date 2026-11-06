"""Owner-requested fictional operating profile, isolated from customer and QA data.

No ML responses are seeded. Re-running preserves workflow, accounts and results.
"""
from calendar import monthrange
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
import hashlib,json,os
from pathlib import Path
from uuid import UUID,uuid5,NAMESPACE_URL
from zoneinfo import ZoneInfo
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.db.models import map_schema
from app.db.repository import MaintenanceRepository
from app.security.sessions import Principal,hash_password
from app.schemas.management import ServiceConfiguration
from .projections import Views
from .management import save_service
from .calendar import _binding_payload,preview_calendar

ROOT=Path(__file__).resolve().parents[3]
ACCOUNTS=[
 ('director','Андрей Смирнов','director@fixrate.local'),
 ('chief_engineer','Сергей Волков','chief@fixrate.local'),
 ('engineer','Мария Орлова','engineer@fixrate.local'),
 ('executor','Алексей Морозов','technician@fixrate.local'),
 ('worker-2','Дмитрий Кузнецов','kuznetsov@fixrate.local'),
 ('worker-3','Павел Белов','belov@fixrate.local'),
]

def identity(key):return uuid5(NAMESPACE_URL,'fixrate:presentation:v1:'+('executive' if key == 'director' else key))
def safe(value):return json.loads(json.dumps(value,default=str,ensure_ascii=False))

def seed_presentation(engine,password,*,as_of=None,storage=None):
    now=as_of or datetime.now(timezone.utc);tz=ZoneInfo('Asia/Yekaterinburg');day=now.astimezone(tz).date()
    anchor=day.replace(year=day.year-3,day=min(day.day,monthrange(day.year-3,day.month)[1]))
    storage=Path(storage or os.environ.get('PHOTO_STORAGE_ROOT','var/photos'))
    models=map_schema(engine);site_id=identity('site');system_id=identity('system')
    accounts=[dict(role=role if role in ('director','chief_engineer','engineer') else 'executor',name=name,email=email,user_id=str(identity(role))) for role,name,email in ACCOUNTS]
    lock=engine.connect();lock.execute(text('SELECT pg_advisory_lock(6813061126)'));lock.commit()
    try:
        with Session(engine) as session:
            repo=MaintenanceRepository(session,models)
            def ensure(table,pk,key,**values):
                uid=identity(key);return repo.get(table,uid) or repo.add(table,**{pk:uid},**values)
            site=ensure('sites','site_id','site',name='ЖК «Сосновый парк»',address='Екатеринбург, улица Сосновая, 12',timezone='Asia/Yekaterinburg')
            ensure('engineering_systems','system_id','system',site_id=site_id,code='HEAT-01',name='Теплоснабжение',notes='synthetic_demo:presentation-v1')
            typ=ensure('equipment_types','equipment_type_id','type',code='HEAT-OPERATIONS',name='Оборудование теплового пункта',default_attributes={'data_origin':'synthetic_demo'})
            password_hash=hash_password(password)
            for role,name,email in ACCOUNTS:
                user=ensure('users','user_id',role,full_name=name,email=email,password_hash=password_hash)
                if not repo.get('site_memberships',(site_id,user.user_id)):
                    repo.add('site_memberships',site_id=site_id,user_id=user.user_id,role=role if role in ('director','chief_engineer','engineer') else 'technician',employed_from=anchor)
            skill=ensure('skills','skill_id','skill',code='HEAT-SERVICE',name='Обслуживание тепловых установок')
            crew=ensure('crews','crew_id','crew',site_id=site_id,name='Бригада теплового пункта')
            for role in ('executor','worker-2','worker-3'):
                uid=identity(role)
                if not repo.get('user_skills',(site_id,uid,skill.skill_id)):
                    repo.add('user_skills',site_id=site_id,user_id=uid,skill_id=skill.skill_id,verified_at=datetime.combine(anchor,time.min,tz))
                ensure('employee_shift_rules','shift_rule_id','shift-'+role,site_id=site_id,user_id=uid,label='Дежурство по объекту',calendar_pattern=dict(frequency='day',anchor_date=str(anchor),interval=1,weekend_policy='none'),valid_from=anchor,starts_local=time.min,ends_local=time(23,59))
                if role!='executor':ensure('crew_members','crew_member_id','crew-'+role,site_id=site_id,crew_id=crew.crew_id,user_id=uid,valid_from=anchor)
            equipment={}
            for key,code,name,location in [
                ('point','ИТП-01','Индивидуальный тепловой пункт','Корпус 1, технический этаж'),
                ('pump','НС-01','Насос циркуляционного контура','ИТП, насосная группа'),
                ('controller','ПУ-01','Контроллер системы отопления','ИТП, шкаф автоматики'),
                ('gauge','МН-01','Манометр контура отопления','ИТП, пост контрольного осмотра'),
                ('circuit','КТ-01','Контур отопления первого корпуса','Корпус 1, распределительный коллектор')]:
                equipment[key]=ensure('equipment','equipment_id',key,site_id=site_id,system_id=system_id,equipment_type_id=typ.equipment_type_id,
                    parent_equipment_id=identity('point') if key!='point' else None,asset_code=code,name=name,location=location,commissioned_on=anchor,
                    properties={'data_origin':'synthetic_demo','profile':'presentation-v1'})
            session.commit()
            chief=accounts[1];principal=Principal(identity('chief_engineer'),site_id,'chief_engineer',chief['name'],chief['email'],site.name,site.timezone)
            v=Views(session,models,principal)
            profiles=json.loads((Path(__file__).resolve().parents[1]/'data/checklist_catalog.json').read_text(encoding='utf-8'))['profiles']
            bindings={};settings={}
            for index,profile in enumerate(profiles):
                code=profile['operation_code'];key=['point','point','controller','pump','gauge','circuit'][index];eq=equipment[key]
                old=[b for b in v.rows('rule_equipment',equipment_id=eq.equipment_id) if b.rule.operation.code==code]
                if not old:
                    checks=[]
                    for item in profile['items']:
                        setting=dict(item['setting']);setting['source_item_key']=item['item_key'];setting['source_refs']=[f"analyst:{r['source_id']}:L{r['line_start']}-L{r['line_end']}" for r in item['source_refs']]
                        if setting['answer_kind']=='number':setting['unit']={'temperature':'°C','reading':'м³'}.get(item['item_key'],'бар')
                        checks.append(setting)
                    frequency='day' if index<3 else 'yearly_count' if index==3 else 'quarter'
                    pattern=dict(frequency=frequency,anchor_date=str(anchor),interval=1,quarter_policy='rolling_months',annual_policy='from_anchor',weekend_policy='next_workday')
                    if frequency=='yearly_count':pattern['count_per_year']=5
                    data=dict(code=code,title=profile['title'],instructions=f"Выполнить {profile['title'].lower()}. Зафиксировать результаты осмотра и замечания по каждому пункту технологической карты.",
                        maintenance_type=profile['maintenance_type'],pattern=pattern,valid_from=str(anchor),crew_size=2 if index==3 else 1,
                        norm_value=['0.25','0.25','0.5','3','1','0.5'][index],norm_unit='person_hour',duration_minutes=[15,15,30,90,60,30][index],
                        qualification_ids=[str(skill.skill_id)],checklist=checks,allowed_lead_days=0,enabled=True,
                        methodology_ref='ЭК-ТП-'+code+' / редакция 1',required_acts=['Протокол сравнения с контрольным прибором'] if code=='1.5' else [])
                    save_service(v,eq.equipment_id,ServiceConfiguration.model_validate_json(json.dumps(data,ensure_ascii=False)))
                    old=[b for b in v.rows('rule_equipment',equipment_id=eq.equipment_id) if b.rule.operation.code==code]
                binding=old[0];bindings[code]=binding
                payload,error,_=_binding_payload(v,binding,binding.rule,eq,site)
                if error:raise RuntimeError(error)
                settings[code]=(payload,eq)
            session.commit()
            plan=ensure('schedule_plans','schedule_plan_id',f'plan-{day:%Y-%m}',site_id=site_id,period_year=day.year,period_month=day.month,revision=1,status='approved',created_by=identity('chief_engineer'),approved_by=identity('chief_engineer'),approved_at=now,source_snapshot={'data_origin':'synthetic_demo'})
            session.commit()
            def create_work(key,code,work_day,status,entry=None):
                if repo.get('work_orders',identity(key)):return repo.get('work_orders',identity(key))
                payload,eq=settings[code];op=payload['operation'];binding=bindings[code];rule=binding.rule
                checks=[dict(id=str(c['checklist_item_id']),text=c['text'],answerKind=c['answer_kind'],unit=c['unit'],required=c['required'],visualVerifiability=c['visual_verifiability'],photoRequired=c['photo_required']) for c in op['checklist']]
                begin=datetime.combine(work_day,time(8+int(code[-1])),tz);duration=rule.schedule_parameters['planning_duration_minutes']
                if status=='in_progress':begin=now-timedelta(minutes=duration)
                finish=begin+timedelta(minutes=duration);deadline=datetime.combine(work_day+timedelta(days=1),time.min,tz)
                snapshot=safe(dict(data_origin='synthetic_demo',profile='presentation-v1',code=code,title=op['title'],instructions=op['instructions'],maintenance_type=op['maintenance_type'],
                    operation_version=op['version'],norm_unit=op['norm_unit'],planning_duration_minutes=duration,duration_basis='configured:explicit-duration',qualification_ids=op['qualification_ids'],
                    methodology_ref=rule.schedule_parameters['methodology_ref'],required_acts=rule.schedule_parameters.get('required_acts',[]),measurement_requirements=[],checklist=checks))
                order=ensure('work_orders','work_order_id',key,site_id=site_id,system_id=system_id,maintenance_rule_id=rule.maintenance_rule_id,schedule_entry_id=entry.schedule_entry_id if entry else None,
                    status=status,origin='scheduled' if entry else 'manual',required_people_snapshot=rule.required_people,norm_hours_snapshot=rule.norm_hours,norm_hours_basis_snapshot='total_person_hours',
                    operation_snapshot=snapshot,planned_start_at=begin,planned_end_at=finish,regulatory_deadline_at=deadline,created_by=identity('engineer'),
                    started_at=begin if status in ('completed','in_progress','rework') else None,completed_at=finish if status=='completed' else None)
                workers=['worker-2','worker-3'] if code=='1.4' else ['executor']
                if status!='draft':
                    for role in workers:ensure('work_assignments','work_assignment_id',key+'-'+role,site_id=site_id,work_order_id=order.work_order_id,user_id=identity(role),assigned_by=identity('engineer'),status='finished' if status=='completed' else 'assigned')
                if status in ('completed','in_progress','rework'):
                    report=ensure('work_reports','work_report_id',key+'-report',site_id=site_id,work_order_id=order.work_order_id,submitted_by=identity(workers[0]),revision_no=1,
                        status='draft' if status=='in_progress' else 'reviewed',comment='Осмотр выполнен. Корпус прибора очищен, повреждённое стекло заменено. Результаты контрольного сравнения приложены.' if code=='1.5' else 'Проверка выполнена по технологической карте, замечания зафиксированы.',
                        submitted_at=finish if status!='in_progress' else None,checklist_snapshot=checks,execution_context=dict(started_at=begin.isoformat(),performed_at=finish.isoformat(),person_hours=str(rule.norm_hours)))
                    for check in checks:
                        answer='done' if check['answerKind']=='boolean' else '62' if check['unit']=='°C' else '1248.6' if check['unit']=='м³' else '3.2' if check['answerKind']=='number' else 'Проверено, отклонений не выявлено'
                        ensure('checklist_results','checklist_result_id',key+'-answer-'+check['id'],site_id=site_id,work_order_id=order.work_order_id,work_report_id=report.work_report_id,checklist_template_id=UUID(check['id']),question_snapshot=check['text'],response_value={'answer':answer})
                    if status!='in_progress':ensure('acceptance_reviews','acceptance_review_id',key+'-acceptance',site_id=site_id,work_order_id=order.work_order_id,work_report_id=report.work_report_id,reviewer_user_id=identity('engineer'),decision='accepted' if status=='completed' else 'rework',comment='Результаты осмотра и протокол проверены.' if status=='completed' else 'Повторить проверку подключения датчика и приложить фотографии.',reviewed_at=finish+timedelta(minutes=10),decision_context=dict(performed_at=finish.isoformat(),actual_person_hours=str(rule.norm_hours)))
                return order
            # Prior service history supplies actual stored facts to the real forecasting API.
            for code in bindings:
                for number,offset in enumerate((73,146,219,292) if code=='1.4' else (30,60,90,120) if code<'1.4' else (91,182,273,364)):
                    create_work(f'history-{code}-{number}',code,day-timedelta(days=offset),'completed')
            session.commit()
            calculated=preview_calendar(v,day.year,day.month,as_of=now)
            if any(d['status']!='ok' for d in calculated['diagnostics']):raise RuntimeError('Presentation catalog calculation is incomplete')
            photo_task=None
            for row in calculated['items']:
                source=date.fromisoformat(row['sourceDate']);work_day=date.fromisoformat(row['mandatoryDueDate']);code=row['operationCode'];binding=bindings[code]
                key=f'month-{day:%Y-%m}-{code}-{source}'
                entry=ensure('schedule_entries','schedule_entry_id',key+'-entry',site_id=site_id,system_id=system_id,schedule_plan_id=plan.schedule_plan_id,maintenance_rule_id=binding.maintenance_rule_id,binding_id=binding.binding_id,
                    planned_date=date.fromisoformat(row['occurrenceDate']),source_date=source,earliest_date=date.fromisoformat(row['earliestDate']),regulatory_deadline_on=work_day,regulatory_deadline_at=datetime.combine(work_day+timedelta(days=1),time.min,tz),rule_snapshot=safe(settings[code][0]),sequence_no=source.day)
                status='completed' if work_day<day else 'in_progress' if work_day==day and code=='1.5' else 'assigned' if work_day==day and code in ('1.2','1.4') else 'draft'
                if work_day==day-timedelta(days=1) and code=='1.3':status='rework'
                order=create_work(key,code,work_day,status,entry)
                if work_day==day and code=='1.5':photo_task=order
            if photo_task is None:
                # On weekends the same explicit operation can be inspected as a separate call-out.
                photo_task=create_work('inspection-'+str(day),'1.5',day,'in_progress')
            if photo_task.status=='in_progress':
                report=v.one('work_reports',work_order_id=photo_task.work_order_id)
                for check in report.checklist_snapshot:
                    if not check['photoRequired']:continue
                    for phase in ('before','after'):
                        uid=identity(str(photo_task.work_order_id)+'-'+check['id']+'-'+phase)
                        if repo.get('evidence_files',uid):continue
                        blob=(ROOT/'data/presentation'/f'inspection-{phase}.jpg').read_bytes();key=f'{site_id}/{uid}';target=storage/key;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
                        repo.add('evidence_files',evidence_file_id=uid,site_id=site_id,work_order_id=photo_task.work_order_id,work_report_id=report.work_report_id,uploaded_by=identity('executor'),stage=phase,storage_key=key,mime_type='image/jpeg',file_size=len(blob),sha256=hashlib.sha256(blob).hexdigest(),checklist_item_id=UUID(check['id']),equipment_id=identity('gauge'),view_key='front')
                uid=identity(str(photo_task.work_order_id)+'-protocol')
                if not repo.get('evidence_files',uid):
                    blob=(ROOT/'data/presentation/inspection-protocol.pdf').read_bytes();key=f'{site_id}/{uid}';target=storage/key;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
                    repo.add('evidence_files',evidence_file_id=uid,site_id=site_id,work_order_id=photo_task.work_order_id,work_report_id=report.work_report_id,uploaded_by=identity('executor'),stage='other',storage_key=key,mime_type='application/pdf',file_size=len(blob),sha256=hashlib.sha256(blob).hexdigest(),verification_context={'kind':'Протокол сравнения с контрольным прибором'})
            from .planning import catalog_token
            plan.source_snapshot=dict(plan.source_snapshot,approved_rule_versions=sorted(str(b.maintenance_rule_id) for b in bindings.values()),approved_catalog_token=catalog_token(v),last_generation_day=str(day))
            session.commit()
            return dict(site_id=str(site_id),site_name=site.name,accounts=accounts,operations=len(bindings),checklist_items=sum(len(p[0]['operation']['checklist']) for p in settings.values()),calendar_items=len(calculated['items']),photo_task_id=str(photo_task.work_order_id))
    finally:
        lock.execute(text('SELECT pg_advisory_unlock(6813061126)'));lock.commit();lock.close();models.registry.dispose()
