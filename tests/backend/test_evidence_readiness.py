"""Actual ASGI/PostgreSQL/private-files tests; injected providers are test-only."""
from contextlib import closing
from dataclasses import replace
import hashlib
import io
from pathlib import Path
from threading import Event
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import text

from app.integration.demo import demo_id
from tests.backend.test_runtime_integration import runtime,login,PREFIX,TASK,isolated_order,image_bytes
from tests.backend.test_management import managed

@pytest.fixture
def job(runtime):
    engine,app=runtime
    task,report=isolated_order(engine,'in_progress')
    with engine.begin() as conn:
        conn.execute(text("UPDATE work_orders SET maintenance_rule_id=(SELECT maintenance_rule_id FROM work_orders WHERE work_order_id=:source), norm_hours_basis_snapshot='total_person_hours' WHERE work_order_id=:id"),dict(source=UUID(TASK),id=task))
    try:
        yield engine,app,task,report
    finally:
        with engine.begin() as conn:
            keys=list(conn.scalars(text('SELECT storage_key FROM evidence_files WHERE work_order_id=:id'),dict(id=task)))
            for table in ('evidence_files','checklist_results','acceptance_reviews','ai_quality_checks','work_reports','work_assignments','work_order_equipment'):
                conn.execute(text(f'DELETE FROM {table} WHERE work_order_id=:id'),dict(id=task))
            conn.execute(text('DELETE FROM audit_events WHERE entity_id=:id'),dict(id=task))
            conn.execute(text('DELETE FROM work_orders WHERE work_order_id=:id'),dict(id=task))
        for key in keys:
            path=(app.state.settings.photo_storage_root/key).resolve()
            assert path.is_relative_to(app.state.settings.photo_storage_root)
            path.unlink(missing_ok=True)

def upload(client,task,revision,name,blob,mime,phase='before'):
    return client.post(PREFIX+f'/tasks/{task}/photos',data=dict(expected_revision=revision,
        checklist_item_id=str(demo_id('runtime-checklist')),phase=phase,view_key='front'),files=dict(file=(name,blob,mime)))

def state(engine,task):
    with engine.connect() as c:
        return (c.execute(text('SELECT status,revision FROM work_orders WHERE work_order_id=:id'),dict(id=task)).one(),
            c.scalar(text('SELECT count(*) FROM evidence_files WHERE work_order_id=:id'),dict(id=task)),
            c.scalar(text('SELECT count(*) FROM audit_events WHERE entity_id=:id'),dict(id=task)))

@pytest.mark.parametrize('name,mime,kind', [('photo.exe','image/png','png'),('photo.jpg','image/jpeg','png'),
    ('photo.png','application/octet-stream','png'),('../photo.png','image/png','png'),
    ('..\\photo.png','image/png','png'),('photo','image/png','png'),('bad.png','image/png','invalid'),
    ('empty.png','image/png','empty'),('huge.png','image/png','oversize')])
def test_upload_rejects_unsafe_or_mismatched_files_atomically(job,name,mime,kind):
    engine,app,task,_=job
    blob={'invalid':b'not-an-image','empty':b'','oversize':b'x'*10_485_761}.get(kind,image_bytes(410))
    before=state(engine,task)
    with closing(login(app,'executor')) as client:
        response=upload(client,task,1,name,blob,mime)
    assert response.status_code==422,response.text
    assert state(engine,task)==before

@pytest.mark.parametrize('fmt,ext,mime',[('JPEG','jpg','image/jpeg'),('PNG','png','image/png'),('WEBP','webp','image/webp')])
def test_valid_evidence_is_private_and_metadata_matches_bytes(job,fmt,ext,mime):
    engine,app,task,report=job
    stream=io.BytesIO(); Image.new('RGB',(32,32),'green').save(stream,format=fmt); blob=stream.getvalue()
    with closing(login(app,'executor')) as client:
        response=upload(client,task,1,'client-name.'+ext,blob,mime)
        assert response.status_code==200,response.text
        photo=response.json()['execution']['photos'][0]
        content=client.get(photo['url'])
        assert content.status_code==200 and content.content==blob
        assert content.headers['cache-control']=='private, no-store'
        assert content.headers['x-content-type-options']=='nosniff'
        with closing(TestClient(app)) as anonymous:
            assert anonymous.get(photo['url']).status_code==401
    with engine.connect() as c:
        row=c.execute(text('SELECT work_order_id,work_report_id,storage_key,mime_type,file_size,sha256 FROM evidence_files WHERE evidence_file_id=:id'),dict(id=UUID(photo['id']))).mappings().one()
    assert row['work_order_id']==task and row['work_report_id']==report
    assert row['mime_type']==mime and row['file_size']==len(blob) and row['sha256'].strip()==hashlib.sha256(blob).hexdigest()
    assert 'client-name' not in row['storage_key'] and UUID(row['storage_key'].split('/')[-1])==UUID(photo['id'])


def test_storage_failure_is_safe_503_and_does_not_change_database(job,monkeypatch,caplog):
    engine,app,task,_=job
    before=state(engine,task)
    def denied(*args,**kwargs): raise PermissionError('private-storage-token')
    with closing(login(app,'executor')) as client:
        with monkeypatch.context() as patch:
            patch.setattr(Path,'write_bytes',denied)
            response=upload(client,task,1,'photo.png',image_bytes(411),'image/png')
    assert response.status_code==503 and response.json()['error']['code']=='PHOTO_STORAGE_UNAVAILABLE'
    assert state(engine,task)==before
    assert 'private-storage-token' not in response.text+caplog.text


def submit_pair(job):
    engine,app,task,_=job
    with closing(login(app,'executor')) as client:
        response=client.put(PREFIX+f'/tasks/{task}/report',json=dict(expected_revision=1,narrative='Actual evidence',answers={str(demo_id('runtime-checklist')):'done'}))
        assert response.status_code==200,response.text
        bundle=response.json()
        for phase in ('before','after'):
            response=upload(client,task,bundle['task']['revision'],'photo.png',image_bytes(412),'image/png',phase)
            assert response.status_code==200,response.text
            bundle=response.json()
        response=client.post(PREFIX+f'/tasks/{task}/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==200,response.text
        return response.json()


def test_corrupt_persisted_photo_is_rejected_before_calling_ai(job,monkeypatch):
    engine,app,task,_=job
    bundle=submit_pair(job)
    with engine.connect() as c:
        key=c.scalar(text('SELECT storage_key FROM evidence_files WHERE work_order_id=:id LIMIT 1'),dict(id=task))
    (app.state.settings.photo_storage_root/key).write_bytes(b'corrupt-stored-image')
    def forbidden(*args,**kwargs): pytest.fail('AI must not receive corrupt evidence')
    monkeypatch.setattr('ml_service.app.cv.api.review_photos',forbidden)
    with closing(login(app,'engineer')) as client:
        response=client.post(PREFIX+f'/tasks/{task}/photo-review',json=dict(expected_revision=bundle['task']['revision']))
    assert response.status_code==422 and response.json()['error']['code']=='PHOTO_CONTENT_INVALID'
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM ai_quality_checks WHERE work_order_id=:id'),dict(id=task))==0


@pytest.mark.parametrize('failure,code',[('exception','PROVIDER_ERROR'),('timeout','TIMEOUT'),('invalid','INVALID_RESPONSE')])
def test_photo_provider_failures_are_persisted_without_accepting_work(job,monkeypatch,failure,code,caplog):
    engine,app,task,_=job
    bundle=submit_pair(job)
    release=Event()
    original=app.state.settings
    app.state.settings=replace(original,photo_review_timeout_seconds=.01)
    def broken(*args,**kwargs):
        if failure=='timeout': release.wait(2)
        if failure=='exception': raise RuntimeError('private-provider-token')
        return '{invalid}'
    monkeypatch.setattr('ml_service.app.cv.api.review_photos',broken)
    try:
        with closing(login(app,'engineer')) as client:
            response=client.post(PREFIX+f'/tasks/{task}/photo-review',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==200,response.text
        assert response.json()['status']=='failed' and response.json()['errorCode']==code
        assert response.json()['modelRef'] is None
        with engine.connect() as c:
            result=c.execute(text('SELECT status,findings FROM ai_quality_checks WHERE work_order_id=:id'),dict(id=task)).one()
            assert result.status=='failed' and result.findings['canonical']['error_code']==code
            assert result.findings['canonical']['item_results']==[]
            assert c.execute(text('SELECT status,revision FROM work_orders WHERE work_order_id=:id'),dict(id=task)).one()==('in_review',bundle['task']['revision'])
        assert 'private-provider-token' not in response.text+caplog.text+str(result.findings)
    finally:
        release.set()
        app.state.settings=original


def test_evidence_from_another_site_is_hidden(job,managed):
    _,app,task,_=job
    _,_,other_admin,_,_=managed
    with closing(login(app,'executor')) as client:
        response=upload(client,task,1,'photo.png',image_bytes(413),'image/png')
        assert response.status_code==200,response.text
        url=response.json()['execution']['photos'][0]['url']
    assert other_admin.get(url).status_code==404
