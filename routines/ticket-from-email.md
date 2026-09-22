# Routine contract: `ticket-from-email`

- **Name:** `ticket-from-email` (an action, not a scheduled routine)
- **Version:** 0.1.0
- **Access:** **write, behind explicit approval** — the first write in the project
- **Input kind:** one mailbox message + operator configuration
- **Purpose:** Turn an email into a Zoho Projects ticket scheduled for the right
  sprint, and record it in the manually maintained sprint tracker.

## Why this is not a routine

Every other capability here is read-only by construction. Creating a ticket and
editing a shared document are consequential actions, and the architecture
reserves those for an explicit approval step. So this is modelled as a
**proposed plan**, not an operation:

1. **Draft.** Milou reads one email and produces an `ActionPlan` describing
   exactly what would change, with every field resolved. Nothing is contacted.
2. **Title.** Milou will *not* choose the title. It offers an extremely brief
   suggestion derived from the subject and waits.
3. **Approve.** The plan is approved by a named person. Approval is bound to the
   plan's exact contents — editing it afterwards clears the approval, so a plan
   cannot be approved and then quietly changed.
4. **Execute.** Only then are the writes attempted, in order.

## Sprint scheduling

Sprints start every **Wednesday**, and developers pick up new work at the start
of a sprint. A ticket therefore belongs to the **next Wednesday strictly after
the day it is created**:

| Created | Sprint | Why |
|---|---|---|
| Monday | that Wednesday | not yet started |
| Tuesday | the next morning | picked up tomorrow |
| Wednesday | the following week | the sprint began without it |
| Thursday–Sunday | the following week | same |

The sprint tag is `2 OCT SPRINT` — day without a leading zero, three-letter
month, uppercase. Month names are a fixed table, not `strftime("%b")`, which is
locale-dependent and would silently produce a different tag on another machine.

## Ticket fields

| Field | Value |
|---|---|
| Title | **supplied by the user** |
| Status | `Ready for Development` (configurable) |
| Tag | the sprint tag, e.g. `2 OCT SPRINT` |
| Expected release date | the sprint start date, matching the tag |
| Description | the email's scope and context, plus From / Received / Subject and a link back to the source message |

## Sprint tracker document

After the ticket exists, one line is added under that sprint's heading:

```
1993 - Issue Bldg 4 stamped drawings
```

The **last four digits** of the ticket number, ` - `, then the title. The line is
built at execution time, because the ticket number does not exist until the task
has actually been created.

If ticket creation fails, **no document line is written**. A tracker entry
pointing at a ticket that does not exist is worse than no entry.

## Safety boundary

- Nothing is created without an explicit, named approval.
- Approval is bound to the plan's contents; any edit clears it.
- The title is never invented — only suggested.
- Write credentials are **separate** from the read tokens:
  `MILOU_ZOHO_WRITE_TOKEN`, never `MILOU_ZOHO_TOKEN`. A read-only run cannot
  write even if misconfigured.
- An absent write token, an unconfigured portal or project, or a missing title
  each fail closed.
- Execution stops at the first failure rather than half-applying a plan.

## Not implemented

- **The live document adapter.** Appending to a shared Microsoft document needs
  to know whether it is a Word file, a OneNote page, or a Loop component; each
  requires a different Graph call, and guessing risks corrupting a manually
  maintained tracker. A dry-run writer reports the exact line and heading it
  would add.
- Zoho task creation is written against the documented REST shape but has not
  been run against a live portal.
