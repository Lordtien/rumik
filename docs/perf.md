## Query performance & explain outputs

### Hot path 1: active session for user (today)

- **Shape**: `SessionsRepo.get_active_for_user_today(user_id)`
- **Index used**: `sessions.user_day_status` (`{ user_id: 1, day: 1, status: 1 }`)
- **Expected plan**:
  - Index scan on equality for `user_id`, `day`, `status`
  - Sort by `started_at` using in-index order where possible
  - Projection of small subset of fields

- Small dataset (~10k):
  - `executionTimeMillis`: **10 ms**
  - `totalDocsExamined` (users stage): **1**
  - `totalKeysExamined` (users stage): **1**
  - `totalDocsExamined` (sessions $lookup): **10000**
  - `totalKeysExamined` (sessions $lookup): **0**

- Large dataset (~1M):
  - `executionTimeMillis`: **1 ms**
  - `totalDocsExamined` (users stage): **1**
  - `totalKeysExamined` (users stage): **1**
  - `totalDocsExamined` (sessions $lookup): **1**
  - `totalKeysExamined` (sessions $lookup): **1** (index `user_day_status`)

### Hot path 2: recent messages for session (N=20)

- **Shape**: `MessagesRepo.get_recent_for_session(session_id, limit_n=20)`
- **Index used**: `messages.session_createdAt_desc` (`{ session_id: 1, created_at: -1 }`)
- **Expected plan**:
  - Index scan on equality for `session_id`
  - Index-order sort on `created_at desc`
  - Early `limit(20)` to cap scanned docs

- Small dataset (~10k):
  - `executionTimeMillis`: **18 ms**
  - `totalDocsExamined` (sessions stage): **1**
  - `totalKeysExamined` (sessions stage): **1**
  - `totalDocsExamined` (messages $lookup): **20000**
  - `totalKeysExamined` (messages $lookup): **0**

- Large dataset (~1M):
  - `executionTimeMillis`: **0 ms**
  - `totalDocsExamined` (sessions stage): **1**
  - `totalKeysExamined` (sessions stage): **1**
  - `totalDocsExamined` (messages $lookup): **1**
  - `totalKeysExamined` (messages $lookup): **1** (index `session_createdAt_desc`)

### Tier/activity aggregation

- Small dataset (~10k):
  - `executionTimeMillis`: **5 ms**
  - `totalDocsExamined`: **10000**
  - `totalKeysExamined`: **0**

- Large dataset (~1M):
  - `executionTimeMillis`: **489 ms**
  - `totalDocsExamined`: **1,000,000**
  - `totalKeysExamined`: **0** (collection scan + group)


