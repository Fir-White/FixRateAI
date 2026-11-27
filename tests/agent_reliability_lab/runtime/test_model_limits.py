"""Fault the model transport, then recover the conversation on real Ollama."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from threading import Thread

import pytest

from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@contextmanager
def interrupted_model(fault):
    model = os.environ['OLLAMA_CHAT_MODEL']
    digest = os.environ['OLLAMA_CHAT_DIGEST']
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def reply(self, status, payload):
            data = json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            assert self.path == '/api/tags'
            self.reply(200, {'models': [{'name': model, 'digest': digest}]})

        def do_POST(self):
            assert self.path == '/api/chat'
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(request['options']['num_predict'])
            if fault == 'generation-limit':
                self.reply(200, {'model': model, 'message': {'content': '{'}, 'done': True, 'done_reason': 'length'})
            else:
                self.reply(503, {'error': 'Temporary laboratory provider outage'})

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', requests
        finally:
            server.shutdown()
            worker.join(timeout=5)


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('fault', ['generation-limit', 'provider-503'])
def test_recovers_model_after_failure(lab, fault, monkeypatch):
    fixture, _, _, _, data, _, clients = lab
    chief = clients['chief_engineer']
    card = data['equipment']['КА-21']
    before = checksums(fixture)
    prompt = 'Сверь состояние, точное название и место установки КА-21 с карточкой. Укажи источник.'
    with interrupted_model(fault) as (address, requests), monkeypatch.context() as broken:
        broken.setenv('OLLAMA_CHAT_BASE_URL', address)
        failed, actions, chat = turn(chief, prompt)
    assert failed['status'] == 'failed' and failed['execution_engine'] == 'v3' and not actions
    assert failed['error_code'] == ('OLLAMA_INVALID_RESPONSE' if fault == 'generation-limit' else 'OLLAMA_UNAVAILABLE')
    assert 1 <= len(requests) <= 6 and all(0 < limit <= 7000 for limit in requests)
    assert card['id'] not in failed['answer'] and checksums(fixture) == before
    if fault == 'generation-limit':
        assert len(requests) >= 2 and requests[1] > requests[0]

    recovered, actions, _ = turn(chief, prompt, chat=chat)
    assert recovered['status'] == 'completed' and recovered['execution_engine'] == 'v3' and not actions
    assert all(value in recovered['answer'] for value in (card['name'], card['location'], 'в эксплуатации', 'equipment_read'))
    assert stored(fixture, recovered['turn_id'])['metrics']['llm_calls'] > 0
    assert checksums(fixture) == before


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
def test_constrained_real_model_preserves_confirmed_facts(lab, monkeypatch, caplog):
    import logging

    fixture, _, _, _, data, _, clients = lab
    card = data['equipment']['КА-21']
    before = checksums(fixture)
    caplog.set_level(logging.INFO, logger='app.assistant.service')
    monkeypatch.setenv('OLLAMA_CHAT_NUM_CTX', '4096')
    background = ('Контрольный фон из синтетического журнала. Смена завершила обход площадки. '
                  'Сведения об оборудовании в журнале отсутствуют. Далее записаны общие сведения о погоде. ')
    request = 'Сверь КА-21 с карточкой и приведи UUID, название, состояние и место установки с источником. '
    result, actions, _ = turn(clients['chief_engineer'], request + background * 66)
    assert result['execution_engine'] == 'v3' and not actions
    assert any(f'assistant_graph_inference_start turn={result["turn_id"]} ' in record.getMessage() for record in caplog.records)
    state = stored(fixture, result['turn_id']) or {}
    answer = result['answer']
    if result['status'] == 'completed' and state.get('outcome') == 'completed':
        assert all(value in answer for value in (card['id'], card['name'], card['location'], 'equipment_read'))
    else:
        assert result['status'] == 'failed' or state.get('outcome') in ('blocked', 'partial'), answer
        assert 'оборудование проверено' not in answer.casefold()
    assert checksums(fixture) == before
