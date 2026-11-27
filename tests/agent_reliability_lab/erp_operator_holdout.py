"""Frozen multi-turn validation prompts, scored against the comparison fixture's SQL ledger."""
from random import Random

from tests.agent_reliability_lab.evals import test_pipeline_comparison as comparison
from tests.agent_reliability_lab.evals.test_pipeline_comparison import pipeline_fixture
from tests.agent_reliability_lab.pipeline_cases import Conversation, step
from tests.backend.test_assistant import assistant_case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def corpus():
    cases = []
    for seed in (19, 83):
        rng = Random(seed)
        roles = ['chief_engineer', 'engineer', 'director', 'executor']
        rng.shuffle(roles)
        for role in roles:
            present = rng.choice(('КС-61', 'КС-63'))
            missing = rng.choice(('КС-62', 'КС-64', 'КС-65'))
            cases.append(Conversation(f'{seed}-{role}-asset-focus', role, (
                step(f'Из реестра мне нужна карточка {present}, сверяю место монтажа.', 'card', code=present),
                step('С этой же установки возьми идентификатор последнего принятого отчёта по ТО.', 'history', code=present),
                step(f'Теперь новая установка, {missing}. Дай запись реестра только по этому коду.', 'equipment', code=missing),
                step('Здесь тоже должна быть история решений. Назови последний принятый отчёт, если он есть.', 'history', code=missing),
                step('На завтра по этой же установке дай самый ранний из назначенных нарядов. Нужна одна позиция.', 'tasks',
                     code=missing, state='assigned', day='tomorrow', limit=1),
                step('По-прежнему один, но на следующую дату.', 'tasks',
                     code=missing, state='assigned', day='next_day', limit=1),
            )))
    for role in ('engineer', 'executor'):
        cases.append(Conversation(f'{role}-cohort-and-count', role, (
            step('Сверь число установок, для которых в доступном журнале есть хотя бы один принятый отчёт ТО.',
                 'equipment', coverage='present', count=True),
            step('Раскрой состав именно этой группы, по одной установке на строку.', 'equipment', coverage='present'),
            step('Для этой группы выведи один первый наряд на {next_day}, со статусом «назначен».',
                 'tasks', coverage='present', day='next_day', state='assigned', limit=1),
            step('Возьми день перед этой датой. Группа, состояние и число строк прежние.',
                 'tasks', coverage='present', day='tomorrow', state='assigned', limit=1),
            step('Посчитай все назначенные работы в этой группе на ту же дату, перечислять их не нужно.',
                 'tasks', coverage='present', day='tomorrow', state='assigned', count=True),
        )))
    return cases


def test_erp_operator_holdout(pipeline_fixture, monkeypatch):
    monkeypatch.setattr(comparison, 'CASES', corpus())
    comparison.test_pipeline_comparison(pipeline_fixture, monkeypatch)
