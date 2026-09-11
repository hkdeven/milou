# Milou

Canonical repository: [github.com/hkdeven/milou](https://github.com/hkdeven/milou)

Milou is a bounded supervisor and control plane for small, replaceable
automation routines. The routines do domain work; Milou manages their
registry, planning, scheduling, context flow, health, evaluation, and
human-approval boundaries. Milou is the supervisor agent name; it is not a
replacement for the human's judgment.

## Current overview

This README is the canonical current overview of the project on `main`.
Keep it concise and update it whenever Milou's identity, architecture,
documented or implemented capabilities, repository structure, status, or next
steps materially change. Detailed decisions belong in the linked documents.

The project is currently documentation-first and read-only:

- **Documented:** supervisor/control-plane architecture, routine lifecycle and
  safety boundaries, a reusable routine contract, and a vetted global AI news
  source set.
- **Proposed capability:** a daily global AI news brief that emphasizes
  non-US coverage, source and geographic diversity, freshness, deduplication,
  citations, and uncertainty handling.
- **Not implemented:** live integrations, feeds, APIs, scrapers, scheduling,
  persistence, report delivery, or external write actions.

## Repository layout

- [`docs/automation-case-study.md`](docs/automation-case-study.md) — the
  living article, decisions, validation, and build log
- [`docs/architecture.md`](docs/architecture.md) — the supervisor/control-plane
  architecture and boundaries
- [`routines/routine-contract.md`](routines/routine-contract.md) — the contract
  and template for replaceable routines
- [`routines/daily-global-ai-news-brief.md`](routines/daily-global-ai-news-brief.md)
  — proposed daily global AI news brief contract
- [`docs/news-sources.md`](docs/news-sources.md) — vetted initial source set
- [`CHANGELOG.md`](CHANGELOG.md) — notable project changes

## Status and next steps

The repository structure and initial routine specifications are published on
the canonical `main` branch. The next step is to validate the news-brief
contract with representative fixtures and an explicit evaluation process
before implementing any live collection or delivery.

Before implementation, keep the read-only boundary, source-access caveats,
direct citations, geographic diversity, and human approval requirements
explicit. See the detailed routine contract and architecture document for
the full rules.

The living case study remains the project workflow record: every work session
must update it with the relevant decision, implementation change, validation
result, or lesson learned.
