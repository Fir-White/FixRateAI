"""Conservative temporal/cohort selectors, resolved against the server's local day."""
import calendar,re
from datetime import date,timedelta

MONTHS=('январ','феврал','март','апрел','ма[йяе]','июн','июл','август','сентябр','октябр','ноябр','декабр')

def _months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))

def task_search_arguments(request, goal, arguments):
    """Keep an explicit overdue task lookup on the authorized overdue list."""
    title = goal['title'].casefold()
    if (re.search(r'\bпросроч\w*\b', request, re.I)
            and re.search(r'\bпросроч\w*\b', title)
            and not re.search(r'\b(?:предстоящ\w*|будущ\w*|сегодня|завтра|истори\w*|без\s+просроч\w*|не\s+просроч\w*)\b', title)
            and not re.search(r'\b(?:без|не)\s+просроч\w*\b', request, re.I)):
        return {**arguments, 'query': {**(arguments.get('query') or {}), 'period': 'overdue'}}
    return arguments

def selectors(question,clock,*,equipment_scoped=False):
    q=question.casefold().replace('ё','е');today=date.fromisoformat(clock['local_date']);query={}
    if re.search(r'только\s+(?:созданные\s+)?вручную',q):query['origin']='manual'
    elif re.search(r'только\s+(?:из календаря|календарные)',q):query['origin']='scheduled'
    if re.search(r'только\s+(?:на приемке|ожидающ\w* приемки)',q):query['cohort']='in_review'
    elif re.search(r'только\s+ожидающ\w* исполнения',q):query['cohort']='execution_pending'
    # "Раздели на просроченные, на сегодня и будущие" is a classification,
    # not a request to restrict the entire analysis to today.
    days=re.findall(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b',q)
    start=end=None
    if days:
        if len(days)>2:raise ValueError('Укажите один день либо один диапазон дат.')
        def day(value):
            if '.' not in value:return date.fromisoformat(value)
            number,month,year=map(int,value.split('.'))
            return date(year,month,number)
        try:start=day(days[0]);end=day(days[-1])
        except ValueError:raise ValueError('Указана некорректная календарная дата.') from None
    elif relative := re.search(r'\b(?:за\s+)?(?:последн\w*|прошедш\w*)\s+(\d{1,3})\s+(дн\w*|день|недел\w*|месяц\w*|год\w*|лет)\b',q):
        amount = int(relative[1])
        if not 1 <= amount <= 3660:raise ValueError('Укажите положительный ограниченный период.')
        unit = relative[2]
        try:
            start = (_months_before(today, amount * (1 if unit.startswith('месяц') else 12))
                     if unit.startswith(('месяц', 'год', 'лет')) else
                     today - timedelta(days=amount * (7 if unit.startswith('недел') else 1)))
        except (ValueError, OverflowError):
            raise ValueError('Указан недопустимый период.') from None
        end = today
    elif re.search(r'\bза\s+(?:последний\s+)?год\b',q):
        start,end=_months_before(today,12),today
    elif re.search(r'\bна завтра\b',q):start=end=today+timedelta(days=1)
    elif re.search(r'\bтолько на сегодня\b',q):start=end=today
    else:
        matches=[(i,m) for i,pattern in enumerate(MONTHS,1) if (m:=re.search(r'\b(?:за|на|в)\s+'+pattern+r'\w*\s+(\d{4})\b',q))]
        if len(matches)>1:raise ValueError('Укажите один месяц либо диапазон в формате ГГГГ-ММ-ДД.')
        if matches:
            month,match=matches[0];year=int(match[1])
            try:start=date(year,month,1);end=date(year,month,calendar.monthrange(year,month)[1])
            except ValueError:raise ValueError('Указан некорректный год.') from None
    if start:
        if end<start:raise ValueError('Конец периода раньше начала.')
        query.update(starts_on=start.isoformat(),ends_on=end.isoformat())
    # Unsupported explicit selectors must not silently expand to the full ledger.
    elif re.search(r'\b(?:за|на|в)\s+(?:прошл\w*|следующ\w*|текущ\w*|эт\w*)?\s*(?:недел|месяц|год)|\bна\s+\d{1,2}\s+\w+|\b(?:за|на|в)\s+(?:'+ '|'.join(MONTHS) +r')|\bза\s+\d{4}\s+год',q):
        raise ValueError('Для точного анализа укажите период двумя датами ГГГГ-ММ-ДД.')
    if not equipment_scoped and re.search(r'только\s+(?:для\s+)?(?:оборудован|систем|по коду)|с\s+кодом\s+',q):
        raise ValueError('Этот полный отчёт пока не поддерживает отбор по конкретному оборудованию. Уточните запрос к карточке оборудования либо запросите сводку всего объекта.')
    return query
