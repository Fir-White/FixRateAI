"""Интеграционные тесты HTTP эндпоинта POST /api/v1/process."""
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_process_endpoint_needs_clarification(client):
    payload = {
        "description_text": "Обнаружена трещина на фасаде здания",
        "files": [
            {
                "file_id": "f-1",
                "file_type": "image",
                "mime_type": "image/jpeg",
            }
        ],
    }
    response = client.post("/api/v1/process", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "needs_clarification"
    assert len(data["clarification_questions"]) == 1
    assert data["clarification_questions"][0]["field_name"] == "length_m"
    assert data["total_cost"] is None


def test_process_endpoint_successful_estimate(client):
    payload = {
        "description_text": "Трещина на фасаде здания, длина 3.5 метра",
        "files": [
            {
                "file_id": "f-2",
                "file_type": "image",
                "mime_type": "image/jpeg",
            }
        ],
    }
    response = client.post("/api/v1/process", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "completed"
    assert len(data["estimate_items"]) == 1
    item = data["estimate_items"][0]
    assert item["rate_code"] == "DEMO-FACADE-CRACK-01"
    # S = 3.5 * 0.1 = 0.35; 0.35 * 850.00 = 297.50 RUB
    assert Decimal(str(item["line_total"])) == Decimal("297.50")
    assert Decimal(str(data["total_cost"])) == Decimal("297.50")
    assert data["currency"] == "RUB"
    assert len(data["audit_trail"]) > 0


def test_process_endpoint_validation_error_on_bad_json(client):
    response = client.post("/api/v1/process", json={"files": "not_a_list"})
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert len(data["error"]["details"]) > 0
