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

## Lessons learned

_To be updated after the first automation is tested._

## What I would recommend to colleagues

_To be written after collecting evidence from the first rollout._

## Appendix: Prompt versions

Prompt versions will be added here as they are tested, along with the reason
for each significant change.
