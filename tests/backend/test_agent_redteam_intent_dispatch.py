"""Explicit action clauses must reach proposal planning, never stop at a read shortcut."""
from uuid import UUID
import pytest
from app.assistant.intents import mutation_requested,literal_rename
from app.assistant.inventory_report import requested as inventory_requested
from app.assistant.task_report import requested as tasks_requested
from app.assistant.grounding import regulation_lookup,equipment_code,equipment_listing


@pytest.mark.parametrize('question',[
    'List saved operations. Do not create, approve or edit operations.',
    'Show the crew. Do not assign tasks or edit the crew.',
    'Read the profile. Never change roles and reset passwords.',
    'Покажи оборудование. Не изменяй имя и удаляй оборудование.',
])
def test_coordinated_prohibitions_do_not_turn_reads_into_mutations(question):
    assert not mutation_requested(question)


@pytest.mark.parametrize('question',[
    'Do not delete equipment; rename it.',
    'Do not edit equipment. Publish the plan.',
    'Do not rename it, but update its location.',
    'Do not delete it, then edit its name.',
    'This is not a read: rename equipment.',
    'Насос не работает, переименуй его.',
    'Not only edit the name but publish the plan.',
])
def test_positive_action_after_a_negative_clause_still_requires_mutation_handling(question):
    assert mutation_requested(question)


@pytest.mark.parametrize('prefix',[
    'Покажи оборудование текущего объекта.',
    'Покажи регламент насоса с кодом RT-PUMP.',
    'Дай обзор оборудования текущего объекта.',
    'Проанализируй все объекты и оборудование.',
    'Покажи все незавершённые задания.',
])
def test_read_shortcuts_do_not_swallow_a_following_rename(prefix):
    question=prefix+' Затем переименуй оборудование в «Новое имя». Остальные поля не меняй.'
    assert mutation_requested(question)
    assert not inventory_requested(question) and not tasks_requested(question) and not regulation_lookup(question) and not equipment_listing(question)


@pytest.mark.parametrize('action',['создай задание','обнови роль','перенеси работу','переименуйте оборудование','опубликуй план'])
def test_read_shortcuts_do_not_swallow_other_explicit_mutations(action):
    question='Покажи все объекты и оборудование, регламенты и незавершенные задания, затем '+action+'.'
    assert mutation_requested(question)
    assert not inventory_requested(question) and not tasks_requested(question) and not regulation_lookup(question)


@pytest.mark.parametrize('question',[
    'Покажи оборудование. Ничего не меняй.',
    'Покажи регламент. Не измени его.',
    'Покажи все задания. Не назначь никого.',
    'Покажи оборудование. Do not rename it.',
    "Покажи регламент. Don't update anything.",
])
def test_negative_action_reminder_does_not_become_a_mutation(question):assert not mutation_requested(question)


@pytest.mark.parametrize('name',['Насос DELTA','Насос "A"','RT/Насос-1','Насос \\ север','Онлайн_%_Тест'])
def test_rename_literal_is_copied_from_the_user_without_unescaping(name):
    assert literal_rename('Переименуй оборудование в «'+name+'».')==name


@pytest.mark.parametrize('question',[
    'Покажи оборудование в «Корпус A».',
    'Переименуй A в «Имя A», B в «Имя B».',
    'Переименуй оборудование в «».',
    'Переименуй оборудование.',
    'Переименуй оборудование в «не закончено',
])
def test_ambiguous_or_missing_literal_is_not_guessed(question):assert literal_rename(question) is None


@pytest.mark.parametrize('identity',[
    '12345678-1234-1234-1234-123456789abc',
    'ABCDEFAB-1234-4567-89AB-123456789ABC',
    '00000000-0000-0000-0000-000000000001',
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
    '6af720fa-b311-4bc8-998c-788c9030058a',
])
def test_explicit_resource_uuid_is_not_inferred_as_an_inventory_label(identity):
    UUID(identity)
    assert equipment_code('Покажи оборудование equipment_id='+identity) is None
    assert equipment_code('Найди оборудование с кодом «'+identity+'».')==identity
