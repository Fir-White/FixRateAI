"""HTTP-контракт API заявок с изолированным сервисом."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.v1.requests import service
from app.core.errors import AppError
from app.main import create_app
from app.schemas.request import RequestOut


BUILDING_ID = UUID("d4000000-0000-4000-8000-000000000001")
REQUEST_ID = UUID("d5000000-0000-4000-8000-000000000001")
USER_ID = UUID("d3000000-0000-4000-8000-000000000001")
NOW = datetime.now(timezone.utc)


def request_out() -> RequestOut:
    return RequestOut(
        request_id=REQUEST_ID,
        building_id=BUILDING_ID,
        created_by=USER_ID,
        title="Трещина на фасаде",
        description="Вертикальная трещина длиной 3 м",
        location_description="подъезд 2",
        status="created",
        cancellation_reason=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRequestService:
    def create(self, data):
        return request_out()

    def get(self, request_id):
        if request_id != REQUEST_ID:
            raise AppError(404, "NOT_FOUND", "Заявка не найдена.")
        return request_out()

    def list(self, **kwargs):
        return [request_out()], 1

    def update(self, request_id, data):
        if request_id != REQUEST_ID:
            raise AppError(404, "NOT_FOUND", "Заявка не найдена.")
        result = request_out()
        if data.title is not None:
            result.title = data.title
        return result


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[service] = lambda: FakeRequestService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_request(client):
    response = client.post(
        "/api/v1/requests",
        json={
            "building_id": str(BUILDING_ID),
            "title": "Трещина на фасаде",
            "description": "Вертикальная трещина длиной 3 м",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "created"
    assert response.json()["request_id"] == str(REQUEST_ID)


def test_create_request_with_photo_reference(client):
    response = client.post(
        "/api/v1/requests",
        json={
            "building_id": str(BUILDING_ID),
            "title": "Повреждение фасада",
            "photos": [{
                "storage_key": "requests/demo/photo.jpg",
                "original_filename": "photo.jpg",
                "mime_type": "image/jpeg",
                "file_size": 123,
                "checksum_sha256": "a" * 64,
            }],
        },
    )
    assert response.status_code == 201


def test_list_get_and_patch_request(client):
    response = client.get("/api/v1/requests?limit=20&offset=0&status=created")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1

    response = client.get(f"/api/v1/requests/{REQUEST_ID}")
    assert response.status_code == 200

    response = client.patch(
        f"/api/v1/requests/{REQUEST_ID}",
        json={"title": "Обновлённое название"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Обновлённое название"


def test_validation_errors_are_stable(client):
    response = client.post(
        "/api/v1/requests",
        json={"building_id": str(BUILDING_ID), "title": "   "},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    response = client.patch(f"/api/v1/requests/{REQUEST_ID}", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    response = client.patch(
        f"/api/v1/requests/{REQUEST_ID}",
        json={"title": None},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_not_found_and_database_errors_are_stable(client, monkeypatch):
    response = client.get(f"/api/v1/requests/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

    def unavailable():
        raise OperationalError("select 1", {}, Exception("offline"))

    app = client.app
    app.dependency_overrides[service] = unavailable
    response = client.get(f"/api/v1/requests/{REQUEST_ID}")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_UNAVAILABLE"
