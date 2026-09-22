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
from .report import Kpi, Report, Row, Signal, Tier
from .sprints import sprint_for

#: Write credentials are deliberately separate from the read tokens, so a
#: misconfigured read-only run cannot mutate anything.
ZOHO_WRITE_TOKEN_ENV = "MILOU_ZOHO_WRITE_TOKEN"
ZOHO_API_ROOT = "https://projectsapi.zoho.com"

#: Sending mail is a second, narrower privilege again: the inbox monitor's read
#: token must never be able to send in the user's name.
OUTLOOK_WRITE_TOKEN_ENV = "MILOU_OUTLOOK_WRITE_TOKEN"
GRAPH_API_ROOT = "https://graph.microsoft.com/v1.0"

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
    document: str = ""
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
        return cls(
            portal=str(value.get("portal") or ""),
            project=str(value.get("project") or ""),
            project_name=str(value.get("project_name") or ""),
            ready_status=str(value.get("ready_status") or "Ready for Development"),
            document=str(value.get("document") or ""),
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

    def with_inputs(self, **values) -> "ActionPlan":
        """Return a copy with supplied inputs filled in. Approval is reset.

        Any field the action already carries can be corrected, not only the
        required ones: the point of showing the whole plan is that all of it is
        editable. Correcting a narrative field re-composes the description, so
        a description that says "Reported by: (not stated)" cannot survive the
        moment you supply the name.
        """
        actions = []
        touched_intake = any(name in INTAKE_FIELDS for name in values)
        for action in self.actions:
            fields = dict(action.fields)
            for name, value in values.items():
                if name in action.requires or name in fields:
                    if value or name not in action.requires:
                        fields[name] = "" if value is None else str(value)
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
            raise ApprovalRequired("approval requires an identified approver")
        missing = self.missing()
        if missing:
            raise IncompleteAction("still missing: %s" % ", ".join(missing))
        stamp = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return replace(self, approved_by=who, approved_at=stamp.isoformat())


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
                        intake: Intake = None, url: str = "") -> ActionPlan:
    """Prepare a reply-all asking the thread for what a ticket needs.

    The questions are the gaps, not a template. Asking someone for a name they
    already gave you is how a standard reply teaches everyone to skim it.
    """
    intake = intake or read_email(subject, body, sender_name=sender, received=received_date)
    questions = context_questions(intake)
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
            raise WriteNotConfigured(
                "%s is not set; ticket creation fails closed" % ZOHO_WRITE_TOKEN_ENV)
        if not portal or not project:
            raise WriteNotConfigured("a portal and project must be configured before writing")
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
            return ExecutionResult("zoho.create_task", False,
                                   "Zoho returned HTTP %s %s" % (exc.code, exc.reason))
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return ExecutionResult("zoho.create_task", False,
                                   "Zoho write failed: %s" % type(exc).__name__)
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
                               "created task %s" % identifier if identifier
                               else "Zoho accepted the write but returned no task id",
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
            raise WriteNotConfigured(
                "%s is not set; the reply fails closed" % OUTLOOK_WRITE_TOKEN_ENV)
        message_id = str(fields.get("message_id") or "")
        if not message_id:
            raise WriteNotConfigured("a reply needs the message it is replying to")
        recipients = _split_links(fields.get("to", ""))
        if not recipients:
            raise IncompleteAction("a reply needs at least one recipient")
        edited = (recipients != _split_links(fields.get("original_to", ""))
                  or _split_links(fields.get("cc", "")) != _split_links(fields.get("original_cc", "")))
        if edited and not self.allow_recipient_edits:
            raise WriteNotConfigured(
                "the recipient list was changed, which needs a draft-then-send flow and a "
                "wider Mail.ReadWrite grant; send it unchanged, or enable recipient edits "
                "deliberately")
        try:
            self._post("/me/messages/%s/replyAll" % urllib.parse.quote(message_id, safe=""),
                       {"comment": str(fields.get("body") or "")})
        except urllib.error.HTTPError as exc:
            # Status and reason only. The response body and the request headers
            # can both carry the token back.
            return ExecutionResult("outlook.reply_all", False,
                                   "Graph returned HTTP %s %s" % (exc.code, exc.reason))
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return ExecutionResult("outlook.reply_all", False,
                                   "the reply failed to send: %s" % type(exc).__name__)
        return ExecutionResult("outlook.reply_all", True,
                               "replied to %d recipient%s"
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
            raise WriteNotConfigured(
                "%s is not set; the acknowledgement draft fails closed" % OUTLOOK_WRITE_TOKEN_ENV)
        message_id = str(fields.get("message_id") or "")
        if not message_id:
            raise WriteNotConfigured("a reply draft needs the message it is replying to")
        quoted = urllib.parse.quote(message_id, safe="")
        try:
            created = self._post("/me/messages/%s/createReplyAll" % quoted, {})
            draft_id = str((created or {}).get("id") or "")
            if not draft_id:
                return ExecutionResult("outlook.create_draft", False,
                                       "Graph created no draft to write into")
            self._patch("/me/messages/%s" % urllib.parse.quote(draft_id, safe=""),
                        {"body": {"contentType": "text", "content": str(fields.get("body") or "")}})
        except urllib.error.HTTPError as exc:
            return ExecutionResult("outlook.create_draft", False,
                                   "Graph returned HTTP %s %s" % (exc.code, exc.reason))
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return ExecutionResult("outlook.create_draft", False,
                                   "the draft could not be created: %s" % type(exc).__name__)
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
            "this plan changes external systems and has not been approved")
    missing = plan.missing()
    if missing:
        raise IncompleteAction("still missing: %s" % ", ".join(missing))

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
                raise WriteNotConfigured("no document writer supplied")
            # Built here, not at draft time: the ticket number does not exist
            # until the task above has actually been created.
            line = document_line(context.get("ticket_id", ""), resolved.fields.get("title", ""))
            result = document_writer.append_under_heading(
                resolved.target, resolved.fields.get("heading", ""), line)
        elif resolved.kind == "outlook.reply_all":
            if mail_writer is None:
                raise WriteNotConfigured("no mail writer supplied")
            result = mail_writer.send_reply(resolved.fields)
        elif resolved.kind == "outlook.create_draft":
            if mail_writer is None:
                raise WriteNotConfigured("no mail writer supplied")
            result = mail_writer.create_draft(resolved.fields)
        else:
            result = ExecutionResult(resolved.kind, False, "no writer for this action kind")
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
