"""Confirmed site access windows shared by every planning/execution path.

These windows limit access, never employee availability or regulatory due dates.
Policy v1 is retained as an explicitly legacy snapshot, without invented windows.
"""
from datetime import datetime,time,timedelta,timezone
from app.assignment.selection import _merge
from app.scheduling.shifts import _local

UTC=timezone.utc

def access_ready(policy,*,allow_legacy=False):
    return allow_legacy if policy.format_version==1 else policy.access_status=='confirmed'

def access_intervals(policy,starts_on,ends_on,tz,*,allow_legacy=False):
    """Return None for unknown access, broad bounds for explicitly unrestricted.

    Include the prior local date so an overnight Sunday window covers Monday.
    Ambiguous/nonexistent local boundaries fail explicitly, never choose an offset.
    """
    if not access_ready(policy,allow_legacy=allow_legacy):return None
    left=datetime.combine(starts_on-timedelta(days=1),time.min,tz).astimezone(UTC)
    right=datetime.combine(ends_on+timedelta(days=2),time.min,tz).astimezone(UTC)
    if policy.format_version==1 or policy.access_mode=='unrestricted':return [(left,right)]
    windows=[]
    for n in range((ends_on-starts_on).days+3):
        day=starts_on+timedelta(days=n-1)
        for window in policy.service_windows:
            if window.weekday!=day.isoweekday():continue
            origin=datetime.combine(day,time.min)
            a_local=origin+timedelta(minutes=window.start_minute);b_local=origin+timedelta(minutes=window.end_minute)
            if b_local<=datetime.combine(starts_on,time.min):continue
            a=_local(a_local,tz).astimezone(UTC)
            b=_local(b_local,tz).astimezone(UTC)
            if b<=a:raise ValueError('Окно доступа имеет неположительную длительность после преобразования часового пояса')
            windows.append((a,b))
    return _merge(windows)

def intersect(left,right):
    """Intersect sorted, merged intervals in linear time."""
    result=[];i=j=0
    while i<len(left) and j<len(right):
        a=max(left[i][0],right[j][0]);b=min(left[i][1],right[j][1])
        if a<b:result.append((a,b))
        if left[i][1]<right[j][1]:i+=1
        else:j+=1
    return result
