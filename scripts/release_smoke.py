"""Exercise generated Linux installers on disposable Compose projects only (CI)."""
from __future__ import annotations
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor,build_opener,Request
from zipfile import ZipFile

from scripts.release_package import build, verify


def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


def run(args,**options):
    return subprocess.run([str(x) for x in args],check=True,**options)


def compose(directory):
    values={}
    for name in ('infrastructure.env','secrets.env','images.env'):
        for line in (directory/name).read_text().splitlines():
            if '=' in line:
                key,value=line.split('=',1);values[key]=value
    assert values['FIXRATE_PROJECT'].startswith('fixrate_')
    return ['docker','compose',*[x for name in ('infrastructure.env','secrets.env','images.env') for x in ('--env-file',str(directory/name))],'-f',str(directory/'compose.yaml')]


def request(opener,base,path,body=None,headers=None,status=200):
    req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with opener.open(req,timeout=20) as response:actual=response.status;data=response.read()
    except HTTPError as exc:actual=exc.code;data=exc.read()
    assert actual==status,(path,actual,status)
    return json.loads(data) if data else None


def ready(base):
    for _ in range(90):
        try:
            result=request(build_opener(),base,'/api/health')
            if result['database']=='ready':return
        except (HTTPError,URLError,AssertionError):pass
        time.sleep(2)
    raise RuntimeError('Stack did not become ready')


def quick_start(pkg, directory, cleanup):
    manifest=json.loads((pkg/'release-manifest.json').read_text(encoding='utf-8'))
    directory.mkdir()
    with ZipFile(pkg/manifest['quick_start']) as archive:
        expected={'compose.yaml','compose.cloud.yaml','images.env','release.json','README.md','.env.example','SHA256SUMS'}
        assert set(archive.namelist())==expected and len(archive.namelist())==len(expected)
        archive.extractall(directory)
    entries=(directory/'SHA256SUMS').read_text(encoding='ascii').splitlines()
    assert set(line.split('  ',1)[1] for line in entries)==expected-{'SHA256SUMS'}
    for line in entries:
        digest,name=line.split('  ',1)
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest
    project='fixrate_quickstart_ci_'+secrets.token_hex(8)
    token=secrets.token_hex(32);password=secrets.token_hex(24);listen=port()
    values=dict(FIXRATE_PROJECT=project,FIXRATE_BIND='127.0.0.1',FIXRATE_PORT=listen,
                POSTGRES_PASSWORD=secrets.token_hex(32),FIXRATE_BOOTSTRAP_TOKEN_SHA256=hashlib.sha256(token.encode()).hexdigest(),
                COOKIE_SECURE='false')
    envfile=directory/'.env'
    with os.fdopen(os.open(envfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as stream:
        stream.writelines(f'{key}={value}\n' for key,value in values.items())
    dc=['docker','compose','--project-name',project,'--env-file',str(directory/'images.env'),'--env-file',str(envfile),
        '-f',str(directory/'compose.yaml')]
    env={key:value for key,value in os.environ.items() if key not in values and key not in {
        'FIXRATE_APP_IMAGE','FIXRATE_WEB_IMAGE','FIXRATE_DB_IMAGE','FIXRATE_ADDRESS','FIXRATE_PERMISSION_PROFILE',
        'FIXRATE_HTTPS_PORT','FIXRATE_HTTP_PORT','COMPOSE_PROFILES'}}
    cleanup.append((dc,env))
    run([*dc,'config','--quiet'],env=env)
    run([*dc,'up','-d','--wait','--wait-timeout','180','--pull','never'],env=env)
    base=f'http://127.0.0.1:{listen}';ready(base)
    opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(base+'/setup',timeout=15) as response:
        assert response.status==200 and response.headers.get_content_type()=='text/html'
    admin={'organization_name':'TEST Quick Start','site_name':'TEST Quick Start site','full_name':'TEST administrator',
           'email':'quickstart@example.test','password':password}
    request(opener,base,'/api/setup',admin,{'X-FixRate-Setup-Token':token},201)
    auth=request(opener,base,'/api/v1/auth/login',{'email':admin['email'],'password':password})
    assert auth['profile']['role']=='admin' and auth['profile']['permissionProfile']=='mvp'
    assert request(opener,base,'/api/v1/maintenance/ui/equipment')==[]


def main():
    p=argparse.ArgumentParser();p.add_argument('--app-image',required=True);p.add_argument('--web-image',required=True);p.add_argument('--sha',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    scratch=Path(tempfile.mkdtemp(prefix='fixrate-release-ci-')).resolve()
    installations=[];quick_projects=[];results=[]
    try:
        pkg=scratch/'package'
        build(pkg,version='0.1.0',source_sha=args.sha,app_image=args.app_image,web_image=args.web_image,channel='test',allow_dirty=True)
        verify(pkg)
        quick_start(pkg,scratch/'quick-start',quick_projects)
        results.append({'test':'QUICK-START','status':'PASS','scope':'Extracted ZIP, Core without seed, /setup and first login'})
        installer=pkg/'fixrate-install.sh'
        directory=scratch/'first';installations.append(directory);first_port=port();base=f'http://127.0.0.1:{first_port}'
        common=['bash',installer,'install','--install-dir',directory,'--port',first_port,'--local-images']
        run(common);ready(base);results.append({'test':'TEST-01','status':'PASS','scope':'Ubuntu CI host; installer invokes no host Python/Node/PostgreSQL'})
        initial=(directory/'secrets.env').read_bytes()
        token=(directory/'bootstrap-token.txt').read_text()
        opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        password=secrets.token_urlsafe(24)
        admin={'organization_name':'TEST organization','site_name':'TEST building','full_name':'TEST administrator','email':'admin@example.test','password':password}
        request(opener,base,'/api/setup',admin,{'X-FixRate-Setup-Token':'wrong'},403)
        request(opener,base,'/api/setup',admin,{'X-FixRate-Setup-Token':token},201);results.append({'test':'TEST-03','status':'PASS'})
        request(opener,base,'/api/setup',admin,{'X-FixRate-Setup-Token':token},409);results.append({'test':'TEST-04','status':'PASS'})
        auth=request(opener,base,'/api/v1/auth/login',{'email':admin['email'],'password':password});headers={'X-CSRF-Token':auth['csrfToken']}
        code=request(opener,base,'/api/v1/maintenance/management/enrollment',{},headers)['code']
        request(opener,base,'/api/v1/auth/register',{'full_name':'TEST employee','email':'worker@example.test','password':secrets.token_urlsafe(24),'company_code':code},status=201)
        application=request(opener,base,'/api/v1/maintenance/management/workforce')['applications'][0]
        request(opener,base,'/api/v1/maintenance/management/applications/'+application['application_id']+'/decision',{'expected_revision':application['revision'],'role':'executor','is_active':True,'decision':'accepted'},headers)
        results.append({'test':'TEST-05','status':'PASS'})
        dc=compose(directory)
        run([*dc,'run','--rm','--no-deps','-T','api','python','-c',"from pathlib import Path;Path('/app/var/photos/persistence-test.bin').write_bytes(b'TEST\\x00\\xff')"])
        run(common);assert initial==(directory/'secrets.env').read_bytes();ready(base)
        results.append({'test':'TEST-02','status':'PASS'})
        run([*dc,'restart','api','worker','web']);ready(base)
        request(opener,base,'/api/v1/auth/login',{'email':admin['email'],'password':password})
        results.append({'test':'TEST-06','status':'PASS','scope':'Database users and dedicated storage fixture'})
        results.append({'test':'TEST-07','status':'PASS','scope':'No Ollama service/model started; Core operates'})
        results.append({'test':'TEST-08','status':'BLOCKED','reason':'No administrator-provided existing Ollama in CI; no weights downloaded'})
        run(['bash',installer,'backup','--install-dir',directory])
        backup=sorted((directory/'backups').iterdir())[-1]
        target=scratch/'restored';installations.append(target);second_port=port();second_base=f'http://127.0.0.1:{second_port}'
        run(['bash',installer,'install','--install-dir',target,'--port',second_port,'--local-images'])
        run(['bash',installer,'restore','--install-dir',target,'--backup-path',backup,'--confirm-data-replacement','--local-images'])
        ready(second_base)
        request(build_opener(),second_base,'/api/v1/auth/login',{'email':admin['email'],'password':password})
        restored_bytes=subprocess.check_output([*compose(target),'run','--rm','--no-deps','-T','api','python','-c',"from pathlib import Path;import sys;sys.stdout.buffer.write(Path('/app/var/photos/persistence-test.bin').read_bytes())"])
        assert restored_bytes==b'TEST\x00\xff'
        results.append({'test':'TEST-10','status':'PASS','scope':'A distinct project, database and storage volume'})
        next_pkg=scratch/'next'
        build(next_pkg,version='0.1.1',source_sha=args.sha,app_image=args.app_image,web_image=args.web_image,channel='test',compatible_from=['0.1.0'],allow_dirty=True)
        run(['bash',next_pkg/'fixrate-install.sh','upgrade','--install-dir',directory,'--local-images']);ready(base)
        request(build_opener(),base,'/api/v1/auth/login',{'email':admin['email'],'password':password})
        upgraded_bytes=subprocess.check_output([*compose(directory),'run','--rm','--no-deps','-T','api','python','-c',"from pathlib import Path;import sys;sys.stdout.buffer.write(Path('/app/var/photos/persistence-test.bin').read_bytes())"])
        assert upgraded_bytes==b'TEST\x00\xff'
        results.append({'test':'TEST-09','status':'PASS','scope':'Declared package update; first-release code/schema baseline, not a production upgrade certification'})
        fault=scratch/'fault';fault.mkdir()
        (fault/'failure.sql').write_text("BEGIN; CREATE TABLE release_failure_canary(id int); DO $$ BEGIN RAISE EXCEPTION 'TEST failure'; END $$; COMMIT;\n")
        (fault/'Dockerfile').write_text(f'FROM {args.app_image}\nCOPY failure.sql /app/database/migrations/025_test_failure.sql\n')
        failure_image='fixrate-release-fault:'+args.sha
        run(['docker','build','-t',failure_image,fault])
        fail_pkg=scratch/'fail-package'
        build(fail_pkg,version='0.1.2',source_sha=args.sha,app_image=failure_image,web_image=args.web_image,channel='test',compatible_from=['0.1.1'],allow_dirty=True)
        failed=subprocess.run(['bash',str(fail_pkg/'fixrate-install.sh'),'upgrade','--install-dir',str(directory),'--local-images'])
        assert failed.returncode!=0
        running=subprocess.check_output([*compose(directory),'ps','--status','running','--services'],text=True).splitlines()
        assert not set(running).intersection({'api','worker','web'})
        canary=subprocess.check_output([*compose(directory),'exec','-T','db','psql','-U','fixrate','-d','fixrate','-Atc',"SELECT to_regclass('release_failure_canary') IS NULL"])
        assert canary.strip()==b't'
        results.append({'test':'TEST-11','status':'PASS','scope':'Injected migration failed atomically; installer stopped'})
        restore_point=sorted((directory/'backups').iterdir())[-1]
        run(['bash',installer,'restore','--install-dir',directory,'--backup-path',restore_point,'--confirm-data-replacement','--local-images']);ready(base)
        request(build_opener(),base,'/api/v1/auth/login',{'email':admin['email'],'password':password})
    finally:
        (args.output/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        for dc,env in quick_projects:
            subprocess.run([*dc,'down','--volumes','--remove-orphans'],stdout=subprocess.DEVNULL,env=env)
        for directory in installations:
            if (directory/'infrastructure.env').is_file() and (directory/'compose.yaml').is_file():
                assert directory.resolve().is_relative_to(scratch)
                subprocess.run([*compose(directory),'down','--volumes','--remove-orphans'],stdout=subprocess.DEVNULL)
        # Logs/configuration contain generated test secrets: do not upload scratch.
        shutil.rmtree(scratch)

if __name__=='__main__':main()
