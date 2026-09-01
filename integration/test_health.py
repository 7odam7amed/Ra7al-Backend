import pytest
from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_contains_status_ok(client: TestClient) -> None:
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


def test_database_health_when_db_available(client: TestClient, db_available: bool) -> None:
    if not db_available:
        pytest.skip("PostgreSQL is not available; start it with docker compose up db")

    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
