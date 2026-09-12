"""Fixture-backed, read-only activity and meeting routines."""

from datetime import datetime, timezone
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


def generate_daily_wins(payload: Mapping) -> str:
    """Render only supplied activity facts; impact is explicitly labeled inference."""
    activities = _items(payload, "activities")
    lines = ["# Daily wins recap", "", "Generated %s." % _date(payload), "",
             "## Verified facts"]
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
    lines.extend(facts or ["- No completed activities were supplied."])
    lines.extend(["", "## Inferred impact"])
    lines.extend(inferences or ["- No impact inference supplied; no impact is asserted."])
    lines.extend(["", "## Coverage and limits",
                  "- Source: structured activity fixture only.",
                  "- No activity outside the fixture was inspected; missing evidence is not treated as completion."])
    return "\n".join(lines) + "\n"


def generate_morning_brief(payload: Mapping) -> str:
    """Render meeting preparation without contacting attendees or changing events."""
    meetings = _items(payload, "meetings")
    lines = ["# Morning brief / meeting prep", "", "Generated %s." % _date(payload), ""]
    if not meetings:
        lines.append("No meetings were supplied by the calendar fixture.")
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


# Descriptive aliases keep the public routine names aligned with their contracts.
generate_daily_wins_recap = generate_daily_wins
generate_morning_brief_meeting_prep = generate_morning_brief
