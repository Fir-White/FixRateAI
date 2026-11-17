"""CI regression on an explicitly named disposable PostgreSQL database; no LLM IO."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]


def main():
    from sqlalchemy.engine import make_url
    from app.db.session import make_engine
    from app.manage import migrate,seed_demo
    from scripts.verify_agent_local import LOCAL_GUARD,environment
    url=os.environ['INTEGRATION_DATABASE_URL'];parsed=make_url(url)
    if parsed.host not in ('127.0.0.1','localhost') or not parsed.database.startswith('fixrate_test_'):
        raise ValueError('Only loopback disposable test databases are accepted')
    output=ROOT/'reports/release-checks';output.mkdir(parents=True,exist_ok=True)
    guard=output/'policy';guard.mkdir(exist_ok=True);(guard/'sitecustomize.py').write_text(LOCAL_GUARD,encoding='utf-8')
    env=environment(dict(os.environ),guard,dict(model='__generation_disabled__',digest='',base_url='http://127.0.0.1:11434'),live=False)
    env['INTEGRATION_DATABASE_URL']=url
    env['PHOTO_STORAGE_ROOT']=str(output/'test-files')
    env['FIXRATE_TEST_PASSWORD']='Release-test-fixture-only-2026'
    engine=make_engine(url)
    try:migrate(engine);seed_demo(engine,env['FIXRATE_TEST_PASSWORD']);migrate(engine)
    finally:engine.dispose()
    command=[sys.executable,'-B','-m','pytest','tests/backend','tests/ml','-q','--junitxml='+str(output/'junit.xml')]
    done=subprocess.run(command,cwd=ROOT,env=env)
    (output/'summary.json').write_text(json.dumps(dict(exit_code=done.returncode,external_network_denied=True,inference=False)),encoding='utf-8')
    return done.returncode

if __name__=='__main__':raise SystemExit(main())
