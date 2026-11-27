"""Control prompts for the next run. Preserve prompts and assertions in place."""
from tests.agent_reliability_lab.evals.corpus import Case, Step


HOLDOUT = (
    Case('control-exact-card-engineer', 'facts', 'engineer', (
        Step('Оборудование КА-210. Выпиши из карточки его инвентарный код, название, место установки, UUID и состояние. Приведи источник.',
             'card_source', ('КА-210',)),
    ), 'holdout'),
    Case('control-missing-code', 'uncertainty', 'director', (
        Step('Покажи карточку ИТП-29.', 'absent', ('ИТП-29',)),
    ), 'holdout'),
    Case('control-current-comparison-director', 'analytics', 'director', (
        Step('Сопоставьте КА-210 и ИТП-21 по состоянию, незавершённым работам и просрочкам.', 'compare', ('КА-210', 'ИТП-21')),
    ), 'holdout'),
    Case('control-historical-cutoff', 'analytics', 'engineer', (
        Step('Сравни ИТП-21 и КА-210 на дату {historical}. Сколько у каждого незавершённых и просроченных нарядов? Укажи UUID и поясни ограничение исторического среза.',
             'historical_compare', ('ИТП-21', 'КА-210')),
    ), 'holdout'),
    Case('control-latest-vs-unaccepted', 'facts', 'chief_engineer', (
        Step('Когда было последнее принятое обслуживание КА-210? Укажи UUID отчёта.',
             'accepted_history', ('КА-210',)),
    ), 'holdout'),
    Case('control-comparison-winner', 'context', 'engineer', (
        Step('Сравни КА-21 и КА-210 по состоянию, открытым заданиям и просрочкам.', 'compare', ('КА-21', 'КА-210')),
        Step('А теперь выбери оборудование с максимальным количеством просрочек: историю ТО и действующий регламент.',
             'winner_history', ('КА-21', 'КА-210')),
    ), 'holdout'),
    Case('control-executor-overdue', 'executor', 'executor', (
        Step('Перечисли только мои незакрытые наряды с истёкшим нормативным сроком. Чужие и завершённые не выводи.',
             'own_overdue', ()),
    ), 'holdout'),
    Case('control-executor-today', 'executor', 'executor', (
        Step('На чём я сегодня работаю? Мне нужны мои задания, запланированные на сегодня.',
             'own_today', ()),
    ), 'holdout'),
    Case('control-compose-from-ledger', 'compound', 'engineer', (
        Step('Нужна сводка по КА-210. Включи состояние карточки, нормативные сроки просроченных работ, последнее принятое ТО, действующий регламент и две конкретные рекомендации. Без изменений.',
             'equipment_report', ('КА-210',)),
    ), 'holdout'),
)
