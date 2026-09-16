"""Integration and end-to-end unit tests for FastAPI endpoints."""

from __future__ import annotations

import asyncio
import pathlib
import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_data_loader, _RUN_LOCK
from src.data.loader import DataLoader
from tests.fixtures.generate_fixtures import create_synthetic_telemetry


@pytest.fixture
def client(tmp_path: pathlib.Path) -> TestClient:
    """Fixture providing a TestClient connected to synthetic telemetry directory."""
    create_synthetic_telemetry(tmp_path, anomaly_gateway="TEST_GW_001")
    app.dependency_overrides[get_data_loader] = lambda: DataLoader(data_dir=tmp_path)
    test_client = TestClient(app)
    # Trigger initial run
    test_client.post("/run?week=2026-02-09")
    yield test_client
    app.dependency_overrides.clear()


def test_get_predictions_success(client: TestClient) -> None:
    """Test GET /predictions/{week_start} returns ranked predictions."""
    response = client.get("/predictions/2026-02-09")
    assert response.status_code == 200

    data = response.json()
    assert data["week_start"] == "2026-02-09"
    assert data["count"] > 0
    assert len(data["predictions"]) > 0

    first_pred = data["predictions"][0]
    assert "rank" in first_pred
    assert "gateway_id" in first_pred
    assert "score" in first_pred
    assert "reason" in first_pred


def test_get_predictions_invalid_date(client: TestClient) -> None:
    """Test GET /predictions/{week_start} returns 422 for malformed or non-Monday dates."""
    # Malformed date string
    res1 = client.get("/predictions/invalid-date")
    assert res1.status_code == 422
    assert "Invalid date format" in res1.json()["detail"]

    # Non-Monday date (2026-02-03 is Tuesday)
    res2 = client.get("/predictions/2026-02-03")
    assert res2.status_code == 422
    assert "must be a Monday" in res2.json()["detail"]


def test_explain_gateway_success(client: TestClient) -> None:
    """Test GET /gateways/{gateway_id}/explain returns gateway ranking explanation."""
    response = client.get("/gateways/TEST_GW_001/explain?week=2026-02-09")
    assert response.status_code == 200

    data = response.json()
    assert data["gateway_id"] == "TEST_GW_001"
    assert data["rank"] == 1
    assert data["is_top_15"] is True
    assert "offline_duration_sec" in data["breached_metrics"]


def test_explain_gateway_unknown(client: TestClient) -> None:
    """Test GET /gateways/{gateway_id}/explain returns 404 for unknown gateway."""
    response = client.get("/gateways/UNKNOWN_GW_999/explain?week=2026-02-09")
    assert response.status_code == 404
    assert "not found in dataset" in response.json()["detail"]


def test_explain_gateway_not_top_15(client: TestClient) -> None:
    """Test GET /gateways/{gateway_id}/explain returns explicit 422 error for non-top-15 gateway."""
    # TEST_GW_020 has 0 anomalies and is rank 20 (outside top 15)
    response = client.get("/gateways/TEST_GW_020/explain?week=2026-02-09")
    # Must explicitly state why it's not present in top 15
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "NOT ranked in that week's top 15" in detail


def test_run_endpoint(client: TestClient) -> None:
    """Test POST /run re-executes pipeline successfully."""
    response = client.post("/run?week=2026-02-09")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert "2026-02-09" in data["refreshed_weeks"]


def test_run_endpoint_conflict(client: TestClient) -> None:
    """Test POST /run returns 409 Conflict when a run is locked/in-progress."""
    async def mock_lock():
        await _RUN_LOCK.acquire()

    asyncio.run(mock_lock())
    try:
        response = client.post("/run")
        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]
    finally:
        if _RUN_LOCK.locked():
            _RUN_LOCK.release()
