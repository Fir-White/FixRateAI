"""Smoke-тесты каркаса (карточка 1). Запуск: pytest -q (из каталога backend/)."""
import re

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError
from app.main import app

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class _Payload(BaseModel):
    title: str


# Временные роуты ТОЛЬКО для проверки обработчиков ошибок (в реальный API не попадают)
_test_router = APIRouter(prefix="/__test__")


@_test_router.get("/boom")
def _boom():
    raise RuntimeError("секретная внутренняя деталь")


@_test_router.get("/app-error")
def _app_error():
    raise AppError(409, "CONFLICT", "Конфликт для теста")


@_test_router.post("/validate")
def _validate(payload: _Payload):
    return payload


app.include_router(_test_router)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_and_openapi_available(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"] == "FixRate AI API"


def test_request_id_generated_and_echoed(client):
    generated = client.get("/health").headers["X-Request-ID"]
    assert UUID_RE.match(generated)
    echoed = client.get("/health", headers={"X-Request-ID": "demo-123"})
    assert echoed.headers["X-Request-ID"] == "demo-123"


def test_unsafe_request_id_is_replaced(client):
    r = client.get("/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert UUID_RE.match(r.headers["X-Request-ID"])


def test_unknown_path_returns_unified_404(client):
    r = client.get("/no-such-path", headers={"X-Request-ID": "rid-404"})
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == "rid-404"
    assert body["error"]["details"] == []


def test_wrong_method_returns_405(client):
    r = client.post("/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_format(client):
    r = client.post("/__test__/validate", json={})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"][0]["field"] == "title"


def test_app_error_is_mapped(client):
    r = client.get("/__test__/app-error")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_unhandled_exception_hides_internals(client):
    r = client.get("/__test__/boom", headers={"X-Request-ID": "rid-500"})
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert err["request_id"] == "rid-500"
    assert "секретная" not in r.text  # traceback/текст исключения клиенту не уходит
    assert r.headers["X-Request-ID"] == "rid-500"
