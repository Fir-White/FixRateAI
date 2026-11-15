"""Reproducible isolated audit runner. No production URL, cloud fallback or auto-push."""
import argparse,hashlib,json,os,subprocess,sys
from importlib.metadata import version,PackageNotFoundError
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def source_manifest():
    paths=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    configuration={'pyproject.toml','pytest.ini','requirements.txt','requirements-solver.txt','setup.cfg','tox.ini','.coveragerc','.python-version'}
    entries={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(paths))
        if (name.startswith(('backend/','ml_service/','scripts/','tests/','contracts/','database/')) or name in configuration) and (ROOT/name).is_file()}
    return dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=entries,
        sha256=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin',type=Path,required=True)
    parser.add_argument('--live',action='store_true',help='Also call the already installed pinned native Ollama model')
    parser.add_argument('--rounds',type=int,default=1,choices=range(1,11))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    output=(args.output or ROOT/'reports'/('agent-redteam-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve()
    if not output.is_relative_to(ROOT/'reports'):parser.error('Audit artifacts must stay below this worktree/reports')
    output.mkdir(parents=True,exist_ok=False)
    packages={}
    for package in ('fastapi','sqlalchemy','psycopg','pydantic','numpy','scikit-learn','ortools','pytest','Pillow'):
        try:packages[package]=version(package)
        except PackageNotFoundError:packages[package]=None
    (output/'environment.json').write_text(json.dumps(dict(python=sys.version,packages=packages),indent=2),encoding='utf-8')
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    # Never inherit credentials or a production DB/provider from the shell.
    for key in list(env):
        if key in ('DATABASE_URL','INTEGRATION_DATABASE_URL','TEST_DATABASE_URL') or any(word in key.upper() for word in ('API_KEY','API_TOKEN','AITUNNEL','OPENAI','ANTHROPIC')):env.pop(key)
    env.update(FIXRATE_AGENT_LIVE='1' if args.live else '0',FIXRATE_SCENARIOS_LIVE='1' if args.live else '0',FIXRATE_SCENARIO_ASSERT='1')
    if args.live:
        config=output/'local-provider.env'
        config.write_text('ASSISTANT_PROVIDER=ollama\nOLLAMA_CHAT_BASE_URL=http://127.0.0.1:11434\nOLLAMA_CHAT_MODEL=qwen3.5:4b-q4_K_M\nOLLAMA_CHAT_DIGEST=sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04\nOLLAMA_CHAT_TIMEOUT_SECONDS=240\n',encoding='utf-8')
        env['FIXRATE_LIVE_PROVIDER_FILE']=str(config)
        env['FIXRATE_SCENARIO_OUTPUT']=str(output)
    tests=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'tests/backend').glob('test_assistant*.py'))]
    tests += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'tests/backend').glob('test_agent_redteam*.py'))]
    tests += ['tests/backend/'+name for name in ('test_optimization.py','test_optimization_api.py','test_draft_plans.py','test_publication.py','test_portfolio_publication.py','test_requirements.py','test_catalog_decisions.py')]
    tests += ['tests/ml/test_ollama_chat.py']
    results=[]
    for number in range(1,args.rounds+1):
        before=source_manifest()
        (output/f'source-{number}.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
        env['FIXRATE_SCENARIO_ROUND']=f'production-{number}'
        command=[sys.executable,'-B',str(ROOT/'scripts/verify.py'),'--pg-bin',str(args.pg_bin),'--agent-only','--output',str(output/f'round-{number}'),'--pytest-target',*tests]
        print(f'Audit round {number}/{args.rounds}; artifacts: {output}',flush=True)
        with (output/f'round-{number}.log').open('w',encoding='utf-8') as log:
            done=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        after=source_manifest();stable=after['sha256']==before['sha256']
        results.append(dict(round=number,exit_code=done.returncode,live_enabled=args.live,source_stable=stable,source_sha256=before['sha256'],source_head=before['head']))
        (output/'summary.json').write_text(json.dumps(dict(rounds=results,complete=len(results)==args.rounds),indent=2),encoding='utf-8')
        # Keep failed evidence; a failed round is never silently retried to green.
        if done.returncode:return done.returncode
        if not stable:
            print('Source files changed during verification; this round cannot validate one coherent revision.',file=sys.stderr)
            return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
