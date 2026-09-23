"""Proposed write actions and the approval boundary they must cross.

Every other routine in this project is read-only by construction. Creating a
Zoho ticket and editing a shared document are the first consequential actions
Milou can take, and the architecture reserves those for an explicit approval
step rather than letting a routine perform them as a side effect.

So a write is never performed by the code that decides it is a good idea. A
routine produces an :class:`ActionPlan` — a description of exactly what would
change, with every field resolved and every missing input named. The plan can be
read, corrected, and only then approved. :func:`execute` refuses a plan that is
unapproved or incomplete, and the writers require their own write-scoped
credentials so a read token can never perform a write.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from typing import Dict, List, Mapping, Sequence, Tuple

from .intake import (Intake, compose_acknowledgement, compose_description, compose_reply,
                     context_questions, intake_from_mapping, long_date, read_email,
                     reply_all_recipients, reply_subject)
from . import explain
from . import worddoc
from .report import Kpi, Report, Row, Signal, Tier
from .sprints import sprint_for

#: Write credentials are deliberately separate from the read tokens, so a
#: misconfigured read-only run cannot mutate anything.
ZOHO_WRITE_TOKEN_ENV = "MILOU_ZOHO_WRITE_TOKEN"
ZOHO_API_ROOT = "https://projectsapi.zoho.com"

#: Sending mail is a second, narrower privilege again: the inbox monitor's read
#: token must never be able to send in the user's name.
OUTLOOK_WRITE_TOKEN_ENV = "MILOU_OUTLOOK_WRITE_TOKEN"
#: And a third: editing the sprint tracker needs Files.ReadWrite, which reaches
#: every file the user can reach. It shares a token with nothing.
DOCUMENT_WRITE_TOKEN_ENV = "MILOU_DOCUMENT_WRITE_TOKEN"
GRAPH_API_ROOT = "https://graph.microsoft.com/v1.0"

#: A placeholder until the portal's real status list is configured. Zoho custom
#: statuses are per-portal, so this is deliberately not a guess at yours.
DEFAULT_STATUSES = ("Ready for Development",)

#: Narrative fields that are carried into the description; editing any of them
#: re-composes it, so the two can never disagree.
INTAKE_FIELDS = ("kind", "requested_by", "reported_by", "reported_on", "record", "context")

#: Placeholder resolved from an earlier action's result.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

_SUBJECT_NOISE = re.compile(r"^\s*(?:re|fw|fwd|aw|tr)\s*:\s*", re.I)
_BRACKETED = re.compile(r"^\s*[\[(][^\])]{0,40}[\])]\s*")
_STOPWORDS = {"the", "a", "an", "for", "and", "to", "of", "on", "in", "please", "request",
              "regarding", "re", "about", "with", "your", "our", "this", "that"}


class ApprovalRequired(Exception):
    """Raised when execution is attempted without explicit approval."""


class IncompleteAction(Exception):
    """Raised when a required input, such as the ticket title, is still missing."""


class WriteNotConfigured(Exception):
    """Raised when a write is attempted without a write-scoped credential."""


@dataclass(frozen=True)
class TicketConfig:
    portal: str = ""
    project: str = ""
    project_name: str = ""
    ready_status: str = "Ready for Development"
    #: Every status the portal offers, in the order the picker should show them.
    statuses: Tuple[str, ...] = DEFAULT_STATUSES
    document: str = ""
    document_url: str = ""
    document_heading: str = "{sprint}"
    #: Left empty on purpose. At "Ready for Development" the sprint is the
    #: queue, and pre-assigning makes someone accountable for work they have
    #: not seen.
    default_owner: str = ""
    #: Signed onto the context reply, because the mail goes out in your name.
    signature: str = ""
    #: After a ticket is created, leave a draft in Outlook telling the thread
    #: the number and the date. A draft, never a send: it is written into the
    #: mailbox and waits for you.
    acknowledge: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping) -> "TicketConfig":
        value = value or {}
        ready = str(value.get("ready_status") or "Ready for Development")
        statuses = tuple(str(item).strip() for item in (value.get("statuses") or ())
                         if str(item).strip())
        if statuses and ready not in statuses:
            # Sending Zoho a status its portal does not have fails at write time
            # with an unhelpful error. Catching it in configuration is cheaper.
            raise ValueError(
                "`ticket.ready_status` is %r, which is not in `ticket.statuses`. The default "
                "selection has to be one of the statuses your portal offers. Either add it to "
                "the list or pick one of: %s. See %s."
                % (ready, ", ".join(statuses), explain.RUNBOOK))
        return cls(
            portal=str(value.get("portal") or ""),
            project=str(value.get("project") or ""),
            project_name=str(value.get("project_name") or ""),
            ready_status=ready,
            statuses=statuses or (ready,),
            document=str(value.get("document") or ""),
            document_url=str(value.get("document_url") or ""),
            document_heading=str(value.get("document_heading") or "{sprint}"),
            default_owner=str(value.get("default_owner") or ""),
            signature=str(value.get("signature") or ""),
            acknowledge=bool(value.get("acknowledge", True)),
        )


@dataclass
class ProposedAction:
    """One change, fully described before anything is touched."""

    kind: str
    summary: str
    target: str
    fields: Dict[str, str] = field(default_factory=dict)
    requires: Tuple[str, ...] = ()
    produces: Tuple[str, ...] = ()

    def missing(self) -> List[str]:
        return [name for name in self.requires if not str(self.fields.get(name, "")).strip()]

    def resolved(self, context: Mapping) -> "ProposedAction":
        """Substitute ``{name}`` placeholders from an earlier action's result."""
        def fill(text: str) -> str:
            return _PLACEHOLDER.sub(
                lambda match: str(context.get(match.group(1), match.group(0))), text)
        return replace(self, summary=fill(self.summary), target=fill(self.target),
                       fields={key: fill(str(value)) for key, value in self.fields.items()})


@dataclass
class ActionPlan:
    """An ordered set of changes that are approved, or not, as one decision."""

    title: str
    actions: List[ProposedAction] = field(default_factory=list)
    approved_by: str = ""
    approved_at: str = ""
    origin: str = ""
    #: The source email's citation details, kept so an edited narrative field
    #: can re-compose the description without re-reading the mailbox.
    source: Dict[str, str] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return bool(self.approved_by)

    def missing(self) -> List[str]:
        names = []
        for action in self.actions:
            names.extend(action.missing())
        return sorted(set(names))

    def with_inputs(self, recompose=None, **values) -> "ActionPlan":
        """Return a copy with supplied inputs filled in. Approval is reset.

        Any field the action already carries can be corrected, not only the
        required ones: the point of showing the whole plan is that all of it is
        editable. Correcting a narrative field re-composes the description, so
        a description that says "Reported by: (not stated)" cannot survive the
        moment you supply the name.

        Re-composition triggers on a narrative value that **actually changed**,
        not merely on one being supplied. A caller that resubmits every field
        unchanged — which is what a form does — would otherwise have its
        hand-edited description silently overwritten, so the text someone
        approved would not be the text that was written. ``recompose`` forces
        the decision either way when the caller already knows.
        """
        actions = []
        for action in self.actions:
            fields = dict(action.fields)
            changed_intake = False
            for name, value in values.items():
                if name in action.requires or name in fields:
                    supplied = "" if value is None else str(value)
                    if name in INTAKE_FIELDS and supplied != str(fields.get(name, "")):
                        changed_intake = True
                    if value or name not in action.requires:
                        fields[name] = supplied
            touched_intake = changed_intake if recompose is None else bool(recompose)
            if touched_intake and "description" in fields:
                fields["description"] = compose_description(
                    intake_from_mapping({**fields, "links": _split_links(fields.get("links", ""))}),
                    subject=self.source.get("subject", ""), sender=self.source.get("sender", ""),
                    received=self.source.get("received", ""), url=self.source.get("url", ""))
            actions.append(replace(action, fields=fields))
        return replace(self, actions=actions, approved_by="", approved_at="")

    def approve(self, who: str, when: datetime = None) -> "ActionPlan":
        """Approve the plan as it stands.

        Approval is bound to the current contents: :meth:`with_inputs` clears it,
        so a plan cannot be approved and then quietly edited before it runs.
        """
        if not who:
            raise ApprovalRequired(
                "Nothing was done, because approval needs a name. Put yours in "
                "\u201cApproved by\u201d so the record of who approved this is not blank.")
        missing = self.missing()
        if missing:
            raise IncompleteAction(
                "Nothing was done, because %s %s still empty. %s"
                % (explain.labels(missing), "is" if len(missing) == 1 else "are",
                   "The email did not state it, so fill it in, or use "
                   "\u201cAsk for context\u201d to ask the thread for it."
                   if set(missing) & {"reported_by", "reported_on", "record"}
                   else "Fill it in before approving."))
        invalid = self.invalid()
        if invalid:
            raise IncompleteAction("Nothing was done. " + "; ".join(invalid))
        stamp = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return replace(self, approved_by=who, approved_at=stamp.isoformat())

    def invalid(self) -> List[str]:
        """Values that are present but cannot be right.

        Only the status so far. It is worth catching here rather than at write
        time, because Zoho rejects an unknown custom status with an error that
        says nothing about which statuses it does have.
        """
        problems = []
        for action in self.actions:
            options = _split_lines(action.fields.get("status_options", ""))
            status = str(action.fields.get("status", "")).strip()
            if options and status and status not in options:
                problems.append(
                    "The status %r is not one your Zoho portal offers, and Zoho rejects an "
                    "unknown status with an error that names no alternatives. Pick one of: %s"
                    % (status, ", ".join(options)))
        return problems


@dataclass
class ExecutionResult:
    action: str
    ok: bool
    detail: str = ""
    produced: Dict[str, str] = field(default_factory=dict)


def shorten(subject: str, words: int = 6) -> str:
    """An extremely brief title suggestion, derived from an email subject.

    Only ever a *suggestion*: the user is asked to confirm or replace it,
    because a ticket title is read by people who never saw the email.
    """
    text = _SUBJECT_NOISE.sub("", subject or "")
    while True:
        stripped = _BRACKETED.sub("", text)
        if stripped == text:
            break
        text = stripped
    text = re.sub(r"\s+", " ", text).strip(" -–—:·")
    if not text:
        return ""
    tokens = text.split(" ")
    kept, seen_word = [], False
    for token in tokens:
        if len(kept) >= words:
            break
        if not seen_word and token.lower() in _STOPWORDS:
            continue
        seen_word = True
        kept.append(token)
    # A suggestion that ends on "on" or "for" reads as though it was cut off,
    # which is exactly what happened.
    while kept and kept[-1].lower() in _STOPWORDS:
        kept.pop()
    suggestion = " ".join(kept).strip(" -–—:·,.")
    return suggestion[:1].upper() + suggestion[1:] if suggestion else ""


def _split_lines(value) -> Tuple[str, ...]:
    """One value per line. Statuses contain spaces, so nothing else will do."""
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(part.strip() for part in str(value or "").splitlines() if part.strip())


def _split_links(value) -> Tuple[str, ...]:
    """Links survive a round trip through the dialog as one newline-joined field."""
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(part.strip() for part in re.split(r"[\s,]+", str(value or "")) if part.strip())


def document_line(ticket_id: str, title: str) -> str:
    """``1234 - Title`` — the last four digits of the ticket number."""
    digits = re.sub(r"\D", "", str(ticket_id or ""))
    return "%s - %s" % (digits[-4:] if digits else str(ticket_id or "?"), title)


def draft_ticket(config: TicketConfig, today: date, subject: str, sender: str = "",
                 received: str = "", body: str = "", url: str = "", title: str = "",
                 received_date: date = None, intake: Intake = None,
                 message_id: str = "") -> ActionPlan:
    """Prepare the ticket and the document line, without performing either.

    A bug report carries two facts a feature request does not — who actually
    reported it, and when — and those are almost never in the email. They are
    therefore **required**, not optional: the plan stays incomplete until they
    are supplied, and the context reply exists to go and get them.
    """
    start, tag = sprint_for(today)
    heading = config.document_heading.format(sprint=tag, date=start.isoformat())
    intake = intake or read_email(subject, body, sender_name=sender,
                                  received=received_date or today)
    source = {"subject": subject or "", "sender": sender or "",
              "received": received or "", "url": url or ""}
    create = ProposedAction(
        kind="zoho.create_task",
        summary="Create a Zoho task in %s scheduled for the %s"
                % (config.project_name or config.project or "the configured project", tag),
        target="%s / %s" % (config.portal or "portal?", config.project or "project?"),
        fields={
            "portal": config.portal,
            "project": config.project,
            "title": title or "",
            "status": config.ready_status,
            "status_options": "\n".join(config.statuses),
            "owner": config.default_owner,
            "tag": tag,
            "release_date": start.isoformat(),
            "kind": intake.kind,
            "requested_by": intake.requested_by,
            "reported_by": intake.reported_by,
            "reported_on": intake.reported_on,
            "record": intake.record,
            "context": intake.context,
            "links": "\n".join(intake.links),
            "description": compose_description(intake, subject, sender, received, url),
        },
        requires=("title",) + intake.required(), produces=("ticket_id", "ticket_url"),
    )
    record = ProposedAction(
        kind="document.append_line",
        summary="Add one line under the %s heading of the sprint tracker" % tag,
        target=config.document or "document not configured",
        fields={"heading": heading, "title": title or ""},
        requires=("title",),
    )
    plan_actions = [create, record]
    if config.acknowledge and message_id:
        # The ticket number does not exist yet, so the body carries a
        # placeholder and is resolved after the task is actually created.
        plan_actions.append(ProposedAction(
            kind="outlook.create_draft",
            summary="Leave a draft reply telling the thread the ticket number and the %s date"
                    % tag,
            target="Outlook drafts",
            fields={
                "message_id": message_id,
                "subject": reply_subject(subject),
                "release_date": start.isoformat(),
                "tag": tag,
                "body": compose_acknowledgement("{ticket_id}", start.isoformat(), tag,
                                                config.signature, intake.is_bug),
            },
        ))
    return ActionPlan(
        title="Create ticket for the %s" % tag,
        actions=plan_actions,
        origin=url or subject,
        source=source,
    )


def draft_context_reply(config: TicketConfig, subject: str = "", sender: str = "",
                        sender_address: str = "", to: Sequence[str] = (),
                        cc: Sequence[str] = (), mailbox: str = "", message_id: str = "",
                        body: str = "", received_date: date = None,
                        intake: Intake = None, url: str = "", questions=None) -> ActionPlan:
    """Prepare a reply-all asking the thread for what a ticket needs.

    The questions are the gaps, not a template. Asking someone for a name they
    already gave you is how a standard reply teaches everyone to skim it.
    """
    intake = intake or read_email(subject, body, sender_name=sender, received=received_date)
    # The caller may have already decided what to ask — a reviewer can tick a
    # question back on, or off — so their list wins over a freshly derived one.
    questions = list(questions) if questions is not None else context_questions(intake)
    outstanding = [question for question in questions if question.outstanding]
    primary, copied = reply_all_recipients(sender_address, to, cc, mailbox)
    reply = ProposedAction(
        kind="outlook.reply_all",
        summary="Reply to everyone on “%s” asking for %d missing detail%s"
                % (subject or "(no subject)", len(outstanding),
                   "" if len(outstanding) == 1 else "s"),
        target=", ".join(primary) or "no recipients",
        fields={
            "message_id": message_id,
            "to": "\n".join(primary),
            "cc": "\n".join(copied),
            "original_to": "\n".join(primary),
            "original_cc": "\n".join(copied),
            "subject": reply_subject(subject),
            "asking_for": ", ".join(question.key for question in outstanding),
            "body": compose_reply(intake, questions, signature=config.signature,
                                  subject=subject),
        },
        requires=("to", "body"),
    )
    return ActionPlan(title="Ask for the missing context", actions=[reply],
                      origin=url or message_id or subject, source={"subject": subject or ""})


class ZohoWriter:
    """Creates a Zoho task. Requires its own write-scoped token."""

    def __init__(self, token=None, environ=None, timeout=20, root=ZOHO_API_ROOT):
        self.token = token if token is not None else (environ or os.environ).get(ZOHO_WRITE_TOKEN_ENV)
        self.timeout = timeout
        self.root = root

    def create_task(self, portal: str, project: str, fields: Mapping) -> ExecutionResult:
        if not self.token:
            raise WriteNotConfigured(explain.missing_token(
                "Zoho Projects write", ZOHO_WRITE_TOKEN_ENV, "creating a ticket"))
        if not portal:
            raise WriteNotConfigured(explain.not_configured(
                "ticket.portal", "Milou does not know which Zoho portal to create the ticket in",
                '"portal": "yourportal"'))
        if not project:
            raise WriteNotConfigured(explain.not_configured(
                "ticket.project", "Milou does not know which project to create the ticket in",
                '"project": "5001" (the numeric id in the project\'s URL)'))
        payload = {
            "name": fields.get("title", ""),
            "description": fields.get("description", ""),
            "custom_status": fields.get("status", ""),
            "tags": fields.get("tag", ""),
            "end_date": fields.get("release_date", ""),
        }
        # Omitted entirely when unassigned. Zoho reads this as a user id, and
        # sending an empty one is not the same as sending none.
        if fields.get("owner"):
            payload["person_responsible"] = fields.get("owner", "")
        body = urllib.parse.urlencode(payload).encode("ascii")
        request = urllib.request.Request(
            "%s/restapi/portal/%s/projects/%s/tasks/" % (self.root, portal, project),
            data=body, method="POST",
            headers={"Authorization": "Zoho-oauthtoken " + self.token,
                     "Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return ExecutionResult("zoho.create_task", False, explain.http_failure(
                "Zoho Projects", "creating the ticket", exc.code, exc.reason,
                ZOHO_WRITE_TOKEN_ENV, "ZohoProjects.tasks.CREATE"))
        except urllib.error.URLError as exc:
            return ExecutionResult("zoho.create_task", False, explain.unreachable(
                "Zoho Projects", "creating the ticket", str(exc.reason)))
        except TimeoutError:
            return ExecutionResult("zoho.create_task", False, explain.timed_out(
                "Zoho Projects", "creating the ticket", self.timeout))
        except ValueError:
            return ExecutionResult("zoho.create_task", False, explain.unreadable(
                "Zoho Projects", "creating the ticket"))
        tasks = payload.get("tasks") if isinstance(payload, Mapping) else None
        created = tasks[0] if isinstance(tasks, list) and tasks else (
            payload if isinstance(payload, Mapping) else {})
        identifier = str(created.get("id_string") or created.get("id") or created.get("key") or "")
        link = created.get("link") or {}
        url = ""
        if isinstance(link, Mapping):
            inner = link.get("self")
            url = str((inner or {}).get("url") or "") if isinstance(inner, Mapping) else str(inner or "")
        return ExecutionResult("zoho.create_task", bool(identifier),
                               "Created task %s." % identifier if identifier
                               else "Zoho accepted the ticket but did not return its number, so "
                                    "the tracker line and the acknowledgement cannot reference it. "
                                    "Check the project in Zoho before creating it again — it may "
                                    "already be there.",
                               {"ticket_id": identifier, "ticket_url": url})


class OutlookReplyWriter:
    """Sends one reply. Requires its own send-scoped token.

    Two paths, and the narrower one is preferred:

    * **Recipients untouched** — ``POST /me/messages/{id}/replyAll`` with a
      comment. This needs only ``Mail.Send``: it cannot read, modify, move or
      delete anything, and Outlook threads the reply correctly.
    * **Recipients edited** — the reply has to be built as a draft first, which
      needs ``Mail.ReadWrite`` as well. That is a materially wider grant, so it
      is refused unless the operator has opted into it explicitly.

    The default is therefore: change the wording freely, and adding or removing
    a recipient is the thing that asks you a question.
    """

    def __init__(self, token=None, environ=None, timeout=20, root=GRAPH_API_ROOT,
                 allow_recipient_edits=False):
        self.token = token if token is not None else (environ or os.environ).get(
            OUTLOOK_WRITE_TOKEN_ENV)
        self.timeout = timeout
        self.root = root
        self.allow_recipient_edits = allow_recipient_edits

    def _post(self, path: str, payload: Mapping):
        request = urllib.request.Request(
            self.root + path, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.token,
                     "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def send_reply(self, fields: Mapping) -> ExecutionResult:
        if not self.token:
            raise WriteNotConfigured(explain.missing_token(
                "Microsoft Graph send", OUTLOOK_WRITE_TOKEN_ENV, "sending this reply"))
        message_id = str(fields.get("message_id") or "")
        if not message_id:
            raise WriteNotConfigured(explain.internal(
                "a reply was built without the message it replies to"))
        recipients = _split_links(fields.get("to", ""))
        if not recipients:
            raise IncompleteAction(
                "Nothing was sent, because the reply has no recipients. Add at least one "
                "address to \u201cTo\u201d.")
        edited = (recipients != _split_links(fields.get("original_to", ""))
                  or _split_links(fields.get("cc", "")) != _split_links(fields.get("original_cc", "")))
        if edited and not self.allow_recipient_edits:
            raise WriteNotConfigured(
                "Nothing was sent, because you changed who this reply goes to. Sending the "
                "thread's own recipients needs only Mail.Send; sending an edited list has to "
                "build a draft first, which needs the wider Mail.ReadWrite grant. Either put "
                "the original recipients back, or set `allow_recipient_edits: true` once that "
                "grant is in place. See %s." % explain.RUNBOOK)
        try:
            if edited:
                # replyAll would send to Outlook's own list and quietly discard
                # the edit, so an edited list must go through a draft whose
                # recipients are actually set. Never fall back to replyAll here:
                # showing one recipient list and mailing another is worse than
                # refusing outright.
                return self._send_edited(message_id, fields, recipients)
            self._post("/me/messages/%s/replyAll" % urllib.parse.quote(message_id, safe=""),
                       {"comment": str(fields.get("body") or "")})
        except urllib.error.HTTPError as exc:
            # Status and reason only. The response body and the request headers
            # can both carry the token back.
            return ExecutionResult("outlook.reply_all", False, explain.http_failure(
                "Microsoft Graph", "sending the reply", exc.code, exc.reason,
                OUTLOOK_WRITE_TOKEN_ENV, "Mail.Send"))
        except urllib.error.URLError as exc:
            return ExecutionResult("outlook.reply_all", False, explain.unreachable(
                "Microsoft Graph", "sending the reply", str(exc.reason)))
        except TimeoutError:
            return ExecutionResult("outlook.reply_all", False, explain.timed_out(
                "Microsoft Graph", "sending the reply", self.timeout))
        except ValueError:
            return ExecutionResult("outlook.reply_all", False, explain.unreadable(
                "Microsoft Graph", "sending the reply"))
        return ExecutionResult("outlook.reply_all", True,
                               "replied to %d recipient%s"
                               % (len(recipients), "" if len(recipients) == 1 else "s"),
                               {"replied_to": ", ".join(recipients)})

    def _send_edited(self, message_id: str, fields: Mapping,
                     recipients: Sequence[str]) -> ExecutionResult:
        """Send a reply whose recipient list differs from the thread's.

        Built as a draft so the recipients can actually be set, then sent. This
        is the path that needs ``Mail.ReadWrite`` on top of ``Mail.Send``.
        """
        quoted = urllib.parse.quote(message_id, safe="")
        created = self._post("/me/messages/%s/createReplyAll" % quoted, {})
        draft_id = str((created or {}).get("id") or "")
        if not draft_id:
            return ExecutionResult("outlook.reply_all", False,
                                   "Graph created no draft to put the edited recipients on")
        self._patch("/me/messages/%s" % urllib.parse.quote(draft_id, safe=""), {
            "body": {"contentType": "text", "content": str(fields.get("body") or "")},
            "toRecipients": [{"emailAddress": {"address": address}} for address in recipients],
            "ccRecipients": [{"emailAddress": {"address": address}}
                             for address in _split_links(fields.get("cc", ""))],
        })
        self._post("/me/messages/%s/send" % urllib.parse.quote(draft_id, safe=""), {})
        return ExecutionResult("outlook.reply_all", True,
                               "replied to %d edited recipient%s"
                               % (len(recipients), "" if len(recipients) == 1 else "s"),
                               {"replied_to": ", ".join(recipients)})

    def create_draft(self, fields: Mapping) -> ExecutionResult:
        """Leave an acknowledgement in Drafts. Nothing is sent.

        This writes into the mailbox rather than out of it, which needs
        ``Mail.ReadWrite`` — wider than ``Mail.Send``, and worth stating: the
        same grant can modify and delete mail. What it buys is that the message
        sits in Outlook until you press Send yourself, with the real ticket
        number already in it.
        """
        if not self.token:
            raise WriteNotConfigured(explain.missing_token(
                "Microsoft Graph", OUTLOOK_WRITE_TOKEN_ENV,
                "leaving the acknowledgement draft in your mailbox"))
        message_id = str(fields.get("message_id") or "")
        if not message_id:
            raise WriteNotConfigured(explain.internal(
                "a draft was built without the message it replies to"))
        quoted = urllib.parse.quote(message_id, safe="")
        try:
            created = self._post("/me/messages/%s/createReplyAll" % quoted, {})
            draft_id = str((created or {}).get("id") or "")
            if not draft_id:
                return ExecutionResult("outlook.create_draft", False,
                                       "The ticket was created, but Outlook did not return a "
                                       "draft to write the acknowledgement into. Nothing is "
                                       "waiting in your Drafts; you can reply to the thread by "
                                       "hand with the ticket number above.")
            self._patch("/me/messages/%s" % urllib.parse.quote(draft_id, safe=""),
                        {"body": {"contentType": "text", "content": str(fields.get("body") or "")}})
        except urllib.error.HTTPError as exc:
            return ExecutionResult("outlook.create_draft", False, explain.http_failure(
                "Microsoft Graph", "leaving the acknowledgement draft", exc.code, exc.reason,
                OUTLOOK_WRITE_TOKEN_ENV, "Mail.ReadWrite"))
        except urllib.error.URLError as exc:
            return ExecutionResult("outlook.create_draft", False, explain.unreachable(
                "Microsoft Graph", "leaving the acknowledgement draft", str(exc.reason)))
        except TimeoutError:
            return ExecutionResult("outlook.create_draft", False, explain.timed_out(
                "Microsoft Graph", "leaving the acknowledgement draft", self.timeout))
        except ValueError:
            return ExecutionResult("outlook.create_draft", False, explain.unreadable(
                "Microsoft Graph", "leaving the acknowledgement draft"))
        return ExecutionResult("outlook.create_draft", True,
                               "draft saved in Outlook, unsent", {"draft_id": draft_id})

    def _patch(self, path: str, payload: Mapping):
        request = urllib.request.Request(
            self.root + path, data=json.dumps(payload).encode("utf-8"), method="PATCH",
            headers={"Authorization": "Bearer " + self.token,
                     "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


class DryRunMailWriter:
    """Records the mail that would be sent or drafted, and touches nothing."""

    def __init__(self):
        self.sent: List[Dict[str, str]] = []
        self.drafted: List[Dict[str, str]] = []

    def send_reply(self, fields: Mapping) -> ExecutionResult:
        self.sent.append(dict(fields))
        return ExecutionResult("outlook.reply_all", True,
                               "dry run: would reply to %s" % (fields.get("to") or "nobody"))

    def create_draft(self, fields: Mapping) -> ExecutionResult:
        self.drafted.append(dict(fields))
        return ExecutionResult("outlook.create_draft", True,
                               "dry run: would leave a draft on %s"
                               % (fields.get("subject") or "the thread"))


class SharePointWordWriter:
    """Appends one line to a Word document stored in SharePoint or OneDrive.

    Scoped to its own credential again. Editing a document is a third kind of
    privilege — ``Files.ReadWrite`` can read and overwrite every file the user
    can reach — and it has no business sharing a token with the mailbox or the
    ticket system.

    The document is downloaded, edited in memory, and uploaded back. The
    original bytes are handed to ``keep_backup`` first when one is supplied, so
    a bad edit to a hand-maintained tracker is recoverable.
    """

    def __init__(self, share_url: str = "", token=None, environ=None, timeout=30,
                 root=GRAPH_API_ROOT, keep_backup=None):
        self.share_url = share_url
        self.token = token if token is not None else (environ or os.environ).get(
            DOCUMENT_WRITE_TOKEN_ENV)
        self.timeout = timeout
        self.root = root
        self.keep_backup = keep_backup

    @staticmethod
    def share_id(url: str) -> str:
        """Graph's encoding for a sharing link: ``u!`` plus unpadded base64url."""
        encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
        return "u!" + encoded.rstrip("=")

    def _request(self, path: str, method="GET", data=None, content_type=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(self.root + path, data=data, method=method,
                                         headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def _locate(self):
        payload = json.loads(self._request(
            "/shares/%s/driveItem?$select=id,name,parentReference"
            % urllib.parse.quote(self.share_id(self.share_url), safe="!")).decode("utf-8"))
        parent = payload.get("parentReference") or {}
        drive, item = str(parent.get("driveId") or ""), str(payload.get("id") or "")
        name = str(payload.get("name") or "")
        if not drive or not item:
            raise WriteNotConfigured(
                "The sprint tracker link does not resolve to a file Milou can open. Use the "
                "link Word gives you under Share \u2192 Copy link, and make sure the account "
                "whose token you configured can open it.")
        if not name.lower().endswith(".docx"):
            # A .doc, or a page that merely looks like one, would be destroyed
            # by writing .docx bytes over it.
            raise WriteNotConfigured(
                "The sprint tracker %r is not a .docx, and writing .docx bytes over it would "
                "destroy it. Open it in Word and use File \u2192 Save As to save a .docx, then "
                "point `ticket.document_url` at the new file." % name)
        return drive, item, name

    def append_under_heading(self, document: str, heading: str, line: str) -> ExecutionResult:
        if not self.token:
            raise WriteNotConfigured(explain.missing_token(
                "Microsoft Graph file", DOCUMENT_WRITE_TOKEN_ENV,
                "adding the line to the sprint tracker"))
        if not self.share_url:
            raise WriteNotConfigured(explain.not_configured(
                "ticket.document_url",
                "Milou does not know which document to add the sprint line to",
                "the link from Word \u2192 Share \u2192 Copy link"))
        try:
            drive, item, name = self._locate()
            path = "/drives/%s/items/%s/content" % (urllib.parse.quote(drive, safe=""),
                                                    urllib.parse.quote(item, safe=""))
            original = self._request(path)
            if self.keep_backup:
                self.keep_backup(original, name)
            updated, detail = worddoc.append_to_docx(original, heading, line)
            if updated == original:
                return ExecutionResult("document.append_line", True, detail)
            self._request(path, method="PUT", data=updated,
                          content_type="application/vnd.openxmlformats-officedocument."
                                       "wordprocessingml.document")
        except worddoc.DocumentError as exc:
            return ExecutionResult("document.append_line", False, str(exc))
        except urllib.error.HTTPError as exc:
            return ExecutionResult("document.append_line", False, explain.http_failure(
                "Microsoft Graph", "updating the sprint tracker", exc.code, exc.reason,
                DOCUMENT_WRITE_TOKEN_ENV, "Files.ReadWrite.All"))
        except urllib.error.URLError as exc:
            return ExecutionResult("document.append_line", False, explain.unreachable(
                "Microsoft Graph", "updating the sprint tracker", str(exc.reason)))
        except TimeoutError:
            return ExecutionResult("document.append_line", False, explain.timed_out(
                "Microsoft Graph", "updating the sprint tracker", self.timeout))
        except ValueError:
            return ExecutionResult("document.append_line", False, explain.unreadable(
                "Microsoft Graph", "updating the sprint tracker"))
        return ExecutionResult("document.append_line", True, "%s in %s" % (detail, name))


class DryRunDocumentWriter:
    """Records what would be appended without touching any document.

    The live document adapter is deliberately absent: appending to a shared
    Microsoft document requires knowing whether it is a Word file, a OneNote
    page, or a Loop component, and each needs a different Graph call. Guessing
    would risk corrupting a manually maintained tracker.
    """

    def __init__(self):
        self.appended: List[Tuple[str, str, str]] = []

    def append_under_heading(self, document: str, heading: str, line: str) -> ExecutionResult:
        self.appended.append((document, heading, line))
        return ExecutionResult("document.append_line", True,
                               "dry run: would add %r under %r in %s" % (line, heading, document))


def execute(plan: ActionPlan, zoho_writer=None, document_writer=None,
            mail_writer=None) -> List[ExecutionResult]:
    """Run an approved plan. Refuses anything unapproved or incomplete."""
    if not plan.approved:
        raise ApprovalRequired(
            "Nothing was done. This plan changes systems outside Milou and has not been "
            "approved, so it will not run.")
    missing = plan.missing()
    if missing:
        raise IncompleteAction(
            "Nothing was done, because %s still empty." % explain.labels(missing))

    results: List[ExecutionResult] = []
    context: Dict[str, str] = {}
    for action in plan.actions:
        resolved = action.resolved(context)
        if resolved.kind == "zoho.create_task":
            if zoho_writer is None:
                raise WriteNotConfigured("no Zoho writer supplied")
            result = zoho_writer.create_task(
                resolved.fields.get("portal", ""), resolved.fields.get("project", ""),
                resolved.fields)
        elif resolved.kind == "document.append_line":
            if document_writer is None:
                raise WriteNotConfigured(explain.internal("no document writer was supplied to execute()"))
            # Built here, not at draft time: the ticket number does not exist
            # until the task above has actually been created.
            line = document_line(context.get("ticket_id", ""), resolved.fields.get("title", ""))
            result = document_writer.append_under_heading(
                resolved.target, resolved.fields.get("heading", ""), line)
        elif resolved.kind == "outlook.reply_all":
            if mail_writer is None:
                raise WriteNotConfigured(explain.internal("no mail writer was supplied to execute()"))
            result = mail_writer.send_reply(resolved.fields)
        elif resolved.kind == "outlook.create_draft":
            if mail_writer is None:
                raise WriteNotConfigured(explain.internal("no mail writer was supplied to execute()"))
            result = mail_writer.create_draft(resolved.fields)
        else:
            result = ExecutionResult(resolved.kind, False, explain.internal(
                "there is no writer for the action kind %r" % resolved.kind))
        results.append(result)
        context.update(result.produced)
        if not result.ok:
            # Stop rather than record a document line for a ticket that does not
            # exist; a half-applied plan is worse than a refused one.
            break
    return results


#: What is worth showing on the review row, per action kind, and in what order.
#: Everything else is in the description, which is shown in full below it.
_PREVIEW_FIELDS = {
    "zoho.create_task": ("title", "status", "owner", "tag", "release_date",
                         "kind", "requested_by", "reported_by", "reported_on", "record"),
    "document.append_line": ("heading", "line"),
    "outlook.reply_all": ("to", "cc", "subject", "asking_for"),
    "outlook.create_draft": ("subject", "release_date", "tag"),
}


def _plan_rows(plan: ActionPlan) -> List[Row]:
    rows = []
    for action in plan.actions:
        preview = dict(action.fields)
        if action.kind == "document.append_line":
            preview["line"] = "#### - %s" % (preview.get("title") or "<title>")
        names = _PREVIEW_FIELDS.get(action.kind, tuple(preview))
        flags = [Signal("%s: %s" % (name.replace("_", " "),
                                    " · ".join(preview[name].splitlines()) or "—"),
                        "" if preview[name] else "notable")
                 for name in names if name in preview]
        if action.missing():
            flags.append(Signal("waiting on: %s" % ", ".join(action.missing()), "critical"))
        rows.append(Row(title=action.summary, byline=action.target,
                        summary=preview.get("description") or preview.get("body", ""),
                        tone="critical" if action.missing() else "notable", flags=flags))
    return rows


def reply_plan_report(plan: ActionPlan, today: date) -> Report:
    """Render the context reply for review. Nothing is sent by building this."""
    missing = plan.missing()
    asking = plan.actions[0].fields.get("asking_for", "") if plan.actions else ""
    recipients = _split_links(plan.actions[0].fields.get("to", "")) if plan.actions else ()
    return Report(
        title="Proposed reply", routine="context-reply",
        generated=today.isoformat(), window=plan.source.get("subject", ""),
        scopes=list(recipients) or ["no recipients"],
        kpis=[
            Kpi("Recipients", str(len(recipients)), "reply-all, minus you"),
            Kpi("Asking for", str(len(_split_links(asking.replace(",", " ")))),
                asking.replace(",", ", ") or "nothing outstanding", "notable"),
            Kpi("Sent", "0", "nothing has left your mailbox", "critical" if missing else ""),
        ],
        tiers=[Tier(label="Nothing has been sent yet", rows=_plan_rows(plan), tone="notable",
                    note="Review the recipients and the wording, then approve")],
        alert="Approval required before this reply is sent",
        alert_detail="Milou has sent nothing. This mail goes out in your name only after "
                     "explicit approval.",
        boundary=("Sending requires %s (Mail.Send) · the read token cannot send · approval is "
                  "bound to these exact recipients and this exact wording."
                  % OUTLOOK_WRITE_TOKEN_ENV),
    )


def plan_report(plan: ActionPlan, config: TicketConfig, today: date) -> Report:
    """Render a plan for review, in the same structure every report uses."""
    start, tag = sprint_for(today)
    missing = plan.missing()
    rows = _plan_rows(plan)
    return Report(
        title="Proposed ticket", routine="ticket-draft",
        generated=today.isoformat(), window="Sprint %s" % tag,
        scopes=[config.project_name or config.project or "project not configured"],
        kpis=[
            Kpi("Sprint", tag, "starts %s" % start.isoformat()),
            Kpi("Status", config.ready_status, "on creation"),
            Kpi("Actions", str(len(plan.actions)), "pending approval", "notable"),
            Kpi("Waiting on you", str(len(missing)), ", ".join(missing) or "nothing",
                "critical" if missing else ""),
        ],
        tiers=[Tier(label="Nothing has been created yet", rows=rows, tone="notable",
                    note="Review, supply the title, then approve")],
        alert=("Approval required — %s" % ", ".join(missing)) if missing
        else "Approval required before anything is created",
        alert_detail="Milou has changed nothing. These actions run only after explicit approval.",
        boundary=("Write actions require %s and a configured document target · approval is "
                  "bound to these exact contents, so editing the plan clears it."
                  % ZOHO_WRITE_TOKEN_ENV),
    )
