"""Run agent checks on fresh PostgreSQL with installed local Ollama only.

No .env is read, no live preference is changed, and no model is pulled. A
process-tree Python audit hook blocks external network destinations even if a
test/provider tries cloud fallback or restores a credential. Existing verify.py
owns disposable databases and cleanup; this wrapper owns inference policy and
reproducible source/model provenance.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = [
    'tests/backend/test_agent_redteam_live.py::test_real_model_agent_episode[A-equipment]',
    'tests/backend/test_agent_redteam_live.py::test_real_model_agent_episode[A-regulations]',
    'tests/backend/test_agent_redteam_live.py::test_real_model_agent_episode[A-card-date]',
    'tests/backend/test_agent_redteam_live.py::test_real_model_agent_episode[F-linked-context]',
    'tests/backend/test_agent_redteam_live.py::test_real_model_agent_episode[E-full-count-beyond-page]',
    'tests/backend/test_agent_redteam_live.py::test_real_model_agent_episode[K-propose-confirm-replay]',
]

# Loaded in every Python child, including when verify.py replaces PYTHONPATH.
# This file stays within ignored artifacts, never in site-packages or a user's
# environment. Popen's environment forwarding preserves the guard in descendants.
LOCAL_GUARD = r'''
import ipaddress, os, subprocess, sys
from urllib.parse import urlsplit
_ALLOW_INFERENCE = os.environ.get('FIXRATE_LOCAL_INFERENCE_ALLOWED') == '1'

def _local(host):
    if host is None or host == '': return True
    if isinstance(host, bytes): host = host.decode('ascii', 'strict')
    if str(host).lower().rstrip('.') == 'localhost': return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or bool(getattr(address, 'ipv4_mapped', None) and address.ipv4_mapped.is_loopback)
    except ValueError: return False

def _audit(event, args):
    if event in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'):
        if not _local(args[0]): raise PermissionError('FIXRATE_EXTERNAL_NETWORK_DENIED')
    elif event in ('socket.connect', 'socket.sendto'):
        address = args[-1]
        if isinstance(address, tuple) and not _local(address[0]):
            raise PermissionError('FIXRATE_EXTERNAL_NETWORK_DENIED')
sys.addaudithook(_audit)

def _ollama_path(url):
    parsed = urlsplit(str(url))
    if _local(parsed.hostname) and parsed.port == 11434:
        if parsed.path not in ('/api/tags', '/api/show', '/api/chat'):
            raise PermissionError('FIXRATE_OLLAMA_MODEL_MUTATION_DENIED')
        if parsed.path == '/api/chat' and not _ALLOW_INFERENCE:
            raise PermissionError('FIXRATE_GENERATION_DISABLED')

import urllib.request
_open = urllib.request.OpenerDirector.open
def _guard_open(self, fullurl, *args, **kwargs):
    _ollama_path(fullurl.full_url if hasattr(fullurl, 'full_url') else fullurl)
    return _open(self, fullurl, *args, **kwargs)
urllib.request.OpenerDirector.open = _guard_open

# requests uses http.client; httpx is covered separately when installed. Internal
# ASGI testserver URLs remain valid because only real socket traffic is denied.
import http.client
_putrequest = http.client.HTTPConnection.putrequest
def _guard_putrequest(self, method, url, *args, **kwargs):
    if _local(self.host) and self.port == 11434:
        _ollama_path('http://localhost:11434' + url)
    return _putrequest(self, method, url, *args, **kwargs)
http.client.HTTPConnection.putrequest = _guard_putrequest
try:
    import httpx
    _send = httpx.Client.send
    _asend = httpx.AsyncClient.send
    def _guard_send(self, request, *args, **kwargs):
        _ollama_path(request.url)
        return _send(self, request, *args, **kwargs)
    async def _guard_asend(self, request, *args, **kwargs):
        _ollama_path(request.url)
        return await _asend(self, request, *args, **kwargs)
    httpx.Client.send = _guard_send
    httpx.AsyncClient.send = _guard_asend
except ImportError: pass

_Popen = subprocess.Popen
class _GuardedPopen(_Popen):
    def __init__(self, *args, **kwargs):
        variables = dict(kwargs.get('env') or os.environ)
        guard = os.environ['FIXRATE_LOCAL_GUARD_DIRECTORY']
        paths = [guard, *[p for p in variables.get('PYTHONPATH', '').split(os.pathsep) if p and p != guard]]
        variables.update(PYTHONPATH=os.pathsep.join(paths), FIXRATE_LOCAL_GUARD_DIRECTORY=guard,
                         FIXRATE_LLM_LOCAL_ONLY='1', FIXRATE_LOCAL_INFERENCE_ALLOWED='1' if _ALLOW_INFERENCE else '0')
        kwargs['env'] = variables
        super().__init__(*args, **kwargs)
subprocess.Popen = _GuardedPopen
'''


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Local Ollama discovery refuses redirects')


def installed_model(model: str | None = None) -> dict[str, str]:
    """Read actual local metadata; never infer installation from a known tag."""
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def read(path, body=None):
        request = Request('http://127.0.0.1:11434' + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=10) as response:
            raw = response.read(2_097_153)
        if len(raw) > 2_097_152:
            raise ValueError('Local model metadata exceeds the limit')
        return json.loads(raw)

    tags = read('/api/tags')
    models = tags.get('models') if isinstance(tags, dict) else None
    if not isinstance(models, list):
        raise ValueError('Invalid local Ollama model catalog')
    candidates = [row for row in models if isinstance(row, dict)
                  and not row.get('remote_model') and not row.get('remote_host')
                  and isinstance(row.get('name'), str) and 'cloud' not in row['name'].casefold()]
    selected = next((row for row in candidates if row['name'] == model), None) if model else next(
        (row for row in candidates if row['name'] == 'qwen3.5:4b-q4_K_M'), candidates[0] if candidates else None)
    if selected is None:
        raise ValueError('Requested local model is not installed; automatic downloads are prohibited')
    name, digest = selected['name'], str(selected.get('digest', '')).removeprefix('sha256:')
    if not re.fullmatch(r'[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+', name) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Local model tag/digest is invalid')
    info = read('/api/show', dict(model=name))
    if not isinstance(info, dict) or info.get('remote_model') or info.get('remote_host') or 'completion' not in info.get('capabilities', []):
        raise ValueError('Installed model does not advertise local completion capability')
    return dict(provider='ollama', base_url='http://127.0.0.1:11434', model=name, digest='sha256:' + digest)


def environment(parent: dict[str, str], guard_directory: Path, model: dict[str, str], *, live: bool) -> dict[str, str]:
    """Build a process-local environment; caller settings and files stay intact."""
    variables = dict(parent)
    for key in list(variables):
        upper = key.upper()
        if upper in ('DATABASE_URL', 'TEST_DATABASE_URL', 'INTEGRATION_DATABASE_URL', 'FIXRATE_LIVE_PROVIDER_FILE') or any(
            token in upper for token in ('API_KEY', 'API_TOKEN', 'AITUNNEL', 'AI_TUNNEL', 'OPENAI', 'ANTHROPIC',
                                         'GEMINI', 'GOOGLE_API', 'HUGGING_FACE_HUB_TOKEN', 'HF_TOKEN')):
            variables.pop(key)
    variables.update(
        PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
        PYTHONPYCACHEPREFIX=str(guard_directory / 'bytecode'),
        PYTHONPATH=os.pathsep.join([str(guard_directory), variables.get('PYTHONPATH', '')]),
        FIXRATE_LOCAL_GUARD_DIRECTORY=str(guard_directory), FIXRATE_LLM_LOCAL_ONLY='1',
        FIXRATE_LOCAL_INFERENCE_ALLOWED='1' if live else '0',
        ASSISTANT_PROVIDER='ollama', OLLAMA_CHAT_BASE_URL=model['base_url'],
        OLLAMA_CHAT_MODEL=model['model'], OLLAMA_CHAT_DIGEST=model['digest'],
        OLLAMA_CHAT_TIMEOUT_SECONDS='180' if live else '240', OLLAMA_CHAT_NUM_CTX='32768',
        PHOTO_REVIEW_PROVIDER='clip', FORECAST_PROVIDER='rf',
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1',
        FIXRATE_AGENT_LIVE='1' if live else '0', FIXRATE_SCENARIOS_LIVE='0',
    )
    return variables


def source_manifest(root: Path) -> dict:
    # The sandbox may read an owner-created worktree through another OS account.
    # Scope the trust exception to this read-only invocation, never global Git.
    git = ['git', '-c', 'safe.directory=' + root.as_posix()]
    paths = subprocess.check_output([*git, 'ls-files', '-co', '--exclude-standard', '-z'], cwd=root).decode('utf-8').split('\0')
    entries = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
               for name in sorted(set(paths)) if (name.startswith(('backend/', 'ml_service/', 'scripts/', 'tests/', 'contracts/', 'database/',
                                                                   'agent_reliability_lab/evals/', 'agent_reliability_lab/acceptance/'))
               or name in ('pytest.ini', 'requirements.txt', 'requirements-solver.txt')) and (root / name).is_file()}
    return dict(head=subprocess.check_output([*git, 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                sha256=hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest(), files=entries)


def corpus_manifest(root: Path, targets: list[str]) -> dict[str, str]:
    """Hash external test files too when the same corpus runs against baseline."""
    entries = {}
    for target in targets:
        path = Path(target.split('::', 1)[0])
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if path.is_file():
            entries[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            for source in sorted(path.rglob('test_*.py')):
                entries[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    return entries


def validate_legacy_model_pin(root: Path, targets: list[str], model: dict[str, str]) -> None:
    """Refuse misleading provenance when older live fixtures pin their own model."""
    legacy = {'test_agent_redteam_live.py', 'test_agent_redteam_live_mutations.py',
              'test_assistant_orchestrator_live.py'}
    if not any(Path(target.split('::', 1)[0]).name in legacy or
               (root / target.split('::', 1)[0]).is_dir() for target in targets):
        return
    source = root / 'tests/backend/test_agent_redteam_live.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'dict':
            continue
        values = {kw.arg: kw.value.value for kw in node.keywords if isinstance(kw.value, ast.Constant)}
        if 'OLLAMA_CHAT_MODEL' in values and 'OLLAMA_CHAT_DIGEST' in values:
            if (values['OLLAMA_CHAT_MODEL'], values['OLLAMA_CHAT_DIGEST']) != (model['model'], model['digest']):
                raise ValueError('Selected installed model differs from the legacy corpus pin; update its shared live fixture before comparing models')
            return
    raise ValueError('Cannot verify the legacy live corpus model pin')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT, help='Baseline or changed worktree; no source files are modified')
    parser.add_argument('--pg-bin', type=Path, default=Path('C:/Program Files/PostgreSQL/18/bin') if os.name == 'nt' else Path('/usr/lib/postgresql/16/bin'))
    parser.add_argument('--model', help='Exact installed local tag; omission prefers installed Qwen 4B')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--live', action='store_true', help='Enable real inference; default is deterministic regression')
    parser.add_argument('--check-only', action='store_true', help='Discover metadata and validate network policy without inference or PostgreSQL')
    parser.add_argument('--pytest-target', nargs='+', help='Selected pytest nodes; absolute test paths permit the same corpus against baseline')
    args = parser.parse_args(argv)
    root = args.source_root.resolve()
    if not (root / 'scripts/verify.py').is_file():
        parser.error('source-root must contain the existing disposable verification runner')
    output = (args.output or root / 'reports' / ('agent-local-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve()
    if not output.is_relative_to(root / 'reports'):
        parser.error('Output must remain below the selected worktree reports/')
    output.mkdir(parents=True, exist_ok=False)
    guard = output / 'policy'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text(LOCAL_GUARD, encoding='utf-8')
    model = installed_model(args.model)
    variables = environment(dict(os.environ), guard, model, live=args.live)
    # An absolute corpus file in another worktree must not cause pytest to load
    # that worktree's config/pythonpath and mix changed code with baseline SQL.
    variables['PYTEST_ADDOPTS'] = shlex.join(['-c', str(root / 'pytest.ini'), '--rootdir', str(root)])
    variables['FIXRATE_VERIFICATION_SOURCE_ROOT'] = str(root)
    # A real child process validates policy inheritance; no external packet is sent.
    probe = "import socket; socket.create_connection(('203.0.113.1',443),timeout=.1)"
    checked = subprocess.run([sys.executable, '-c', probe], env=variables, capture_output=True, text=True)
    if checked.returncode == 0 or 'FIXRATE_EXTERNAL_NETWORK_DENIED' not in checked.stderr:
        raise RuntimeError('Local-only child network policy did not activate')
    before = source_manifest(root)
    targets = args.pytest_target or (DEFAULT_TARGETS if args.live else ['tests/backend/test_assistant.py'])
    if args.live:
        validate_legacy_model_pin(root, targets, model)
    corpus = corpus_manifest(root, targets)
    dependencies={}
    for package in ('pytest','fastapi','pydantic','sqlalchemy','httpx','numpy','ortools'):
        try:dependencies[package]=version(package)
        except PackageNotFoundError:dependencies[package]=None
    manifest = dict(source_root=str(root), source_head=before['head'], source_sha256=before['sha256'],
                    python_version=sys.version,dependencies=dependencies,
                    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), corpus_files=corpus,
                    model=model, local_network_guard=True, environment_files_read=False,
                    automatic_downloads=False, live=args.live, check_only=args.check_only,
                    inference_allowed=args.live,
                    targets=targets,
                    started_at=datetime.now(timezone.utc).isoformat())
    (output / 'provenance.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'source-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    if args.check_only:
        print(json.dumps(dict(output=str(output), model=model, policy='verified', inference_requests=0), indent=2))
        return 0
    command = [sys.executable, '-B', str(root / 'scripts/verify.py'), '--pg-bin', str(args.pg_bin),
               '--agent-only', '--output', str(output / 'run'), '--pytest-target', *manifest['targets']]
    started = time.monotonic()
    print(f"Local-only verification: {root}; installed model {model['model']}; artifacts {output}", flush=True)
    with (output / 'runner.log').open('w', encoding='utf-8') as log:
        done = subprocess.run(command, cwd=root, env=variables, stdout=log, stderr=subprocess.STDOUT)
    after = source_manifest(root)
    (output / 'source-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    summary = dict(exit_code=done.returncode, source_stable=before['sha256'] == after['sha256'],
                   corpus_stable=corpus == corpus_manifest(root, targets),
                   seconds=round(time.monotonic() - started, 3), live=args.live,
                   completed_at=datetime.now(timezone.utc).isoformat())
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
    return done.returncode or (0 if summary['source_stable'] and summary['corpus_stable'] else 2)


if __name__ == '__main__':
    raise SystemExit(main())
