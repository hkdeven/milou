# Changelog

All notable changes to Milou are recorded here. The living case study contains
the detailed reasoning and decisions behind each change.

## Unreleased

### Added

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
