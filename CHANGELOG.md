# Changelog

All notable changes to Milou are recorded here. The living case study contains
the detailed reasoning and decisions behind each change.

## Unreleased

### Added

- Added report signal-to-noise refinement: consistent KPI blocks, omission of
  empty activity sections/categories, concise no-activity reports, and
  separately visible coverage/API/permission warnings. Change Radar KPIs now
  include repositories scanned, change types, contributors, and high-risk
  counts.

- Added browser-friendly report authentication: a minimal root login form,
  constant-time token validation, short-lived server-side Secure/HttpOnly/
  SameSite session cookies, logout, and retained Bearer API/CLI support.
  Unconfigured tokens still fail closed and credentials are not emitted in
  URLs, HTML, or logs.
- Added the read-only, bounded GitHub Change Radar with authenticated `gh`
  CLI/API collection, explicit repository/organization scope, direct
  citations, categories, timestamps, visible failures, deterministic fixtures,
  tests, and a real-report CLI path. No token is exposed or stored.
- Clarified Allied-Steel-Buildings as the default/highest-priority organization
  scope, added non-user activity priority, bounded pagination/rate-limit
  visibility, expanded event fields and lifecycle categories, per-repository
  and per-author summaries, risk signals, and explicit coverage gaps without
  mention filtering.
- Added fixture-backed Launch Decoder, Launch Radar, and Travel Logistics
  Tracker routines with canonical CLI aliases, registry metadata, contracts,
  fixtures, cited uncertainty/unknowns, and read-only tests.
- Added deterministic supervisor planning/dispatch with explicit read-only
  permission checks, routing metadata, and failure visibility.
- Made `ReportStore` filenames collision-safe for same-second reports and
  normalized callable archive labels to canonical routine names.

- Added fixture-backed `daily-wins-recap` and
  `morning-brief-meeting-prep` routines, registry entries, CLI selection,
  callable storage, deterministic fixtures, contracts, and report output.

- Added a standard-library delivery slice with dated Markdown/JSON report
  persistence, fixture-backed generation callable/CLI storage, and a
  responsive bearer-authenticated index/archive that fails closed when its
  token is not configured.
- Added private-host/reverse-proxy deployment guidance without deploying or
  adding credentials.

- Added the first safe vertical slice of the daily global AI news brief:
  explicit routine registry, configured sources, injectable JSON fetching,
  freshness filtering, duplicate handling, explainable ranking, diversity
  selection, citation-linked Markdown output, fixtures, tests, and a CLI.
- Established the initial repository structure for Milou, a bounded
  supervisor/control plane over replaceable routines.
- Added the living automation case study under `docs/`.
- Added the supervisor architecture and safety boundaries.
- Added a routine contract and activation checklist under `routines/`.
- Added the project README and documentation workflow rule.
- Added a vetted initial source set for a global AI news brief.
- Added the proposed `daily-global-ai-news-brief` routine contract with
  ranking, geographic weighting, freshness, citation, uncertainty, and
  read-only requirements.
- Corrected the canonical GitHub repository identity to
  [`hkdeven/milou`](https://github.com/hkdeven/milou); Milou remains the
  supervisor agent name.
- Added the supplied Milou visual identity at `docs/assets/milou.png` and
  linked it from the canonical README.
- Refined the README image presentation to a smaller, left-aligned,
  text-wrapping figure without changing the source asset.
- Moved the image to the start of the introductory paragraph using inline
  left-float markup so the opening text wraps around it.
- Recorded the accepted manual README layout correction and the lesson to
  validate GitHub-rendered layout visually.

### Not implemented

- Live external integrations, credentials, and deployment remain intentionally
  out of scope; the runtime is read-only and uses fixture/mocked fetching in
  tests.
- Live activity/calendar integrations and deployment remain intentionally out
  of scope; these routines accept local fixtures only.
- Added fixture-backed Commitments and Follow-Up Tracker, Stale Work Finder,
  and Dependabot PR Triage routines, registry entries, canonical CLI paths,
  contracts, fixtures, and read-only tests/documentation.
- Made same-second archived routine reports distinct by including the routine
  name in stored filenames.

- Added durable SQLite routine configuration and scheduler ledger with daily/
  weekly timezone-aware due calculation, enabled state, bounded visible retries,
  idempotency keys, read-only permission enforcement, and scheduler/status/run/
  ledger CLI commands.
- Added authenticated archive health/status JSON endpoints and scheduler
  configuration documentation.
- Clarified that live repository-change tracking across personal and
  organization repositories is not implemented; a separately scoped
  read-only tracker remains the next repository-focused slice.
