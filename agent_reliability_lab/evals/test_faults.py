"""Dependency fault injection through the ordinary assistant HTTP entry point."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from threading import Thread

from fastapi import HTTPException
import pytest

from app.assistant import read_transport
from agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@contextmanager
def malformed_provider():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def send_bytes(self, data):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            assert self.path == '/api/tags'
            self.send_bytes(json.dumps({'models': [{'name': os.environ['OLLAMA_CHAT_MODEL'],
                                                    'digest': os.environ['OLLAMA_CHAT_DIGEST']}]}).encode())

        def do_POST(self):
            assert self.path == '/api/chat'
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_bytes(b'{incomplete response')

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            worker.join(timeout=5)


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
def test_invalid_provider_json_does_not_deliver_or_write(lab, monkeypatch):
    fixture, _, _, _, data, _, sessions = lab
    chief = sessions['chief_engineer']
    before = checksums(fixture)
    with malformed_provider() as endpoint:
        monkeypatch.setenv('OLLAMA_CHAT_BASE_URL', endpoint)
        result, actions, _ = turn(chief, 'Сверь КА-21 с карточкой. Выпиши её состояние и точное место установки.')
    assert result['execution_engine'] == 'v3' and result['status'] == 'failed', result
    assert result['error_code'] == 'OLLAMA_INVALID_RESPONSE'
    assert data['equipment']['КА-21']['id'] not in result['answer']
    assert not actions and checksums(fixture) == before


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('recover', [False, True], ids=['persistent-503', 'transient-503'])
def test_equipment_unavailability_is_bounded(lab, recover, monkeypatch):
    fixture, _, _, _, data, _, sessions = lab
    chief = sessions['chief_engineer']
    original = read_transport.invoke
    failures = 0

    async def unavailable(app, tool, arguments, headers):
        nonlocal failures
        if tool.name == 'equipment_read' and (not recover or failures == 0):
            failures += 1
            raise HTTPException(503, 'Синтетический сбой чтения')
        return await original(app, tool, arguments, headers)

    before = checksums(fixture)
    monkeypatch.setattr(read_transport, 'invoke', unavailable)
    result, actions, _ = turn(chief, 'Открой карточку КА-21.')
    assert result['execution_engine'] == 'v3' and result['status'] == 'completed', result
    reads = [attempt for entry in result['trace'] if entry['tool'] == 'equipment_read'
             for attempt in entry['attempts']]
    assert not actions and checksums(fixture) == before
    assert reads[0]['status'] == 'denied' and reads[0]['code'] == 503
    assert len(reads) == 2
    if recover:
        assert reads[-1]['status'] == 'completed' and result['workflow']['outcome'] == 'completed', result
        assert data['equipment']['КА-21']['id'] in result['answer']
    else:
        assert result['workflow']['outcome'] in ('partial', 'blocked'), result
        assert data['equipment']['КА-21']['name'] not in result['answer']
        assert 'не найден' not in result['answer'].casefold()
