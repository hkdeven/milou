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
from typing import Dict, List, Mapping, Tuple

from .report import Kpi, Report, Row, Signal, Tier
from .sprints import sprint_for

#: Write credentials are deliberately separate from the read tokens, so a
#: misconfigured read-only run cannot mutate anything.
ZOHO_WRITE_TOKEN_ENV = "MILOU_ZOHO_WRITE_TOKEN"
ZOHO_API_ROOT = "https://projectsapi.zoho.com"

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

    @property
    def approved(self) -> bool:
        return bool(self.approved_by)

    def missing(self) -> List[str]:
        names = []
        for action in self.actions:
            names.extend(action.missing())
        return sorted(set(names))

    def with_inputs(self, **values) -> "ActionPlan":
        """Return a copy with supplied inputs filled in. Approval is reset."""
        actions = []
        for action in self.actions:
            fields = dict(action.fields)
            for name, value in values.items():
                if name in action.requires and value:
                    fields[name] = str(value)
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
    suggestion = " ".join(kept).strip(" -–—:·,.")
    return suggestion[:1].upper() + suggestion[1:] if suggestion else ""


def describe_source(sender: str, when: str, subject: str, body: str, url: str) -> str:
    """Carry the email's scope and context onto the ticket, with a citation."""
    lines = []
    if body:
        lines.extend([body.strip(), ""])
    lines.append("--- Raised from email ---")
    for label, value in (("From", sender), ("Received", when), ("Subject", subject)):
        if value:
            lines.append("%s: %s" % (label, value))
    if url:
        lines.append("Source: %s" % url)
    return "\n".join(lines).strip()


def document_line(ticket_id: str, title: str) -> str:
    """``1234 - Title`` — the last four digits of the ticket number."""
    digits = re.sub(r"\D", "", str(ticket_id or ""))
    return "%s - %s" % (digits[-4:] if digits else str(ticket_id or "?"), title)


def draft_ticket(config: TicketConfig, today: date, subject: str, sender: str = "",
                 received: str = "", body: str = "", url: str = "",
                 title: str = "") -> ActionPlan:
    """Prepare the ticket and the document line, without performing either."""
    start, tag = sprint_for(today)
    suggestion = shorten(subject)
    heading = config.document_heading.format(sprint=tag, date=start.isoformat())
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
            "tag": tag,
            "release_date": start.isoformat(),
            "description": describe_source(sender, received, subject, body, url),
        },
        requires=("title",), produces=("ticket_id", "ticket_url"),
    )
    record = ProposedAction(
        kind="document.append_line",
        summary="Add one line under the %s heading of the sprint tracker" % tag,
        target=config.document or "document not configured",
        fields={"heading": heading, "title": title or ""},
        requires=("title",),
    )
    return ActionPlan(
        title="Create ticket for the %s" % tag,
        actions=[create, record],
        origin=url or subject,
    )


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
        body = urllib.parse.urlencode({
            "name": fields.get("title", ""),
            "description": fields.get("description", ""),
            "custom_status": fields.get("status", ""),
            "tags": fields.get("tag", ""),
            "end_date": fields.get("release_date", ""),
        }).encode("ascii")
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


def execute(plan: ActionPlan, zoho_writer=None, document_writer=None) -> List[ExecutionResult]:
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
        else:
            result = ExecutionResult(resolved.kind, False, "no writer for this action kind")
        results.append(result)
        context.update(result.produced)
        if not result.ok:
            # Stop rather than record a document line for a ticket that does not
            # exist; a half-applied plan is worse than a refused one.
            break
    return results


def plan_report(plan: ActionPlan, config: TicketConfig, today: date) -> Report:
    """Render a plan for review, in the same structure every report uses."""
    start, tag = sprint_for(today)
    missing = plan.missing()
    rows = []
    for action in plan.actions:
        preview = dict(action.fields)
        if action.kind == "document.append_line":
            preview["line"] = "#### - %s" % (preview.get("title") or "<title>")
        flags = [Signal("%s: %s" % (name, value), "" if value else "notable")
                 for name, value in preview.items()
                 if name != "description" and name not in ("portal", "project")]
        if action.missing():
            flags.append(Signal("waiting on: %s" % ", ".join(action.missing()), "critical"))
        rows.append(Row(title=action.summary, byline=action.target,
                        summary=preview.get("description", ""),
                        tone="critical" if action.missing() else "notable", flags=flags))
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
