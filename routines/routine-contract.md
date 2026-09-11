# Routine contract and template

Every routine must have a contract before Milou can register or activate it.
Copy the template below into a new routine specification and replace each
placeholder. Keep the routine small enough to test and replace independently.

## Contract

### Identity

- **Name:** `<stable routine name>`
- **Purpose:** `<one-sentence problem this routine solves>`
- **Owner:** `<person or team>`
- **Version:** `0.1.0`
- **Status:** `proposed | tested | enabled | disabled | retired`

### Trigger and scope

- **Trigger:** `<manual request, event, or schedule>`
- **Schedule:** `<when it runs, or "on demand">`
- **In scope:** `<specific work the routine performs>`
- **Out of scope:** `<work it must not perform>`

### Inputs and data sources

List every required input and the source that provides it.

| Input | Source | Required | Retention or handling |
| --- | --- | --- | --- |
| `<input>` | `<source>` | `yes/no` | `<constraint>` |

The routine may use only the listed sources and must report missing or
inaccessible inputs instead of guessing.

### Output

- **Output format:** `<schema, document, or result type>`
- **Required fields:** `<fields and meaning>`
- **Evidence:** `<links, identifiers, timestamps, or other supporting facts>`
- **Uncertainty:** `<how inferred or missing information is labeled>`

### Permissions and side effects

- **Access level:** `read-only | proposed-write | approved-write`
- **Side effects:** `<none, or enumerate each possible side effect>`
- **Approval required:** `none | per-run | per-action`
- **Approval owner:** `<who can approve, if applicable>`

No side effect may be introduced without updating this contract and reviewing
the approval boundary.

### Reliability behavior

- **Timeout:** `<duration and what happens when it expires>`
- **Retries:** `<count, backoff, and retryable failures>`
- **Partial results:** `<whether they are allowed and how they are labeled>`
- **Failure reporting:** `<where the error is surfaced>`
- **Idempotency:** `<how repeated execution behaves>`

Failures and permission errors must remain visible to Milou and the user.

### Evaluation

- **Expected behavior:** `<observable success criteria>`
- **Metrics:** `<false positives, misses, latency, cost, usefulness, etc.>`
- **Test fixtures:** `<representative inputs and edge cases>`
- **Known limitations:** `<conditions where the output is incomplete>`
- **Review cadence:** `<when the contract and results are reviewed>`

### Lifecycle

- **Created:** `<date>`
- **Last reviewed:** `<date>`
- **Change history:** `<links or concise list of contract changes>`
- **Retirement condition:** `<when this routine should be disabled or removed>`

## Activation checklist

Before enabling a routine, confirm:

- [ ] The purpose and boundaries are specific.
- [ ] Every data source and permission is listed.
- [ ] The output shape and evidence requirements are testable.
- [ ] Side effects have an explicit approval policy.
- [ ] Timeout, retry, and failure behavior are defined.
- [ ] Representative success, failure, and edge cases are evaluated.
- [ ] The case study records the decision and validation result.
