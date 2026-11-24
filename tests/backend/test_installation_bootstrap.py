"""Real PostgreSQL first-install race, closure and existing-user protection."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db.session import make_engine
from app.installation import FirstAdministrator, arm_bootstrap, create_first_administrator
from app.manage import migrate
from app.main import create_app
from app.security.sessions import verify_password


@pytest.fixture
def installation(monkeypatch):
    value=os.environ.get('INTEGRATION_DATABASE_URL')
    if not value:pytest.skip('Disposable PostgreSQL runner required')
    url=make_url(value)
    assert url.database.startswith('fixrate_test_')
    import psycopg
    from psycopg import sql
    name='fixrate_test_install_'+uuid4().hex
    connection=psycopg.connect(host=url.host,port=url.port,user=url.username,password=url.password,dbname='postgres',autocommit=True)
    connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    engine=make_engine(url.set(database=name).render_as_string(hide_password=False))
    token=uuid4().hex+uuid4().hex
    monkeypatch.setenv('FIXRATE_BOOTSTRAP_TOKEN_SHA256',hashlib.sha256(token.encode()).hexdigest())
    migrate(engine);arm_bootstrap(engine)
    try:yield engine,token
    finally:
        engine.dispose()
        connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        connection.close()


def command(**changes):
    values=dict(organization_name='TEST organization',site_name='TEST building',
        full_name='TEST administrator',email='admin@example.test',password='Test-only-Secret-2026')
    values.update(changes)
    return FirstAdministrator(**values)


def test_default_site_timezone_from_environment(monkeypatch):
    monkeypatch.delenv('FIXRATE_DEFAULT_TIMEZONE', raising=False)
    assert command().timezone == 'Asia/Yekaterinburg'
    monkeypatch.setenv('FIXRATE_DEFAULT_TIMEZONE', 'Europe/Moscow')
    assert command().timezone == 'Europe/Moscow'
    assert command(timezone='UTC').timezone == 'UTC'
    monkeypatch.setenv('FIXRATE_DEFAULT_TIMEZONE', 'Not/AZone')
    with pytest.raises(ValueError, match='Неизвестный часовой пояс'):
        command()


def test_wrong_secret_is_denied_without_partial_data(installation):
    engine,token=installation
    with pytest.raises(HTTPException) as error:create_first_administrator(engine,command(),'wrong-token')
    assert error.value.status_code==403
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM users'))==0
        assert conn.scalar(text('SELECT count(*) FROM sites'))==0


def test_first_admin_and_repeat_are_atomic_and_preserve_data(installation):
    engine,token=installation
    assert create_first_administrator(engine,command(),token)['status']=='created'
    arm_bootstrap(engine);migrate(engine)
    with pytest.raises(HTTPException) as error:create_first_administrator(engine,command(),token)
    assert error.value.status_code==409
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM users'))==1
        assert conn.scalar(text('SELECT role FROM site_memberships'))=='admin'
        assert verify_password('Test-only-Secret-2026',conn.scalar(text('SELECT password_hash FROM users')))
        assert conn.scalar(text('SELECT bootstrap_token_hash FROM fixrate_installation')) is None


def test_parallel_bootstrap_creates_exactly_one_admin(installation):
    engine,token=installation
    def submit(_):
        try:return create_first_administrator(engine,command(),token)['status']
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,range(2)))
    assert sorted(map(str,results))==['409','created']
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM users'))==1
        assert conn.scalar(text('SELECT count(*) FROM sites'))==1


def test_failed_bootstrap_rolls_back_every_row_and_keeps_token(installation):
    from sqlalchemy import event
    engine,token=installation
    def fail_audit(conn,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO audit_events'):raise RuntimeError('Injected failure')
    event.listen(engine,'before_cursor_execute',fail_audit)
    try:
        with pytest.raises(RuntimeError):create_first_administrator(engine,command(),token)
    finally:event.remove(engine,'before_cursor_execute',fail_audit)
    with engine.connect() as conn:
        assert not conn.connection.driver_connection.autocommit
        assert conn.scalar(text('SELECT count(*) FROM users'))==0
        assert conn.scalar(text('SELECT count(*) FROM sites'))==0
        assert conn.scalar(text('SELECT completed_at FROM fixrate_installation')) is None
    assert create_first_administrator(engine,command(),token)['status']=='created'


def test_existing_pending_account_seals_bootstrap(installation):
    engine,token=installation
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users(full_name,email) VALUES ('Existing account','existing@example.test')"))
    arm_bootstrap(engine)
    with pytest.raises(HTTPException) as error:create_first_administrator(engine,command(),token)
    assert error.value.status_code==409


def test_http_setup_login_and_regular_staff_enrollment(installation):
    engine,token=installation
    with TestClient(create_app(engine)) as client:
        assert client.get('/api/setup').json()=={'required':True}
        created=client.post('/api/setup',json=command().model_dump(),headers={'X-FixRate-Setup-Token':token})
        assert created.status_code==201,created.text
        assert token not in created.text and 'Test-only-Secret' not in created.text
        assert client.get('/api/setup').json()=={'required':False}
        assert client.post('/api/setup',json=command().model_dump(),headers={'X-FixRate-Setup-Token':token}).status_code==409
        login=client.post('/api/v1/auth/login',json={'email':'admin@example.test','password':'Test-only-Secret-2026'})
        assert login.status_code==200,login.text
        client.headers['X-CSRF-Token']=login.json()['csrfToken']
        code=client.post('/api/v1/maintenance/management/enrollment').json()['code']
        registered=client.post('/api/v1/auth/register',json={'full_name':'TEST technician','email':'worker@example.test','password':'Worker-only-Secret-2026','company_code':code})
        assert registered.status_code==201,registered.text
        applications=client.get('/api/v1/maintenance/management/workforce').json()['applications']
        assert len(applications)==1
        row=applications[0]
        accepted=client.post('/api/v1/maintenance/management/applications/'+row['application_id']+'/decision',json={'expected_revision':row['revision'],'role':'executor','is_active':True,'decision':'accepted'})
        assert accepted.status_code==200,accepted.text
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM site_memberships WHERE role='executor'"))==1


def test_invalid_configuration_and_whitespace_are_rejected(installation,monkeypatch):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):command(organization_name='   ')
    engine,_=installation
    monkeypatch.setenv('FIXRATE_BOOTSTRAP_TOKEN_SHA256','not-a-hash')
    with pytest.raises(ValueError):arm_bootstrap(engine)


def test_upgrade_from_populated_023_never_opens_initial_registration(installation):
    engine,token=installation
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE fixrate_installation'))
        conn.execute(text("DELETE FROM fixrate_schema_migrations WHERE filename='024_installation_bootstrap.sql'"))
        conn.execute(text("INSERT INTO users(full_name,email) VALUES ('TEST existing','existing@example.test')"))
    migrate(engine);arm_bootstrap(engine)
    with pytest.raises(HTTPException) as error:create_first_administrator(engine,command(),token)
    assert error.value.status_code==409
    with engine.connect() as conn:assert conn.scalar(text('SELECT count(*) FROM users'))==1


def test_operator_recovery_rotates_existing_admin_and_revokes_sessions(installation,monkeypatch):
    from sqlalchemy.orm import Session
    from app.security.sessions import create_session
    from scripts.release_runtime import main
    import sys
    engine,token=installation
    create_first_administrator(engine,command(),token)
    with engine.connect() as conn:row=conn.execute(text('SELECT user_id,site_id FROM site_memberships')).mappings().one()
    with Session(engine) as session,session.begin():create_session(session,row['user_id'],row['site_id'])
    monkeypatch.setattr('app.db.session.make_engine',lambda:engine)
    monkeypatch.setattr('getpass.getpass',lambda _: 'Recovery-test-password-2026')
    monkeypatch.setattr(sys,'argv',['release_runtime.py','recover-admin','--email','admin@example.test','--confirm-data-replacement'])
    main()
    with engine.connect() as conn:
        assert verify_password('Recovery-test-password-2026',conn.scalar(text('SELECT password_hash FROM users')))
        assert conn.scalar(text('SELECT count(*) FROM fixrate_sessions'))==0
        assert conn.scalar(text("SELECT count(*) FROM audit_events WHERE action='operator_password_recovery'"))==1


def test_native_database_and_files_restore_to_another_environment(installation,tmp_path):
    import io
    from pathlib import Path
    import shutil
    import subprocess
    import psycopg
    from psycopg import sql
    from scripts.release_runtime import files_export,files_restore
    engine,token=installation
    binaries=Path('C:/Program Files/PostgreSQL/18/bin') if os.name=='nt' else Path(shutil.which('pg_dump') or '/missing').parent
    dump=binaries/('pg_dump.exe' if os.name=='nt' else 'pg_dump')
    restore=binaries/('pg_restore.exe' if os.name=='nt' else 'pg_restore')
    if not dump.is_file() or '18.' not in subprocess.check_output([str(dump),'--version'],text=True):
        pytest.skip('Native PostgreSQL 18 client binaries are required for this additional check')
    create_first_administrator(engine,command(),token)
    url=engine.url;name='fixrate_test_restore_'+uuid4().hex
    env=dict(os.environ,PGPASSWORD=url.password or '')
    flags=['-h',url.host,'-p',str(url.port),'-U',url.username,'-w']
    backup=tmp_path/'database.dump'
    subprocess.run([str(dump),*flags,'-d',url.database,'-Fc','-f',str(backup)],env=env,check=True,capture_output=True)
    files=tmp_path/'original';files.mkdir();(files/'report.bin').write_bytes(b'TEST\x00\xff')
    stream=io.BytesIO();files_export(files,stream);stream.seek(0)
    connection=psycopg.connect(host=url.host,port=url.port,user=url.username,password=url.password,dbname='postgres',autocommit=True)
    connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    restored_engine=make_engine(url.set(database=name).render_as_string(hide_password=False))
    try:
        subprocess.run([str(restore),*flags,'-d',name,'--exit-on-error','--single-transaction',str(backup)],env=env,check=True,capture_output=True)
        restored=tmp_path/'restored-files';restored.mkdir();files_restore(restored,stream)
        assert (restored/'report.bin').read_bytes()==b'TEST\x00\xff'
        with restored_engine.connect() as conn:
            assert verify_password('Test-only-Secret-2026',conn.scalar(text('SELECT password_hash FROM users')))
            assert conn.scalar(text('SELECT count(*) FROM site_memberships'))==1
            assert conn.scalar(text('SELECT completed_at IS NOT NULL FROM fixrate_installation'))
    finally:
        restored_engine.dispose()
        connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        connection.close()
