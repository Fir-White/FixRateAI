"""Interpret requested results independently of the transport/tool catalogue."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Literal

from pydantic import Field

from app.schemas.assistant import GoalSpec, GoalSelector, Input, ToolSelection

from .analysis_scope import selectors
from .intents import explicit_revision, mutation_command_requested, mutation_requested, prohibits_changes


Intent = Literal[
    'self_profile', 'staff_details', 'password', 'equipment_details', 'equipment_exists',
    'task_details', 'task_list', 'task_count', 'maintenance_history', 'service_frequency',
    'manufacturer_source', 'workbook_row', 'notifications', 'start_task', 'assign_task',
    'cancel_task', 'rename_equipment', 'move_equipment', 'other',
    'read_notifications', 'edit_equipment', 'quoted_command', 'reference_details',
    'equipment_tasks', 'latest_maintenance', 'active_regulations', 'maintenance_calendar',
    'general_explanation', 'recommend_actions',
    'explain_results',
]
AnswerField = Literal[
    'name', 'location', 'role', 'site', 'email', 'code', 'state', 'start', 'deadline',
    'crew_size', 'assignees', 'checklist', 'revision', 'closed',
]


class RequestedResult(Input):
    intent: Intent
    subjects: list[str] = Field(default_factory=list, max_length=12)
    fields: list[AnswerField] = Field(default_factory=list, max_length=12)
    period: Literal['upcoming', 'overdue', 'all', 'undated'] | None = None
    sheet: str | None = Field(default=None, max_length=255)
    row: int | None = Field(default=None, ge=1, le=1048576)
    columns: list[str] = Field(default_factory=list, max_length=12)
    value: str | None = Field(default=None, max_length=1000)
    one_worker: bool = False
    source_text: str | None = Field(default=None, min_length=2, max_length=700)
    recommendation_count: int | None = Field(default=None, ge=1, le=10)


class RequestedResults(Input):
    results: list[RequestedResult] = Field(min_length=1, max_length=12)
    read_only: bool = False
    constraints: list[str] = Field(default_factory=list, max_length=12)
    response_format: str | None = Field(default=None, max_length=400)


class RequestCoverageReview(Input):
    missing: list[RequestedResult] = Field(max_length=12)
    constraints: list[str] = Field(default_factory=list, max_length=12)


ROUTES = {
    'self_profile': ('profile_read', 'Мой профиль'),
    'staff_details': ('staff_find', 'Сотрудник'),
    'equipment_details': ('equipment_read', 'Оборудование'),
    'equipment_exists': ('equipment_find', 'Наличие оборудования'),
    'task_details': ('task_read', 'Задание'),
    'task_list': ('tasks_find', 'Задания'),
    'task_count': ('tasks_analyze', 'Число заданий'),
    'maintenance_history': ('equipment_service_history', 'Фактическое обслуживание'),
    'service_frequency': ('regulations_read', 'Сохранённый регламент'),
    'workbook_row': ('attachment_read', 'Строка XLSX'),
    'notifications': ('notifications_list', 'Мои уведомления'),
    'start_task': ('task_start', 'Начало задания'),
    'assign_task': ('task_assign', 'Назначение исполнителя'),
    'cancel_task': ('task_cancel', 'Отмена задания'),
    'rename_equipment': ('equipment_edit', 'Название оборудования'),
    'move_equipment': ('equipment_edit', 'Место установки оборудования'),
    'edit_equipment': ('equipment_edit', 'Изменение оборудования'),
    'read_notifications': ('notifications_read_all', 'Отметка уведомлений прочитанными'),
    'reference_details': ('task_read', 'Карточка по ID'),
    'equipment_tasks': ('tasks_find', 'Задания оборудования'),
    'latest_maintenance': ('equipment_service_history', 'Последнее подтверждённое обслуживание'),
    'active_regulations': ('regulations_read', 'Действующие регламенты'),
    'maintenance_calendar': ('calendar_evidence', 'Расчётный календарь обслуживания'),
    'general_explanation': ('', 'Инженерное пояснение'),
    'explain_results': ('', 'Пояснение проверенных данных'),
    'recommend_actions': ('', 'Рекомендации'),
}
DISCUSSION = {'general_explanation', 'explain_results', 'recommend_actions'}
EQUIPMENT_ANALYSIS = {'equipment_tasks', 'latest_maintenance', 'active_regulations', 'maintenance_calendar'}
CHANGES = {'start_task', 'assign_task', 'cancel_task', 'rename_equipment', 'move_equipment', 'edit_equipment', 'read_notifications'}
TASK_REFS = {'task_details', 'start_task', 'assign_task', 'cancel_task', 'reference_details'}
EQUIPMENT_REFS = {'equipment_details', 'equipment_exists', 'maintenance_history', 'service_frequency',
                  'rename_equipment', 'move_equipment', 'edit_equipment'} | EQUIPMENT_ANALYSIS
UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
ASSET = r'[A-ZА-ЯЁ][A-ZА-ЯЁ0-9]{0,23}(?:[-_][A-ZА-ЯЁ0-9]{1,24})+'
QUOTED = re.compile(r'«([^»\n]+)»|"([^"\n]+)"')
EXTERNAL_CALENDAR = re.compile(r'\b(?:из|по)\s+(?:неподключ[её]нн\w*\s+)?'
                               r'(?:внешн|сторонн)\w*\s+(?:календар|расписани)\w*', re.I)
WRITE_VERBS = {
    'start_task': r'начни(?:те)?|запусти(?:те)?|приступи(?:те)?|начало|start',
    'assign_task': r'назнач(?:ь|ьте|ение|ить)|распредел(?:и|ите|ение)|assign',
    'cancel_task': r'отмен(?:и|ите|у|ить)|cancel',
    'rename_equipment': r'переимен(?:уй|уйте|овать)|измен(?:и|ите)|замен(?:и|ите)|rename|change',
    'move_equipment': r'перенес(?:и|ите|ти)|смен(?:и|ите|ить)|(?:из|по)мен(?:яй|яйте|и|ите|ить)|change|move',
}
LEGACY_WRITE_TERMS = {
    'staff_edit': r'измени\w*|обнови\w*|установи\w*|set|change|update',
    'task_reopen': r'переоткрой\w*|открой\s+(?:снова|повторно)|верни\s+на\s+доработку|reopen',
    'equipment_retire': r'выведи\w*\s+из\s+эксплуатации|спиши\w*|retire',
    'notifications_read_all': r'отметь\w*.{0,50}прочитан|mark.{0,40}read',
}
FIELD_PATTERNS = {
    'name': r'наименован\w*|названи\w*|называетс[яь]|\bим(?:я|ен\w*)\b|фио|заголов\w*',
    'location': r'мест[оае]\s+установк\w*|расположен\w*|где\s+(?:он[аои]?\s+)?(?:установлен\w*|смонтирован\w*|размещ[её]н\w*|стоит|стоят)',
    'role': r'\bрол(?:ь|и|ей|ью|ям|ями|ях)\b|\bдолжност\w*',
    'site': r'(?:текущ\w*|мо[её]|выбранн\w*)\s+(?:здани\w*|объект\w*)|(?:здани\w*|объект\w*)\s+(?:сейчас\s+)?(?:выбран\w*|открыт\w*|актив\w*)',
    'email': r'e-?mail\b|электронн\w*\s+(?:почт|адрес)\w*|рабоч\w*\s+почт\w*',
    'code': r'инвентарн\w*\s+код\w*',
    'state': r'статус\w*|состояни\w*',
    'start': r'(?:врем[яени]+|дат\w*|день)\s+начала|(?:планов\w*|запланированн\w*)\s+начал\w*|когда\s+начн',
    'deadline': r'(?:нормативн\w*|крайн\w*)\s+срок\w*|дедлайн\w*',
    'crew_size': r'число\s+(?:исполнител\w*|работник\w*|сотрудник\w*)|сколько\s+(?:(?:нужн|требу)\w*\s+)?(?:работник\w*|исполнител\w*|сотрудник\w*)|состав\s+бригады',
    'assignees': r'кто\s+(?:назначен|выполняет|исполнител)|фамили\w*\s+исполнител\w*',
    'checklist': r'чек[ -]?лист\w*|пункты\s+проверк\w*',
    'revision': r'ревизи\w*|верси\w*',
    'closed': r'(?:дат\w*|врем\w*)\s+(?:фактическ\w*\s+)?(?:закрыти\w*|завершени\w*)|когда\s+(?:фактически\s+)?(?:закры[лт]|заверш[ие])',
}
FIELD_GROUPS = {
    'self_profile': ('name', 'role', 'site', 'email'),
    'staff_details': ('name', 'role', 'email'),
    'equipment_details': ('code', 'name', 'location', 'state', 'revision'),
    'task_details': ('name', 'state', 'start', 'deadline', 'crew_size', 'assignees', 'checklist', 'revision', 'closed'),
    'reference_details': ('name', 'state', 'revision'),
    'task_list': ('name', 'state', 'start', 'deadline', 'crew_size', 'assignees'),
    'equipment_tasks': ('name', 'state', 'start', 'deadline', 'crew_size', 'assignees'),
}
DEFAULT_FIELDS = {
    'self_profile': ('name', 'role', 'site'),
    'staff_details': ('name', 'role'),
    'equipment_details': ('code', 'name', 'location', 'state'),
    'task_details': ('name', 'state', 'start', 'deadline'),
    'task_list': ('name', 'start', 'state'),
    'equipment_tasks': ('name', 'state', 'deadline'),
}

EQUIPMENT_FIELDS = {
    'name': r'(?:названи|наименован)\w*',
    'location': r'мест[оае]\s+установк\w*',
}
EQUIPMENT_CHANGE = re.compile(
    r'(?:' + '|'.join(f'(?P<{key}>{value})' for key, value in EQUIPMENT_FIELDS.items()) +
    r')(?P<subject>[^«»"\n.!?;]{0,180}?)\s+(?:на|to)\s+'
    r'(?P<value>«[^»\n]+»|"[^"\n]+"|[^«»"\n.!?;,]+?'
    r'(?=\s+(?:и|а\s+также)\s+[\w -]{1,65}\s+(?:на|в|to)\s+|[.!?;,\n]|$))', re.I,
)
SECRET_WORD = r'\b(?:парол\w*|password|токен\w*|секрет\w*|api[ -]?ключ\w*)\b'
TASK_WORD = r'\b(?:задани|наряд|работ)[а-яё]*\b|\btask_id\b'
EQUIPMENT_WORD = r'\b(?:оборудовани|агрегат)[а-яё]*\b|\bequipment_id\b'
SHEET_LIST = r'\b(?:список|перечень|названи\w*)\s+лист\w*|\b(?:какие|все)\s+листы\b'


def _literal(text, value):
    return bool(value and re.search(r'(?<!\w)' + re.escape(value.strip()) + r'(?!\w)', text, re.I))


def _matches(pattern, text):
    return bool(re.search(pattern, text, re.I))


def positive_text(text):
    """Remove explicit exclusions from a field or column request."""
    negative = r'\bне\s+(?:надо|нужн\w*|требу\w*|выводи\w*|показывай\w*|печатай\w*|перечисляй\w*|путай\w*)\b'
    parts = []
    for sentence in re.split(r'[.!?;]\s+(?=\S)', text):
        chunks = re.split(r',\s*', sentence)
        negation = re.search(negative, sentence, re.I)
        if negation and re.search(negative, chunks[-1], re.I):
            main = chunks[0]
            if len(chunks) == 1 or not _matches(r'\b(?:выведи|выпиши|скажи|дай|перечисли|покажи|укажи|назови)\b', main):
                continue
            sentence = ', '.join(chunks[:-1])
        parts.append(re.split(r'\bбез\b|' + negative, sentence, maxsplit=1, flags=re.I)[0])
    return ' '.join(parts)


def equipment_changes(question):
    """Return exact field assignments and whether the requested set is incomplete."""
    clean = QUOTED.sub(' ', question)
    mentioned = {key for key, pattern in EQUIPMENT_FIELDS.items() if _matches(pattern, clean)}
    if not mentioned or not authorizes_operation('edit_equipment', question):
        return {}, False
    changes = {}
    incomplete = False
    for match in EQUIPMENT_CHANGE.finditer(question):
        # A field name inside a quoted value is data.
        if any(quoted.start() < match.start() < quoted.end() for quoted in QUOTED.finditer(question)):
            continue
        key = 'name' if match['name'] else 'location'
        value = match['value'].strip()
        if value.startswith(('«', '"')):
            value = value[1:-1]
        if key in changes or not value or (changes and match['subject'].strip()):
            incomplete = True
        changes[key] = value
    if len(mentioned) > 1 or _matches(r'\b(?:в\s+одной\s+карточке|одним\s+изменением|атомарно)\b', clean):
        incomplete |= changes.keys() != mentioned
    if _matches(r'\bкотор\w+\s+(?:скажу|сообщу|уточню|пришлю)|\b(?:ещ[её]|пока)\s+не\s+(?:выбрал|решил)\w*\b', clean):
        incomplete = True
    for tail in re.finditer(r'\b(?:и|а\s+также)\s+(?P<field>[\w -]{1,55}?)\s+(?:на|в|to)\b', clean, re.I):
        if not any(_matches(pattern, tail['field']) for pattern in EQUIPMENT_FIELDS.values()):
            incomplete = True
    return changes, incomplete


def _reason(question, subject):
    if not subject:
        return None
    match = re.search(re.escape(subject) + r'\s*(?:[:,]\s*(?:причин\w*\s*[:—–-]\s*)?|'
                      r'\s+(?:по причине|причина)\s*[:—–-]?\s*)(.+)', question, re.I)
    if not match:
        return None
    quoted = QUOTED.match(match[1])
    if quoted:
        return quoted[1] or quoted[2]
    candidate = re.split(r'[.!?;\n](?:\s|$)', match[1], maxsplit=1)[0].strip()
    return candidate or None


def explicit_results(question):
    """Resolve standalone operations whose authorization and operands are in the text."""
    clean = QUOTED.sub(' ', question)
    quotes = list(QUOTED.finditer(question))
    if len(quotes) == 1 and _matches(r'\b(?:перескаж\w*|перефразиру\w*|опиши\w*.*(?:действие|смысл)|объясни\w*.*(?:означает|смысл))\b', clean):
        return RequestedResults(results=[RequestedResult(intent='quoted_command', value=quotes[0][1] or quotes[0][2])])
    if _matches(SECRET_WORD, clean) and not _matches(r'\b(?:почт\w*|e-?mail|фио|рол[ьи]|имя)\b', clean):
        if _matches(r'\b(?:найди\w*|сообщи\w*|назови\w*|покажи\w*|выдай\w*|скажи\w*|како[йе])\b', clean):
            return RequestedResults(results=[RequestedResult(intent='password')])
    if authorizes_operation('read_notifications', question) and _matches(r'\b(?:все|all)\b', clean):
        return RequestedResults(results=[RequestedResult(intent='read_notifications')])
    changes, incomplete = equipment_changes(question)
    if (changes or incomplete) and not _matches(r'\b(?:затем|после этого|потом)\b', clean):
        return RequestedResults(results=[RequestedResult(intent='edit_equipment')])
    if authorizes_operation('cancel_task', question) and _matches(UUID, clean) and not _matches(r'\b(?:затем|после этого|потом)\b', clean):
        return RequestedResults(results=[RequestedResult(intent='cancel_task')])
    if authorizes_operation('start_task', question) and _matches(UUID, clean) and not _matches(r'\b(?:затем|после этого|потом)\b', clean):
        return RequestedResults(results=[RequestedResult(intent='start_task')])
    if not mutation_command_requested(clean) and not _matches(r'\b(?:затем|также|после этого)\b', clean):
        workbook = _matches(r'\b(?:xlsx|excel|лист\w*)\b', clean)
        coordinates = _matches(r'\b(?:строк|ячейк|столбц|заголов|структур)\w*|' + SHEET_LIST, clean)
        if workbook and coordinates:
            return RequestedResults(results=[RequestedResult(intent='workbook_row')])
    if not mutation_command_requested(clean) and not _matches(TASK_WORD + '|' + EQUIPMENT_WORD, clean):
        ids = list(dict.fromkeys(re.findall(r'\b' + UUID + r'\b', clean, re.I)))
        generic = any(_matches(FIELD_PATTERNS[field], clean) for field in ('state', 'revision'))
        typed = any(_matches(FIELD_PATTERNS[field], clean) for field in ('location', 'start', 'deadline', 'checklist', 'closed', 'crew_size', 'assignees', 'site'))
        if len(ids) == 1 and generic and not typed and not _matches(r'\b(?:и\s+ещ[её]|затем|парол\w*|уведомлен\w*|паспорт\w*)\b', clean) and not asset_references(clean):
            return RequestedResults(results=[RequestedResult(intent='reference_details', subjects=ids)])
    return None


def authorizes_operation(intent, question):
    """An interpreted write still needs an independently supported user verb."""
    text = QUOTED.sub(' ', question)
    if intent == 'read_notifications':
        return (_matches(r'^\s*(?:пожалуйста,?\s+)?(?:отметь\w*|пометь\w*|mark)\b[^.!?;]*(?:прочитан\w*|\bread\b)', text)
                and _matches(r'уведомлен\w*|notifications', text)
                and not _matches(r'\b(?:чуж\w*|коллег\w*|другого|сотрудник\w*|other)\b', text))
    if intent == 'edit_equipment':
        return any(authorizes_operation(action, question) for action in ('rename_equipment', 'move_equipment'))
    if intent == 'start_task' and _matches(r'^\s*приступаю\b', text):
        return _matches(r'\bподготовь\w*\s+(?:карточк\w*|подтверждени\w*)', text)
    pattern = WRITE_VERBS.get(intent)
    if not pattern:
        return False
    for match in re.finditer(r'\b(?:' + pattern + r')\b', text, re.I):
        clause = re.split(r'[.!?;\n]|\b(?:затем|потом|но)\b', text[:match.start()], flags=re.I)[-1]
        if match[0].casefold() in ('начало', 'назначение', 'распределение', 'отмену') and not _matches(r'подготов|предлож|prepare', clause):
            continue
        if re.fullmatch(r'\s*(?:(?:пожалуйста|please)\s+)?(?:(?:подготовь(?:те)?|предложи(?:те)?|prepare)\s+(?:предложение\s+)?(?:изменения\s+|на\s+)?)?', clause, re.I):
            return True
        if mutation_requested(clause + match[0]) and _matches(r'\b(?:и|then)\s*$', clause):
            return True
    return False


def may_offer_legacy(tool, question, history=()):
    """Reject clear conflicts at the proposal boundary, including on resumed plans."""
    exact = {
        'task_start': ('start_task',), 'task_assign': ('assign_task',), 'task_cancel': ('cancel_task',),
        'notifications_read_all': ('read_notifications',),
    }
    clean = QUOTED.sub(' ', question)
    # A reply to a prior choice is meaningful only within a genuine earlier change request.
    if tool == 'task_assign' and history and len(question) <= 250 and '?' not in question:
        prior = history[0]
        if (_matches(r'\b(?:выберите|укажите|уточните|select|choose)\b', prior['answer'])
                and authorizes_operation('assign_task', prior['content'])):
            return True
    if tool in exact:
        return any(authorizes_operation(intent, clean) for intent in exact[tool])
    if tool in LEGACY_WRITE_TERMS:
        return mutation_requested(clean) and _matches(r'\b(?:' + LEGACY_WRITE_TERMS[tool] + r')', clean)
    return mutation_requested(clean) or any(authorizes_operation(intent, clean) for intent in CHANGES)


def _subjects(result, question):
    candidates = list(dict.fromkeys(value.strip() for value in result.subjects if _literal(question, value)))
    if result.intent in TASK_REFS:
        ids = list(dict.fromkeys(re.findall(r'\b' + UUID + r'\b', question, re.I)))
        return [value.lower() for value in candidates if re.fullmatch(UUID, value, re.I)] or (ids if len(ids) == 1 else [])
    if result.intent in EQUIPMENT_REFS:
        clean = QUOTED.sub(lambda m: m[1] or m[2], question)
        identities = re.findall(r'\bequipment_id\s*[:=]\s*(' + UUID + r')\b', clean, re.I)
        if len(set(identities)) == 1:
            return [identities[0].lower()]
        if candidates:
            return candidates
        if result.source_text and result.source_text in question:
            scoped_codes = asset_references(QUOTED.sub(' ', result.source_text))
            if scoped_codes:
                return scoped_codes
        codes = asset_references(QUOTED.sub(' ', question))
        return codes if len(codes) == 1 else []
    if result.intent == 'staff_details' and not candidates:
        emails = re.findall(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', question)
        names = re.findall(r'(?<!\w)[А-ЯЁA-Z][а-яёa-z-]{2,}(?:\s+[А-ЯЁA-Z][а-яёa-z-]{2,}){1,2}(?!\w)', question)
        exact = list(dict.fromkeys(emails or names))
        return exact if len(exact) == 1 else []
    return candidates


def asset_references(text):
    without_ids = re.sub(r'\b' + UUID + r'\b', ' ', text, flags=re.I)
    return list(dict.fromkeys(value for value in re.findall(r'\b' + ASSET + r'\b', without_ids, re.I)
                              if any(char.isdigit() for char in value)))


def _projection_text(question, intent, subject):
    if intent == 'reference_details':
        return question
    if subject:
        clauses = re.split(r',\s*(?=(?:из|для|по)\s+' + UUID + r')', question, flags=re.I)
        if len(clauses) > 1:
            return next((clause for clause in clauses if _literal(clause, subject)), question)
    if intent == 'self_profile':
        clauses = re.split(r',\s*|\s+и\s+(?=[^,.!?]*(?:\bаккаунт\w*|\bпрофил\w*|'+TASK_WORD+r'))', question, flags=re.I)
        personal = [clause for clause in clauses if _matches(r'\b(?:мо[йяеию]|мо[её]м|моего|моему|мо[её])\b|\bавторизован\w*', clause)]
        if len(personal) == 1 and not _matches(UUID, personal[0]):
            return personal[0]
    if intent in ('equipment_details', 'equipment_exists') and subject:
        codes = re.findall(r'\b' + ASSET + r'\b', QUOTED.sub(' ', question), re.I)
        if set(code.casefold() for code in codes) == {subject.casefold()} and not _matches(r'\b' + UUID + r'\b', question):
            return question
    clauses = re.split(r'[!?;.]\s+|\s+(?:затем|после\s+этого|а\s+также)\s+|\s+и\s+(?=(?:\w+\s+){0,3}(?:покажи|скажи|найди|назови|укажи|где|измени)\b)', question, flags=re.I)
    if subject:
        matching = [clause for clause in clauses if _literal(clause, subject)]
        if len(matching) == 1:
            clause = matching[0]
            for join in re.finditer(r'\s+и\s+', clause, re.I):
                left, right = clause[:join.start()], clause[join.end():]
                left_ids = _matches(r'\b' + UUID + r'\b', left)
                right_ids = _matches(r'\b' + UUID + r'\b', right)
                if left_ids == right_ids:
                    continue
                equipment = left if right_ids else right
                if _matches(r'\b' + ASSET + r'\b', QUOTED.sub(' ', equipment)):
                    return left if _literal(left, subject) else right
            return clause
    if intent == 'self_profile':
        matching = [clause for clause in clauses if _matches(r'\b(?:мо[йяеию]|текущ\w*)\b', clause)]
        if len(matching) == 1:
            return matching[0]
    return question


def normalize_equipment_requirements(interpretation, question):
    """Bind explicit task cohorts and accepted dates to literal equipment references."""
    clean = QUOTED.sub(' ', question)
    codes = asset_references(clean)
    if len(codes) != 1 or mutation_command_requested(clean):
        return interpretation
    code = codes[0]
    task_words = r'\b(?:работ|задан|наряд)\w*\b'
    overdue_words = r'\b(?:просроч\w*|пропущенн\w*\s+(?:нормативн\w*\s+)?срок\w*|ист[её]к\w*\s+срок\w*)\b'
    open_words = r'\b(?:незаверш\w*|незакры\w*|открыт\w*|не\s+закрыт\w*|не\s+заверш\w*|остаются\s+открыт\w*)\b'
    latest_words = r'\b(?:последн\w*|наиболее\s+свеж\w*|сам\w*\s+свеж\w*)\b'
    actual_words = r'\b(?:подтвержд\w*|принят\w*|фактическ\w*|выполненн\w*|состоялось)\b'
    clauses = [clause.strip() for clause in re.split(r'(?<=[.!?;])\s+(?!\d)|\n+', question) if clause.strip()]
    relevant = [clause for clause in clauses if _literal(clause, code)]
    task_clause = next((clause for clause in relevant if (_matches(task_words, clause) or _matches(r'\bпросрочк\w*\b', clause))
                        and (_matches(overdue_words, clause) or _matches(open_words, clause))
                        and not _matches(UUID, clause)), None)
    date_clause = next((clause for clause in relevant if _matches(latest_words, clause)
                        and _matches(actual_words, clause)
                        and _matches(r'\b(?:то|обслужива\w*|работ\w*|отч[её]т\w*)\b', clause)), None)
    if not task_clause and not date_clause:
        return interpretation
    results = list(interpretation.results)
    if task_clause:
        periods = []
        overdue = _matches(overdue_words, task_clause) and not _matches(r'\b(?:без|не)\s+просроч\w*\b', task_clause)
        paired = _matches(open_words + r'.{0,70}(?:[,;]\s*|\b(?:или|и|отдельно)\s+)просроч\w*\b', task_clause)
        if _matches(open_words, task_clause) and (not overdue or paired):
            periods.append('all')
        if overdue:
            periods.append('overdue')
        if periods:
            existing = [result for result in results if result.intent == 'equipment_tasks'
                        and (not result.subjects or any(subject.casefold() == code.casefold() for subject in result.subjects))]
            prototype = existing[0] if existing else RequestedResult(intent='equipment_tasks')
            results = [result for result in results if result not in existing and not (
                result.intent in ('task_list', 'task_details') and (not result.source_text or
                    result.source_text in task_clause or code in result.source_text))]
            results.extend(prototype.model_copy(update={'subjects': [code], 'source_text': task_clause[:700],
                           'period': period}) for period in periods)
    if date_clause:
        existing = [result for result in results if result.intent == 'latest_maintenance' and (
                    not result.subjects or any(subject.casefold() == code.casefold() for subject in result.subjects))]
        if not existing:
            results = [result for result in results if not (result.intent == 'maintenance_history' and
                       (not result.source_text or result.source_text in date_clause) and
                       not _matches(r'\b(?:перечен\w*|всю\s+истори\w*)\b', date_clause))]
            results.append(RequestedResult(intent='latest_maintenance', subjects=[code], source_text=date_clause[:700]))
    has_card = _matches(r'\b(?:карточк\w*|состояни\w*|статус\w*|место\s+установки|наименован\w*)\b', clean)
    if not has_card:
        results = [result for result in results if result.intent not in ('equipment_details', 'equipment_exists')]
    if 1 <= len(results) <= 12:
        return interpretation.model_copy(update={'results': results})
    return interpretation


def preserve_requested_source(interpretation, question):
    """An external schedule request cannot be answered with an internal calculation."""
    clean = QUOTED.sub(' ', question)
    external = EXTERNAL_CALENDAR.search(clean)
    if not external:
        return interpretation
    results = [result for result in interpretation.results if result.intent != 'maintenance_calendar'
               or result.source_text and result.source_text in question and
               _matches(r'\b(?:внутренн\w*|сохран[её]нн\w*|утвержд[её]нн\w*)\s+(?:регламент|календар)\w*', result.source_text)]
    if not any(result.intent == 'other' and result.source_text and external[0] in result.source_text for result in results):
        results.append(RequestedResult(intent='other', source_text=external[0]))
    return interpretation.model_copy(update={'results': results[:12]})


def bind_discussion_and_projections(interpretation, question, *, role):
    """Bind commentary to saved facts and keep distinct field projections."""
    clean = QUOTED.sub(' ', question)
    task_ids = list(dict.fromkeys(re.findall(r'\b' + UUID + r'\b', clean, re.I)))
    asset_codes = asset_references(clean)
    results = []
    for result in interpretation.results:
        source = result.source_text if result.source_text and result.source_text in question else ''
        intent = result.intent
        if intent == 'general_explanation' and (asset_references(source) or _matches(UUID, source) or _matches(
                r'\bчто\s+известно\b|\bпо\s+(?:прочитанн\w*|сохран[её]нн\w*|полученн\w*)\s+данн\w*', source)):
            intent = 'explain_results'
        if intent in ('general_explanation', 'other') and _matches(
                r'\b(?:предлож\w*|вариант\w*)\b', source) and _matches(r'\bдля\s+обсуждения\b', source):
            intent = 'recommend_actions'
        if intent == 'equipment_tasks' and len(task_ids) == 1 and not asset_codes and _matches(TASK_WORD, clean):
            result = result.model_copy(update={'subjects': task_ids, 'period': None})
            intent = 'task_details'
        if intent == 'maintenance_calendar' and role == 'executor' and not asset_codes and not task_ids and _matches(
                r'\bмо[ийх]\s+(?:занят|работ|задан|наряд)\w*\b', clean) and not _matches(r'\bкалендар\w*\b', clean):
            intent = 'task_list'
        if intent == 'other' and source and not mutation_command_requested(clean):
            references = re.findall(r'\b' + UUID + r'\b', source, re.I)
            if len(references) == 1 and _matches(TASK_WORD, source) and any(
                    _matches(FIELD_PATTERNS[field], source) for field in FIELD_GROUPS['task_details']):
                result = result.model_copy(update={'subjects': references})
                intent = 'task_details'
        options = {'intent': intent}
        if intent in ('explain_results', 'recommend_actions') and len(task_ids) == 1 and not asset_codes:
            options['subjects'] = task_ids
            if intent == 'recommend_actions' and not result.recommendation_count and _matches(r'\bдля\s+обсуждения\b', source):
                options['recommendation_count'] = 2
        results.append(result.model_copy(update=options))
    return interpretation.model_copy(update={'results': results})


def _metadata(result, question, clock, current_files, subject=None):
    intent = result.intent
    allowed_fields = FIELD_GROUPS.get(intent, ())
    source_text = result.source_text if result.source_text and result.source_text in question else None
    field_request = (source_text if source_text and intent in EQUIPMENT_ANALYSIS else
                     _projection_text(question, intent, subject))
    positive_fields = positive_text(field_request)
    explicit_fields = [field for field in allowed_fields if _matches(FIELD_PATTERNS[field], positive_fields)]
    if intent == 'self_profile' and _matches(r'\b(?:здани\w*|объект\w*)\b', positive_fields):
        explicit_fields = list(dict.fromkeys((*explicit_fields, 'site')))
        if not _matches(r'\b(?:фио|им[яе]\w*|фамили\w*)\b', positive_fields):
            explicit_fields = [field for field in explicit_fields if field != 'name']
    exclusive = re.search(r'\b(?:только|исключительно)\s+([^.!?;]+)', positive_fields, re.I)
    if exclusive:
        only_fields = [field for field in allowed_fields if _matches(FIELD_PATTERNS[field], exclusive[1])]
        if only_fields:
            explicit_fields = only_fields
    if intent == 'self_profile' and _matches(r'\bздани\w*\b', positive_fields) and not _matches(r'\b(?:фио|им[яе]\w*|фамили\w*)\b', positive_fields):
        explicit_fields = list(dict.fromkeys([field for field in explicit_fields if field != 'name'] + ['site']))
    if intent == 'task_list' and _matches(r'^\s*(?:дай|выведи|перечисли|покажи)\w*\s+(?:только\s+)?названи\w*|достаточно\s+назван', positive_fields):
        explicit_fields = ['name']
    elif (intent == 'task_list' and explicit_fields and not exclusive
          and _matches(r'\b(?:наряд\w*|задан\w*|заняти\w*|работ\w*)\s+(?:по\s+\S+\s+)?с\s+', positive_fields)):
        explicit_fields = list(dict.fromkeys(['name', *explicit_fields]))
    if intent == 'equipment_details' and _matches(r'(?:назови\w*|укажи\w*)\s+(?:само\s+)?оборудовани\w*', field_request):
        explicit_fields = list(dict.fromkeys(('name', *explicit_fields)))
    fields = [field for field in result.fields if field in allowed_fields]
    if explicit_fields or intent == 'task_list':
        fields = explicit_fields
    meta = {'intent': intent, 'fields': list(dict.fromkeys(fields or DEFAULT_FIELDS.get(intent, ())))}
    blocked_fields = set()
    if allowed_fields:
        excluded = re.findall(r'\b(?:без|не\s+(?:путай\s+с|показывай|выводи|добавляй))\s+([^.!?;\n]+)',
                              QUOTED.sub(' ', question), re.I)
        if excluded:
            exclusion = ' '.join(excluded)
            blocked_fields = {field for field in allowed_fields if _matches(FIELD_PATTERNS[field], exclusion)}
            if _matches(r'\bдат\w*\b', exclusion):
                blocked_fields.update(('start', 'deadline', 'closed'))
    if source_text:
        meta['source_text'] = source_text
    if intent == 'general_explanation' and not source_text:
        meta['block'] = 'Уточните, какой инженерный вопрос нужно пояснить.'
    if intent == 'recommend_actions':
        meta['recommendation_count'] = result.recommendation_count or 3
    if intent in EQUIPMENT_ANALYSIS:
        meta['local_date'] = clock['local_date']
    if intent in ('equipment_tasks', 'latest_maintenance', 'maintenance_calendar'):
        try:
            dates = selectors(source_text or question, clock, equipment_scoped=True)
            meta['query'] = {key: dates[key] for key in ('starts_on', 'ends_on') if key in dates}
        except ValueError as exc:
            meta['block'] = str(exc)
        if intent == 'equipment_tasks':
            meta.update(period=result.period or 'all', full=True)
            if not source_text or not exclusive:
                meta['fields'] = list(dict.fromkeys(['name', *meta['fields'], 'deadline']))
        elif intent == 'latest_maintenance':
            meta['query'] = {**meta.get('query', {}), 'latest_only': True}
        elif not meta.get('query'):
            local_day = date.fromisoformat(clock['local_date'])
            meta['query'] = dict(starts_on=local_day.isoformat(), ends_on=(local_day + timedelta(days=366)).isoformat())
        if intent == 'maintenance_calendar':
            meta['calendar_view'] = ('next' if _matches(r'\b(?:следующ|ближайш)\w*\b', source_text or question)
                                     else 'period')
    if intent in ('task_list', 'assign_task'):
        meta['period'] = ('overdue' if _matches(r'\bпросроч\w*\b', question) else
                          'upcoming' if _matches(r'\b(?:предстоящ|ближайш|будущ)\w*\b', question) else
                          result.period or 'upcoming')
    if intent == 'task_list':
        numbers = ('один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять', 'десять')
        limit = re.search(r'\bпервые\s+(\d+|' + '|'.join(numbers) + r')\b|\b(\d+|' + '|'.join(numbers) + r')\s+первых\b', question, re.I)
        if limit:
            amount = next(group for group in limit.groups() if group).casefold()
            meta['limit'] = int(amount) if amount.isdecimal() else numbers.index(amount) + 1
        meta['full'] = not limit and _matches(r'\bвсе[хм]?\b', question)
        meta['scheduled_only'] = meta['period'] == 'upcoming' and _matches(r'\b(?:запланированн\w*\s+|планов\w*\s+)(?:работ|наряд|задан)\w*\b', positive_fields)
    if intent in ('task_count', 'maintenance_history'):
        try:
            meta['query'] = selectors(source_text or question, clock, equipment_scoped=intent == 'maintenance_history')
        except ValueError as exc:
            meta['block'] = str(exc)
        if intent == 'task_count' and _matches(r'\b(?:вручную|ручн\w*)\b', question):
            meta.setdefault('query', {})['origin'] = 'manual'
        if intent == 'task_count' and not _matches(r'незаверш|незакрыт|не\s+заверш|открыт\w*|в\s+работе|ожида', question):
            if _matches(r'\b(?:заверш[её]н|выполнен|принят)\w*\b', question):
                meta['counter'] = 'completed'
            else:
                meta['counter'] = 'all_tasks'
            if meta.get('query'):
                meta.setdefault('block', 'Такой отбор не подтверждён полным счётчиком. Уточните состояние или период.')
        if intent == 'maintenance_history' and not {'starts_on', 'ends_on'} <= meta.get('query', {}).keys():
            meta.setdefault('block', 'Укажите даты начала и конца периода фактического обслуживания.')
        if intent == 'task_count' and not meta.get('query') and _matches(r'\b(?:ближайш|предстоящ|будущ)\w*\b', positive_fields):
            meta['list_period'] = 'upcoming'
            meta['scheduled_only'] = _matches(r'\bзапланирован\w*\b|\bнезапланирован\w*\b', positive_fields)
    if intent == 'workbook_row':
        files = [file for file in current_files if file['mime_type'] ==
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
        named = [file for file in files if _literal(question, file.get('original_name'))]
        if named:
            files = named
        sheet = result.sheet if _literal(question, result.sheet) else None
        sheet_match = re.search(r'\bлист\w*\s+(?:«([^»\n]+)»|"([^"\n]+)")', question, re.I)
        if sheet_match:
            sheet = sheet_match[1] or sheet_match[2]
        elif sheet is None:
            bare_sheet = re.search(r'\b(?i:лист(?:е|а|у|ом)?)\s+([А-ЯЁA-Z][\w-]*)', question)
            if bare_sheet:
                sheet = bare_sheet[1]
        row_match = re.search(r'(?:\bстрок\w*\s*(?:№\s*)?(\d+)|(\d+)(?:\s*[-–]\s*\w{1,3})?\s+строк\w*)', question, re.I)
        ordinals = ('перв', 'втор', 'трет', 'четв[её]рт', 'пят', 'шест', 'седьм', 'восьм', 'девят', 'десят')
        ordinal = next((index for index, stem in enumerate(ordinals, 1)
                        if _matches(r'\b' + stem + r'\w*\s+строк\w*', question)), None)
        row = int(next(group for group in row_match.groups() if group)) if row_match else ordinal
        explicit_cell = re.search(r'\b(?:ячейк\w*|cell)\s+([A-Z]{1,3})([1-9]\d*)\b', question, re.I)
        projection = positive_text(question)
        columns = [column for column in result.columns if _literal(projection, column)]
        if explicit_cell:
            columns, row = [explicit_cell[1].upper()], int(explicit_cell[2])
        mode = ('headers' if _matches(r'\b(?:заголовк\w*\s+столбц\w*|названи\w*\s+столбц\w*|заголовки)\b', projection) else
                'sheets' if _matches(SHEET_LIST, projection) else
                'structure' if _matches(r'\bструктур\w*\s+лист\w*', projection) else 'row')
        if not files:
            meta['block'] = ('Формат вложения не поддерживается для чтения Excel. Прикрепите файл XLSX.'
                             if current_files else 'Для чтения нужен файл XLSX. Прикрепите книгу к сообщению.')
        elif len(files) > 1:
            meta['block'] = 'Укажите одну из прикреплённых книг XLSX.'
        elif (mode == 'row' and not row) or (row is not None and not 1 <= row <= 1048576):
            meta['block'] = 'Укажите номер строки Excel или адрес ячейки.'
        else:
            meta.update(attachment_id=str(files[0]['attachment_id']), row=row, columns=columns, sheet=sheet,
                        workbook_mode=mode, whole_row=_matches(r'\b(?:всю|целую|полную)\s+строку\b', projection))
    if intent == 'edit_equipment':
        changes, incomplete = equipment_changes(question)
        if changes and not incomplete:
            meta['changes'] = changes
        else:
            meta['block'] = 'Уточните все поля, точные значения и одну карточку оборудования для изменения.'
    if intent in ('rename_equipment', 'move_equipment'):
        values = [match[1] or match[2] for match in QUOTED.finditer(question)]
        if result.value in values:
            meta['changes'] = {'name' if intent == 'rename_equipment' else 'location': result.value}
        elif len(values) == 1:
            meta['changes'] = {'name' if intent == 'rename_equipment' else 'location': values[0]}
        else:
            meta['block'] = 'Укажите точное новое значение в кавычках.'
        if intent == 'move_equipment' and not _matches(FIELD_PATTERNS['location'], question):
            meta['block'] = 'Уточните, какое поле оборудования требуется изменить.'
        if intent == 'rename_equipment' and not _matches(r'переимен|названи|наименован|\brename\b', QUOTED.sub(' ', question)):
            meta['block'] = 'Подтвердите, что нужно изменить именно название оборудования.'
    if intent == 'cancel_task':
        reason = _reason(question, subject)
        if reason:
            meta['changes'] = {'reason': reason}
        else:
            meta['block'] = 'Укажите причину отмены задания.'
    if intent == 'read_notifications' and not _matches(r'\b(?:все|all)\b', QUOTED.sub(' ', question)):
        meta['block'] = 'Уточните, нужно ли отметить все ваши уведомления прочитанными.'
    if intent == 'assign_task':
        meta['one_worker'] = _matches(r'\b(?:одного|одному|один|единственного|ровно\s+1|1)\s+(?:человек\w*|исполнител\w*|работник\w*|сотрудник\w*)', question)
        if re.search(r'\b(?:исполнител[ья]|работник[а]?|сотрудник[а]?)\s+[А-ЯЁ][а-яё]{2,}\b', question) or len(re.findall(r'\b'+UUID+r'\b', question, re.I)) > 1:
            meta['block'] = 'Для назначения с конкретным составом уточните задание и рабочие идентификаторы исполнителей.'
    if intent in CHANGES and not authorizes_operation(intent, question):
        meta['block'] = 'Уточните, какое изменение нужно подготовить.'
    if intent in CHANGES and intent != 'assign_task' and _matches(r'\b(?:если|при условии|only if)\b', QUOTED.sub(' ', question)):
        meta['block'] = 'Условие изменения не подтверждено. Уточните, нужно ли готовить карточку после проверки.'
    if intent in CHANGES and explicit_revision(QUOTED.sub(' ', question)):
        revisions = re.findall(r'\b(?:expected_revision|revision|ревизи\w*|верси\w*)\s*[:=№]?\s*(\d+)\b',
                               QUOTED.sub(' ', question), flags=re.I)
        if len(revisions) == 1 and int(revisions[0]) > 0:
            meta['expected_revision'] = int(revisions[0])
        else:
            meta['block'] = 'Укажите одну положительную ревизию для изменения.'
    meta['fields'] = [field for field in meta['fields'] if field not in blocked_fields]
    return meta


def compile_plan(interpreted, question, tools, clock, current_files, *, preserve_unknown=False):
    """Compile typed user results to fixed existing transports; decline unsupported requests."""
    results = list(interpreted.results)
    clean = QUOTED.sub(' ', question)
    if preserve_unknown:
        recommendations = {result.source_text for result in results if result.intent == 'recommend_actions' and result.source_text}
        results = [result for result in results if not (result.intent == 'general_explanation' and result.source_text in recommendations)]
        # An unfinished-task lookup and an overdue lookup have different
        # predicates. Preserve the explicitly requested cohorts even when a
        # model compressed them to one default task list.
        cohort_match = re.search(r'\bнезаверш[её]нн\w*\s+(?:или|и)\s+просроченн\w*\s+(?:задани|наряд|работ)\w*', clean, re.I)
        equipment_lists = [result for result in results if result.intent == 'equipment_tasks']
        if cohort_match and equipment_lists:
            for result in equipment_lists:
                if not any(other.subjects == result.subjects and other.period == 'overdue' for other in equipment_lists):
                    results.append(result.model_copy(update={'period': 'overdue', 'source_text': cohort_match[0]}))
                if not any(other.subjects == result.subjects and other.period in (None, 'all') for other in equipment_lists):
                    results.append(result.model_copy(update={'period': 'all', 'source_text': cohort_match[0]}))
    explicit_ids = list(dict.fromkeys(value.lower() for value in re.findall(r'\b' + UUID + r'\b', clean, re.I)))
    asset_codes = asset_references(clean)
    if (len(results) == 1 and results[0].intent == 'other' and len(asset_codes) == 1
            and _matches(r'\b(?:сохран[её]нн\w*|утвержд[её]нн\w*)\s+регламент\w*\b', clean)
            and not mutation_command_requested(clean)):
        results = [RequestedResult(intent='service_frequency', subjects=asset_codes)]
    if len(results) == 1 and results[0].intent == 'other' and not mutation_command_requested(clean):
        workbook = _matches(r'\bxlsx\b|\bexcel\b|\bлист\w*\b', clean)
        selection = _matches(r'\b(?:строк|ячейк|столбц|заголов|структур)\w*|' + SHEET_LIST, clean)
        if workbook and selection:
            results = [results[0].model_copy(update={'intent': 'workbook_row'})]
    has_write = any(result.intent in CHANGES and authorizes_operation(result.intent, question) for result in results)
    if not has_write and not mutation_command_requested(clean):
        personal = _matches(r'\b(?:авторизован\w*|активн\w*\s+сеанс\w*)|\b(?:мо[йяеию]|мо[её]м|моего|моему|свой|сво[её]м)\s+(?:\w+\s+)?(?:аккаунт|профил|рол|фио|email|почт|электронн\w*\s+адрес)\w*', clean)
        if personal:
            results = [result.model_copy(update={'intent': 'self_profile', 'subjects': []})
                       if result.intent == 'staff_details' and not result.subjects else result for result in results]
            if not any(result.intent == 'self_profile' for result in results):
                results = [result for result in results if result.intent != 'other'] + [RequestedResult(intent='self_profile')]
        if explicit_ids and not _matches(EQUIPMENT_WORD, clean):
            task_fields = any(_matches(FIELD_PATTERNS[field], clean) for field in ('start', 'deadline', 'crew_size', 'closed', 'checklist'))
            as_task = _matches(TASK_WORD, clean) or task_fields
            if as_task:
                converted = []
                for result in results:
                    refs = [value for value in result.subjects if value.lower() in explicit_ids]
                    task_card_fields = refs and any(
                        any(_matches(FIELD_PATTERNS[field], _projection_text(question, 'task_details', ref))
                            for field in FIELD_GROUPS['task_details']) for ref in refs
                    )
                    wrong_route = result.intent in CHANGES or result.intent == 'maintenance_history'
                    staff_field = result.intent == 'staff_details' and result.source_text and any(
                        _matches(FIELD_PATTERNS[field], result.source_text) for field in ('role','email'))
                    if result.intent in ('task_list', 'task_details') or (
                        result.intent in ('equipment_details', 'equipment_exists', 'service_frequency', 'maintenance_calendar', 'staff_details', 'other')
                        and (refs or (not asset_codes and not any(value.intent == 'self_profile' for value in results)
                                      and (result.intent != 'staff_details' or not result.subjects and not staff_field)))
                    ) or wrong_route and (task_card_fields or (
                        task_fields and len(explicit_ids) == 1 and result.intent in CHANGES and
                        not authorizes_operation(result.intent, question)
                    )):
                        converted.append(result.model_copy(update={'intent': 'task_details', 'subjects': refs or explicit_ids}))
                    else:
                        converted.append(result)
                results = converted
        if asset_codes and not explicit_ids:
            presence = _matches(r'\b(?:существует\s+ли|есть\s+ли|наличи\w*)\b', clean)
            scopes = ('task_details', 'equipment_exists', 'equipment_details', 'service_frequency', 'other', 'staff_details')
            equipment_fields = any(_matches(FIELD_PATTERNS[field], positive_text(clean)) for field in ('name', 'location', 'state', 'revision', 'code'))
            dedicated = (all(result.intent in scopes and (not result.subjects or
                         set(value.casefold() for value in result.subjects) <= {code.casefold() for code in asset_codes})
                         for result in results) and not _matches(r'\b(?:и\s+ещ[её]|затем|почт\w*|парол\w*|уведомлен\w*|регламент\w*|истори\w*)\b', clean))
            if dedicated and (presence or equipment_fields):
                chosen = 'equipment_details' if equipment_fields else 'equipment_exists'
                prior = next((result for result in results if result.intent == chosen), results[0])
                results = [prior.model_copy(update={'intent': chosen, 'subjects': asset_codes})]
    changes, incomplete = equipment_changes(question)
    if (len(changes) > 1 or incomplete) and any(result.intent in ('rename_equipment', 'move_equipment') for result in results):
        subjects = list(dict.fromkeys(subject for result in results if result.intent in ('rename_equipment', 'move_equipment')
                                     for subject in _subjects(result, question)))
        results = [result for result in results if result.intent not in ('rename_equipment', 'move_equipment')]
        results.append(RequestedResult(intent='edit_equipment', subjects=subjects))
    if len(results) == 1 and results[0].intent in ('other', 'maintenance_history', 'equipment_details'):
        # The two typed facts below disambiguate recorded work from forecasts or a card.
        dated = len(re.findall(r'\b\d{4}-\d{2}-\d{2}\b', question)) == 2
        history = _matches(r'фактическ\w*\s+(?:дат\w*|выполн\w*)|истори\w*\s+то|приняты\w*\s+отч[её]т\w*', question)
        if dated and history and not mutation_requested(question):
            results = [results[0].model_copy(update={'intent': 'maintenance_history'})]
    if _matches(r'\bпаспорт\w*\b', clean) or _matches(r'производител\w*|изготовител\w*|manufacturer', clean) and _matches(r'цитат\w*|дословн\w*|инструкци\w*|recommend', clean):
        results = [result for result in results if result.intent not in ('service_frequency', 'maintenance_history')
                   or result.source_text and not _matches(r'паспорт|производител|изготовител|manufacturer', result.source_text)]
        if len(results) == 1 and results[0].intent == 'other' and not mutation_requested(question):
            results = []
        if not any(result.intent == 'manufacturer_source' for result in results):
            results = [*results, RequestedResult(intent='manufacturer_source')]
    results = [result for result in results if result.intent != 'password' or _matches(SECRET_WORD, clean)]
    if any(result.intent == 'other' for result in results) and (
            not preserve_unknown or all(result.intent == 'other' for result in results) and not EXTERNAL_CALENDAR.search(clean)):
        return None
    if _matches(SECRET_WORD, clean) and not any(result.intent in ('password', 'quoted_command') for result in results):
        results = [*results, RequestedResult(intent='password')]
    if results and all(result.intent == 'task_details' for result in results) and len(explicit_ids) > 1:
        if len(results) == 1 or all(result.fields == results[0].fields for result in results):
            results = [results[0].model_copy(update={'subjects': explicit_ids})]
    requested_read = _matches(r'\b(?:покажи|назови|укажи|сообщи|прочитай|найди|проверь|скажи|выведи|где|find|show|read)\b',
                              QUOTED.sub(' ', question))
    write_equipment = {subject.casefold() for result in results
                       if result.intent in ('rename_equipment', 'move_equipment', 'edit_equipment') and authorizes_operation(result.intent, question)
                       for subject in _subjects(result, question)}
    goals, metadata = [], {}
    seen = {}
    for result in sorted(results, key=lambda result: {'explain_results': 1, 'recommend_actions': 2}.get(result.intent, 0)):
        if result.intent == 'equipment_exists' and (
            not _matches(r'\b(?:существует\s+ли|есть\s+ли|наличи\w*)\b', clean) and (
                result.fields or _matches(r'\b(?:назови|укажи|сообщи|выведи)\w*\s+(?:только\s+)?(?:названи\w*|наименован\w*|мест[оае]\s+установк\w*)', question))
        ):
            result = result.model_copy(update={'intent': 'equipment_details'})
        intent = result.intent
        if preserve_unknown and intent == 'task_list' and result.subjects and _subjects(
                result.model_copy(update={'intent': 'equipment_tasks'}), question):
            intent = 'equipment_tasks'
            result = result.model_copy(update={'intent': intent})
        if intent == 'task_details' and not _matches(r'задан\w*|наряд\w*|\b' + UUID + r'\b', question) and len(results) > 1:
            continue
        subjects = _subjects(result, question)
        for subject in subjects or [None]:
            if (intent in ('equipment_details', 'equipment_exists') and not requested_read
                    and subject and subject.casefold() in write_equipment):
                continue
            name, title = ROUTES.get(intent, ('', 'Ограничение источника'))
            if intent == 'equipment_exists' and subject and re.fullmatch(UUID, subject, re.I):
                name = 'equipment_read'
            meta = {**_metadata(result, question, clock, current_files, subject), 'subject': subject}
            if meta.get('block'):
                meta['disposition'] = 'missing_input'
            if intent == 'task_count' and meta.get('list_period'):
                name = 'tasks_find'
            dedupe = (intent, (subject or '').casefold(), meta.get('period'),
                      tuple(sorted(meta.get('query', {}).items())), meta.get('sheet'), meta.get('row'),
                      tuple(meta.get('columns', ())),
                      meta.get('source_text') if intent in DISCUSSION | {'other'} else None)
            if dedupe in seen:
                previous = metadata[seen[dedupe]]
                previous['fields'] = list(dict.fromkeys([*previous['fields'], *meta['fields']]))
                continue
            if intent == 'manufacturer_source':
                meta['block'] = 'Проверенной инструкции или паспорта производителя в доступных источниках нет. Прикрепите документ, чтобы проверить цитату и версию.'
                meta['disposition'] = 'unsupported'
            elif intent == 'password':
                meta['block'] = 'Текущий пароль и другие защищённые данные недоступны для просмотра. Помощник не может их сообщить.'
                meta['disposition'] = 'forbidden'
            elif intent == 'quoted_command':
                quoted = result.value
                if quoted and _literal(question, quoted):
                    text = re.sub(r'^(?:отмени(?:те)?|спиши(?:те)?)\b', lambda match:
                                  'Отменить задание' if match[0].casefold().startswith('отмен') else 'Списать', quoted, flags=re.I)
                    meta['block'] = 'В цитате сформулировано поручение: ' + text + '.'
                else:
                    meta['block'] = 'Укажите текст, смысл которого нужно объяснить.'
            elif intent == 'other':
                meta['block'] = ('Подключённого источника внешнего расписания нет.'
                                 if EXTERNAL_CALENDAR.search(meta.get('source_text', '')) else
                                 'Для этого требования нужен доступный источник или уточнение операции.')
                meta['disposition'] = 'unsupported'
            elif intent not in DISCUSSION and name not in tools:
                meta['block'] = 'Эта операция недоступна вашей текущей роли.'
                meta['disposition'] = 'forbidden'
            elif intent in TASK_REFS and not subject and not (intent == 'assign_task' and meta.get('period') == 'upcoming'
                    and _matches(r'\bближайш\w*\b', question)):
                meta['block'] = 'Укажите конкретное задание, например его ID из списка работ.'
            elif intent in EQUIPMENT_REFS | {'staff_details'} and not subject:
                meta['block'] = 'Уточните название, код или ID нужной записи.'
            if intent in CHANGES and not meta.get('block') and subject and len(subjects) > 1:
                meta['block'] = 'Для изменения укажите один однозначно выбранный объект.'
            if intent in CHANGES and (interpreted.read_only or prohibits_changes(clean)):
                meta['block'] = 'Пользователь ограничил поручение чтением.'
                meta['disposition'] = 'forbidden'
            if meta.get('block'):
                meta.setdefault('disposition', 'missing_input')
            gid = 'intent-' + str(len(goals) + 1)
            seen[dedupe] = gid
            selector = GoalSelector(task_id=subject) if subject and intent in TASK_REFS else GoalSelector()
            if subject and intent in EQUIPMENT_REFS:
                selector = (GoalSelector(equipment_id=subject) if re.fullmatch(UUID, subject, re.I) else
                            GoalSelector(equipment_code=subject) if re.fullmatch(ASSET, subject, re.I) else GoalSelector())
            for key in ('starts_on', 'ends_on'):
                if key in meta.get('query', {}) and intent in EQUIPMENT_REFS:
                    setattr(selector, key, date.fromisoformat(meta['query'][key]))
            title = title + (' · ' + subject[:160] if subject else '')
            if intent == 'equipment_tasks':
                title = ('Просроченные задания оборудования' if meta['period'] == 'overdue' else
                         'Незавершённые задания оборудования') + (' · ' + subject[:160] if subject else '')
            elif intent == 'other' and meta.get('source_text'):
                title = meta['source_text'][:400]
            goals.append(GoalSpec(id=gid, title=title,
                                  tool='' if meta.get('block') else name, selector=selector,
                                  kind='unavailable' if meta.get('block') else 'change' if intent in CHANGES else
                                  'conversation' if intent in DISCUSSION else 'read',
                                  required_evidence='manufacturer_document' if intent == 'manufacturer_source' else None))
            metadata[gid] = meta
    if not goals or len(goals) > 12:
        return None
    return ToolSelection(tools=[], goals=goals), metadata
