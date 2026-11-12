"""Real HTTP/PostgreSQL/storage; ML response is an explicit contract stub, not cloud inference."""
from contextlib import closing
from datetime import datetime,timezone
from uuid import uuid4
import pytest
from sqlalchemy import text
from app.schemas.maintenance import PhotoReviewResult
from tests.backend.test_runtime_integration import runtime,isolated_order,login,image_bytes,PREFIX,TASK


def prepare(runtime,client,pair=True):
    engine,_=runtime
    task,_=isolated_order(engine,'in_progress')
    with engine.begin() as c:
        c.execute(text("UPDATE work_orders SET maintenance_rule_id=(SELECT maintenance_rule_id FROM work_orders WHERE work_order_id=:source),regulatory_deadline_at=now()+interval '1 day' WHERE work_order_id=:task"),dict(source=TASK,task=task))
    endpoint=PREFIX+f'/tasks/{task}'
    bundle=client.get(PREFIX+f'/ui/tasks/{task}').json()
    item=bundle['execution']['checklist'][0]['id']
    bundle=client.put(endpoint+'/report',json=dict(expected_revision=bundle['task']['revision'],narrative='TEST automatic photo review',answers={item:'done'})).json()
    for phase in (('before','after') if pair else ('before',)):
        response=client.post(endpoint+'/photos',data=dict(expected_revision=bundle['task']['revision'],checklist_item_id=item,phase=phase,view_key='front'),files={'file':(phase+'.png',image_bytes(172),'image/png')})
        assert response.status_code==200,response.text
        bundle=response.json()
    return task,endpoint,bundle


def install_stub(monkeypatch,fail=False):
    calls=[]
    def invoke(request,loader,**kwargs):
        calls.append(request)
        assert kwargs['comparability_confirmed'](request.photos[0],request.photos[1]) is False
        assert all(loader(p.photo_id) for p in request.photos)
        if fail:raise RuntimeError('TEST inference failure')
        return PhotoReviewResult(schema_version=request.schema_version,data_origin=request.data_origin,ai_review_id=uuid4(),
            execution_id=request.execution_id,operation_version_id=request.operation.operation_version_id,status='uncertain',
            model_ref='test-contract-stub',prompt_set_version=request.prompt_set_version,input_photo_ids=[p.photo_id for p in request.photos],
            item_results=[],limitations=['TEST ONLY: stubbed ML response'],error_code=None,elapsed_ms=1,created_at=datetime.now(timezone.utc))
    monkeypatch.setattr('ml_service.app.cv.api.invoke_review',invoke)
    return calls


@pytest.mark.parametrize('through_transition',[False,True])
def test_submission_automatically_runs_contract_stub_once_without_methodology_or_engineer(runtime,monkeypatch,through_transition):
    engine,app=runtime;calls=install_stub(monkeypatch)
    worker=app.state.automatic_photo_review;arguments=[]
    def capture(*args):arguments.append(args);return worker(*args)
    monkeypatch.setitem(app.state._state,'automatic_photo_review',capture)
    with closing(login(app,'executor')) as client:
        task,endpoint,bundle=prepare(runtime,client)
        payload=dict(expected_revision=bundle['task']['revision'])
        target=endpoint+'/submit'
        if through_transition:target=f'/api/v1/maintenance_jobs/{task}/transitions';payload['status']='submitted'
        response=client.post(target,json=payload)
        assert response.status_code==200,response.text
        assert len(calls)==1
        current=client.get(PREFIX+f'/ui/tasks/{task}').json()
        assert current['photoAnalysisStatus']=='ready' and current['review']['modelRef']=='test-contract-stub'
        assert current['task']['state']=='submitted' and current['decision'] is None
        assert client.post(target,json=payload).status_code==409
        worker(*arguments[0]);assert len(calls)==1
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM ai_quality_checks WHERE work_order_id=:id'),{'id':task})==1


def test_background_inference_error_is_saved_and_does_not_undo_submission(runtime,monkeypatch):
    _,app=runtime;calls=install_stub(monkeypatch,fail=True)
    with closing(login(app,'executor')) as client:
        task,endpoint,bundle=prepare(runtime,client)
        response=client.post(endpoint+'/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==200,response.text
        current=client.get(PREFIX+f'/ui/tasks/{task}').json()
        assert len(calls)==1 and current['photoAnalysisStatus']=='failed'
        assert current['review']['errorCode']=='AUTO_PHOTO_REVIEW_FAILED'
        assert current['task']['state']=='submitted' and current['decision'] is None


def test_recovery_only_runs_explicit_new_submission_queue_not_historical_reports(runtime,monkeypatch):
    from app.integration.scheduler import tick
    engine,app=runtime;calls=[]
    monkeypatch.setitem(app.state._state,'automatic_photo_review',lambda *args:calls.append(args))
    historical,_=isolated_order(engine,'in_review')
    with closing(login(app,'executor')) as client:
        task,endpoint,bundle=prepare(runtime,client)
        response=client.post(endpoint+'/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==200 and len(calls)==1
        assert client.get(PREFIX+f'/ui/tasks/{task}').json()['photoAnalysisStatus']=='pending'
        with engine.begin() as c:c.execute(text("UPDATE work_reports SET submitted_at=now()-interval '2 minutes' WHERE work_order_id=:id"),{'id':task})
        calls.clear();tick(app)
        assert [args[0] for args in calls]==[task]
        assert historical not in [args[0] for args in calls]


def test_incomplete_pair_never_triggers_analysis(runtime,monkeypatch):
    _,app=runtime;calls=install_stub(monkeypatch)
    with closing(login(app,'executor')) as client:
        task,endpoint,bundle=prepare(runtime,client,pair=False)
        response=client.post(endpoint+'/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==422
        assert not calls
        assert client.get(PREFIX+f'/ui/tasks/{task}').json()['photoAnalysisStatus']=='not_requested'
