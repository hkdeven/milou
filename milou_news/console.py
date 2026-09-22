"""The navigable application: routines on the left, one report at a time.

Until now Milou was a command line and a read-only web view of stored reports.
This is the layer that makes it something you open: it knows which routines
exist, builds any of them on demand, and carries the two inbox actions from a
row through a form to an approved write.

Two rules shape it.

**The console never writes on its own.** It builds plans and renders them. A
write happens only when a request arrives carrying an explicit intent, a named
approver, and a session that is already authenticated; and even then it goes
through the same :mod:`~milou_news.actions` approval boundary as the CLI, with
the same separate write credentials. A console with no write tokens configured
still works — every action reports what it *would* do and says so plainly,
rather than pretending or failing late.

**The forms are server-rendered.** Every recomputation — the description
rewriting itself when a name changes, the reply rewriting itself when a
question is unticked — is a round trip, not a script. That keeps one
implementation of those rules (the Python one) instead of a second copy in the
browser that can drift from it, and it means the application works in any
viewer that can submit a form.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from . import actions as write_actions
from . import render_html
from .actions import (DryRunDocumentWriter, DryRunMailWriter, OutlookReplyWriter,
                      SharePointWordWriter, TicketConfig, ZohoWriter, draft_context_reply,
                      draft_ticket)
from .github_radar import GhApi, RadarConfig, build_radar_report
from .intake import context_questions, intake_from_mapping, read_email
from .outlook import GraphApi, InboxConfig, build_outlook_report, fetch_body, locate_message
from .pipeline import BriefConfig, build_brief_report
from .report import Report
from .routines import build_routine_report
from .config import SOURCES
from .sources import JsonSourceFetcher
from .sprints import upcoming
from .zoho import ZohoApi, ZohoConfig, build_zoho_report, coverage_from
from .zoho import prepare as prepare_zoho

#: Routines that read a system directly, and the order they appear in.
WATCHING = (
    ("outlook-inbox-monitor", "Outlook inbox monitor", "Every 2 hours", "mail"),
    ("zoho-projects-radar", "Zoho Projects radar", "Daily · 08:00", "ticket"),
    ("github-change-radar", "GitHub change radar", "Daily · 08:00", "code"),
    ("commitments-follow-up-tracker", "Commitments tracker", "Daily · 09:00", "clock"),
    ("stale-work-finder", "Stale work finder", "Weekly · Mon", "clock"),
    ("dependabot-pr-triage", "Dependabot triage", "Daily · 08:30", "code"),
)

#: Routines that read the outside world.
READING = (
    ("daily-global-ai-news-brief", "Daily AI news brief", "Daily · 07:00", "news"),
    ("daily-wins-recap", "Daily wins recap", "Daily · 18:00", "check"),
    ("morning-brief-meeting-prep", "Morning brief", "Weekdays · 07:30", "calendar"),
    ("launch-decoder", "Launch decoder", "Daily · 09:00", "news"),
    ("launch-radar", "Launch radar", "Weekly · Tue", "news"),
    ("travel-logistics-tracker", "Travel logistics", "On demand", "calendar"),
)

#: The routine whose rows carry the two actions.
INBOX = WATCHING[0][0]


class UnknownRoutine(Exception):
    """Raised when a request names a routine that does not exist."""


@dataclass
class ConsoleConfig:
    """Everything the console needs that is not code."""

    inbox: InboxConfig = field(default_factory=InboxConfig)
    zoho: ZohoConfig = field(default_factory=ZohoConfig)
    ticket: TicketConfig = field(default_factory=TicketConfig)
    radar: Optional[RadarConfig] = None
    brief: BriefConfig = field(default_factory=BriefConfig)
    owners: Tuple[str, ...] = ()
    approver: str = ""
    #: Whether the operator has granted Mail.ReadWrite as well as Mail.Send.
    #: Editing a reply's recipients needs it, so this is an operator decision
    #: about scope — never inferred from the fact that someone edited the list.
    allow_recipient_edits: bool = False
    #: Payload fixtures for the routines that are fed rather than fetched.
    payloads: Mapping = field(default_factory=dict)

    @property
    def statuses(self) -> Tuple[str, ...]:
        return self.ticket.statuses


class Console:
    """Builds reports and action plans for the web layer.

    Adapters are injected so the whole console can be exercised against
    fixtures; in production they default to the live, read-only clients.
    """

    def __init__(self, config: ConsoleConfig = None, graph=None, zoho=None, fetcher=None,
                 github=None, environ=None):
        self.config = config or ConsoleConfig()
        self.graph = graph if graph is not None else GraphApi(environ=environ)
        self.zoho = zoho if zoho is not None else ZohoApi(environ=environ)
        self.github = github if github is not None else GhApi()
        self.fetcher = fetcher if fetcher is not None else JsonSourceFetcher()
        self.environ = environ if environ is not None else os.environ

    # ---------------------------------------------------------------- views

    def views(self, now: datetime = None) -> List[dict]:
        """The navigation, with each routine's headline number."""
        entries = []
        for group, routines in (("Watching", WATCHING), ("Reading", READING)):
            for key, name, cadence, icon in routines:
                entries.append({"key": key, "name": name, "group": group, "cadence": cadence,
                                "icon": icon, "href": "/routine/" + key,
                                "headline": {}, "actions": key == INBOX})
        return entries

    def report(self, key: str, now: datetime = None) -> Report:
        """Build one routine's report, the way the routine builds it."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        config = self.config
        if key == "outlook-inbox-monitor":
            return build_outlook_report(self.graph, config.inbox, now,
                                        coverages=self._coverages(now))
        if key == "zoho-projects-radar":
            return build_zoho_report(self.zoho, config.zoho, now)
        if key == "github-change-radar":
            if config.radar is None:
                raise UnknownRoutine("the GitHub radar has no configured scope")
            return build_radar_report(self.github, config.radar, now)
        if key == "daily-global-ai-news-brief":
            return build_brief_report(SOURCES, self.fetcher, now, config.brief)
        payload = config.payloads.get(key)
        report = build_routine_report(key, payload) if payload is not None else None
        if report is None:
            raise UnknownRoutine("no routine named %r" % key)
        return report

    def _coverages(self, now):
        """What the Zoho radar demonstrably reported, so mail is not shown twice."""
        if not self.config.zoho.portal:
            return ()
        try:
            _now, activities, _errors, _count = prepare_zoho(self.zoho, self.config.zoho, now)
        except Exception:
            # A radar that cannot be reached must not take the inbox down with
            # it; the inbox simply loses its de-duplication for this run.
            return ()
        return (coverage_from(activities, self.config.zoho),)

    def headline(self, report: Report) -> dict:
        for kpi in report.kpis:
            if kpi.tone in ("critical", "notable"):
                return {"value": kpi.value, "label": kpi.label, "tone": kpi.tone}
        return {}

    # -------------------------------------------------------------- actions

    def message(self, identifier: str):
        """``(mailbox, message)`` for one mailbox item, or ``(mailbox, None)``."""
        return locate_message(self.graph, self.config.inbox, identifier)

    def _body(self, message) -> str:
        """The full body, read only for the message being acted on."""
        return fetch_body(self.graph, message.id) or message.preview

    def ticket_plan(self, identifier: str, form: Mapping = None, now: datetime = None):
        """Draft the ticket, then apply whatever the form has already changed."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        mailbox, message = self.message(identifier)
        if message is None:
            return None, None
        form = form or {}
        plan = draft_ticket(
            self.config.ticket, now.date(), subject=message.subject, sender=message.display,
            received=message.when.strftime("%b %d, %H:%M UTC") if message.when else "",
            body=self._body(message), url=message.url, message_id=message.id,
            received_date=message.when.date() if message.when else now.date())
        edits = {name: form[name] for name in
                 ("title", "status", "owner", "tag", "release_date", "requested_by",
                  "reported_by", "reported_on", "record")
                 if name in form}
        # The composed texts are editable, so the form carries what it showed
        # and the edit is only honoured when it differs. Without that, pressing
        # Refresh would resubmit the composed text and look like an edit, and a
        # real edit would be silently overwritten by the next re-composition —
        # either way the text that was approved is not the text that is written.
        edited_description = _was_edited(form, "description", "composed_description")
        if edited_description is not None:
            edits["description"] = edited_description
        edited_ack = _was_edited(form, "ack_body", "composed_ack")
        if edited_ack is not None:
            edits["body"] = edited_ack
        # The type is a choice, and flipping it changes which fields are
        # required, so it is re-drafted rather than patched.
        chosen = form.get("kind_choice")
        if chosen and chosen != plan.actions[0].fields.get("kind"):
            intake = read_email(message.subject, self._body(message), message.display,
                                message.when.date() if message.when else now.date())
            intake.kind = chosen
            plan = draft_ticket(
                self.config.ticket, now.date(), subject=message.subject, sender=message.display,
                received=message.when.strftime("%b %d, %H:%M UTC") if message.when else "",
                body=self._body(message), url=message.url, message_id=message.id,
                received_date=message.when.date() if message.when else now.date(), intake=intake)
        if "acknowledge" in form and not form.get("acknowledge"):
            plan.actions = [action for action in plan.actions
                            if action.kind != "outlook.create_draft"]
        if edits:
            plan = plan.with_inputs(recompose=edited_description is None, **edits)
        return plan, message

    def reply_plan(self, identifier: str, form: Mapping = None, now: datetime = None):
        """Draft the context reply, then apply the form's edits."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        mailbox, message = self.message(identifier)
        if message is None:
            return None, None, ()
        form = form or {}
        body = self._body(message)
        intake = read_email(message.subject, body, message.display,
                            message.when.date() if message.when else now.date())
        questions = context_questions(intake)
        if "ask" in form:
            wanted = set(form.get("ask") or ())
            for question in questions:
                question.outstanding = question.key in wanted
        plan = draft_context_reply(
            self.config.ticket, subject=message.subject, sender=message.display,
            sender_address=message.sender, to=message.to, cc=message.cc, mailbox=mailbox,
            message_id=message.id, body=body, url=message.url, intake=intake,
            questions=questions,
            received_date=message.when.date() if message.when else now.date())
        edits = {name: form[name] for name in ("to", "cc", "subject") if name in form}
        # The message is composed from the ticks, so an untouched one is left to
        # be recomposed and a hand-edited one is kept exactly as it was written.
        edited_body = _was_edited(form, "body", "composed_body")
        if edited_body is not None:
            edits["body"] = edited_body
        if edits:
            plan = plan.with_inputs(**edits)
        return plan, message, questions

    # -------------------------------------------------------------- writing

    def can_write(self) -> Dict[str, bool]:
        """Which credentials are actually present. Shown, never assumed."""
        return {
            "zoho": bool(self.environ.get(write_actions.ZOHO_WRITE_TOKEN_ENV)),
            "outlook": bool(self.environ.get(write_actions.OUTLOOK_WRITE_TOKEN_ENV)),
            "document": bool(self.environ.get(write_actions.DOCUMENT_WRITE_TOKEN_ENV)),
        }

    def writers(self, allow_recipient_edits: bool = False):
        """Live writers where a credential exists, dry-run writers where none does.

        A missing token is not an error here. It makes the action a rehearsal
        that reports exactly what it would have done, which is the right
        behaviour for a console someone is seeing for the first time.
        """
        available = self.can_write()
        zoho = ZohoWriter(environ=self.environ) if available["zoho"] else _DryRunZoho()
        mail = (OutlookReplyWriter(environ=self.environ,
                                   allow_recipient_edits=allow_recipient_edits)
                if available["outlook"] else DryRunMailWriter())
        document = (SharePointWordWriter(self.config.ticket.document_url, environ=self.environ)
                    if available["document"] and self.config.ticket.document_url
                    else DryRunDocumentWriter())
        return zoho, document, mail

    def create_ticket(self, plan, approver: str):
        zoho, document, mail = self.writers()
        return write_actions.execute(plan.approve(approver), zoho, document, mail_writer=mail)

    def send_reply(self, plan, approver: str):
        _zoho, _document, mail = self.writers(
            allow_recipient_edits=self.config.allow_recipient_edits)
        return write_actions.execute(plan.approve(approver), mail_writer=mail)

    # --------------------------------------------------------------- render

    def sprints(self, now: datetime = None):
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return upcoming(now.date(), 4)


def _was_edited(form: Mapping, field: str, baseline: str):
    """The submitted value, but only when it differs from what was displayed.

    Returns ``None`` when the field was not submitted or still holds the text
    the form rendered, so a composed value can be recomputed freely while a
    hand-edited one is never overwritten.
    """
    if field not in form:
        return None
    supplied = str(form.get(field) or "")
    shown = str(form.get(baseline) or "")
    if baseline not in form:
        return supplied
    return None if supplied.strip() == shown.strip() else supplied


class _DryRunZoho:
    """Stands in for the Zoho writer when no write token is configured."""

    def __init__(self):
        self.created: List[dict] = []

    def create_task(self, portal, project, fields):
        self.created.append(dict(fields))
        # A recognisable, obviously fake number: a rehearsal must never be
        # mistaken for a ticket somebody can go and open.
        return write_actions.ExecutionResult(
            "zoho.create_task", True,
            "dry run: no %s configured, so nothing was created"
            % write_actions.ZOHO_WRITE_TOKEN_ENV,
            {"ticket_id": "0000", "ticket_url": ""})
