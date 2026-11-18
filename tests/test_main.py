from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_status_reports_each_service():
    # Fonctionne avec ou sans Redis/PostgreSQL : on vérifie seulement la forme de la réponse.
    res = client.get("/status")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["services"]) == {"api", "redis", "postgres"}

def test_visits_rejects_invalid_limit():
    # La validation FastAPI a lieu avant tout accès à la base.
    assert client.get("/visits?limit=0").status_code == 422
    assert client.get("/visits?limit=500").status_code == 422
