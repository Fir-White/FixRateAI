"""Batch private resource facts for users accessible at the selected site.

Foreign-site task identifiers stay inside the server snapshot; public choices
contain only the current site's people, never foreign client/task metadata.
"""
from collections import defaultdict
from datetime import datetime,time,timedelta,timezone
from uuid import UUID
import json
from fastapi import HTTPException
from sqlalchemy import text
from app.assignment.schemas import Worker
from app.scheduling.shifts import expand_shift,employment_availability


def _job_interval(row,now):
    completed=row['completed_at'] is not None and row['order_status'] in ('completed','in_review')
    if completed and row['started_at']: return row['started_at'],row['completed_at'],False,True
    if row['order_status']!='in_progress' and row['start_at'] and row['end_at']:
        return row['start_at'],row['end_at'],row['assignment_status']!='finished' and not completed,True
    start=row['started_at'] if row['order_status']=='in_progress' else row['planned_start_at']
    duration=row['operation_snapshot'].get('planning_duration_minutes')
    basis=row['operation_snapshot'].get('duration_basis')
    if start is None or not isinstance(duration,int) or isinstance(duration,bool) or not 0<duration<=46080 or not isinstance(basis,str) or not basis.strip():
        return start,None,not completed and row['assignment_status']!='finished',False
    end=start+timedelta(minutes=duration)
    complete=not (row['order_status']=='in_progress' and not completed and end<=now)
    return start,end,not completed and row['assignment_status']!='finished',complete


def resources(v,start,end,now,asset_ids=(),*,exclude_order_ids=()):
    site=v.one('sites',site_id=v.principal.site_id)
    params=dict(site=site.site_id,exclude=list(exclude_order_ids))
    members=v.session.execute(text('''SELECT m.user_id,m.is_active AS membership_active,m.employed_from,m.employed_until,
        u.full_name,u.is_active FROM site_memberships m JOIN users u USING(user_id)
        WHERE m.site_id=:site AND m.role IN ('executor','technician') ORDER BY m.user_id LIMIT 501'''),params).mappings().all()
    if len(members)>500: raise HTTPException(422,'Более 500 сотрудников в расчёте: требуется ограниченный подтверждённый пул')
    ids=[m['user_id'] for m in members]
    params.update(ids=ids,starts=start,ends=end)
    workers={m['user_id']:dict(worker_id=m['user_id'],site_id=site.site_id,name=m['full_name'],active=m['is_active'],
        membership_active=m['membership_active'],can_execute=True,booking_data_complete=True,workload_data_complete=True,
        availability_data_complete=False,qualifications=[],availability=[],bookings=[]) for m in members}
    if ids:
        slots=v.session.execute(text('''SELECT user_id,starts_at,ends_at,status FROM availability_slots
            WHERE user_id=ANY(CAST(:ids AS uuid[])) AND is_active AND (site_id=:site OR status='unavailable')
            AND ends_at>:starts AND starts_at<:ends LIMIT 100001'''),params).mappings().all()
        shifts=v.session.execute(text('''SELECT r.*,s.timezone FROM employee_shift_rules r JOIN sites s USING(site_id)
            WHERE r.user_id=ANY(CAST(:ids AS uuid[])) AND r.is_active AND (r.site_id=:site OR r.status='unavailable') LIMIT 100001'''),params).mappings().all()
        skills=v.session.execute(text('''SELECT r.user_id,r.skill_id,r.verified_at,r.valid_until,s.validity_required
            FROM user_skills r JOIN skills s USING(skill_id) WHERE r.site_id=:site AND r.user_id=ANY(CAST(:ids AS uuid[]))'''),params).mappings().all()
        bookings=v.session.execute(text('''SELECT a.user_id,a.status AS assignment_status,a.start_at,a.end_at,
            o.work_order_id,o.status AS order_status,o.started_at,o.completed_at,o.planned_start_at,o.operation_snapshot
            FROM work_assignments a JOIN work_orders o USING(work_order_id)
            WHERE a.user_id=ANY(CAST(:ids AS uuid[])) AND a.status NOT IN ('declined','cancelled') AND o.status<>'cancelled'
            AND o.work_order_id<>ALL(CAST(:exclude AS uuid[]))
            AND (o.completed_at IS NULL OR o.status NOT IN ('completed','in_review') OR o.completed_at>:starts)
            AND ((o.status IN ('completed','in_review') AND o.started_at IS NOT NULL AND o.completed_at IS NOT NULL AND o.started_at<:ends AND o.completed_at>:starts)
              OR (NOT (o.status IN ('completed','in_review') AND o.started_at IS NOT NULL AND o.completed_at IS NOT NULL)
                AND (o.status='in_progress' OR a.start_at IS NULL OR a.end_at IS NULL OR (a.start_at<:ends AND a.end_at>:starts))))
            LIMIT 100001'''),params).mappings().all()
        if any(len(rows)>100000 for rows in (slots,shifts,bookings)):
            raise HTTPException(422,'Слишком много интервалов ресурсов: сократите расчёт')
        for row in slots:
            w=workers[row['user_id']];w['availability_data_complete']=True
            w['availability'].append(dict(start_at=row['starts_at'],end_at=row['ends_at'],status=row['status']))
        shift_problems=set()
        for row in shifts:
            w=workers[row['user_id']]
            if row['site_id']==site.site_id: w['availability_data_complete']=True
            intervals,diagnostics=expand_shift(dict(row),start.date(),end.date(),row['timezone'])
            if diagnostics: shift_problems.add(row['user_id'])
            w['availability'].extend(intervals)
        for identity in shift_problems: workers[identity]['availability_data_complete']=False
        for member in members:
            worker=workers[member['user_id']]
            worker['availability']=employment_availability(worker['availability'],member['employed_from'],member['employed_until'],site.timezone)
        for row in skills: workers[row['user_id']]['qualifications'].append({k:row[k] for k in ('skill_id','verified_at','valid_until','validity_required')})
        for row in bookings:
            w=workers[row['user_id']];left,right,blocks,complete=_job_interval(row,now)
            if not complete:
                if left is None or left<end:
                    w['booking_data_complete' if blocks else 'workload_data_complete']=False
            if left and right:
                if right<=left: w['workload_data_complete']=False
                elif right>start and left<end:
                    w['bookings'].append(dict(task_id=row['work_order_id'],start_at=left,end_at=right,blocks_time=blocks))
    if sum(len(w['availability'])+len(w['bookings']) for w in workers.values())>100000:
        raise HTTPException(422,'Слишком много развёрнутых смен: сократите расчёт')
    equipment,unknown=equipment_reservations(v,start,end,now,asset_ids,exclude_order_ids=exclude_order_ids)
    parsed=[Worker.model_validate_json(json.dumps(w,default=str)) for w in workers.values()]
    return parsed,equipment,unknown


def equipment_reservations(v,start,end,now,asset_ids,*,exclude_order_ids=(),published_only=False):
    equipment=defaultdict(list);unknown=set()
    if asset_ids:
        params=dict(site=v.principal.site_id,assets=list(asset_ids),exclude=list(exclude_order_ids),published_only=published_only)
        rows=v.session.execute(text('''SELECT e.equipment_id,a.status AS assignment_status,a.start_at,a.end_at,
            o.work_order_id,o.status AS order_status,o.started_at,o.completed_at,o.planned_start_at,o.operation_snapshot
            FROM work_order_equipment e JOIN work_orders o USING(work_order_id)
            LEFT JOIN work_assignments a ON a.work_order_id=o.work_order_id AND a.status NOT IN ('declined','cancelled','finished')
            WHERE e.site_id=:site AND e.equipment_id=ANY(CAST(:assets AS uuid[])) AND o.status IN ('assigned','in_progress','rework')
            AND o.work_order_id<>ALL(CAST(:exclude AS uuid[]))
            AND (NOT :published_only OR EXISTS (SELECT 1 FROM published_catalog_tasks p
                         WHERE p.site_id=e.site_id AND p.work_order_id=o.work_order_id))
            LIMIT 100001'''),params).mappings().all()
        if len(rows)>100000: raise HTTPException(422,'Слишком много резервов оборудования: сократите расчёт')
        for row in rows:
            left,right,_,complete=_job_interval(row,now)
            if not complete and (left is None or left<end): unknown.add(row['equipment_id'])
            if left and right and right>left and right>start and left<end: equipment[row['equipment_id']].append((left,right))
    return dict(equipment),unknown


def ensure_equipment_free(v,order,start,end,now,*,published_only=False):
    assets={link.equipment_id for link in v.rows('work_order_equipment',work_order_id=order.work_order_id)}
    booked,unknown=equipment_reservations(v,start,end,now,assets,exclude_order_ids=[order.work_order_id],published_only=published_only)
    if not assets or unknown:
        raise HTTPException(409,'Недостаточно подтверждённых данных о занятости оборудования')
    if booked:
        raise HTTPException(409,'Оборудование уже занято другим нарядом в выбранном интервале')
