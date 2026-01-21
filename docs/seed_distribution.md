## Seed distribution (realistic-ish)

Target scale (assignment): ~1,000,000 documents per collection.

### Tier distribution

- **Free**: 90%
- **Premium**: 9%
- **Enterprise**: 1%

### Activity skew

We’ll generate a long-tail distribution:

- Most users: 0–2 sessions/month, low message counts
- Small cohort: daily sessions with high message counts

### Session definition reminder

Session = **one per user per UTC day** (`day = YYYY-MM-DD`).

