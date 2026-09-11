# Changelog

All notable changes to Milou are recorded here. The living case study contains
the detailed reasoning and decisions behind each change.

## Unreleased

### Added

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

### Not implemented

- External integrations, routine execution, scheduling, and persistence remain
  intentionally out of scope for this initial setup.
