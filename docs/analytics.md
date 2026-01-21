## Analytics model

Events are written to the `analytics_events` collection via a bounded in-memory queue.

**Event shape (per chat request)**

- `ts` (float): unix timestamp
- `correlation_id` (string)
- `user_id` (string)
- `tier` (string)
- `pool` (string or null)
- `latency_ms` (float)
- `rate_limited` (bool)
- `safety_blocked` (bool)
- `degraded` (bool)
- `path` (string)

**Indexes**

- `{ ts: -1 }`
- `{ tier: 1, ts: -1 }`

These support “latest events” and “events per tier over time” queries efficiently.

