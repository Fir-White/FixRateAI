"""Natural held-out conversations on synthetic PostgreSQL and real Ollama."""
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from PIL import Image, ImageDraw
import pytest
from sqlalchemy import text

from agent_reliability_lab.evals.test_agent_v3_e2e import lab
from agent_reliability_lab.evals.test_maintenance_conversation import schedule
from tests.backend.test_assistant import B, assistant_case, confirm, thread
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


pytestmark = pytest.mark.skipif(os.getenv('FIXRATE_AGENT_LIVE') != '1', reason='Explicit real-model local profile')


@pytest.fixture
def v4(lab, monkeypatch):
    fixture, _, _, _, _, _, clients = lab
    engine, app, *_ = fixture
    monkeypatch.setattr(app.state, 'settings', replace(app.state.settings, assistant_agent_version='v4', assistant_v3_pipeline='v3'))
    assert not hasattr(app.state, 'assistant_provider_factory')
    return engine, clients, lab


def exercise(v4, case, role, prompts, *, photo=None, subject=None):
    engine, clients, _ = v4
    client = clients[role]
    if subject:
        created = client.post(f'{B}/conversations', json={'subject_task_id': subject})
        assert created.status_code == 201, created.text
        chat = created.json()['conversation_id']
    else:
        chat = thread(client)
    records = []
    path = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT']) / 'tool-agent-v4' / (case + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    for i, prompt in enumerate(prompts):
        attachments = []
        if photo is not None and i == len(prompts)-1:
            uploaded = client.post(f'{B}/conversations/{chat}/attachments', files={'file': ('work.png', photo, 'image/png')})
            assert uploaded.status_code == 201, uploaded.text
            attachments.append(uploaded.json()['attachment_id'])
        start = perf_counter()
        posted = client.post(f'{B}/conversations/{chat}/messages', json=dict(content=prompt, idempotency_key=str(uuid4()),
                             attachment_ids=attachments))
        assert posted.status_code == 202, posted.text
        payload = client.get(f'{B}/conversations/{chat}').json()
        result = next(x for x in payload['turns'] if x['turn_id'] == posted.json()['turn_id'])
        with engine.connect() as db:
            evidence = db.scalar(text('SELECT agent_context FROM assistant_turns WHERE turn_id=:id'), {'id': result['turn_id']})
        records.append(dict(question=prompt, answer=result['answer'], status=result['status'], error=result['error_code'],
                            model=result['model_ref'], seconds=round(perf_counter()-start, 3), trace=result['trace'],
                            evidence=evidence, cards=[dict(status=a['status'], tool=a['tool_name']) for a in payload['actions']]))
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        assert result['status'] == 'completed', records[-1]
        assert result['execution_engine'] == 'v4' and result['prompt_version'] == 'fixrate-tool-calling-v4'
        assert result['model_ref'].startswith('ollama:') and result['workflow'] is None
    return records, payload['actions']


def answers(records):
    return [row['answer'].casefold() for row in records]


def test_closest_and_next(v4):
    schedule(v4[2])
    records, cards = exercise(v4, 'next', 'engineer', [
        'Какое ближайшее ТО?', 'А какое после него?', 'А кто его выполняет?', 'Что мне с ним делать?'])
    first, second, third, fourth = answers(records)
    assert 'контроль уставок' in first and 'поздний осмотр' not in first
    assert 'поздний осмотр' in second
    assert 'не назнач' in third or 'нет исполнител' in third
    assert len(fourth) > 90 and not cards


def test_overdue_then_priority(v4):
    records, cards = exercise(v4, 'overdue', 'engineer', [
        'Что у нас вылетело по срокам?', 'Какую взять первой и почему?', 'Кто за неё отвечает?', 'Какой следующий шаг?'])
    first, second, third, fourth = answers(records)
    assert all(x in first for x in ('осмотр соединений', 'снять показания', 'маркировку'))
    assert 'осмотр соединений' in second and 'дн' in second
    assert len(third) > 35 and len(fourth) > 90 and not cards


def test_assignment_confirmation(v4):
    engine, clients, lab_data = v4
    task, _, _, worker = schedule(lab_data)
    records, cards = exercise(v4, 'assignment', 'engineer', [
        'Что завтра стоит без исполнителей?', 'Берём ближайшую. Кого лучше отправить?',
        'А чем он лучше остальных?', 'Назначь его.'])
    first, second, third, fourth = answers(records)
    assert len(cards) == 1 and cards[0]['status'] == 'proposed', fourth
    card = cards[0]
    assert card['arguments']['path']['task_id'] == task
    assert card['arguments']['body']['executor_ids'] == [str(worker)]
    q = text('SELECT status,revision FROM work_orders WHERE work_order_id=:id')
    with engine.connect() as db:
        before = db.execute(q, {'id': task}).one()
    assert before.status == 'draft'
    assert confirm(clients['executor'], card).status_code in (403, 404)
    for _ in range(2):
        result = confirm(clients['engineer'], card)
        assert result.status_code == 200 and result.json()['status'] == 'succeeded', result.text
    with engine.connect() as db:
        after = db.execute(q, {'id': task}).one()
        assert after.status == 'assigned' and after.revision == before.revision + 1
        assert db.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='assign'"), {'id': task}) == 1
    assert 'контроль уставок' in first and 'алексей' in second and 'нагруз' in third


def test_filter_continuation(v4):
    schedule(v4[2])
    records, cards = exercise(v4, 'filters', 'engineer', [
        'Покажи незавершённые работы на завтра', 'А на послезавтра?', 'Только те, где нет исполнителя', 'Покажи первую.'])
    first, second, third, fourth = answers(records)
    assert 'контроль уставок' in first and 'поздний осмотр' in second and 'поздний осмотр' in third and 'поздний осмотр' in fourth
    assert not cards


def test_executor_context(v4):
    engine, _, lab_data = v4
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders
            SET operation_snapshot=operation_snapshot||CAST(:requirements AS jsonb)
            WHERE site_id=:site AND operation_snapshot->>'title'='Сверить уставки защиты'"""),
            dict(lab_data[0][-1], requirements=json.dumps({
                'instructions': 'Сверить текущие настройки с паспортом.',
                'checklist': [{'text': 'Проверить показание контрольного индикатора', 'required': True}],
            }, ensure_ascii=False)))
    records, cards = exercise(v4, 'executor', 'executor', [
        'Какие у меня сегодня задания?', 'Что нужно сделать в первом?', 'Объясни простыми словами.',
        'А как проверить, что всё сделал правильно?'])
    first, second, third, fourth = answers(records)
    assert 'уставк' in first and 'маркировк' not in first
    assert 'паспорт' in second and len(third) > 35 and 'индикатор' in fourth and not cards


@pytest.mark.parametrize('variant', ('crack', 'clear', 'blurred'))
def test_visual_review_uses_real_pixels(v4, variant):
    image = Image.new('RGB', (512, 400), '#b6b6b6' if variant != 'blurred' else '#262626')
    if variant != 'blurred':
        draw = ImageDraw.Draw(image)
        draw.rectangle((45, 35, 465, 360), fill='#d4d4d4', outline='#525252', width=9)
        draw.ellipse((190, 136, 320, 266), fill='#e22119')
        if variant == 'crack':
            draw.line([(52, 46), (100, 114), (91, 178), (182, 220), (165, 308), (203, 354)], fill='#181818', width=13)
    blob = BytesIO()
    image.save(blob, 'PNG')
    with v4[0].connect() as db:
        subject = db.scalar(text("""SELECT work_order_id::text FROM work_orders
            WHERE site_id=:site AND operation_snapshot->>'title'='Сверить уставки защиты'"""), v4[2][0][-1])
    records, cards = exercise(v4, 'photo-'+variant, 'executor', ['Нормально сделал?'],
                              photo=blob.getvalue(), subject=subject)
    result = answers(records)[-1]
    assert not cards and len(result) > 120
    assert any(row.get('images') == 1 for row in records[-1]['trace'])
    if variant == 'crack':
        assert 'трещин' in result or 'чёрн' in result or 'черн' in result
    elif variant == 'clear':
        assert 'красн' in result and ('круг' in result or 'кнопк' in result or 'индикатор' in result)
    else:
        assert any(part in result for part in ('тёмн', 'темн', 'чёрн', 'черн', 'недостаточ', 'не видно'))
        assert 'не загруз' not in result


def test_conversation_stays_conversation(v4):
    records, cards = exercise(v4, 'social', 'engineer', [
        'Привет.', 'Спасибо.', 'Ты вообще не то понял.', 'Да блин, я про предыдущий наряд.', 'Пиздец.'])
    assert not cards
    assert all('эмоциональная поддержка' not in row['answer'].casefold() for row in records)
    assert all(not records[i]['evidence']['results'] for i in (0, 1, 2, 4))
