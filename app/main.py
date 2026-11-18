import os
import psycopg
import redis
from fastapi import FastAPI, Query

app = FastAPI(title="Visits API")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@localhost:5432/visits")
APP_VERSION = os.getenv("APP_VERSION", "dev")

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True, socket_connect_timeout=2)

CREATE_LOGS = "CREATE TABLE IF NOT EXISTS logs (id SERIAL PRIMARY KEY, at TIMESTAMPTZ DEFAULT now())"


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/")
def visit():
    count = r.incr("visits")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(CREATE_LOGS)
        conn.execute("INSERT INTO logs DEFAULT VALUES")
    return {"visits": count, "pod": os.getenv("HOSTNAME"), "version": APP_VERSION}


@app.get("/visits/count")
def visits_count():
    """Valeur actuelle du compteur Redis, sans enregistrer de visite."""
    return {"visits": int(r.get("visits") or 0)}


@app.get("/visits")
def history(limit: int = Query(20, ge=1, le=100)):
    """Dernières visites enregistrées dans PostgreSQL (la plus récente en premier)."""
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(CREATE_LOGS)
        rows = conn.execute(
            "SELECT id, at FROM logs ORDER BY id DESC LIMIT %s", (limit,)
        ).fetchall()
        total = conn.execute("SELECT count(*) FROM logs").fetchone()[0]
    return {"total": total, "items": [{"id": i, "at": at.isoformat()} for i, at in rows]}


@app.get("/status")
def status():
    """État de l'API et de ses dépendances (contrairement à /health, utilisé par les probes)."""
    services = {"api": "ok"}
    try:
        r.ping()
        services["redis"] = "ok"
    except redis.RedisError:
        services["redis"] = "down"
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        services["postgres"] = "ok"
    except psycopg.Error:
        services["postgres"] = "down"
    overall = "ok" if all(s == "ok" for s in services.values()) else "degraded"
    return {"status": overall, "version": APP_VERSION, "pod": os.getenv("HOSTNAME"), "services": services}
