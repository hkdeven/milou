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
    lines = ["# Commitments and follow-up tracker", "", "Generated %s." % _date(payload), "",
             "## Explicit commitments"]
    if rows:
        for owner, commitment, source, age, status, follow_up in rows:
            lines.append("- **Owner:** %s; **Commitment:** %s; **Source:** [%s](%s); **Age:** %d days; **Status/ambiguity:** %s; **Suggested follow-up:** %s" %
                         (owner, commitment, source, source if source.startswith("http") else "#", age, status, follow_up))
    else:
        lines.append("- No explicit commitments detected.")
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
    lines = ["# Stale work finder", "", "Generated %s." % _date(payload), ""]
    for urgency in ("Urgent", "Soon", "Monitor"):
        lines.extend(["## %s" % urgency, *(groups[urgency] or ["- None found."]), ""])
    lines.extend(["## Thresholds", "- Authored PR: 7 days; assigned review: 3 days; assigned issue: 14 days; draft: 30 days.",
                  "## Safety boundary", "- Fixture-backed, read-only triage. No reviews, issues, branches, or PRs were changed."])
    return "\n".join(lines) + "\n"


def generate_dependabot_pr_triage(payload: Mapping) -> str:
    """Classify Dependabot updates without approving or merging them."""
    generated = _parse_date(payload.get("generated_at"), datetime.now(timezone.utc))
    lines = ["# Dependabot PR triage", "", "Generated %s." % _date(payload), ""]
    prs = _items(payload, "pull_requests") or _items(payload, "dependabot_prs")
    if not prs:
        lines.append("No Dependabot pull requests supplied.")
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
