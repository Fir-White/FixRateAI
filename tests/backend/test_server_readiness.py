"""Server boundary unit checks; PostgreSQL integration lives in separate tests."""
from contextlib import closing
import logging

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.db.session import make_engine


def test_database_parameters_are_hidden_without_connecting():
    engine=make_engine('postgresql+psycopg://qa:private-password@127.0.0.1/qa')
    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


@pytest.mark.parametrize('origin,expected',[('http://testserver',200),('https://untrusted.example',403),('null',403)])
def test_same_origin_policy_covers_all_api_routes(origin,expected):
    app=create_app()
    @app.get('/api/qa-readiness')
    def readiness(): return {'ok':True}
    app.router.routes.insert(0,app.router.routes.pop())
    with closing(TestClient(app)) as client:
        result=client.get('/api/qa-readiness',headers={'Origin':origin})
    assert result.status_code==expected
    assert 'access-control-allow-origin' not in result.headers


def test_unexpected_api_error_has_safe_json_and_request_id(caplog):
    marker='readiness-test-private-token'
    app=create_app()
    @app.get('/api/qa-boom')
    def boom(): raise RuntimeError(marker)
    app.router.routes.insert(0,app.router.routes.pop())
    with caplog.at_level(logging.ERROR), closing(TestClient(app,raise_server_exceptions=False)) as client:
        result=client.get('/api/qa-boom')
    assert result.status_code==500
    assert result.headers.get('content-type','').startswith('application/json')
    assert result.json()['error']['code']=='INTERNAL_ERROR'
    assert result.json()['error']['request_id']==result.headers['X-Request-ID']
    assert marker not in result.text and marker not in caplog.text


@pytest.mark.parametrize('name,value', [('COOKIE_SECURE','tru'),('PHOTO_REVIEW_TIMEOUT_SECONDS','nan'),
    ('PHOTO_REVIEW_TIMEOUT_SECONDS','0'),('PHOTO_REVIEW_TIMEOUT_SECONDS','secret'),
    ('PHOTO_STORAGE_ROOT',''),('PHOTO_STORAGE_ROOT','frontend/dist/photos')])
def test_invalid_runtime_configuration_fails_without_echoing_values(monkeypatch,name,value):
    from app.config import RuntimeSettings
    monkeypatch.setenv(name,value)
    with pytest.raises(ValueError) as caught:
        RuntimeSettings.from_environment()
    assert name in str(caught.value)
    if value=='secret': assert value not in str(caught.value)


def test_private_storage_relative_to_repository(monkeypatch,tmp_path):
    from app.config import RuntimeSettings,ROOT
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PHOTO_STORAGE_ROOT','var/qa-photos')
    assert RuntimeSettings.from_environment().photo_storage_root==ROOT/'var/qa-photos'


def test_invalid_database_url_does_not_echo_secret():
    marker='private-dsn-token'
    with pytest.raises(ValueError) as caught:
        make_engine('postgresql+psycopg://user:'+marker+'@localhost:invalid/db')
    assert marker not in str(caught.value)


@pytest.mark.parametrize('name,value',[('FORECAST_TIMEOUT_SECONDS','nan'),('FORECAST_TIMEOUT_SECONDS','6'),
    ('FORECAST_TIMEOUT_SECONDS','0'),('PHOTO_REVIEW_MAX_FILES','1'),('PHOTO_REVIEW_MAX_FILES','101'),
    ('PHOTO_REVIEW_MAX_BYTES','0'),('PHOTO_REVIEW_MAX_BYTES','-1'),('PHOTO_REVIEW_MAX_BYTES','not-an-integer')])
def test_ml_runtime_limits_reject_invalid_values(monkeypatch,name,value):
    from app.config import RuntimeSettings
    monkeypatch.setenv(name,value)
    with pytest.raises(ValueError,match=name): RuntimeSettings.from_environment()


def test_ml_runtime_settings_use_explicit_environment_values(monkeypatch):
    from app.config import RuntimeSettings
    for key,value in dict(FORECAST_TIMEOUT_SECONDS='.125',PHOTO_REVIEW_TIMEOUT_SECONDS='40',
                          PHOTO_REVIEW_MAX_FILES='6',PHOTO_REVIEW_MAX_BYTES='1000000').items():
        monkeypatch.setenv(key,value)
    config=RuntimeSettings.from_environment()
    assert (config.forecast_timeout_seconds,config.photo_review_timeout_seconds,
            config.photo_review_max_files,config.photo_review_max_bytes)==(.125,40,6,1000000)



def test_photo_upload_and_ml_decode_limits_are_consistent():
    from app.files import MAX_BYTES,MAX_PIXELS
    from ml_service.app.core.config import settings
    assert (MAX_BYTES,MAX_PIXELS)==(settings.image_max_bytes,settings.image_max_pixels)
