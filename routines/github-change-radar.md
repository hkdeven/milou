# GitHub Change Radar

- **Name:** `github-change-radar`
- **Purpose:** Monitor Allied-Steel-Buildings organization-wide first, especially activity not involving the authenticated user, then report secondary configured repositories or organizations.
- **Version:** `0.1.0`
- **Status:** tested
- **Trigger:** manual or daily schedule
- **In scope:** bounded event pages for commits (author/committer/branch/message/link), branch lifecycle, PR lifecycle/reviewers/labels/status, issues, releases/tags, workflows/checks/failures, Dependabot/security, and repository lifecycle where permitted. Includes per-repository and per-author counts and notable/high-risk changes.
- **Out of scope:** repository discovery beyond the configured organization cap, historical search, writes, notifications, and public hosting.

## Inputs and output

`Allied-Steel-Buildings` is the default/highest-priority organization.
`repositories`, secondary `organizations`, `window_hours` (1–744),
`max_repositories_per_org` (1–100), and `max_pages` (1–5) are local configuration.
The live source is
the authenticated `gh api` CLI; tests use `fixtures/github-radar.json`.
Markdown reports contain user activity, configured-scope activity, categories,
timestamps, direct URLs, and visible API/permission failures.

## Permissions and reliability

The routine is read-only and uses no token argument or shell interpolation.
`gh` owns authentication. Missing auth, denied endpoints, malformed responses,
timeouts, rate-limit headers, pagination caps, and missing citations remain
visible in the report. No mention filtering is applied. A run is bounded and
never performs an unbounded organization scan.

## Evaluation and limitations

Fixtures cover user activity, organization scope, deduplication, and errors.
GitHub events are a recent activity feed, not a complete historical audit;
items outside the configured window or unsupported event types are unknown.
