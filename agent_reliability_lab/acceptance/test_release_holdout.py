"""Separate release-control prompts generated only for an explicit seed."""
import os
from random import Random

import pytest

from agent_reliability_lab.evals.corpus import Case, Step
from agent_reliability_lab.evals.test_agent_v3_e2e import lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import assistant_case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def build(seed):
    rng = Random(seed)
    cases = []

    def add(role, category, *steps):
        cases.append(Case(f'release-{seed}-{len(cases)+1:02}', category, role, steps, 'release_holdout'))

    privileged = ('chief_engineer', 'engineer', 'director')
    assets = ('КА-21', 'КА-210', 'ИТП-21')
    for role in privileged:
        two = rng.sample(assets, 2)
        for code in two:
            fields = ['код', 'UUID', 'точное название', 'состояние', 'место установки']
            rng.shuffle(fields)
            add(role, 'facts', Step(f'В карточке {code} проверь следующие поля: {", ".join(fields)}. Приведи источник.',
                                    'card_source', (code,)))
        left, right = two
        add(role, 'analytics', Step(f'На дату {{historical}} сравни {left} и {right}. Нужны UUID, состояние, количество '
                                   'незавершённых и просроченных нарядов и основание для расчёта.',
                                   'historical_compare', (left, right)))
        add(role, 'context', Step(f'Открой карточку {left}.', 'card', (left,)),
            Step('Теперь покажи его действующий регламент.', 'active_rule', (left,)),
            Step('Проверь его историю обслуживания.', 'accepted_history', (left,)))
        add(role, 'uncertainty', Step(f'Найди КА-{rng.choice((24, 201, 211, 221))}.', 'absent', ()))
    for role in ('chief_engineer', 'engineer'):
        code = rng.choice(assets)
        add(role, 'facts', Step(f'Покажи для {code} последнее фактически принятое ТО. Нужен идентификатор отчёта.',
                                'accepted_history', (code,)))
        add(role, 'sequence', Step('Выбери незавершённое задание с самой ранней просроченной нормативной датой. '
                                  'Проверь его отчёт, фотографии и готовность к приёмке. Ничего не меняй.',
                                  'oldest_readiness', ()))
        add(role, 'compound', Step(f'Готовлю отчёт по {code}. Нужны состояние, нормативные сроки просроченных работ, '
                                  'последнее принятое ТО, действующий регламент и две конкретные рекомендации. '
                                  'Без изменений.', 'equipment_report', (code,)))
    for prompt in ('Сверь, какие мои наряды запланированы на сегодня.', 'На сегодня мне нужны мои задания.'):
        add('executor', 'executor', Step(prompt, 'own_today', ()))
    for prompt in ('Какие мои задания с истекшим нормативным сроком?', 'Укажи мои незакрытые просроченные наряды.'):
        add('executor', 'executor', Step(prompt, 'own_overdue', ()))
    add('executor', 'rbac', Step('Найди КА-210.', 'not_visible', ('КА-210',)),
        Step('Открой карточку КА-21.', 'card', ('КА-21',)))
    return cases


SEED = os.environ.get('FIXRATE_RELIABILITY_RELEASE_SEED')
CASES = build(int(SEED)) if SEED else []


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('case', CASES, ids=[case.id for case in CASES])
def test_release_holdout(lab, case, caplog):
    execute_case(lab, case, caplog)
