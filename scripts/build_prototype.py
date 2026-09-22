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
from milou_news.actions import (DEFAULT_STATUSES, TicketConfig, draft_context_reply,
                                draft_ticket, shorten)
from milou_news.github_radar import FixtureApi, RadarConfig, build_radar_report
from milou_news.intake import context_questions, read_email
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
            context=intake.context, links=list(intake.links), body=text,
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
            .replace("/*__APP_STYLES__*/", render_html.STYLES + render_html.APP_STYLES)
            .replace('"__PAYLOAD__"', json.dumps(payload, ensure_ascii=False)))
    target = os.path.join(ROOT, "prototypes", "milou-app.html")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(page)
    flat = flat_page(views, payload)
    flat_target = os.path.join(ROOT, "prototypes", "milou-flat.html")
    with open(flat_target, "w", encoding="utf-8") as handle:
        handle.write(flat)
    print("built %d views, %d actionable messages · app %d KB · flat %d KB"
          % (len(views), len(payload["mail"]), len(page) // 1024, len(flat) // 1024))
    return payload


FLAT_STYLES = """
.flat{max-width:1100px;margin:0 auto;padding:40px 20px 90px;display:flex;flex-direction:column;gap:34px}
@media(max-width:640px){.flat{padding:26px 14px 60px}}
.flat h1{margin:0;font-size:34px;font-weight:600;letter-spacing:-.025em}
.flat h2{margin:0;font-size:21px;font-weight:600;letter-spacing:-.02em}
.lede{margin:0;font-size:15.5px;line-height:1.6;color:var(--ink-2);max-width:72ch}
.eyebrow{margin:0;font-size:10.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
.toc{padding:20px 22px;border-radius:20px;display:flex;flex-wrap:wrap;gap:8px}
.toc a{display:inline-flex;align-items:center;height:30px;padding:0 13px;border-radius:999px;
  background:rgba(255,255,255,.9);border:1px solid var(--hair);font-size:12.5px;color:var(--ink-2)}
.sec{display:flex;flex-direction:column;gap:14px}
.sec-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.sec-head .cad{font-size:12.5px;color:var(--ink-3)}
.sheet{background:rgba(255,255,255,.86);border:1px solid var(--edge);border-radius:24px;
  box-shadow:var(--spec),var(--lift);display:flex;flex-direction:column;overflow:hidden}
.sheet-head{padding:20px 24px 15px;border-bottom:1px solid var(--hair)}
.sheet-body{padding:20px 24px;display:flex;flex-direction:column;gap:16px}
.sheet-foot{padding:15px 24px 19px;border-top:1px solid var(--hair);display:flex;
  align-items:center;gap:12px;flex-wrap:wrap}
.field{display:flex;flex-direction:column;gap:6px;min-width:0}
.field-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.field-row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
@media(max-width:600px){.field-row,.field-row-3{grid-template-columns:1fr}}
.lbl{font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3);
  display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.val{font-size:14px;color:var(--ink-1);background:rgba(255,255,255,.92);border:1px solid var(--hair);
  border-radius:12px;padding:10px 12px;min-height:40px;white-space:pre-wrap;overflow-wrap:anywhere}
.val.mono{font-family:var(--mono);font-size:12.5px;line-height:1.6;color:var(--ink-2)}
.val.empty{color:var(--ink-3)}
.hint{font-size:11.5px;color:var(--ink-3)}
.tag{display:inline-flex;align-items:center;height:18px;padding:0 7px;border-radius:999px;
  font-size:9.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}
.tag-sug{background:var(--note-tint);border:1px solid var(--note-edge);color:var(--note)}
.tag-req{background:var(--crit-tint);border:1px solid var(--crit-edge);color:var(--crit)}
.tag-gue{background:var(--cov-tint);border:1px solid var(--cov-edge);color:var(--cov)}
.tag-ok{background:rgba(12,163,12,.12);border:1px solid rgba(14,107,51,.24);color:var(--pos)}
.tag-auto{background:rgba(0,0,0,.05);border:1px solid var(--hair);color:var(--ink-3)}
.warn{display:flex;align-items:flex-start;gap:11px;padding:12px 15px;border-radius:14px;
  background:rgba(255,255,255,.74);border:1px solid var(--note-edge)}
.warn-ok{border-color:rgba(14,107,51,.24)}
.warn b{display:block;font-size:12.5px;color:var(--note)}
.warn-ok b{color:var(--pos)}
.warn span{font-size:11.5px;color:var(--ink-3)}
.fake-btn{display:inline-flex;align-items:center;height:32px;padding:0 14px;border-radius:999px;
  font-size:12.5px;font-weight:500;background:var(--ink-1);color:#fff}
.fake-btn.ghost{background:rgba(255,255,255,.9);color:var(--ink-2);border:1px solid var(--hair)}
.opts{display:flex;flex-wrap:wrap;gap:6px}
.opt{display:inline-flex;align-items:center;height:26px;padding:0 11px;border-radius:999px;
  background:rgba(255,255,255,.72);border:1px solid var(--hair);font-size:12px;color:var(--ink-3)}
.opt.on{background:#fff;border-color:rgba(22,87,217,.3);color:#1657D9;font-weight:600}
.ask{display:flex;align-items:flex-start;gap:10px;font-size:13px;line-height:1.45}
.box{flex:0 0 auto;width:15px;height:15px;margin-top:3px;border-radius:4px;border:1.5px solid var(--ink-3)}
.box.on{background:#1657D9;border-color:#1657D9}
.ask .sub{display:block;font-size:11px;color:var(--ink-3);margin-top:2px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-size:10.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;
  color:var(--ink-3);padding:0 12px 9px 0;border-bottom:1px solid var(--hair)}
td{padding:10px 12px 10px 0;border-bottom:1px solid var(--hair-2);color:var(--ink-2);vertical-align:top}
td b{color:var(--ink-1);font-weight:600}
tr:last-child td{border-bottom:0}
.panel{padding:24px 26px;display:flex;flex-direction:column;gap:14px}
"""


#: What each badge says, so the caller names the meaning rather than the colour.
_TAG_TEXT = {"tag-sug": "suggested", "tag-req": "required", "tag-gue": "guessed",
             "tag-ok": "not sent", "tag-auto": "automatic"}


def _e(value):
    return render_html._e(value)


def _val(value, mono=False, placeholder="— not stated in the email"):
    classes = "val" + (" mono" if mono else "") + ("" if value else " empty")
    return '<div class="%s">%s</div>' % (classes, _e(value if value else placeholder))


def _field(label, value, tag="", hint="", mono=False, placeholder="—", span=False):
    return ('<div class="field"%s><span class="lbl">%s%s</span>%s%s</div>'
            % (' style="grid-column:1/-1"' if span else "", _e(label),
               (' <span class="tag %s">%s</span>' % (tag, _TAG_TEXT.get(tag, tag))) if tag else "",
               _val(value, mono, placeholder),
               '<span class="hint">%s</span>' % _e(hint) if hint else ""))


def _options(values, selected):
    return '<div class="opts">%s</div>' % "".join(
        '<span class="opt%s">%s</span>' % (" on" if value == selected else "", _e(value))
        for value in values)


def ticket_sheet(mail, config):
    """The Create-ticket dialog, filled in by the code that fills it in."""
    plan = draft_ticket(config, NOW.date(), subject=mail["subject"], sender=mail["fromName"],
                        received=mail["when"], body=mail["body"], url=mail["url"],
                        message_id=mail["id"], received_date=NOW.date())
    create = plan.actions[0].fields
    is_bug = create["kind"] == "bug"
    suggestion = shorten(mail["subject"])
    missing = [name for name in plan.missing() if name != "title"]

    bug_fields = ""
    if is_bug:
        bug_fields = (
            _field("Reported by", create["reported_by"],
                   "tag-gue" if create["reported_by"] else "tag-req",
                   placeholder="required — ask for it") +
            _field("Reported on", create["reported_on"],
                   "tag-gue" if create["reported_on"] else "tag-req",
                   placeholder="required — ask for it"))

    return ('<div class="sheet"><div class="sheet-head">'
            '<p class="eyebrow">New Zoho ticket</p>'
            '<h2 style="margin-top:6px">Zoho project <span class="tag tag-req">not configured</span></h2>'
            '<p class="hint" style="margin-top:6px">From <b>%s</b> · %s · %s</p></div>'
            '<div class="sheet-body">'
            '<div class="warn"><div><b>Nothing is created until you press Create</b>'
            '<span>Three things happen in order: the Zoho task, one line in the sprint tracker, '
            'then an unsent draft reply. The first failure stops the rest.</span></div></div>'
            '%s'
            '<div class="field"><span class="lbl">Status <span class="tag tag-auto">default selected</span></span>%s'
            '<span class="hint">Your portal\'s full list, from configuration.</span></div>'
            '<div class="field-row">%s%s</div>'
            '<div class="field"><span class="lbl">Type <span class="tag tag-gue">detected</span></span>%s'
            '<span class="hint">%s</span></div>'
            '<div class="field-row-3">%s%s</div>'
            '%s'
            '%s'
            '%s'
            '</div>'
            '<div class="sheet-foot"><span class="hint">%s</span>'
            '<span style="flex:1 1 auto"></span>'
            '<span class="fake-btn ghost">Cancel</span>'
            '<span class="fake-btn">Create ticket</span></div></div>'
            % (_e(mail["fromName"]), _e(mail["subject"]), _e(mail["when"]),
               _field("Title", suggestion, "tag-sug",
                      "Keep it extremely brief. Read by people who never saw the email.",
                      span=True),
               _options(STATUSES, config.ready_status),
               _field("Owner", "Unassigned — the sprint is the queue", "tag-auto",
                      "At Ready for Development the sprint is the queue."),
               _field("Project / record", create["record"],
                      "tag-gue" if create["record"] else "tag-auto", placeholder="— optional"),
               _options(["Bug report", "Feature / change"],
                        "Bug report" if is_bug else "Feature / change"),
               "A bug needs a reporter and a report date. Both are required before it can be "
               "created." if is_bug else "A change request needs only the requester.",
               _field("Requested by", create["requested_by"], "tag-auto"), bug_fields,
               _field("Sprint tag", create["tag"], "tag-auto",
                      "Today is Tuesday — developers pick this up tomorrow.", span=True)
               + _field("Expected release date", create["release_date"], "tag-auto",
                        "Matches the sprint.", span=True),
               _field("Description", create["description"], "tag-auto",
                      "Composed from the fields above. Edit a field and it rewrites itself.",
                      mono=True, span=True),
               _field("Acknowledgement draft", plan.actions[2].fields["body"], "tag-auto",
                      "The ticket number does not exist yet, so it is a placeholder here and is "
                      "substituted the moment Zoho allocates one.", mono=True, span=True)
               if len(plan.actions) > 2 else "",
               ("waiting on: " + ", ".join(missing) + " · ask for them with “Ask for context”")
               if missing else "ready · unassigned · " + config.ready_status))


def reply_sheet(mail, config):
    """The Ask-for-context dialog, filled in by the code that fills it in."""
    plan = draft_context_reply(
        config, subject=mail["subject"], sender=mail["fromName"], sender_address=mail["from"],
        to=mail["to"], cc=mail["cc"], mailbox=mail["mailbox"], message_id=mail["id"],
        body=mail["body"], received_date=NOW.date(), url=mail["url"])
    fields = plan.actions[0].fields
    intake = read_email(mail["subject"], mail["body"], mail["fromName"], NOW.date())
    asks = "".join(
        '<div class="ask"><span class="box%s"></span><span>%s<span class="sub">%s</span></span></div>'
        % (" on" if question.outstanding else "", _e(question.text),
           _e("missing — this is why the ticket cannot be created yet" if question.outstanding
              else "the email already gave this"))
        for question in context_questions(intake))

    return ('<div class="sheet"><div class="sheet-head">'
            '<p class="eyebrow">Reply to the thread</p>'
            '<h2 style="margin-top:6px">Ask for the missing context</h2>'
            '<p class="hint" style="margin-top:6px">Replying to <b>%s</b> · %s</p></div>'
            '<div class="sheet-body">'
            '<div class="warn"><div><b>Nothing is sent until you press Send</b>'
            '<span>This goes out from your mailbox, in your name, to everyone listed below.</span>'
            '</div></div>'
            '%s%s%s'
            '<div class="field"><span class="lbl">What to ask for '
            '<span class="tag tag-auto">ticked = still missing</span></span>'
            '<div class="val" style="display:flex;flex-direction:column;gap:10px">%s</div></div>'
            '%s</div>'
            '<div class="sheet-foot"><span class="hint">%d recipient(s) · asking for %s</span>'
            '<span style="flex:1 1 auto"></span>'
            '<span class="fake-btn ghost">Cancel</span>'
            '<span class="fake-btn">Send reply</span></div></div>'
            % (_e(mail["fromName"]), _e(mail["subject"]),
               _field("To", ", ".join(fields["to"].splitlines()), "tag-auto",
                      "Everyone on the thread except you. Sending this list as-is needs only "
                      "Mail.Send.", span=True),
               _field("Cc", ", ".join(fields["cc"].splitlines()), "", placeholder="— nobody",
                      span=True),
               _field("Subject", fields["subject"], "", span=True),
               asks,
               _field("Message", fields["body"], "tag-auto",
                      "Composed from the ticks above.", mono=True, span=True),
               len(fields["to"].splitlines()),
               fields["asking_for"] or "nothing outstanding"))


def flat_page(views, payload):
    """A version with no JavaScript at all.

    iPadOS renders a downloaded .html in Quick Look, which draws the CSS but
    refuses to run scripts — so the app version opens and then does nothing. This
    one has nothing to run: every routine is stacked on one scrolling page, and
    the two dialogs are shown filled in, in place.
    """
    config = TicketConfig.from_mapping({
        "statuses": STATUSES, "signature": payload["signature"], "document": "Sprint tracker"})
    by_id = {mail["id"]: dict(mail, mailbox=payload["you"]) for mail in payload["mail"]}
    bug = by_id.get("m10") or list(by_id.values())[0]
    request = by_id.get("m2") or list(by_id.values())[-1]

    toc = "".join('<a href="#%s">%s</a>' % (view["key"], _e(view["name"])) for view in views)
    sections = "".join(
        '<section class="sec" id="%s"><div class="sec-head"><h2>%s</h2>'
        '<span class="cad">%s · last run %s</span></div>%s</section>'
        % (view["key"], _e(view["name"]), _e(view["cadence"]), _e(view["report"].generated),
           render_html.render_report(view["report"]))
        for view in views)

    rows = "".join(
        '<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
        % (_e(item["name"]), _e(item["cadence"]), _e(item["timezone"] or "—"),
           _e(item["last"]), "enabled" if item["enabled"] else "paused")
        for item in payload["schedule"])

    body = (
        '<div class="flat">'
        '<header style="display:flex;flex-direction:column;gap:12px">'
        '<p class="eyebrow">Milou · prototype, flat version</p>'
        '<h1>Every routine, on one page</h1>'
        '<p class="lede">The same reports as the app version, stacked instead of navigated, with '
        'the two inbox actions shown filled in. Nothing on this page runs, so it renders anywhere '
        'that can draw a web page — including a file opened straight from the Files app on an '
        'iPad, which will not execute scripts.</p></header>'
        '<div class="glass-soft toc">%s<a href="#actions">The two actions</a>'
        '<a href="#scheduler">Scheduler</a></div>'
        '%s'
        '<section class="sec" id="actions"><div class="sec-head"><h2>The two actions</h2>'
        '<span class="cad">on every actionable inbox row</span></div>'
        '<p class="lede">Every field below was filled in by the code that fills it in — the sprint '
        'rule, the composed description, the reporter and date pulled out of the email, and which '
        'questions the reply asks. In the app these are modal sheets; here they are shown open.</p>'
        '%s%s</section>'
        '<section class="sec" id="scheduler"><div class="sec-head"><h2>Scheduler</h2></div>'
        '<div class="glass panel"><table><thead><tr><th>Routine</th><th>Cadence</th>'
        '<th>Timezone</th><th>Last run</th><th>State</th></tr></thead><tbody>%s</tbody></table>'
        '</div></section>'
        '<section class="sec"><div class="sec-head"><h2>What is real here</h2></div>'
        '<div class="glass panel"><p class="lede">Every report above is produced by the routine '
        'that produces it in the running application, rendered by the renderer the web view uses, '
        'over the fixtures the test suite runs against. If a report looks wrong here, it is wrong '
        'in the product.</p>'
        '<p class="lede">The sample mailbox, portal, repositories and people are fixtures. Nothing '
        'has been created, edited or sent. The application has no navigation like this today: it '
        'is a CLI and a read-only web view of stored reports, the two actions have no server '
        'endpoint, and the Zoho and Graph adapters have never run against a live portal or '
        'mailbox.</p></div></section>'
        '</div>'
        % (toc, sections, ticket_sheet(bug, config), reply_sheet(request, config), rows))

    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Milou</title><style>%s%s</style></head><body>%s</body></html>'
            % (render_html.STYLES, FLAT_STYLES, body))


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
