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
| Owner | **unassigned** by default — see below |
| Tag | the sprint tag, e.g. `2 OCT SPRINT` |
| Expected release date | the sprint start date, matching the tag |
| Description | composed to the fixed shape below |

### Owner

The default is **unassigned**, and deliberately so. At `Ready for Development`
the sprint is the queue: whoever picks the ticket up owns it. Pre-assigning
makes someone accountable for work they have not seen, and it is the one field
where a wrong default causes an argument rather than an edit. A `default_owner`
can be configured, and the field is editable either way.

## How the description is composed

The description is **composed, not pasted**, to the same shape on every ticket,
so nobody has to read one end to end to find a single fact:

```
Type: Bug report
Requested by: <the person who made the request>
Reported by: <the person who hit it — bugs only>
Reported on: <when it was reported — bugs only>
Project / record: <where it was encountered, when stated>

Context
-------
<short, but every load-bearing sentence kept>

Supporting documents
--------------------
- <every link shared in the thread, in full>

--- Raised from email ---
From / Received / Subject / Source
```

- **Requested by** defaults to the sender and is required.
- **Reported by** and **Reported on** appear on bug reports only, and are
  **required**. The person emailing about a bug is usually not the person who
  hit it, and the report date is almost never stated, so both are extracted
  heuristically where possible and **marked as guesses**. When nothing is found
  the field stays empty and the plan stays incomplete. That is the point: a
  description reading `Reported by: (unknown)` is a question nobody goes back
  and answers.
- **Context** drops greetings, sign-offs and quoted reply chains, then keeps
  sentences in order until a character budget is spent — except that a sentence
  carrying a constraint ("must", "before Friday", "steps to reproduce") is kept
  regardless, because dropping it makes the summary wrong rather than short.
- Inline URLs are replaced with `[doc 1]` references into the document list. A
  120-character SharePoint URL mid-sentence makes the sentence unreadable, and
  the full URL is listed below it anyway.
- Bug or request is **detected** from the wording and can be flipped; a tie goes
  to bug, because a bug needs two extra facts.

Correcting any of these fields **re-composes the description**, so the prose and
the fields beside it cannot disagree.

### Reading the body

The inbox monitor stores only a bounded preview and never a body. This action
reads the body of **exactly the one message it is drafting from**, uses it to
compose a description the user then reviews, and never writes it to the archive.
A description built from 240 characters would be a truncated one.

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

## The acknowledgement draft

Once the ticket exists, a third action leaves a reply-all **in Outlook's Drafts**
telling the thread:

- the ticket number, and that it is being looked at;
- that they can follow the development, the release and the change log against
  that number rather than waiting for an update;
- the expected release date, stated as **the latest** it should take.

That last qualifier is load-bearing. A date given without it reads as a promise
for that exact day and gets chased on it.

The number does not exist at draft time, so the body carries a `{ticket_id}`
placeholder and is resolved after the task is created — the same rule as the
tracker line. Execution is ordered by consequence and stops at the first
failure, so a failed ticket or a failed tracker line leaves no draft. Telling
six people to follow a ticket that was never recorded is worse than silence.

**It is a draft, never a send.** The message sits in Outlook until the user
presses Send. That asymmetry is deliberate: a draft is reversible and a sent
mail is not, and this one would go out seconds after a ticket number was
allocated. Set `"acknowledge": false` to switch it off.

Creating a draft needs `Mail.ReadWrite`, which is wider than `Mail.Send` and
worth stating plainly: the same grant can modify and delete mail. An operator
who does not want that grant should turn the acknowledgement off and keep
`Mail.Send` alone for the context reply.

## Configuration

```json
{
  "portal": "yourportal",
  "project": "5001",
  "project_name": "Bldg 4 Fabrication",
  "ready_status": "Ready for Development",
  "default_owner": "",
  "document": "Sprint Ticket Tracker",
  "document_heading": "{sprint}",
  "signature": "Your Name",
  "acknowledge": true
}
```

## Safety boundary

- Nothing is created without an explicit, named approval.
- Approval is bound to the plan's contents; any edit clears it.
- The title is never invented — only suggested.
- The reporter and the report date are never invented either. They are extracted
  where the email states them, marked as guesses, and otherwise left empty.
- Write credentials are **separate** from the read tokens:
  `MILOU_ZOHO_WRITE_TOKEN`, never `MILOU_ZOHO_TOKEN`; `MILOU_OUTLOOK_WRITE_TOKEN`,
  never `MILOU_OUTLOOK_TOKEN`. A read-only run cannot write even if misconfigured.
- An absent write token, an unconfigured portal or project, a missing title, or a
  bug with no reporter each fail closed.
- Execution stops at the first failure rather than half-applying a plan.
- The acknowledgement is drafted, never sent.

## Not implemented

- **The live document adapter.** Appending to a shared Microsoft document needs
  to know whether it is a Word file, a OneNote page, or a Loop component; each
  requires a different Graph call, and guessing risks corrupting a manually
  maintained tracker. A dry-run writer reports the exact line and heading it
  would add.
- Zoho task creation is written against the documented REST shape but has not
  been run against a live portal.
