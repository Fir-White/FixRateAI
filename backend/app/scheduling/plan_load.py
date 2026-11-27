"""Exact normative hours and separate concurrent people/availability projections."""
from collections import defaultdict,Counter
from datetime import datetime,time,timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from app.assignment.selection import _merge,_subtract
from app.scheduling.draft_validator import _utc,_parts
from app.scheduling.planning_policy import access_intervals,intersect

ZERO=Decimal(0)

def peaks(events):
    required=0;peak_required=0;people=Counter();peak_selected=0
    for _,delta,workers in sorted(events,key=lambda e:(e[0],e[1])):
        required+=delta
        for person in workers:
            people[person]+=1 if delta>0 else -1
            if people[person]==0:del people[person]
        peak_required=max(peak_required,required);peak_selected=max(peak_selected,len(people))
    return peak_required,peak_selected


def project(roots,segments,workers,policy,report,starts_on,ends_on,timezone_name):
    tz=ZoneInfo(timezone_name);by_root={r.occurrence_id:r for r in roots}
    due_days=defaultdict(Decimal);remaining=defaultdict(Decimal);events=defaultdict(list)
    for root in roots:
        deadline=(max(w.end_at for w in root.allowed_intervals)-timedelta(microseconds=1)).astimezone(tz).date()
        due_days[deadline]+=root.total_person_hours
    for segment in segments:
        root=by_root[segment.occurrence_id]
        if not segment.start_at:
            deadline=(max(w.end_at for w in root.allowed_intervals)-timedelta(microseconds=1)).astimezone(tz).date()
            remaining[deadline]+=segment.person_hours
        else:
            for day,left,right in _parts(segment.start_at,segment.end_at,tz):
                events[day].extend([(left,root.crew_size,segment.worker_ids),(right,-root.crew_size,segment.worker_ids)])
    active=[w for w in workers if w.active and w.membership_active and w.can_execute]
    unknown=sum(not all((w.booking_data_complete,w.workload_data_complete,w.availability_data_complete)) for w in active)
    try:access=access_intervals(policy,starts_on,ends_on,tz)
    except ValueError:access=None
    available=defaultdict(list)
    if not unknown and access is not None and policy.capacity_confirmed:
        for worker in active:
            raw=_merge([(_utc(a.start_at),_utc(a.end_at)) for a in worker.availability if a.status=='available'])
            raw=_subtract(raw,[(_utc(a.start_at),_utc(a.end_at)) for a in worker.availability if a.status=='unavailable'])
            windows=_subtract(raw,_merge([(_utc(b.start_at),_utc(b.end_at)) for b in worker.bookings if b.blocks_time]))
            if policy.format_version==2:windows=intersect(windows,access)
            for left,right in windows:
                for day,a,b in _parts(left,right,tz):available[day].extend([(a,1,[worker.worker_id]),(b,-1,[worker.worker_id])])
    days=[]
    for day in report.days:
        required,selected=peaks(events[day.date])
        capacity_peak=None if unknown or access is None or not policy.capacity_confirmed else peaks(available[day.date])[1]
        days.append(dict(date=day.date,planned_person_hours=day.planned_person_hours,reserved_person_hours=day.reserved_person_hours,
            unplaced_due_person_hours=remaining[day.date],required_people_peak=required,selected_people_peak=selected,
            available_people_peak=capacity_peak,available_person_hours=day.available_person_hours,deficit_person_hours=day.deficit_person_hours))
    # An allowed night window can end on the day after the selected horizon,
    # including an unplaced event. Preserve that obligation in the visible ledger.
    known={d['date'] for d in days}
    for day in sorted(set(remaining)-known):
        if starts_on<=day<=ends_on+timedelta(days=1):
            days.append(dict(date=day,planned_person_hours=ZERO,reserved_person_hours=ZERO,unplaced_due_person_hours=remaining[day],
                required_people_peak=0,selected_people_peak=0,available_people_peak=None,available_person_hours=None,deficit_person_hours=None))
    days.sort(key=lambda d:d['date']);groups=defaultdict(list)
    for day in days:groups[day['date'].strftime('%Y-%m')].append(day)
    def total(rows,key):return None if any(r[key] is None for r in rows) else sum((r[key] for r in rows),ZERO)
    visible_days={r['date'] for r in days}
    months=[dict(month=month,due_person_hours=sum((due_days[r['date']] for r in rows),ZERO),
        **{key:total(rows,key) for key in ('planned_person_hours','reserved_person_hours','unplaced_due_person_hours','available_person_hours','deficit_person_hours')},
        required_people_peak=max(r['required_people_peak'] for r in rows),selected_people_peak=max(r['selected_people_peak'] for r in rows)) for month,rows in sorted(groups.items())]
    return dict(days=days,months=months,unknown_workers=unknown,totals=dict(total_person_hours=report.total_person_hours,
        placed_person_hours=report.placed_person_hours,unplaced_person_hours=sum(remaining.values(),ZERO),
        due_outside_view_person_hours=sum((hours for day,hours in due_days.items() if day not in visible_days),ZERO),
        unplaced_outside_view_person_hours=sum((hours for day,hours in remaining.items() if day not in visible_days),ZERO),
        available_person_hours=total(days,'available_person_hours'),deficit_person_hours=total(days,'deficit_person_hours')))
