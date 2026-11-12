"""Expand recurring local shifts into exact aware intervals; never guess DST."""
from datetime import date, datetime, time, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from app.schemas.maintenance import CalendarPattern
from .recurrence import occurrence_dates


def _local(value: datetime, tz: ZoneInfo):
    aware=value.replace(tzinfo=tz)
    if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=value:
        raise ValueError("DST_GAP")
    if aware.utcoffset()!=value.replace(tzinfo=tz,fold=1).utcoffset():
        raise ValueError("DST_AMBIGUOUS")
    return aware


def expand_shift(rule, start: date, end: date, timezone_name: str):
    """Rows/dicts are copied at the boundary; the rule is not materialized in SQL."""
    get=rule.get if isinstance(rule,dict) else lambda key:getattr(rule,key)
    if not get('is_active'):
        return [],[]
    first=max(start-timedelta(days=1),get('valid_from'))
    last=min(end,get('valid_until') or end)
    if last<first:
        return [],[]
    tz=ZoneInfo(timezone_name)
    pattern=CalendarPattern.model_validate_json(json.dumps(get('calendar_pattern'),default=str))
    rows,diagnostics=[],[]
    try:
        days=occurrence_dates(pattern,first,last)
    except ValueError as exc:
        return [dict(start_at=datetime.combine(start,time.min,tz),end_at=datetime.combine(end+timedelta(days=1),time.min,tz),status='unavailable')],[dict(date=str(start),code='CALENDAR_PATTERN_UNSATISFIABLE',explanation=str(exc))]
    for day in days:
        finish_day=day+timedelta(days=1) if get('ends_local')<=get('starts_local') else day
        # valid_until bounds the full shift, not merely the date it started.
        limit=datetime.combine(get('valid_until')+timedelta(days=1),time.min,tz) if get('valid_until') else None
        try:
            begin=_local(datetime.combine(day,get('starts_local')),tz)
            finish=_local(datetime.combine(finish_day,get('ends_local')),tz)
            if limit:
                finish=min(finish,limit)
            if finish>begin and finish>datetime.combine(start,time.min,tz) and begin<datetime.combine(end+timedelta(days=1),time.min,tz):
                rows.append(dict(start_at=begin,end_at=finish,status=get('status')))
        except ValueError as exc:
            diagnostics.append(dict(date=str(day),code=str(exc),explanation='Переход часового пояса: задайте отдельный точный интервал доступности.'))
            rows.append(dict(start_at=datetime.combine(day,time.min,tz),end_at=datetime.combine(finish_day+timedelta(days=1),time.min,tz),status='unavailable'))
    return rows,diagnostics


def employment_availability(intervals, employed_from, employed_until, timezone_name):
    tz=ZoneInfo(timezone_name)
    begin=datetime.combine(employed_from,time.min,tz) if employed_from else None
    end=datetime.combine(employed_until+timedelta(days=1),time.min,tz) if employed_until else None
    result=[]
    for row in intervals:
        left=max(row['start_at'],begin) if begin else row['start_at']
        right=min(row['end_at'],end) if end else row['end_at']
        if right>left:
            result.append(dict(row,start_at=left,end_at=right))
    return result
