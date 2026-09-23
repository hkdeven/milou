"""Read-only Zoho Projects activity radar.

Most work arrives here as tickets rather than as GitHub changes, and Zoho also
emails a notification for nearly everything it does. This routine watches the
projects directly so the mail becomes redundant, and publishes what it reported
as :class:`~milou_news.coverage.Coverage` so the inbox monitor can suppress the
matching notifications instead of reporting the same event twice.

Comments are the top tier by design: a comment usually needs a response whether
or not it is phrased as a direct question, so it is never demoted for lacking a
question mark.

Access is strictly read-only. Only HTTP GET is issued, a read scope is
sufficient, and the OAuth token is read from the environment, never logged,
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
from typing import List, Mapping, Optional, Sequence, Tuple

from . import explain
from .coverage import Coverage, normalize
from .report import Bar, Kpi, Report, Row, Segment, Signal, Tier, humanize_age
from .render_text import render_markdown

ROUTINE_NAME = "zoho-projects-radar"
API_ROOT = "https://projectsapi.zoho.com"
TOKEN_ENV = "MILOU_ZOHO_TOKEN"

#: Path templates. Zoho's REST surface differs across portal API versions, so
#: these are configuration with documented defaults rather than constants: an
#: operator can correct a path without touching the classifier.
DEFAULT_ENDPOINTS = {
    "projects": "/restapi/portal/{portal}/projects/",
    "activities": "/restapi/portal/{portal}/projects/{project}/activities/",
}

#: Senders whose notifications this radar makes redundant.
DEFAULT_NOTIFICATION_DOMAINS = ("zohoprojects.com", "projects.zoho.com", "zoho.com", "zoho.eu")

_COMMENT = re.compile(r"\bcomment", re.I)
_ASSIGN = re.compile(r"\bassign|\bowner changed", re.I)
_STATUS = re.compile(r"\bstatus|closed|reopen|completed|resolved|in progress", re.I)


@dataclass(frozen=True)
class ZohoConfig:
    portal: str = ""
    projects: Tuple[str, ...] = ()
    me: str = ""
    window_hours: int = 72
    max_items: int = 10
    max_projects: int = 20
    include_own_activity: bool = False
    endpoints: Mapping = None
    notification_domains: Tuple[str, ...] = DEFAULT_NOTIFICATION_DOMAINS

    def endpoint(self, name: str) -> str:
        return (self.endpoints or {}).get(name, DEFAULT_ENDPOINTS[name])

    @classmethod
    def from_mapping(cls, value: Mapping) -> "ZohoConfig":
        value = value or {}
        hours = int(value.get("window_hours", 72))
        items = int(value.get("max_items", 10))
        projects_cap = int(value.get("max_projects", 20))
        if not 1 <= hours <= 744:
            raise ValueError(explain.out_of_range(
                "zoho.window_hours", 1, 744, "It is how far back the radar looks."))
        if not 1 <= items <= 25:
            raise ValueError(explain.out_of_range(
                "zoho.max_items", 1, 25,
                "An uncapped report is the ticket list again."))
        if not 1 <= projects_cap <= 200:
            raise ValueError(explain.out_of_range(
                "zoho.max_projects", 1, 200, "It caps how many projects are read."))
        domains = tuple(str(d).strip().lower() for d in
                        (value.get("notification_domains") or DEFAULT_NOTIFICATION_DOMAINS)
                        if str(d).strip())
        return cls(
            portal=str(value.get("portal") or ""),
            projects=tuple(str(p) for p in (value.get("projects") or ())),
            me=str(value.get("me") or "").strip().lower(),
            window_hours=hours, max_items=items, max_projects=projects_cap,
            include_own_activity=bool(value.get("include_own_activity", False)),
            endpoints=dict(value.get("endpoints") or {}), notification_domains=domains,
        )


@dataclass(frozen=True)
class ZohoResult:
    data: object = None
    error: str = ""


class ZohoApi:
    """Read-only Zoho Projects adapter. Only GET is issued."""

    def __init__(self, token=None, environ=None, timeout=20, root=API_ROOT):
        self.token = token if token is not None else (environ or os.environ).get(TOKEN_ENV)
        self.timeout = timeout
        self.root = root

    def get(self, path: str, doing: str = "reading your Zoho projects") -> ZohoResult:
        if not self.token:
            return ZohoResult(error=explain.missing_token("Zoho Projects", TOKEN_ENV, doing))
        if not path.startswith("/"):
            return ZohoResult(error=explain.internal(
                "a Zoho request was built with the path %r, which is not absolute" % path))
        request = urllib.request.Request(
            self.root + path, method="GET",
            headers={"Authorization": "Zoho-oauthtoken " + self.token,
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return ZohoResult(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            # Status and reason only: never the body or the request headers.
            return ZohoResult(error=explain.http_failure(
                "Zoho Projects", doing, exc.code, exc.reason, TOKEN_ENV,
                "the ZohoProjects read scopes"))
        except urllib.error.URLError as exc:
            return ZohoResult(error=explain.unreachable("Zoho Projects", doing, str(exc.reason)))
        except TimeoutError:
            return ZohoResult(error=explain.timed_out("Zoho Projects", doing, self.timeout))
        except ValueError:
            return ZohoResult(error=explain.unreadable("Zoho Projects", doing))


class FixtureZoho:
    """Deterministic stand-in so the routine is testable without a portal."""

    def __init__(self, responses, errors=None):
        self.responses, self.errors = responses or {}, errors or {}

    def get(self, path: str, doing: str = "") -> ZohoResult:
        if path in self.errors:
            return ZohoResult(error=self.errors[path])
        if path not in self.responses:
            return ZohoResult(error=explain.internal(
                "the test fixture has no Zoho response for %s" % path))
        return ZohoResult(self.responses[path])


@dataclass
class Activity:
    id: str = ""
    project: str = ""
    project_name: str = ""
    kind: str = ""
    action: str = ""
    actor: str = ""
    item_id: str = ""
    item_name: str = ""
    detail: str = ""
    url: str = ""
    when: Optional[datetime] = None
    participants: Tuple[str, ...] = ()

    def involves(self, me: str) -> bool:
        if not me:
            return True
        return any(me in (participant or "").lower() for participant in self.participants)


def _pick(raw: Mapping, *names, default=""):
    for name in names:
        value = raw.get(name)
        if value not in (None, "", [], {}):
            return value
    return default


def _time(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        stamp = float(value)
        # Zoho reports epoch milliseconds in its *_long fields.
        if stamp > 1e11:
            stamp /= 1000.0
        try:
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _people(raw: Mapping) -> Tuple[str, ...]:
    people = []
    for key in ("assignee", "assignee_email", "owner", "owner_name", "owner_email",
                "completed_by", "created_by"):
        value = _pick(raw, key)
        if value:
            people.append(str(value).lower())
    for key in ("followers", "participants", "mentions", "assignees"):
        value = raw.get(key)
        if isinstance(value, list):
            people.extend(str(entry.get("email") or entry.get("name") or entry).lower()
                          if isinstance(entry, Mapping) else str(entry).lower()
                          for entry in value)
    return tuple(person for person in people if person)


def _activity(raw: Mapping, project: str, project_name: str) -> Optional[Activity]:
    if not isinstance(raw, Mapping):
        return None
    when = _time(_pick(raw, "activity_time", "time_long", "last_modified_time",
                       "created_time", "updated_time"))
    if when is None:
        return None
    link = raw.get("link")
    url = ""
    if isinstance(link, Mapping):
        inner = link.get("self")
        url = str((inner or {}).get("url") or "") if isinstance(inner, Mapping) else str(inner or "")
    url = url or str(_pick(raw, "url", "permalink", "web_url"))
    return Activity(
        id=str(_pick(raw, "id", "id_string", "activity_id")),
        project=project, project_name=project_name,
        kind=str(_pick(raw, "activity_for", "module", "type")),
        action=str(_pick(raw, "activity_type", "action", "name", "state")),
        actor=str(_pick(raw, "activity_by", "user", "added_by", "modified_by")).lower(),
        item_id=str(_pick(raw, "item_id", "task_id", "bug_id", "entity_id")),
        item_name=str(_pick(raw, "item_name", "task_name", "title", "subject", "name")),
        detail=" ".join(str(_pick(raw, "content", "description", "comment", "display_text")).split())[:240],
        url=url, when=when, participants=_people(raw),
    )


def _classify(activity: Activity) -> str:
    haystack = "%s %s" % (activity.kind, activity.action)
    if _COMMENT.search(haystack) or _COMMENT.search(activity.detail[:40]):
        return "comment"
    if _ASSIGN.search(haystack):
        return "assigned"
    if _STATUS.search(haystack):
        return "status"
    return "other"


def prepare(api, config: ZohoConfig, now=None):
    """Collect bounded recent activity. Shared by every renderer."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors: List[str] = []
    if not config.portal:
        return now, [], ["no Zoho portal configured; nothing was requested"], 0

    projects: List[Tuple[str, str]] = []
    if config.projects:
        projects = [(str(project), str(project)) for project in config.projects]
    else:
        listed = api.get(config.endpoint("projects").format(portal=config.portal))
        if listed.error:
            errors.append("projects: " + listed.error)
        else:
            values = listed.data.get("projects") if isinstance(listed.data, Mapping) else listed.data
            for raw in (values if isinstance(values, list) else [])[:config.max_projects]:
                if isinstance(raw, Mapping):
                    identifier = str(_pick(raw, "id_string", "id"))
                    if identifier:
                        projects.append((identifier, str(_pick(raw, "name", default=identifier))))

    activities: List[Activity] = []
    for identifier, name in projects[:config.max_projects]:
        result = api.get(config.endpoint("activities").format(
            portal=config.portal, project=identifier))
        if result.error:
            errors.append("project %s: %s" % (name, result.error))
            continue
        values = result.data.get("activities") if isinstance(result.data, Mapping) else result.data
        for raw in values if isinstance(values, list) else []:
            activity = _activity(raw, identifier, name)
            if activity:
                activities.append(activity)
    return now, activities, errors, len(projects)


def _row(activity: Activity, action: str, now: datetime, reasons: Sequence[Signal],
         tone: str) -> Row:
    return Row(
        title=action,
        byline=" · ".join(part for part in (activity.project_name, activity.item_name) if part),
        summary=activity.detail, ago=humanize_age(activity.when, now),
        when=activity.when.strftime("%b %d, %H:%M") if activity.when else "",
        url=activity.url, tone=tone, flags=list(reasons))


def _selected(activities: Sequence[Activity], config: ZohoConfig, now: datetime):
    """Split activity into tiers, counting everything deliberately dropped."""
    cutoff = now - timedelta(hours=config.window_hours)
    skipped: Counter = Counter()
    comments, assigned, status, other = [], [], [], []
    for activity in sorted(activities, key=lambda a: a.when, reverse=True):
        if activity.when < cutoff:
            skipped["outside the %d-hour window" % config.window_hours] += 1
            continue
        if config.me and activity.actor and config.me in activity.actor and not config.include_own_activity:
            skipped["your own activity"] += 1
            continue
        category = _classify(activity)
        mine = activity.involves(config.me)
        if category == "comment":
            # A comment usually needs a response whether or not it is a direct
            # question, so it is never demoted for lacking one.
            comments.append(_row(
                activity, "%s commented on %s" % (activity.actor or "Someone",
                                                  activity.item_name or "an item"),
                now, [Signal("comments usually need a reply" +
                             (" · on your item" if mine else ""))], "critical"))
        elif category == "assigned" and mine:
            assigned.append(_row(activity, "Assigned to you: %s" % (activity.item_name or "an item"),
                                 now, [Signal("assignment change involving you")], "critical"))
        elif category == "status" and mine:
            status.append(_row(activity, "%s on %s" % (activity.action or "Status change",
                                                       activity.item_name or "an item"),
                               now, [Signal("status change on your item")], "notable"))
        elif mine:
            other.append(_row(activity, "%s on %s" % (activity.action or "Activity",
                                                      activity.item_name or "an item"),
                              now, [Signal("activity on your item")], "quiet"))
        else:
            skipped["not involving you"] += 1
    return comments, assigned, status, other, skipped


def build_zoho_report(api, config: ZohoConfig = None, now=None, prepared=None) -> Report:
    config = config or ZohoConfig()
    now, activities, errors, project_count = prepared or prepare(api, config, now)
    comments, assigned, status, other, skipped = _selected(activities, config, now)

    tiers, remaining, overflow = [], config.max_items, 0
    for label, rows, tone, note in (
            ("Comments", comments, "critical", "A comment usually needs a reply"),
            ("Assigned to you", assigned, "critical", "Ownership changed to you"),
            ("Status changes on your items", status, "notable", "Moved without you"),
            ("Other activity on your items", other, "quiet", "No action implied")):
        shown, hidden = rows[:max(remaining, 0)], rows[max(remaining, 0):]
        overflow += len(hidden)
        remaining -= len(shown)
        if shown:
            tier = Tier(label=label, rows=shown, tone=tone, note=note)
            if hidden:
                tier.footnote = "%d more in this tier, held back by the %d-item cap." % (
                    len(hidden), config.max_items)
            tiers.append(tier)

    excluded = sum(skipped.values())
    bars = []
    if skipped:
        ordered = sorted(skipped.items(), key=lambda item: (-item[1], item[0]))
        bars.append(Bar(label="Why activity was excluded", kind="sequential",
                        caption="Counted, never listed",
                        segments=[Segment(name, float(count), str(count), index)
                                  for index, (name, count) in enumerate(ordered)]))
    return Report(
        title="Zoho Projects radar", routine=ROUTINE_NAME,
        generated=now.strftime("%b %d, %H:%M UTC"),
        window="Last %d hours" % config.window_hours,
        scopes=[config.portal or "portal not configured"],
        kpis=[
            Kpi("Comments", str(len(comments)), "usually need a reply",
                "critical" if comments else ""),
            Kpi("Assigned to you", str(len(assigned)), "ownership changed",
                "critical" if assigned else ""),
            Kpi("Status changes", str(len(status)), "on your items",
                "notable" if status else ""),
            Kpi("Projects", str(project_count), "scanned"),
            Kpi("Excluded", str(excluded), "not shown", "coverage" if excluded else ""),
            Kpi("Warnings", str(len(errors)), "access or coverage", "coverage" if errors else ""),
        ],
        bars=bars, tiers=tiers,
        alert=("%d Zoho access problem%s — this report is incomplete"
               % (len(errors), "" if len(errors) == 1 else "s")) if errors else "",
        alert_detail="; ".join(errors),
        boundary=("Read-only Zoho Projects GET only · never comments, closes, reassigns or "
                  "changes a ticket · %d of at most %d items shown%s."
                  % (sum(tier.count for tier in tiers), config.max_items,
                     ", %d held back" % overflow if overflow else "")),
        empty_note=("No Zoho Projects activity in the last %d hours needed you. "
                    "%d project(s) scanned, %d activities excluded."
                    % (config.window_hours, project_count, excluded)),
    )


def coverage_from(activities: Sequence[Activity], config: ZohoConfig = None) -> Coverage:
    """What this radar has reported, so notification mail can be suppressed.

    Only the records actually collected are published. A notification that
    cannot be matched against these is never silently dropped — the inbox
    monitor reports it as a coverage gap instead.
    """
    config = config or ZohoConfig()
    keys, titles = set(), []
    for activity in activities or ():
        for identifier in (activity.item_id, activity.id):
            if identifier and identifier.isdigit():
                keys.add(identifier)
        title = normalize(activity.item_name)
        if len(title) >= 8:
            titles.append(title)
    return Coverage(routine=ROUTINE_NAME, keys=frozenset(keys),
                    titles=tuple(dict.fromkeys(titles)),
                    domains=tuple(config.notification_domains))


def generate_zoho_radar(api, config: ZohoConfig = None, now=None, report: Report = None) -> str:
    return render_markdown(report if report is not None else build_zoho_report(api, config, now))
