# Milou

Canonical repository: [github.com/hkdeven/milou](https://github.com/hkdeven/milou)

Milou is a bounded supervisor and control plane for small, replaceable
automation routines. The routines do domain work; Milou manages their
registry, planning, scheduling, context flow, health, evaluation, and
human-approval boundaries.

The project starts with a read-only, GitHub-first rollout. External
integrations are intentionally not implemented yet. The initial design and
decisions are recorded in the [living case study](docs/automation-case-study.md).

## Repository layout

- [`docs/automation-case-study.md`](docs/automation-case-study.md) — the
  running article and project record
- [`docs/architecture.md`](docs/architecture.md) — the supervisor/control-plane
  architecture and boundaries
- [`routines/routine-contract.md`](routines/routine-contract.md) — the contract
  and template for replaceable routines
- [`routines/daily-global-ai-news-brief.md`](routines/daily-global-ai-news-brief.md)
  — proposed daily global AI news brief contract
- [`docs/news-sources.md`](docs/news-sources.md) — vetted initial source set
- [`CHANGELOG.md`](CHANGELOG.md) — notable project changes

## Working rule

Whenever work occurs on this project, update the living case study with the
relevant decision, implementation change, validation result, or lesson
learned. The case study is part of the project workflow, not a separate
documentation task.

## Current status

The first proposed capability is a read-only daily global AI news brief.
Routine execution, scheduling, and external integrations will be added only
after their contracts, permissions, approval boundaries, and evaluation
criteria are explicit.
