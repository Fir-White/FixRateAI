"""Outcome-based presenter checks; no model or exact tool-sequence assertions."""
from copy import deepcopy
import pytest
from app.assistant.fact_presenter import present_facts

USER = '11111111-1111-4111-8111-111111111111'
TASK = '22222222-2222-4222-8222-222222222222'


def text(value, tool, **kwargs):
    return '\n'.join(present_facts(value, tool=tool, **kwargs).lines)


def test_staff_delivers_actual_identity_effective_flags_dates_and_qualifications():
    value = dict(full_name='Иван Петров', role='executor', membership_is_active=True,
                 account_is_active=False, is_active=False, employed_from='2024-02-03',
                 employed_until=None, qualifications=[dict(skill_id='skill-7', verified_at='2026-10-10',
                 valid_until='2027-10-10')], shifts=[dict(label='Утренняя',
                 starts_local='08:00', ends_local='16:00')], availability=[])
    before = deepcopy(value)
    answer = text(value, 'staff_read', arguments=dict(path=dict(user_id=USER)))
    for actual in ('Иван Петров', 'Исполнитель', '2024-02-03', 'skill-7',
                   '2026-10-10', '2027-10-10', 'Утренняя', '08:00', '16:00'):
        assert actual in answer
    for fact in ('Членство активно: да', 'Учётная запись активна: нет',
                 'Доступ действует: нет', 'Окончание работы: не указано',
                 'Доступность: записей 0'):
        assert fact in answer
    assert '/api/v1/assistant/workspace/staff/' + USER in answer
    assert value == before


def test_task_delivers_instruction_norm_unit_assignees_and_actual_report_decision():
    value = dict(task=dict(summary='Проверка насоса', instructions='Отключить питание перед осмотром.',
                 normHours=0, normUnit=None, assignees=[dict(full_name='Анна Соколова')],
                 requiredActs=[], measurementRequirements=[dict(parameter_code='pressure', unit='кПа')]),
                 execution=dict(narrative='Есть течь', checklist=[dict(text='Герметичность', answer=False)],
                 readings=[dict(value=0, unit='кПа')], actual=dict(performed_at='2026-11-12T09:00:00+05:00')),
                 decision=dict(verdict='rejected', reason='Устранить течь', decidedBy='Инженер Иванов'))
    answer = text(value, 'task_read', arguments=dict(path=dict(task_id=TASK)))
    for actual in ('Проверка насоса', 'Отключить питание перед осмотром.', 'Анна Соколова',
                   'Есть течь', 'Герметичность', 'Ответ: нет', 'Значение: 0', 'Единица: кПа',
                   'Норма: 0', 'Единица нормы: не указано', 'Обязательные акты: записей 0',
                   'Устранить течь', 'Инженер Иванов', '2026-11-12T09:00:00+05:00'):
        assert actual in answer
    assert '/api/v1/maintenance/ui/tasks/' + TASK in answer
    assert 'Норма: 0.0' not in answer


@pytest.mark.parametrize(('unit', 'shown'), [
    (None, 'не указано'), ('', 'пустая строка'),
    ('unconfirmed', 'unconfirmed'), ('чел·ч', 'чел·ч'),
])
def test_missing_empty_and_unconfirmed_units_are_not_invented(unit, shown):
    answer = text(dict(normHours=0, normUnit=unit), 'task_read')
    assert 'Норма: 0.' in answer
    assert 'Единица нормы: ' + shown + '.' in answer
    if unit in (None, '', 'unconfirmed'):
        assert 'чел·ч' not in answer
        assert 'elapsed' not in answer


def test_workforce_nested_names_dates_and_empty_crews_are_visible():
    answer = text(dict(staff=[dict(full_name='Павел Орлов', role='engineer', employed_until='2026-12-01')],
                       crews=[], skills=[dict(name='Электробезопасность')]), 'workforce_read')
    for actual in ('Павел Орлов', 'Инженер', '2026-12-01', 'Бригады: записей 0',
                   'Электробезопасность', '/api/v1/maintenance/management/workforce'):
        assert actual in answer


def test_draft_changes_preserves_distinct_before_after_and_zero_values():
    answer = text(dict(items=[dict(title='ТО насоса',
                before=dict(start_at='2026-11-17T08:00:00Z', person_hours=0, locked=False),
                after=dict(start_at='2026-11-18T08:00:00Z', person_hours=2, locked=True))],
                total=1), 'draft_changes', arguments=dict(query=dict(identity=TASK,before_revision=2,after_revision=3)))
    for actual in ('До:', 'После:', '2026-11-17T08:00:00Z', '2026-11-18T08:00:00Z',
                   'Трудоёмкость, чел·ч: 0', 'Трудоёмкость, чел·ч: 2',
                   'Закреплено: нет', 'Закреплено: да', 'before_revision=2', 'after_revision=3'):
        assert actual in answer


def test_nested_credentials_and_trace_are_omitted_with_visible_notice():
    answer = text(dict(full_name='Доступный факт', api_key='MUST-NOT-APPEAR',
                       nested=dict(password='NO-PASSWORD', trace=['NO-TRACE'], value=0)),
                  'staff_read')
    assert 'Доступный факт' in answer
    assert 'Значение: 0' in answer
    assert 'MUST-NOT-APPEAR' not in answer
    assert 'NO-PASSWORD' not in answer
    assert 'NO-TRACE' not in answer
    assert 'Защищённые и служебные поля не показаны' in answer
    assert 'PRIVATE-ENROLLMENT' not in text(dict(code='PRIVATE-ENROLLMENT'), 'enrollment_read')


def test_global_row_budget_and_long_text_have_explicit_limits():
    rows = [dict(full_name='Сотрудник ' + str(i)) for i in range(100)]
    result = present_facts(dict(staff=rows), tool='workforce_read')
    answer = '\n'.join(result.lines)
    assert result.truncated
    assert 'Сотрудник 24' in answer
    assert 'Сотрудник 25.' not in answer
    assert 'Показано 25 из 100' in answer
    assert 'Показана ограниченная часть' in answer
    assert result.details_url == '/api/v1/maintenance/management/workforce'
    result = present_facts(dict(instructions='Длинная инструкция ' * 2000), tool='operation_read')
    assert result.truncated
    assert len('\n'.join(result.lines)) < 13000
    assert 'весь результат здесь не показан' in '\n'.join(result.lines)


def test_rendering_does_not_complete_pending_goal_or_mutate_evidence():
    from app.assistant.orchestrator import _render
    goal = dict(id='g1', title='Проверить сотрудника и завершить подготовку', kind='read',
                tool='staff_read', mode='read', status='partial', evidence_ids=['e1'])
    state = dict(goals=[goal], evidence=[dict(id='e1', tool='staff_read',
                 checked_at='2026-11-16T09:00:00Z', arguments=dict(path=dict(user_id=USER)),
                 result=dict(full_name='Лидия Фёдорова', role='engineer'))])
    before = deepcopy(state)
    answer = _render(state)
    assert 'Лидия Фёдорова' in answer
    assert 'Инженер' in answer
    assert 'Незавершённые пункты' in answer
    assert 'проверено частично' in answer
    assert state == before


def test_successful_read_with_undelivered_rows_stays_an_unfinished_objective():
    from app.assistant.orchestrator import finalize_delivery
    from app.assistant.workflow import update_outcome
    goal=dict(id='staff',title='Show the complete workforce',mode='read',tool='workforce_read',status='completed',evidence_ids=['e'])
    state=dict(goals=[goal],evidence=[dict(id='e',tool='workforce_read',result=dict(staff=[dict(full_name=str(i)) for i in range(100)]))])
    finalize_delivery(state);update_outcome(state)
    assert goal['status']=='partial' and goal['reason']=='result_delivery_truncated'
    assert state['outcome']!='completed'


def test_compound_request_reuses_unspent_display_budget_for_independent_results():
    from app.assistant.orchestrator import finalize_delivery,_render
    goals=[dict(id='equipment',title='All equipment',mode='read',tool='equipment_find',status='completed',evidence_ids=['e1']),
           dict(id='staff',title='Worker',mode='read',tool='staff_read',status='completed',evidence_ids=['e2'])]
    state=dict(goals=goals,evidence=[dict(id='e1',tool='equipment_find',checked_at='TEST',result=dict(total=31,items=[dict(asset_code='UNIT-'+str(i),name='Unit '+str(i)) for i in range(31)])),
        dict(id='e2',tool='staff_read',checked_at='TEST',result=dict(full_name='Visible person',is_active=False))])
    finalize_delivery(state)
    assert all(goal['status']=='completed' for goal in goals)
    answer=_render(state)
    assert all('UNIT-'+str(i) in answer for i in range(31)) and 'Visible person' in answer


def equipment_rows(count):
    return [dict(equipment_id=f'identity-{index}', asset_code=f'PUMP-{index:03}',
                 name=f'Насос {index:03}', status='active', commissioned_on='2020-02-03',
                 system_id='system', equipment_type_id='type', parent_equipment_id=None,
                 serial_number=f'serial-{index}', location='Подвал', properties={'note': 'not a list field'},
                 revision=7, site_id='site') for index in range(count)]


def test_equipment_full_list_delivers_all_31_actual_names_without_expanding_cards():
    value = dict(items=equipment_rows(31), total=31, returned_count=31, complete=True)
    before = deepcopy(value)
    result = present_facts(value, tool='equipment_find')
    answer = '\n'.join(result.lines)
    assert result.truncated is False
    assert 'Найдено: 31. Прочитано: 31.' in answer
    assert 'Показано: 31 из 31' in answer
    for row in value['items']:
        assert row['name'] in answer
        assert row['asset_code'] in answer
    assert 'active' in answer and '2020-02-03' in answer
    assert 'serial-' not in answer and 'not a list field' not in answer
    assert value == before


def test_equipment_over_50_has_explicit_partial_delivery_and_actual_counts():
    result = present_facts(dict(items=equipment_rows(61), total=61), tool='equipment_find')
    answer = '\n'.join(result.lines)
    assert result.truncated is True
    assert 'Найдено: 61. Прочитано: 61.' in answer
    assert 'Показано: 50 из 61' in answer
    assert 'Насос 049' in answer and 'Насос 050' not in answer
    assert 'Список показан частично' in answer


def test_equipment_compact_summary_keeps_zero_false_none_and_empty_date_visible():
    value = dict(items=[dict(asset_code=0, name='Нулевое оборудование', status=False, commissioned_on=None),
                        dict(asset_code='EMPTY', name='Без даты', status='active', commissioned_on='')], total=2)
    answer = text(value, 'equipment_find')
    assert '- 0; Нулевое оборудование; состояние: нет; дата ввода: не указано.' in answer
    assert 'дата ввода: пустая строка.' in answer


def test_equipment_compact_character_budget_never_silently_cuts_an_identity():
    result = present_facts(dict(items=equipment_rows(31), total=31), tool='equipment_find', max_characters=100)
    answer = '\n'.join(result.lines)
    assert result.truncated is True
    assert 'Показано: 1 из 31' in answer
    assert 'Насос 000' in answer and 'Насос 001' not in answer
    assert 'весь прочитанный результат здесь не показан' in answer


@pytest.mark.parametrize(('requested', 'shown'), [(3, 3), (200, 50)])
def test_equipment_compact_budget_can_shrink_but_cannot_expand_past_50(requested, shown):
    result = present_facts(dict(items=equipment_rows(61), total=61), tool='equipment_find', max_compact_rows=requested)
    assert result.truncated is True
    assert f'Показано: {shown} из 61' in '\n'.join(result.lines)
