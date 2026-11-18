"""Tests sans Redis ni PostgreSQL : la validation FastAPI a lieu avant tout accès aux données."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_status_reports_each_service():
    res = client.get("/status")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["services"]) == {"api", "redis", "postgres"}


def test_visits_rejects_invalid_limit():
    assert client.get("/visits?limit=0").status_code == 422
    assert client.get("/visits?limit=500").status_code == 422


def test_create_task_requires_title():
    assert client.post("/tasks", json={}).status_code == 422
    assert client.post("/tasks", json={"title": "   "}).status_code == 422


def test_create_task_rejects_invalid_priority_and_status():
    assert client.post("/tasks", json={"title": "x", "priority": "Urgente"}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "status": "Fini"}).status_code == 422


def test_filters_are_validated():
    assert client.get("/tasks?status=Inconnu").status_code == 422
    assert client.get("/tasks?sort=alpha").status_code == 422


def test_update_rejects_invalid_status():
    assert client.patch("/tasks/1", json={"status": "Fini"}).status_code == 422


def test_activity_rejects_invalid_limit():
    assert client.get("/activity?limit=0").status_code == 422


def test_openapi_lists_all_features():
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/", "/visits", "/visits/count", "/status", "/tasks", "/tasks/{task_id}", "/tasks/stats", "/activity"):
        assert path in paths
