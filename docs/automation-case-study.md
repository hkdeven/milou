# Automating the Invisible Work: A Leadership Workflow Case Study

_Working draft — started September 11, 2026_

## Overview

I am exploring how scheduled AI agents can reduce the invisible operational work
that accumulates across GitHub, meetings, messages, email, and documents. The
goal is not to automate leadership or replace human judgment. The goal is to
automate the scaffolding: finding context, surfacing forgotten commitments,
summarizing activity, and preparing useful briefs.

This is a living case study. I will update it as I design, test, refine, and
adopt each automation.

**Working rule:** Any time I work on this project, I will update this case
study with the relevant decision, implementation change, test result, or lesson
learned. The case study is part of the project workflow, not a separate
documentation task.

## Project home and version control

The initial draft was created in the Copilot session workspace so it could be
started immediately. That is temporary storage, not the project’s long-term
home. The case study, supervisor design, routine contracts, prompts, tests,
and implementation should live together in a dedicated Git repository so the
work is versioned, shareable, reviewable, and easy to continue across sessions.

**Decision:** Use the canonical GitHub repository
[`hkdeven/milou`](https://github.com/hkdeven/milou) for this project and keep
this document in it before implementation begins.

**Repository status:** Initial repository structure is established in
[`hkdeven/milou`](https://github.com/hkdeven/milou).

### September 11, 2026 — Tooling and access planning

- Identified that repository creation requires authenticated GitHub write
  access, typically through the `gh` CLI or GitHub REST API.
- Identified the likely integration needs: GitHub, calendar, email, messaging,
  documents, and a durable scheduler/automation runtime.
- Decided to begin with least-privilege, read-only integrations and add write
  permissions only for explicitly approved actions.
- Confirmed that GitHub SSH authentication is already configured on the
  machine. This will support cloning and pushing to an existing repository, but
  repository creation still requires GitHub API or `gh` authentication.
- Chose GitHub CLI (`gh`) as the single standard access path. It provides the
  GitHub API access needed to create and manage the project repository while
  retaining SSH for Git transport.
- Confirmed that `gh` is authenticated on the development machine. Repository
  creation can now proceed through the chosen access path.

### September 11, 2026 — Initial repository structure

- Initialized the Milou project repository and moved this living case study
  into `docs/automation-case-study.md`.
- Added the supervisor architecture, routine contract template, README, and
  changelog.
- Preserved the read-only, GitHub-first rollout and the decision not to
  implement external integrations yet.
- Established the repository rule that every project change updates this case
  study with the relevant decision, implementation change, validation result,
  or lesson learned.
- **Repository status:** Initial documentation structure ready for review;
  implementation and external integrations are not yet started.

### September 11, 2026 — Daily global AI news brief requirement

- Added the next Milou capability: a daily, read-only global AI
  authority/news brief.
- The brief must identify the most globally discussed AI stories while
  explicitly emphasizing substantial non-US coverage and geographic
  diversity.
- Each item must avoid duplicate coverage, include a headline, only a few
  concise sentences when context is needed, and provide a direct article or
  source link.
- The initial source set will be vetted and documented before any live news
  integration is implemented.
- The routine will define freshness, ranking, source-diversity and
  geographic-weighting signals, citation and uncertainty requirements, and a
  read-only safety boundary.
- **Current project date:** September 11, 2026.

### September 11, 2026 — Initial news source set and routine contract

- Vetted an initial eight-source mix spanning global impact, technical
  analysis, European policy, Asian business and technology, China, and
  commercial AI reporting.
- Selected Rest of World as the core non-US/global-impact source and paired it
  with MIT Technology Review, IEEE Spectrum, THE DECODER, South China Morning
  Post, Euractiv, TechCrunch, and Nikkei Asia.
- Documented each source's rationale, geographic focus, role, direct links,
  and access or editorial caveats in `docs/news-sources.md`.
- Defined the proposed `daily-global-ai-news-brief` routine with a 24-hour
  freshness preference, duplicate clustering, source and geographic
  diversity constraints, direct citations, uncertainty labels, and a
  read-only boundary.
- Checked the eight source-section links; seven returned successfully and
  Euractiv returned HTTP 403 to automated retrieval, which is now documented
  as an access caveat rather than hidden.
- Decided not to implement live feeds, APIs, scrapers, credentials, or
  publishing actions yet.

### September 11, 2026 — Canonical repository rename

- Corrected the project's canonical repository from
  `hkdeven/work-automation-supervisor` to
  [`hkdeven/milou`](https://github.com/hkdeven/milou).
- Confirmed that **Milou** remains the supervisor agent name; only the GitHub
  repository identity changed.
- Updated repository documentation and the local Git remote to use the
  canonical `hkdeven/milou` URL.

### September 11, 2026 — Initial repository publication

- Found that the initialized setup and documentation files existed only on
  the local feature branch, so the renamed GitHub repository appeared empty on
  its default branch.
- Published the complete initial Milou setup to the canonical
  `hkdeven/milou` repository and merged it to the default `main` branch.
- Verified that `README.md` and the documentation are visible from `main`.

### September 11, 2026 — Publication verification

- Rechecked the initialization branch, local history, and canonical remote
  before repeating the publication verification.
- Confirmed the remote remains `https://github.com/hkdeven/milou.git` and that
  the initialization pull request is merged.
- Confirmed the published `main` branch exposes `README.md`, the case study,
  architecture and source documentation, routine contracts, and
  `CHANGELOG.md` through the authenticated GitHub contents API.

### September 11, 2026 — Canonical README maintenance rule

- Established `README.md` on `main` as the canonical current project overview.
- The README must be updated whenever Milou's identity, architecture,
  documented or implemented capabilities, repository structure, status, or
  next steps materially change.
- The README should remain concise and link to detailed architecture, routine,
  source, and case-study documentation rather than duplicating it.

### September 11, 2026 — README identity clarification

- Feedback identified that the README was too generic and did not clearly
  connect the project to Tintin and Milou.
- Decided to make the README's opening explain Milou as Tintin's loyal scout:
  the supervisor runs ahead, notices what is unseen, and fetches context
  without taking over human judgment.
- Kept the README technically concise while retaining the control-plane
  concept, documented capabilities, safety boundary, repository map, current
  status, and documentation-maintenance rules.

### September 11, 2026 — Milou visual identity

- Adopted the supplied Milou image as the repository's visual identity.
- Added it as a resized repository asset and linked it from the canonical
  README with a concise caption connecting the image to Tintin's loyal scout.
- Preserved the image's aspect ratio and legibility; no unrelated image was
  substituted.

### September 11, 2026 — README image layout refinement

- Feedback identified that the README image presentation was too large.
- Decided to keep `docs/assets/milou.png` unchanged while displaying it at a
  modest width, left-aligned with text wrapping around it.
- Preserved accessible alt text and the concise Tintin/Milou caption in the
  README.

### September 11, 2026 — README introductory paragraph image placement

- Refined the layout requirement so the image must start the first
  introductory paragraph rather than occupy a standalone figure block.
- Chose GitHub-compatible inline left-float markup immediately before the
  paragraph text, with explicit spacing and a clear break after the wrapped
  introduction.
- Preserved the 120px display width, source aspect ratio, accessible alt text,
  and Tintin/Milou context.

### September 11, 2026 — Manual README layout correction

- The README image layout was manually corrected and the final rendered
  arrangement was accepted.
- Preserved the user's manual README change without further layout edits.
- Learned that GitHub-rendered layout must be visually validated rather than
  inferred from source markup alone.

### September 11, 2026 — What's next: first safe vertical slice

- Chose the read-only daily global AI news brief as Milou's first implemented
  vertical slice.
- The first slice will provide a small maintainable runtime with an explicit
  routine model and registry, configured source definitions, source
  fetching/parsing with visible failures, freshness filtering, deduplication,
  global-discussion ranking with non-US weighting, geographic and source
  diversity, and citation-linked Markdown output.
- Tests will use local fixtures and mocked fetching only; no live external
  integrations or credentials will be added.
- The slice will include a simple CLI or callable entry point for generating a
  report from fixture data while preserving the read-only safety boundary.

### September 11, 2026 — First vertical slice implementation

- Added `milou_news/`, a small Python standard-library runtime with an explicit
  `daily-global-ai-news-brief` routine model and registry.
- Added configured source definitions matching the documented initial source
  set. JSON fetching is GET-only, injectable for tests, and converts malformed
  payloads, missing fields, invalid timestamps, and unavailable sources into
  visible per-source failures rather than guessed content.
- Implemented UTC freshness filtering, event-key/title deduplication, weighted
  ranking signals (global discussion, significance, freshness, evidence, and a
  non-US adjustment), and greedy source/geographic diversity selection.
- Implemented citation-linked Markdown output with publication metadata,
  ranking signals, uncertainty labels, duplicate counts, and unavailable-source
  notes. The CLI reads a local fixture and writes only to stdout.
- Added deterministic fixture data and standard-library unit tests covering the
  registry, parser failures, mocked fetching, freshness, deduplication,
  explainable ranking, diversity, and report citations.
- Validation: `python3 -m unittest discover -s tests` passes (6 tests), and the
  fixture CLI produces a cited report without network access.
- **Status:** Safe fixture-backed slice implemented; live collection and
  delivery remain deliberately unimplemented.

### September 12, 2026 — Private device-independent web delivery

- Chose private/authenticated web access so Milou reports can be viewed from
  any device while remaining inaccessible to the public.
- Identified hosted web delivery as the next layer after the news engine:
  scheduled generation, dated report storage, and a hosted index/archive.
- Kept public hosting and GitHub Pages out of scope because the reports are
  private.
- This phase will implement a local/testable authenticated web layer and
  deployment documentation without cloud credentials or deployment secrets.

### September 12, 2026 — Unblock and continue execution rule

- Established a standing execution rule: when Milou encounters a blocker,
  record it and continue independent related implementation, tests, fixtures,
  UI, storage, and authentication-boundary work.
- A true pause is warranted only for a safety issue, a missing required user
  decision, or a correctness dependency that makes further work unsafe or
  misleading.
- Deployment-provider details and credentials are not prerequisites for the
  current local/testable web-delivery slice, so that work should continue
  while deployment remains documented as a separate user-action blocker.

### September 12, 2026 — Scope clarification for implemented routines

- Confirmed that no Morning Brief or Daily Wins routine has been implemented
  as of September 12, 2026.
- The implemented routine is the fixture-backed, read-only daily global AI
  news brief, alongside the Milou supervisor foundation and private report
  delivery layer.
- Morning Brief and Daily Wins remain roadmap candidates only; this scope
  clarification does not add either routine.

### September 12, 2026 — Next implementation phase: wins and meeting prep

- Proceeded with the next safe, fixture-backed implementation phase:
  **Daily Wins Recap** and **Morning Brief/Meeting Prep**.
- Daily Wins Recap will generate an evidence-based accomplishment report from
  structured activity fixtures, separating verified facts from inferred impact.
- Morning Brief/Meeting Prep will generate per-meeting briefs from calendar and
  meeting fixtures, including purpose, attendees, linked context, decisions,
  open questions, commitments, and inaccessible links.
- Both routines remain read-only: they must not contact attendees, change
  events, publish externally, or add credentials. They will reuse the routine
  registry, dated report storage, CLI, authenticated archive, and local tests.
- External integrations and deployment details remain out of scope; unresolved
  integration or hosting details should be recorded while independent local
  interfaces, fixtures, tests, and behavior continue.

### September 12, 2026 — Next article roadmap routines

- Proceeded with the next safe, fixture-backed phase from the article roadmap:
  **Commitments and Follow-Up Tracker**, **Stale Work Finder**, and
  **Dependabot PR Triage**, in that order.
- The commitments routine will detect explicit promises in structured
  message/activity fixtures and report owner, commitment, source, age,
  status/ambiguity, and a suggested follow-up without sending messages.
- Stale Work Finder will identify aging authored pull requests, assigned
  reviews, inactive assigned issues, and old drafts, grouped by urgency with
  citations.
- Dependabot PR Triage will classify dependency updates by security/urgency,
  checks, conflicts, age, and safe-review recommendation without approving or
  merging.
- All three routines will remain read-only, fixture-backed, integrated with
  the registry, canonical CLI, dated storage, authenticated archive, tests,
  contracts, README, architecture, changelog, and case-study record.

### September 14, 2026 — Launch, travel, and supervisor phase

- Continued following the article roadmap with the next fixture-backed,
  read-only routines in order: **Launch Decoder**, **Launch Radar**, and
  **Travel Logistics Tracker**.
- Launch Decoder will summarize AI/product launches from the previous 24 hours
  in plain language with direct sources, evidence, uncertainty, and no
  invented details.
- Launch Radar will report weekly upcoming launches relevant to configured
  team/user areas with timing, source, confidence, and unknowns.
- Travel Logistics Tracker will consolidate structured travel and conference
  message/calendar fixtures into a dated brief with itinerary, logistics, open
  items, source links, and missing information, without booking or changing
  anything.
- Began the supervisor orchestration/scheduling layer with a deterministic
  planner/dispatcher over registered routines, explicit read-only permissions,
  routing metadata, and visible failures. External integrations and
  credentials remain out of scope.

### September 14, 2026 — Scheduler and operational health direction

- Completed the Launch Decoder, Launch Radar, Travel Logistics Tracker, and
  deterministic planner/dispatcher phase.
- Chose durable scheduler configuration as the next foundational slice:
  daily/weekly cadence, enabled/disabled state, timezone-aware due
  calculation, deterministic run ledger/idempotency, and visible failures and
  retries.
- Operational health and scheduler status will be surfaced through the
  authenticated archive without expanding routine permissions beyond
  read-only.
- The scheduler remains local and fixture-backed for now; external schedulers,
  integrations, credentials, and deployment details are not prerequisites for
  implementing or testing the interfaces.

### September 15, 2026 — Repository-change tracking scope assessment

- Assessed whether Milou currently tracks repository changes across the user's
  own repositories and associated organizations.
- Current implementation does **not** inspect live Git repositories, GitHub
  organizations, issues, pull requests, commits, releases, or activity feeds.
  The existing routines use local fixtures only, and the scheduler does not
  collect repository events.
- Therefore Milou currently has no repository-change tracking coverage across
  personal or organization-owned repositories.
- The next implementation needed is a separately scoped, read-only
  repository-change tracker with explicit repository/organization inputs,
  event freshness and deduplication rules, citations, permission handling,
  and fixture-backed evaluation before any live integration.

### September 15, 2026 — Local GitHub Change Radar requirement

- Added the requirement to make a read-only GitHub Change Radar runnable
  locally so recent repository activity can be viewed from the authenticated
  development environment.
- The radar must use the authenticated `gh` CLI/API without exposing tokens,
  support a bounded recent window and configured personal/organization
  repository scope, and report recent changes involving the user and
  associated organizations with categories, timestamps, and direct citations.
- API and permission failures must remain visible. The implementation must
  not perform an unbounded organization scan, add credentials, or publish
  reports publicly.
- The local demo will generate a real report, serve it through the existing
  localhost-only authenticated archive, and document the exact command and
  token setup needed for viewing.

### September 15, 2026 — Allied-Steel-Buildings organization-wide radar scope

- Clarified that the primary need is visibility across **all
  Allied-Steel-Buildings repositories**, especially activity that does not
  mention or involve the user directly.
- Made the Allied-Steel-Buildings organization-wide scope the default and
  highest-priority radar scope; configured personal repositories and other
  organizations remain secondary, opt-in scopes.
- Expanded the bounded event inventory to include commits and attribution,
  branches, pull requests and review metadata, issues, releases/tags,
  workflow/check changes and failures, Dependabot/security changes, and
  repository additions or archival where APIs permit.
- Required per-repository and per-author summaries, activity counts,
  notable/high-risk changes, explicit coverage gaps and permission failures,
  pagination/rate-limit visibility, and no mention-based filtering.
- Kept the radar read-only, bounded, credential-free in the repository, and
  local-only for the demo.
- Implementation/build log: added registry metadata and canonical aliases,
  callable and CLI storage paths, three deterministic JSON fixtures, three
  contracts, authenticated archive labels, and focused unit coverage. The
  archive now avoids same-second filename collisions and stores canonical
  read-only labels.
- Validation target for this phase is full unittest discovery, `compileall`,
  canonical CLI generation/storage for each new routine, storage uniqueness,
  and `git diff --check`.

### September 15, 2026 — Browser authentication implementation/build log

- Implemented the browser-friendly decision above in `milou_news/web.py`:
  configured `GET /` now renders a minimal login form instead of an opaque
  401, while protected archive/API paths retain 401 plus the Bearer challenge.
- `POST /login` validates the submitted token with constant-time comparison,
  stores only a short-lived random server-side session identifier, and sets a
  Secure, HttpOnly, SameSite=Strict cookie. Both GET and POST `/logout` clear
  that cookie; Bearer authentication remains available for API and CLI clients.
- Missing `MILOU_REPORT_TOKEN` still returns 503 for every entry point. Tokens
  are not placed in URLs, generated HTML, or request logs, and the server
  continues to bind to localhost by default.
- Added focused tests for login failure/success, cookie authorization, logout,
  absent-token fail-closed behavior, and unchanged API 401 behavior. Updated
  README, deployment, architecture, and changelog guidance without changing
  the existing README image markup.
- Validation: full unittest discovery, Python bytecode compilation, local HTTP
  login/cookie/logout checks, and `git diff --check` are the completion gates
  for this change.

### September 12, 2026 — Article roadmap implementation result

- Added three standard-library routines and registry entries. The canonical CLI
  accepts both stable names and short aliases, and `ReportStore` metadata keeps
  routine labels visible in the authenticated archive.
- Added deterministic fixtures and contracts. Stale-work thresholds are
  explicit (7/3/14/30 days); Dependabot output separates security urgency from
  checks/conflicts and recommends review without approval or merge.
- Validation: full unittest discovery, `compileall`, canonical CLI generation
  and storage for all three fixtures, and `git diff --check`.

### September 12, 2026 — Private delivery implementation

- Added `ReportStore` dated JSON/Markdown persistence and a
  `generate_and_store` callable plus `--store` CLI path using the existing
  fixture input.
- Added a device-independent responsive HTML index/archive with an explicit
  bearer-token boundary. The token is injected or read from
  `MILOU_REPORT_TOKEN`; missing configuration returns a fail-closed error.
- Added stdlib tests for persistence, rendering, authorization, and
  generation, plus private-host deployment guidance. No deployment,
  credentials, public hosting, source-data writes, or outbound contact were
  added.
- Validation: unittest, compileall, fixture generation/storage, and diff
  checks were run for this slice.

## Why I started

My work is distributed across multiple tools, and the main cost is often
context-switching rather than any individual task. Important information can
become difficult to find: a pull request waiting for review, a promise made in
a message, a document linked from a meeting invite, or a project update that
should be recorded for later.

The problem I want to solve is not simply productivity. It is consistency:
remembering commitments, arriving prepared, recognizing progress, and protecting
time for work that requires judgment and relationships.

## Principles

- Start with one painful, repetitive problem.
- Prefer small, specific agents over one oversized agent.
- Begin with read-only reports and require approval for external actions.
- Show evidence and distinguish facts from guesses.
- Keep human judgment, recognition, and relationship-building human.
- Measure whether an automation reduces friction without creating new noise.
- Treat accessibility and executive-function support as valid design goals.

## Architectural deviation: a supervisor over the routines

The article describes a collection of scheduled automations. I want to take a
different approach: build a layer above those routines that is responsible for
managing the system as a whole.

I will treat each capability as a small, replaceable **routine** (or
sub-agent), and add a **supervisor**—a control-plane agent responsible for:

- maintaining a registry of available routines, their purpose, inputs, outputs,
  permissions, owners, and current version
- deciding which routine or sequence of routines should handle a request
- scheduling and prioritizing work
- passing context between routines without duplicating every integration
- detecting failures, stale outputs, permission problems, and changing APIs
- proposing new routines when it detects a recurring unmet need
- testing and validating routine changes before activation
- monitoring quality, cost, latency, false positives, and missed items
- keeping a human approval boundary around consequential actions
- maintaining this case study and a changelog of system behavior

The supervisor should not become an all-powerful agent. Its authority must be
explicitly bounded. By default it can inspect, summarize, plan, and recommend.
Actions such as sending messages, changing calendar events, approving or
merging code, or modifying production systems require an explicit approval
step unless separately authorized.

The supervisor will be named **Milou**, after Tintin's dog. Milou is the loyal
scout: the agent that runs ahead, notices what is unseen, and fetches the
context or information needed by the human. It supports the work without
taking over the human's judgment.

### Control-plane model

```text
User goals and standing preferences
                |
                v
        Supervisor / control plane
        - intent and priority
        - routine registry
        - planning and orchestration
        - permissions and approvals
        - health and evaluation
                |
       +--------+---------+----------------+
       v                  v                v
  GitHub routine     Meeting routine   Commitments routine
       |                  |                |
       +-------- context, evidence, results+
                |
                v
       Brief, recommendation, or approval request
```

The important distinction is that the routines do the domain work; the
supervisor manages lifecycle and coordination. This should make the system
easier to extend than a set of unrelated scheduled prompts while avoiding a
single monolithic prompt that is difficult to test or trust.

### Initial supervisor responsibilities

1. **Discover:** inspect connected work surfaces and identify recurring friction.
2. **Register:** turn an approved capability into a routine specification.
3. **Plan:** choose the smallest set of routines needed for a goal.
4. **Run:** execute routines with scoped context and least-privilege access.
5. **Evaluate:** compare results with expected output and record feedback.
6. **Maintain:** detect broken integrations, stale instructions, and degraded
   quality.
7. **Extend:** draft new routine specifications for human review rather than
   silently creating and activating capabilities.

### Routine contract

Every routine should declare:

- name, purpose, owner, and version
- supported triggers and schedule
- required inputs and permitted data sources
- output schema and evidence requirements
- side effects and required approval level
- timeout, retry, and failure behavior
- evaluation criteria and known limitations

This contract gives the supervisor something concrete to orchestrate and makes
individual routines independently replaceable.

## The initial routine portfolio

### 1. Daily GitHub triage

**Purpose:** Find work that may be falling through the cracks.

**Checks:** Assigned issues without activity, authored pull requests waiting for
review, review assignments that are aging, old draft pull requests, and failing
checks.

**Schedule:** Daily.

**Safety boundary:** Read-only. No comments, approvals, merges, or closures.

**Supervisor role:** Schedule daily, provide repository scope, validate the
report shape, and escalate only items meeting the configured urgency rules.

**Status:** Planned.

### 2. Daily wins recap

**Purpose:** Maintain an evidence-based record of accomplishments and impact.

**Checks:** Commits, pull requests, reviews, issues, discussions, and meaningful
project progress from the previous day.

**Schedule:** Daily, at the end of the workday.

**Safety boundary:** Record verified activity; do not inflate or invent impact.

**Supervisor role:** Run after the workday, append verified activity to the
case-study record, and ask for clarification when impact is inferred.

**Status:** Planned.

### 3. Weekly dependency and maintenance review

**Purpose:** Keep repository maintenance visible without spending time searching
manually.

**Checks:** Dependabot pull requests, security alerts, failed checks, stale
branches, and recurring dependency problems.

**Schedule:** Weekly.

**Safety boundary:** Report recommendations only; do not merge or approve.

**Supervisor role:** Run weekly, correlate findings with triage results, and
route high-severity security findings for explicit review.

**Status:** Planned.

### 4. Meeting preparation

**Purpose:** Arrive prepared with relevant context and known commitments.

**Checks:** Calendar events, linked documents, related messages, GitHub issues
and pull requests, prior decisions, and open questions.

**Schedule:** Before meetings, initially for selected meetings only.

**Safety boundary:** Do not contact attendees or change calendar events.

**Supervisor role:** Trigger only for selected meetings, gather relevant
context, check access, and produce a brief without contacting attendees.

**Status:** Planned.

## How I will evaluate success

For each automation, I will record:

- the problem and manual workflow it replaces
- setup time and data sources
- false positives and missed items
- time saved or context-switches avoided
- whether the output changed a decision or prevented a dropped commitment
- what I changed in the prompt after real use
- what must remain human

For the supervisor itself, I will additionally track:

- whether it selected the right routine
- unnecessary orchestration or duplicated work
- incorrect escalation and missed escalation
- routine failures it detected and recovered from
- time and cost added by the management layer
- whether a proposed extension solved a real recurring problem

The most important success measure is not the number of automations. It is
whether I can be more present, reliable, and thoughtful because less invisible
coordination is consuming my attention.

## Build log

### September 11, 2026 — Starting point

- Read the case study that inspired this project.
- Identified the first automation candidates.
- Chose a read-only, GitHub-first rollout.
- Created this living case-study draft.
- Decided to build a supervisor/control-plane layer rather than a collection of
  unconnected workflows.
- Defined routines as replaceable components with explicit contracts and
  approval boundaries.
- Named the supervisor agent **Milou**.

### September 12, 2026 — Daily Wins and Morning Brief implementation

- Added two read-only, fixture-backed routines to the registry: Daily Wins
  Recap and Morning Brief/Meeting Prep.
- Daily Wins renders supplied activity as **Verified facts**, and keeps any
  `inferred_impact` in a separate section so likely outcomes cannot be mistaken
  for observed accomplishments.
- Meeting Prep renders each meeting's purpose, attendees, linked context,
  decisions, open questions, commitments, and inaccessible links. It performs
  no contacting or calendar mutation.
- Integrated both routines with the CLI, callable report generation, dated
  `ReportStore` metadata, and the existing authenticated archive.
- Added deterministic JSON fixtures, routine contracts, registry and output
  tests. No credentials or external integrations were added.
- Validation: targeted unit tests, `compileall`, both fixture CLI paths, and
  a final diff check pass. Deployment/provider integration remains a blocker
  for hosted operation, not for local implementation.

## Lessons learned

_To be updated after the first automation is tested._

## What I would recommend to colleagues

_To be written after collecting evidence from the first rollout._

## Appendix: Prompt versions

Prompt versions will be added here as they are tested, along with the reason
for each significant change.

### September 14, 2026 — Durable scheduler foundation

- Added a local SQLite scheduler for registered routines. Daily and weekly
  schedules use each routine's IANA timezone and deterministic local day/week
  idempotency keys; disabled routines never become due.
- Added a durable run ledger with bounded retries, attempt counts, timestamps,
  and preserved failure text. Successful runs are not duplicated, and all
  scheduler configuration is enforced as read-only.
- Added `scheduler`, `status`, `run`, and `ledger` CLI commands plus fixture
  configuration, and exposed authenticated `/status` and `/health` JSON for
  operational reporting. No deployment or external integration was required;
  local SQLite and fixtures remain the supported path.

### September 15, 2026 — GitHub Change Radar implementation

- Added the `github-change-radar` routine and canonical aliases
  `github-radar`/`change-radar` to the registry and CLI. It reports recent
  authenticated-user activity and changes across explicitly configured
  repositories and organizations, grouped by category with UTC timestamps and
  direct GitHub citations.
- Chose a bounded local design: a 1–744 hour window, a 1–100 repository cap per
  configured organization, and one recent event page per endpoint. Overlapping
  user and repository events are deduplicated; unsupported or incomplete events
  are omitted and described as unknown.
- The live path calls `gh api` through a safe subprocess argument list, so the
  GitHub CLI owns credentials and no token is exposed. Fixture-backed API
  responses provide deterministic demos and tests, while API, authentication,
  timeout, and permission failures remain visible in the report.
- Added a routine contract, scope/response fixtures, ReportStore metadata
  labels, and the command path for local authenticated generation. The command
  does not start a server or publish reports.
- Validation: `python3 -m unittest discover -s tests`, `python3 -m compileall
  milou_news`, fixture CLI generation, and a final diff/status check pass.

### September 15, 2026 — Allied-Steel-Buildings monitoring clarification

- Made `Allied-Steel-Buildings` the default and highest-priority organization
  scope, with activity not involving the authenticated user explicitly shown
  before secondary personal repositories or organizations.
- Expanded the bounded event model to preserve commit author/committer,
  branch/message/link, branch lifecycle, PR lifecycle/reviewers/labels/status,
  issues, releases/tags, workflows/check failures, Dependabot/security, and
  repository lifecycle changes where the API permits.
- Added per-repository and per-author counts, notable/high-risk signals,
  pagination/rate-limit visibility, coverage gaps, and an explicit statement
  that no mention filtering is applied. Updated deterministic config and
  fixtures to demonstrate the priority path.

### September 15, 2026 — Local Change Radar demo

- Ran the real authenticated radar locally with `gh auth status` confirming
  the existing GitHub CLI session and a bounded 168-hour,
  Allied-Steel-Buildings-only configuration with a 100-repository cap.
- The organization currently exposes 48 repositories to the authenticated
  session; the generated report scanned the organization scope and recorded
  per-repository/per-author activity, citations, and coverage telemetry.
- The GitHub `/user/events` endpoint returned a visible HTTP 404 through `gh`;
  this is recorded as an API coverage gap rather than hidden or treated as
  empty activity.
- Stored the real report under a local dated archive and started the
  authenticated archive on `http://127.0.0.1:8768/`. Authenticated archive,
  `/status`, and stored report-page checks returned HTTP 200; unauthenticated
  archive access returned HTTP 401.
- The demo token is held outside the repository in a local temporary file;
  no credential or report artifact was committed.

### September 15, 2026 — Local token support

- Supported the user after they could not locate the local archive
  authentication token.
- Kept token handling secret and operator-friendly: the token file is read
  without output, never displayed or committed, and the local server can be
  restarted from a terminal with the token supplied through an environment
  variable or an explicit file read.
- Added clearer startup guidance so operators can locate or create a
  permission-restricted local token file without exposing its contents.

### September 15, 2026 — Browser login UX correction

- Observed that opening the localhost archive directly in a browser returned
  HTTP 401 because browsers do not automatically send the Bearer header used by
  API/CLI clients.
- Decided to add a browser-friendly login form at `GET /` and a `POST /login`
  flow that validates the token without exposing it, then uses a short-lived,
  HttpOnly, SameSite cookie for browser navigation.
- Bearer authorization remains supported for API/CLI requests; logout,
  absent-token fail-closed behavior, localhost binding, and no-token-in-URL or
  HTML rules remain mandatory.

### September 15, 2026 — Local report folder shortcut

- Supported the user after they asked to open the locally generated report
  folder.
- Documented `/tmp/milou-live-reports` as the current demo archive directory
  and added an operator shortcut using `open /tmp/milou-live-reports`.
- Kept the path configurable and separate from token handling; no credentials
  or user files are exposed or changed.

### September 15, 2026 — Report signal-to-noise refinement

- Feedback identified that repeated no-activity headings reduce report
  readability and obscure useful signals.
- Decided to suppress empty activity sections and empty routine categories.
- Reports with no substantive findings will use a concise **No activity to
  report** state containing the window/scope and any coverage warnings,
  without hiding API or permission failures.
- Added a consistent KPI block near the top of every report for generated time,
  window, scope/source count where applicable, total findings/items,
  high-priority count, and warnings/failures. Change Radar additionally
  reports repositories scanned, changes by type, contributors/authors, and
  high-risk count.

Implementation/build log:

- Updated fixture routine renderers and the news pipeline to calculate KPI
  totals and omit empty facts, impact, urgency, launch, itinerary, and
  logistics categories. Empty inputs now render one concise no-activity state
  with explicit fixture coverage warnings.
- Updated Change Radar to omit empty scope sections, preserve its separate
  coverage/API/permission section, and expose expanded KPI telemetry.
- Added empty-report and populated KPI assertions; existing populated reports
  retain citations and safety boundaries.
- Validation: `python3 -m unittest discover -s tests` and
  `python3 -m compileall milou_news` pass. Safe live Allied-Steel-Buildings
  regeneration was run with the authenticated `gh` session using the bounded
  fixture configuration; the generated Markdown/JSON archive was inspected
  and removed after the check.

### September 21, 2026 — Project status review and repository hygiene

- Reviewed project state on request: the working tree matched `main`, all 28
  tests passed via `python3 -m unittest discover -s tests`, and no pull
  requests or issues were open. The last substantive work was the
  September 15 report signal-to-noise refinement.
- Observed that running the test suite left untracked `__pycache__` bytecode in
  the working tree because the repository had no `.gitignore`.
- Decided to add one covering Python bytecode caches, the local `reports/`
  archive directory, and SQLite scheduler database files. These are
  operator-managed local artifacts and must never be committed, which also
  keeps generated reports and scheduler state out of version control by
  default.
- Lesson: validation commands should not be able to dirty the repository;
  ignore rules belong alongside the runtime they support.
- Validation: `python3 -m unittest discover -s tests` passes and
  `git status --untracked-files=all` is clean after the change.

### September 21, 2026 — Reports keep their structure

- Reviewed how routine output is displayed and found the problem was not the
  writing but the last step. A Change Radar row already carries fourteen typed
  fields — timestamp, category, repository, summary, url, author, branch,
  labels, reviewers, committers, status, risk, scope, id — and the renderer
  concatenated all of them into one prose sentence. The structure existed right
  up until render, then was discarded.
- The sharpest instance: `risk` was already computed as `high` / `notable` /
  empty, never affected ordering, and reappeared only as one summary line near
  the bottom. Rows were sorted by timestamp alone, so a failed CI check and a
  whitespace commit ranked only by which happened later.
- The daily brief had the opposite problem. Its ranking, its region-diversity
  rule, and its de-duplication are the product, and all three were footnotes: a
  `global_discussion=0.70, significance=0.80, ...` debug string, a trailing
  diversity sentence, and `Not included: 1 duplicate(s).`
- Decided on an intermediate rather than a second renderer: generators build a
  structured `Report`, and each format decides how much of it to keep. Markdown
  keeps the text and is unchanged; HTML keeps the ordering, tiers, and signals
  too. Collection is shared through a `prepare` step so producing both formats
  never collects from the API or the sources twice.
- Four display rules now hold: every field gets a column rather than a clause;
  consequence outranks recency; boilerplate recedes while failures are promoted
  to a banner above the findings; and colour is reserved — neutral glass carries
  structure, reserved tones carry state.
- Colour was validated rather than chosen by eye, and three candidate palettes
  failed: several system hues fall below 3:1 on a light surface, green and pink
  collide under deuteranopia at dE 4.3, and blue and indigo fail even for normal
  vision at 9.8. The shipped categorical set passes across all pairs at dE 8.7
  worst case under simulated colour-vision deficiency and 21.2 for normal
  vision. Six slots did not fit the hue space, so the set was cut to four and
  the fifth meter segment carries texture instead of hue — which is also truer,
  since the non-US bonus is added on top rather than weighted in. Magnitude
  breakdowns use one hue stepped light to dark with labels chosen per step to
  clear 4.5:1.
- Two findings came out of building it. Position in the brief is not rank:
  `select_diverse` promotes a lower-scoring item so another region appears,
  which is correct and was invisible; promoted and demoted items are now marked
  with the score that explains them. And de-duplication keeps the first match in
  source order rather than the best-evidenced one, so the EU evaluation guidance
  kept the SCMP account and dropped Euractiv's, which scored higher on both
  evidence (0.95 vs 0.70) and significance (0.90 vs 0.70). The routine now
  reports that trade rather than a count. The ordering itself is left unchanged
  and is recorded here as the next correctness question for this routine.
- Fixed a related data defect: a commit with no committer block stringified the
  missing value into a literal `committer: None`, which both formats printed as
  though it were a contributor name.
- Lesson: a rendering problem is worth reading as a data-flow problem first.
  Every display fix here was recovering something the routine already knew.
- Validation: `python3 -m unittest discover -s tests` passes with 55 tests
  (27 added), `python3 -m compileall milou_news` passes, and both routines were
  generated and rendered from their committed fixtures and inspected.
