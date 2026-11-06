"""Build and smoke-test a unique disposable Compose project, never the user's stack."""
import argparse
from http.cookiejar import CookieJar
from datetime import datetime, timedelta, timezone
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
    docker=shutil.which('docker')
    if not docker and os.name=='nt':
        candidate=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DockerDesktop/resources/bin/docker.exe'
        if candidate.is_file(): docker=str(candidate)
    parser=argparse.ArgumentParser()
    parser.add_argument('--docker',default=docker or 'docker')
    models=parser.add_mutually_exclusive_group()
    models.add_argument('--ml-cache',type=Path,help='Require real CLIP using an existing read-only host cache')
    models.add_argument('--bundled-image',help='Use a prebuilt local image containing RF and CLIP weights')
    parser.add_argument('--local-vision',action='store_true',help='Require real prepared Ollama vision alongside --bundled-image')
    parser.add_argument('--cloud-ai',action='store_true',help='Use real AI Tunnel; requires a private key in .env')
    parser.add_argument('--photo-before',type=Path,help='Optional private before photo for the isolated QA task')
    parser.add_argument('--photo-after',type=Path,help='Optional private after photo for the isolated QA task')
    args=parser.parse_args()
    if args.cloud_ai and args.local_vision:
        parser.error('Select --cloud-ai or --local-vision')
    if args.local_vision and not args.bundled_image:
        parser.error('--local-vision requires --bundled-image')
    if bool(args.photo_before) != bool(args.photo_after):
        parser.error('Provide both --photo-before and --photo-after')
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
    if args.bundled_image: env['FIXRATE_IMAGE']=args.bundled_image
    compose_file='compose.bundled.yaml' if args.bundled_image else 'compose.yaml'
    base=[args.docker,'compose','--project-name',project,'--file',str(ROOT/compose_file),
          '--env-file',str(envfile),'--project-directory',str(ROOT)]
    if args.ml_cache:
        env['CLIP_CACHE_ROOT']=str(args.ml_cache.resolve())
        base.extend(['--file',str(ROOT/'compose.ml.yaml')])
    if args.local_vision:
        prepared=json.loads((ROOT/'var/local-vision/model.json').read_text(encoding='utf-8'))
        env.update(OLLAMA_IMAGE=prepared['image'],OLLAMA_VISION_MODEL=prepared['model'],
            OLLAMA_VISION_DIGEST=prepared['digest'],PHOTO_REVIEW_TIMEOUT_SECONDS='120')
        base.extend(['--file',str(ROOT/'compose.vision.yaml')])
    cloud_key = None
    if args.cloud_ai:
        from scripts.start_local import read_ai_environment
        from ml_service.app.providers.aitunnel import AITunnelConfig
        cloud_values=read_ai_environment(ROOT/'.env')
        cloud_key=AITunnelConfig.from_environment('vision',cloud_values).api_key
        if not cloud_key:
            raise ValueError('Set AITUNNEL_API_KEY in private .env before real cloud verification')
        env.update({key:value for key,value in cloud_values.items() if key != 'AI_TUNNEL_API_KEY'})
        env.update(AITUNNEL_API_KEY=cloud_key,PHOTO_REVIEW_TIMEOUT_SECONDS='120',FORECAST_TIMEOUT_SECONDS='100')
        env.pop('AI_TUNNEL_API_KEY',None)
        base.extend(['--file',str(ROOT/'compose.cloud.yaml')])
    results=[]
    def safe(value):
        value=value.replace(db_password,'[REDACTED]').replace(password,'[REDACTED]')
        return value.replace(cloud_key,'[REDACTED]') if cloud_key else value
    def command(label,*parts):
        print(label,flush=True)
        started=time.monotonic()
        done=subprocess.run([*base,*parts],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
        raw=done.stdout+'\n'+done.stderr
        content=safe(raw)
        (logs/(label+'.log')).write_text(content,encoding='utf-8')
        results.append(dict(check=label,exit_code=done.returncode,seconds=round(time.monotonic()-started,2)))
        if label.startswith('app_logs'):
            assert db_password not in raw and password not in raw and (not cloud_key or cloud_key not in raw),'Secret appeared in raw application logs'
            results.append(dict(check='no_secrets_in_raw_app_logs',passed=True))
        if done.returncode: raise RuntimeError(label+' failed; see log')
        return done.stdout
    origin=f'http://127.0.0.1:{port}'
    def http(label,opener,path,expected=200,method='GET',body=None,csrf=None):
        headers={'Content-Type':'application/json'}
        if csrf: headers['X-CSRF-Token']=csrf
        request=Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try: response=opener.open(request,timeout=130 if (args.local_vision or args.cloud_ai) else 30)
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
        supplied=args.photo_before if phase=='before' else args.photo_after
        if supplied:
            with Image.open(supplied) as image: image.convert('RGB').save(stream,format=fmt)
        else:
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
        if args.bundled_image:
            done=subprocess.run([args.docker,'image','inspect',args.bundled_image],capture_output=True,text=True)
            assert done.returncode==0,'Bundled image must already exist locally'
        else:
            command('build','build','app')
        command('up','up','--detach','--no-build','--wait','--wait-timeout','180')
        if args.bundled_image:
            container=command('app_container','ps','--quiet','app').strip()
            mounts=subprocess.run([args.docker,'inspect','--format','{{json .Mounts}}',container],capture_output=True,text=True,check=True).stdout
            assert not any('/app/model-cache'==m['Destination'] or '/app/model-cache'.startswith(m['Destination'].rstrip('/')+'/') for m in json.loads(mounts))
            results.append(dict(check='model_weights_inside_image_without_host_mount',passed=True))
        plain=build_opener()
        assert http('health',plain,'/api/health')['database']=='ready'
        http('spa',plain,'/')
        http('openapi',plain,'/openapi.json')
        command('pip_check','exec','-T','app','python','-m','pip','check')
        if args.local_vision:
            command('vision_warmup','exec','-T','app','python','-c',
                'from ml_service.app.cv.local_vision import warmup_local_model; print(warmup_local_model())')
        command('seed','exec','-T','-e','FIXRATE_DEMO_PASSWORD','app','python','-m','app.manage','seed-demo')
        counts_sql="SELECT (SELECT count(*) FROM fixrate_schema_migrations),(SELECT count(*) FROM operation_templates),(SELECT count(*) FROM work_orders),(SELECT count(*) FROM users);"
        before=command('counts_before','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',counts_sql).strip()
        command('seed_repeat','exec','-T','-e','FIXRATE_DEMO_PASSWORD','app','python','-m','app.manage','seed-demo')
        after=command('counts_after','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',counts_sql).strip()
        assert before==after and before.split('|')[0]=='9'
        results.append(dict(check='seed_idempotence',passed=True,counts=before))
        prefix='/api/v1/maintenance'
        http('anonymous',plain,prefix+'/ui/equipment',401)
        executor=None; clients={}
        task=str(demo_id('runtime-order'))
        for role,email in [('director','fixrate-demo-executive@example.test'),('chief_engineer','fixrate-demo-chief_engineer@example.test'),('admin','fixrate-demo-admin@example.test'),('dispatcher','fixrate-demo-dispatcher@example.test'),
                          ('engineer','fixrate-demo-engineer@example.test'),('executor','fixrate-demo-1@example.test')]:
            client=build_opener(HTTPCookieProcessor(CookieJar()))
            login=http(role+'_login',client,'/api/v1/auth/login',method='POST',body=dict(email=email,password=password))
            assert login['profile']['role']==role
            clients[role]=(client,login['csrfToken'])
            http(role+'_session',client,'/api/v1/auth/session')
            http(role+'_equipment',client,prefix+'/ui/equipment')
            http(role+'_tasks',client,prefix+'/ui/tasks')
            if role=='dispatcher':
                run=http('real_cloud_forecast' if args.cloud_ai else 'real_rf_forecast',client,prefix+f'/tasks/{task}/forecast',method='POST',csrf=login['csrfToken'],body=dict(expected_revision=1))['run']
                if args.cloud_ai:
                    assert run['ai']['status'] in ('ok','needs_input') and run['ai']['modelRef'].startswith('aitunnel:')
                    if run['ai']['status']=='needs_input':
                        assert run['ai']['recommendedDate'] is None and run['ai']['errorCode']=='INSUFFICIENT_HISTORY'
                    assert run['decision']['selectedDate'] is None or run['decision']['selectedDate'] <= run['mandatoryDueDate']
                else:
                    assert run['ai']['status']=='ok' and run['ai']['recommendedDate']
                    assert run['ai']['modelRef'].startswith('synthetic_demo:rf:')
                results.append(dict(check='actual_cloud_forecast_result' if args.cloud_ai else 'actual_rf_result',status=run['ai']['status'],model_ref=run['ai']['modelRef'],method_version=run['ai']['methodVersion'],snapshot_hash=run['snapshotHash']))
                saved=command('cloud_forecast_persistence' if args.cloud_ai else 'rf_persistence','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',
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
        result=http('real_photo_review',engineer,prefix+f'/tasks/{task}/photo-review',method='POST',csrf=csrf,body=dict(expected_revision=bundle['task']['revision'],comparability_confirmed=args.local_vision or args.cloud_ai))
        results.append(dict(check='actual_cv_result',status=result['status'],model_ref=result['modelRef'],error_code=result['errorCode'],items=result['items']))
        print('Real photo review:',result['status'],result['modelRef'],result['errorCode'],flush=True)
        if args.cloud_ai:
            expected=AITunnelConfig.from_environment('vision',cloud_values).model_ref
            assert result['modelRef']==expected and result['status'] in ('completed','uncertain') and result['errorCode'] is None
            assert any(item.get('assessment') for item in result['items'])
            results.append(dict(check='actual_structured_cloud_vision',passed=True,model_ref=expected))
        elif args.local_vision:
            expected='ollama:'+prepared['model']+'@'+prepared['digest']
            assert result['modelRef']==expected and result['status'] in ('completed','uncertain') and result['errorCode'] is None
            assert any(item.get('assessment') for item in result['items'])
            results.append(dict(check='actual_structured_vision',passed=True,model_ref=expected))
        elif args.ml_cache or args.bundled_image:
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
        if args.local_vision or args.cloud_ai: assert any(item.visual_assessment for item in canonical.item_results)
        elif args.ml_cache or args.bundled_image: assert any(item.scores for item in canonical.item_results)
        results.append(dict(check='both_canonical_models_persisted',passed=True))
        # Restart while submitted, then call both real tools again through the API.
        saved_run=http('comparison_before_restart',engineer,prefix+'/ui/comparisons/'+run['runId'])['run']
        assert saved_run==run
        command('restart_before_acceptance','restart','app')
        for attempt in range(60):
            try:
                http('models_restart_health',plain,'/api/health'); break
            except (OSError,AssertionError): time.sleep(.5)
        else: raise RuntimeError('Model restart did not become healthy')
        restored=http('comparison_after_restart',engineer,prefix+'/ui/comparisons/'+run['runId'])['run']
        assert restored==saved_run
        results.append(dict(check='both_forecast_dates_inputs_and_reason_restored',passed=True))
        repeated_rf=http('cloud_forecast_after_restart' if args.cloud_ai else 'rf_after_restart',engineer,prefix+f'/tasks/{task}/forecast',method='POST',csrf=csrf,
            body=dict(expected_revision=bundle['task']['revision']))['run']
        assert repeated_rf['ai']['status'] in (('ok','needs_input') if args.cloud_ai else ('ok',)) and repeated_rf['ai']['modelRef']==run['ai']['modelRef']
        if args.local_vision:
            command('disable_vision','stop','vision')
            outage=http('vision_offline',engineer,prefix+f'/tasks/{task}/photo-review',method='POST',csrf=csrf,
                body=dict(expected_revision=bundle['task']['revision'],comparability_confirmed=True))
            assert outage['status']=='unavailable' and outage['modelRef'] is None and outage['errorCode']=='LOCAL_VISION_UNAVAILABLE'
            outage_saved=command('vision_error_persisted','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',
                "SELECT findings->'ui'->>'errorCode' FROM ai_quality_checks WHERE ai_quality_check_id='"+outage['id']+"';")
            assert outage_saved.strip()=='LOCAL_VISION_UNAVAILABLE'
            command('restore_vision','up','--detach','--no-build','--wait','--wait-timeout','120','vision')
            command('vision_warmup_after_outage','exec','-T','app','python','-c',
                'from ml_service.app.cv.local_vision import warmup_local_model; print(warmup_local_model())')
            results.append(dict(check='local_vision_outage_no_fake_clip_fallback',passed=True))
        if args.cloud_ai:
            command('app_logs_before_cloud_disable','logs','--no-color','app')
            env['AITUNNEL_API_KEY']=''
            command('disable_cloud_key','up','--detach','--no-build','--wait','--wait-timeout','120','app')
            outage=http('cloud_unconfigured',engineer,prefix+f'/tasks/{task}/photo-review',method='POST',csrf=csrf,
                body=dict(expected_revision=bundle['task']['revision'],comparability_confirmed=True))
            assert outage['status']=='unavailable' and outage['modelRef'] is None and outage['errorCode']=='AITUNNEL_NOT_CONFIGURED'
            saved_error=command('cloud_error_persisted','exec','-T','db','psql','-U','fixrate','-d','fixrate','-At','-c',
                "SELECT findings->'ui'->>'errorCode' FROM ai_quality_checks WHERE ai_quality_check_id='"+outage['id']+"';")
            assert saved_error.strip()=='AITUNNEL_NOT_CONFIGURED'
            # The original runtime rule is intentionally a draft. Create a separate
            # explicitly configured rule through the public API, never by SQL edits.
            admin,admin_csrf=clients['chief_engineer']; dispatcher,dispatcher_csrf=clients['dispatcher']
            day=(datetime.now(timezone.utc)+timedelta(days=1)).date()
            configured=http('published_cloud_test_configuration',admin,
                prefix+f"/equipment/{demo_id('equipment-2')}/service-configurations",expected=201,method='POST',csrf=admin_csrf,
                body=dict(code='CLOUD-SMOKE',title='Explicit cloud fallback test',instructions='Synthetic API fixture, not a customer regulation',
                    maintenance_type='ТО2',pattern=dict(frequency='dates',anchor_date=str(day),dates=[str(day)]),valid_from=str(day),
                    crew_size=1,norm_value='1.000',norm_unit='person_hour',duration_minutes=60,qualification_ids=[],
                    checklist=[dict(text='Synthetic fallback check')],allowed_lead_days=0,enabled=True,methodology_ref='TEST ONLY cloud failure fixture'))
            preview=http('published_cloud_test_preview',dispatcher,prefix+f'/ui/calendar/preview?year={day.year}&month={day.month}')
            generated=http('published_cloud_test_generation',dispatcher,prefix+'/calendar/generate',method='POST',csrf=dispatcher_csrf,
                body=dict(year=day.year,month=day.month,preview_token=preview['generationToken'],idempotency_key=str(uuid4())))
            generated_task=next(row for row in generated['items'] if row['operationTitle']=='Explicit cloud fallback test')['taskId']
            fallback=http('cloud_disabled_forecast',engineer,prefix+f'/tasks/{generated_task}/forecast',method='POST',csrf=csrf,
                body=dict(expected_revision=1))['run']
            assert fallback['ai']['status']=='unavailable' and fallback['ai']['errorCode']=='AITUNNEL_NOT_CONFIGURED'
            assert fallback['decision']['status']=='fallback' and fallback['decision']['selectedDate']==fallback['algorithmic']['recommendedDate']
            command('app_logs_cloud_disabled','logs','--no-color','app')
            env['AITUNNEL_API_KEY']=cloud_key
            command('restore_cloud_key','up','--detach','--no-build','--wait','--wait-timeout','120','app')
            results.append(dict(check='missing_cloud_key_persisted_and_regulatory_fallback',passed=True))
        repeated_cv=http('cv_after_restart',engineer,prefix+f'/tasks/{task}/photo-review',method='POST',csrf=csrf,
            body=dict(expected_revision=bundle['task']['revision']))
        if args.ml_cache or args.bundled_image or args.cloud_ai:
            assert repeated_cv['modelRef']==result['modelRef'] and repeated_cv['errorCode'] is None
        else:
            assert repeated_cv['status']=='unavailable' and repeated_cv['errorCode']=='MODEL_NOT_READY'
        results.append(dict(check='both_ml_tools_invoked_after_restart',passed=True))
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
        persisted=http('persistent_task',executor,prefix+f'/ui/tasks/{task}')
        assert persisted['task']['state']=='accepted' and persisted['execution']['id']==bundle['execution']['id']
        assert persisted['review']['id']==repeated_cv['id']
        assert http('closed_job_comparison',engineer,prefix+'/ui/comparisons/'+run['runId'])['run']==saved_run
        history=http('closed_job_equipment_history',engineer,prefix+'/ui/equipment/'+persisted['task']['equipmentId'])['history']
        assert any(event['taskCode']==task[:8] for event in history)
        results.append(dict(check='closed_job_history_and_comparison_survive_restart',passed=True))
        assert http('persistent_photo',executor,photo_url)==photo_blob
        command('app_logs','logs','--no-color','app')
        raw='\n'.join(path.read_text(encoding='utf-8') for path in sorted(logs.glob('app_logs*.log')))
        (logs/'app_logs_combined.log').write_text(raw,encoding='utf-8')
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
