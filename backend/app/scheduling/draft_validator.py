"""One pure validator for stored drafts and future manual/solver candidates.

Validation checks a resource snapshot; it neither reserves people nor publishes.
"""
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from app.assignment.selection import _merge, _subtract
from app.schemas.draft_plans import PlanValidation
from app.scheduling.planning_policy import access_intervals,intersect

ZERO=Decimal(0)
UTC=timezone.utc
INCOMPLETE={'UNPLACED','CAPACITY_UNCONFIRMED','QUALIFICATIONS_UNCONFIRMED','RESOURCE_DATA_INCOMPLETE','SOURCE_STALE','QUALIFICATION_EXPIRY_UNKNOWN','EQUIPMENT_BOOKING_UNKNOWN','DEPENDENCY_UNPLACED','ACCESS_UNCONFIRMED','ACCESS_TIME_UNRESOLVED'}


def digest(value):
    return sha256(json.dumps(value,default=str,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _utc(value): return value.astimezone(UTC)
def _hours(start,end): return Decimal(str((_utc(end)-_utc(start)).total_seconds()))/Decimal(3600)


def _parts(start,end,tz):
    start,end=_utc(start),_utc(end)
    while start<end:
        day=start.astimezone(tz).date()
        right=min(end,datetime.combine(day+timedelta(days=1),time.min,tz).astimezone(UTC))
        yield day,start,right
        start=right


def _contains(intervals,starts,left,right):
    index=bisect_right(starts,left)-1
    return index>=0 and intervals[index][1]>=right


def validate(occurrences,segments,workers,policy,starts_on,ends_on,timezone_name,now,*,source_stale=False,equipment_bookings=None,equipment_unknown=(),previous_segments=(),unlock=False,allow_legacy_policy=False):
    tz=ZoneInfo(timezone_name);issues=[];counts=Counter()
    def add(code,message,root=None,segment=None,day=None):
        counts[code]+=1
        if len(issues)<25:
            issues.append(dict(code=code,message=message,row_number=root.source_row if root else None,
                occurrence_id=root.occurrence_id if root else None,segment_id=segment.segment_id if segment else None,date=day))
        elif code not in INCOMPLETE:
            index=next((i for i in range(len(issues)-1,-1,-1) if issues[i]['code'] in INCOMPLETE),None)
            if index is not None:
                issues[index]=dict(code=code,message=message,row_number=root.source_row if root else None,
                    occurrence_id=root.occurrence_id if root else None,segment_id=segment.segment_id if segment else None,date=day)
    roots={r.occurrence_id:r for r in occurrences};people={w.worker_id:w for w in workers}
    grouped=defaultdict(list);seen=set();by_id={s.segment_id:s for s in segments}
    for segment in segments:
        if segment.segment_id in seen: add('DUPLICATE_SEGMENT','Идентификатор сегмента повторяется',segment=segment)
        seen.add(segment.segment_id)
        if segment.occurrence_id not in roots: add('UNKNOWN_OCCURRENCE','Сегмент ссылается на неизвестную работу',segment=segment)
        grouped[segment.occurrence_id].append(segment)
    if len(roots)!=len(occurrences): add('DUPLICATE_OCCURRENCE','Корневая работа повторяется')
    successors=defaultdict(list);indegree={identity:0 for identity in by_id}
    for segment in segments:
        for identity in segment.depends_on_segment_ids:
            predecessor=by_id.get(identity)
            if predecessor is None: add('DEPENDENCY_MISSING','Предшествующий сегмент не найден',roots.get(segment.occurrence_id),segment);continue
            successors[identity].append(segment.segment_id);indegree[segment.segment_id]+=1
            if not predecessor.end_at: add('DEPENDENCY_UNPLACED','Предшествующий сегмент ещё не размещён',roots.get(segment.occurrence_id),segment)
            elif segment.start_at and _utc(predecessor.end_at)>_utc(segment.start_at):
                add('DEPENDENCY_ORDER','Сегмент начинается раньше завершения предшественника',roots.get(segment.occurrence_id),segment)
    queue=[i for i,n in indegree.items() if n==0];visited=0
    while queue:
        identity=queue.pop();visited+=1
        for child in successors[identity]:
            indegree[child]-=1
            if indegree[child]==0: queue.append(child)
    if visited!=len(indegree): add('DEPENDENCY_CYCLE','В зависимостях сегментов обнаружен цикл')
    if source_stale: add('SOURCE_STALE','Источник, решение или привязка изменились: создайте новый расчёт')
    if not policy.capacity_confirmed or not policy.capacity_ref: add('CAPACITY_UNCONFIRMED','Подтвердите полезную ёмкость и её источник')
    try: access=access_intervals(policy,starts_on,ends_on,tz,allow_legacy=allow_legacy_policy)
    except ValueError:
        access=None;add('ACCESS_TIME_UNRESOLVED','Граница окна доступа попадает в пропущенное или неоднозначное местное время; уточните окно')
    if access is None and 'ACCESS_TIME_UNRESOLVED' not in counts:
        add('ACCESS_UNCONFIRMED','Подтвердите допустимые часы обслуживания объекта или отсутствие дополнительных ограничений')
    access_starts=[a for a,_ in access] if access is not None else []
    for old in previous_segments:
        if old.locked and not unlock and (old.segment_id not in by_id or old.model_dump()!=by_id[old.segment_id].model_dump()):
            add('LOCKED_SEGMENT','Закреплённый сегмент изменён без явного разблокирования',roots.get(old.occurrence_id),old)
    free={};available={};booked={};capacity=defaultdict(Decimal);existing_load=defaultdict(Decimal);access_capacity=defaultdict(Decimal);unknown=set()
    for identity,worker in people.items():
        if not worker.active or not worker.membership_active or not worker.can_execute: continue
        if not all((worker.booking_data_complete,worker.workload_data_complete,worker.availability_data_complete)): unknown.add(identity)
        raw=_merge([(_utc(a.start_at),_utc(a.end_at)) for a in worker.availability if a.status=='available'])
        exclusions=[(_utc(a.start_at),_utc(a.end_at)) for a in worker.availability if a.status=='unavailable']
        available[identity]=_subtract(raw,exclusions)
        booked[identity]=_merge([(_utc(b.start_at),_utc(b.end_at)) for b in worker.bookings if b.blocks_time])
        windows=_subtract(available[identity],booked[identity])
        if access is not None and policy.format_version==2:windows=intersect(windows,access)
        free[identity]=(windows,[a for a,_ in windows])
        for start,end in windows:
            for day,left,right in _parts(start,end,tz):access_capacity[identity,day]+=_hours(left,right)
        for start,end in available[identity]:
            for day,left,right in _parts(start,end,tz):
                if starts_on<=day<=ends_on+timedelta(days=1) and policy.capacity_hours_per_24h is not None:
                    capacity[identity,day]+=_hours(left,right)*policy.capacity_hours_per_24h/24
        for start,end in booked[identity]:
            for day,left,right in _parts(start,end,tz):
                if starts_on<=day<=ends_on+timedelta(days=1): existing_load[identity,day]+=_hours(left,right)
    worker_intervals=defaultdict(list);asset_intervals=defaultdict(list);reserved=defaultdict(Decimal);planned=defaultdict(Decimal)
    assigned_hours=defaultdict(Decimal);unplaced=0;placed=ZERO
    equipment_bookings=equipment_bookings or {}
    for root in occurrences:
        children=grouped[root.occurrence_id]
        if sum((s.person_hours for s in children),ZERO)!=root.total_person_hours:
            add('HOURS_NOT_CONSERVED','Сумма сегментов не равна подтверждённым человеко-часам',root)
        if not root.splittable and len(children)!=1: add('SEGMENTATION_FORBIDDEN','Неделимая работа должна оставаться одним сегментом',root)
        if not root.qualifications_confirmed: add('QUALIFICATIONS_UNCONFIRMED','Подтвердите требования к допускам, включая отсутствие специальных требований',root)
        root_assets=set(root.equipment_ids)
        if set(a for s in children for a in s.equipment_ids)!=root_assets: add('ASSET_COVERAGE','Сегменты должны покрывать всё подтверждённое оборудование',root)
        if root.interpretation=='EQUIPMENT_BATCH' and root.norm_scope=='per_asset' and len(children)>1:
            asset_hours=defaultdict(Decimal)
            for child in children:
                if len(child.equipment_ids)!=1: add('BATCH_UNIT_REQUIRED','У разделённой партии каждый сегмент относится к одной реальной единице',root,child)
                else: asset_hours[child.equipment_ids[0]]+=child.person_hours
            unit_hours=root.total_person_hours/len(root_assets)
            if any(asset_hours[a]!=unit_hours for a in root_assets): add('BATCH_HOURS_NOT_CONSERVED','Объём каждой единицы партии должен совпадать с её нормой',root)
        allowed=_merge([(_utc(w.start_at),_utc(w.end_at)) for w in root.allowed_intervals]);allowed_starts=[a for a,_ in allowed]
        if not allowed or sum((_hours(a,b)*root.crew_size for a,b in allowed),ZERO)<root.total_person_hours or (not root.splittable and all(_hours(a,b)*root.crew_size<root.total_person_hours for a,b in allowed)):
            add('WINDOW_TOO_SHORT','Подтверждённая работа не помещается ни в один допустимый интервал',root)
        if any(a in equipment_unknown for a in root_assets): add('EQUIPMENT_BOOKING_UNKNOWN','Для действующего задания на оборудование неизвестен интервал занятости',root)
        for segment in children:
            if not set(segment.equipment_ids).issubset(root_assets): add('FOREIGN_ASSET','В сегмент добавлено оборудование вне подтверждённой работы',root,segment)
            if len(children)>1 and root.min_segment_minutes and segment.person_hours*60<Decimal(root.min_segment_minutes)*root.crew_size:
                add('SEGMENT_TOO_SMALL','Объём сегмента меньше подтверждённого минимума',root,segment)
            if not segment.start_at:
                for identity in segment.worker_ids:
                    worker=people.get(identity)
                    if not worker or worker.site_id!=root.site_id or not worker.active or not worker.membership_active or not worker.can_execute:
                        add('WORKER_UNAVAILABLE','Сотрудник не имеет действующего доступа исполнителя к объекту',root,segment)
                unplaced+=1;add('UNPLACED','Сегмент ещё не размещён',root,segment);continue
            left,right=_utc(segment.start_at),_utc(segment.end_at)
            if left<_utc(now): add('PAST_PLACEMENT','Нельзя выдавать прошлый интервал за новое будущее назначение',root,segment)
            if not _contains(allowed,allowed_starts,left,right): add('OUTSIDE_WINDOW','Размещение выходит за допустимые даты или слот работы',root,segment)
            if access is not None and policy.format_version==2 and not _contains(access,access_starts,left,right):
                add('OUTSIDE_ACCESS_WINDOW','Объект недоступен для обслуживания в выбранном интервале',root,segment)
            if left.astimezone(tz).date()<starts_on or (right-timedelta(microseconds=1)).astimezone(tz).date()>ends_on+timedelta(days=root.source_slot=='night'):
                add('OUTSIDE_HORIZON','Размещение выходит за горизонт версии плана',root,segment)
            if _hours(left,right)*root.crew_size<segment.person_hours: add('DURATION_TOO_SHORT','Интервал бригады меньше подтверждённой трудоёмкости сегмента',root,segment)
            if root.minimum_duration_minutes and right-left<timedelta(minutes=root.minimum_duration_minutes):add('DURATION_TOO_SHORT','Интервал меньше подтверждённой длительности регламента',root,segment)
            if len(segment.worker_ids)!=root.crew_size: add('CREW_SIZE','Для сегмента нужен полный одновременный состав бригады',root,segment)
            placed+=segment.person_hours
            parts=list(_parts(left,right,tz));remaining=segment.person_hours;duration=_hours(left,right)
            for index,(day,a,b) in enumerate(parts):
                share=remaining if index==len(parts)-1 else segment.person_hours*_hours(a,b)/duration
                remaining-=share;planned[day]+=share;reserved[day]+=_hours(a,b)*len(segment.worker_ids)
            for asset in segment.equipment_ids:
                asset_intervals[asset].append((left,right,root,segment))
                if any(left<_utc(b) and _utc(a)<right for a,b in equipment_bookings.get(asset,())):
                    add('EQUIPMENT_BUSY','Оборудование занято действующим заданием в этом интервале',root,segment)
            for identity in segment.worker_ids:
                worker=people.get(identity)
                if not worker or worker.site_id!=root.site_id or not worker.active or not worker.membership_active or not worker.can_execute:
                    add('WORKER_UNAVAILABLE','Сотрудник не имеет действующего доступа исполнителя к объекту',root,segment);continue
                if identity in unknown: add('RESOURCE_DATA_INCOMPLETE',f'Недостаточно данных о доступности или занятости: {worker.name}',root,segment)
                windows,window_starts=free.get(identity,([],[]))
                if identity not in unknown and not _contains(windows,window_starts,left,right):
                    add('WORKER_BUSY_OR_ABSENT',f'Нет свободного интервала у сотрудника: {worker.name}',root,segment)
                quals={q.skill_id:q for q in worker.qualifications}
                end_day=(right-timedelta(microseconds=1)).astimezone(tz).date()
                for skill in root.qualification_ids:
                    q=quals.get(skill)
                    if not q or not q.verified_at or _utc(q.verified_at)>left or (q.valid_until and q.valid_until<end_day):
                        add('QUALIFICATION_MISSING',f'Нет действующего обязательного допуска: {worker.name}',root,segment)
                    elif q.validity_required and not q.valid_until: add('QUALIFICATION_EXPIRY_UNKNOWN',f'Не задан срок обязательного допуска: {worker.name}',root,segment)
                worker_intervals[identity].append((left,right,root,segment))
                for day,a,b in parts: assigned_hours[identity,day]+=_hours(a,b)
        if root.interpretation=='CONTINUOUS_WORK' and children and all(s.start_at for s in children):
            ordered=sorted(children,key=lambda s:_utc(s.start_at))
            if any(_utc(a.end_at)!=_utc(b.start_at) or set(a.worker_ids)!=set(b.worker_ids) for a,b in zip(ordered,ordered[1:])):
                add('CONTINUITY_BROKEN','Непрерывная работа требует смежных сегментов с одной бригадой',root)
    for groups,code,message in ((worker_intervals,'WORKER_OVERLAP','Сотрудник назначен на пересекающиеся сегменты'),(asset_intervals,'EQUIPMENT_OVERLAP','Оборудование обслуживается одновременно в нескольких сегментах')):
        for values in groups.values():
            furthest=None
            for left,right,root,segment in sorted(values,key=lambda x:(x[0],x[1])):
                if furthest and left<furthest: add(code,message,root,segment)
                furthest=max(furthest,right) if furthest else right
    for (identity,day),hours in assigned_hours.items():
        if policy.capacity_confirmed and policy.capacity_hours_per_24h is not None and identity not in unknown and hours+existing_load[identity,day]>capacity[identity,day]:
            add('CAPACITY_EXCEEDED',f'Превышена полезная ёмкость сотрудника: {people[identity].name}',day=day)
    available_by_day=defaultdict(Decimal)
    for (identity,day),hours in capacity.items():
        remaining=max(ZERO,hours-existing_load[identity,day])
        available_by_day[day]+=min(remaining,access_capacity[identity,day]) if policy.format_version==2 else remaining
    days=[]
    for number in range((ends_on-starts_on).days+1+int(any(d>ends_on for d in planned))):
        day=starts_on+timedelta(days=number)
        free_capacity=None if unknown else available_by_day[day]
        if not policy.capacity_confirmed or access is None: free_capacity=None
        days.append(dict(date=day,planned_person_hours=planned[day],reserved_person_hours=reserved[day],
            available_person_hours=free_capacity,deficit_person_hours=None if free_capacity is None else max(ZERO,reserved[day]-free_capacity)))
    facts=[w.model_dump(mode='json') for w in sorted(workers,key=lambda w:str(w.worker_id))]
    for w in facts:
        for name in ('availability','bookings','qualifications'): w[name].sort(key=lambda r:json.dumps(r,sort_keys=True))
    resource_sha=digest(dict(workers=facts,equipment_bookings={str(k):sorted(v,key=lambda pair:(_utc(pair[0]),_utc(pair[1]))) for k,v in sorted(equipment_bookings.items(),key=lambda p:str(p[0]))},equipment_unknown=sorted(map(str,equipment_unknown))))
    snapshot=dict(occurrences=[r.model_dump(mode='json') for r in occurrences],segments=[s.model_dump(mode='json') for s in segments],policy=policy.model_dump(mode='json'),resources=resource_sha,stale=source_stale)
    return PlanValidation(status='invalid' if set(counts)-INCOMPLETE else 'incomplete' if counts else 'valid',checked_at=now,
        input_sha256=digest(snapshot),resource_sha256=resource_sha,total_issues=sum(counts.values()),issue_counts=dict(counts),issues=issues,
        total_person_hours=sum((r.total_person_hours for r in occurrences),ZERO),placed_person_hours=placed,unplaced_segments=unplaced,days=days)
