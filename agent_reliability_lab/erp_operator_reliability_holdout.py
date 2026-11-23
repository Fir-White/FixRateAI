"""Additional frozen prompts, evaluated with the existing SQL oracle."""
from random import Random

from agent_reliability_lab.evals import test_pipeline_comparison as comparison
from agent_reliability_lab.evals.test_pipeline_comparison import pipeline_fixture
from agent_reliability_lab.pipeline_cases import Conversation, step
from tests.backend.test_assistant import assistant_case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def corpus():
    roles = ('chief_engineer', 'executor', 'engineer', 'director')
    cases = []
    for index, seed in enumerate((41, 107, 283, 509, 1301)):
        rng = Random(seed)
        serviced = rng.choice(('КС-61', 'КС-63'))
        pending = rng.choice(('КС-62', 'КС-64', 'КС-65'))
        cases.extend(
            Conversation(f'R{seed}-{family}', roles[(index + position) % len(roles)], checks)
            for position, (family, checks) in enumerate((
                ('card-and-actual', (
                    step(f'Открой полную карточку установки {serviced}. Сверяю, где она стоит.', 'card', code=serviced),
                    step('Дай номер принятого отчёта по ней, самый свежий.', 'history', code=serviced),
                )),
                ('asset-and-next-day', (
                    step(f'Поищи по инвентарному коду {pending}.', 'equipment', code=pending),
                    step('По найденному активу дай первый назначенный наряд на послезавтра, только один.', 'tasks',
                         code=pending, day='next_day', state='assigned', limit=1),
                )),
                ('accepted-coverage', (
                    step('Сколько единиц имеют в нашем доступе подтверждённое ТО с принятым отчётом?', 'equipment',
                         count=True, coverage='present'),
                    step('Теперь покажи состав этой выборки.', 'equipment', coverage='present'),
                    step('Из неё выбери на завтра один наиболее ранний назначенный наряд.', 'tasks',
                         day='tomorrow', state='assigned', coverage='present', limit=1),
                )),
                ('unaccepted-coverage', (
                    step('Нужны установки, где принятого отчёта по ТО в истории нет.', 'equipment', coverage='none'),
                    step('По этому перечню дай на {tomorrow} только первый по времени наряд из черновиков.',
                         'tasks', day='tomorrow', coverage='none', state='draft', limit=1),
                )),
                ('date-and-count', (
                    step('На {next_day} покажи первый назначенный наряд. Хватит одной позиции.', 'tasks',
                         day='next_day', state='assigned', limit=1),
                    step('Переставим на сутки раньше, остальное то же.', 'tasks', day='tomorrow', state='assigned', limit=1),
                    step('А теперь только сколько таких нарядов за этот день.', 'tasks', day='tomorrow', state='assigned', count=True),
                )),
                ('asset-switch', (
                    step(f'Нужна карточка {serviced}.', 'card', code=serviced),
                    step(f'Переключись на карточку оборудования {pending}.', 'card', code=pending),
                    step(f'Вернёмся к {serviced}: какой последний принятый отчёт по ТО?', 'history', code=serviced),
                )),
                ('catalog-reference', (
                    step('Что сейчас доступно по видам обслуживания? Сначала только виды ТО.', 'types'),
                    step('Раскрой второй вид из ответа, выведи весь перечень операций.', 'operations', position=2),
                    step('Такой же перечень для ТО-1.', 'operations', position=1),
                )),
                ('regulation', (
                    step(f'Мне нужен действующий регламент по инвентарному коду {pending}.', 'regulation', code=pending),
                    step(f'А какие регламенты действуют для {serviced}?', 'regulation', code=serviced),
                )),
                ('empty-and-retry', (
                    step('Проверь, есть ли единица с точным кодом КС-00.', 'equipment', code='КС-00'),
                    step(f'Исправлю код: {pending}. Найди именно его.', 'equipment', code=pending),
                    step('Покажи по нему последний принятый отчёт, если найдётся.', 'history', code=pending),
                )),
                ('status-switch', (
                    step('Сколько завтра назначенных нарядов?', 'tasks', day='tomorrow', state='assigned', count=True),
                    step('Оставь дату, но возьми только один ближайший черновик.', 'tasks',
                         day='tomorrow', state='draft', limit=1),
                )),
            ))
        )
    return cases


def test_reliability_holdout(pipeline_fixture, monkeypatch):
    cases = corpus()
    assert len(cases) == len({case.id for case in cases}) == 50
    monkeypatch.setattr(comparison, 'CASES', cases)
    comparison.test_pipeline_comparison(pipeline_fixture, monkeypatch)
