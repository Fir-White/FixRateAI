"""Literal maintenance type and site-local calendar references."""
from datetime import date, timedelta
import re


TYPE = re.compile(r'(?<!\w)(?:то|to)\s*[-‑–]?\s*(\d{1,3})(?!\w)', re.I)
MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
          'сентября', 'октября', 'ноября', 'декабря')
MONTH = '|'.join(MONTHS)
DAY_LIST = re.compile(
    rf'(?<![\d.])(?P<days>\d{{1,2}}(?:\s*числ[оа]\b)?(?:\s*(?:,\s*|\bи\s+|\bза\s+|\bна\s+)'
    rf'(?:за\s+|на\s+)?\d{{1,2}}(?:\s*числ[оа]\b)?)*)\s+(?P<month>{MONTH})'
    r'(?:\s+(?P<year>\d{4})(?:\s*г(?:ода)?\.?)?)?\b', re.I)
ISO_DATE = re.compile(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)')
RANGE = re.compile(rf'\bс\s+(\d{{1,2}})\s+(?:по|до)\s+(\d{{1,2}})\s+({MONTH})(?:\s+(\d{{4}}))?\b', re.I)
EQUIPMENT_TYPE_CODE = re.compile(
    rf'\b(?:инвентарн\w*\s+код|оборудовани\w*|агрегат\w*|актив\w*)\s+'
    rf'(?:(?:с\s+)?код\w*\s*)?(?:[:№]\s*)?{TYPE.pattern}', re.I)
ORDINAL_WORDS = ('перв', 'втор', 'треть', 'четв[её]рт', 'пят', 'шест', 'седьм', 'восьм', 'девят', 'десят')


def type_keys(value):
    if EQUIPMENT_TYPE_CODE.search(value):
        return []
    return list(dict.fromkeys(f'то{int(match[1])}' for match in TYPE.finditer(value)))


def without_types(value):
    return TYPE.sub(' ', value) if type_keys(value) else value


def numbered_reference(value):
    # An index is meaningful only against the actual previously delivered list.
    if match := re.search(r'(?<!\w)(?:номер\s+|№\s*|(?:у|для)\s+)(\d{1,3})(?:-(?:го|й|ый))?(?!\w)', value):
        return int(match[1])
    for index, prefix in enumerate(ORDINAL_WORDS, 1):
        if re.search(rf'\b(?:у|для|про)\s+{prefix}\w*\b|\b{prefix}\w*\s+(?:из\s+списка|вид\w*|тип\w*)\b', value):
            return index
    return None


def dates(value, local_day):
    """Return exact named days. Invalid dates stay explicit for clarification."""
    today = date.fromisoformat(local_day)
    selected = set()
    try:
        if match := RANGE.search(value):
            first, last, month, year = match.groups()
            number = MONTHS.index(month.lower()) + 1
            start, finish = (date(int(year or today.year), number, int(day)) for day in (first, last))
            if finish < start:
                return None
            return [(start + timedelta(days=offset)).isoformat() for offset in range((finish-start).days+1)]
        for literal in ISO_DATE.findall(value):
            selected.add(date.fromisoformat(literal))
        for match in DAY_LIST.finditer(value):
            month = MONTHS.index(match['month'].lower()) + 1
            year = int(match['year']) if match['year'] else today.year
            selected.update(date(year, month, int(day)) for day in re.findall(r'\d{1,2}', match['days']))
    except ValueError:
        return None
    return [day.isoformat() for day in sorted(selected)]
