"""HTTP-контракт запуска MVP-сметы."""
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests import estimate_service
from app.core.errors import AppError
from app.main import create_app
from app.schemas.estimate import EstimateRunResult, EstimateRunOut


REQUEST_ID = UUID("d5000000-0000-0000-8000-000000000001")
RUN_ID = UUID("d6000000-0000-0000-8000-000000000001")
NOW = datetime.now(timezone.utc)


class FakeEstimateService:
    def run(self, request_id):
        if request_id != REQUEST_ID:
            raise AppError(404, "NOT_FOUND", "Заявка не найдена.")
        return EstimateRunResult(
            run=EstimateRunOut(
                run_id=RUN_ID,
                request_id=REQUEST_ID,
                status="completed",
                pipeline_version="v2.0",
                error_message=None,
                started_at=NOW,
                completed_at=NOW,
            ),
            warnings=["DEMO source"],
            audit_trail=["calculated"],
        )

    def latest(self, request_id):
        return self.run(request_id)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[estimate_service] = lambda: FakeEstimateService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_run_estimate_contract(client):
    response = client.post(f"/api/v1/estimates/requests/{REQUEST_ID}")
    assert response.status_code == 201
    assert response.json()["run"]["status"] == "completed"
    assert response.json()["warnings"] == ["DEMO source"]


def test_get_estimate_contract(client):
    response = client.get(f"/api/v1/estimates/requests/{REQUEST_ID}")
    assert response.status_code == 200
    assert response.json()["run"]["pipeline_version"] == "v2.0"


def test_run_estimate_not_found(client):
    response = client.post(
        "/api/v1/estimates/requests/d5000000-0000-0000-8000-000000000099"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
