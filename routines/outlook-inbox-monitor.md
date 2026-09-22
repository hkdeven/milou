# Routine contract: `outlook-inbox-monitor`

- **Name:** `outlook-inbox-monitor`
- **Aliases:** `inbox`, `outlook`
- **Version:** 0.1.0
- **Access:** read-only
- **Input kind:** authenticated Microsoft Graph (or deterministic fixture)
- **Schedule:** daily
- **Purpose:** Replace opening the inbox — not summarise it.

## The failure this routine exists to avoid

A report that covers the whole inbox is the inbox again: the same volume, less
scannable, and now untrustworthy because the reader cannot tell what was left
out. Reading the original mail is strictly better than reading that. **The value
of this routine is what it refuses to show.**

Every rule below follows from that.

## Output rules

1. **Bounded, not proportional.** At most `max_items` actionable lines (default
   8). A busier inbox does not produce a longer report; the overflow is reported
   as a count. If the report length tracks inbox volume, the routine has failed.
2. **Silence is a success state.** A quiet window produces a short report saying
   nothing needs the user. It is never padded to look useful.
3. **Every line is an action, not a topic.** "A. Rivera is waiting on your
   approval of the Q3 pricing sheet" — never "Re: Q3 pricing — pricing
   discussion".
4. **Never claim completeness.** The report states how many messages were
   scanned and how many were excluded, broken down by reason. The excluded
   messages are counted, never itemised.
5. **Every line shows why it surfaced** (addressed directly to the user, request
   language detected, no reply sent). A wrong call must be diagnosable.
6. **Safe to ignore.** The routine reads current mailbox state, not an event
   stream, so skipping days never loses an item and never double-reports one.
7. **Recall over precision, but tiered.** Missing a real request costs far more
   than one extra line, so borderline items drop a tier rather than disappear.

## What earns a line

| Tier | Meaning |
|---|---|
| **Blocked on you** | The sender states they cannot proceed without a reply, approval, or decision. |
| **Waiting on your reply** | Addressed directly to the user, contains a request, and the user has not replied in that conversation. |
| **You promised** | Explicit promise language in the user's own sent mail. |
| **No reply yet** | The user sent something and no reply has been recorded after `follow_up_days` business days. |

## What is excluded, and counted

- Messages where the user is only on CC.
- Automated senders (`noreply@`, `notifications@`, mailer daemons, bounces).
- Microsoft Graph Focused Inbox `other` classification, unless `include_other`.
- Conversations the user has already replied to.
- Senders listed in `mute_senders`.
- Messages outside `lookback_days`.
- Messages with no detectable request.

## Configuration

```json
{
  "follow_up_days": 2,
  "max_items": 8,
  "lookback_days": 14,
  "max_messages": 200,
  "include_other": false,
  "mute_senders": ["newsletter@example.test"]
}
```

`follow_up_days` counts **business days**, so mail sent on Friday is not chased
on Sunday. Every value is operator-configurable; none is hard-coded.

## Safety boundary

- **Read-only.** Only HTTP `GET` against Microsoft Graph. The routine never
  sends, replies, forwards, flags, archives, deletes, moves, or marks anything
  read. It cannot change mailbox state.
- **Least privilege.** `Mail.Read` is sufficient; `Mail.ReadWrite` must not be
  granted.
- **Credentials stay outside the repository.** The access token is read from
  `MILOU_OUTLOOK_TOKEN` and is never logged, stored, echoed into a report, or
  written to the archive. An absent token fails closed.
- **Message bodies are not stored.** Only a bounded preview needed to explain
  why an item surfaced.
- Failures, permission errors, and truncated pages are reported visibly rather
  than being rendered as an empty inbox.

## Not implemented

- No write scope, no send, no calendar access.
- No snooze or acknowledgement state yet: the routine is stateless across runs,
  so an item stays visible until the mailbox itself changes.
