"""Conservative temporal/cohort selectors, resolved against the server's local day."""
import calendar,re
from datetime import date,timedelta

MONTHS=('январ','феврал','март','апрел','ма[йяе]','июн','июл','август','сентябр','октябр','ноябр','декабр')

def selectors(question,clock):
    q=question.casefold().replace('ё','е');today=date.fromisoformat(clock['local_date']);query={}
    if re.search(r'только\s+(?:созданные\s+)?вручную',q):query['origin']='manual'
    elif re.search(r'только\s+(?:из календаря|календарные)',q):query['origin']='scheduled'
    if re.search(r'только\s+(?:на приемке|ожидающ\w* приемки)',q):query['cohort']='in_review'
    elif re.search(r'только\s+ожидающ\w* исполнения',q):query['cohort']='execution_pending'
    # "Раздели на просроченные, на сегодня и будущие" is a classification,
    # not a request to restrict the entire analysis to today.
    days=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',q)
    start=end=None
    if days:
        if len(days)>2:raise ValueError('Укажите один день либо один диапазон дат.')
        try:start=date.fromisoformat(days[0]);end=date.fromisoformat(days[-1])
        except ValueError:raise ValueError('Указана некорректная календарная дата.') from None
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
    if re.search(r'только\s+(?:для\s+)?(?:оборудован|систем|по коду)|с\s+кодом\s+',q):
        raise ValueError('Этот полный отчёт пока не поддерживает отбор по конкретному оборудованию. Уточните запрос к карточке оборудования либо запросите сводку всего объекта.')
    return query
