# Routine contract: `zoho-projects-radar`

- **Name:** `zoho-projects-radar`
- **Aliases:** `zoho`, `projects`
- **Version:** 0.1.0
- **Access:** read-only
- **Input kind:** authenticated Zoho Projects REST API (or deterministic fixture)
- **Schedule:** daily
- **Purpose:** Watch the ticket system directly, so its notification email stops
  being the way work is discovered.

## Why this exists

Most work arrives as Zoho Projects tickets rather than GitHub changes, and Zoho
emails a notification for nearly everything it does. Reading the mail is a poor
substitute for reading the system: the mail is unordered, unbounded, and mixed
in with human correspondence. This routine reads the projects directly and then
**publishes what it reported**, so the corresponding notification mail can be
suppressed by the inbox monitor rather than shown a second time.

## What earns a line

| Tier | Meaning |
|---|---|
| **Comments** | Any comment, on any tracked item. |
| **Assigned to you** | Ownership or assignment changed to the user. |
| **Status changes on your items** | An item involving the user moved without them. |
| **Other activity on your items** | Everything else touching the user's items; collapsed. |

**Comments lead deliberately.** A comment usually needs a response whether or
not it is phrased as a direct question, so a comment is never demoted for
lacking a question mark — the request-detection used for email does not apply
here.

## What is excluded, and counted

- The user's own activity, unless `include_own_activity` is set.
- Activity outside the `window_hours` window.
- Non-comment activity on items that do not involve the user.
- Projects beyond `max_projects`.

Exclusions are counted and reported by reason. They are never listed.

## Output rules

Output is capped at `max_items`; overflow is reported as a count. A quiet window
produces a short report. These are the same rules as the inbox monitor, for the
same reason: a report whose length tracks the ticket list is the ticket list.

## De-duplication contract

The radar publishes a `Coverage` record containing the item identifiers and
titles it actually collected, plus the notification sender domains it makes
redundant. The inbox monitor suppresses a message only when **both** hold:

1. the sender is one of this routine's notification domains, and
2. the message quotes an identifier or title the radar actually reported.

A notification from a covered domain that cannot be matched is **not** dropped
silently. It is counted separately and raised as a coverage gap, because an
unmatched notification usually means the radar is missing a project, a
permission, or a window. Suppressing the whole channel by sender would hide
exactly that case.

## Configuration

```json
{
  "portal": "yourportal",
  "me": "you@example.test",
  "projects": [],
  "window_hours": 72,
  "max_items": 10,
  "max_projects": 20,
  "include_own_activity": false,
  "endpoints": {
    "projects": "/restapi/portal/{portal}/projects/",
    "activities": "/restapi/portal/{portal}/projects/{project}/activities/"
  }
}
```

`projects` empty means every accessible project, up to `max_projects`.

**`endpoints` is deliberately configuration.** Zoho's REST surface differs
across portal API versions, and the defaults above have **not been confirmed
against a live portal**. If a path is wrong for your portal, correct it here
rather than in code; the classifier does not depend on the path shape.

## Safety boundary

- **Read-only.** Only HTTP `GET`. The routine never comments, closes,
  reassigns, logs time, or changes a ticket in any way.
- **Least privilege.** A read scope is sufficient; no write scope should be
  granted.
- **Credentials stay outside the repository.** The OAuth token is read from
  `MILOU_ZOHO_TOKEN` and is never logged, stored, echoed into a report, or
  written to the archive. An absent token fails closed.
- Access failures and coverage gaps are reported visibly rather than rendering
  as an empty portal.

## Not implemented

- No write scope, no time logging, no ticket creation.
- Not yet verified against a live Zoho portal; the adapter is written against
  the documented REST shape and exercised only through fixtures.
