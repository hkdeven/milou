"""Read-only Outlook inbox monitor.

This routine exists to replace opening the inbox, not to summarise it. A report
that covers everything is the inbox again — same volume, less scannable, and
untrustworthy because the reader cannot see what was dropped. So the value here
is in what is *refused*: the output is capped, most mail is excluded by explicit
rules, and the exclusions are counted rather than listed.

Access is strictly read-only. Only HTTP GET is issued, `Mail.Read` is
sufficient, and the access token is read from the environment, never logged,
stored, or written into a report.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .coverage import Coverage, find_owner
from .render_text import render_markdown
from .report import Bar, Kpi, Report, Row, Segment, Signal, Tier, humanize_age

ROUTINE_NAME = "outlook-inbox-monitor"
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
TOKEN_ENV = "MILOU_OUTLOOK_TOKEN"

#: Fields requested from Graph. Deliberately narrow: no message body is read.
_SELECT = ("id,conversationId,subject,from,toRecipients,ccRecipients,"
           "receivedDateTime,sentDateTime,bodyPreview,isRead,importance,"
           "inferenceClassification,webLink")

#: Someone states they cannot proceed without the user. Highest cost to miss.
_BLOCKED = re.compile(
    r"\b(?:blocked (?:on|by) you|waiting (?:on|for) (?:you|your)|"
    r"(?:can(?:'|’)?t|cannot|can not|unable to|won(?:'|’)?t be able to) "
    r"(?:proceed|continue|move forward|move ahead|go ahead|start|finish|close)|"
    r"need your (?:approval|sign[- ]?off|decision|go[- ]?ahead|input|confirmation)|"
    r"without your (?:approval|sign[- ]?off|decision|input|response|confirmation)|"
    r"pending your (?:approval|review|response|decision)|awaiting your|"
    r"until (?:you|we hear from you)|hold(?:ing)? (?:this|everything|off) until|"
    r"stuck (?:on|until) you|depends on your (?:approval|decision|response))\b", re.I)

#: An explicit ask directed at the reader.
_ASK = re.compile(
    r"\b(?:could you|can you|would you|please (?:can |could )?(?:you |send|share|review|confirm|advise|approve|sign)|"
    r"any (?:update|chance)|let me know|what(?:'|’)?s the status|when (?:can|will) you|"
    r"do you (?:have|know)|are you able|we need|i need|requesting|request for|"
    r"action required|for your (?:approval|review|signature))\b", re.I)

#: Promise language in the user's own sent mail. Mirrors the commitments routine.
_PROMISE = re.compile(
    r"\b(?:i(?:'|’)?ll|i will|we(?:'|’)?ll|we will|i can have|i(?:'|’)?m going to|"
    r"let me (?:send|share|check|confirm)|will (?:send|share|revert|circle back|follow up|get))\b", re.I)

#: Senders that never warrant a line.
_AUTOMATED = re.compile(
    r"(?:^|[.@+_-])(?:no-?reply|do-?not-?reply|notifications?|notify|alerts?|mailer-daemon|"
    r"postmaster|bounces?|newsletter|marketing|updates|digest|automated|system)(?:[.@+_-]|$)", re.I)


@dataclass(frozen=True)
class InboxConfig:
    """Every threshold is operator-configurable; none is hard-coded."""

    follow_up_days: int = 2
    max_items: int = 8
    lookback_days: int = 14
    max_messages: int = 200
    include_other: bool = False
    mute_senders: Tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping) -> "InboxConfig":
        value = value or {}
        follow_up = int(value.get("follow_up_days", 2))
        items = int(value.get("max_items", 8))
        lookback = int(value.get("lookback_days", 14))
        messages = int(value.get("max_messages", 200))
        if not 1 <= follow_up <= 30:
            raise ValueError("follow_up_days must be 1..30 business days")
        if not 1 <= items <= 25:
            raise ValueError("max_items must be 1..25; an uncapped report is the inbox again")
        if not 1 <= lookback <= 90:
            raise ValueError("lookback_days must be 1..90")
        if not 1 <= messages <= 1000:
            raise ValueError("max_messages must be 1..1000")
        muted = tuple(str(item).strip().lower() for item in (value.get("mute_senders") or ()) if str(item).strip())
        return cls(follow_up, items, lookback, messages, bool(value.get("include_other", False)), muted)


@dataclass(frozen=True)
class GraphResult:
    data: object = None
    error: str = ""
    truncated: bool = False


class GraphApi:
    """Read-only Microsoft Graph adapter.

    Only GET is issued. The bearer token is read from the environment and is
    never logged, echoed into an error, or written to a report.
    """

    def __init__(self, token=None, environ=None, timeout=20, root=GRAPH_ROOT):
        self.token = token if token is not None else (environ or os.environ).get(TOKEN_ENV)
        self.timeout = timeout
        self.root = root

    def get(self, path: str) -> GraphResult:
        if not self.token:
            return GraphResult(error="%s is not set; mailbox access fails closed" % TOKEN_ENV)
        if not path.startswith("/"):
            return GraphResult(error="invalid Graph path")
        request = urllib.request.Request(
            self.root + path, method="GET",
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Status and reason only: never the response body or request headers,
            # which can carry the token back.
            return GraphResult(error="Graph %s returned HTTP %s %s" % (path, exc.code, exc.reason))
        except urllib.error.URLError as exc:
            return GraphResult(error="Graph %s unreachable: %s" % (path, exc.reason))
        except (ValueError, TimeoutError) as exc:
            return GraphResult(error="Graph %s returned an unreadable response: %s"
                               % (path, type(exc).__name__))
        return GraphResult(payload, truncated=bool(payload.get("@odata.nextLink"))
                           if isinstance(payload, Mapping) else False)


class FixtureGraph:
    """Deterministic stand-in so the routine is testable without a mailbox."""

    def __init__(self, responses, errors=None):
        self.responses, self.errors = responses or {}, errors or {}

    def get(self, path: str) -> GraphResult:
        if path in self.errors:
            return GraphResult(error=self.errors[path])
        if path not in self.responses:
            return GraphResult(error="fixture missing Graph path %s" % path)
        return GraphResult(self.responses[path])


@dataclass
class Message:
    id: str = ""
    conversation: str = ""
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    to: Tuple[str, ...] = ()
    to_names: Tuple[str, ...] = ()
    cc: Tuple[str, ...] = ()
    when: Optional[datetime] = None
    preview: str = ""
    classification: str = ""
    importance: str = ""
    url: str = ""
    folder: str = ""

    @property
    def display(self) -> str:
        return self.sender_name or self.sender or "unknown sender"

    @property
    def to_display(self) -> str:
        names = self.to_names or self.to
        if not names:
            return "an unnamed recipient"
        return ", ".join(names[:2]) + (" and %d others" % (len(names) - 2) if len(names) > 2 else "")


def _time(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _address(entry) -> Tuple[str, str]:
    mail = (entry or {}).get("emailAddress") or {} if isinstance(entry, Mapping) else {}
    return str(mail.get("address") or "").lower(), str(mail.get("name") or "")


def _addresses(entries) -> Tuple[str, ...]:
    return tuple(_address(entry)[0] for entry in (entries or []) if _address(entry)[0])


def _display_names(entries) -> Tuple[str, ...]:
    names = []
    for entry in entries or []:
        address, name = _address(entry)
        if address:
            names.append(name or address)
    return tuple(names)


def _sentence_with(pattern, text: str) -> str:
    """The one sentence that triggered a match, rather than a generic preview."""
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        if pattern.search(sentence):
            return sentence.strip()
    return (text or "").strip()


def _message(raw: Mapping, folder: str) -> Optional[Message]:
    if not isinstance(raw, Mapping):
        return None
    sender, sender_name = _address(raw.get("from"))
    when = _time(raw.get("receivedDateTime") if folder == "inbox" else raw.get("sentDateTime"))
    if when is None:
        return None
    return Message(
        id=str(raw.get("id") or ""), conversation=str(raw.get("conversationId") or raw.get("id") or ""),
        subject=str(raw.get("subject") or "(no subject)"), sender=sender, sender_name=sender_name,
        to=_addresses(raw.get("toRecipients")), to_names=_display_names(raw.get("toRecipients")),
        cc=_addresses(raw.get("ccRecipients")),
        when=when, preview=" ".join(str(raw.get("bodyPreview") or "").split())[:240],
        classification=str(raw.get("inferenceClassification") or ""),
        importance=str(raw.get("importance") or ""), url=str(raw.get("webLink") or ""),
        folder=folder)


def business_days_between(start: datetime, end: datetime) -> int:
    """Business days elapsed, so Friday mail is not chased on Sunday."""
    if start is None or end is None or end <= start:
        return 0
    days, cursor, last = 0, start.date(), end.date()
    while cursor < last:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days


def _folder_path(folder: str, config: InboxConfig, order: str) -> str:
    query = urllib.parse.urlencode({
        "$select": _SELECT, "$top": str(config.max_messages), "$orderby": "%s desc" % order})
    return "/me/mailFolders/%s/messages?%s" % (folder, query)


def _collect(api, config: InboxConfig) -> Tuple[str, List[Message], List[Message], List[str], bool]:
    errors: List[str] = []
    identity = api.get("/me")
    mailbox = ""
    if identity.error:
        errors.append("mailbox identity: " + identity.error)
    elif isinstance(identity.data, Mapping):
        mailbox = str(identity.data.get("mail") or identity.data.get("userPrincipalName") or "").lower()

    truncated = False
    folders: Dict[str, List[Message]] = {"inbox": [], "sentitems": []}
    for folder, order in (("inbox", "receivedDateTime"), ("sentitems", "sentDateTime")):
        result = api.get(_folder_path(folder, config, order))
        if result.error:
            errors.append("%s: %s" % ("inbox" if folder == "inbox" else "sent items", result.error))
            continue
        truncated = truncated or result.truncated
        values = result.data.get("value") if isinstance(result.data, Mapping) else result.data
        for raw in values if isinstance(values, list) else []:
            message = _message(raw, "inbox" if folder == "inbox" else "sent")
            if message:
                folders[folder].append(message)
    return mailbox, folders["inbox"], folders["sentitems"], errors, truncated


def _excluded(message: Message, mailbox: str, config: InboxConfig,
              replied: Mapping, cutoff: datetime,
              coverages: Sequence[Coverage] = ()) -> Tuple[str, bool]:
    """Why this message earns no line, and whether it is an unmatched notification.

    Coverage is checked before the automated-sender rule on purpose. A Zoho or
    GitHub notification would otherwise disappear as "automated sender" whether
    or not the routine watching that system actually saw the event, which is
    not de-duplication — it is a silent drop.
    """
    if message.when < cutoff:
        return "older than the %d-day window" % config.lookback_days, False
    if mailbox and message.sender == mailbox:
        return "sent by you", False
    owner = find_owner(coverages, message.sender)
    if owner is not None:
        if owner.matches(message.subject, message.preview, message.url):
            return "already reported by %s" % owner.routine, False
        return "notification from %s not matched to a tracked item" % owner.routine, True
    if _AUTOMATED.search(message.sender):
        return "automated sender", False
    if message.sender in config.mute_senders:
        return "muted sender", False
    if message.classification.lower() == "other" and not config.include_other:
        return "Focused Inbox: other", False
    if mailbox and mailbox not in message.to:
        return "you were only CC'd", False
    replied_at = replied.get(message.conversation)
    if replied_at is not None and replied_at > message.when:
        return "you already replied", False
    return "", False


def _reasons(message: Message, blocked: bool) -> List[Signal]:
    """Say why a line surfaced, so a wrong call is diagnosable."""
    reasons = ["addressed directly to you"]
    reasons.append("states they are blocked" if blocked else "request language detected")
    reasons.append("no reply from you")
    if message.importance.lower() == "high":
        reasons.append("marked high importance")
    # One compact line: these are diagnostics, not findings, and stacking them
    # makes every row taller than the thing it is reporting.
    return [Signal(" · ".join(reasons))]


def _row(message: Message, action: str, ago: str, reasons: Sequence[Signal], tone: str,
         summary: str = None) -> Row:
    return Row(
        title=action, byline="%s · %s" % (message.display, message.subject),
        summary=message.preview if summary is None else summary, ago=ago,
        when=message.when.strftime("%b %d, %H:%M") if message.when else "",
        url=message.url, tone=tone, flags=list(reasons))


def _alert(errors: Sequence[str], gaps: Sequence[str]) -> str:
    """Name the kind of problem: a coverage gap is not an access failure."""
    parts = []
    if errors:
        parts.append("%d mailbox access problem%s" % (len(errors), "" if len(errors) == 1 else "s"))
    if gaps:
        parts.append("%d coverage gap%s" % (len(gaps), "" if len(gaps) == 1 else "s"))
    if not parts:
        return ""
    return " and ".join(parts) + " — this report may be incomplete"


def build_outlook_report(api, config: InboxConfig = None, now=None,
                        coverages: Sequence[Coverage] = ()) -> Report:
    """Build the inbox monitor report.

    Ordering is by consequence: someone blocked on the user, then unanswered
    requests, then the user's own promises, then silent sent mail.
    """
    config = config or InboxConfig()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(days=config.lookback_days)
    mailbox, inbox, sent, errors, truncated = _collect(api, config)

    # Latest reply-from-user per conversation, used to retire answered threads.
    replied: Dict[str, datetime] = {}
    for message in sent:
        current = replied.get(message.conversation)
        if current is None or message.when > current:
            replied[message.conversation] = message.when

    skipped: Counter = Counter()
    unmatched: Counter = Counter()
    candidates: Dict[str, Message] = {}
    for message in sorted(inbox, key=lambda m: m.when, reverse=True):
        reason, gap = _excluded(message, mailbox, config, replied, cutoff, coverages)
        if reason:
            skipped[reason] += 1
            if gap:
                unmatched[message.sender.split("@")[-1]] += 1
            continue
        candidates.setdefault(message.conversation, message)

    blocked_rows, request_rows = [], []
    for message in sorted(candidates.values(), key=lambda m: m.when, reverse=True):
        haystack = "%s %s" % (message.subject, message.preview)
        ago = humanize_age(message.when, now)
        if _BLOCKED.search(haystack):
            blocked_rows.append(_row(
                message, "%s cannot proceed without you" % message.display, ago,
                _reasons(message, True), "critical",
                summary=_sentence_with(_BLOCKED, message.preview)))
        elif _ASK.search(haystack) or "?" in haystack:
            request_rows.append(_row(
                message, "%s is waiting on your reply" % message.display, ago,
                _reasons(message, False), "critical",
                summary=_sentence_with(_ASK, message.preview)))
        else:
            skipped["no request detected"] += 1

    # The user's own promises, and sent mail that has gone quiet.
    #
    # A promise means the user owes the recipient, so it belongs in "You
    # promised" and is never also chased as an unanswered message. Only mail
    # that actually asked something is chased: a thread the user closed with an
    # acknowledgement is not waiting on anybody, and nagging about it is the
    # noise that gets follow-up reminders ignored.
    promises, follow_ups, latest_sent = [], [], {}
    for message in sorted(sent, key=lambda m: m.when, reverse=True):
        if message.when < cutoff or not message.to:
            continue
        latest_sent.setdefault(message.conversation, message)
    for conversation, message in latest_sent.items():
        haystack = "%s %s" % (message.subject, message.preview)
        recipients = message.to_display
        if _PROMISE.search(haystack):
            promises.append(_row(
                message, "You owe %s: %s" % (recipients, message.subject),
                humanize_age(message.when, now),
                [Signal("promise language in your own sent mail")], "notable",
                summary=_sentence_with(_PROMISE, message.preview)))
            continue
        if not (_ASK.search(haystack) or "?" in haystack):
            skipped["sent mail that asked nothing"] += 1
            continue
        if any(other.conversation == conversation and other.when > message.when
               for other in inbox):
            skipped["you already replied"] += 1
            continue
        waiting = business_days_between(message.when, now)
        if waiting < config.follow_up_days:
            skipped["sent too recently to chase"] += 1
            continue
        follow_ups.append(_row(
            message, "%s has not replied: %s" % (recipients, message.subject),
            "%d business day%s" % (waiting, "" if waiting == 1 else "s"),
            [Signal("you asked; nothing received since"),
             Signal("threshold is %d business days" % config.follow_up_days)], "notable",
            summary=_sentence_with(_ASK, message.preview)))

    # Bounded output: a busier inbox must not produce a longer report.
    tiers, remaining, overflow = [], config.max_items, 0
    for label, rows, tone, note in (
            ("Blocked on you", blocked_rows, "critical", "They say they cannot move without you"),
            ("Waiting on your reply", request_rows, "critical", "Addressed to you, asked, unanswered"),
            ("You promised", promises, "notable", "Promise language in your own sent mail"),
            ("No reply yet", follow_ups, "notable",
             "Silent for %d business days or more" % config.follow_up_days)):
        shown, hidden = rows[:max(remaining, 0)], rows[max(remaining, 0):]
        overflow += len(hidden)
        remaining -= len(shown)
        if shown:
            tier = Tier(label=label, rows=shown, tone=tone, note=note)
            if hidden:
                tier.footnote = "%d more in this tier, held back by the %d-item cap." % (
                    len(hidden), config.max_items)
            tiers.append(tier)

    scanned = len(inbox) + len(sent)
    excluded = sum(skipped.values())
    needs_you = len(blocked_rows) + len(request_rows)
    bars = []
    if skipped:
        ordered = sorted(skipped.items(), key=lambda item: (-item[1], item[0]))
        bars.append(Bar(label="Why mail was excluded", kind="sequential",
                        caption="Counted, never listed — so you can tell what the report is not showing",
                        segments=[Segment(name, float(count), str(count), index)
                                  for index, (name, count) in enumerate(ordered)]))
    if truncated:
        errors.append("the mailbox returned more messages than the %d-message cap; "
                      "older mail in this window was not examined" % config.max_messages)
    gaps = ["%d notification(s) from %s did not match anything the covering routine "
            "reported; it may be missing a project, a permission, or a window"
            % (count, domain) for domain, count in sorted(unmatched.items())]

    return Report(
        title="Outlook inbox monitor", routine=ROUTINE_NAME,
        generated=now.strftime("%b %d, %H:%M UTC"),
        window="Last %d days" % config.lookback_days,
        scopes=[mailbox or "mailbox unknown"],
        kpis=[
            Kpi("Needs you", str(needs_you), "blocked or asked",
                "critical" if needs_you else ""),
            Kpi("You promised", str(len(promises)), "in sent mail",
                "notable" if promises else ""),
            Kpi("No reply yet", str(len(follow_ups)),
                "%d+ business days" % config.follow_up_days, "notable" if follow_ups else ""),
            Kpi("Scanned", str(scanned), "messages"),
            Kpi("Excluded", str(excluded), "not shown", "coverage" if excluded else ""),
            Kpi("Warnings", str(len(errors) + len(gaps)), "access or coverage",
                "coverage" if (errors or gaps) else ""),
        ],
        bars=bars, tiers=tiers,
        alert=_alert(errors, gaps), alert_detail="; ".join(errors + gaps),
        boundary=("Read-only Microsoft Graph GET only · never sends, replies, flags, moves, "
                  "archives or marks read · %d of at most %d items shown%s · message bodies "
                  "are not stored."
                  % (sum(tier.count for tier in tiers), config.max_items,
                     ", %d held back" % overflow if overflow else "")),
        empty_note=("Nothing in the last %d days needs you. %d messages scanned, %d excluded."
                    % (config.lookback_days, scanned, excluded)),
    )


def generate_outlook_monitor(api, config: InboxConfig = None, now=None,
                             report: Report = None) -> str:
    """Markdown entry point; pass ``report`` to render an already-built report."""
    return render_markdown(report if report is not None else build_outlook_report(api, config, now))
