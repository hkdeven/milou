# Milou architecture

## Purpose

Milou is a bounded supervisor/control plane over a set of small, replaceable
automation routines. It is not a monolithic agent and it is not intended to
automate leadership or replace human judgment. Its job is to coordinate useful
scaffolding: finding context, surfacing commitments, summarizing activity,
preparing briefs, and requesting approval for consequential actions.

The routines do the domain work. Milou manages routine lifecycle and
coordination.

## Control-plane model

```text
User goal and standing preferences
                 |
                 v
        Milou supervisor/control plane
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

## Responsibilities

Milou owns the following control-plane responsibilities:

1. **Discover** — identify recurring friction across connected work surfaces.
2. **Register** — maintain each routine's purpose, version, owner, inputs,
   outputs, permissions, and status.
3. **Plan** — select the smallest set of routines needed for a goal.
4. **Run** — invoke routines with scoped context and least-privilege access.
5. **Evaluate** — compare results with expected output and record feedback.
6. **Maintain** — detect broken integrations, stale instructions, and degraded
   quality.
7. **Extend** — propose routine specifications for human review instead of
   silently creating or activating capabilities.

Milou must not silently expand a routine's scope, permissions, or side
effects. A proposed routine or routine change remains inactive until it has
been reviewed, tested, and explicitly enabled.

## Routine boundary

Each routine is an independently replaceable component with an explicit
contract. At minimum, the contract declares:

- supported triggers and schedule
- required inputs and permitted data sources
- output shape and evidence requirements
- side effects and required approval level
- timeout, retry, and failure behavior
- evaluation criteria and known limitations

This boundary keeps orchestration logic out of domain prompts and makes
individual routines testable without requiring the entire supervisor.

## Safety and approval model

The default mode is read-only. Inspection, summarization, planning, and
recommendation may run without an approval step when their declared inputs and
outputs are within scope.

Consequential actions—such as sending messages, changing calendar events,
approving or merging code, or modifying production systems—require an
explicit human approval step unless a later, separately reviewed policy grants
that authority. Approval must be visible in the routine result and recorded
alongside the action request.

Failures, missing permissions, stale data, and uncertain inferences must be
reported explicitly. A routine must not convert an error into a successful
looking result or guess when required evidence is unavailable.

## Initial rollout

The first rollout is GitHub-first and read-only. Planned routines include
daily GitHub triage, a daily wins recap, a weekly dependency and maintenance
review, meeting preparation, and a proposed daily global AI news brief.
External integrations and execution infrastructure are deliberately out of
scope for this initial structure. The news brief's source set and contract
live in [`docs/news-sources.md`](news-sources.md) and
[`routines/daily-global-ai-news-brief.md`](../routines/daily-global-ai-news-brief.md).

The news brief is a useful example of the boundary: Milou may eventually
coordinate read-only collection, ranking, deduplication, and citation, but it
must not publish, contact sources, or change subscriptions without a separate
approved capability.

As of September 12, 2026, the runtime also includes fixture-backed Daily Wins
and Morning Brief/Meeting Prep routines. They use only local structured input:
Daily Wins labels supplied activity as verified facts and keeps impact as
explicit inference, while Meeting Prep preserves per-meeting context and
unknowns. Neither routine contacts people or changes calendar data.
It also includes commitment detection, stale-work grouping, and Dependabot
triage. These routines cite fixture evidence, expose ambiguity and thresholds,
and only recommend human follow-up; they never send, approve, merge, or edit.

As of September 14, 2026, Launch Decoder reads only last-24-hour launch
fixtures and separates plain-language summaries, direct sources, evidence, and
uncertainty. Launch Radar renders a weekly view for explicitly configured
areas with timing, source, confidence, and unknowns. Travel Logistics Tracker
combines structured calendar and message fixtures into a dated itinerary brief.
All three remain read-only and preserve missing information rather than filling
gaps.

The smallest supervisor layer is deterministic: `SupervisorPlanner` validates
registered names and read-only permissions, while `SupervisorDispatcher`
routes to a known handler and returns an explicit error instead of hiding a
failure. It does not infer new routines, call external systems, or grant
permissions.

Success will be evaluated using evidence such as false positives, missed
items, time saved, context-switches avoided, useful decisions enabled, routine
failures detected, unnecessary orchestration, and the cost of the management
layer itself.

## Report rendering

Routines do not render. They build a structured `Report` — KPIs, distribution
bars, and rows grouped into tiers — and each renderer decides how much of that
structure to keep:

```text
routine parse -> structured Report -> Markdown renderer (stored record)
                                   -> HTML renderer (reading surface)
```

The intermediate exists because the previous renderers discarded it. Every
routine already classified what it found — a change's risk, a stale item's
urgency, a dependency update's severity — and then flattened each record into
one prose line ordered only by timestamp. Keeping the classification lets the
HTML renderer order rows by consequence before recency, give each field its own
column, promote coverage and permission failures above the findings, and let
boilerplate recede.

Collection is shared: a routine exposes a `prepare` step so producing both
formats never fetches or collects twice. Colour in the HTML renderer is
reserved — neutral surfaces carry structure, and the four reserved tones
(critical, notable, coverage, positive) carry state and always pair an icon and
a word so hue is never the only carrier.

## Hosted private delivery pipeline

The delivery slice is deliberately read-only:

```text
fixture/source input -> scheduled generation callable/CLI
                    -> dated Markdown + JSON archive (structure preserved)
                    -> private host -> browser-session/API-bearer web index/archive
```

`ReportStore` writes reports under a year/month/day archive and the web layer
only reads those files. The HTTP boundary requires the configured
`MILOU_REPORT_TOKEN`; an absent token fails closed. Browser users authenticate
at `/login` and receive a short-lived server-side Secure, HttpOnly,
SameSite=Strict cookie; API and CLI clients retain Bearer authentication.
`/logout` clears the session. A private host and operator-managed TLS/reverse
proxy are required. Public hosting and GitHub Pages are explicitly excluded.
The application never publishes reports,
contacts sources, or changes source data.

## Blockers and continuation

Milou records blockers and continues independent related work rather than
stopping the project. A true pause is reserved for a safety issue, a missing
required user decision, or a correctness dependency that makes further work
unsafe or misleading. Deployment-provider selection and credentials do not
block local report persistence, UI, tests, or authentication-boundary work.

## The write boundary

Creating a Zoho ticket and editing a shared tracker are the first consequential
actions in this project, and they are deliberately not implemented as routine
side effects. A routine produces an `ActionPlan`: a full description of what
would change, with every field resolved and every missing input named. Nothing
is contacted while drafting.

Three properties make the boundary real rather than decorative:

- **Approval is explicit and named.** `execute` refuses an unapproved plan.
- **Approval is bound to contents.** Supplying or changing an input clears the
  approval, so a plan cannot be approved and then quietly edited before it runs.
- **Write credentials are separate.** The writers read
  `MILOU_ZOHO_WRITE_TOKEN`, never the read token, so a misconfigured read-only
  run cannot mutate anything.

Execution stops at the first failure rather than half-applying a plan: a tracker
line naming a ticket that was never created is worse than no line at all. The
user supplies the ticket title; Milou only ever suggests one, because a title is
read by people who never saw the originating email.

## Cross-routine coverage

When one routine watches a system directly and that system also emails a
notification, the user is told the same thing twice. Silencing the notification
channel by sender would fix the duplication and introduce a worse failure: it
would also hide alerts the direct routine never saw.

So de-duplication is evidence-based. A routine publishes a `Coverage` record —
the record identifiers and titles it *actually collected*, plus the notification
sender domains it makes redundant — and a consuming routine suppresses a message
only when both the sender and the content match. The suppression is counted
under its own reason, naming the routine responsible, so it is traceable rather
than silent.

Anything from a covered sender that cannot be matched is never dropped quietly.
It is counted separately and raised as a coverage gap, because an unmatched
notification usually means the direct routine is missing a project, a
permission, or a window. The duplicate-suppression mechanism therefore doubles
as a detector for the direct routine's own blind spots.

Coverage is checked before the generic automated-sender rule, since a
notification would otherwise disappear as "automated" whether or not the
covering routine saw the event.

## Zoho Projects radar

Most work arrives as tickets rather than GitHub changes. `zoho-projects-radar`
reads the portal directly and applies the same output discipline as the inbox
monitor — capped output, counted exclusions, a short report when quiet.

Its one deliberate departure: **comments are the top tier unconditionally**. A
comment usually needs a response whether or not it is phrased as a question, so
the request-detection used for email is not applied to it. Zoho's REST surface
differs across portal API versions, so endpoint paths are configuration with
documented defaults rather than constants.

## Outlook inbox monitor

This routine inverts the usual summarisation goal. A report covering the whole
inbox is the inbox again — same volume, less scannable, and untrustworthy
because the reader cannot see what was dropped. Its value is therefore in what
it refuses to show, and the architecture enforces that:

- **Output is bounded, not proportional.** A hard item cap means a busier
  mailbox produces the same report length; overflow is a count, not more lines.
- **Exclusions are counted, never listed.** The report states how many messages
  were scanned and why each excluded group was dropped, so the reader can
  calibrate trust without the excluded mail reappearing as content.
- **Only four things earn a line**: a sender who states they are blocked, an
  unanswered request addressed directly to the user, a promise in the user's own
  sent mail, and sent mail that asked something and has had no reply.
- **The user's own obligations and other people's are kept apart.** A promise
  means the user owes the recipient, so it is never also chased as unanswered
  mail; a thread the user closed with an acknowledgement is not chased at all.
- **Thresholds are configuration.** Follow-up delay, item cap, lookback window
  and muted senders are all operator-set, and follow-up delay counts business
  days so Friday mail is not chased on Sunday.

Access is read-only Microsoft Graph `GET` with `Mail.Read`. The routine cannot
send, reply, flag, move, archive or mark read, so it cannot change mailbox
state. The token is read from the environment, never logged, stored or written
into a report, and an absent token fails closed. Message bodies are not stored —
only the short preview needed to explain why an item surfaced.

## Durable scheduling and health

The local `Scheduler` persists configuration and an idempotent run ledger in
SQLite. Daily and weekly due keys are calculated in each routine's IANA timezone
(and only after its configured local time), while disabled routines are ignored.
Every attempt records status, attempt count, timestamps, and any error; retries
are bounded and visible. Scheduler configuration is read-only by construction.
The authenticated archive exposes `/status` and `/health` when given a scheduler
instance, so operational failures are not hidden behind report pages.

Given a report store, a scheduled run persists what it produced and records the
stored path in the ledger, so a run can be traced to its output rather than only
to the fact that it happened. Failing to store a report is recorded as a run
failure: a run whose report nobody can find has not succeeded.

## GitHub Change Radar

`github-change-radar` defaults to highest-priority, organization-wide
monitoring of `Allied-Steel-Buildings`, including activity not involving the
user. Personal repositories and other organizations are secondary explicit
configuration. It renders bounded commits (author, committer, branch, message,
link), branch lifecycle, PR lifecycle/reviewers/labels/status, issues,
releases/tags, workflow/check failures, Dependabot/security, and repository
lifecycle events where permitted. Reports include per-repository and
per-author counts, notable/high-risk changes, direct citations, pagination and
rate-limit visibility, and API/permission/coverage gaps. No mention filtering
is applied. Nothing is written to GitHub, and events outside scope/window
remain unknown.

All report families start with a consistent KPI block covering generation time,
bounded window, scope/source count, total findings/items, high-priority items,
and warnings/failures. Empty activity sections and routine categories are
omitted. When no substantive findings exist, the report uses a concise
“No activity to report” state. Coverage, API, and permission failures remain
separate and visible; Change Radar additionally reports repositories scanned,
changes by type, contributors/authors, and high-risk count.
