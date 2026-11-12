"""One Gregorian/ISO calendar implementation shared by maintenance and shifts."""
from calendar import isleap, monthrange
from datetime import date, timedelta
from functools import lru_cache

from app.schemas.maintenance import CalendarPattern


def _matches_days(day,wanted,policy):
    last=monthrange(day.year,day.month)[1]
    days={last if value==-1 else min(value,last) if policy=='last_day' else value for value in wanted}
    return day.day in days


@lru_cache(maxsize=256)
def _annual_dates(year,count,excluded,weekdays,parity,month_days,months,short_month):
    first=date(year,1,1)
    allowed=[]
    for index in range(366 if isleap(year) else 365):
        day=first+timedelta(days=index)
        if day in excluded or (weekdays and day.isoweekday() not in weekdays) or (months and day.month not in months): continue
        if parity!='any' and day.isocalendar().week%2!=(1 if parity=='odd' else 0): continue
        if month_days and not _matches_days(day,month_days,short_month): continue
        allowed.append(day)
    if len(allowed)<count:
        raise ValueError('Недостаточно допустимых дней для заданного числа обслуживаний за год')
    return frozenset(allowed[i*len(allowed)//count] for i in range(count))


def _annual_for(pattern,year):
    return _annual_dates(year,pattern.count_per_year,tuple(sorted(pattern.excluded_dates)),
        tuple(sorted(pattern.weekdays)),pattern.week_parity,tuple(sorted(pattern.month_days)),tuple(sorted(pattern.months)),pattern.short_month)


@lru_cache(maxsize=256)
def _anchor_dates(year,month,anchor_day,count,excluded,weekdays,parity,month_days,months,short_month):
    first=date(year,month,min(anchor_day,monthrange(year,month)[1]))
    last=date(year+1,month,min(anchor_day,monthrange(year+1,month)[1]))
    allowed=[]
    for offset in range((last-first).days):
        day=first+timedelta(days=offset)
        if day in excluded or (weekdays and day.isoweekday() not in weekdays) or (months and day.month not in months):continue
        if parity!='any' and day.isocalendar().week%2!=(1 if parity=='odd' else 0):continue
        if month_days and not _matches_days(day,month_days,short_month):continue
        allowed.append(day)
    if len(allowed)<count:raise ValueError('Недостаточно допустимых дней для годового цикла от ввода')
    return frozenset(allowed[i*len(allowed)//count] for i in range(count))


def _anchor_for(pattern,year):
    return _anchor_dates(year,pattern.anchor_date.month,pattern.anchor_date.day,pattern.count_per_year,
        tuple(sorted(pattern.excluded_dates)),tuple(sorted(pattern.weekdays)),pattern.week_parity,
        tuple(sorted(pattern.month_days)),tuple(sorted(pattern.months)),pattern.short_month)


def _validate_annual(pattern,start,end):
    if pattern.frequency!='yearly_count':return
    for year in range(start.year-(pattern.annual_policy=='from_anchor'),end.year+1):
        if year>=pattern.anchor_date.year and (year-pattern.anchor_date.year)%pattern.interval==0:
            (_anchor_for if pattern.annual_policy=='from_anchor' else _annual_for)(pattern,year)


def _month_day_matches(pattern: CalendarPattern, day: date, default: int) -> bool:
    return _matches_days(day,pattern.month_days or [default],pattern.short_month)


def _base_matches_date(pattern: CalendarPattern, day: date) -> bool:
    """ISO week parity uses the ISO week number, including week 53/year boundaries."""
    if day < pattern.anchor_date or day in pattern.excluded_dates:
        return False
    if pattern.week_parity != "any" and day.isocalendar().week % 2 != (1 if pattern.week_parity == "odd" else 0):
        return False
    if pattern.weekdays and day.isoweekday() not in pattern.weekdays:
        return False
    anchor, step = pattern.anchor_date, pattern.interval
    if pattern.frequency == "dates":
        return day in pattern.dates
    if pattern.frequency == "day":
        return (day-anchor).days % step == 0
    if pattern.frequency == "week":
        monday = day-timedelta(days=day.weekday())
        origin = anchor-timedelta(days=anchor.weekday())
        return ((monday-origin).days//7) % step == 0 and day.isoweekday() in (pattern.weekdays or [anchor.isoweekday()])
    if pattern.frequency == "month":
        return ((day.year-anchor.year)*12+day.month-anchor.month) % step == 0 and _month_day_matches(pattern, day, anchor.day)
    if pattern.frequency == "quarter":
        if pattern.quarter_policy=="rolling_months":
            return ((day.year-anchor.year)*12+day.month-anchor.month) % (3*step)==0 and _month_day_matches(pattern,day,anchor.day)
        quarter = (day.month-1)//3
        origin = (anchor.month-1)//3
        month = quarter*3+(1 if pattern.period_edge == "start" else 3)
        return ((day.year-anchor.year)*4+quarter-origin) % step == 0 and day.month == month and _month_day_matches(pattern, day, 1 if pattern.period_edge == "start" else -1)
    if pattern.frequency=="yearly_count" and pattern.annual_policy=="from_anchor":
        for year in (day.year-1,day.year):
            if year<anchor.year or (year-anchor.year)%step: continue
            if day in _anchor_for(pattern,year):return True
        return False
    if (day.year-anchor.year) % step:
        return False
    if pattern.frequency == "yearly_count":
        return day in _annual_for(pattern,day.year)
    return day.month in (pattern.months or [anchor.month]) and _month_day_matches(pattern, day, anchor.day)


def shifted_date(pattern, source):
    if pattern.weekend_policy=='next_workday' and source.weekday()>4:
        return source+timedelta(days=7-source.weekday())
    return source


def occurrence_pairs(pattern: CalendarPattern,start:date,end:date):
    """One obligation per source date, even when several dates shift to Monday."""
    if end<start or (end-start).days>3660:raise ValueError('calendar query must cover 0..3660 days')
    _validate_annual(pattern,start,end)
    return [(day,shifted_date(pattern,day)) for offset in range((end-start).days+1) if _base_matches_date(pattern,day:=start+timedelta(days=offset))]


def matches_date(pattern: CalendarPattern, day: date) -> bool:
    if pattern.weekend_policy=='none': return _base_matches_date(pattern,day)
    if day.weekday()>4 or day in pattern.excluded_dates: return False
    return any(day.toordinal()>offset and _base_matches_date(pattern,day-timedelta(days=offset)) for offset in range(3 if day.weekday()==0 else 1))


def occurrence_dates(pattern: CalendarPattern,start:date,end:date)->list[date]:
    """Unique effective dates, for shifts. Maintenance uses occurrence_pairs."""
    if end<start or (end-start).days>3660:raise ValueError('calendar query must cover 0..3660 days')
    _validate_annual(pattern,start,end)
    return [day for offset in range((end-start).days+1) if matches_date(pattern,day:=start+timedelta(days=offset))]


def pattern_description(pattern: CalendarPattern) -> str:
    units = {"day":"дн.", "week":"нед.", "month":"мес.", "quarter":"календарных кварталов", "year":"календарных лет"}
    if pattern.frequency == "dates":
        text = "Выбранные календарные даты"
    elif pattern.frequency == "quarter" and pattern.quarter_policy == "rolling_months":
        text = f"Каждые {pattern.interval*3} месяца от {pattern.anchor_date}"
    elif pattern.frequency == "yearly_count":
        text = (f"{pattern.count_per_year} раз за цикл от ввода {pattern.anchor_date}, интервалы по длине года"
                if pattern.annual_policy == "from_anchor" else
                f"{pattern.count_per_year} раз за календарный год, равномерно по фактической длине года")
        if pattern.interval>1:
            text+=f'; цикл каждые {pattern.interval} лет от {pattern.anchor_date.year}'
    else:
        text = f"Каждые {pattern.interval} {units[pattern.frequency]} от {pattern.anchor_date}"
    if pattern.frequency == "quarter" and pattern.quarter_policy == "calendar_edge":
        text += "; начало квартала" if pattern.period_edge == "start" else "; конец квартала"
    if pattern.weekdays:
        text += "; дни недели ISO: " + ", ".join(map(str, sorted(pattern.weekdays)))
    if pattern.week_parity != "any":
        text += "; чётные недели ISO" if pattern.week_parity == "even" else "; нечётные недели ISO"
    if pattern.month_days:
        text += "; дни месяца: " + ", ".join("последний" if d == -1 else str(d) for d in sorted(pattern.month_days))
    if pattern.months:
        text+='; месяцы: '+', '.join(map(str,sorted(pattern.months)))
    if pattern.frequency in ('month','quarter','year','yearly_count'):
        text+='; отсутствующий день: пропуск' if pattern.short_month=='skip' else '; отсутствующий день: последний день месяца'
    if pattern.excluded_dates:
        text+=f'; исключений дат: {len(pattern.excluded_dates)}'
    return text + ("; выходные на следующий рабочий день" if pattern.weekend_policy=="next_workday" else "; без переноса выходных") + "; часовой пояс объекта"
