"""Unit/HTTP contract tests. Replies here are fixtures, not real AI accuracy results."""
from dataclasses import replace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time

import pytest

from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig, AITunnelFailure
from ml_service.app.cv.aitunnel import AITunnelVisionClient, review_cloud_photos
from ml_service.app.cv.local_vision import ImageObservation
from ml_service.app.forecast.aitunnel import CloudRecommendation, predict_cloud_maintenance
from ml_service.app.forecast.synthetic import compute_snapshot_hash
from tests.ml.test_local_vision import assessment, photos

CONFIG = AITunnelConfig(model="qwen3.7-flash", api_key="unit-test-secret")
OBSERVATION = {"description": "Fixture image description", "visible_defects": [], "uncertain_features": []}


@pytest.fixture
def endpoint():
    state = {"calls": [], "status": 200, "payload": None, "delay": 0, "raw": None}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"].append((self.path, self.headers.get("Authorization"), body))
            if state["delay"]:
                time.sleep(state["delay"])
            self.send_response(state["status"])
            if state["status"] in (302, 307):
                self.send_header("Location", "https://example.test/leak")
            self.end_headers()
            try:
                payload = state["payload"] or {"model": CONFIG.model, "choices": [{"finish_reason": "stop",
                    "message": {"content": json.dumps(OBSERVATION), "reasoning": "Do not persist this"}}]}
                self.wfile.write(state["raw"] if state["raw"] is not None else json.dumps(payload).encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    yield state, replace(CONFIG, base_url=f"http://127.0.0.1:{server.server_port}/v1")
    server.shutdown(); server.server_close(); thread.join()


def test_real_http_multipart_auth_model_schema_and_no_reasoning_persistence(endpoint):
    state, config = endpoint
    client = AITunnelClient(config)
    result = client.chat([{"role": "user", "content": "Fixture", "images": ["encoded-fixture"]}], ImageObservation, 800)
    path, auth, body = state["calls"][0]
    assert path == "/v1/chat/completions" and auth == "Bearer " + CONFIG.api_key
    assert body["model"] == config.model and body["stream"] is False
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,encoded-fixture"
    assert body["include_reasoning"] is False and result.model_dump() == OBSERVATION
    assert CONFIG.api_key not in repr(config)
    assert client.response_model == config.model


@pytest.mark.parametrize("status,code", [(401,"AITUNNEL_AUTH_FAILED"),(403,"AITUNNEL_AUTH_FAILED"),
    (402,"AITUNNEL_QUOTA_EXCEEDED"),(429,"AITUNNEL_RATE_LIMITED"),(404,"AITUNNEL_MODEL_UNAVAILABLE"),
    (400,"AITUNNEL_INVALID_REQUEST"),(503,"AITUNNEL_UNAVAILABLE"),(307,"AITUNNEL_REDIRECT_REJECTED")])
def test_http_failures_are_safe_and_never_retried(endpoint, status, code):
    state, config = endpoint; state["status"] = status
    with pytest.raises(AITunnelFailure, match=code) as caught:
        AITunnelClient(config).chat([], ImageObservation, 800)
    assert CONFIG.api_key not in str(caught.value) and len(state["calls"]) == 1


@pytest.mark.parametrize("change", ["truncated", "schema", "model", "no_model", "refusal", "array", "not_json", "too_large"])
def test_invalid_provider_output_is_not_success(endpoint, change):
    state, config = endpoint
    payload = {"model": config.model, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(OBSERVATION)}}]}
    if change == "truncated": payload["choices"][0]["finish_reason"] = "length"
    if change == "schema": payload["choices"][0]["message"]["content"] = "{}"
    if change == "model": payload["model"] = "different-model"
    if change == "no_model": payload.pop("model")
    if change == "array": payload["choices"][0]["message"]["content"] = json.dumps([OBSERVATION])
    if change == "refusal": payload["choices"][0]["message"]["refusal"] = "refused"
    if change == "not_json": state["raw"] = b"not-json"
    if change == "too_large": state["raw"] = b"x" * 1_048_577
    state["payload"] = payload
    with pytest.raises(AITunnelFailure): AITunnelClient(config).chat([], ImageObservation, 800)


def test_missing_key_does_not_contact_provider(endpoint):
    state, config = endpoint
    with pytest.raises(AITunnelFailure, match="AITUNNEL_NOT_CONFIGURED"):
        AITunnelClient(replace(config, api_key="")).chat([], ImageObservation, 800)
    assert not state["calls"]


def test_timeout_is_controlled(endpoint):
    state, config = endpoint; state["delay"] = .2
    with pytest.raises(AITunnelFailure, match="AITUNNEL_TIMEOUT"):
        AITunnelClient(replace(config, timeout=.03)).chat([], ImageObservation, 800)


@pytest.mark.parametrize("url", ["http://api.aitunnel.ru/v1", "https://evil.example/v1", "https://api.aitunnel.ru/v1?key=secret",
    "https://user:secret@api.aitunnel.ru/v1", "https://api.aitunnel.ru/v1#secret"])
def test_environment_rejects_unapproved_secret_destinations(url):
    with pytest.raises(ValueError) as caught:
        AITunnelConfig.from_environment(environment={"AITUNNEL_BASE_URL": url})
    assert "secret" not in str(caught.value)


def test_environment_accepts_user_key_alias_without_logging():
    result = AITunnelConfig.from_environment(environment={"AI_TUNNEL_API_KEY": CONFIG.api_key})
    assert result.api_key == CONFIG.api_key and result.model == "qwen3.7-flash"
    assert result.reasoning_effort == "none" and CONFIG.api_key not in repr(result)


class VisionFixtureClient:
    response_model = CONFIG.model
    def check_model(self): pass
    def assess(self, *args): return assessment()


def test_cloud_vision_preserves_guardrails_and_provider_provenance(canonical_photo_review_request):
    request = canonical_photo_review_request
    result = review_cloud_photos(request, photos(request).__getitem__, config=CONFIG,
        client=VisionFixtureClient(), comparability_confirmed=lambda b,a: True)
    assert result.status == "completed" and result.model_ref == "aitunnel:qwen3.7-flash"
    assert result.item_results[0].verdict == "visible_change" and not result.item_results[0].scores
    assert "qwen3.7-flash" in result.limitations[-1]
    uncertain = review_cloud_photos(request, photos(request).__getitem__, config=CONFIG, client=VisionFixtureClient())
    assert uncertain.status == "uncertain"


def test_cloud_vision_key_failure_has_no_fake_local_fallback(canonical_photo_review_request):
    request = canonical_photo_review_request
    result = review_cloud_photos(request, photos(request).__getitem__, config=replace(CONFIG, api_key=""))
    assert result.status == "unavailable" and result.error_code == "AITUNNEL_NOT_CONFIGURED"
    assert result.model_ref is None and not result.item_results


class ForecastFixtureClient:
    response_model = CONFIG.model
    calls = 0
    def __init__(self, output): self.output = output; self.messages = None
    def chat(self, messages, schema, tokens):
        self.calls += 1; self.messages = messages
        return CloudRecommendation.model_validate(self.output)


def forecast_reply(snapshot, **changes):
    payload = dict(status="ready", recommended_date=str(snapshot.as_of.date()+timedelta(days=1)),
        explanation="Fixture independent recommendation", evidence=["Fixture history"], missing_data=[])
    payload.update(changes)
    return payload


def test_cloud_forecast_is_bound_to_snapshot_and_is_never_calibrated(synthetic_snapshot):
    snapshot = synthetic_snapshot; client = ForecastFixtureClient(forecast_reply(snapshot))
    result = predict_cloud_maintenance(snapshot, config=CONFIG, client=client)
    assert client.calls == 1 and result.status == "ok"
    assert result.snapshot_sha256 == snapshot.content_sha256 and result.binding_id == snapshot.binding_id
    assert result.model_ref == CONFIG.model_ref and result.uncertainty.kind == "unknown" and not result.uncertainty.calibrated
    context = json.loads(client.messages[1]["content"])
    assert "mandatory_due_date" not in context and "rule" not in context and "site" not in context
    assert str(snapshot.site.site_id) not in client.messages[1]["content"]


def test_missing_history_cloud_advice_cannot_invent_a_date(synthetic_snapshot):
    snapshot = synthetic_snapshot.model_copy(update={"accepted_events": [], "runtime_reading": None})
    payload = json.loads(snapshot.model_dump_json()); snapshot.content_sha256 = compute_snapshot_hash(payload)
    client = ForecastFixtureClient(forecast_reply(snapshot))
    result = predict_cloud_maintenance(snapshot, config=CONFIG, client=client)
    assert result.status == "failed" and result.error_code == "AITUNNEL_INSUFFICIENT_EVIDENCE" and result.recommended_date is None and client.calls == 1


@pytest.mark.parametrize("change,code", [("past","AITUNNEL_DATE_OUT_OF_RANGE"),("invalid","AITUNNEL_FAILED"),
    ("insufficient","INSUFFICIENT_HISTORY"),("hash","AI_SNAPSHOT_MISMATCH")])
def test_cloud_forecast_errors_are_controlled(synthetic_snapshot, change, code):
    snapshot = synthetic_snapshot
    reply = forecast_reply(snapshot)
    if change == "past": reply["recommended_date"] = str(snapshot.as_of.date()-timedelta(days=1))
    if change == "invalid": reply["evidence"] = []
    if change == "insufficient": reply.update(status="insufficient_data",recommended_date=None)
    if change == "hash": snapshot = snapshot.model_copy(update={"content_sha256": "0"*64})
    result = predict_cloud_maintenance(snapshot, config=CONFIG, client=ForecastFixtureClient(reply))
    assert result.status != "ok" and result.error_code == code and result.recommended_date is None
