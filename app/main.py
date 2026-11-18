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



def connect():
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, connect_timeout=3)


def init_db():
    for attempt in range(20):
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""CREATE TABLE IF NOT EXISTS tasks (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        description TEXT DEFAULT '',
                        status VARCHAR(30) NOT NULL DEFAULT 'A faire',
                        priority VARCHAR(20) NOT NULL DEFAULT 'Normale',
                        due_date DATE
                    )""")
            return
        except psycopg2.OperationalError:
            if attempt == 19:
                raise
            time.sleep(2)

@app.get('/api/health')
def health():
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
        return jsonify(status='ok', database='connected')
    except Exception as exc:
        return jsonify(status='error', message=str(exc)), 503


@app.get('/api/tasks')
def list_tasks():
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT id, title, description, status, priority, due_date FROM tasks ORDER BY id DESC')
            rows = cur.fetchall()
    for row in rows:
        if row['due_date']:
            row['due_date'] = row['due_date'].isoformat()
    return jsonify(rows)


@app.post('/api/tasks')
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify(error='Le titre est obligatoire'), 400
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('''INSERT INTO tasks(title, description, status, priority, due_date)
                           VALUES (%s, %s, %s, %s, %s)
                           RETURNING id, title, description, status, priority, due_date''',
                        (title, data.get('description', ''), data.get('status', 'A faire'),
                         data.get('priority', 'Normale'), data.get('due_date') or None))
            row = cur.fetchone()
    if row['due_date']:
        row['due_date'] = row['due_date'].isoformat()
    return jsonify(row), 201


@app.put('/api/tasks/<int:task_id>')
def update_task(task_id):
    data = request.get_json(silent=True) or {}
    allowed_status = {'A faire', 'En cours', 'Terminee'}
    allowed_priority = {'Basse', 'Normale', 'Haute'}
    status = data.get('status')
    priority = data.get('priority')
    if status is not None and status not in allowed_status:
        return jsonify(error='Statut invalide'), 400
    if priority is not None and priority not in allowed_priority:
        return jsonify(error='Priorite invalide'), 400
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('''UPDATE tasks SET
                title=COALESCE(%s,title), description=COALESCE(%s,description),
                status=COALESCE(%s,status), priority=COALESCE(%s,priority),
                due_date=CASE WHEN %s THEN %s::date ELSE due_date END
                WHERE id=%s RETURNING id, title, description, status, priority, due_date''',
                (data.get('title'), data.get('description'), status, priority,
                 'due_date' in data, data.get('due_date') or None, task_id))
            row = cur.fetchone()
    if row is None:
        return jsonify(error='Tache introuvable'), 404
    if row['due_date']:
        row['due_date'] = row['due_date'].isoformat()
    return jsonify(row)


@app.delete('/api/tasks/<int:task_id>')
def delete_task(task_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM tasks WHERE id=%s', (task_id,))
            deleted = cur.rowcount
    return ('', 204) if deleted else (jsonify(error='Tache introuvable'), 404)


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
