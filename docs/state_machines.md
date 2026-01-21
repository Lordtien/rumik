## State Machines

### Rate Limiting (per user per day, per tier)

States (logical view for a given user + day):

- `BelowLimit`: user is under daily quota.
- `AtOrAboveLimit_NoNotice`: user has just crossed the limit; no friendly notice sent yet.
- `AtOrAboveLimit_NoticeSent`: user is over the limit and notice has already been sent.

Transitions:

```mermaid
stateDiagram-v2
  [*] --> BelowLimit

  BelowLimit --> BelowLimit: message\ncount < limit
  BelowLimit --> AtOrAboveLimit_NoNotice: message\ncount == limit+1

  AtOrAboveLimit_NoNotice --> AtOrAboveLimit_NoticeSent: message\nfirst over-limit\n-> send notice

  AtOrAboveLimit_NoticeSent --> AtOrAboveLimit_NoticeSent: message\n-> silent

  AtOrAboveLimit_NoNotice --> [*]: day resets (UTC)
  AtOrAboveLimit_NoticeSent --> [*]: day resets (UTC)
  BelowLimit --> [*]: day resets (UTC)
```

Implementation mapping:

- `BelowLimit`: count key `< limit`; limiter returns `allowed=True`.
- `AtOrAboveLimit_NoNotice`:
  - count > limit AND `notice` key doesn’t exist; limiter sets notice key (`NX`) and returns `first_notice=True`.
- `AtOrAboveLimit_NoticeSent`:
  - count > limit AND `notice` key exists; limiter returns `first_notice=False`.

Workers interpret the result as:

- `allowed=True` → process normally.
- `allowed=False, first_notice=True` → send human “I need rest” reply.
- `allowed=False, first_notice=False` → silent (reply=null).

### Safety Blocking

States:

- `Allowed`: prompt passes safety checks.
- `Blocked`: prompt matches at least one unsafe category.

Transitions:

```mermaid
stateDiagram-v2
  [*] --> Allowed
  Allowed --> Allowed: safe prompt
  Allowed --> Blocked: unsafe prompt\n(jailbreak/nsfw/violence/self_harm/hate)
  Blocked --> Blocked: subsequent prompts\nthat remain unsafe
  Blocked --> Allowed: next prompt is safe
```

Implementation mapping:

- Each message is evaluated independently (`detect_unsafe`).
- No long-lived state; blocking decision is per-request.

Worker behavior:

- If `Blocked`:
  - Respond with refusal_message (tone + category).
  - Mark response as `blocked=True`.
- If `Allowed`:
  - Proceed to rate limiting and processing pipeline.

### Tier-Aware Routing / Degradation

States (per request at router):

- `Routing`: evaluating candidate pools.
- `Forwarded`: successfully forwarded to a worker pool.
- `Shed`: could not forward (all pools unhealthy/overloaded) → graceful degradation message.

Transitions:

```mermaid
stateDiagram-v2
  [*] --> Routing
  Routing --> Forwarded: at least one candidate\npool healthy & admits request
  Routing --> Shed: all candidate pools\nunhealthy/overloaded
  Forwarded --> [*]
  Shed --> [*]
```

Tier-specific candidate sets:

- Enterprise:
  - `["priority", "overflow"]`
- Premium:
  - `["standard", "overflow", "priority"]`
- Free:
  - `["overflow"]`

Degradation semantics:

- Enterprise:
  - Prefer priority; only falls back to overflow if needed.
  - Never displaced by lower tiers (router checks pool health/load, not global fairness).
- Premium:
  - Uses standard under normal conditions; may fall back to overflow or priority.
- Free:
  - Only uses overflow; under heavy load, router may respond with a friendly “I’m busy” message (Shed).

### Analytics Queue / Flusher

States:

- `Idle`: queue empty, flusher waiting.
- `Collecting`: events being enqueued; batch being built.
- `Flushing`: writing batch to Mongo.
- `Stopping`: stop signal received; draining remaining events.
- `Stopped`: background task finished.

Transitions:

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Collecting: track(event)\n(queue not empty)
  Collecting --> Collecting: more events\n(below batch/interval threshold)
  Collecting --> Flushing: batch size >= max\nor interval elapsed
  Flushing --> Idle: batch flushed\nqueue empty
  Flushing --> Collecting: batch flushed\nqueue still has items

  Idle --> Stopping: stop() called
  Collecting --> Stopping: stop() called
  Flushing --> Stopping: stop() called
  Stopping --> Stopped: queue drained\nfinal flush done
```

Implementation details:

- `analytics.start()`:
  - Spawns background task (`_run`) which loops until `_stopping` and queue empty.
- `analytics.track(event)`:
  - `put_nowait` into bounded queue; if full, increments drop counter.
- `analytics.stop()`:
  - Sets `_stopping=True` and awaits flusher task.

