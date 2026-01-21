## Ira AI Gateway (Assignment Scaffold)

This repo is intentionally minimal at the start: it sets up **Poetry**, a **multi-service folder layout**, and small FastAPI apps with **correlation IDs** + **structured JSON logs**.

### Prereqs

- Python **3.13**
- Poetry

### Install

```bash
poetry install
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


