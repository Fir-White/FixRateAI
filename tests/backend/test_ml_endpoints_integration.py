"""Real API/DB adapters, actual RF and actual CLIP or controlled missing weights.

No successful model response is mocked. The optional real-weights release profile
is independently required by scripts/verify_compose.py --ml-cache PATH.
"""
from contextlib import closing
from dataclasses import replace
import json
from uuid import UUID

import pytest
from sqlalchemy import text

from app.schemas.maintenance import ForecastResult,PhotoReviewResult
from tests.backend.test_runtime_integration import runtime,login,PREFIX,TASK,confirmed_preview_rule,image_bytes
from tests.backend.test_evidence_readiness import job,upload
from app.integration.demo import demo_id


def test_real_rf_endpoint_returns_and_persists_versioned_forecasts(confirmed_preview_rule):
    engine,app,_=confirmed_preview_rule
    assert app.state.forecaster is not None
    with closing(login(app,'dispatcher')) as client:
        revision=client.get(PREFIX+f'/ui/tasks/{TASK}').json()['task']['revision']
        response=client.post(PREFIX+f'/tasks/{TASK}/forecast',json=dict(expected_revision=revision))
    assert response.status_code==200,response.text
    run=response.json()['run']
    assert run['algorithmic']['status']=='ok' and run['ai']['status']=='ok'
    assert run['ai']['modelRef']=='synthetic_demo:rf:'+app.state.forecaster.artifact_sha256[:16]
    with engine.connect() as conn:
        rows=conn.execute(text('SELECT input_snapshot,output_snapshot FROM forecast_runs WHERE forecast_run_id IN (:a,:b)'),
            dict(a=UUID(run['ai']['resultId']),b=UUID(run['algorithmic']['resultId']))).all()
    assert len(rows)==2 and rows[0].input_snapshot==rows[1].input_snapshot
    canonical=[ForecastResult.model_validate_json(json.dumps(row.output_snapshot['canonical'])) for row in rows]
    assert {r.snapshot_sha256 for r in canonical}=={run['snapshotHash']}
    assert {r.method for r in canonical}=={'ai','algorithmic'}


def test_absent_rf_is_controlled_and_regulation_fallback_is_saved(confirmed_preview_rule):
    engine,app,_=confirmed_preview_rule
    original=app.state.forecaster
    app.state.forecaster=None
    try:
        with closing(login(app,'engineer')) as client:
            revision=client.get(PREFIX+f'/ui/tasks/{TASK}').json()['task']['revision']
            response=client.post(PREFIX+f'/tasks/{TASK}/forecast',json=dict(expected_revision=revision))
        assert response.status_code==200,response.text
        run=response.json()['run']
        assert run['ai']['status']=='unavailable' and run['ai']['errorCode']=='MODEL_NOT_READY'
        assert run['ai']['modelRef'] is None and run['ai']['recommendedDate'] is None
        assert run['decision']['status']=='fallback'
        assert run['decision']['selectedDate']==run['algorithmic']['recommendedDate']
        with engine.connect() as conn:
            canonical=conn.scalar(text('SELECT output_snapshot FROM forecast_runs WHERE forecast_run_id=:id'),dict(id=UUID(run['ai']['resultId'])))['canonical']
        assert ForecastResult.model_validate_json(json.dumps(canonical)).error_code=='MODEL_NOT_READY'
    finally:
        app.state.forecaster=original


def submitted_pair(job,extra=False):
    _,app,task,_=job
    with closing(login(app,'executor')) as client:
        response=client.put(PREFIX+f'/tasks/{task}/report',json=dict(expected_revision=1,narrative='ML service integration',answers={str(demo_id('runtime-checklist')):'done'}))
        assert response.status_code==200,response.text
        bundle=response.json()
        for phase,seed in [('before',510),('after',511)]+([('before',512)] if extra else []):
            response=upload(client,task,bundle['task']['revision'],'photo.png',image_bytes(seed),'image/png',phase)
            assert response.status_code==200,response.text
            bundle=response.json()
        response=client.post(PREFIX+f'/tasks/{task}/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==200,response.text
        return response.json()


def test_real_cv_adapter_with_missing_local_weights_returns_persisted_unavailable(job,monkeypatch):
    from ml_service.app.cv.classifier import CLIPZeroShotClassifier
    _,app,task,report=job
    engine=job[0]
    bundle=submitted_pair(job)
    # Actual classifier with an intentionally absent LOCAL artifact; no response/provider stub.
    monkeypatch.setattr('ml_service.app.cv.service._CLASSIFIER',CLIPZeroShotClassifier(model_name='fixrate-missing-local-weights',revision='missing'))
    with closing(login(app,'engineer')) as client:
        response=client.post(PREFIX+f'/tasks/{task}/photo-review',json=dict(expected_revision=bundle['task']['revision']))
    assert response.status_code==200,response.text
    assert response.json()['status']=='unavailable' and response.json()['errorCode']=='MODEL_NOT_READY'
    assert response.json()['modelRef'] is None
    with engine.connect() as conn:
        saved=conn.scalar(text('SELECT findings FROM ai_quality_checks WHERE work_report_id=:id'),dict(id=report))['canonical']
        assert conn.scalar(text('SELECT status FROM work_orders WHERE work_order_id=:id'),dict(id=task))=='in_review'
    canonical=PhotoReviewResult.model_validate_json(json.dumps(saved))
    assert canonical.status=='unavailable' and not canonical.item_results and canonical.model_ref is None


@pytest.mark.parametrize('limit',['files','bytes'])
def test_photo_review_batch_limit_rejected_before_model_and_database_write(job,monkeypatch,limit):
    engine,app,task,_=job
    bundle=submitted_pair(job,extra=True)
    original=app.state.settings
    app.state.settings=replace(original,photo_review_max_files=2) if limit=='files' else replace(original,photo_review_max_bytes=1)
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append(True)
        raise RuntimeError('Model must not receive oversized batch')
    monkeypatch.setattr('ml_service.app.cv.api.review_photos',forbidden)
    try:
        with closing(login(app,'engineer')) as client:
            response=client.post(PREFIX+f'/tasks/{task}/photo-review',json=dict(expected_revision=bundle['task']['revision']))
        assert response.status_code==413 and response.json()['error']['code']=='PHOTO_REVIEW_LIMIT_EXCEEDED'
        assert not calls
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT count(*) FROM ai_quality_checks WHERE work_order_id=:id'),dict(id=task))==0
            assert conn.scalar(text('SELECT revision FROM work_orders WHERE work_order_id=:id'),dict(id=task))==bundle['task']['revision']
    finally:
        app.state.settings=original


def test_forecast_http_honors_configured_deadline_and_keeps_regulatory_date(confirmed_preview_rule,monkeypatch):
    from threading import Event
    _,app,_=confirmed_preview_rule
    release=Event()
    original=app.state.settings
    app.state.settings=replace(original,forecast_timeout_seconds=.01)
    def slow(*args,**kwargs):
        release.wait(.5)
        return None
    monkeypatch.setattr('ml_service.app.forecast.client.predict_maintenance_ai',slow)
    try:
        with closing(login(app,'dispatcher')) as client:
            revision=client.get(PREFIX+f'/ui/tasks/{TASK}').json()['task']['revision']
            response=client.post(PREFIX+f'/tasks/{TASK}/forecast',json=dict(expected_revision=revision))
        assert response.status_code==200,response.text
        run=response.json()['run']
        assert run['ai']['errorCode']=='TIMEOUT' and run['ai']['recommendedDate'] is None
        assert run['decision']['status']=='fallback'
        assert run['decision']['selectedDate']==run['algorithmic']['recommendedDate']
    finally:
        release.set()
        app.state.settings=original
