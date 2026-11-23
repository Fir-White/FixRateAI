"""Interpret the current message before creating business workflow state."""
from typing import Literal
import re

from pydantic import Field

from app.schemas.assistant import Input

from .semantic_plan import FIELD_PATTERNS, QUOTED, UUID, asset_references, equipment_report_fields
from .intents import primary_document_requested


Kind = Literal['conversation', 'system_question', 'data_query', 'single_action',
               'multi_step_task', 'unsupported_request', 'clarification']
Unavailable = Literal['repository', 'shell', 'unattached_files', 'internet',
                      'external_message', 'other']
MaintenanceIntent = Literal['other', 'types', 'operations', 'upcoming', 'overdue', 'assignees', 'recommendation', 'reason']


class DialogueRoute(Input):
    kind: Kind
    explain: bool = False
    previous_workflow: bool = False
    depends_on_object_data: bool = False
    maintenance_intent: MaintenanceIntent = 'other'
    unavailable: list[Unavailable] = Field(default_factory=list, max_length=6)


WORK_KINDS = {'data_query', 'single_action', 'multi_step_task'}
SOURCE_NEEDED = ('Пока не удалось подтвердить ответ данными текущего объекта. '
                 'Если нужен конкретный наряд, регламент или период, укажите его название или дату.')
DOMAIN = (r'\b(?:то|техобслуживани\w*|обслуживани\w*|регламент\w*|наряд\w*|задани\w*|'
          r'оборудовани\w*|просроч\w*|исполнител\w*|сотрудник\w*|смен\w*|отч[её]т\w*|календар\w*)\b')
OBJECT = (r'\b(?:у\s+(?:нас|меня)|(?:на|по|для|у)\s+(?:(?:текущ\w*|выбранн\w*|наш\w*|этом|эту|этого)\s+)?объект\w*|'
          r'в\s+(?:наш\w*\s+)?(?:реестр\w*|календар\w*|системе)|по\s+данным\s+(?:систем\w*|fixrate|реестр\w*|объект\w*)|'
          r'мо[ийяею]\s+(?:наряд\w*|задани\w*|смен\w*|отч[её]т\w*))\b')
FOLLOW_UP = (r'^\s*(?:а\s+)?(?:конкретнее|подробнее|поподробнее|детальнее|покажи\s+вс[её]|все\s+по\s+пунктам|'
             r'кто\s+(?:их|это|из\s+них)|какие\s+(?:из\s+них|просроч\w*)|кого\s+лучше|почему\s+именно)\b')


def object_data_requested(question, history=()):
    """Identify claims that require the current principal's persisted records."""
    source = QUOTED.sub(' ', question)
    if re.match(r'^\s*(?:как\s+(?:найти|открыть|посмотреть|узнать)\b|что\s+такое\b|'
                r'(?:переведи|перефразируй|разбери)\s+(?:эту\s+)?(?:цитат\w*|фраз\w*|текст\w*))', source, re.I):
        return False
    if asks_saved_facts(question) or re.search(OBJECT, source, re.I) and re.search(DOMAIN, source, re.I):
        return True
    if re.search(r'\b(?:какие|какой|кто|когда|найди|покажи|проверь|выбери|подбери)\b', source, re.I) and re.search(
            r'\b(?:ближайш\w*|просроч\w*|запланирован\w*|действующ\w*|сегодня|завтра|текущ\w*)\b', source, re.I):
        if re.search(DOMAIN, source, re.I):
            return True
    if history and re.search(FOLLOW_UP, source, re.I):
        previous = history[0]
        state = previous.get('workflow') or {}
        route = state.get('dialogue_route') or {}
        return (route.get('kind') in WORK_KINDS or bool(state.get('object_data_request')) or
                bool(state.get('maintenance_dialogue')) or object_data_requested(previous['content']))
    return False


def unauthorised_site_claim(answer):
    """A response-only model cannot assert what is saved on the selected object."""
    for part in re.split(r'[.!?\n]+', QUOTED.sub(' ', answer)):
        if re.search(OBJECT, part, re.I) and re.search(DOMAIN, part, re.I) and re.search(
                r'\b(?:указан\w*|зарегистрирован\w*|сохранен\w*|найден\w*|запланирован\w*|провод\w*|'
                r'выполня\w*|числ\w*|назначен\w*|подтвержд[её]н\w*|отсутству\w*|нет|имеются|есть)\b', part, re.I):
            if not re.search(r'\b(?:если|допустим|например|проверить|посмотреть|откройте|можно)\b', part, re.I):
                return True
    return False


def planning_history(question, history):
    """Expose prior requests and verified selectors, never past prose as evidence."""
    from .service import needs_history

    if not history or not (needs_history(question) or re.search(FOLLOW_UP, question, re.I)):
        return []
    prior = []
    for row in reversed(history[:4]):
        state = row.get('workflow') or {}
        sources = [dict(tool=item['tool'], entity=item.get('entity', {}), period=item.get('period', {}))
                   for item in state.get('evidence', []) if item.get('complete') and item.get('retained')
                   and item.get('status') in ('FOUND', 'EMPTY')]
        prior.append(dict(request=row['content'][:1000], prior_verified_refs=sources[:8],
                          subject=saved_subject(state)))
    return prior


def saved_subject(workflow):
    context = workflow.get('maintenance_dialogue') or {}
    return {key: context[key] for key in ('kind', 'type_keys', 'type_codes', 'resolved_types', 'period', 'days', 'task_id')
            if key in context and context[key]}

LIMITS = {
    'repository': 'У меня нет доступа к Git и исходникам репозитория.',
    'shell': 'Из этого чата нельзя запускать команды и тесты.',
    'unattached_files': 'Я не могу открыть файлы с вашего устройства. Вставьте текст в сообщение или приложите файл поддерживаемого формата.',
    'internet': 'В этом чате нет доступа к произвольным сайтам.',
    'external_message': 'Я могу составить текст для вас. Отправка сообщений во внешние сервисы из этого чата недоступна.',
    'other': 'Для этой части запроса в чате нет доступного действия или источника.',
}
CAPABILITY_TERMS = {
    'repository': r'\b(?:git|diff|commit|репозитор\w*|исходн\w*\s+код\w*)\b',
    'shell': r'\b(?:тест\w*|pytest|терминал\w*|команд\w*|shell|npm|ci)\b',
    'unattached_files': r'\b(?:файл\w*|рабоч\w*\s+стол\w*|диск\w*|компьютер\w*)\b',
    'internet': r'\b(?:сайт\w*|интернет\w*|погугл\w*|https?|web|website)\b',
    'external_message': r'\b(?:отправь\w*|перешли\w*|разошли\w*|доставь\w*|send)\b',
}


def grounded_limits(route, question):
    source = QUOTED.sub(' ', question)
    missing = [item for item in route.unavailable
               if item in CAPABILITY_TERMS and re.search(CAPABILITY_TERMS[item], source, re.I)]
    return route.model_copy(update={'unavailable': missing})


def asks_about_previous(question, history):
    """A past-tense question attached to a saved plan is a status explanation."""
    from .intents import mutation_command_requested
    from .task_execution import SUBMIT

    source = QUOTED.sub(' ', question)
    clauses = re.split(r'[.!?;]\s*|\s+и\s+', source)
    if not any(row.get('workflow') for row in history) or any(
        mutation_command_requested(clause) or re.match(SUBMIT, clause.lstrip(), re.I) for clause in clauses
    ):
        return False
    return bool(re.search(r'\b(?:почему|из-за чего)\b.{0,90}\b(?:остановил\w*|'
                          r'не\s+(?:отправил\w*|выполнил\w*|завершил\w*|продолжил\w*))\b', source, re.I | re.S))


def saved_task_explanation(history):
    from .task_execution import message_for

    previous = next((row['workflow'] for row in history if row.get('workflow')), None)
    if not previous or not previous.get('task_execution'):
        return None
    goal = next((goal for goal in previous['goals'] if goal['status'] != 'completed'), None)
    if not goal:
        return None
    message = message_for(goal)
    if goal['status'] == 'awaiting_confirmation' and goal['reason'] == 'human_confirmation_required':
        return (f'Этап «{goal["title"]}» ожидает вашего подтверждения. '
                'Проверьте карточку в предыдущем сообщении. После подтверждения нажмите «Продолжить поручение».')
    return message


def asks_saved_facts(question):
    """Literal selectors and requested persisted fields outweigh a routing guess."""
    unquoted = QUOTED.sub(' ', question)
    if primary_document_requested(question):
        return True
    from .semantic_plan import equipment_references
    if equipment_references(question) and re.search(
            r'\b(?:найди|проверь|открой|покажи)\w*\s+оборудовани\w*|\b(?:названи\w*\s+неоднознач\w*|инвентарн\w*\s+код\w*)\b',
            unquoted, re.I):
        return True
    personal = r'\b(?:мо[йяеию]|сво[йяеию])\s+(?:\w+\s+){0,2}(?:профил\w*|рол[ьиью]\b|задани\w*|наряд\w*|уведомлени\w*|email|электронн\w*\s+адрес)'
    lookup = r'\b(?:посмотри|найди|проверь|покажи|открой|прочитай|назови|сверь|выпиши|какие|сколько)\b'
    has_named_equipment = len(asset_references(unquoted)) == 1
    for portion in re.split(r'[.!?;\n]+|,?\s+и\s+(?=помоги|объясни|предложи|запусти|передай|отправь)', unquoted, flags=re.I):
        if re.search(r'\b(?:как|где)\s+(?:в\s+\S+\s+)?(?:посмотреть|проверить|открыть|найти)\b'
                     r'|\b(?:объясни|разбери|переведи|перескажи|перефразируй)\s+(?:эту\s+)?(?:фраз|цитат|текст|пример|команд)\w*'
                     r'|\bчерновик\s+письм', portion, re.I):
            continue
        if re.search(personal, portion, re.I) and re.search(lookup, portion, re.I):
            return True
        if _asks_for_selected_record(portion):
            return True
        # In a report request the literal equipment often appears in a lead-in
        # before the clause that lists the persisted facts to retrieve.
        if has_named_equipment and equipment_report_fields(portion):
            return True
    return False


def _asks_for_selected_record(portion):
    if not re.search(UUID, portion, re.I) and not asset_references(portion):
        return False
    fields = '|'.join(FIELD_PATTERNS.values())
    return bool(re.search(fields, portion, re.I) or re.search(
        r'\b(?:посмотри|найди|проверь|покажи|открой|прочитай|назови|сверь|уточни|просроч\w*|регламент\w*|периодичност\w*|'
        r'паспорт\w*|инструкци\w*|что\s+известно|как\s+называется)\b', portion, re.I))


def mixed_read_portion(question, route):
    """Remove a trailing prose request or a known external step from tool selection."""
    from .intents import mutation_command_requested

    split = re.compile(r'(?:,\s*|\s+и\s+)(?=(?:помоги\w*\s+(?:написать|составить)|'
                       r'простыми\s+словами|объясни\w*|запусти\w*\s+(?:тест\w*|pytest)))', re.I)
    for match in split.finditer(question):
        if any(quote.start() <= match.start() < quote.end() for quote in QUOTED.finditer(question)):
            continue
        head, tail = question[:match.start()], question[match.end():]
        advice = re.search(r'\b(?:для обсуждения|вариант\w*|письм\w*|сообщени\w*|простыми словами)\b', tail, re.I)
        external = 'shell' in route.unavailable and re.match(r'запусти\w*\s+(?:тест\w*|pytest)', tail, re.I)
        if (not advice and not external) or mutation_command_requested(head) or not asks_saved_facts(head):
            continue
        later = re.split(r'\s*(?:[;.!?]|\bи\s+|\bзатем\s+|\bпосле этого\s+|\bа также\s+)', tail, flags=re.I)[1:]
        if any(mutation_command_requested(part) and not discussion_requested(part) for part in later):
            continue
        if mutation_command_requested(tail) and not external and not re.search(r'\bдля обсуждения\b', tail, re.I):
            continue
        return head
    return None


def discussion_requested(question):
    return bool(re.search(r'\bвариант\w*\b', question, re.I) and re.search(r'\bдля обсуждения\b', question, re.I))


def draft_requested(question):
    return bool(re.search(r'\b(?:напиши\w*|написать|составь\w*|составить|черновик\w*)\b', question, re.I)
                and re.search(r'\b(?:письм\w*|сообщени\w*)\b', question, re.I))


def overdue_verified(facts):
    for item in facts:
        value = item['facts']
        task = value.get('task') if isinstance(value, dict) else None
        if isinstance(task, dict) and task.get('isOverdue') is True:
            return True
    return False


def wants_explanation(route, question):
    source = QUOTED.sub(' ', question)
    return (route.explain or route.kind == 'data_query') and re.search(
        r'\b(?:объясн\w*|простыми\s+словами|почему|расскажи\w*|помоги\w*|резюмиру\w*|вариант\w*|черновик\w*|explain|summari[sz]e|draft)\b',
        source, re.I) and not re.search(
        r'\b(?:не\s+(?:объясняй\w*|комментируй\w*)|без\s+(?:пояснений|комментариев)|'
        r'(?:только|ровно)\s+(?:одн\w*\s+)?(?:числ\w*|цифр\w*))\b',
        source, re.I)


def limitation(route):
    missing = list(dict.fromkeys(route.unavailable or ['other']))
    details = ' '.join(LIMITS[capability] for capability in missing)
    if {'repository', 'shell'}.intersection(missing):
        return details + ' Пришлите diff, фрагмент кода или вывод тестов, и я помогу их разобрать.'
    return details


def history_context(history, *, diagnostic=False):
    messages = []
    for row in reversed(history[:4]):
        message = dict(user=row['content'][:2600], answer=row['answer'][:3800])
        if diagnostic and row.get('workflow'):
            from .task_execution import message_for
            workflow = row['workflow']
            message['workflow'] = dict(outcome=workflow.get('outcome'),
                steps=[dict(title=goal['title'], status=goal['status'], reason=goal.get('reason'),
                            explanation=message_for(goal) if workflow.get('task_execution') else goal.get('message'))
                       for goal in workflow.get('goals', [])])
            if subject := saved_subject(workflow):
                message['subject'] = subject
        messages.append(message)
    return messages


def render_supported_limits(answer, route):
    missing = [item for item in route.unavailable if item != 'other']
    return answer + '\n\n' + limitation(route.model_copy(update={'unavailable': missing})) if missing else answer


def show_plan(state):
    if state.get('task_execution'):
        return True
    goals = [goal for goal in state['goals'] if goal.get('kind') != 'conversation']
    return any(goal.get('workflow_kind') or goal.get('depends_on') for goal in goals) or (
        len(goals) > 1 and sum(goal.get('mode') == 'write' or goal.get('kind') == 'change' for goal in goals) > 0)
