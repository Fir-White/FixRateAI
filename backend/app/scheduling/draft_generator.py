"""Pure expansion of confirmed source decisions; never infer a year from marks."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo
from collections import defaultdict
from app.schemas.catalog_decisions import DecisionInput
from app.schemas.draft_plans import WorkOccurrence, WorkSegment, GenerationInput
from app.scheduling.recurrence import occurrence_pairs
from app.scheduling.shifts import _local

GENERATOR_VERSION='catalog-occurrences-v1'
MAX_OCCURRENCES=5000
MAX_SEGMENTS=10000


def _interval(day,slot,policy,tz):
    if slot=='whole_day': start,end=0,1440
    elif slot=='day': start,end=policy.day_start_minute,policy.night_start_minute
    else: start,end=policy.night_start_minute,policy.day_start_minute+1440
    origin=datetime.combine(day,time.min)
    return dict(start_at=_local(origin+timedelta(minutes=start),tz),end_at=_local(origin+timedelta(minutes=end),tz))


def expand(source,request:GenerationInput):
    """source contains immutable source rows plus current decision assessments."""
    occurrences=[];segments=[];issues=[]
    selected=set(request.row_numbers)
    tz=ZoneInfo(source['timezone'])
    parsed={n:DecisionInput.model_validate(r['decision']) for n,r in source['decisions'].items() if n in selected}
    children=defaultdict(list)
    for n,d in parsed.items():
        if d.included_in_row: children[d.included_in_row].append(n)
    def issue(code,message,row): issues.append(dict(code=code,message=message,row_number=row))
    for number in sorted(selected):
        row=source['operations'].get(number)
        record=source['decisions'].get(number)
        if not row:
            issue('SOURCE_ROW_MISSING','Строка не найдена в выбранном каталоге',number);continue
        if not record or not record['prepared']:
            issue('SOURCE_NOT_CONFIRMED','Решение строки неполно, не подтверждено или устарело',number);continue
        d=parsed[number]
        if d.frequency_kind=='included_in':
            if d.included_in_row not in selected: issue('PARENT_NOT_SELECTED','Выберите родительскую работу вместе с включённой операцией',number)
            continue
        if d.frequency_kind=='event':
            issue('EVENT_TRIGGER_REQUIRED','Работа по необходимости требует реального события; регулярный график не создаётся',number);continue
        if d.frequency_kind=='dates' and request.expansion!='confirmed_rule':
            issue('EXPLICIT_DATES_REQUIRED','Для правила конкретных дат выберите расчёт по подтверждённому календарному правилу',number);continue
        if d.frequency_kind=='daily_events' and (d.frequency_interval!=2 or d.mark_slots!='day_night'):
            issue('EVENT_SLOTS_UNCONFIRMED','Для двух событий в сутки подтвердите дневной и ночной слоты; другие кратности требуют отдельного правила',number);continue
        if d.mark_slots=='day_night' and d.frequency_kind!='daily_events':
            issue('EVENT_FREQUENCY_CONFLICT','Два слота требуют подтверждённой частоты два события в сутки',number);continue
        if d.mark_slots=='day_night' and (request.policy.day_start_minute is None or d.interpretation!='FIXED_EXECUTION'):
            issue('SLOT_WINDOWS_REQUIRED','День/ночь требуют границ слотов и отдельных подтверждённых выполнений',number);continue
        slots=['day','night'] if d.mark_slots=='day_night' else ['whole_day']
        events=[]
        if request.expansion=='source_january':
            days=[date(d.calendar_year,1,m['day']) for m in row['calendar_marks'] if m.get('text') and m['text'].strip()]
            if not days:
                issue('NO_CONFIRMED_DATES','В исходном январе нет отметок; задайте подтверждённое календарное правило',number);continue
            if d.interpretation=='FIXED_EXECUTION':
                limit=(d.frequency_interval if d.frequency_kind=='yearly_count' else 1) if d.frequency_kind in ('month','quarter','year','yearly_count') else None
                if limit is not None and len(days)*len(slots)>limit:
                    issue('MARK_FREQUENCY_CONFLICT','Число отдельных выполнений января расходится с подтверждённой частотой; проверьте смысл отметок',number);continue
                events=[(day,[day]) for day in days if request.starts_on<=day<=request.ends_on]
            elif any(request.starts_on<=day<=request.ends_on for day in days):
                events=[(max(days),days)]
        else:
            if d.calendar_pattern is None:
                issue('CALENDAR_ANCHOR_REQUIRED','Для других месяцев подтвердите календарное правило и опорную дату',number);continue
            try:
                first=max(date(2000,1,1),request.starts_on-timedelta(days=7))
                last=min(date(2200,12,31),request.ends_on+timedelta(days=d.allowed_lead_days+7))
                for original,due in occurrence_pairs(d.calendar_pattern,first,last):
                    earliest=due-timedelta(days=d.allowed_lead_days)
                    if due>=request.starts_on and earliest<=request.ends_on:
                        events.append((original,[earliest+timedelta(days=i) for i in range((due-earliest).days+1)]))
            except ValueError as error:
                issue('CALENDAR_UNSATISFIABLE',str(error),number);continue
        included=[];qualifications=set(d.qualification_ids);qualifications_confirmed=d.qualifications_confirmed
        for child in sorted(children[number]):
            child_record=source['decisions'].get(child)
            child_decision=parsed[child]
            if not child_record['prepared']:
                issue('INCLUDED_STEP_UNCONFIRMED','Включённая операция не готова; подтвердите её до расчёта пакета',child);continue
            included.append(child)
            qualifications.update(child_decision.qualification_ids)
            qualifications_confirmed=qualifications_confirmed and child_decision.qualifications_confirmed
        assets=sorted(d.equipment_ids,key=str)
        total=Decimal(record['total_person_hours'])
        for original,days in events:
            for slot in slots:
                try: intervals=[_interval(day,slot,request.policy,tz) for day in days]
                except ValueError:
                    issue('LOCAL_TIME_AMBIGUOUS','Переход часового пояса: задайте точные допустимые даты/интервалы',number);continue
                merged=[]
                for interval in intervals:
                    if merged and merged[-1]['end_at']==interval['start_at']: merged[-1]['end_at']=interval['end_at']
                    else: merged.append(interval)
                intervals=merged
                identity=uuid5(UUID(str(request.import_id)),f'{number}:{original}:{slot}:{d.interpretation}:'+','.join(map(str,assets)))
                cells=[row['source_cells']['B'],row['source_cells']['D'],row['source_cells']['E']]
                if request.expansion=='source_january':
                    cells+=[m['address'] for m in row['calendar_marks'] if m.get('text') and m['text'].strip() and (d.interpretation!='FIXED_EXECUTION' or m['day']==original.day)]
                item=WorkOccurrence(occurrence_id=identity,site_id=source['site_id'],import_id=request.import_id,
                    source_sha256=source['source_sha256'],parser_version=source['parser_version'],
                    source_row=number,decision_revision=record['revision'],source_cells=cells,
                    source_date=original,source_slot=slot,date_basis=request.expansion,title=row['title'],operation_code=row['code'],maintenance_type=row['maintenance_type'],
                    interpretation=d.interpretation,equipment_ids=assets,earliest_date=min(days),latest_date=max(days),
                    allowed_intervals=intervals,total_person_hours=total,crew_size=d.crew_size,splittable=d.splittable,
                    min_segment_minutes=d.min_segment_minutes,qualification_ids=sorted(qualifications,key=str),
                    qualifications_confirmed=qualifications_confirmed,included_rows=included,norm_ref=d.norm_ref,norm_scope=d.norm_scope,policy_note=d.policy_note)
                occurrences.append(item)
                batches=([[asset] for asset in assets] if d.interpretation=='EQUIPMENT_BATCH' and d.norm_scope=='per_asset' and d.splittable else [assets])
                for index,batch in enumerate(batches):
                    segments.append(WorkSegment(segment_id=uuid5(identity,f'initial:{index}'),occurrence_id=identity,
                        equipment_ids=batch,person_hours=total/len(batches)))
                if len(occurrences)>MAX_OCCURRENCES or len(segments)>MAX_SEGMENTS:
                    issue('GENERATION_LIMIT','Превышен размер черновика; сократите период или число строк',number)
                    return [],[],issues
    return occurrences,segments,issues
