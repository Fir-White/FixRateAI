"""Интеграционные тесты для API проверки работоспособности сервиса."""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health_endpoint_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "FixRate AI ML Service"
    assert "version" in data
    assert "X-Request-ID" in response.headers


def test_request_id_custom_forwarding(client):
    custom_rid = "custom-req-id-789"
    response = client.get("/health", headers={"X-Request-ID": custom_rid})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_rid


def test_unified_error_format_on_404(client):
    response = client.get("/non-existent-path")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "request_id" in data["error"]
    assert response.headers["X-Request-ID"] == data["error"]["request_id"]


def test_openapi_and_docs_available(client):
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    spec_resp = client.get("/openapi.json")
    assert spec_resp.status_code == 200
    spec = spec_resp.json()
    assert spec["info"]["title"] == "FixRate AI ML Service"
