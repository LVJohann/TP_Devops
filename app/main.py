"""API TaskFlow & Visits : FastAPI + Redis (compteur) + PostgreSQL (visites, tâches, journal)."""
import os
from datetime import date
from typing import Literal, Optional

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Query, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="TaskFlow API")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@localhost:5432/visits")
APP_VERSION = os.getenv("APP_VERSION", "dev")

# Pas « REDIS_PORT » : Kubernetes injecte REDIS_PORT=tcp://<ip>:6379 pour le Service « redis ».
REDIS_PORT = int(os.getenv("REDIS_TCP_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=2)

Status = Literal["A faire", "En cours", "Terminee"]
Priority = Literal["Basse", "Normale", "Haute"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (id SERIAL PRIMARY KEY, at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'A faire',
    priority VARCHAR(20) NOT NULL DEFAULT 'Normale',
    due_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS activity (
    id SERIAL PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    action VARCHAR(30) NOT NULL,
    task_id INTEGER,
    detail TEXT NOT NULL DEFAULT ''
);
"""
TASK_COLUMNS = "id, title, description, status, priority, due_date, created_at"
_schema_ready = False


def db():
    """Connexion PostgreSQL ; crée les tables à la première connexion réussie."""
    global _schema_ready
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=3, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise HTTPException(503, f"PostgreSQL indisponible : {exc}") from exc
    if not _schema_ready:
        conn.execute(SCHEMA)
        conn.commit()
        _schema_ready = True
    return conn


def log_activity(conn, action: str, task_id: Optional[int], detail: str) -> None:
    conn.execute(
        "INSERT INTO activity (action, task_id, detail) VALUES (%s, %s, %s)",
        (action, task_id, detail),
    )


def serialize(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


# ---------------------------------------------------------------- santé
@app.get("/health")
def health():
    """Sonde Kubernetes : ne dépend ni de Redis ni de PostgreSQL."""
    return {"status": "ok", "version": APP_VERSION}


# ---------------------------------------------------------------- 1. compteur de visites
@app.get("/")
def visit():
    try:
        count = r.incr("visits")
    except redis.RedisError as exc:
        raise HTTPException(503, "Redis indisponible") from exc
    with db() as conn:
        conn.execute("INSERT INTO logs DEFAULT VALUES")
    return {"visits": count, "pod": os.getenv("HOSTNAME"), "version": APP_VERSION}


@app.get("/visits/count")
def visits_count():
    try:
        return {"visits": int(r.get("visits") or 0)}
    except redis.RedisError as exc:
        raise HTTPException(503, "Redis indisponible") from exc


# ---------------------------------------------------------------- 2. historique des visites
@app.get("/visits")
def history(limit: int = Query(20, ge=1, le=100)):
    with db() as conn:
        rows = conn.execute("SELECT id, at FROM logs ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
        total = conn.execute("SELECT count(*) AS n FROM logs").fetchone()["n"]
    return {"total": total, "items": [serialize(row) for row in rows]}


# ---------------------------------------------------------------- 3. état des services
@app.get("/status")
def status():
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


# ---------------------------------------------------------------- 4 à 9. TaskFlow
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    status: Status = "A faire"
    priority: Priority = "Normale"
    due_date: Optional[date] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le titre est obligatoire")
        return value


class TaskPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[Status] = None
    priority: Optional[Priority] = None
    due_date: Optional[date] = None


@app.get("/tasks")
def list_tasks(
    q: str = Query("", max_length=100),
    status: Optional[Status] = None,
    priority: Optional[Priority] = None,
    sort: Literal["recent", "due", "priority"] = "recent",
):
    """5. Recherche et filtres (texte, statut, priorité) + tri."""
    where, params = [], []
    if q:
        where.append("(title ILIKE %s OR description ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if status:
        where.append("status = %s")
        params.append(status)
    if priority:
        where.append("priority = %s")
        params.append(priority)
    order = {
        "recent": "id DESC",
        "due": "due_date ASC NULLS LAST, id DESC",
        "priority": "CASE priority WHEN 'Haute' THEN 0 WHEN 'Normale' THEN 1 ELSE 2 END, id DESC",
    }[sort]
    sql = f"SELECT {TASK_COLUMNS} FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order}"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [serialize(row) for row in rows]


@app.post("/tasks", status_code=201)
def create_task(task: TaskIn):
    """4. Création d'une tâche."""
    with db() as conn:
        row = conn.execute(
            f"""INSERT INTO tasks (title, description, status, priority, due_date)
                VALUES (%s, %s, %s, %s, %s) RETURNING {TASK_COLUMNS}""",
            (task.title, task.description.strip(), task.status, task.priority, task.due_date),
        ).fetchone()
        log_activity(conn, "creation", row["id"], row["title"])
    return serialize(row)


@app.patch("/tasks/{task_id}")
def update_task(task_id: int, patch: TaskPatch):
    """6. Changement de statut et 7. modification d'une tâche."""
    # Seule l'échéance peut être remise à null ; les autres champs null sont ignorés.
    changes = {
        key: value
        for key, value in patch.model_dump(exclude_unset=True).items()
        if value is not None or key == "due_date"
    }
    if "title" in changes:
        changes["title"] = (changes["title"] or "").strip()
        if not changes["title"]:
            raise HTTPException(422, "Le titre est obligatoire")
    if not changes:
        raise HTTPException(400, "Aucune modification fournie")
    assignments = ", ".join(f"{column} = %s" for column in changes)
    with db() as conn:
        row = conn.execute(
            f"UPDATE tasks SET {assignments} WHERE id = %s RETURNING {TASK_COLUMNS}",
            (*changes.values(), task_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Tâche introuvable")
        if set(changes) == {"status"}:
            log_activity(conn, "statut", task_id, f"{row['title']} → {row['status']}")
        else:
            log_activity(conn, "modification", task_id, row["title"])
    return serialize(row)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    """7. Suppression d'une tâche."""
    with db() as conn:
        row = conn.execute("DELETE FROM tasks WHERE id = %s RETURNING title", (task_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Tâche introuvable")
        log_activity(conn, "suppression", task_id, row["title"])
    return Response(status_code=204)


@app.get("/tasks/stats")
def task_stats():
    """8. Statistiques : répartition, taux d'achèvement, retards."""
    with db() as conn:
        row = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status = 'A faire')  AS todo,
                      count(*) FILTER (WHERE status = 'En cours') AS doing,
                      count(*) FILTER (WHERE status = 'Terminee') AS done,
                      count(*) FILTER (WHERE priority = 'Haute' AND status <> 'Terminee') AS urgent,
                      count(*) FILTER (WHERE due_date < CURRENT_DATE AND status <> 'Terminee') AS overdue
               FROM tasks"""
        ).fetchone()
    row["completion"] = round(100 * row["done"] / row["total"]) if row["total"] else 0
    return row


@app.get("/activity")
def activity(limit: int = Query(15, ge=1, le=100)):
    """9. Journal d'activité des tâches."""
    with db() as conn:
        rows = conn.execute(
            "SELECT id, at, action, task_id, detail FROM activity ORDER BY id DESC LIMIT %s", (limit,)
        ).fetchall()
    return [serialize(row) for row in rows]
