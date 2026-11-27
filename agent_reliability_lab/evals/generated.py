"""Generate reproducible metamorphic checks from operation and scope invariants."""
from random import Random

from agent_reliability_lab.evals.corpus import Case, Step


def generate(seed):
    rng = Random(seed)
    equipment = ['КА-21', 'КА-210', 'ИТП-21']
    roles = ['chief_engineer', 'engineer', 'director']
    case_id = 0
    for role in roles:
        order = rng.sample(equipment, len(equipment))
        for code in order:
            case_id += 1
            yield Case(f'generated-{seed}-card-{case_id}', 'metamorphic', role, (
                Step(f'Открой {code}.', 'card', (code,)),
                Step(rng.choice([
                    f'Выпиши UUID, инвентарный код, название, статус и место установки {code}. Укажи источник карточки.',
                    f'Для {code} перечисли состояние, расположение, инвентарный код, UUID и название. Нужен источник.',
                    f'Инвентарный код {code}. Из карточки нужны название, код, место установки, состояние, UUID и источник.',
                ]), 'card_source', (code,)),
            ), 'metamorphic')
        first, second = order[:2]
        yield Case(f'generated-{seed}-swap-{role}', 'metamorphic', role, (
            Step(f'Сравни {first} и {second} по незавершённым работам и просрочкам.', 'compare', (first, second)),
            Step(f'Сопоставь {second} с {first} по незавершённым работам и просрочкам.', 'compare', (second, first)),
        ), 'metamorphic')
    yield Case(f'generated-{seed}-executor-scope', 'metamorphic', 'executor', (
        Step('Открой карточку КА-210.', 'not_visible', ('КА-210',)),
        Step('Найди КА-21.', 'card', ('КА-21',)),
        Step('Покажи КА-210.', 'not_visible', ('КА-210',)),
    ), 'metamorphic')
