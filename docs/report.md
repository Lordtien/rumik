## Test Report (template)

### How to run

With Docker Compose running:

- Functional tests:
  - `docker compose run --rm --build tests`

- Load-ish test (prints p50/p95/p99 per tier):
  - `docker compose run --rm --build -e LOAD_CONCURRENCY=50 -e LOAD_N_FREE=200 -e LOAD_N_PREMIUM=200 -e LOAD_N_ENTERPRISE=200 tests pytest -q tests/test_load.py -s`

### Results (fill in)

Paste output from `tests/test_load.py` here, plus any screenshots.

### Observations

- Enterprise stability:
- Premium degradation:
- Free graceful shedding:

### Trade-offs / Notes

#### Architecture Trade-offs

1. **HTTP forwarding vs. message queue**
   - **Chosen**: HTTP forwarding between router and workers
   - **Pros**: Simple, observable, easy to test, FastAPI-native
   - **Cons**: Higher latency than gRPC, no built-in retries/backpressure
   - **Acceptable for assignment**: Assignment scope doesn't require production-grade message queue

2. **Semaphore-based admission vs. queue-based**
   - **Chosen**: Semaphore-based admission control (immediate accept/reject)
   - **Pros**: Simple, no queue management, immediate backpressure
   - **Cons**: No queuing means requests are shed rather than delayed
   - **Matches requirement**: "Free traffic should degrade gracefully, not abruptly" — shedding is graceful

3. **Bounded analytics queue with drops**
   - **Chosen**: Drop events when queue is full
   - **Pros**: Guarantees < 1ms track() latency, never blocks user requests
   - **Cons**: Analytics events may be lost under extreme load
   - **Acceptable**: Analytics are for observability, not critical business logic

4. **Router-level shedding vs. worker-level rate limiting**
   - **Behavior**: Router may shed free tier before worker rate limit is hit
   - **Pros**: Protects workers from overload, tier-aware decisions
   - **Cons**: Free users may see "I'm busy" (router shed) instead of "I'll be back after X hours" (rate limit message)
   - **Acceptable**: Router shedding is system-level protection; rate limiting is user-level quota

#### Performance Trade-offs

1. **MongoDB indexes vs. query flexibility**
   - **Chosen**: Compound indexes optimized for hot-path queries
   - **Pros**: < 50ms performance on 1M documents
   - **Cons**: Some aggregation queries may scan if index doesn't match exactly
   - **Acceptable**: Hot paths are optimized; analytics aggregations are less frequent

2. **Redis for rate limiting vs. MongoDB**
   - **Chosen**: Redis for rate limit state
   - **Pros**: < 1ms latency, atomic operations, TTL support
   - **Cons**: Additional infrastructure, eventual consistency
   - **Acceptable**: Rate limiting needs speed; Redis is standard for this use case

#### UX Trade-offs

1. **First notice then silent vs. repeated messages**
   - **Chosen**: Send one human message on first over-limit, then silent
   - **Pros**: Better UX than repeated system messages, avoids spamming
   - **Cons**: User may not understand why they're being ignored after first message
   - **Matches requirement**: "Avoids spamming the user with repeated system messages"

2. **UTC day reset vs. local timezone**
   - **Chosen**: UTC day reset for rate limits
   - **Pros**: Simple, consistent across all users
   - **Cons**: May confuse users in different timezones (e.g., reset at 2 AM local time)
   - **Acceptable**: Assignment doesn't require timezone-aware resets

#### Observability Trade-offs

1. **Structured JSON logs vs. plain text**
   - **Chosen**: JSON logs with correlation IDs and context
   - **Pros**: Easy to parse, searchable, includes correlation_id for tracing
   - **Cons**: Harder to read in terminal without tools
   - **Acceptable**: Production systems use structured logs; reviewers can use `jq` or log aggregators

2. **Analytics in MongoDB vs. time-series DB**
   - **Chosen**: MongoDB for analytics events
   - **Pros**: Single database, can join with user/session data
   - **Cons**: Not optimized for high-volume time-series writes
   - **Acceptable**: Assignment scope doesn't require dedicated time-series database

#### Testing Trade-offs

1. **E2E tests vs. unit tests**
   - **Chosen**: E2E tests for core behavior (routing, rate limiting, safety)
   - **Pros**: Tests real system behavior, catches integration issues
   - **Cons**: Slower, harder to isolate failures
   - **Acceptable**: Assignment requires behavioral tests; unit tests are nice-to-have

2. **Load-ish test vs. production load test**
   - **Chosen**: Pytest-based concurrent requests (not dedicated load testing tool)
   - **Pros**: Simple, integrated with test suite, prints p50/p95/p99
   - **Cons**: Not as comprehensive as dedicated load testing (e.g., Locust, k6)
   - **Acceptable**: Assignment requires "pytest-based load tests"; this meets the requirement

