"""Compare assistant pipelines and providers in disposable PostgreSQL."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.verify_agent_local import LOCAL_GUARD, ROOT, corpus_manifest, environment, installed_model, source_manifest


def cloud_guard():
    """Permit the one explicitly selected provider request in the test process tree."""
    return (LOCAL_GUARD.replace('import ipaddress, os, subprocess, sys',
                                'import ipaddress, os, subprocess, sys, threading\n_TUNNEL = threading.local()')
            .replace('def _audit(event, args):', '''def _audit(event, args):
    if getattr(_TUNNEL, 'request', False):
        if event in ('socket.getaddrinfo', 'socket.gethostbyname') and args[0] not in ('api.aitunnel.ru', b'api.aitunnel.ru'):
            raise PermissionError('FIXRATE_UNAPPROVED_TUNNEL_HOST')
        return''')
            .replace('    return _open(self, fullurl, *args, **kwargs)', '''    url = urlsplit(fullurl.full_url if hasattr(fullurl, 'full_url') else str(fullurl))
    if (os.getenv('FIXRATE_PIPELINE_CLOUD_CONFIG')
            and url.geturl() == 'https://api.aitunnel.ru/v1/chat/completions'
            and getattr(fullurl, 'get_method', lambda: None)() == 'POST'):
        _TUNNEL.request = True
        try:
            return _open(self, fullurl, *args, **kwargs)
        finally:
            _TUNNEL.request = False
    return _open(self, fullurl, *args, **kwargs)'''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pg-bin', type=Path, default=Path('C:/Program Files/PostgreSQL/18/bin'))
    parser.add_argument('--cloud-config', type=Path, help='AI Tunnel config file for the authorized synthetic corpus')
    parser.add_argument('--variants', help='A fixed Qwen, B dynamic Qwen, C dynamic DeepSeek, D ERP Qwen, E ERP DeepSeek')
    parser.add_argument('--cases', default='', help='Comma-separated IDs from the synthetic comparison corpus')
    corpus = parser.add_mutually_exclusive_group()
    corpus.add_argument('--operator-holdout', action='store_true', help='Use the separate multi-turn ERP validation corpus')
    corpus.add_argument('--reliability-holdout', action='store_true', help='Use the 50 additional frozen ERP dialogues')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'reports'):
        parser.error('--output must be inside reports/')
    variants = args.variants or ('CAB' if args.cloud_config else 'AB')
    if not variants or len(variants) != len(set(variants)) or set(variants) - set('ABCDE'):
        parser.error('--variants must be a sequence of distinct letters A through E')
    if set('CE') & set(variants) and not args.cloud_config:
        parser.error('Cloud variants require --cloud-config')
    guard = output / 'policy'
    guard.mkdir(parents=True, exist_ok=False)
    (guard/'sitecustomize.py').write_text(cloud_guard() if args.cloud_config else LOCAL_GUARD, encoding='utf-8')
    model = installed_model('qwen3.5:4b-q4_K_M')
    variables = environment(dict(os.environ), guard, model, live=True)
    variables.update(FIXRATE_ASSISTANT_AGENT_VERSION='v3', FIXRATE_ASSISTANT_V3_PIPELINE='v3',
                     FIXRATE_PIPELINE_COMPARE='1', FIXRATE_PIPELINE_CASES=args.cases, PYTHON_DOTENV_DISABLED='1',
                     FIXRATE_PIPELINE_VARIANTS=variants)
    if args.cloud_config:
        variables['FIXRATE_PIPELINE_CLOUD_CONFIG'] = str(args.cloud_config.resolve(strict=True))
    test = ('agent_reliability_lab/erp_operator_holdout.py' if args.operator_holdout
            else 'agent_reliability_lab/erp_operator_reliability_holdout.py' if args.reliability_holdout
            else 'agent_reliability_lab/evals/test_pipeline_comparison.py')
    harness_paths = [test, 'agent_reliability_lab/pipeline_cases.py',
                     'agent_reliability_lab/run_pipeline_comparison.py']
    harness = corpus_manifest(ROOT, harness_paths)
    before = source_manifest(ROOT)
    (output/'provenance.json').write_text(json.dumps(dict(source=before, local_model=model,
        cloud_model='aitunnel:deepseek-v4-flash' if args.cloud_config else None, test=test, harness=harness,
        started_at=datetime.now(timezone.utc).isoformat()), indent=2), encoding='utf-8')
    command = [sys.executable, '-B', str(ROOT/'scripts/verify.py'), '--pg-bin', str(args.pg_bin),
               '--agent-only', '--output', str(output/'run'), '--pytest-target', test]
    with (output/'runner.log').open('w', encoding='utf-8') as log:
        run = subprocess.run(command, cwd=ROOT, env=variables, stdout=log, stderr=subprocess.STDOUT, check=False)
    after = source_manifest(ROOT)
    result = dict(exit_code=run.returncode, source_stable=before['sha256'] == after['sha256']
                  and harness == corpus_manifest(ROOT, harness_paths),
                  completed_at=datetime.now(timezone.utc).isoformat())
    (output/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return run.returncode or int(not result['source_stable'])


if __name__ == '__main__':
    raise SystemExit(main())
