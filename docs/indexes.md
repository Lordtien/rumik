## Indexing strategy (compound indexes)

Goal: keep the two hot-path queries under **50ms** on ~1M documents per collection.

### `users`

- **Unique PK**: `_id` (implicit)
- **Tier aggregations**:
  - `{ tier: 1, last_seen_at: -1 }`

### `personalities`

- Fetch personality by user quickly:
  - `{ user_id: 1, updated_at: -1 }`

### `sessions`

Hot path: fetch today's active session for a user.

- `{ user_id: 1, day: 1, status: 1 }`
  - Supports equality match on all three fields.
- Optional analytics:
  - `{ tier: 1, day: 1 }`

### `messages`

Hot path: fetch recent N messages (N=20) for a session, newest-first.

- `{ session_id: 1, created_at: -1 }`
  - Supports `match(session_id)` + `sort(created_at desc)` + `limit(20)`.
- Optional analytics:
  - `{ tier: 1, created_at: -1 }`

### `analytics_events`

- Recent events:
  - `{ ts: -1 }`
- Per-tier time series:
  - `{ tier: 1, ts: -1 }`

### Why these help

- Compound indexes match the **exact filter+sort patterns** of the hot path.
- Denormalized `tier` fields on `sessions/messages` allow analytics without `$lookup`.
- `analytics_events` is optimized for “latest events by tier” queries.

