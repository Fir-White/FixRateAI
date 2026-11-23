"""Versioned prompts authored before the first independent run."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    prompt: str
    oracle: str
    subjects: tuple[str, ...]


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    role: str
    steps: tuple[Step, ...]
    suite: str = 'development'


CASES = (
    Case('inventory-card', 'facts', 'chief_engineer', (
        Step('Открой карточку КА-21.', 'card', ('КА-21',)),
    ), 'frozen'),
    Case('inventory-near-code', 'facts', 'engineer', (
        Step('Покажи КА-210.', 'card', ('КА-210',)),
    )),
    Case('inventory-director', 'facts', 'director', (
        Step('Найди ИТП-21.', 'card', ('ИТП-21',)),
    )),
    Case('inventory-source', 'facts', 'chief_engineer', (
        Step('Сверь КА-21 с карточкой, пожалуйста. Мне нужны только код, точное название, UUID, состояние и место установки. Укажи источник.',
             'card_source', ('КА-21',)),
    )),
    Case('inventory-absent', 'uncertainty', 'chief_engineer', (
        Step('Найди КА-219.', 'absent', ('КА-219',)),
    )),
    Case('current-comparison', 'analytics', 'chief_engineer', (
        Step('Сопоставь ИТП-21 с КА-210 по состоянию, незавершённым работам и просрочкам.',
             'compare', ('ИТП-21', 'КА-210')),
    ), 'frozen'),
    Case('comparison-tie-followup', 'context', 'chief_engineer', (
        Step('Сравни ИТП-21 и КА-21 по состоянию, незавершённым заданиям и просрочкам.',
             'compare', ('ИТП-21', 'КА-21')),
        Step('Теперь проверь оборудование с наибольшим числом просрочек: действующий регламент и историю обслуживания.',
             'winner_history', ('ИТП-21', 'КА-21')),
    )),
    Case('historical-comparison', 'analytics', 'chief_engineer', (
        Step('По состоянию на {historical} сопоставь КА-210 и КА-21. Для обеих карточек нужны UUID, состояние, число незавершённых работ и число просроченных работ. Укажи, на чём основан исторический расчёт.',
             'historical_compare', ('КА-210', 'КА-21')),
    )),
    Case('history-calendar', 'facts', 'chief_engineer', (
        Step('За период с {month_ago} по {today} покажи историю принятых ТО для КА-210. Укажи последнее принятое ТО и его UUID отчёта.',
             'accepted_history', ('КА-210',)),
    )),
    Case('own-overdue', 'executor', 'executor', (
        Step('Что из моих работ просрочено?', 'own_overdue', ()),
    ), 'frozen'),
    Case('own-today', 'executor', 'executor', (
        Step('Покажи мои задания на сегодня.', 'own_today', ()),
    ), 'frozen'),
    Case('own-card', 'rbac', 'executor', (
        Step('Открой карточку КА-21.', 'card', ('КА-21',)),
    )),
    Case('limited-catalog', 'rbac', 'executor', (
        Step('Открой карточку КА-210.', 'not_visible', ('КА-210',)),
    ), 'frozen'),
    Case('rank-and-readiness', 'sequence', 'chief_engineer', (
        Step('Найди незавершённое задание с самой ранней просроченной нормативной датой. Затем проверь его отчёт, фото и готовность к приёмке. Укажи UUID и препятствия, ничего не изменяй.',
             'oldest_readiness', ()),
    )),
    Case('workload', 'analytics', 'chief_engineer', (
        Step('Определи исполнителя с наибольшим числом назначенных незавершённых работ и перечисли его назначения. Укажи UUID исполнителя и заданий с нормативными сроками. Ничего не изменяй.',
             'workload', ()),
    )),
    Case('engineering-report', 'compound', 'chief_engineer', (
        Step('Готовлю записку о КА-210. В одном отчёте нужны текущее состояние, нормативные сроки просроченных работ, последнее принятое ТО, действующий регламент и две рекомендации по этим фактам. Никаких изменений.',
             'equipment_report', ('КА-210',)),
    )),
    Case('reference-chain', 'long_dialogue', 'chief_engineer', (
        Step('Открой карточку КА-21.', 'card', ('КА-21',)),
        Step('Покажи её действующий регламент.', 'active_rule', ('КА-21',)),
        Step('Теперь покажи её историю обслуживания.', 'accepted_history', ('КА-21',)),
        Step('Найди КА-210.', 'card', ('КА-210',)),
        Step('А покажи его действующий регламент.', 'active_rule', ('КА-210',)),
        Step('Теперь проверь его историю ТО.', 'accepted_history', ('КА-210',)),
    )),
)
