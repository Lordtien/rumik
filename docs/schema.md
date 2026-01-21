## Data model (MongoDB 7+)

This project uses **UUID strings** as primary IDs across collections (stored in Mongo as `_id: <uuid-str>`).

### 1) `users`

Represents an Ira end-user (WhatsApp/app identity resolved upstream).

**Example document**

- `_id` (string UUID, PK)
- `tier` (string enum: `free|premium|enterprise`)
- `created_at` (date)
- `status` (string enum: `active|disabled`)
- `active_session_key` (string, denormalized pointer for hot path; see sessions)
- `last_seen_at` (date)
- `limits` (object; tier-derived defaults persisted for audit)

### 2) `personalities`

Per-user personality configuration used to generate natural rate-limit / safety responses.

**Example document**

- `_id` (string UUID, PK)
- `user_id` (string UUID, FK -> users._id)
- `version` (int)
- `tone` (string: e.g. `warm`, `playful`, `direct`)
- `style_prompts` (array[string])
- `safety_voice` (object: templates / refusal style)
- `updated_at` (date)

### 3) `sessions` (definition)

**Session = calendar-day conversation container** per user.

Uniqueness rule: at most **one session per user per day**.

We encode “day” as a stable key: `YYYY-MM-DD` in UTC.

**Example document**

- `_id` (string UUID, PK)
- `user_id` (string UUID, FK -> users._id)
- `day` (string, `YYYY-MM-DD`)
- `status` (string enum: `active|closed`)
- `started_at` (date)
- `last_activity_at` (date)
- `message_count` (int)
- `tier` (denormalized tier for analytics)

### 4) `messages`

All messages for a session (user + assistant + system-internal notes).

**Example document**

- `_id` (string UUID, PK)
- `user_id` (string UUID, FK -> users._id)
- `session_id` (string UUID, FK -> sessions._id)
- `role` (string enum: `user|assistant|system`)
- `content` (string)
- `created_at` (date)
- `tier` (denormalized tier for analytics)
- `safety` (object: flags like `blocked`, `category`, `score`)

