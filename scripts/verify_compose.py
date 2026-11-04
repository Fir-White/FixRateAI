"""Build and smoke-test a unique disposable Compose project, never the user's stack."""
import argparse
from http.cookiejar import CookieJar
import json
import io
import random
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from scripts.verification_paths import prepare_run
from app.integration.demo import demo_id

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--docker',default=shutil.which('docker') or 'docker')
    parser.add_argument('--ml-cache',type=Path,help='Require real CLIP using an existing read-only host cache')
    args=parser.parse_args()
    if args.ml_cache and not args.ml_cache.resolve().is_dir():
        parser.error('--ml-cache must point to an existing cache directory')
    output,logs=prepare_run(prefix='compose')
    project='fixrate-qa-'+uuid4().hex[:12]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    db_password=secrets.token_hex(32); password=secrets.token_hex(24)
    env=dict(os.environ,POSTGRES_PASSWORD=db_password,FIXRATE_DEMO_PASSWORD=password,
             FIXRATE_PORT=str(port),COOKIE_SECURE='false',PHOTO_REVIEW_TIMEOUT_SECONDS='20')
    # Empty env-file prevents accidental use of a real project .env.
    temporary=tempfile.TemporaryDirectory(prefix='fixrate-compose-')
    envfile=Path(temporary.name)/'empty.env'; envfile.write_text('')
    base=[args.docker,'compose','--project-name',project,'--file',str(ROOT/'compose.yaml'),
          '--env-file',str(envfile),'--project-directory',str(ROOT)]
    if args.ml_cache:
        env['CLIP_CACHE_ROOT']=str(args.ml_cache.resolve())
        base.extend(['--file',str(ROOT/'compose.ml.yaml')])
    results=[]
    def safe(value): return value.replace(db_password,'[REDACTED]').replace(password,'[REDACTED]')
    def command(label,*parts):
        print(label,flush=True)
        started=time.monotonic()
        done=subprocess.run([*base,*parts],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
        raw=done.stdout+'\n'+done.stderr
        content=safe(raw)
        (logs/(label+'.log')).write_text(content,encoding='utf-8')
        results.append(dict(check=label,exit_code=done.returncode,seconds=round(time.monotonic()-started,2)))
        if label=='app_logs':
            assert db_password not in raw and password not in raw,'Secret appeared in raw application logs'
            results.append(dict(check='no_secrets_in_raw_app_logs',passed=True))
        if done.returncode: raise RuntimeError(label+' failed; see log')
        return done.stdout
    origin=f'http://127.0.0.1:{port}'
    def http(label,opener,path,expected=200,method='GET',body=None,csrf=None):
        headers={'Content-Type':'application/json'}
        if csrf: headers['X-CSRF-Token']=csrf
        request=Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try: response=opener.open(request,timeout=30)
        except HTTPError as exc: response=exc
        with response:
            status=response.status; data=response.read()
        results.append(dict(check=label,status=status,expected=expected))
        assert status==expected,label+': HTTP '+str(status)
        return json.loads(data) if data.startswith((b'{',b'[')) else data
    def upload(client,task,bundle,phase,fmt,ext,mime,csrf):
        from PIL import Image
        stream=io.BytesIO()
        pixels=random.Random(410 if phase=='before' else 411).randbytes(128*128*3)
        Image.frombytes('RGB',(128,128),pixels).save(stream,format=fmt)
        blob=stream.getvalue(); boundary='fixrate'+uuid4().hex
        fields=dict(expected_revision=bundle['task']['revision'],checklist_item_id=bundle['execution']['checklist'][0]['id'],phase=phase,view_key='front')
        chunks=[]
        for name,value in fields.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="photo.{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode()+blob+f'\r\n--{boundary}--\r\n'.encode())
        request=Request(origin+f'/api/v1/maintenance/tasks/{task}/photos',data=b''.join(chunks),
            headers={'Content-Type':'multipart/form-data; boundary='+boundary,'X-CSRF-Token':csrf})
        with client.open(request,timeout=30) as response:
            assert response.status==200
            result=json.loads(response.read())
        photo=next(p for p in result['execution']['photos'] if p['phase']==phase)
        assert http('download_'+phase,client,photo['url'])==blob
        results.append(dict(check='upload_'+fmt,passed=True,photo_id=photo['id']))
        return result,photo['url'],blob
    try:
        command('config','config','--quiet')
        command('build','build','app')
        command('up','up','--detach','--no-build','--wait','--wait-timeout','180')
        plain=build_opener()
        assert http('health',plain,'/api/health')['database']=='ready'
        http('spa',plain,'/')
        http('openapi',plain,'/openapi.json')
        command('pip_check','exec','-T','app','python','-m','pip','check')
        command('seed','exec','-T','-e','FIXRATE_DEMO_PASSWORD','app','python','-m','app.manage','seed-demo')
        counts_sql="SELECT (SELECT count(*) FROM fixrate_schema_migrations),(SELECT count(*) FROM operation_templates),(SELECT count(*) FROM work_orders),(SELECT count(*) FROM users);"
        before=command('counts_before','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',counts_sql).strip()
        command('seed_repeat','exec','-T','-e','FIXRATE_DEMO_PASSWORD','app','python','-m','app.manage','seed-demo')
        after=command('counts_after','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',counts_sql).strip()
        assert before==after and before.split('|')[0]=='8'
        results.append(dict(check='seed_idempotence',passed=True,counts=before))
        prefix='/api/v1/maintenance'
        http('anonymous',plain,prefix+'/ui/equipment',401)
        executor=None; clients={}
        task=str(demo_id('runtime-order'))
        for role,email in [('admin','fixrate-demo-admin@example.test'),('dispatcher','fixrate-demo-dispatcher@example.test'),
                          ('engineer','fixrate-demo-engineer@example.test'),('executor','fixrate-demo-1@example.test')]:
            client=build_opener(HTTPCookieProcessor(CookieJar()))
            login=http(role+'_login',client,'/api/v1/auth/login',method='POST',body=dict(email=email,password=password))
            assert login['profile']['role']==role
            clients[role]=(client,login['csrfToken'])
            http(role+'_session',client,'/api/v1/auth/session')
            http(role+'_equipment',client,prefix+'/ui/equipment')
            http(role+'_tasks',client,prefix+'/ui/tasks')
            if role=='dispatcher':
                run=http('real_rf_forecast',client,prefix+f'/tasks/{task}/forecast',method='POST',csrf=login['csrfToken'],body=dict(expected_revision=1))['run']
                assert run['ai']['status']=='ok' and run['ai']['recommendedDate']
                assert run['ai']['modelRef'].startswith('synthetic_demo:rf:')
                results.append(dict(check='actual_rf_result',status=run['ai']['status'],model_ref=run['ai']['modelRef'],method_version=run['ai']['methodVersion'],snapshot_hash=run['snapshotHash']))
                saved=command('rf_persistence','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',
                    "SELECT output_snapshot->'canonical' FROM forecast_runs WHERE forecast_run_id='"+run['ai']['resultId']+"';")
                from app.schemas.maintenance import ForecastResult
                canonical=ForecastResult.model_validate_json(saved.strip())
                assert canonical.model_ref==run['ai']['modelRef'] and canonical.snapshot_sha256==run['snapshotHash']
            if role=='executor':
                executor=client
                http('executor_management_denied',client,prefix+'/management/workforce',403)
                http('executor_generate_denied',client,prefix+'/calendar/generate',403,method='POST',csrf=login['csrfToken'],
                     body=dict(year=2026,month=11,idempotency_key=str(uuid4()),preview_token='0'*64))
                task=str(demo_id('runtime-order'))
                bundle=http('executor_start',client,prefix+f'/tasks/{task}/start',method='POST',csrf=login['csrfToken'],body=dict(expected_revision=1))
                assert bundle['task']['state']=='in_progress'
                bundle=http('save_report',client,prefix+f'/tasks/{task}/report',method='PUT',csrf=login['csrfToken'],body=dict(
                    expected_revision=bundle['task']['revision'],narrative='Compose real-files smoke',answers={bundle['execution']['checklist'][0]['id']:'done'}))
                bundle,photo_url,photo_blob=upload(client,task,bundle,'before','PNG','png','image/png',login['csrfToken'])
                bundle,_,_=upload(client,task,bundle,'after','JPEG','jpg','image/jpeg',login['csrfToken'])
                bundle=http('submit',client,prefix+f'/tasks/{task}/submit',method='POST',csrf=login['csrfToken'],body=dict(expected_revision=bundle['task']['revision']))
        engineer,csrf=clients['engineer']
        result=http('real_photo_review',engineer,prefix+f'/tasks/{task}/photo-review',method='POST',csrf=csrf,body=dict(expected_revision=bundle['task']['revision']))
        results.append(dict(check='actual_cv_result',status=result['status'],model_ref=result['modelRef'],error_code=result['errorCode'],items=result['items']))
        print(json.dumps(results[-1],ensure_ascii=True),flush=True)
        if args.ml_cache:
            from ml_service.app.core.config import settings
            expected=f'{settings.clip_model_name}@{settings.clip_revision}'
            assert result['modelRef']==expected and result['status'] in ('completed','uncertain') and result['errorCode'] is None
        else:
            assert result['status']=='unavailable' and result['modelRef'] is None and result['errorCode']=='MODEL_NOT_READY'
        saved=command('cv_persistence','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',
            "SELECT findings->'canonical' FROM ai_quality_checks WHERE ai_quality_check_id='"+result['id']+"';")
        from app.schemas.maintenance import PhotoReviewResult
        canonical=PhotoReviewResult.model_validate_json(saved.strip())
        assert str(canonical.ai_review_id)==result['id'] and canonical.model_ref==result['modelRef']
        if args.ml_cache: assert any(item.scores for item in canonical.item_results)
        results.append(dict(check='both_canonical_models_persisted',passed=True))
        bundle=http('accept',engineer,prefix+f'/tasks/{task}/review',method='POST',csrf=csrf,body=dict(expected_revision=bundle['task']['revision'],execution_id=bundle['execution']['id'],verdict='accepted',reason='Compose smoke acceptance'))
        assert bundle['task']['state']=='accepted'
        command('seed_after_acceptance','exec','-T','-e','FIXRATE_DEMO_PASSWORD','app','python','-m','app.manage','seed-demo')
        assert http('seed_preserves_acceptance',executor,prefix+f'/ui/tasks/{task}')['task']['state']=='accepted'

        # Restart exercises the same persistent DB with checksummed migrations and existing sessions.
        command('restart','restart','app')
        for attempt in range(60):
            try:
                http('restart_health',plain,'/api/health'); break
            except (OSError,AssertionError): time.sleep(.5)
        else: raise RuntimeError('Restart did not become healthy')
        http('persistent_session',executor,'/api/v1/auth/session')
        assert http('persistent_task',executor,prefix+f'/ui/tasks/{task}')['task']['state']=='accepted'
        assert http('persistent_photo',executor,photo_url)==photo_blob
        command('app_logs','logs','--no-color','app')
        raw=(logs/'app_logs.log').read_text(encoding='utf-8')
        assert 'ml_call_done tool=forecast' in raw and 'ml_result tool=photo-review' in raw
        results.append(dict(check='both_ml_calls_logged',passed=True))
        assert db_password not in raw and password not in raw
        results.append(dict(check='overall',passed=True))
    finally:
        try:
            command('cleanup','down','--volumes','--remove-orphans')
        finally:
            temporary.cleanup()
            (output/'results.json').write_text(json.dumps(dict(project=project,results=results),ensure_ascii=False,indent=2),encoding='utf-8')
            print('Results: '+str(output/'results.json'),flush=True)
            print('Logs: '+str(logs),flush=True)

if __name__=='__main__': main()
