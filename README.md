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
- a proposed daily global AI news brief that emphasizes non-US coverage,
  source and geographic diversity, freshness, deduplication, direct citations,
  and uncertainty handling; and
- a vetted initial global AI news source set.

## Safety boundary

The default mode is read-only. Milou may inspect, summarize, plan, recommend,
and report evidence within a declared routine scope. Sending messages,
changing calendar events, approving or merging code, publishing reports, or
modifying production systems requires a separate explicit approval boundary.

Live integrations, feeds, APIs, scrapers, scheduling, persistence, report
delivery, and external write actions are not implemented yet.

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
- [`CHANGELOG.md`](CHANGELOG.md) — notable project changes
- [`milou_news/`](milou_news/) — read-only standard-library news-brief runtime
- [`fixtures/news.json`](fixtures/news.json) — deterministic sample input for
  the CLI and tests

## Status and next steps

The first safe vertical slice is implemented on the development branch: a
read-only standard-library runtime can fetch configured JSON sources, report
clear failures, filter freshness, deduplicate, rank with explainable global and
non-US signals, enforce source/geographic diversity, and render cited Markdown.
Run `python3 -m unittest discover -s tests` and
`python3 -m milou_news --fixture fixtures/news.json` to exercise it. Live
integrations, credentials, scheduling, persistence, and delivery remain out of
scope.

The case study is updated for every project work session with the relevant
decision, implementation change, validation result, or lesson learned. This
README is the canonical current overview on `main` and must be refreshed when
Milou's identity, architecture, capabilities, repository structure, status,
or next steps materially change. Detailed rules belong in the linked
documents, not duplicated here.
