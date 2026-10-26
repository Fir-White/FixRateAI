"""Smoke-тесты каркаса (карточка 1)."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


def test_request_id_echo() -> None:
    client = TestClient(create_app())
    custom = "11111111-2222-3333-4444-555555555555"
    response = client.get("/health", headers={"X-Request-ID": custom})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom


def test_not_found_json_shape() -> None:
    client = TestClient(create_app())
    response = client.get("/no-such-path")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
    assert "request_id" in body["error"]
    assert body["error"]["request_id"] != "-"
    assert response.headers.get("X-Request-ID") == body["error"]["request_id"]


def test_openapi_docs_available() -> None:
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "FixRate AI API"
