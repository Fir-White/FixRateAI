"""Actual loopback HTTP to distinct API processes sharing a disposable DB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
from tempfile import gettempdir
from time import monotonic, sleep
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url

from agent_reliability_lab.evals.test_action_lifecycle import event_counts, order
from agent_reliability_lab.evals.test_agent_v3_e2e import lab
from scripts.verify import unused_port
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@contextmanager
def api_process(name):
    dsn = make_url(os.environ['INTEGRATION_DATABASE_URL'])
    assert dsn.host == '127.0.0.1' and dsn.database == 'fixrate_test_runtime'
    output = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT']) / 'wire'
    output.mkdir(parents=True, exist_ok=True)
    port = unused_port()
    address = f'http://127.0.0.1:{port}'
    env = dict(os.environ, DATABASE_URL=dsn.render_as_string(hide_password=False),
               FIXRATE_ASSISTANT_AGENT_VERSION='v3', OPTIMIZATION_WORKER='false', MAINTENANCE_SCHEDULER='false')
    command = [sys.executable, '-B', '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
               '--host', '127.0.0.1', '--port', str(port)]
    hidden = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    with (output/f'{name}.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, **hidden)
        try:
            with httpx.Client(base_url=address, trust_env=False) as probe:
                deadline = monotonic()+40
                while monotonic() < deadline:
                    assert server.poll() is None, f'{name} exited before readiness'
                    try:
                        if probe.get('/api/health', timeout=1).is_success:
                            break
                    except httpx.TransportError:
                        pass
                    sleep(.2)
                else:
                    pytest.fail(f'{name} failed readiness')
            yield address, server.pid
        finally:
            if server.poll() is None:
                server.terminate()
                server.wait(timeout=10)


def prepare(client, task):
    thread = client.post(f'{B}/conversations', json={'agent': 'assistant'})
    assert thread.status_code == 201
    identity = thread.json()['conversation_id']
    message = client.post(f'{B}/conversations/{identity}/messages', json={
        'content': f'Отмени задание {task}, причина: сняли работу из тестового графика.',
        'attachment_ids': [], 'idempotency_key': str(uuid4()),
    })
    assert message.status_code == 202
    deadline = monotonic()+25
    while monotonic() < deadline:
        response = client.get(f'{B}/conversations/{identity}')
        assert response.status_code == 200
        data = response.json()
        if data['turns'][0]['status'] != 'running':
            assert data['turns'][0]['execution_engine'] == 'v3'
            assert data['turns'][0]['workflow']['outcome'] == 'awaiting_confirmation'
            proposal, = data['actions']
            return proposal
        sleep(.2)
    pytest.fail('No proposal before the read deadline')


def sign_in(client, marker):
    response = client.post('/api/v1/auth/login', json={
        'email': f'chief-{marker}@example.test', 'password': os.environ['FIXRATE_TEST_PASSWORD'],
    })
    assert response.status_code == 200
    client.headers['X-CSRF-Token'] = response.json()['csrfToken']


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('mode', ['parallel', 'lost-response'])
def test_process_boundary_does_not_dispatch_twice(lab, mode):
    fixture, _, _, _, data, _, _ = lab
    engine, _, _, _, ids = fixture
    task = next(row['id'] for row in data['work'].values()
                if row['snapshot'].get('title') == 'Проверить резервную индикацию')
    before = order(engine, task)
    with api_process(f'{mode}-first') as (first, first_pid), api_process(f'{mode}-other') as (other, other_pid):
        assert first_pid != other_pid
        with httpx.Client(base_url=first, trust_env=False) as client:
            sign_in(client, ids['marker'])
            action = prepare(client, task)
            assert order(engine, task) == before
            endpoint = f'{B}/actions/{action["action_id"]}/confirm'
            payload = {'confirmed': True, 'payload_sha256': action['payload_sha256']}
            with httpx.Client(base_url=other, trust_env=False, cookies=client.cookies, headers=client.headers) as peer:
                if mode == 'parallel':
                    with ThreadPoolExecutor(max_workers=2) as workers:
                        calls = [workers.submit(session.post, endpoint, json=payload) for session in (client, peer)]
                        assert all(call.result(timeout=15).status_code == 200 for call in calls)
                else:
                    with client.stream('POST', endpoint, json=payload) as incomplete:
                        assert incomplete.status_code == 200
                assert peer.post(endpoint, json=payload).json()['status'] == 'succeeded'
    assert order(engine, task) == ('cancelled', before.revision+1)
    assert event_counts(engine, action['action_id']) == {'proposed': 1, 'confirmed': 1, 'succeeded': 1}


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
def test_process_restart_recovers_pending_confirmation(lab):
    fixture, _, _, _, data, _, _ = lab
    engine, _, _, _, ids = fixture
    task = next(row['id'] for row in data['work'].values()
                if row['snapshot'].get('title') == 'Проверить резервную индикацию')
    before = order(engine, task)
    with api_process('restart-preparation') as (address, first_pid), httpx.Client(base_url=address, trust_env=False) as client:
        sign_in(client, ids['marker'])
        action = prepare(client, task)
        cookies, headers = httpx.Cookies(client.cookies), httpx.Headers(client.headers)
    assert order(engine, task) == before
    with api_process('restart-confirmation') as (address, pid), httpx.Client(
            base_url=address, cookies=cookies, headers=headers, trust_env=False) as restored:
        assert first_pid != pid
        endpoint = f'{B}/actions/{action["action_id"]}/confirm'
        payload = {'confirmed': True, 'payload_sha256': action['payload_sha256']}
        response = restored.post(endpoint, json=payload)
        assert response.status_code == 200 and response.json()['status'] == 'succeeded'
        assert restored.post(endpoint, json=payload).json() == response.json()
    assert order(engine, task) == ('cancelled', before.revision+1)
    assert event_counts(engine, action['action_id']) == {'proposed': 1, 'confirmed': 1, 'succeeded': 1}


@contextmanager
def database_disconnect():
    target = make_url(os.environ['INTEGRATION_DATABASE_URL'])
    assert target.host == '127.0.0.1' and target.database == 'fixrate_test_runtime'
    admin = target.set(drivername='postgresql', database='postgres')
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as db:
        directory = Path(db.execute("SELECT current_setting('data_directory')").fetchone()[0]).resolve()
        assert directory.parent.parent == Path(gettempdir()).resolve() and directory.parent.name.startswith('fixrate-verify-')
        # Database DDL does not support server-side bind parameters.
        switch = sql.SQL('ALTER DATABASE {} WITH ALLOW_CONNECTIONS {}')
        db.execute(switch.format(sql.Identifier(target.database), sql.SQL('false')))
        try:
            db.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s', (target.database,)).fetchall()
            yield
        finally:
            db.execute(switch.format(sql.Identifier(target.database), sql.SQL('true')))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
def test_database_disconnect_does_not_lose_saved_chat(lab):
    fixture, _, _, _, _, _, _ = lab
    _, _, _, _, ids = fixture
    with api_process('database-disconnect') as (address, _), httpx.Client(base_url=address, trust_env=False) as client:
        sign_in(client, ids['marker'])
        before = checksums(fixture)
        created = client.post(f'{B}/conversations', json={'agent': 'assistant'})
        assert created.status_code == 201
        chat = created.json()['conversation_id']
        with database_disconnect():
            unavailable = client.get(f'{B}/conversations/{chat}')
            assert unavailable.status_code == 503
        response = client.get(f'{B}/conversations/{chat}')
        assert response.status_code == 200 and response.json()['conversation']['conversation_id'] == chat
        assert checksums(fixture) == before
