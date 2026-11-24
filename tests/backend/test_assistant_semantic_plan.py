"""Domain meaning, literal constraints, authorized execution and compact answers."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.assistant.semantic_execution import next_step, render
from app.assistant.semantic_plan import RequestedResult, RequestedResults, compile_plan, explicit_results, may_offer_legacy
from app.integration.demo import demo_id
from tests.backend.test_assistant import B, assistant_case, confirm, equipment_body, thread
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import login, runtime


def compile_results(request, results, *authorized):
    selection, metadata = compile_plan(
        RequestedResults(results=results), request, dict.fromkeys(authorized, SimpleNamespace()),
        {'local_date': '2027-04-02'}, [],
    )
    return [(goal.model_dump(mode='json'), metadata[goal.id]) for goal in selection.goals]


def test_semantic_multi_entity_read_keeps_exact_ids_and_only_requested_fields():
    left, right = str(uuid4()), str(uuid4())
    request = f'Сообщите статус работ {left} и {right}, каждую отдельно.'
    goals = compile_results(request, [RequestedResult(intent='task_details', subjects=[left], fields=['state'])], 'task_read')
    assert [meta['subject'] for _, meta in goals] == [left, right]
    for goal, meta in goals:
        goal.update(semantic=meta)
        assert next_step(goal, {'scope': {}, 'evidence': []}).calls[0].arguments == {'path': {'task_id': meta['subject']}}
        assert render(goal, [{'tool':'task_read', 'result':{'task':{'state':'assigned','title':'Лишнее название'}}}]) == 'Состояние: назначено'


def test_semantic_permissions_and_revision_are_authoritative():
    identity = str(uuid4())
    request = f'Приступи к выполнению задания {identity}.'
    result = RequestedResult(intent='start_task', subjects=[identity])
    (denied, decision), = compile_results(request,[result],'task_read')
    assert not denied['tool'] and 'роли' in decision['block']
    (allowed, decision), = compile_results(request,[result],'task_start')
    allowed['semantic'] = decision
    assert next_step(allowed, {'scope': {}, 'evidence': []}).calls[0].arguments == {'path': {'task_id': identity}, 'body': {}}
    assert not may_offer_legacy('task_cancel', request)
    assert not may_offer_legacy('staff_edit', 'Назови роль сотрудника из карточки.')
    assert not may_offer_legacy('equipment_edit', 'Прочитай описание «Измени место установки».')


def test_semantic_count_uses_server_selected_scope_and_no_extra_counters():
    query = 'Сколько работ, созданных вручную, ещё не завершено с 2027-04-01 по 2027-04-09?'
    (goal, meta), = compile_results(query,[RequestedResult(intent='task_count')],'tasks_analyze')
    goal['semantic'] = meta
    assert next_step(goal, {'scope': {}, 'evidence': []}).calls[0].arguments['query'] == {
        'section':'summary','origin':'manual','starts_on':'2027-04-01','ends_on':'2027-04-09',
    }
    assert render(goal,[{'tool':'tasks_analyze','result':{'complete':True,'selected_tasks':4,'counters':{'unfinished':81}}}]) == '4'


def test_lookup_and_exclusive_projection_are_one_read():
    request = 'Отыщи КЛ-23 по инвентарному коду и покажи исключительно расположение, без названия.'
    (goal, meta), = compile_results(request, [RequestedResult(intent='equipment_exists', subjects=['КЛ-23'], fields=['name'])],
                                   'equipment_read', 'equipment_find')
    assert goal['tool'] == 'equipment_read' and meta['fields'] == ['location']


def test_mixed_entities_do_not_share_each_others_requested_fields():
    identity = str(uuid4())
    request = f'Назови статус наряда {identity} и место установки КЛ-23.'
    goals = compile_results(request, [
        RequestedResult(intent='task_details', subjects=[identity], fields=['state', 'deadline']),
        RequestedResult(intent='equipment_details', subjects=['КЛ-23'], fields=['state', 'location']),
    ], 'task_read', 'equipment_read')
    assert [meta['fields'] for _, meta in goals] == [['state'], ['location']]


def test_password_request_does_not_add_unrelated_staff_fields():
    request = 'Назови текущий пароль и рабочий email Дарьи Игнатьевой.'
    goals = compile_results(request, [
        RequestedResult(intent='staff_details', subjects=['Дарьи Игнатьевой'], fields=['role', 'email']),
    ], 'staff_read')
    assert [meta['intent'] for _, meta in goals] == ['staff_details', 'password']
    assert goals[0][1]['fields'] == ['email'] and 'пароль' in goals[1][1]['block']


def test_equipment_preflight_is_visible_only_when_user_requests_read():
    results = [RequestedResult(intent='equipment_details', subjects=['КЛ-23']),
               RequestedResult(intent='move_equipment', subjects=['КЛ-23'], value='Узел 14')]
    change = 'Измени место установки КЛ-23 на «Узел 14».'
    goals = compile_results(change, results, 'equipment_edit', 'equipment_read')
    assert [goal['tool'] for goal, _ in goals] == ['equipment_edit']
    read_and_change = 'Покажи место установки КЛ-23. Затем измени место установки КЛ-23 на «Узел 14».'
    goals = compile_results(read_and_change, results, 'equipment_edit', 'equipment_read')
    assert [goal['tool'] for goal, _ in goals] == ['equipment_read', 'equipment_edit']


def test_user_supplied_revision_is_kept_and_unknown_condition_cannot_prepare_change():
    identity = str(uuid4())
    result = RequestedResult(intent='start_task', subjects=[identity])
    (goal, meta), = compile_results(f'Начни задание {identity} с ревизией 7.', [result], 'task_start')
    goal['semantic'] = meta
    assert next_step(goal, {'scope': {}, 'evidence': []}).calls[0].arguments['body'] == {'expected_revision': 7}
    (goal, meta), = compile_results(f'Начни задание {identity}, если завтра будет доступен объект.', [result], 'task_start')
    assert goal['tool'] == '' and 'Условие' in meta['block']


def test_live_http_pipeline_uses_intent_plan_and_protected_proposal_boundary(assistant_case):
    engine, app, client, _, _ = assistant_case

    class Provider:
        supports_semantic_plan = True

        def chat(self, messages, schema, budget):
            assert schema is RequestedResults
            # Simulate a model that mistakes a profile lookup for a mutation.
            return RequestedResults(results=[
                RequestedResult(intent='self_profile', fields=['role']),
                RequestedResult(intent='start_task'),
            ])

    app.state.assistant_provider_factory = Provider
    try:
        identity = thread(client)
        sent = client.post(B + f'/conversations/{identity}/messages',
                           json={'content':'Покажи роль моего аккаунта. Только чтение.', 'idempotency_key':str(uuid4())})
        assert sent.status_code == 202
        saved = client.get(B + f'/conversations/{identity}').json()
        turn = saved['turns'][-1]
        assert turn['status'] == 'completed'
        assert [line['tool'] for line in turn['trace']] == ['profile_read']
        assert 'Роль:' in turn['answer'] and not saved['actions']
    finally:
        del app.state.assistant_provider_factory


@pytest.fixture
def hardening_executor(assistant_case):
    engine, _, _, login_person, ids = assistant_case
    identity = uuid4()
    address = f'hardening-{identity.hex}@example.test'
    with engine.begin() as db:
        db.execute(text("""INSERT INTO users(user_id,full_name,email,password_hash)
                          SELECT :id,'Hardening executor',:email,password_hash FROM users WHERE user_id=:admin"""),
                   {'id':identity,'email':address,'admin':ids['user']})
        db.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:id,'executor')"),
                   {'site':ids['site'],'id':identity})
    with login_person(address) as client:
        yield client


@pytest.mark.parametrize('case', ['apply', 'stale', 'stale_preview', 'reject', 'expired', 'rollback', 'forbidden', 'incomplete'])
def test_compound_equipment_changes_share_confirmation_and_transaction(assistant_case, hardening_executor, case, monkeypatch):
    engine, app, admin, _, ids = assistant_case
    executor = hardening_executor
    body = {**equipment_body(ids), 'location': 'Западная галерея'}
    response = admin.post('/api/v1/maintenance/equipment', json=body)
    assert response.status_code == 201, response.text
    item = response.json()
    endpoint = '/api/v1/maintenance/equipment/' + item['equipment_id']
    actor = executor if case == 'forbidden' else admin
    chat = thread(actor)
    request = f'Измени место установки {body["asset_code"]} на «Пост 7» и название на «Узел подпитки».'
    if case == 'incomplete':
        request = f'Измени место установки {body["asset_code"]} на «Пост 7» и укажи новое название в этой же карточке.'
    elif case == 'stale_preview':
        request += ' Для ревизии 9.'

    class Provider:
        supports_semantic_plan = True

        def chat(self, messages, schema, budget):
            raise AssertionError('The explicit compound command is resolved before inference')

    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    sent = actor.post(f'{B}/conversations/{chat}/messages',
                      json={'content': request, 'idempotency_key': str(uuid4())})
    assert sent.status_code == 202, sent.text
    conversation = actor.get(f'{B}/conversations/{chat}').json()
    assert admin.get(endpoint).json() == item
    if case in ('forbidden', 'incomplete', 'stale_preview'):
        assert not conversation['actions']
        if case == 'stale_preview':
            assert any(step.get('code') == 409 for step in conversation['turns'][-1]['trace'])
        return
    action, = conversation['actions']
    assert action['status'] == 'proposed'
    assert action['arguments']['path'] == {'equipment_id': item['equipment_id']}
    assert action['arguments']['body'] == {'name': 'Узел подпитки', 'location': 'Пост 7',
                                          'expected_revision': item['revision']}
    assert confirm(executor, action).status_code == 404
    if case == 'reject':
        assert admin.post(f'{B}/actions/{action["action_id"]}/reject').json()['status'] == 'rejected'
        assert confirm(admin, action).json()['status'] == 'rejected'
    elif case == 'expired':
        with engine.begin() as db:
            db.execute(text("UPDATE assistant_actions SET expires_at=now()-interval '1 second' WHERE action_id=:id"),
                       {'id': action['action_id']})
        assert confirm(admin, action).status_code == 409
    elif case == 'rollback':
        with engine.begin() as db:
            db.execute(text("""CREATE FUNCTION hardening_fail_compound_edit() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                    IF NEW.name = 'Узел подпитки' AND NEW.location = 'Пост 7' THEN
                        RAISE EXCEPTION 'test database write failure';
                    END IF;
                    RETURN NEW;
                END $$"""))
            db.execute(text("""CREATE TRIGGER hardening_fail_compound_edit AFTER UPDATE ON equipment
                              FOR EACH ROW EXECUTE FUNCTION hardening_fail_compound_edit()"""))
        try:
            result = confirm(admin, action)
            assert result.status_code == 200 and result.json()['status'] == 'uncertain', result.text
            assert confirm(admin, action).json() == result.json()
        finally:
            with engine.begin() as db:
                db.execute(text('DROP TRIGGER hardening_fail_compound_edit ON equipment'))
                db.execute(text('DROP FUNCTION hardening_fail_compound_edit()'))
    elif case == 'stale':
        changed = admin.patch(endpoint, json={'expected_revision': item['revision'], 'location': 'Галерея 2'})
        assert changed.status_code == 200, changed.text
        item = changed.json()
        assert confirm(admin, action).status_code == 409
    else:
        result = confirm(admin, action)
        assert result.status_code == 200 and result.json()['status'] == 'succeeded', result.text
        assert confirm(admin, action).json() == result.json()
        item = {**item, 'name': 'Узел подпитки', 'location': 'Пост 7', 'revision': item['revision'] + 1}
    assert admin.get(endpoint).json() == item


def test_quoted_commands_and_net_new_asset_references_are_not_executable():
    question = 'В инструкции есть «Измени название ВТ-42 на Основной блок». Перескажи указание.'
    (goal, meta), = compile_results(question, explicit_results(question).results, 'equipment_edit')
    assert not goal['tool'] and meta['intent'] == 'quoted_command'
    assert 'ВТ-42' in meta['block']
    assert not may_offer_legacy('equipment_edit', question)


@pytest.mark.parametrize('recovers', [True, False])
def test_transient_read_failure_retries_same_arguments_at_most_once(monkeypatch, recovers):
    from app.assistant import read_transport

    tool = SimpleNamespace(name='task_read', mode='read', method='GET')
    args = {'path': {'task_id': str(uuid4())}}
    calls, trace = [], []
    monkeypatch.setattr(read_transport, 'validate_arguments', lambda app, tool, value: value)

    async def read_once(app, tool, value, headers):
        calls.append(value)
        if len(calls) == 1 or not recovers:
            raise HTTPException(503, 'Temporary backend outage')
        return {'task': {'id': value['path']['task_id']}}

    monkeypatch.setattr(read_transport, 'invoke', read_once)
    if recovers:
        returned, result = asyncio.run(read_transport.read(None, tool, args, {}, trace, retry_temporary=True))
        assert returned == args and result['task']['id'] == args['path']['task_id']
    else:
        with pytest.raises(HTTPException) as failure:
            asyncio.run(read_transport.read(None, tool, args, {}, trace, retry_temporary=True))
        assert failure.value.status_code == 503
    assert calls == [args, args]
    assert [entry['retry_count'] for entry in trace] == [0, 1]


def test_chat_reads_authoritative_record_after_transient_backend_error(runtime, monkeypatch):
    from app.assistant import read_transport

    _, app = runtime
    identity = str(demo_id('equipment-2'))
    path = '/api/v1/maintenance/equipment/' + identity
    original = read_transport.invoke
    seen = []

    async def transient(app, tool, args, headers):
        if tool.name == 'equipment_read':
            seen.append(args['path']['equipment_id'])
            if len(seen) == 1:
                raise HTTPException(503, 'Test backend outage')
        return await original(app, tool, args, headers)

    class Provider:
        supports_semantic_plan = True

        def chat(self, messages, schema, budget):
            return RequestedResults(results=[RequestedResult(intent='equipment_details', subjects=[identity])])

    monkeypatch.setattr(read_transport, 'invoke', transient)
    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with login(app, 'chief_engineer') as client:
        response = client.get(path)
        assert response.status_code == 200, response.text
        item = response.json()
        chat = thread(client)
        try:
            sent = client.post(f'{B}/conversations/{chat}/messages',
                               json={'content': f'Из equipment_id={identity} выпиши только название.',
                                     'idempotency_key': str(uuid4())})
            assert sent.status_code == 202, sent.text
            saved = client.get(f'{B}/conversations/{chat}').json()
            turn = saved['turns'][-1]
            assert turn['answer'] == f'Название: {item["name"]}'
            assert seen == [identity, identity]
            assert [attempt['status'] for attempt in turn['trace'][0]['attempts']] == ['denied', 'completed']
            assert not saved['actions'] and client.get(path).json() == item
        finally:
            client.delete(f'{B}/conversations/{chat}')
