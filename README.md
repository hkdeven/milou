# Milou

<img align="right" src="docs/assets/milou.png" width="75" alt="Milou, Tintin's loyal scout">
Milou is Tintin's loyal scout: the one who runs ahead, notices what is unseen,
and fetches the context needed for the next decision. In this project, Milou
is a bounded supervisor/control plane over small, replaceable automation
routines. It supports human judgment; it does not replace it.

<br clear="left">

## What Milou does

Routines do the domain work. Milou manages their registry, planning,
scheduling, context flow, health, evaluation, and approval boundaries. This
keeps capabilities small and replaceable instead of hiding them inside one
unbounded prompt.

The documented initial capabilities are:

- a routine contract and activation checklist;
- a read-only, GitHub-first rollout model;
- an implemented fixture-backed daily global AI news brief that emphasizes
  non-US coverage,
  source and geographic diversity, freshness, deduplication, direct citations,
  and uncertainty handling; and
- implemented fixture-backed Daily Wins and Morning Brief/Meeting Prep
  routines that distinguish verified facts from inferred impact and preserve
  meeting context, decisions, questions, commitments, and inaccessible links; and
- implemented fixture-backed Commitments/Follow-Up, Stale Work Finder, and
  Dependabot PR Triage routines with cited, read-only recommendations; and
- implemented fixture-backed Launch Decoder, Launch Radar, and Travel Logistics
  Tracker routines with explicit evidence, timing, uncertainty, and missing
  information; and
- an implemented fixture-backed, authenticated `github-change-radar` that
  prioritizes organization-wide Allied-Steel-Buildings activity (especially
  changes not involving the user), then secondary configured repositories,
  with bounded event coverage, citations, summaries, risk signals, and visible
  API/permission failures; and
- a deterministic supervisor planner/dispatcher with read-only permissions,
  routing metadata, and visible failures; and
- a vetted initial global AI news source set; and
- a durable local scheduler with timezone-aware daily/weekly cadence,
  idempotent run ledger, bounded visible retries, and authenticated health
  reporting.

## Safety boundary

The default mode is read-only. Milou may inspect, summarize, plan, recommend,
and report evidence within a declared routine scope. Sending messages,
changing calendar events, approving or merging code, publishing reports, or
modifying production systems requires a separate explicit approval boundary.

Live integrations, feeds, APIs, scrapers, and external write actions are not
implemented. Local report persistence, scheduled-generation callable/CLI
support, and private authenticated archive delivery are implemented; deployment
still requires an operator-managed private host and reverse proxy.

## Execution rule

If a blocker appears, record it and continue independent implementation, tests,
fixtures, UI, storage, and authentication-boundary work. Pause only for a
safety issue, a missing required user decision, or a correctness dependency
that makes further work unsafe or misleading.

## Repository map

- [`docs/architecture.md`](docs/architecture.md) — control-plane model,
  responsibilities, lifecycle, and safety boundaries
- [`docs/automation-case-study.md`](docs/automation-case-study.md) — living
  decisions, build log, validation results, and lessons learned
- [`docs/news-sources.md`](docs/news-sources.md) — vetted sources and
  geographic/editorial rationale for the news brief
- [`routines/routine-contract.md`](routines/routine-contract.md) — reusable
  contract template and activation checklist
- [`routines/daily-global-ai-news-brief.md`](routines/daily-global-ai-news-brief.md)
  — proposed daily news brief contract
- [`routines/daily-wins-recap.md`](routines/daily-wins-recap.md) and
  [`routines/morning-brief-meeting-prep.md`](routines/morning-brief-meeting-prep.md)
  — fixture-backed routine contracts
- [`routines/commitments-follow-up-tracker.md`](routines/commitments-follow-up-tracker.md),
  [`routines/stale-work-finder.md`](routines/stale-work-finder.md), and
  [`routines/dependabot-pr-triage.md`](routines/dependabot-pr-triage.md)
  — read-only triage contracts
- [`routines/launch-decoder.md`](routines/launch-decoder.md),
  [`routines/launch-radar.md`](routines/launch-radar.md), and
  [`routines/travel-logistics-tracker.md`](routines/travel-logistics-tracker.md)
  — launch and travel contracts
- [`routines/github-change-radar.md`](routines/github-change-radar.md) —
  bounded authenticated repository-change contract
- [`CHANGELOG.md`](CHANGELOG.md) — notable project changes
- [`milou_news/`](milou_news/) — read-only standard-library news-brief runtime
- [`milou_news/report.py`](milou_news/report.py) and
  [`milou_news/render_html.py`](milou_news/render_html.py) — the structured
  report model every renderer shares, and the HTML layout that keeps ordering,
  tiers, and signals instead of flattening them into prose
- [`milou_news/archive.py`](milou_news/archive.py) and
  [`milou_news/web.py`](milou_news/web.py) — dated persistence and private
  browser/API-authenticated report delivery and health/status endpoints
- [`milou_news/scheduler.py`](milou_news/scheduler.py) and
  [`routines/scheduler-configuration.md`](routines/scheduler-configuration.md)
  — durable routine configuration, due calculation, and run ledger
- [`docs/deployment.md`](docs/deployment.md) — private-host deployment
  requirements (no deployment is performed here)
- [`fixtures/news.json`](fixtures/news.json) — deterministic sample input for
  the CLI and tests
- [`fixtures/activity.json`](fixtures/activity.json) and
  [`fixtures/meetings.json`](fixtures/meetings.json) — deterministic routine fixtures
- [`fixtures/github-radar.json`](fixtures/github-radar.json) and
  [`fixtures/github-radar-config.json`](fixtures/github-radar-config.json) —
  deterministic radar demo inputs

## Status and next steps

The safe vertical slices are implemented locally: a
read-only standard-library runtime can fetch configured JSON sources, report
clear failures, filter freshness, deduplicate, rank with explainable global and
non-US signals, enforce source/geographic diversity, and render cited Markdown.
Run `python3 -m unittest discover -s tests` and
`python3 -m milou_news --fixture fixtures/news.json` to exercise it. The
delivery slice stores dated Markdown/JSON reports, supports fixture-backed
generation, and serves a responsive authenticated archive. Authentication
fails closed without an injected `MILOU_REPORT_TOKEN`; no credentials are
committed and no public hosting is used. Live integrations and deployment
remain out of scope. Browser users authenticate at `/login` and receive a
short-lived Secure, HttpOnly, SameSite session cookie; API and CLI clients
continue to send `Authorization: Bearer ...`.

Reports render in two formats from one structured model. Markdown remains the
stored, quotable record; HTML is the reading surface. The structured report
decides ordering by consequence before recency, gives every field its own
column, promotes coverage and permission failures above the findings, and lets
boilerplate recede to a footer. Generate one with
`python3 -m milou_news --routine github-change-radar --config path/to/radar.json --format html`,
or `--fixture fixtures/news.json --format html` for the daily brief. The GitHub
Change Radar and the daily global AI news brief build structured reports today;
the other routines still render as Markdown and display from it unchanged.

When a report is stored with `--store`, its structure is saved alongside the
Markdown so the authenticated archive can render the full layout later without
re-running the routine. Reports captured before this existed still display,
from their stored Markdown.

The scheduler is local-only and uses SQLite. Inspect it with
`python3 -m milou_news status --config fixtures/scheduler.json`; use
`scheduler`, `run`, and `ledger` for configuration, execution, and audit
history. The authenticated archive's `/status` and `/health` endpoints expose
operational counts and the latest failure rather than hiding errors.

**Status:** Daily Wins, Morning Brief/Meeting Prep, Commitments/Follow-Up,
Stale Work Finder, Dependabot PR Triage, Launch Decoder, Launch Radar, and
Travel Logistics Tracker are implemented as read-only fixture-backed routines.
The deterministic supervisor layer plans and dispatches registered routines.
Live integrations and deployment remain out of scope; local scheduling and
health reporting are implemented.

The GitHub Change Radar defaults to organization-wide
`Allied-Steel-Buildings` monitoring and tracks secondary repositories and
organizations only when configured, all within a bounded recent window. It
uses authenticated `gh api` GET calls (or deterministic fixtures), never
exposes the token, performs no mention filtering or unbounded scan, and reports
pagination, rate-limit, coverage, and permission/API failures visibly. Generate a
real local report with
`python3 -m milou_news --routine github-change-radar --config path/to/radar.json`
and optionally persist it with `--store reports`. No server is started by this
command and no credentials are committed.

For a local authenticated archive, keep the token outside the repository in a
permission-restricted file such as `$HOME/.config/milou/report-token` (or use
an existing operator-managed secret). Read it without printing it, then start
or restart the server from a terminal:

```sh
TOKEN_FILE="$HOME/.config/milou/report-token"
read -r MILOU_REPORT_TOKEN < "$TOKEN_FILE"
export MILOU_REPORT_TOKEN
python3 -c 'from milou_news.archive import ReportStore; from milou_news.web import serve; serve(ReportStore("reports"), host="127.0.0.1", port=8768)'
```

If no token file exists, create one with a local secret generator and restrict
its permissions; do not paste or echo the token:
`mkdir -p "$HOME/.config/milou" && umask 077 && python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$HOME/.config/milou/report-token"`.
Open `http://127.0.0.1:8768/` in a browser and use the **Sign out** control
when finished. The archive is intentionally localhost-only unless an operator
explicitly places it behind a private authenticated network boundary.

The current local demo report directory is `/tmp/milou-live-reports`; open it
in Finder with `open /tmp/milou-live-reports`. If a different report directory
is configured, replace that path in the command.

The case study is updated for every project work session with the relevant
decision, implementation change, validation result, or lesson learned. This
README is the canonical current overview on `main` and must be refreshed when
Milou's identity, architecture, capabilities, repository structure, status,
or next steps materially change. Detailed rules belong in the linked
documents, not duplicated here.

All generated reports begin with a compact Report KPIs block. Empty activity
sections and routine categories are omitted; a report with no substantive
findings says “No activity to report” while retaining coverage, API, and
permission warnings. The Change Radar KPI block also includes repositories
scanned, change types, contributors, and high-risk changes.
