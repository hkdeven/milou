# Scheduler and routine configuration

The local scheduler is deliberately durable and boring: SQLite stores registered
routine configuration and a run ledger. Configuration is JSON (see
`fixtures/scheduler.json`) and may declare `daily`, `weekly`, or `on-demand`
routines, an `HH:MM` local time, IANA timezone, enabled state, retry limit, and
fixture path. All scheduled routines must declare `read-only` access (the
scheduler rejects other permissions).

Run `python3 -m milou_news scheduler --config fixtures/scheduler.json --database
scheduler.sqlite3` to load configuration and inspect status. `run` evaluates
currently due routines, `ledger` prints every attempt, and `status` reports
configured/enabled/due counts and failures. A routine gets one deterministic
ledger key per local day or ISO week; successful keys are never run twice.
Failures remain visible and may retry up to the configured limit. No error is
converted into a successful report.
