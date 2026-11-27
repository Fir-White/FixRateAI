"""Start the actual built SPA, using only the runner's disposable database."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

import pytest
from sqlalchemy import text

from app.integration.demo import demo_id
from tests.backend.test_runtime_integration import runtime


@pytest.mark.skipif(os.getenv('FIXRATE_AGENT_LIVE') != '1' or os.getenv('FIXRATE_TOOL_AGENT_BROWSER') != '1',
                    reason='Opt-in local v4 UI verification')
def test_real_tool_agent_in_built_spa(runtime):
    engine, _ = runtime
    assert engine.url.host == '127.0.0.1' and engine.url.database.startswith('fixrate_test_')
    with engine.begin() as db:
        task = db.execute(text("""UPDATE work_orders w
            SET planned_start_at=timezone(s.timezone,e.planned_date+time '10:00'),
                planned_end_at=timezone(s.timezone,e.planned_date+time '12:00')
            FROM sites s,schedule_entries e WHERE w.work_order_id=:id
            AND w.site_id=s.site_id AND w.schedule_entry_id=e.schedule_entry_id
            AND timezone(s.timezone,e.planned_date+time '12:00') <= w.regulatory_deadline_at
            RETURNING w.work_order_id"""), {'id': demo_id('assignment-order')}).scalar_one()
    root = Path(__file__).resolve().parents[3]
    assert (root / 'frontend/dist/index.html').exists(), 'Build the production SPA first'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, DATABASE_URL=engine.url.render_as_string(hide_password=False),
               FIXRATE_ASSISTANT_AGENT_VERSION='v4', FIXRATE_ASSISTANT_V3_PIPELINE='v3',
               OPTIMIZATION_WORKER='false', MAINTENANCE_SCHEDULER='false', FIXRATE_BASE_URL=base,
               FIXRATE_TEST_ASSIGNMENT_ORDER=str(task))
    output = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT']) / 'v4-browser'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'uvicorn.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
            '127.0.0.1', '--port', str(port), '--no-access-log'], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            ready = threading.Event()
            while time.monotonic() < deadline and server.poll() is None:
                try:
                    with urlopen(base + '/api/health', timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    ready.wait(.2)
            else:
                pytest.fail('Disposable v4 runtime failed to start; see uvicorn.log')
            checked = subprocess.run(['node', 'node_modules/@playwright/test/cli.js', 'test',
                'assistant-tool-agent-v4.spec.ts', '--output', str(output / 'playwright')],
                cwd=root / 'frontend', env=env, capture_output=True, timeout=460)
            report = checked.stdout + checked.stderr
            (output / 'playwright.log').write_bytes(report)
            assert checked.returncode == 0, report.decode('utf-8', errors='replace')
        finally:
            server.terminate()
            server.wait(timeout=15)
