"""Reading one email well enough to raise a ticket from it.

A ticket description is read by a developer who never saw the email, months
after it was sent. So the description is *composed*, not pasted: who asked, who
actually hit the problem, when they hit it, what is in scope, and which
documents were attached to the thread.

Two of those facts are routinely absent from the email itself. The person
emailing about a bug is usually not the person who reported it, and the date it
was reported is almost never stated. This module therefore does two things it
would be easy to conflate:

1. It **extracts** what the email genuinely says, and marks every extracted
   value as a guess, because a name lifted out of a sentence by a regular
   expression is a suggestion and nothing more.
2. It **names what is missing**, so the gap is visible rather than quietly
   filled in. Those same gaps are what the context reply asks for, which is why
   both live here: the questions are derived from the holes, not from a fixed
   template that asks for things the email already answered.

Nothing here contacts anything. It is text in, structure out.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Mapping, Optional, Sequence, Tuple

#: A defect that already happened, as opposed to work that is being asked for.
KIND_BUG = "bug"
KIND_REQUEST = "request"

_BUG = re.compile(
    r"\b(?:bug|defect|error|errors|crash(?:ed|ing|es)?|broken|breaks?|broke|"
    r"not working|isn(?:'|’)?t working|doesn(?:'|’)?t work|stopped working|"
    r"fail(?:s|ed|ing|ure)?|exception|stack ?trace|traceback|"
    r"wrong (?:value|total|number|result|data)|(?:is|are|was|were) wrong|"
    r"not (?:correct|right)|incorrect|missing data|"
    r"(?:problem|issue|trouble) with|reported (?:that|a|this)|"
    r"can(?:'|’)?t (?:save|submit|log ?in|open|load)|unable to (?:save|submit|log ?in|open|load)|"
    r"regression|reproduc(?:e|ible|ing)|steps to reproduce|"
    r"http (?:4\d\d|5\d\d)|\b(?:404|403|500|502|503) error)\b", re.I)

_REQUEST = re.compile(
    r"\b(?:feature|enhancement|new (?:report|field|screen|module|form)|"
    r"would like|we(?:'|’)?d like|could we (?:have|add)|can we (?:have|add)|"
    r"request(?:ing)? (?:a|an|the)?|please add|add a|ability to|"
    r"nice to have|improvement|change request)\b", re.I)

#: "reported by Jane Smith", "Jane Smith reported", "raised by …", "on behalf of …".
_REPORTER = (
    re.compile(r"\b(?:reported|raised|flagged|logged|submitted|noticed|found|hit)\s+by\s+"
               r"([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,2})"),
    re.compile(r"\bon behalf of\s+([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,2})"),
    re.compile(r"\b(?:our|the)\s+(?:user|customer|client|operator|foreman|estimator)\s+"
               r"([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,2})"),
    re.compile(r"\b([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,2})\s+"
               r"(?:reported|raised|flagged|is seeing|was seeing|is getting|ran into|hit)\b"),
)

#: Date-ish phrases. Captured verbatim; relative ones are resolved separately.
_WHEN = (
    re.compile(r"\b(?:on|since)\s+((?:mon|tues|wednes|thurs|fri|satur|sun)day)\b", re.I),
    re.compile(r"\b(yesterday|today|this morning|last night)\b", re.I),
    re.compile(r"\blast\s+((?:mon|tues|wednes|thurs|fri|satur|sun)day)\b", re.I),
    re.compile(r"\b(?:on|since)\s+(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*"
               r"(?:\s+\d{4})?)\b", re.I),
    re.compile(r"\b(?:on|since)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}"
               r"(?:,?\s+\d{4})?)\b", re.I),
    re.compile(r"\b(?:on|since)\s+(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d+)\s+days?\s+ago\b", re.I),
)

#: Where it happened: a project, a job, or a named record.
_RECORD = (
    re.compile(r"\b(?:project|job|order|record|ticket|module|screen|report)\s+"
               r"(?:named\s+|titled\s+|called\s+)?[\"“']?([A-Z0-9][\w .#/-]{2,48}?)[\"”']?"
               r"(?=[,.;:]|\s+(?:and|but|when|while|which|where)\b|$)"),
    re.compile(r"\b(?:in|on|for)\s+(?:the\s+)?([A-Z][\w .#/-]{2,48}?)\s+"
               r"(?:project|job|module|screen|record)\b"),
)

_LINK = re.compile(r"https?://[^\s<>\"'\]\)]+")
#: Trailing punctuation that belongs to the sentence, not the URL.
_LINK_TAIL = ".,;:!?'\"”’)]}>"

#: Quoted reply chains and signatures. Everything below one of these is history.
_HISTORY = re.compile(
    r"^\s*(?:-{2,}\s*original message\s*-{2,}|_{5,}|-{5,}|"
    r"on .{0,80}\bwrote:\s*$|from:\s.+|sent from my \w+|"
    r"begin forwarded message:)\s*$", re.I | re.M)

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

#: Sentences worth keeping even when the budget is nearly spent: they carry the
#: constraint, not the courtesy.
_LOAD_BEARING = re.compile(
    r"\b(?:must|need|needs|required?|should|deadline|due|by (?:mon|tues|wednes|thurs|fri)day|"
    r"before|blocked|urgent|so that|because|steps|expected|instead|"
    r"scope|spec(?:ification)?|acceptance|criteria)\b", re.I)

_GREETING = re.compile(r"^\s*(?:hi|hey|hello|good (?:morning|afternoon|evening))\b[^.\n]{0,40}[,.!]?\s*",
                       re.I)
_SIGNOFF = re.compile(r"\b(?:thanks|thank you|regards|best|cheers|kind regards|many thanks)\b"
                      r"[,.!]?\s*$", re.I)
#: A sign-off on a line of its own ends the message; the name below it is not
#: context, and left in it reads as part of the last sentence.
_SIGNOFF_BLOCK = re.compile(
    r"^\s*(?:thanks|thank you|thanks again|regards|best|best regards|kind regards|"
    r"many thanks|cheers|sincerely|appreciate it)\s*[,.!]?\s*$", re.I | re.M)


def strip_history(text: str) -> str:
    """Drop quoted reply chains, forwarded headers, and mobile signatures."""
    match = _HISTORY.search(text or "")
    body = (text or "")[:match.start()] if match else (text or "")
    signoff = _SIGNOFF_BLOCK.search(body)
    if signoff:
        body = body[:signoff.start()]
    lines = [line for line in body.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def extract_links(text: str) -> Tuple[str, ...]:
    """Supporting documents shared in the thread, in the order they appear."""
    found: List[str] = []
    for raw in _LINK.findall(text or ""):
        url = raw.rstrip(_LINK_TAIL)
        if url and url not in found:
            found.append(url)
    return tuple(found)


def summarize(text: str, budget: int = 600) -> str:
    """Short, but thoroughly complete: every load-bearing sentence, nothing else.

    Courtesy opens and sign-offs are dropped, then sentences are kept in order
    until the budget is spent — except that a sentence carrying a constraint
    ("must", "before Friday", "steps to reproduce") is kept even when the
    budget is gone, because dropping it is what makes a summary wrong rather
    than merely short.
    """
    body = strip_history(text)
    body = _GREETING.sub("", body)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n{2,}", body) if part.strip()]
    kept, spent = [], 0
    for sentence in sentences:
        flat = " ".join(sentence.split())
        # A link lifted out of an <a href> leaves a space before the full stop
        # it was standing in front of.
        flat = re.sub(r"\s+([,.;:!?])", r"\1", flat)
        if not flat or _SIGNOFF.fullmatch(flat):
            continue
        flat = _SIGNOFF.sub("", flat).strip()
        if not flat:
            continue
        if spent + len(flat) > budget and not _LOAD_BEARING.search(flat):
            continue
        kept.append(flat)
        spent += len(flat) + 1
    return " ".join(kept).strip()


def reference_links(text: str, links: Sequence[str]) -> str:
    """Replace inline URLs with ``[doc 1]`` references into the document list.

    A 120-character SharePoint URL in the middle of a sentence makes the
    sentence unreadable, and the URL itself is already listed below, in full,
    where someone can click it.
    """
    text = text or ""
    # Longest first, so one link that is a prefix of another cannot be replaced
    # inside it and leave a dangling tail.
    for position, link in sorted(enumerate(links, start=1), key=lambda pair: -len(pair[1])):
        text = text.replace(link, "[doc %d]" % position)
    return text


def classify(subject: str, body: str) -> str:
    """Bug or request. Ties go to bug, because a bug needs two extra facts."""
    haystack = "%s\n%s" % (subject or "", strip_history(body))
    bugs = len(_BUG.findall(haystack))
    requests = len(_REQUEST.findall(haystack))
    return KIND_BUG if bugs and bugs >= requests else KIND_REQUEST


def _first(patterns: Sequence, text: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return " ".join(match.group(1).split())
    return ""


def extract_reporter(text: str) -> str:
    """The person who hit the problem, who is usually not the person emailing."""
    return _first(_REPORTER, strip_history(text))


def extract_record(text: str) -> str:
    """The project or record title the problem was encountered in."""
    return _first(_RECORD, strip_history(text))


def resolve_when(phrase: str, received: Optional[date]) -> str:
    """Turn a relative phrase into a date, keeping the original wording.

    "yesterday" on a ticket read three weeks later is worse than no date at
    all, so a relative phrase is resolved against the day the email arrived and
    both are shown: ``yesterday (2026-09-28)``.
    """
    phrase = " ".join((phrase or "").split())
    if not phrase or received is None:
        return phrase
    lowered = phrase.lower()
    resolved: Optional[date] = None
    if lowered in ("today", "this morning"):
        resolved = received
    elif lowered in ("yesterday", "last night"):
        resolved = received - timedelta(days=1)
    elif lowered in _WEEKDAYS:
        wanted = _WEEKDAYS.index(lowered)
        back = (received.weekday() - wanted) % 7 or 7
        resolved = received - timedelta(days=back)
    else:
        digits = re.fullmatch(r"(\d+)", lowered)
        if digits:
            resolved = received - timedelta(days=int(digits.group(1)))
    return "%s (%s)" % (phrase, resolved.isoformat()) if resolved else phrase


def extract_reported_on(text: str, received: Optional[date] = None) -> str:
    """When the problem was reported, resolved to a date where it can be."""
    body = strip_history(text)
    for pattern in _WHEN:
        match = pattern.search(body)
        if match:
            phrase = match.group(1)
            if pattern.pattern.startswith(r"\b(\d+)\s+days"):
                return resolve_when(phrase, received) if received else "%s days ago" % phrase
            return resolve_when(phrase, received)
    return ""


@dataclass
class Intake:
    """What the email said, what was guessed, and what is still unknown."""

    kind: str = KIND_REQUEST
    requested_by: str = ""
    reported_by: str = ""
    reported_on: str = ""
    record: str = ""
    context: str = ""
    links: Tuple[str, ...] = ()
    #: Field names whose value came from a regular expression, not a statement.
    guessed: Tuple[str, ...] = ()

    @property
    def is_bug(self) -> bool:
        return self.kind == KIND_BUG

    def required(self) -> Tuple[str, ...]:
        """Fields a description cannot be composed without, for this kind."""
        if self.is_bug:
            return ("requested_by", "reported_by", "reported_on")
        return ("requested_by",)

    def unknown(self) -> List[str]:
        return [name for name in self.required() if not str(getattr(self, name, "")).strip()]


def read_email(subject: str, body: str, sender_name: str = "",
               received: Optional[date] = None) -> Intake:
    """Derive the ticket's narrative fields from one email."""
    kind = classify(subject, body)
    haystack = "%s\n%s" % (subject or "", body or "")
    reporter = extract_reporter(haystack) if kind == KIND_BUG else ""
    when = extract_reported_on(haystack, received) if kind == KIND_BUG else ""
    record = extract_record(haystack)
    guessed = [name for name, value in (("reported_by", reporter), ("reported_on", when),
                                        ("record", record)) if value]
    links = extract_links(body)
    return Intake(
        kind=kind,
        requested_by=(sender_name or "").strip(),
        reported_by=reporter, reported_on=when, record=record,
        context=summarize(reference_links(body, links)), links=links,
        guessed=tuple(guessed),
    )


def _unknown_marker(field_name: str) -> str:
    return "(not stated in the email — ask, or fill in before creating)"


def compose_description(intake: Intake, subject: str = "", sender: str = "",
                        received: str = "", url: str = "") -> str:
    """The ticket description, composed to a fixed shape.

    The shape is fixed on purpose: a developer opening any ticket knows where
    the requester is, where the reproduction details are, and where the
    supporting documents are, without reading the whole thing.
    """
    lines: List[str] = []
    lines.append("Type: %s" % ("Bug report" if intake.is_bug else "Feature / change request"))
    lines.append("Requested by: %s" % (intake.requested_by or _unknown_marker("requested_by")))
    if intake.is_bug:
        lines.append("Reported by: %s" % (intake.reported_by or _unknown_marker("reported_by")))
        lines.append("Reported on: %s" % (intake.reported_on or _unknown_marker("reported_on")))
    if intake.record:
        lines.append("Project / record: %s" % intake.record)
    lines.extend(["", "Context", "-------", intake.context or "(the email carried no description)"])
    lines.extend(["", "Supporting documents", "--------------------"])
    if intake.links:
        lines.extend("- %s" % link for link in intake.links)
    else:
        lines.append("- none shared in the email")
    lines.extend(["", "--- Raised from email ---"])
    for label, value in (("From", sender), ("Received", received), ("Subject", subject)):
        if value:
            lines.append("%s: %s" % (label, value))
    if url:
        lines.append("Source: %s" % url)
    return "\n".join(lines).strip()


@dataclass
class Question:
    """One thing the context reply asks for."""

    key: str
    text: str
    #: False when the email already answered it, so asking again is noise.
    outstanding: bool = True


def context_questions(intake: Intake) -> List[Question]:
    """What to ask the thread for, derived from what is actually missing."""
    who = ("the person who reported it" if intake.is_bug
           else "the person who requested it")
    questions = [
        Question("reported_by" if intake.is_bug else "requested_by",
                 "The full name of %s." % who,
                 not (intake.reported_by if intake.is_bug else intake.requested_by)),
        Question("record",
                 "The project name or record title where it was %s."
                 % ("encountered" if intake.is_bug else "needed"),
                 not intake.record),
    ]
    if intake.is_bug:
        questions.append(Question("reported_on", "The date it was first reported or noticed.",
                                  not intake.reported_on))
    questions.append(Question(
        "documents",
        "If you have any documentation, scope, screenshots or specifications, "
        "please attach those as well.",
        not intake.links))
    return questions


def compose_reply(intake: Intake, questions: Sequence[Question] = None,
                  signature: str = "", subject: str = "") -> str:
    """The pre-composed request for the details a ticket needs.

    Only outstanding questions are asked. A reply that asks for something the
    sender already told you is how a template teaches people to skim past it.
    """
    questions = list(questions if questions is not None else context_questions(intake))
    asked = [question for question in questions if question.outstanding]
    opening = ("Thanks for flagging this. Before I raise it as a ticket, could you fill in a "
               "few details for me?" if intake.is_bug else
               "Thanks for this. Before I raise it as a ticket, could you fill in a few details "
               "for me?")
    numbered = [question for question in asked if question.key != "documents"]
    lines = ["Hi all,", ""]
    if numbered:
        lines.extend([opening, ""])
        for index, question in enumerate(numbered, start=1):
            lines.append("%d. %s" % (index, question.text))
        if any(question.key == "documents" for question in asked):
            lines.extend(["", next(question.text for question in asked
                                   if question.key == "documents")])
    else:
        # Everything was found — but found by pattern-matching a sentence, which
        # is a guess. Confirming a guess is a smaller ask than answering a
        # question they already answered, and it catches the wrong name.
        lines.extend(["Thanks — I think I have everything I need to raise this as a ticket. "
                      "Can you confirm I have it right?", ""])
        for label, value in (("Reported by" if intake.is_bug else "Requested by",
                              intake.reported_by if intake.is_bug else intake.requested_by),
                             ("Reported on", intake.reported_on if intake.is_bug else ""),
                             ("Project / record", intake.record)):
            if value:
                lines.append("- %s: %s" % (label, value))
        lines.extend(["", "If anything else is documented — scope, screenshots, "
                          "specifications — please attach that as well."])
    lines.extend(["", "Once I have that, I will raise the ticket and send you the number.", ""])
    lines.append("Thanks,")
    lines.append(signature or "")
    return "\n".join(line for line in lines).rstrip()


#: Full month names, for a date a customer reads rather than a machine parses.
_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December")


def long_date(value) -> str:
    """``2026-09-30`` → ``30 September 2026``. Unparseable input is passed through."""
    if isinstance(value, date):
        return "%d %s %d" % (value.day, _MONTH_NAMES[value.month - 1], value.year)
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return str(value or "")
    return "%d %s %d" % (parsed.day, _MONTH_NAMES[parsed.month - 1], parsed.year)


def compose_acknowledgement(ticket_reference: str = "{ticket_id}", release_date: str = "",
                            sprint_tag: str = "", signature: str = "",
                            is_bug: bool = False) -> str:
    """Tell the thread the ticket exists, and how to follow it without asking you.

    The point of the number is that it replaces you as the status channel. So
    the message says where to look, and states the release date as the **latest**
    it should take — a date given without that qualifier is read as a promise
    for that exact day, and then chased on it.
    """
    lines = [
        "Hi all,",
        "",
        "Thanks — this is now raised as ticket #%s, and we are looking into it." % ticket_reference,
        "",
        "You are welcome to follow it directly. The development work, the release it goes into "
        "and the change log are all recorded against that ticket number, so you can check "
        "progress there at any time rather than waiting for an update from me.",
        "",
    ]
    if release_date:
        lines.append("Expected release date: %s%s."
                     % (long_date(release_date),
                        " (the %s)" % sprint_tag if sprint_tag else ""))
        lines.append("That is when we are aiming to have this %s at the very latest. If it lands "
                     "sooner, the ticket will show it before I do."
                     % ("resolved" if is_bug else "delivered"))
        lines.append("")
    lines.extend(["Thanks,", signature or ""])
    return "\n".join(lines).rstrip()


def reply_all_recipients(sender: str, to: Sequence[str], cc: Sequence[str],
                         mailbox: str = "") -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Reply-all, minus the user's own address, in Outlook's order.

    The sender leads ``To``; everyone else the message was addressed to follows.
    The user is removed from both lists: a reply that copies you is a reply you
    have to file twice.
    """
    mailbox = (mailbox or "").strip().lower()

    def clean(addresses, seen):
        kept = []
        for address in addresses or ():
            address = (address or "").strip().lower()
            if not address or address == mailbox or address in seen:
                continue
            seen.add(address)
            kept.append(address)
        return kept

    seen = set()
    primary = clean([sender], seen) + clean(to, seen)
    copied = clean(cc, seen)
    return tuple(primary), tuple(copied)


def reply_subject(subject: str) -> str:
    text = (subject or "").strip()
    return text if re.match(r"^\s*re\s*:", text, re.I) else "Re: %s" % (text or "(no subject)")


def intake_from_mapping(value: Mapping) -> Intake:
    """Rebuild an intake from user-edited values, for re-composing a description."""
    value = value or {}
    return Intake(
        kind=str(value.get("kind") or KIND_REQUEST),
        requested_by=str(value.get("requested_by") or ""),
        reported_by=str(value.get("reported_by") or ""),
        reported_on=str(value.get("reported_on") or ""),
        record=str(value.get("record") or ""),
        context=str(value.get("context") or ""),
        links=tuple(str(link) for link in (value.get("links") or ())),
        guessed=tuple(str(name) for name in (value.get("guessed") or ())),
    )
