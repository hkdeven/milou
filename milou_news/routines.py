"""Fixture-backed, read-only activity and meeting routines.

Each routine renders twice from one parse: ``generate_*`` returns the stored
Markdown record, and ``build_*_report`` returns the structured
:class:`~milou_news.report.Report` the HTML renderer consumes. The parsing and
the classification are shared, so the two formats cannot disagree about what a
routine found.
"""

from datetime import datetime, timezone
import re
from typing import List, Mapping, Optional

from .report import Bar, Kpi, Report, Row, Segment, Signal, Tier


def _items(payload, key):
    values = payload.get(key, []) if isinstance(payload, Mapping) else []
    return values if isinstance(values, list) else []


def _text(item, key, default=""):
    value = item.get(key, default) if isinstance(item, Mapping) else default
    return str(value) if value is not None else default


def _link(item):
    return _text(item, "url") or _text(item, "link")


def _date(payload):
    value = _text(payload, "generated_at") or datetime.now(timezone.utc).isoformat()
    return value


def _kpis(generated, window, scope, source_count, total, high_priority=0,
          warnings=0, failures=0):
    return [
        "## Report KPIs",
        "- **Generated:** %s" % generated,
        "- **Window:** %s" % window,
        "- **Scope:** %s" % scope,
        "- **Sources:** %d" % source_count,
        "- **Total findings/items:** %d" % total,
        "- **High-priority:** %d" % high_priority,
        "- **Warnings/failures:** %d" % (warnings + failures),
        "",
    ]


def _empty_report(title, generated, window, scope, source_count, warning):
    lines = ["# %s" % title, ""]
    lines.extend(_kpis(generated, window, scope, source_count, 0, warnings=1))
    lines.extend(["No activity to report.", "", "## Coverage and warnings",
                  "- %s" % warning])
    return "\n".join(lines) + "\n"


def generate_daily_wins(payload: Mapping) -> str:
    """Render only supplied activity facts; impact is explicitly labeled inference."""
    activities = _items(payload, "activities")
    generated = _date(payload)
    if not activities:
        return _empty_report("Daily wins recap", generated, "fixture period",
                             "structured activity fixture", 0,
                             "Only the supplied fixture was inspected; missing activity is unknown.")
    lines = ["# Daily wins recap", ""]
    lines.extend(_kpis(generated, "fixture period", "structured activity fixture",
                       len(activities), len(activities)))
    lines.append("## Verified facts")
    facts = []
    inferences = []
    for item in activities:
        title = _text(item, "title") or _text(item, "name") or "Untitled activity"
        status = _text(item, "status")
        evidence = _link(item)
        timestamp = _text(item, "timestamp") or _text(item, "completed_at")
        detail = _text(item, "detail") or _text(item, "description")
        fact = title
        if status:
            fact += " (%s)" % status
        if detail:
            fact += " — %s" % detail
        if timestamp:
            fact += " [%s]" % timestamp
        if evidence:
            fact += " ([evidence](%s))" % evidence
        else:
            fact += " (evidence link not provided)"
        facts.append("- " + fact)
        impact = _text(item, "inferred_impact") or _text(item, "impact")
        if impact:
            inferences.append("- %s — inferred impact: %s" % (title, impact))
    lines.extend(facts)
    if inferences:
        lines.extend(["", "## Inferred impact"])
        lines.extend(inferences)
    lines.extend(["", "## Coverage and limits",
                  "- Source: structured activity fixture only.",
                  "- No activity outside the fixture was inspected; missing evidence is not treated as completion."])
    return "\n".join(lines) + "\n"


def generate_morning_brief(payload: Mapping) -> str:
    """Render meeting preparation without contacting attendees or changing events."""
    meetings = _items(payload, "meetings")
    generated = _date(payload)
    if not meetings:
        return _empty_report("Morning brief / meeting prep", generated, "calendar fixture period",
                             "calendar/meeting fixture", 0,
                             "Only the supplied calendar fixture was inspected; inaccessible calendars are unknown.")
    lines = ["# Morning brief / meeting prep", ""]
    lines.extend(_kpis(generated, "calendar fixture period", "calendar/meeting fixture",
                       len(meetings), len(meetings)))
    for index, meeting in enumerate(meetings, 1):
        title = _text(meeting, "title") or _text(meeting, "name") or "Untitled meeting"
        lines.extend(["## %d. %s" % (index, title)])
        for label, keys in (
            ("When", ("start", "start_time", "scheduled_at")),
            ("Purpose", ("purpose", "description")),
            ("Attendees", ("attendees",)),
        ):
            value = next((meeting.get(key) for key in keys if meeting.get(key)), "")
            if isinstance(value, list):
                value = ", ".join(str(entry) for entry in value)
            lines.append("- **%s:** %s" % (label, value or "Not provided"))
        links = meeting.get("linked_context") or meeting.get("context") or []
        if isinstance(links, str):
            links = [links]
        lines.append("- **Linked context:** %s" % (
            ", ".join("[%s](%s)" % (link, link) for link in links) or "None provided"))
        for label, key in (("Decisions", "decisions"), ("Open questions", "open_questions"),
                           ("Commitments", "commitments")):
            values = meeting.get(key) or []
            if isinstance(values, str):
                values = [values]
            lines.append("- **%s:** %s" % (label, "; ".join(str(value) for value in values) or "None recorded"))
        inaccessible = meeting.get("inaccessible_links") or []
        if isinstance(inaccessible, str):
            inaccessible = [inaccessible]
        lines.append("- **Inaccessible links:** %s" % ("; ".join(str(value) for value in inaccessible) or "None reported"))
        lines.append("")
    lines.extend(["## Safety boundary",
                  "- Read-only preparation from the supplied calendar/meeting fixture.",
                  "- No attendees were contacted and no event was created, edited, accepted, declined, or moved."])
    return "\n".join(lines) + "\n"


def _parse_date(value, fallback):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return fallback


def _age(value, generated):
    return max(0, (_parse_date(value, generated).date() - generated.date()).days * -1)


def generate_commitments_tracker(payload: Mapping) -> str:
    """Find explicit commitments in supplied messages and activities only."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    candidates = _items(payload, "messages") + _items(payload, "activities")
    promise = re.compile(r"\b(?:i['’]?ll|i will|i can|i promise|we['’]?ll|we will|will do|committed to|follow up|send|share|deliver|review)\b", re.I)
    rows = []
    for item in candidates:
        text = _text(item, "text") or _text(item, "body") or _text(item, "content") or _text(item, "detail")
        if not text or not promise.search(text):
            continue
        owner = _text(item, "owner") or _text(item, "author") or _text(item, "sender") or "Unclear owner"
        source = _link(item) or _text(item, "source") or _text(item, "id") or "fixture item"
        age = _age(_text(item, "timestamp") or _text(item, "created_at") or _text(item, "date"), generated)
        status = _text(item, "status") or ("ambiguous" if owner == "Unclear owner" else "open")
        ambiguity = _text(item, "ambiguity")
        if ambiguity:
            status += "; " + ambiguity
        follow_up = _text(item, "suggested_follow_up") or (
            "Clarify owner and due date, then follow up" if owner == "Unclear owner"
            else "Confirm progress and agree a due date")
        rows.append((owner, text, source, age, status, follow_up))
    if not rows:
        return _empty_report("Commitments and follow-up tracker", _date(payload), "fixture period",
                             "messages and activities fixture", len(candidates),
                             "Detection is limited to explicit promise language in the supplied fixture.")
    lines = ["# Commitments and follow-up tracker", ""]
    lines.extend(_kpis(_date(payload), "fixture period", "messages and activities fixture",
                       len(candidates), len(rows)))
    if rows:
        for owner, commitment, source, age, status, follow_up in rows:
            lines.append("- **Owner:** %s; **Commitment:** %s; **Source:** [%s](%s); **Age:** %d days; **Status/ambiguity:** %s; **Suggested follow-up:** %s" %
                         (owner, commitment, source, source if source.startswith("http") else "#", age, status, follow_up))
    lines.extend(["", "## Safety boundary",
                  "- Structured message/activity fixture only; detection is limited to explicit promise language.",
                  "- Read-only: no messages were sent and no commitment was edited."])
    return "\n".join(lines) + "\n"


STALE_THRESHOLDS = {"pr": 7, "review": 3, "issue": 14, "draft": 30}


def generate_stale_work_finder(payload: Mapping) -> str:
    """Group aging GitHub work from fixture records and cite each item."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    groups = {"Urgent": [], "Soon": [], "Monitor": []}
    collections = (
        ("authored_prs", "Authored PR", "pr"),
        ("assigned_reviews", "Assigned review", "review"),
        ("assigned_issues", "Assigned issue", "issue"),
        ("drafts", "Old draft", "draft"),
    )
    for key, label, kind in collections:
        for item in _items(payload, key):
            age = _age(_text(item, "updated_at") or _text(item, "created_at") or _text(item, "submitted_at"), generated)
            threshold = STALE_THRESHOLDS[kind]
            if age < threshold:
                continue
            title = _text(item, "title") or _text(item, "name") or "Untitled work"
            url = _link(item)
            urgency = "Urgent" if age >= threshold * 3 else ("Soon" if age >= threshold * 2 else "Monitor")
            groups[urgency].append("- **%s:** %s — %d days inactive (threshold %d days); [source](%s)" %
                                  (label, title, age, threshold, url or "#"))
    total = sum(len(values) for values in groups.values())
    if not total:
        return _empty_report("Stale work finder", _date(payload), "fixture period",
                             "GitHub work fixture", sum(len(_items(payload, key)) for key, _, _ in collections),
                             "No records met the age thresholds; records outside the fixture were not inspected.")
    lines = ["# Stale work finder", ""]
    lines.extend(_kpis(_date(payload), "fixture period", "GitHub work fixture",
                       sum(len(_items(payload, key)) for key, _, _ in collections), total,
                       high_priority=len(groups["Urgent"])))
    for urgency in ("Urgent", "Soon", "Monitor"):
        if groups[urgency]:
            lines.extend(["## %s" % urgency, *groups[urgency], ""])
    lines.extend(["## Thresholds", "- Authored PR: 7 days; assigned review: 3 days; assigned issue: 14 days; draft: 30 days.",
                  "## Safety boundary", "- Fixture-backed, read-only triage. No reviews, issues, branches, or PRs were changed."])
    return "\n".join(lines) + "\n"


def generate_dependabot_pr_triage(payload: Mapping) -> str:
    """Classify Dependabot updates without approving or merging them."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    prs = _items(payload, "pull_requests") or _items(payload, "dependabot_prs")
    if not prs:
        return _empty_report("Dependabot PR triage", _date(payload), "fixture period",
                             "Dependabot pull-request fixture", 0,
                             "Only supplied dependency updates were inspected; repository access is unknown.")
    urgent_count = sum(1 for item in prs if (_text(item, "security") or _text(item, "severity")).lower() in ("critical", "high"))
    lines = ["# Dependabot PR triage", ""]
    lines.extend(_kpis(_date(payload), "fixture period", "Dependabot pull-request fixture",
                       len(prs), len(prs), high_priority=urgent_count))
    for item in prs:
        title = _text(item, "title") or "Untitled dependency update"
        url = _link(item) or "#"
        security = _text(item, "security") or _text(item, "severity") or "unknown"
        checks = _text(item, "checks") or ("passing" if item.get("checks_passed") is True else "unknown")
        conflict = _text(item, "conflicts") or ("yes" if item.get("mergeable") is False else "no/unknown")
        age = _age(_text(item, "created_at") or _text(item, "updated_at"), generated)
        urgent = security.lower() in ("critical", "high") or "security" in title.lower()
        classification = "Security / urgent" if urgent else ("Review soon" if age >= 14 else "Routine")
        recommendation = "Safe to review checks and diff; do not auto-approve" if checks.lower() in ("passing", "passed", "success") and conflict.lower() in ("no", "none", "no/unknown") else "Needs human investigation before review"
        lines.append("- **%s** ([source](%s)): %s; checks: %s; conflicts: %s; age: %d days; recommendation: %s." %
                     (title, url, classification, checks, conflict, age, recommendation))
    lines.extend(["", "## Safety boundary", "- Fixture-backed recommendation only; no approval, merge, dependency change, or external notification was performed."])
    return "\n".join(lines) + "\n"


# Descriptive aliases keep the public routine names aligned with their contracts.
generate_daily_wins_recap = generate_daily_wins
generate_morning_brief_meeting_prep = generate_morning_brief
generate_commitments_follow_up_tracker = generate_commitments_tracker
generate_stale_work = generate_stale_work_finder
generate_dependabot_triage = generate_dependabot_pr_triage


def _source_line(item):
    source = _link(item) or _text(item, "source")
    return "[source](%s)" % source if source.startswith("http") else (source or "source link not provided")


def generate_launch_decoder(payload: Mapping) -> str:
    """Decode only launch records supplied by the last-24-hour fixture."""
    launches = _items(payload, "launches")
    if not launches:
        return _empty_report("Launch Decoder", _date(payload), "last 24 hours",
                             "launch fixture", 0,
                             "Only the supplied 24-hour fixture was inspected; other launch sources are unknown.")
    lines = ["# Launch Decoder", ""]
    lines.extend(_kpis(_date(payload), "last 24 hours", "launch fixture",
                       len(launches), len(launches)))
    lines.append("## Launches")
    for item in launches:
        name = _text(item, "name") or _text(item, "title") or "Untitled launch"
        summary = _text(item, "summary") or _text(item, "description") or "No plain-language description supplied."
        evidence = _text(item, "evidence") or _text(item, "evidence_url") or _link(item)
        uncertainty = _text(item, "uncertainty") or "None recorded; fixture evidence is limited."
        lines.extend(["### %s" % name, "- **What happened:** %s" % summary,
                      "- **Direct source:** %s" % (_source_line(item)),
                      "- **Evidence:** %s" % (("[evidence](%s)" % evidence) if evidence.startswith("http") else (evidence or "Not provided")),
                      "- **Uncertainty:** %s" % uncertainty, ""])
    lines.extend(["## Safety boundary",
                  "- Fixture-backed, read-only decoding; no launch details were inferred or invented.",
                  "- Records outside the supplied 24-hour fixture are unknown."])
    return "\n".join(lines) + "\n"


def generate_launch_radar(payload: Mapping) -> str:
    """Render upcoming launches relevant to explicitly configured areas."""
    launches = _items(payload, "launches") or _items(payload, "upcoming_launches")
    areas = payload.get("areas") or payload.get("configured_areas") or []
    if isinstance(areas, str):
        areas = [areas]
    if not launches:
        return _empty_report("Launch Radar", _date(payload), "next seven days",
                             "configured areas: %s" % (", ".join(str(area) for area in areas) or "none"),
                             0, "Only configured launch records were inspected; external calendars and feeds are unknown.")
    lines = ["# Launch Radar", ""]
    lines.extend(_kpis(_date(payload), "next seven days",
                       "configured areas: %s" % (", ".join(str(area) for area in areas) or "none"),
                       len(launches), len(launches)))
    lines.extend(["- **Configured areas:** %s" % (", ".join(str(area) for area in areas) or "Not configured"), "",
                  "## Upcoming launches"])
    for item in launches:
        name = _text(item, "name") or _text(item, "title") or "Untitled launch"
        timing = _text(item, "timing") or _text(item, "date") or "Timing not provided"
        relevance = _text(item, "relevance") or _text(item, "area") or "Relevance not provided"
        confidence = _text(item, "confidence") or "unknown"
        unknowns = _text(item, "unknowns") or "None recorded; verify timing and scope."
        lines.append("- **%s:** timing: %s; relevance: %s; source: %s; confidence: %s; unknowns: %s." %
                     (name, timing, relevance, _source_line(item), confidence, unknowns))
    lines.extend(["", "## Safety boundary",
                  "- Read-only weekly radar from supplied records and configured areas.",
                  "- Missing timing, relevance, source, or confidence is reported as unknown; no forecast is asserted."])
    return "\n".join(lines) + "\n"


def generate_travel_logistics_tracker(payload: Mapping) -> str:
    """Create a dated travel brief from structured calendar and message fixtures."""
    generated = _date(payload)
    events = _items(payload, "events") or _items(payload, "calendar")
    messages = _items(payload, "messages")
    logistics = payload.get("logistics") or []
    if isinstance(logistics, str):
        logistics = [logistics]
    open_items = payload.get("open_items") or payload.get("questions") or []
    if isinstance(open_items, str):
        open_items = [open_items]
    substantive = events or messages or logistics or open_items
    if not substantive:
        return _empty_report("Travel Logistics Tracker", generated, "travel fixture period",
                             "calendar and message fixtures", 0,
                             "Only supplied travel fixtures were inspected; booking and itinerary systems are unknown.")
    lines = ["# Travel Logistics Tracker", ""]
    lines.extend(_kpis(generated, "travel fixture period", "calendar and message fixtures",
                       len(events) + len(messages), len(events) + len(messages) + len(logistics) + len(open_items)))
    if events:
        lines.append("## Itinerary")
        for event in events:
            title = _text(event, "title") or _text(event, "name") or "Untitled event"
            when = _text(event, "start") or _text(event, "date") or "Date/time not provided"
            location = _text(event, "location") or "Location not provided"
            lines.append("- **%s:** %s; location: %s; %s." % (when, title, location, _source_line(event)))
    if logistics:
        lines.extend(["", "## Logistics"])
        lines.extend("- %s" % entry for entry in logistics)
    if open_items or messages:
        lines.extend(["", "## Open items and missing information"])
        lines.extend("- %s" % entry for entry in open_items)
    for message in messages:
        text = _text(message, "text") or _text(message, "body") or "Message detail not provided"
        lines.append("- Message note: %s (%s)." % (text, _source_line(message)))
    lines.extend(["", "## Safety boundary",
                  "- Read-only synthesis of supplied calendar and message fixtures; never book, change, or cancel travel.",
                  "- No booking, changing, or cancelling occurred.",
                  "- Missing information remains explicitly unknown."])
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Structured reports
#
# The Markdown renderers above pack every field of a record into one bullet and
# leave classification implicit. These builders keep the classification the
# routine already performs — urgency, severity, provenance — as tiers, so the
# order and weight of a row carry meaning.
# --------------------------------------------------------------------------

#: Tier tones, strongest first. ``critical`` and ``notable`` are reserved state
#: colours; ``quiet`` is the collapsed remainder.
_URGENCY_TONE = {"Urgent": "critical", "Soon": "notable", "Monitor": "quiet"}


def _tier(label, rows, tone="", note=""):
    """A tier, or ``None`` when it has no rows. Empty sections never render."""
    return Tier(label=label, rows=list(rows), tone=tone, note=note) if rows else None


def _tiers(*candidates) -> List[Tier]:
    return [tier for tier in candidates if tier is not None]


def _listed(value) -> List[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [str(entry) for entry in (value or []) if str(entry)]


def _cited(item) -> str:
    """Only a real link becomes a citation; anything else is not a URL."""
    source = _link(item) or _text(item, "source")
    return source if source.startswith(("http://", "https://")) else ""


def _report(title, routine, payload, window, scope, tiers, kpis,
            boundary, empty_note, bars=None) -> Report:
    return Report(
        title=title, routine=routine, generated=_date(payload), window=window,
        scopes=[scope], kpis=kpis, bars=list(bars or []), tiers=tiers,
        boundary=boundary, empty_note=empty_note,
    )


def build_daily_wins_report(payload: Mapping) -> Report:
    """Verified facts and inferred impact stay in separate tiers.

    The distinction is the routine's whole safety claim, so it survives as
    structure rather than as a heading halfway down a page.
    """
    activities = _items(payload, "activities")
    facts, inferences, missing_evidence = [], [], 0
    for item in activities:
        title = _text(item, "title") or _text(item, "name") or "Untitled activity"
        evidence = _cited(item)
        if not evidence:
            missing_evidence += 1
        status = _text(item, "status")
        facts.append(Row(
            title=title,
            when=_text(item, "timestamp") or _text(item, "completed_at"),
            summary=_text(item, "detail") or _text(item, "description"),
            url=evidence,
            signals=[Signal(status)] if status else [],
            flags=[] if evidence else [Signal("Evidence link not provided", "coverage")],
        ))
        impact = _text(item, "inferred_impact") or _text(item, "impact")
        if impact:
            inferences.append(Row(title=title, summary=impact, tone="notable",
                                  flags=[Signal("Inferred, not measured", "notable")]))
    return _report(
        "Daily wins recap", "daily-wins-recap", payload, "fixture period",
        "structured activity fixture",
        _tiers(_tier("Verified facts", facts, "", "Each carries its own evidence link"),
               _tier("Inferred impact", inferences, "notable",
                     "Inference from the same activity — not a measurement")),
        [Kpi("Wins", str(len(facts)), "recorded"),
         Kpi("With evidence", str(len(facts) - missing_evidence), "of %d" % len(facts)),
         Kpi("Inferred", str(len(inferences)), "impact claims", "notable"),
         Kpi("Missing evidence", str(missing_evidence), "unverified",
             "coverage" if missing_evidence else "")],
        "Structured activity fixture only · missing evidence is never treated as completion.",
        "Only the supplied fixture was inspected; missing activity is unknown.")


def build_morning_brief_report(payload: Mapping) -> Report:
    """Meeting prep, with everything a reader must not lose kept as its own signal."""
    meetings = _items(payload, "meetings")
    rows, commitments, questions, inaccessible = [], 0, 0, 0
    for meeting in meetings:
        attendees = meeting.get("attendees")
        flags = []
        for label, key, tone in (("Decision", "decisions", ""),
                                 ("Open question", "open_questions", "notable"),
                                 ("Commitment", "commitments", "notable")):
            for entry in _listed(meeting.get(key)):
                flags.append(Signal("%s: %s" % (label, entry), tone))
                questions += 1 if key == "open_questions" else 0
                commitments += 1 if key == "commitments" else 0
        for entry in _listed(meeting.get("inaccessible_links")):
            flags.append(Signal("Inaccessible link: %s" % entry, "coverage"))
            inaccessible += 1
        context = _listed(meeting.get("linked_context") or meeting.get("context"))
        rows.append(Row(
            title=_text(meeting, "title") or _text(meeting, "name") or "Untitled meeting",
            when=next((_text(meeting, key) for key in ("start", "start_time", "scheduled_at")
                       if _text(meeting, key)), ""),
            summary=_text(meeting, "purpose") or _text(meeting, "description"),
            byline=", ".join(_listed(attendees)),
            url=context[0] if context and context[0].startswith(("http://", "https://")) else "",
            signals=[Signal("%d linked" % len(context))] if context else [],
            flags=flags,
        ))
    return _report(
        "Morning brief / meeting prep", "morning-brief-meeting-prep", payload,
        "calendar fixture period", "calendar/meeting fixture",
        _tiers(_tier("Meetings", rows, "", "Context, decisions and commitments preserved")),
        [Kpi("Meetings", str(len(rows)), "scheduled"),
         Kpi("Commitments", str(commitments), "to carry in", "notable" if commitments else ""),
         Kpi("Open questions", str(questions), "unresolved"),
         Kpi("Inaccessible", str(inaccessible), "links", "coverage" if inaccessible else "")],
        "Read-only preparation · no attendee was contacted and no event was created, "
        "edited, accepted, declined, or moved.",
        "Only the supplied calendar fixture was inspected; inaccessible calendars are unknown.")


def build_commitments_report(payload: Mapping) -> Report:
    """Commitments tiered by how long they have gone unanswered."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    candidates = _items(payload, "messages") + _items(payload, "activities")
    promise = re.compile(r"\b(?:i['’]?ll|i will|i can|i promise|we['’]?ll|we will|will do|committed to|follow up|send|share|deliver|review)\b", re.I)
    ageing, recent, fresh, unclear = [], [], [], 0
    for item in candidates:
        text = _text(item, "text") or _text(item, "body") or _text(item, "content") or _text(item, "detail")
        if not text or not promise.search(text):
            continue
        owner = _text(item, "owner") or _text(item, "author") or _text(item, "sender") or "Unclear owner"
        age = _age(_text(item, "timestamp") or _text(item, "created_at") or _text(item, "date"), generated)
        status = _text(item, "status") or ("ambiguous" if owner == "Unclear owner" else "open")
        ambiguity = _text(item, "ambiguity")
        follow_up = _text(item, "suggested_follow_up") or (
            "Clarify owner and due date, then follow up" if owner == "Unclear owner"
            else "Confirm progress and agree a due date")
        flags = [Signal("Suggested follow-up: " + follow_up)]
        if ambiguity:
            flags.append(Signal("Ambiguity: " + ambiguity, "notable"))
        if owner == "Unclear owner":
            unclear += 1
            flags.append(Signal("No clear owner in the source text", "notable"))
        bucket, tone = ((ageing, "critical") if age >= 7 else
                        (recent, "notable") if age >= 3 else (fresh, "quiet"))
        bucket.append(Row(title=text, byline=owner, ago="%d days" % age, tone=tone,
                          url=_cited(item), signals=[Signal(status)], flags=flags))
    total = len(ageing) + len(recent) + len(fresh)
    return _report(
        "Commitments and follow-up tracker", "commitments-follow-up-tracker", payload,
        "fixture period", "messages and activities fixture",
        _tiers(_tier("Ageing", ageing, "critical", "Open for a week or more"),
               _tier("Recent", recent, "notable", "Three days or more"),
               _tier("New", fresh, "quiet", "Raised in the last three days")),
        [Kpi("Commitments", str(total), "detected"),
         Kpi("Ageing", str(len(ageing)), "a week or more", "critical" if ageing else ""),
         Kpi("Unclear owner", str(unclear), "need clarifying", "notable" if unclear else ""),
         Kpi("Scanned", str(len(candidates)), "messages & activities")],
        "Explicit promise language only · read-only: no message was sent and no "
        "commitment was edited.",
        "Detection is limited to explicit promise language in the supplied fixture.")


def build_stale_work_report(payload: Mapping) -> Report:
    """Aging work, tiered by the urgency the routine already computes."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    groups = {"Urgent": [], "Soon": [], "Monitor": []}
    collections = (("authored_prs", "Authored PR", "pr"),
                   ("assigned_reviews", "Assigned review", "review"),
                   ("assigned_issues", "Assigned issue", "issue"),
                   ("drafts", "Old draft", "draft"))
    scanned = 0
    for key, label, kind in collections:
        for item in _items(payload, key):
            scanned += 1
            age = _age(_text(item, "updated_at") or _text(item, "created_at") or _text(item, "submitted_at"), generated)
            threshold = STALE_THRESHOLDS[kind]
            if age < threshold:
                continue
            urgency = "Urgent" if age >= threshold * 3 else ("Soon" if age >= threshold * 2 else "Monitor")
            groups[urgency].append(Row(
                title=_text(item, "title") or _text(item, "name") or "Untitled work",
                category=label, ago="%d days idle" % age, tone=_URGENCY_TONE[urgency],
                url=_cited(item),
                signals=[Signal("threshold %d days" % threshold)]))
    total = sum(len(rows) for rows in groups.values())
    return _report(
        "Stale work finder", "stale-work-finder", payload, "fixture period",
        "GitHub work fixture",
        _tiers(_tier("Urgent", groups["Urgent"], "critical", "Three times past its threshold"),
               _tier("Soon", groups["Soon"], "notable", "Twice past its threshold"),
               _tier("Monitor", groups["Monitor"], "quiet", "Past its threshold")),
        [Kpi("Stale", str(total), "of %d scanned" % scanned),
         Kpi("Urgent", str(len(groups["Urgent"])), "act now", "critical" if groups["Urgent"] else ""),
         Kpi("Soon", str(len(groups["Soon"])), "act this week", "notable" if groups["Soon"] else ""),
         Kpi("Monitor", str(len(groups["Monitor"])), "watch")],
        "Thresholds: authored PR 7 days · assigned review 3 days · assigned issue 14 days · "
        "draft 30 days. Read-only: nothing was changed.",
        "No records met the age thresholds; records outside the fixture were not inspected.")


def build_dependabot_report(payload: Mapping) -> Report:
    """Dependency updates tiered by security severity, never by recency alone."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    prs = _items(payload, "pull_requests") or _items(payload, "dependabot_prs")
    urgent, soon, routine_rows, blocked = [], [], [], 0
    for item in prs:
        title = _text(item, "title") or "Untitled dependency update"
        security = _text(item, "security") or _text(item, "severity") or "unknown"
        checks = _text(item, "checks") or ("passing" if item.get("checks_passed") is True else "unknown")
        conflict = _text(item, "conflicts") or ("yes" if item.get("mergeable") is False else "no/unknown")
        age = _age(_text(item, "created_at") or _text(item, "updated_at"), generated)
        clean = (checks.lower() in ("passing", "passed", "success")
                 and conflict.lower() in ("no", "none", "no/unknown"))
        if not clean:
            blocked += 1
        is_urgent = security.lower() in ("critical", "high") or "security" in title.lower()
        signals = [Signal(security, "critical" if is_urgent else ""),
                   Signal("checks: " + checks, "" if clean else "critical"),
                   Signal("conflicts: " + conflict)]
        flags = [Signal("Safe to review checks and diff — never auto-approve" if clean
                        else "Needs human investigation before review",
                        "" if clean else "notable")]
        row = Row(title=title, ago="%d days" % age, url=_cited(item), signals=signals, flags=flags)
        if is_urgent:
            row.tone = "critical"
            urgent.append(row)
        elif age >= 14:
            row.tone = "notable"
            soon.append(row)
        else:
            row.tone = "quiet"
            routine_rows.append(row)
    counts = [("security", len(urgent)), ("review soon", len(soon)), ("routine", len(routine_rows))]
    bars = [Bar(label="Updates by classification", kind="sequential",
                segments=[Segment(name, float(count), str(count), index)
                          for index, (name, count) in enumerate(counts) if count])]
    return _report(
        "Dependabot PR triage", "dependabot-pr-triage", payload, "fixture period",
        "Dependabot pull-request fixture",
        _tiers(_tier("Security", urgent, "critical", "Critical or high severity"),
               _tier("Review soon", soon, "notable", "Open two weeks or more"),
               _tier("Routine", routine_rows, "quiet", "Version bumps")),
        [Kpi("Updates", str(len(prs)), "open"),
         Kpi("Security", str(len(urgent)), "critical or high", "critical" if urgent else ""),
         Kpi("Review soon", str(len(soon)), "two weeks or more", "notable" if soon else ""),
         Kpi("Blocked", str(blocked), "failing or conflicted",
             "coverage" if blocked else "")],
        "Recommendation only · no approval, merge, dependency change, or notification "
        "was performed.",
        "Only supplied dependency updates were inspected; repository access is unknown.",
        bars=[bar for bar in bars if bar.segments])


def build_launch_decoder_report(payload: Mapping) -> Report:
    """Launches decoded from the fixture, with uncertainty kept visible."""
    rows, uncertain = [], 0
    for item in _items(payload, "launches"):
        uncertainty = _text(item, "uncertainty")
        evidence = _text(item, "evidence") or _text(item, "evidence_url") or _cited(item)
        flags = []
        if uncertainty:
            uncertain += 1
            flags.append(Signal(uncertainty, "notable"))
        if not evidence.startswith(("http://", "https://")):
            flags.append(Signal("No direct evidence link supplied", "coverage"))
        rows.append(Row(
            title=_text(item, "name") or _text(item, "title") or "Untitled launch",
            summary=_text(item, "summary") or _text(item, "description")
            or "No plain-language description supplied.",
            url=_cited(item), flags=flags))
    return _report(
        "Launch Decoder", "launch-decoder", payload, "last 24 hours", "launch fixture",
        _tiers(_tier("Launches", rows, "", "Decoded from supplied records only")),
        [Kpi("Launches", str(len(rows)), "in window"),
         Kpi("With uncertainty", str(uncertain), "flagged", "notable" if uncertain else "")],
        "Read-only decoding · no launch detail was inferred or invented; records "
        "outside the supplied 24-hour fixture are unknown.",
        "Only the supplied 24-hour fixture was inspected; other launch sources are unknown.")


def build_launch_radar_report(payload: Mapping) -> Report:
    """Upcoming launches, tiered by stated confidence."""
    areas = _listed(payload.get("areas") or payload.get("configured_areas"))
    confident, tentative = [], []
    for item in _items(payload, "launches") or _items(payload, "upcoming_launches"):
        confidence = _text(item, "confidence") or "unknown"
        unknowns = _text(item, "unknowns")
        flags = [Signal("Unknowns: " + unknowns, "notable")] if unknowns else []
        row = Row(
            title=_text(item, "name") or _text(item, "title") or "Untitled launch",
            when=_text(item, "timing") or _text(item, "date") or "Timing not provided",
            byline=_text(item, "relevance") or _text(item, "area") or "Relevance not provided",
            url=_cited(item), signals=[Signal("confidence: " + confidence)], flags=flags)
        if confidence.lower() in ("high", "confirmed"):
            confident.append(row)
        else:
            row.tone = "notable"
            tentative.append(row)
    return _report(
        "Launch Radar", "launch-radar", payload, "next seven days",
        "configured areas: %s" % (", ".join(areas) or "none"),
        _tiers(_tier("Confirmed", confident, "", "Stated high confidence"),
               _tier("Tentative", tentative, "notable", "Lower or unstated confidence")),
        [Kpi("Upcoming", str(len(confident) + len(tentative)), "in window"),
         Kpi("Confirmed", str(len(confident)), "high confidence"),
         Kpi("Tentative", str(len(tentative)), "verify timing", "notable" if tentative else ""),
         Kpi("Areas", str(len(areas)), "configured")],
        "Read-only weekly radar · missing timing, relevance, source, or confidence is "
        "reported as unknown; no forecast is asserted.",
        "Only configured launch records were inspected; external calendars and feeds are unknown.")


def build_travel_logistics_report(payload: Mapping) -> Report:
    """Itinerary, logistics, and what is still missing, kept apart."""
    events = _items(payload, "events") or _items(payload, "calendar")
    messages = _items(payload, "messages")
    logistics = _listed(payload.get("logistics"))
    open_items = _listed(payload.get("open_items") or payload.get("questions"))
    itinerary = [Row(
        title=_text(event, "title") or _text(event, "name") or "Untitled event",
        when=_text(event, "start") or _text(event, "date") or "Date/time not provided",
        byline=_text(event, "location") or "Location not provided",
        url=_cited(event)) for event in events]
    logistics_rows = [Row(title=entry, tone="quiet") for entry in logistics]
    outstanding = [Row(title=entry, tone="notable",
                       flags=[Signal("Unresolved", "notable")]) for entry in open_items]
    outstanding.extend(Row(
        title=_text(message, "text") or _text(message, "body") or "Message detail not provided",
        byline="message note", tone="notable", url=_cited(message)) for message in messages)
    return _report(
        "Travel Logistics Tracker", "travel-logistics-tracker", payload,
        "travel fixture period", "calendar and message fixtures",
        _tiers(_tier("Itinerary", itinerary, "", "Confirmed events from the fixture"),
               _tier("Logistics", logistics_rows, "quiet", "Supplied arrangements"),
               _tier("Open items and missing information", outstanding, "notable",
                     "Unresolved — never assume a booking exists")),
        [Kpi("Events", str(len(itinerary)), "in itinerary"),
         Kpi("Logistics", str(len(logistics_rows)), "arrangements"),
         Kpi("Open items", str(len(outstanding)), "unresolved",
             "notable" if outstanding else "")],
        "Read-only synthesis · never book, change, or cancel travel; missing "
        "information remains explicitly unknown.",
        "Only supplied travel fixtures were inspected; booking and itinerary systems are unknown.")


#: Canonical routine name -> structured builder.
REPORT_BUILDERS = {
    "daily-wins-recap": build_daily_wins_report,
    "morning-brief-meeting-prep": build_morning_brief_report,
    "commitments-follow-up-tracker": build_commitments_report,
    "stale-work-finder": build_stale_work_report,
    "dependabot-pr-triage": build_dependabot_report,
    "launch-decoder": build_launch_decoder_report,
    "launch-radar": build_launch_radar_report,
    "travel-logistics-tracker": build_travel_logistics_report,
}


def build_routine_report(routine: str, payload: Mapping) -> Optional[Report]:
    """Build a structured report for a canonical routine name, if one exists."""
    builder = REPORT_BUILDERS.get(routine)
    return builder(payload) if builder else None
