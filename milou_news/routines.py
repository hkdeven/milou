"""Fixture-backed, read-only activity and meeting routines."""

from datetime import datetime, timezone
import re
from typing import Mapping, Sequence


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
