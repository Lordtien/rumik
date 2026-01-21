## Low-Level Design

### Core modules

- `services/common/request_context.py`
  - Holds `RequestContext` (correlation_id, service, user_id, tier, operation) in a `contextvars.ContextVar`.
- `services/common/logging.py`
  - Configures root logger with **JSON formatter**.
  - Each log line includes context (correlation_id, service, user_id, tier, operation) when available.
- `services/common/http.py`
  - Middleware that:
    - Extracts or generates `X-Correlation-Id`.
    - Sets `RequestContext` for each request.
    - Logs slow requests above threshold.
- `services/common/mongo.py`
  - Lazily constructs a singleton `AsyncIOMotorClient`.
  - Provides `get_db()` and `close_mongo()`.
- `services/common/redis_client.py`
  - Lazily constructs a singleton `redis.asyncio.Redis` instance from `REDIS_URL`.
  - Provides `get_redis()` and `close_redis()`.
- `services/common/repos.py`
  - `UsersRepo`, `PersonalitiesRepo`, `SessionsRepo`, `MessagesRepo`.
  - Encapsulate Motor queries with correct indexes and projections.

### Router internals

- `services/router/app/pools.py`
  - `PoolConfig`: name, base_url, max_concurrency.
  - `PoolState`: healthy, last_health_check_s, last_error, inflight, ewma_latency_ms.
  - `PoolManager`:
    - Maintains configs and state per pool.
    - Holds per-pool `asyncio.Semaphore` to enforce `max_concurrency`.
    - Background health polling task:
      - Periodically hits each pool’s `/healthz`.
      - Updates `healthy` and `last_error`.
    - `call_process(pool, payload, max_queue_wait_s)`:
      - Admission control:
        - If `max_queue_wait_s > 0`: `await asyncio.wait_for(sem.acquire(), timeout=...)`.
        - Else: if `sem.locked()` → raise `PoolOverloaded`; otherwise `await sem.acquire()`.
      - Records inflight count + latency EWMA.
      - Performs HTTP POST to `${base_url}/process` with JSON payload.
      - Releases semaphore and updates stats.
    - `snapshot()`:
      - Returns a dict with per-pool health and load; exposed via `/pools`.
- `services/router/app/tier_router.py`
  - `TierRouter` encapsulates tier-aware routing:
    - For each tier, returns an **ordered list** of pools with max wait:
      - Enterprise: `[("priority", 0.0), ("overflow", 0.05)]`.
      - Premium: `[("standard", 0.10), ("overflow", 0.05), ("priority", 0.0)]`.
      - Free: `[("overflow", 0.0)]`.
    - `route_and_call(tier, payload)`:
      - Iterates candidates:
        - Skips unhealthy pools for non-enterprise.
        - Calls `PoolManager.call_process`.
        - On 200 → returns `RouteDecision` with `action="forward"` and worker JSON.
        - On overload/error → records reason and tries next.
      - If all candidates fail → returns `RouteDecision(action="shed")` plus a friendly message.
- `services/router/app/main.py`
  - Creates FastAPI app with custom `lifespan`:
    - Instantiates `PoolManager` and `TierRouter`.
    - Starts analytics background flusher.
    - On shutdown, closes pool HTTP client and flushes analytics queue.
  - `POST /chat`:
    - Sets request context.
    - Calls `tier_router.route_and_call`.
    - Computes end-to-end latency.
    - Enqueues analytics event via `analytics_track`.
    - Returns:
      - `reply`, `tier`, `pool`, `degraded`, `rate_limited`, `silent`, `blocked`.
  - `GET /pools`:
    - Returns `PoolManager.snapshot()` for observability and tests.

### Worker internals

- Each worker (`services/worker_priority/app/main.py`, etc.):
  - Uses `create_app(service=...)` so health/readiness + logging are consistent.
  - Defines a single `/process` endpoint with:
    - `ProcessRequest(user_id, message, tier)`.
  - Pipeline:
    1. **Set request context** with updated user_id + tier.
    2. **Safety check**:
       - `detect_unsafe(message)` returns `SafetyResult`.
       - If `allowed=False`:
         - Returns JSON with `reply=refusal_message`, `blocked=True`.
    3. **Rate limiting**:
       - Uses `SessionDayLimiter.check_and_increment(user_id, tier)` backed by Redis.
       - If tier has no limit (enterprise) → immediately allowed.
       - Otherwise:
         - Allowed if count ≤ limit; returns `allowed=True`.
         - If first over-limit:
           - Writes a one-time “notice” key (per user per day).
           - Returns `allowed=False`, `first_notice=True`.
         - Subsequent over-limits:
           - Returns `allowed=False`, `first_notice=False`.
       - Worker behavior:
         - On `allowed=False` and `first_notice=True`:
           - Returns `reply=human_reset_message(reset_in_seconds)`, `rate_limited=True`, `silent=False`.
         - On `allowed=False` and `first_notice=False`:
           - Returns `reply=None`, `rate_limited=True`, `silent=True`.
    4. **LLM stub**:
       - Async `sleep` with latency profile:
         - Priority: ~20–60ms.
         - Standard: ~50–150ms.
         - Overflow: ~100–350ms.
       - Returns a simple “Processed by ... pool (stub)” reply.

### Rate limiting implementation details

- `services/common/rate_limit.py`
  - Keys per UTC day:
    - Count key: `ira:rl:count:{day}:{user_id}`.
    - Notice key: `ira:rl:notice:{day}:{user_id}`.
  - Both keys expire at **next UTC midnight**.
  - `check_and_increment` logic:
    - Increments count and ensures TTL is set to seconds until midnight.
    - Determines remaining quota.
    - If over limit, uses `SET notice_key NX EX` to atomically check whether to send the first notice.

### Safety implementation details

- `services/common/safety.py`
  - Regex-based detection:
    - Jailbreak / prompt injection keywords.
    - Explicit NSFW words.
    - Self-harm phrases.
    - Violence queries.
    - Hate-related keywords.
  - `refusal_message(tone, category)`:
    - Picks copy based on tone (`warm`, `playful`, `direct`) and category.
    - For self-harm, uses a more empathetic message.
  - Lightweight and deterministic; easy to unit test and extend.

### Analytics and logging

- `services/common/analytics.py`
  - Bounded `asyncio.Queue` for events.
  - Background task:
    - Reads from queue.
    - Batches up to 100 events or every 0.5s.
    - Writes to `analytics_events` in Mongo.
  - On shutdown, drains remaining events and logs drops if any.
- Structured logs:
  - All services log JSON to stdout with correlation_id, user_id, tier, and operation.

