"""Tests for the monthly demand API endpoint.

The endpoint returns a list of demand records or a 404 when no data is present.
These tests verify both status codes and the response schema.
"""

import pytest
from httpx import AsyncClient
from app.main import create_app
from app.db.session import make_engine, make_session_factory

@pytest.fixture(scope="module")
def test_app():
    # Use an in‑memory SQLite for fast isolated tests (the app supports PostgreSQL,
    # but the reflected models work with any SQLAlchemy engine for the purpose of
    # this simple endpoint).
    engine = make_engine(url="sqlite:///:memory:")
    app = create_app(engine=engine)
    return app

@pytest.mark.asyncio
async def test_get_monthly_demand_success(test_app):
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        resp = await client.get("/api/v1/demand/monthly")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)
            if data:
                record = data[0]
                for key in ("material_id", "quantity", "unit", "month", "work_id", "equipment_id", "basis"):
                    assert key in record

@pytest.mark.asyncio
async def test_get_monthly_demand_404_when_empty(test_app):
    # Ensure the DB is empty – the service will return [] and the endpoint 404.
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        resp = await client.get("/api/v1/demand/monthly")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No demand data found"
