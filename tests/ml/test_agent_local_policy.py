"""Local evaluation isolation includes child processes and provider fallback."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.verify_agent_local import LOCAL_GUARD, corpus_manifest, environment, installed_model, validate_legacy_model_pin


MODEL = dict(provider='ollama', base_url='http://127.0.0.1:11434',
             model='installed:local', digest='sha256:' + 'a' * 64)


@pytest.fixture
def guarded(tmp_path):
    (tmp_path / 'sitecustomize.py').write_text(LOCAL_GUARD, encoding='utf-8')
    return environment(dict(os.environ), tmp_path, MODEL, live=True)


def test_policy_environment_does_not_inherit_secrets_or_database_urls(tmp_path):
    parent = dict(AITUNNEL_API_KEY='private', AI_TUNNEL_API_KEY='private', OPENAI_API_KEY='private',
                  ANTHROPIC_API_KEY='private', API_TOKEN='private', HF_TOKEN='private',
                  DATABASE_URL='postgresql://live', TEST_DATABASE_URL='postgresql://live',
                  INTEGRATION_DATABASE_URL='postgresql://live', ASSISTANT_PROVIDER='aitunnel', KEEP='yes')
    before = dict(parent)
    result = environment(parent, tmp_path, MODEL, live=True)
    assert parent == before
    assert not any(key in result for key in parent if key not in ('ASSISTANT_PROVIDER', 'KEEP'))
    assert result['ASSISTANT_PROVIDER'] == 'ollama' and result['KEEP'] == 'yes'
    assert result['FIXRATE_LLM_LOCAL_ONLY'] == result['HF_HUB_OFFLINE'] == '1'


def test_local_gpu_run_can_set_a_smaller_context_without_changing_the_model_pin(tmp_path):
    result = environment({}, tmp_path, MODEL, live=True, num_ctx=8192)
    assert result['OLLAMA_CHAT_NUM_CTX'] == '8192'
    assert result['OLLAMA_CHAT_DIGEST'] == MODEL['digest']
    assert result['FIXRATE_LOCAL_INFERENCE_ALLOWED'] == '1'


@pytest.mark.parametrize('code', [
    "import socket; socket.create_connection(('203.0.113.1',443),timeout=.1)",
    "import socket; socket.getaddrinfo('external.example',443)",
    "import socket; socket.socket(socket.AF_INET,socket.SOCK_DGRAM).sendto(b'x',('203.0.113.1',443))",
])
def test_external_destination_is_denied_before_network_io(guarded, code):
    result = subprocess.run([sys.executable, '-c', code], env=guarded, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'FIXRATE_EXTERNAL_NETWORK_DENIED' in result.stderr


def test_guard_survives_verify_style_pythonpath_replacement(guarded):
    child = "import socket; socket.create_connection(('203.0.113.1',443),timeout=.1)"
    code = ('import subprocess,sys,os; '
            "env=dict(os.environ,PYTHONPATH=''); "
            f'child=subprocess.run([sys.executable,"-c",{child!r}],env=env,capture_output=True,text=True); '
            'print(child.stderr); sys.exit(child.returncode)')
    result = subprocess.run([sys.executable, '-c', code], env=guarded, capture_output=True, text=True)
    assert result.returncode != 0 and 'FIXRATE_EXTERNAL_NETWORK_DENIED' in result.stdout


@pytest.mark.parametrize('transport', ['urllib', 'httpx'])
def test_local_ollama_download_endpoint_is_denied(guarded, transport):
    if transport == 'urllib':
        code = "from urllib.request import urlopen,Request; urlopen(Request('http://127.0.0.1:11434/api/pull',data=b'{}'))"
    else:
        code = "import httpx; httpx.post('http://127.0.0.1:11434/api/pull',json={})"
    result = subprocess.run([sys.executable, '-c', code], env=guarded, capture_output=True, text=True)
    assert result.returncode != 0 and 'FIXRATE_OLLAMA_MODEL_MUTATION_DENIED' in result.stderr


def test_cloud_keys_restored_in_child_do_not_allow_fallback(guarded):
    code = "import os,socket; os.environ['OPENAI_API_KEY']='restored'; socket.create_connection(('api.openai.com',443),timeout=.1)"
    result = subprocess.run([sys.executable, '-c', code], env=guarded, capture_output=True, text=True)
    assert result.returncode != 0 and 'FIXRATE_EXTERNAL_NETWORK_DENIED' in result.stderr


def test_loopback_dns_still_works(guarded):
    code = "import socket; print(bool(socket.getaddrinfo('localhost',11434)))"
    result = subprocess.run([sys.executable, '-c', code], env=guarded, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == 'True'


@pytest.mark.parametrize('transport', ['urllib', 'http_client', 'httpx'])
def test_no_live_profile_denies_real_generation_before_transport(guarded, transport):
    variables = {**guarded, 'FIXRATE_LOCAL_INFERENCE_ALLOWED': '0'}
    code = {
        'urllib': "from urllib.request import urlopen,Request; urlopen(Request('http://127.0.0.1:11434/api/chat',data=b'{}'))",
        'http_client': "from http.client import HTTPConnection; HTTPConnection('127.0.0.1',11434).putrequest('POST','/api/chat')",
        'httpx': "import httpx; httpx.post('http://127.0.0.1:11434/api/chat',json={})",
    }[transport]
    result = subprocess.run([sys.executable, '-c', code], env=variables, capture_output=True, text=True)
    assert result.returncode != 0 and 'FIXRATE_GENERATION_DISABLED' in result.stderr


def test_no_live_profile_keeps_read_only_model_metadata_available(guarded):
    variables = {**guarded, 'FIXRATE_LOCAL_INFERENCE_ALLOWED': '0'}
    code = ("from sitecustomize import _ollama_path; "
            "_ollama_path('http://127.0.0.1:11434/api/tags'); "
            "_ollama_path('http://127.0.0.1:11434/api/show')")
    result = subprocess.run([sys.executable, '-c', code], env=variables, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_child_env_cannot_enable_generation_in_a_no_live_process_tree(guarded):
    variables = {**guarded, 'FIXRATE_LOCAL_INFERENCE_ALLOWED': '0'}
    child = "from sitecustomize import _ollama_path; _ollama_path('http://127.0.0.1:11434/api/chat')"
    code = ('import subprocess,sys,os; '
            "env=dict(os.environ,FIXRATE_LOCAL_INFERENCE_ALLOWED='1'); "
            f'child=subprocess.run([sys.executable,"-c",{child!r}],env=env,capture_output=True,text=True); '
            'print(child.stderr); sys.exit(child.returncode)')
    result = subprocess.run([sys.executable, '-c', code], env=variables, capture_output=True, text=True)
    assert result.returncode != 0 and 'FIXRATE_GENERATION_DISABLED' in result.stdout


def test_discovery_uses_actual_catalog_and_show_without_pulling(monkeypatch):
    calls = []

    class Reply:
        def __init__(self, value): self.value = value
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return json.dumps(self.value).encode()

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return Reply(dict(models=[dict(name=MODEL['model'], digest=MODEL['digest'])])
                         if request.full_url.endswith('/api/tags') else dict(capabilities=['completion']))

    monkeypatch.setattr('scripts.verify_agent_local.build_opener', lambda *args: Opener())
    assert installed_model(MODEL['model']) == MODEL
    assert calls == ['http://127.0.0.1:11434/api/tags', 'http://127.0.0.1:11434/api/show']
    with pytest.raises(ValueError, match='not installed'):
        installed_model('absent:local')


def test_external_corpus_file_is_hashed_separately_from_baseline_sources(tmp_path):
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    corpus = tmp_path / 'changed' / 'test_compound.py'
    corpus.parent.mkdir()
    corpus.write_text('def test_goal(): pass\n', encoding='utf-8')
    before = corpus_manifest(baseline, [str(corpus) + '::test_goal'])
    assert list(before) == [str(corpus.resolve())]
    corpus.write_text('def test_goal(): assert True\n', encoding='utf-8')
    assert corpus_manifest(baseline, [str(corpus) + '::test_goal']) != before


def test_legacy_corpus_cannot_silently_test_a_different_model_than_provenance(tmp_path):
    source = tmp_path / 'tests/backend/test_agent_redteam_live.py'
    source.parent.mkdir(parents=True)
    source.write_text("config=dict(OLLAMA_CHAT_MODEL='installed:local', OLLAMA_CHAT_DIGEST='sha256:" + 'a' * 64 + "')", encoding='utf-8')
    targets = ['tests/backend/test_assistant_orchestrator_live.py']
    validate_legacy_model_pin(tmp_path, targets, MODEL)
    with pytest.raises(ValueError, match='differs'):
        validate_legacy_model_pin(tmp_path, targets, {**MODEL, 'model': 'other:installed'})
