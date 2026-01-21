## Ira AI Gateway (Assignment Scaffold)

This repo is intentionally minimal at the start: it sets up **Poetry**, a **multi-service folder layout**, and small FastAPI apps with **correlation IDs** + **structured JSON logs**.

### Prereqs

- Python **3.13**
- Poetry

### Install

```bash
poetry install
```

### Run with Docker Compose

Bring everything up (Mongo + Redis + router + workers):

```bash
docker compose up --build
```

Seed a small dataset (one-shot service):

```bash
docker compose run --rm seeder
```

Run tests (executes pytest inside a container against the running router):

```bash
docker compose run --rm tests
```

### Seed Mongo (local)

By default, the seeder targets **1,000,000 docs per collection** (heavy).
Start with a smaller run:

```bash
MONGO_URI="mongodb://localhost:27017" MONGO_DB="ira" \
SEED_DROP_DB=true SEED_USERS=10000 SEED_SESSIONS=10000 SEED_MESSAGES=20000 \
poetry run python scripts/seed_mongo.py
```

### Run (local, single service)

Router:

```bash
poetry run uvicorn services.router.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Worker (priority):

```bash
poetry run uvicorn services.worker_priority.app.main:app --host 0.0.0.0 --port 8001 --reload
```

Worker (standard):

```bash
poetry run uvicorn services.worker_standard.app.main:app --host 0.0.0.0 --port 8002 --reload
```

Worker (overflow):

```bash
poetry run uvicorn services.worker_overflow.app.main:app --host 0.0.0.0 --port 8003 --reload
```

Seeder:

```bash
poetry run uvicorn services.seeder.app.main:app --host 0.0.0.0 --port 8004 --reload
```

### Endpoints

- `GET /healthz`
- `GET /readyz`
- `POST /chat` (stub)
  - returns `rate_limited`, `silent`, `blocked` flags when applicable



