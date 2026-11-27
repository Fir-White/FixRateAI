"""Frozen multi-turn comparisons. Each row describes the whole response expected at that step."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    prompt: str
    source: str
    options: dict


@dataclass(frozen=True)
class Conversation:
    id: str
    role: str
    turns: tuple[Check, ...]


def step(prompt, source, **options):
    return Check(prompt, source, options)


def conversations():
    cases = [Conversation('reported', 'chief_engineer', (
        step('Какое необслуженное оборудование есть?', 'equipment', coverage='none'),
        step('Какое из них ближайшее на завтра?', 'tasks', coverage='none', day='tomorrow', limit=1),
        step('Только одно надо ближайшее', 'tasks', coverage='none', day='tomorrow', limit=1),
    ))]

    def add(identity, role, *turns):
        cases.append(Conversation(identity, role, turns))

    for role in ('chief_engineer', 'engineer', 'director', 'executor'):
        add('count-cohort-' + role, role,
            step('Сколько оборудования, по которому в доступной истории нет принятого ТО?', 'equipment', coverage='none', count=True),
            step('Покажи перечень именно этих единиц.', 'equipment', coverage='none'))
        add('cohort-assigned-' + role, role,
            step('Перечисли оборудование с принятым техническим обслуживанием в реестре.', 'equipment', coverage='present'),
            step('По этой группе найди ровно один самый ранний назначенный наряд на завтра.', 'tasks', coverage='present',
                 day='tomorrow', state='assigned', limit=1))
        add('tomorrow-state-' + role, role,
            step('Покажи ближайший назначенный наряд на завтра. Только один.', 'tasks', day='tomorrow', state='assigned', limit=1),
            step('Теперь ближайший черновик на ту же дату.', 'tasks', day='tomorrow', state='draft', limit=1))
        add('two-dates-' + role, role,
            step('Выведи один ближайший к началу дня запланированный наряд на {next_day}.', 'tasks', day='next_day', limit=1),
            step('А теперь самый ранний на день раньше.', 'tasks', day='tomorrow', limit=1))
        add('catalog-' + role, role,
            step('Какие виды ТО есть на объекте?', 'types'),
            step('Перечисли все операции второго вида из списка.', 'operations', position=2))
        add('date-total-' + role, role,
            step('Сколько назначенных нарядов в плане на завтра?', 'tasks', day='tomorrow', state='assigned', count=True),
            step('Напиши только первый из них.', 'tasks', day='tomorrow', state='assigned', limit=1))
        add('missing-code-' + role, role,
            step('Найди оборудование с точным кодом КС-69.', 'equipment', code='КС-69'),
            step('Проверь похожий КС-61.', 'equipment', code='КС-61'))

    for role, code in [('chief_engineer', 'КС-61'), ('engineer', 'КС-63'), ('director', 'КС-61'),
                       ('executor', 'КС-61'), ('chief_engineer', 'КС-63'), ('engineer', 'КС-61')]:
        add('history-' + role + '-' + code, role,
            step(f'Открой карточку {code}, нужны название и место установки.', 'card', code=code),
            step('Какой у него последний принятый отчёт ТО? Нужен номер отчёта.', 'history', code=code))

    for role, code in [('chief_engineer', 'КС-62'), ('engineer', 'КС-64'), ('director', 'КС-62'), ('executor', 'КС-62')]:
        add('no-history-' + role, role,
            step(f'Найди {code} в реестре оборудования.', 'equipment', code=code),
            step('Есть ли по нему принятый отчёт? Проверь историю приёмки.', 'history', code=code))

    for role, code in [('chief_engineer', 'КС-62'), ('engineer', 'КС-61'), ('director', 'КС-64'), ('executor', 'КС-61')]:
        add('linked-task-' + role, role,
            step(f'Покажи карточку {code}.', 'card', code=code),
            step('Нужен один ближайший назначенный наряд по этому оборудованию на завтра.', 'tasks', code=code,
                 day='tomorrow', state='assigned', limit=1))

    add('role-scope', 'executor', step('Найди КС-66 по его точному коду.', 'equipment', code='КС-66'),
        step('А какой ближайший назначенный наряд по этому оборудованию завтра?', 'tasks', code='КС-66',
             day='tomorrow', state='assigned', limit=1))
    add('draft-next-day', 'director', step('Есть ли черновики нарядов на {next_day}? Сколько?', 'tasks',
        day='next_day', state='draft', count=True), step('А назначенные на эту дату, покажи один.', 'tasks',
        day='next_day', state='assigned', limit=1))
    add('history-change-focus', 'engineer', step('Проверь последний принятый отчёт по КС-61.', 'history', code='КС-61'),
        step('А у КС-63? Укажи UUID отчёта.', 'history', code='КС-63'))
    add('regulation-change-focus', 'chief_engineer', step('Дай действующий регламент КС-61.', 'regulation', code='КС-61'),
        step('Теперь действующий регламент КС-62.', 'regulation', code='КС-62'))
    add('type-switch', 'engineer', step('Перечисли операции ТО-1.', 'operations', position=1),
        step('А операции ТО-2 целиком?', 'operations', position=2))
    add('past-to-future', 'chief_engineer', step('Есть назначенные работы на вчера? Только количество.', 'tasks',
        day='yesterday', state='assigned', count=True), step('А одну назначенную на завтра покажи.', 'tasks',
        day='tomorrow', state='assigned', limit=1))
    add('filter-change', 'director', step('Какие единицы без принятого ТО?', 'equipment', coverage='none'),
        step('Теперь наоборот, какие с уже принятым ТО?', 'equipment', coverage='present'))
    assert len(cases) == 50 and len({case.id for case in cases}) == len(cases)
    return tuple(cases)
