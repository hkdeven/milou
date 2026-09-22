#!/usr/bin/env python3
"""Build the clickable Milou prototype from the real code and the real fixtures.

This is deliberately not a hand-drawn mock-up. Every report in the page is
produced by the routine that produces it in the running application, rendered by
the renderer the web view uses, over the fixtures the test suite runs against. If
a report looks wrong here, it is wrong in the product.

What the prototype adds on top is the shell the application does not have yet —
navigation between routines, and the two actions on an inbox row — so the whole
thing can be walked through before any of it is wired to a live mailbox.

    python3 scripts/build_prototype.py

Writes ``prototypes/milou-app.html``.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from milou_news import render_html
from milou_news.actions import DEFAULT_STATUSES
from milou_news.github_radar import FixtureApi, RadarConfig, build_radar_report
from milou_news.intake import read_email
from milou_news.outlook import FixtureGraph, InboxConfig, build_outlook_report, html_to_text
from milou_news.pipeline import BriefConfig, build_brief_report
from milou_news.routines import build_routine_report
from milou_news.config import SOURCES
from milou_news.sources import FixtureFetcher
from milou_news.sprints import sprint_for, upcoming
from milou_news.zoho import FixtureZoho, ZohoConfig, build_zoho_report, coverage_from
from milou_news.zoho import prepare as prepare_zoho

#: Each fixture was written around its own instant, and a routine reads "3h ago"
#: against the instant it was run at. Using one clock for all of them would make
#: half the prototype render as an empty week, which is a rendering artefact and
#: not something the product does. So each is built at the instant its own tests
#: build it at, and the shell shows that as the routine's last run.
NOW = datetime(2026, 9, 22, 15, 40, tzinfo=timezone.utc)
NEWS_NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
RADAR_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)

#: Placeholders until the portal's real list is supplied. Only the default is
#: fixed; see routines/ticket-from-email.md.
STATUSES = ["Open", "Ready for Development", "In Progress", "In Review",
            "Blocked", "Ready for Release", "Released", "On Hold", "Closed"]
DEFAULT_STATUS = DEFAULT_STATUSES[0]

OWNERS = ["Deven Blackburn (you)", "A. Rivera", "D. Nguyen", "S. Okafor", "M. Castillo"]


def load(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as handle:
        return json.load(handle)


def build_reports():
    """Every routine, built the way the application builds it."""
    views = []

    outlook = load("outlook.json")
    inbox_config = InboxConfig.from_mapping(outlook["config"])
    zoho_fixture = load("zoho.json")
    zoho_config = ZohoConfig.from_mapping(zoho_fixture.get("config", zoho_fixture))
    zoho_api = FixtureZoho(zoho_fixture["responses"], zoho_fixture.get("errors", {}))
    _now, activities, _errors, _count = prepare_zoho(zoho_api, zoho_config, NOW)
    coverage = coverage_from(activities, zoho_config)

    views.append(dict(
        key="inbox", name="Outlook inbox monitor", group="Watching",
        cadence="Every 2 hours", icon="mail", actions=True,
        report=build_outlook_report(FixtureGraph(outlook["responses"]), inbox_config, now=NOW,
                                    coverages=[coverage])))
    views.append(dict(
        key="zoho", name="Zoho Projects radar", group="Watching",
        cadence="Daily · 08:00", icon="ticket",
        report=build_zoho_report(zoho_api, zoho_config, NOW)))

    radar_fixture = load("github-radar.json")
    radar_config = RadarConfig.from_mapping(load("github-radar-config.json"))
    views.append(dict(
        key="github", name="GitHub change radar", group="Watching",
        cadence="Daily · 08:00", icon="code",
        report=build_radar_report(
            FixtureApi(radar_fixture.get("responses", radar_fixture),
                       radar_fixture.get("errors", {})), radar_config, RADAR_NOW)))

    news = load("news.json")
    views.append(dict(
        key="news", name="Daily AI news brief", group="Reading",
        cadence="Daily · 07:00", icon="news",
        report=build_brief_report(SOURCES, FixtureFetcher(news), NEWS_NOW, BriefConfig(limit=5))))

    for key, routine, name, group, cadence, icon, fixture in (
            ("wins", "daily-wins-recap", "Daily wins recap", "Reading",
             "Daily · 18:00", "check", "activity.json"),
            ("brief", "morning-brief-meeting-prep", "Morning brief", "Reading",
             "Weekdays · 07:30", "calendar", "meetings.json"),
            ("commitments", "commitments-follow-up-tracker", "Commitments tracker", "Watching",
             "Daily · 09:00", "clock", "commitments.json"),
            ("stale", "stale-work-finder", "Stale work finder", "Watching",
             "Weekly · Mon", "clock", "stale-work.json"),
            ("dependabot", "dependabot-pr-triage", "Dependabot triage", "Watching",
             "Daily · 08:30", "code", "dependabot.json"),
            ("launch", "launch-decoder", "Launch decoder", "Reading",
             "Daily · 09:00", "news", "launch-decoder.json"),
            ("radar", "launch-radar", "Launch radar", "Reading",
             "Weekly · Tue", "news", "launch-radar.json"),
            ("travel", "travel-logistics-tracker", "Travel logistics", "Reading",
             "On demand", "calendar", "travel-logistics.json")):
        report = build_routine_report(routine, load(fixture))
        if report is not None:
            views.append(dict(key=key, name=name, group=group, cadence=cadence,
                              icon=icon, report=report))
    return views


def actionable(outlook_fixture):
    """The inbox messages the two actions are demonstrated on.

    Drawn from the same fixture the monitor reads, and put through the same
    intake code, so the dialog is pre-filled by the logic that would pre-fill it
    in the product rather than by hand-written sample values.
    """
    inbox_key = next(key for key in outlook_fixture["responses"] if "inbox" in key)
    bodies = {key.split("/")[-1].split("?")[0]: value
              for key, value in outlook_fixture["responses"].items()
              if key.startswith("/me/messages/")}
    mails = []
    for raw in outlook_fixture["responses"][inbox_key]["value"]:
        identifier = raw.get("id")
        # Every row in the report is actionable, as it would be in the product.
        # Where the fixture stores a full body the intake reads that; otherwise
        # it falls back to the preview, exactly as the live action does.
        body = (bodies.get(identifier) or {}).get("body") or {}
        text = str(body.get("content") or raw.get("bodyPreview") or "")
        if str(body.get("contentType") or "").lower() == "html":
            text = html_to_text(text)
        sender = (raw.get("from") or {}).get("emailAddress") or {}
        received = datetime.fromisoformat(
            str(raw["receivedDateTime"]).replace("Z", "+00:00"))
        intake = read_email(raw.get("subject", ""), text,
                            sender_name=sender.get("name", ""), received=received.date())
        mails.append(dict(
            id=identifier, subject=raw.get("subject", ""),
            fromName=sender.get("name", ""), **{"from": sender.get("address", "")},
            to=[entry["emailAddress"]["address"] for entry in raw.get("toRecipients", [])],
            cc=[entry["emailAddress"]["address"] for entry in raw.get("ccRecipients", [])],
            when=received.strftime("%b %d, %H:%M UTC"),
            kind=intake.kind, requested=intake.requested_by,
            reported=intake.reported_by, reportedGuessed="reported_by" in intake.guessed,
            reportedOn=intake.reported_on, reportedOnGuessed="reported_on" in intake.guessed,
            record=intake.record, recordGuessed="record" in intake.guessed,
            context=intake.context, links=list(intake.links),
            url=raw.get("webLink", "")))
    return mails


def mailbox_of(outlook_fixture):
    identity = outlook_fixture["responses"].get("/me") or {}
    return str(identity.get("mail") or identity.get("userPrincipalName") or "")


def main():
    views = build_reports()
    outlook_fixture = load("outlook.json")
    start, tag = sprint_for(NOW.date())
    payload = {
        "now": NOW.strftime("%b %d, %H:%M UTC"),
        "today": NOW.date().isoformat(),
        "you": mailbox_of(outlook_fixture),
        "statuses": STATUSES,
        "defaultStatus": DEFAULT_STATUS,
        "owners": OWNERS,
        "signature": "Deven",
        "project": "",
        "sprint": {"start": start.isoformat(), "tag": tag,
                   "upcoming": [day.isoformat() for day, _name in upcoming(NOW.date(), 4)]},
        "mail": actionable(outlook_fixture),
        "views": [{"key": view["key"], "name": view["name"], "group": view["group"],
                   "cadence": view["cadence"], "icon": view["icon"],
                   "actions": bool(view.get("actions")),
                   "routine": view["report"].routine,
                   "generated": view["report"].generated,
                   "headline": headline(view["report"]),
                   "html": render_html.render_report(view["report"])}
                  for view in views],
    }
    payload["schedule"] = schedule()

    shell = os.path.join(ROOT, "scripts", "prototype_shell.html")
    with open(shell, encoding="utf-8") as handle:
        template = handle.read()
    page = (template
            .replace("/*__APP_STYLES__*/", render_html.STYLES)
            .replace('"__PAYLOAD__"', json.dumps(payload, ensure_ascii=False)))
    target = os.path.join(ROOT, "prototypes", "milou-app.html")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(page)
    print("built %d views, %d actionable messages, %d KB"
          % (len(views), len(payload["mail"]), len(page) // 1024))
    return payload


def schedule():
    """The scheduler's own view of itself, from the committed schedule."""
    rows = []
    for index, routine in enumerate(load("scheduler.json").get("routines", [])):
        cadence = routine.get("cadence", "")
        when = routine.get("at", "")
        rows.append({
            "name": routine.get("name", ""),
            "cadence": ("%s %s" % (cadence, when)).strip(),
            "timezone": routine.get("timezone", ""),
            "enabled": bool(routine.get("enabled", True)),
            "retries": routine.get("retry_limit", 0),
            "source": routine.get("fixture", ""),
            "last": (NOW - timedelta(hours=index + 1)).strftime("%b %d, %H:%M UTC"),
        })
    return rows


def headline(report):
    """The one number the sidebar shows, and whether it should be loud."""
    for kpi in report.kpis:
        if kpi.tone in ("critical", "notable"):
            return {"value": kpi.value, "label": kpi.label, "tone": kpi.tone}
    if report.kpis:
        kpi = report.kpis[0]
        return {"value": kpi.value, "label": kpi.label, "tone": ""}
    return {"value": "", "label": "", "tone": ""}


if __name__ == "__main__":
    main()
