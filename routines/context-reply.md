# Routine contract: `context-reply`

- **Name:** `context-reply` (an action, not a scheduled routine)
- **Version:** 0.1.0
- **Access:** **write (sends mail), behind explicit approval**
- **Input kind:** one mailbox message + operator configuration
- **Purpose:** Ask the whole thread for the details a ticket needs, so a bug
  report stops being a ticket nobody can act on.

## Why this exists

The `ticket-from-email` action refuses to create a bug ticket that does not say
who reported it and when. That refusal is only useful if there is a way to go
and get those facts, and doing it by hand means opening the mailbox — which is
the thing the inbox monitor exists to replace.

So this is the other half of the same decision: the ticket action names what is
missing, and this action asks for exactly that.

## What it asks for

The questions are **derived from the gaps**, not from a template:

| Question | Asked when |
|---|---|
| The full name of the person who reported it (bug) or requested it (change) | that name was not found in the email |
| The project name or record title where it was encountered | no project or record was named |
| The date it was first reported or noticed (bugs only) | no date was found |
| "If you have any documentation, scope, screenshots or specifications, please attach those as well." | the email shared no links |

Asking someone for a name they already gave you is how a standard reply teaches
everyone to skim it. Each question can still be ticked back on by hand.

**When nothing is outstanding**, the reply does not fall back to asking
everything again. It asks them to *confirm* what Milou extracted, because every
extracted value came from pattern-matching a sentence and is a guess. Confirming
a guess is a smaller ask than answering an answered question, and it catches the
wrong name.

## Recipients

Reply-all, **minus the user's own address**. The sender leads `To`, everyone else
the message was addressed to follows, duplicates collapse, and the user is
removed from both `To` and `Cc`: a reply that copies you is a reply you have to
file twice.

## Safety boundary

- **Nothing is sent without an explicit, named approval**, and approval is bound
  to the exact recipients and the exact wording. Editing either clears it.
- **Send credentials are separate.** The token is read from
  `MILOU_OUTLOOK_WRITE_TOKEN`, never from the monitor's read-only
  `MILOU_OUTLOOK_TOKEN`, and is never logged, stored, echoed into a report, or
  written to the archive. An absent token fails closed.
- **`Mail.Send` is sufficient** for the default path, which posts to
  `/me/messages/{id}/replyAll` with a comment. That scope cannot read, modify,
  move or delete anything.
- **Editing the recipient list needs more.** Changing who receives the mail
  requires building a draft first, which needs `Mail.ReadWrite`. Rather than
  silently requiring the wider grant, the writer **refuses** an edited recipient
  list unless the operator has enabled it deliberately. Change the wording
  freely; changing who sees it is the thing that asks you a question.
- An empty recipient list, or a missing source message, fails closed.

## Not implemented

- No attachment handling: the reply asks for documents, it does not read or
  re-send any.
- Not yet run against a live mailbox; the adapter is written against the
  documented Graph shape and exercised only through fixtures.
