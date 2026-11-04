"""Local vision safety and transport unit tests; model replies here are explicit fixtures."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from ml_service.app.cv.local_vision import (LocalVisionClient, LocalVisionConfig, ProviderFailure, review_local_photos)
from ml_service.app.schemas import VisualAssessment
from tests.ml.test_cv import make_test_jpeg

CONFIG = LocalVisionConfig("http://127.0.0.1:11434", "qwen3-vl:4b-instruct", "sha256:"+"0"*64)


def assessment(**changes):
    data = dict(subject_matches_task="yes", same_subject="yes", comparable="yes",
                before_description="Тестовое описание до", after_description="Тестовое описание после",
                visible_changes=["Тестовое изменение поверхности"], concerns=[],
                recommended_actions=["Проверить поверхность инженером"], cannot_confirm=["Скрытые работы не видны"],
                conclusion="visible_improvement", summary="Тестовый вывод модели")
    data.update(changes)
    return VisualAssessment.model_validate(data)


class FixtureClient:
    calls = 0
    def __init__(self, reply=None, error=None):
        self.reply = reply or assessment()
        self.error = error
        self.calls = 0
    def check_model(self):
        if self.error:
            raise ProviderFailure(self.error)
    def assess(self, *args):
        self.calls += 1
        return self.reply


def photos(request):
    return {request.photos[0].photo_id: make_test_jpeg("dirty"),
            request.photos[1].photo_id: make_test_jpeg("clean_serviced")}


def invoke(request, client, **kwargs):
    storage = photos(request)
    return review_local_photos(request, storage.__getitem__, config=CONFIG, client=client,
                               comparability_confirmed=lambda b,a: True, **kwargs)


def test_structured_observations_and_versions_are_retained(canonical_photo_review_request):
    result = invoke(canonical_photo_review_request, FixtureClient())
    assert result.status == "completed"
    assert result.model_ref == CONFIG.model_ref
    assert result.item_results[0].visual_assessment.before_description == "Тестовое описание до"
    assert result.item_results[0].scores == []  # Never invent CLIP scores or calibrated confidence.
    assert result.item_results[0].verdict == "visible_change"


@pytest.mark.parametrize("field", ["subject_matches_task", "same_subject", "comparable"])
def test_wrong_object_or_incomparable_pair_cannot_confirm_work(canonical_photo_review_request, field):
    result = invoke(canonical_photo_review_request, FixtureClient(assessment(**{field:"no"})))
    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "uncertain"
    assert result.item_results[0].visual_assessment is not None


def test_human_comparability_confirmation_is_still_required(canonical_photo_review_request):
    request=canonical_photo_review_request
    result=review_local_photos(request, photos(request).__getitem__, config=CONFIG, client=FixtureClient())
    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "uncertain"


def test_no_change_is_not_a_green_success(canonical_photo_review_request):
    result=invoke(canonical_photo_review_request, FixtureClient(assessment(conclusion="no_clear_improvement",visible_changes=[])))
    assert result.status == "uncertain"
    assert result.item_results[0].verdict == "no_visible_change"


@pytest.mark.parametrize("code,status", [("LOCAL_VISION_UNAVAILABLE","unavailable"),
    ("LOCAL_VISION_MODEL_NOT_READY","unavailable"),("LOCAL_VISION_MODEL_CHANGED","failed"),
    ("LOCAL_VISION_INVALID_RESPONSE","failed")])
def test_local_model_failure_has_no_fake_fallback(canonical_photo_review_request,code,status):
    result=invoke(canonical_photo_review_request,FixtureClient(error=code))
    assert result.status==status and result.error_code==code
    assert result.model_ref is None and not result.item_results


def test_identical_photos_do_not_call_model(canonical_photo_review_request):
    request=canonical_photo_review_request; client=FixtureClient();blob=make_test_jpeg("dirty")
    result=review_local_photos(request,lambda _:blob,config=CONFIG,client=client)
    assert result.status=="uncertain" and client.calls==0
    assert result.item_results[0].visual_assessment is None


def test_hidden_work_does_not_call_model(canonical_photo_review_request):
    request=canonical_photo_review_request.model_copy(deep=True)
    request.operation.code="1.5";client=FixtureClient()
    result=invoke(request,client)
    assert result.status=="not_verifiable" and client.calls==0


@pytest.mark.parametrize("url", ["https://api.example.test","http://example.test","http://vision.evil.test",
    "http://user:pass@127.0.0.1:11434","http://localhost:11434/path","http://localhost:11434?redirect=cloud"])
def test_external_endpoints_are_rejected(monkeypatch,url):
    monkeypatch.setenv("OLLAMA_BASE_URL",url)
    with pytest.raises(ValueError,match="local vision service"):
        LocalVisionConfig.from_environment()


def test_cloud_tag_is_rejected(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL","http://localhost:11434")
    monkeypatch.setenv("OLLAMA_VISION_MODEL","qwen3-vl:235b-cloud")
    with pytest.raises(ValueError,match="explicit local"):
        LocalVisionConfig.from_environment()


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        payload={"models":[]}
        redirect=False
        def do_GET(self):
            if self.redirect:
                self.send_response(302);self.send_header("Location","https://example.test/");self.end_headers();return
            body=json.dumps(self.payload).encode()
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=Thread(target=http.serve_forever,daemon=True);thread.start()
    try:yield http,Handler
    finally:http.shutdown();http.server_close();thread.join()


def test_real_local_http_refuses_model_digest_change_and_ignores_proxy(server,monkeypatch):
    http,handler=server
    handler.payload={"models":[dict(name=CONFIG.model,digest="sha256:"+"1"*64)]}
    monkeypatch.setenv("HTTP_PROXY","http://invalid.invalid:1")
    client=LocalVisionClient(LocalVisionConfig(f"http://127.0.0.1:{http.server_port}",CONFIG.model,CONFIG.digest))
    with pytest.raises(ProviderFailure,match="MODEL_CHANGED"):client.check_model()


def test_http_redirect_cannot_send_photos_outside_local_service(server):
    http,handler=server;handler.redirect=True
    client=LocalVisionClient(LocalVisionConfig(f"http://127.0.0.1:{http.server_port}",CONFIG.model,CONFIG.digest))
    with pytest.raises(ProviderFailure,match="REDIRECT_REJECTED"):client.request("/api/tags")


def test_truncated_generation_is_not_accepted(canonical_photo_review_request,monkeypatch):
    client=LocalVisionClient(CONFIG)
    monkeypatch.setattr(client,"request",lambda *args:dict(done=True,done_reason="length",model=CONFIG.model,message=dict(content=assessment().model_dump_json())))
    request=canonical_photo_review_request;storage=photos(request)
    with pytest.raises(ProviderFailure,match="INVALID_RESPONSE"):
        client.assess(request,request.operation.checklist[0],*storage.values())


def test_model_pin_accepts_ollama_bare_sha256_hex(server):
    http,handler=server
    handler.payload={"models":[dict(name=CONFIG.model,digest=CONFIG.digest.removeprefix("sha256:"))]}
    client=LocalVisionClient(LocalVisionConfig(f"http://127.0.0.1:{http.server_port}",CONFIG.model,CONFIG.digest))
    client.check_model()


def test_independent_photo_observations_are_not_overwritten_by_comparison(canonical_photo_review_request,monkeypatch):
    client=LocalVisionClient(CONFIG);calls=[]
    contents=iter([
        json.dumps(dict(description="До: на стекле видны линии повреждения",visible_defects=["Линии на стекле"],uncertain_features=[])),
        json.dumps(dict(description="После: стекло снято крупным планом",visible_defects=[],uncertain_features=["Причина изменения не установлена"])),
        assessment(before_description="Одинаковый текст",after_description="Одинаковый текст").model_dump_json(),
    ])
    def response(path,payload):
        calls.append(payload)
        return dict(done=True,done_reason="stop",model=CONFIG.model,message=dict(content=next(contents)))
    monkeypatch.setattr(client,"request",response)
    request=canonical_photo_review_request
    result=client.assess(request,request.operation.checklist[0],*photos(request).values())
    assert result.before_description=="До: на стекле видны линии повреждения"
    assert result.after_description=="После: стекло снято крупным планом"
    assert [len(call["messages"][-1]["images"]) for call in calls]==[1,1,2]
    assert all(call["keep_alive"]==-1 for call in calls)
