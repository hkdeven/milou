"""Bounded, read-only GitHub change radar.

The default scope is Allied-Steel-Buildings organization activity, including
activity not involving the authenticated user. Secondary repositories and
organizations are opt-in. Authentication remains entirely inside ``gh``.
"""

import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping, Optional, Tuple

from .report import Bar, Kpi, Report, Row, Segment, Signal, Tier, humanize_age

RADAR_NAME = "github-change-radar"


def _time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RadarConfig:
    repositories: Tuple[str, ...] = ()
    organizations: Tuple[str, ...] = ("Allied-Steel-Buildings",)
    window_hours: int = 168
    max_repositories_per_org: int = 100
    max_pages: int = 2
    primary_organizations: Tuple[str, ...] = ("Allied-Steel-Buildings",)

    @classmethod
    def from_mapping(cls, value: Mapping) -> "RadarConfig":
        hours = int(value.get("window_hours", 168))
        maximum = int(value.get("max_repositories_per_org", 100))
        pages = int(value.get("max_pages", 2))
        if not 1 <= hours <= 744 or not 1 <= maximum <= 100 or not 1 <= pages <= 5:
            raise ValueError("window_hours must be 1..744, repository cap 1..100, max_pages 1..5")
        repos = tuple(str(item) for item in (value.get("repositories") or ()))
        orgs = tuple(str(item) for item in (value.get("organizations") or ("Allied-Steel-Buildings",)))
        primary = tuple(str(item) for item in (value.get("primary_organizations") or ("Allied-Steel-Buildings",)))
        return cls(repos, orgs, hours, maximum, pages, primary)


@dataclass(frozen=True)
class ApiResult:
    data: object = None
    error: str = ""
    headers: Mapping = None
    pages: int = 1


class GhApi:
    """Safe subprocess adapter: argv is direct and auth stays in gh."""

    def __init__(self, timeout=20):
        self.timeout = timeout

    def get(self, endpoint):
        if not endpoint.startswith("/") or " " in endpoint:
            return ApiResult(error="invalid API endpoint")
        try:
            completed = subprocess.run(
                ["gh", "api", endpoint, "--include", "--header", "Accept: application/vnd.github+json"],
                capture_output=True, text=True, timeout=self.timeout, check=False,
            )
        except FileNotFoundError:
            return ApiResult(error="gh CLI is not installed")
        except subprocess.TimeoutExpired:
            return ApiResult(error="gh api timed out after %ss" % self.timeout)
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            return ApiResult(error="gh api %s failed: %s" % (endpoint, detail or "unknown error"))
        raw = completed.stdout
        body = raw[raw.find("\n\n") + 2:] if "\n\n" in raw else raw
        try:
            return ApiResult(json.loads(body), headers={"raw": raw[:raw.find("\n\n")]})
        except ValueError:
            return ApiResult(error="gh api %s returned invalid JSON" % endpoint)


class FixtureApi:
    def __init__(self, responses, errors=None, metadata=None):
        self.responses, self.errors = responses, errors or {}
        self.metadata = metadata or {}

    def get(self, endpoint):
        if endpoint in self.errors:
            return ApiResult(error=self.errors[endpoint], headers=self.metadata.get(endpoint, {}))
        if endpoint not in self.responses:
            return ApiResult(error="fixture missing endpoint %s" % endpoint)
        value = self.responses[endpoint]
        if isinstance(value, Mapping) and "data" in value:
            return ApiResult(value["data"], headers=value.get("headers", {}), pages=value.get("pages", 1))
        return ApiResult(value, headers=self.metadata.get(endpoint, {}))


def _actor(event, payload, item):
    return str((event.get("actor") or {}).get("login") or
               (payload.get("sender") or {}).get("login") or
               (item.get("user") or {}).get("login") or
               (item.get("author") or {}).get("login") or "unknown")


def _event_row(event, fallback_repo=""):
    event_type = str(event.get("type") or "UnknownEvent")
    payload = event.get("payload") or {}
    repo = (event.get("repo") or {}).get("name") or fallback_repo
    when = _time(event.get("created_at") or payload.get("created_at"))
    if not when:
        return None
    item = payload.get("pull_request") or payload.get("issue") or payload.get("release") or {}
    action = str(payload.get("action") or "")
    names = {"PushEvent": "commit", "CreateEvent": "branch create", "DeleteEvent": "branch delete",
             "PullRequestEvent": "pull request", "IssuesEvent": "issue", "IssueCommentEvent": "issue comment",
             "ReleaseEvent": "release", "PullRequestReviewEvent": "pull request review",
             "WorkflowRunEvent": "workflow/check", "CheckRunEvent": "workflow/check",
             "DeploymentStatusEvent": "workflow/check", "CommitCommentEvent": "commit comment"}
    category = names.get(event_type)
    if not category:
        return None
    committers = []
    if event_type == "PushEvent":
        commits = payload.get("commits") or []
        parts = ["%d commit%s" % (len(commits), "" if len(commits) == 1 else "s")]
        for commit in commits[:5]:
            message = str(commit.get("message") or "").splitlines()
            parts.append("%s by %s: %s" % (str(commit.get("sha", ""))[:8],
                         commit.get("author", {}).get("name") or commit.get("committer", {}).get("name") or "unknown",
                         message[0] if message else "message unavailable"))
        subject = "; ".join(parts)
        branch = payload.get("ref") or ""
    elif event_type in ("CreateEvent", "DeleteEvent"):
        branch = payload.get("ref") or ""
        subject = "%s %s" % (category, branch)
    else:
        branch = ""
        subject = category
        if item.get("title") or item.get("name") or item.get("tag_name"):
            subject += ": " + str(item.get("title") or item.get("name") or item.get("tag_name"))
        if action:
            subject += " [" + action + "]"
    labels = [str(x.get("name")) for x in item.get("labels", []) if isinstance(x, Mapping)]
    reviewers = [str(x.get("login") or x.get("name")) for x in item.get("requested_reviewers", []) if isinstance(x, Mapping)]
    # A commit with no committer block must contribute nothing: stringifying the
    # missing value printed a literal "None" as though it were a name.
    committers = [name for name in
                  (str(x.get("committer", {}).get("name")
                       or x.get("committer", {}).get("email") or "")
                   for x in payload.get("commits", []) if isinstance(x, Mapping))
                  if name]
    status = str(item.get("state") or item.get("status") or payload.get("conclusion") or "")
    url = event.get("html_url") or item.get("html_url") or ""
    risk = ("high" if category in ("branch delete", "workflow/check") and
            (action in ("failure", "failed") or "delete" in category) else
            "notable" if category in ("release", "pull request") and action in ("closed", "merged", "published") else "")
    return {"timestamp": when.isoformat(), "category": category, "repository": str(repo),
            "summary": subject, "url": str(url), "id": str(event.get("id") or ""),
            "author": _actor(event, payload, item), "branch": str(branch), "labels": ", ".join(labels),
            "reviewers": ", ".join(reviewers), "committers": ", ".join(committers),
            "status": status, "risk": risk}


def _collect(api, config):
    errors, rows, telemetry = [], [], []
    identity = api.get("/user")
    login = identity.data.get("login", "") if isinstance(identity.data, Mapping) else ""
    if identity.error:
        errors.append("authenticated user: " + identity.error)
    user_events = api.get("/user/events?per_page=100")
    if user_events.error:
        errors.append("user activity: " + user_events.error)
    else:
        for event in user_events.data if isinstance(user_events.data, list) else []:
            row = _event_row(event)
            if row:
                row["scope"] = "user"
                rows.append(row)
        telemetry.append("user activity pages fetched: %d" % user_events.pages)
    repos = list(config.repositories)
    for org in config.organizations:
        endpoint = "/orgs/%s/repos?per_page=%d&sort=updated" % (org, config.max_repositories_per_org)
        result = api.get(endpoint)
        if result.error:
            errors.append("organization %s: %s" % (org, result.error))
            continue
        telemetry.append("organization %s repository page(s): %d (cap %d)" % (org, result.pages, config.max_repositories_per_org))
        for item in result.data if isinstance(result.data, list) else []:
            if isinstance(item, Mapping) and item.get("full_name"):
                repos.append(str(item["full_name"]))
    seen = set()
    for repo in repos:
        if repo in seen:
            continue
        seen.add(repo)
        result = api.get("/repos/%s/events?per_page=100" % repo)
        if result.error:
            errors.append("repository %s: %s" % (repo, result.error))
            continue
        telemetry.append("repository %s event page(s): %d" % (repo, result.pages))
        for event in result.data if isinstance(result.data, list) else []:
            row = _event_row(event, repo)
            if row:
                row["scope"] = "primary" if repo.split("/")[0] in config.primary_organizations else "configured"
                rows.append(row)
    return login, rows, errors, telemetry, len(seen)


def prepare(api, config, now=None):
    """Collect, window, and de-duplicate. Shared by every renderer.

    Callers that need more than one output format pass the result back in as
    ``prepared`` so a real run never collects from the API twice.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(hours=config.window_hours)
    login, rows, errors, telemetry, repositories_scanned = _collect(api, config)
    unique = {}
    for row in rows:
        if (_time(row["timestamp"]) or now) >= cutoff:
            unique[row["id"] or (row["repository"], row["timestamp"], row["summary"])] = row
    selected = sorted(unique.values(), key=lambda r: r["timestamp"], reverse=True)
    return login, selected, errors, telemetry, repositories_scanned


def generate_github_radar(api, config, now=None, prepared=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    login, selected, errors, telemetry, repositories_scanned = prepared or prepare(api, config, now)
    scope = ", ".join(config.organizations + config.repositories)
    category_counts = Counter(r["category"] for r in selected)
    authors = {r["author"] for r in selected if r["author"] != "unknown"}
    high_risk = [r for r in selected if r["risk"] == "high"]
    lines = ["# GitHub Change Radar", "",
             "## Report KPIs",
             "- **Generated:** %s" % now.isoformat(),
             "- **Window:** last %d hours" % config.window_hours,
             "- **Scope:** %s" % (scope or "none configured"),
             "- **Repositories scanned:** %d" % repositories_scanned,
             "- **Changes by type:** %s" % (", ".join("%s=%d" % x for x in sorted(category_counts.items())) or "none"),
             "- **Contributors/authors:** %d" % len(authors),
             "- **Total findings/items:** %d" % len(selected),
             "- **High-priority:** %d" % len(high_risk),
             "- **High-risk:** %d" % len(high_risk),
             "- **Warnings/failures:** %d" % len(errors),
             "",
             "- **Highest-priority organization:** Allied-Steel-Buildings (all scoped activity, including activity not involving the user)",
             "- **Secondary configured scope:** %s" % scope, "- **Authenticated user:** %s" % (login or "unknown"), ""]
    for heading, kinds in (("Priority: Allied-Steel-Buildings activity", ("primary",)),
                           ("Secondary configured repository activity", ("configured",)),
                           ("Activity involving the authenticated user", ("user",))):
        lines.extend(["## " + heading])
        matches = [r for r in selected if r.get("scope") in kinds]
        if matches:
            for row in matches:
                citation = "[direct citation](%s)" % row["url"] if row["url"].startswith("http") else "direct citation unavailable"
                details = "; ".join(x for x in ("author: " + row["author"], "committer: " + row["committers"],
                                  "branch: " + row["branch"], "reviewers: " + row["reviewers"],
                                  "labels: " + row["labels"], "status: " + row["status"]) if x.split(": ", 1)[1])
                lines.append("- **%s UTC** — `%s` — **%s** — %s%s (%s)." %
                         (row["timestamp"], row["repository"], row["summary"], citation,
                          ("; " + details) if details else "", row["category"]))
            lines.append("")
        else:
            lines.pop()
    if not selected:
        lines.extend(["No activity to report.", "",
                      "## Coverage and warnings",
                      "- No in-window activity was returned by the bounded feeds."])
    repo_counts = Counter(r["repository"] for r in selected)
    author_counts = Counter(r["author"] for r in selected)
    notable = [r for r in selected if r["risk"]]
    if selected:
        lines.extend(["## Summaries and notable/high-risk changes",
                      "- **Per repository counts:** %s" % (", ".join("%s=%d" % x for x in sorted(repo_counts.items())) or "none"),
                      "- **Per author counts:** %s" % (", ".join("%s=%d" % x for x in sorted(author_counts.items())) or "none"),
                      "- **Notable/high-risk:** " + ("; ".join("%s: %s" % (r["risk"], r["summary"]) for r in notable) if notable else "none detected."), ""])
    lines.extend(["## Coverage, pagination, rate limits, and API/permission failures",
                  "- Categories include commits (author/committer/branch/message/link), branch create/delete, PR lifecycle/reviewers/labels/status, issues, releases/tags, workflow/check changes/failures, Dependabot/security events, and repository lifecycle events where GitHub exposes them.",
                  "- No mention filtering is applied; activity is collected by scope and event feed.",
                  "- Pagination: %s; configured maximum pages: %d." % ("; ".join(telemetry) or "no successful pages", config.max_pages),
                  "- Rate-limit headers are surfaced by the authenticated adapter when available; fixture/API did not provide a rate-limit value." if not telemetry else "- Rate-limit visibility depends on headers returned by gh api.",
                  "- Coverage gaps: event feeds are recent and bounded; unsupported event payloads, inaccessible repositories, and unavailable fields remain unknown."])
    lines.append("## API and permission failures")
    lines.extend("- %s" % e for e in errors) if errors else lines.append("- None reported.")
    lines.extend(["", "## Safety boundary", "- Read-only authenticated `gh api` GET calls only; no writes, labels, comments, merges, or notifications.",
                  "- Results outside configured scope/window are unknown."])
    return "\n".join(lines) + "\n"


_FAILED = ("failure", "failed", "error", "timed_out", "cancelled")

#: Risk value -> (tier key, label, note). The ``risk`` field already exists on
#: every row; here it finally decides ordering and weight instead of being
#: reduced to one summary line.
_TIERS = (
    ("high", "critical", "Needs attention", "Failed checks and deleted branches"),
    ("notable", "notable", "Notable", "Merged pull requests, closures and releases"),
    ("", "quiet", "Routine activity", "Commits, branches, comments — no action implied"),
)


def _radar_row(raw: Mapping, now: datetime, tone: str) -> Row:
    """Map one collected event onto the structured row. Empty fields are dropped."""
    owner, _, name = str(raw.get("repository") or "").partition("/")
    when = _time(raw.get("timestamp"))
    signals: List[Signal] = []
    status = str(raw.get("status") or "")
    if status:
        signals.append(Signal(status, "critical" if status.lower() in _FAILED else ""))
    if raw.get("branch"):
        signals.append(Signal(str(raw["branch"])))
    for label in str(raw.get("labels") or "").split(","):
        if label.strip():
            signals.append(Signal(label.strip()))
    def present(value) -> str:
        """Placeholders are not data: they never reach the rendered row."""
        text = str(value or "").strip()
        return "" if text.lower() in ("", "none", "unknown") else text

    byline = []
    for prefix, value in (("", raw.get("author")), ("reviewed by ", raw.get("reviewers")),
                          ("committed by ", raw.get("committers"))):
        text = present(value)
        if text:
            byline.append(prefix + text)
    return Row(
        title=str(raw.get("summary") or ""),
        ago=humanize_age(when, now) if when else "",
        when=when.strftime("%b %d, %H:%M") if when else "",
        owner=owner if name else "",
        source=name or owner,
        category=str(raw.get("category") or ""),
        byline=" · ".join(byline),
        url=str(raw.get("url") or ""),
        tone=tone,
        signals=signals,
    )


def build_radar_report(api, config, now=None, prepared=None) -> Report:
    """Build the structured Change Radar report.

    Same collection as :func:`generate_github_radar`; the difference is that the
    structure survives to the renderer instead of being flattened into prose.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    login, selected, errors, telemetry, repositories_scanned = prepared or prepare(api, config, now)
    counts = Counter(row["category"] for row in selected)
    authors = {row["author"] for row in selected if row["author"] != "unknown"}
    high_risk = [row for row in selected if row["risk"] == "high"]
    notable = [row for row in selected if row["risk"] == "notable"]

    tiers = []
    for risk, tone, label, note in _TIERS:
        rows = [_radar_row(row, now, tone) for row in selected if row["risk"] == risk]
        if rows:
            tiers.append(Tier(label=label, rows=rows, note=note, tone=tone))

    # Magnitude, not identity: one hue stepped light to dark, ordered by count.
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    bars = []
    if ordered:
        bars.append(Bar(
            label="Changes by type",
            kind="sequential",
            segments=[Segment(name, float(count), str(count), index)
                      for index, (name, count) in enumerate(ordered)],
        ))

    scope = ", ".join(config.organizations + config.repositories)
    kpis = [
        Kpi("Changes", str(len(selected)), "in window"),
        Kpi("Repositories", str(repositories_scanned), "scanned"),
        Kpi("Contributors", str(len(authors)), "distinct authors"),
        Kpi("High risk", str(len(high_risk)), "needs attention", "critical"),
        Kpi("Notable", str(len(notable)), "merges & releases", "notable"),
        Kpi("Warnings", str(len(errors)), "API or permission", "coverage" if errors else ""),
    ]
    return Report(
        title="GitHub Change Radar",
        routine=RADAR_NAME,
        generated=now.strftime("%b %d, %H:%M UTC"),
        window="Last %d hours" % config.window_hours,
        scopes=list(config.organizations) + list(config.repositories),
        kpis=kpis,
        bars=bars,
        tiers=tiers,
        alert=("%d API or permission failure%s — this report is incomplete"
               % (len(errors), "" if len(errors) == 1 else "s")) if errors else "",
        alert_detail="; ".join(errors),
        boundary=("Read-only authenticated `gh api` GET calls only · no mention filtering · "
                  "%s · results outside the configured scope and window are unknown."
                  % ("; ".join(telemetry) if telemetry else "no successful pages")),
        empty_note=("Scanned %d repositor%s across %s."
                    % (repositories_scanned, "y" if repositories_scanned == 1 else "ies",
                       scope or "no configured scope")),
    )
