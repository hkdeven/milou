# Contract: the console

- **Name:** `console` (an application, not a routine)
- **Version:** 0.1.0
- **Access:** read-only by default; two write actions behind approval
- **Entry point:** `python3 -m milou_news.cli serve --config console.json`
- **Purpose:** Make Milou something you open, instead of something you run.

## What it is

Until now Milou was a command line plus a read-only web view of stored reports.
The console adds the layer between them: routines on the left, one report at a
time on the right, and the two inbox actions reachable from the row they belong
to.

Every report it shows is built by the routine that builds it and rendered by
`render_html.render_report` — the same renderer the archive uses. The console
adds navigation and actions; it does not add a second way of producing reports.

## Routes

| Route | Method | What it does |
|---|---|---|
| `/` | GET | the archive index, or the sign-in form |
| `/routine/<name>` | GET | one routine, built on demand, inside the shell |
| `/action/ticket?message=<id>` | GET | the Create-ticket form, pre-filled |
| `/action/ticket` | POST | `intent=refresh` re-composes; `intent=create` writes |
| `/action/reply?message=<id>` | GET | the Ask-for-context form, pre-filled |
| `/action/reply` | POST | `intent=refresh` re-composes; `intent=send` sends |

An unknown routine is a 404 rather than a guess.

## No scripts

The forms are server-rendered, and every recomputation is a round trip:
correcting a name and pressing **Refresh** re-composes the description on the
server; unticking a question and pressing **Refresh** rewrites the reply.

That is a deliberate trade of a network round trip for a property worth more
than it: there is exactly one implementation of those rules, in Python, tested.
A browser-side copy would be a second implementation of the sprint rule, the
description shape and the question logic, free to drift from the one the CLI and
the scheduler use. It also means the console works in any viewer that can submit
a form.

## Safety boundary

- **Writes need a session.** A bearer token is accepted for reading a report and
  **refused** for `/action/*` POSTs. Bearer tokens exist so a script can fetch a
  report; letting one create a ticket would widen a read credential into a write
  credential by accident.
- **Writes need a CSRF token**, issued per session, compared in constant time,
  and required on every POST. A missing or wrong token is a 403.
- **Writes need a named approver**, and go through the same `ActionPlan`
  approval boundary as the CLI. Approval is bound to the plan's contents.
- **Writes need their own credentials**, which the console never holds: the
  three write tokens are read from the environment at execution time and are
  separate from every read token.
- **A console with no write credentials is fully usable and changes nothing.**
  Every action runs as a rehearsal that reports exactly what it would have done.
  A rehearsal is never reported as a completed action: the heading says it was a
  rehearsal, and the stand-in ticket number is an obviously fake `0000`.
- **Localhost by default.** The server binds `127.0.0.1` and is never published.

### Editing a reply's recipients

Sending a reply to the thread's own list needs only `Mail.Send`. Sending to an
**edited** list cannot use `replyAll` — that endpoint mails Outlook's own
recipient list and would silently discard the edit, showing one list and mailing
another. So an edited list is built as a draft whose recipients are actually
set, then sent, which needs `Mail.ReadWrite` as well.

Whether that wider grant exists is an **operator decision**
(`allow_recipient_edits` in the console configuration), never inferred from the
fact that somebody edited the field. Without it, an edited list is refused with a
message saying why, and nothing is sent.

## Not implemented

- No live run against a real mailbox, portal or document; the adapters are
  exercised against fixtures only.
- No per-user accounts: the console is single-user, and "approved by" is a name
  typed into the form rather than an identity the server can verify.
- No background refresh: a report is built when the page is requested.
