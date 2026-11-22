"""Ground aggregate selectors in comparative wording and literal calendar values."""
import re
from datetime import date

from .analysis_contract import AnalysisRequest, Window
from .analysis_scope import MONTHS, selectors


RANK = (r'наибольш\w*|наиболее\s+загруж\w*|больше\s+всего|максимальн\w*|сам\w*\s+загруж\w*|'
        r'ранжир\w*|по\s+убыван\w*|топ\b|top\b|most\b')
COHORT = r'просроч\w*|наруш\w*|незаверш\w*|незакры\w*|открытых\s+работ|загруж\w*|нагрузк\w*|overdue|unfinished|workload'
EQUIPMENT = r'оборудован\w*|установ\w*|агрегат\w*|asset\w*|equipment'
ASSIGNEE = r'исполнител\w*|работник\w*|сотрудник\w*|assignee\w*|worker\w*'
NUMBERS = (r'одну|один|одного|one', r'две|два|двух|two', r'три|тр[её]х|three', r'четыре|четыр[её]х|four',
           r'пять|пяти|five', r'шесть|шести|six', r'семь|семи|seven', r'восемь|восьми|eight',
           r'девять|девяти|nine', r'десять|десяти|ten')
ISO_DAY = r'\b\d{4}-\d{2}-\d{2}\b'
PLANNING = r'период\w*\s+планир\w*|запланирован\w*|планов\w*\s+работ\w*|planning\s+period'
TASK = r'задани\w*|наряд\w*|task\w*|work\s+order\w*'
EARLIEST = r'ранн\w*|старейш\w*|стар\w*\s+просроч\w*|earliest|oldest|давн\w*'
GAP = r'недоста\w*|неполн\w*|не\s+хватает|без\s+(?:отч[её]т\w*|фото|материал\w*)|missing|incomplete'
MATERIAL = r'материал\w*|фото\w*|отч[её]т\w*|чек[-‑– ]?лист\w*|акт\w*|при[её]мк\w*|evidence|report'
SERVICE_GAP = r'без\s+(?:фактическ\w*\s+)?(?:подтвержд[её]нн\w*|принят\w*)|не\s+(?:проводил\w*|подтвержд\w*)'


def has(pattern, value):
    return re.search(r'\b(?:' + pattern + ')', value, re.I)


def clauses(question):
    return re.split(r'(?<=[.!?;])\s+|\n+', question)


def ranked_clause(phrases):
    return next((phrase for phrase in phrases if has(RANK, phrase) and has(COHORT, phrase) and
                 (has(EQUIPMENT, phrase) or has(ASSIGNEE, phrase))), None)


def compare_clause(phrases):
    return next((phrase for phrase in phrases if has(r'сравн\w*|compare', phrase) and has(PLANNING, phrase)), None)


def selection_clause(phrases):
    from .semantic_plan import UUID

    for phrase in phrases:
        if has(UUID, phrase):
            continue
        if has(TASK, phrase):
            if has(EARLIEST, phrase) and has(r'просроч\w*|overdue|нормативн\w*\s+срок', phrase):
                return 'task', 'earliest_overdue', phrase
            if has(GAP, phrase) and has(MATERIAL, phrase):
                return 'task', 'missing_materials', phrase
        if has(EQUIPMENT, phrase) and has(SERVICE_GAP, phrase) and has(r'обслуживан\w*|то\b', phrase):
            return 'equipment', 'without_service', phrase
    return None


def candidate(question):
    phrases = clauses(question)
    return bool(selection_clause(phrases) or ranked_clause(phrases) or compare_clause(phrases))


def amount(phrase):
    if phrase.isdecimal():
        return int(phrase)
    return next(i for i, number in enumerate(NUMBERS, 1) if re.fullmatch(number, phrase, re.I))


def anchored_date(question):
    prefix = r'\b(?:на дату|по состоянию на|сегодня|as of)\s+'
    if match := re.search(prefix + '(' + ISO_DAY + ')', question, re.I):
        return date.fromisoformat(match[1])
    months = '|'.join(rf'(?P<m{i}>{month}\w*)' for i, month in enumerate(MONTHS, 1))
    if match := re.search(prefix + r'(\d{1,2})\s+(?:' + months + r')\s+(\d{4})\b', question, re.I):
        month = next(i for i in range(1, 13) if match[f'm{i}'])
        return date(int(match.group(match.lastindex)), month, int(match[1]))
    return None


def grounded_analysis(question, interpretation, clock):
    existing = getattr(interpretation, 'analysis', None)
    if existing and existing.source_text not in question:
        existing = None
    phrases = clauses(question)
    selected = selection_clause(phrases)
    if selected:
        group, metric, anchor = selected
        if group=='task' and metric=='earliest_overdue' and not has(r'просроч\w*|overdue', anchor):
            if not has(r'просроч\w*|overdue', question):
                return existing
        given_window = []
        if metric=='without_service':
            try:
                days = selectors(anchor, clock, equipment_scoped=True)
                if {'starts_on','ends_on'} <= days.keys():
                    given_window.append(Window(starts_on=days['starts_on'], ends_on=days['ends_on']))
            except ValueError:
                pass
        options = dict(source_text=anchor.strip(), group_by=group, metric=metric,
                       limit=1 if group=='task' else 10, as_of=anchored_date(question), windows=given_window)
        if existing and existing.group_by==group:
            return existing.model_copy(update=options)
        return AnalysisRequest(**options)
    rank = ranked_clause(phrases)
    if rank and not has(r'человеко-час\w*|по\s+трудозатрат\w*|по\s+длительност\w*|person.hours', rank):
        group = 'equipment' if has(EQUIPMENT, rank) else 'assignee'
        metric = 'overdue' if has(r'просроч\w*|наруш\w*\s+(?:нормативн\w*\s+)?срок\w*|overdue', rank) else 'unfinished'
        number = r'(?P<count>\d{1,3}|' + '|'.join(NUMBERS) + r')'
        entity = EQUIPMENT if group=='equipment' else ASSIGNEE
        limit = re.search(r'\b' + number + r'\s+(?:\w+\s+){0,3}(?:' + entity + r')\b|'
                          r'\b(?:топ|top)[ -]*(' + r'\d{1,3}' + ')\b', rank, re.I)
        count = amount(limit['count'] or limit[2]) if limit else (existing.limit if existing else None)
        explicit_as_of = anchored_date(question)
        if not explicit_as_of and existing and existing.as_of and existing.as_of.isoformat() in question:
            explicit_as_of = existing.as_of
        all_groups = not limit and bool(has(r'(?:всех|все|all)\s+(?:(?:подходящ|доступн|единиц|активн)\w*\s+){0,2}(?:' + entity + r')', rank))
        options = dict(source_text=rank.strip(), group_by=group, metric=metric, limit=None if all_groups else count,
                       all_groups=all_groups, as_of=explicit_as_of)
        singular = (r'(?:какое\s+оборудовани[ея]|какой\s+агрегат|како[йе].*наибольш\w*)' if group=='equipment' else
                    r'(?:исполнител[ьяю]|работник[ау]?|сотрудник[ау]?|assignee|worker)\s+(?:с|with)\b')
        if not limit and not all_groups and has(singular, rank):
            options['limit'] = 1
        if existing and existing.group_by==group:
            return existing.model_copy(update=options)
        return AnalysisRequest(**options)
    compare = compare_clause(phrases)
    if compare:
        days = re.findall(ISO_DAY, compare)
        windows = []
        if len(days) in (2,4):
            if len(days)==2:
                days = [days[0], days[0], days[1], days[1]]
            windows = [Window(starts_on=days[i], ends_on=days[i+1]) for i in (0,2)]
        if existing and existing.group_by=='period':
            return existing.model_copy(update={'windows': windows}) if windows else existing
        return AnalysisRequest(source_text=compare.strip(), group_by='period', metric='planned', windows=windows)
    return existing


def requested_projections(question, request):
    if request.group_by=='task':
        fields = {'task_details': request.source_text}
        if request.metric=='missing_materials' or has(MATERIAL, question):
            fields['task_materials'] = request.source_text
        return fields, None
    if request.group_by=='assignee' and has(r'назначени\w*|назначенн\w*\s+им\s+работ\w*|assignments', question):
        return {'staff_assignments': request.source_text}, None
    if request.group_by!='equipment':
        return {}, None
    found = {}
    history_months = None
    for clause in clauses(question):
        if has(r'инвентарн\w*\s+код\w*|состояни\w*\s+оборудован\w*|(?:укажи|покажи|проверь|сверь)\w*[^.!?;]{0,65}\bсостояни\w*', clause):
            found['equipment_details'] = clause.strip()
        if has(r'названи\w*|перечисл\w*|перечень', clause) and has(r'просроч\w*|наруш\w*\s+срок', clause):
            found['overdue_tasks'] = clause.strip()
        history = has(r'истори\w*\s+(?:(?:фактическ|подтвержд[её]нн|принят)\w*\s+)*(?:то\b|обслуживан\w*)', clause)
        if history or has(r'фактическ\w*\s+(?:подтвержд\w*\s+)?(?:то\b|обслуживан\w*)', clause):
            found['maintenance_history' if history else 'latest_maintenance'] = clause.strip()
            relative = has(r'(?:последн\w*|прошедш\w*)\s+(\d{1,3})\s+месяц\w*', clause)
            if relative:
                history_months = int(relative[1])
        if has(r'(?:действующ\w*|утвержд\w*)\s+регламент\w*|регламент\w*\s+обслуживан\w*|(?:сверь|проверь|прочитай|покажи)\w*\s+регламент\w*', clause):
            found['active_regulations'] = clause.strip()
        if has(r'календар\w*\s+(?:(?:следующ|ближайш|планов)\w*\s+)?(?:то\b|обслуживан\w*)|срок\w*\s+(?:следующ\w*|ближайш\w*)\s+то\b|ближайш\w*\s+то\b|(?:проверь|покажи|прочитай)\w*[^.!?;]{0,75}\bкалендар\w*', clause):
            found['maintenance_calendar'] = clause.strip()
    return found, history_months


def recommendation_count(question):
    numbers = '|'.join(NUMBERS)
    match = has(r'(?:предлож\w*|сформулиру\w*|рекоменду\w*)\s+(?:(\d{1,2}|' + numbers +
                r')\s+)?(?:\w+\s+){0,4}(?:действ\w*|рекомендаци\w*|шаг\w*)', question)
    return amount(match[1]) if match and match[1] else 3 if match else None
