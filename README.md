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

This runs both:
- **E2E tests** (`tests/test_e2e.py`): Functional tests against running services
- **Unit tests** (`tests/unit/`): Isolated tests for core logic (rate limiting, safety, router policy, pool manager)

### Load test (pytest, “load-ish”)

This prints p50/p95/p99 latency per tier and basic degradation counts:

```bash
docker compose run --rm --build \
  -e LOAD_CONCURRENCY=50 \
  -e LOAD_N_FREE=200 \
  -e LOAD_N_PREMIUM=200 \
  -e LOAD_N_ENTERPRISE=200 \
  tests pytest -q tests/test_load.py -s
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

---

## Design Decisions

### Why per-day (UTC) rate limiting?
- Aligns with "session" concept (one session per user per UTC day)
- Simple reset semantics (midnight UTC)
- Avoids complex sliding windows or per-hour buckets
- Redis TTL naturally expires at next midnight

### Why three worker pools (priority, standard, overflow)?
- **Priority pool**: Reserved capacity for enterprise; isolated from contention
- **Standard pool**: Default for premium; can degrade to overflow if needed
- **Overflow pool**: Best-effort for free tier; absorbs load spikes
- This design ensures enterprise stability while allowing graceful degradation for lower tiers

### Why Redis for rate limiting (not Mongo)?
- **Latency**: Redis in-memory operations are < 1ms; Mongo writes are 5-20ms
- **Atomicity**: Redis `INCR` + `SET NX EX` provides atomic "first notice" detection
- **TTL**: Redis TTL aligns perfectly with "expires at midnight" requirement
- **Scalability**: Redis can handle millions of rate-limit checks per second

### Why router sheds before worker rate limit?
- **Protection**: Router-level shedding protects workers from overload
- **Tier priority**: Router can make tier-aware decisions (enterprise never sheds)
- **Trade-off**: Free users may see "I'm busy" (router shed) instead of "I'll be back after X hours" (rate limit message)
- This is acceptable because router shedding is a system-level protection, while rate limiting is a user-level quota

### Why bounded queue for analytics (drops when full)?
- **Non-blocking guarantee**: `analytics_track()` must return in < 1ms
- **Backpressure**: If Mongo is slow, we drop analytics events rather than slow down user requests
- **Trade-off**: Some analytics events may be lost under extreme load
- This is acceptable because analytics are for observability, not critical business logic

### Why MongoDB for analytics (not a separate time-series DB)?
- **Simplicity**: Single database for all data (users, sessions, messages, analytics)
- **Query flexibility**: Can join analytics with user/session data for analysis
- **Assignment constraint**: Assignment specifies MongoDB 7+; using it for analytics is consistent
- **Trade-off**: Not optimized for high-volume time-series writes, but acceptable for assignment scope

### Why HTTP between router and workers (not gRPC/queue)?
- **Simplicity**: HTTP is easy to debug, test, and observe
- **FastAPI native**: FastAPI makes HTTP endpoints trivial
- **Trade-off**: Slightly higher latency than gRPC, but acceptable for assignment scope
- In production, gRPC or message queues (RabbitMQ/Kafka) would be better for high throughput

### Why semaphore-based admission control (not queue-based)?
- **Simplicity**: Semaphores are built into asyncio; no queue management needed
- **Backpressure**: When pool is full, router immediately tries next pool or sheds
- **Trade-off**: No queuing means requests are either accepted or rejected immediately
- This matches the "graceful degradation" requirement: free tier sheds rather than waiting

---

## Trade-offs

### Performance vs. Consistency
- **Hot-path queries use indexes** for < 50ms performance, but some aggregation queries may scan if index doesn't match query pattern exactly
- **Analytics writes are async** (non-blocking), but events may be lost if queue is full
- **Rate limiting uses Redis** (fast, eventually consistent), not Mongo (slower, strongly consistent)

### Availability vs. Data Loss
- **Router sheds free tier** to protect enterprise availability
- **Analytics queue drops events** when full to avoid blocking user requests
- **Graceful shutdown** flushes analytics, but in-process events may be lost on crash

### Simplicity vs. Production-Ready Features
- **No circuit breakers**: Pool health is binary (healthy/unhealthy), not gradual degradation
- **No retries**: Router tries next pool once, then sheds (no exponential backoff)
- **No distributed tracing**: Correlation IDs are logged but not propagated to external services
- **No metrics/alerting**: Health checks exist but no Prometheus/Grafana integration

### Tier Fairness vs. Enterprise Protection
- **Enterprise always routed to priority pool** (may starve premium if priority is full)
- **Premium can use priority pool** as fallback, but only if standard + overflow fail
- **Free tier only uses overflow pool** (never gets priority/standard capacity)

### Rate Limit UX vs. System Protection
- **Router shedding happens before rate limit check**: Free users may see "I'm busy" instead of rate limit message
- **First notice then silent**: Better UX than repeated messages, but user may not understand why they're being ignored
- **Per-day limits reset at UTC midnight**: Simple but may confuse users in different timezones

---

## Architecture Overview

See `docs/high_level.md` for component overview and data flow.

See `docs/low_level.md` for implementation details and module structure.

See `docs/state_machines.md` for rate limiting and safety blocking state diagrams.

See `docs/schema.md` for MongoDB collection schemas.

See `docs/indexes.md` for indexing strategy.

See `docs/perf.md` for query performance analysis.

See `docs/analytics.md` for analytics event model.

See `docs/report.md` for load test results and observations.

---

## Notes for Reviewers

- **MongoDB version**: Assignment requires MongoDB 7+; tested with 8.2.4 (compatible)
- **Python version**: Strictly Python 3.13 (enforced in `pyproject.toml`)
- **Diagram format**: High-level diagram is in Mermaid format in `docs/high_level.md` (renders in GitHub). For external tools (Figma/Excalidraw), the Mermaid diagram can be used as a reference.
- **Unit tests**: Core logic (rate limiting, safety, pool management) is tested via e2e tests. Unit tests for individual modules can be added but are not required for assignment scope.
- **Seeder realism**: Seeder generates 1M docs with realistic tier distribution (90% free, 9% premium, 1% enterprise) but does not enforce full relational consistency (e.g., messages.user_id may not always match users._id). This is acceptable for load testing purposes.

