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

Success will be evaluated using evidence such as false positives, missed
items, time saved, context-switches avoided, useful decisions enabled, routine
failures detected, unnecessary orchestration, and the cost of the management
layer itself.

## Hosted private delivery pipeline

The delivery slice is deliberately read-only:

```text
fixture/source input -> scheduled generation callable/CLI
                    -> dated Markdown + JSON archive
                    -> private host -> bearer-authenticated web index/archive
```

`ReportStore` writes reports under a year/month/day archive and the web layer
only reads those files. The HTTP boundary requires the configured
`MILOU_REPORT_TOKEN`; an absent token fails closed. A private host and
operator-managed TLS/reverse proxy are required. Public hosting and GitHub
Pages are explicitly excluded. The application never publishes reports,
contacts sources, or changes source data.

## Blockers and continuation

Milou records blockers and continues independent related work rather than
stopping the project. A true pause is reserved for a safety issue, a missing
required user decision, or a correctness dependency that makes further work
unsafe or misleading. Deployment-provider selection and credentials do not
block local report persistence, UI, tests, or authentication-boundary work.
