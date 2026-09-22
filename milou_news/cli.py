import argparse
import json
import sys
from datetime import datetime, timezone

from . import render_html, render_text
from .config import SOURCES
from .pipeline import (BriefConfig, build_brief_report, generate_brief,
                       prepare as prepare_brief)
from .sources import FixtureFetcher
from .archive import ReportStore
from .routines import (build_routine_report, generate_daily_wins, generate_morning_brief,
                       generate_commitments_tracker, generate_stale_work_finder,
                       generate_dependabot_pr_triage, generate_launch_decoder,
                       generate_launch_radar, generate_travel_logistics_tracker)
from .scheduler import Scheduler
from .models import default_registry
from .supervisor import SupervisorDispatcher
from .github_radar import (FixtureApi, GhApi, RadarConfig, build_radar_report,
                           generate_github_radar, prepare as prepare_radar)
from .actions import (ApprovalRequired, DryRunDocumentWriter, DryRunMailWriter, IncompleteAction,
                      OutlookReplyWriter, SharePointWordWriter, TicketConfig, WriteNotConfigured,
                      ZohoWriter, draft_context_reply, draft_ticket, execute, plan_report,
                      reply_plan_report, shorten)
from .outlook import (FixtureGraph, GraphApi, InboxConfig, build_outlook_report,
                      fetch_body, generate_outlook_monitor, locate_message)
from .zoho import (FixtureZoho, ZohoApi, ZohoConfig, build_zoho_report, coverage_from,
                   generate_zoho_radar, prepare as prepare_zoho)


#: CLI alias -> canonical routine name, used for storage labels and builders.
CANONICAL_LABELS = {
    "news": "daily-global-ai-news-brief",
    "daily-wins": "daily-wins-recap",
    "morning-brief": "morning-brief-meeting-prep",
    "commitments": "commitments-follow-up-tracker",
    "commitments-follow-up": "commitments-follow-up-tracker",
    "stale-work": "stale-work-finder",
    "dependabot": "dependabot-pr-triage",
    "launch-decoder-24h": "launch-decoder",
    "weekly-launch-radar": "launch-radar",
    "travel-logistics": "travel-logistics-tracker",
    "github-radar": "github-change-radar",
    "change-radar": "github-change-radar",
    "inbox": "outlook-inbox-monitor",
    "outlook": "outlook-inbox-monitor",
    "zoho": "zoho-projects-radar",
    "projects": "zoho-projects-radar",
}


def scheduler_command(argv):
    parser = argparse.ArgumentParser(description="Manage the local durable routine scheduler.")
    parser.add_argument("command", choices=("scheduler", "status", "ledger", "run"))
    parser.add_argument("--database", default="milou-scheduler.sqlite3")
    parser.add_argument("--config", help="JSON scheduler configuration")
    parser.add_argument("--store", help="dated archive directory; persist each scheduled report")
    args = parser.parse_args(argv)
    scheduler = Scheduler(args.database, default_registry())
    if args.config:
        scheduler.load_config(args.config)
    if args.command == "run":
        payloads = {}
        for routine in scheduler.status()["routines"]:
            fixture = routine.get("fixture")
            if fixture:
                with open(fixture, encoding="utf-8") as handle:
                    payloads[routine["name"]] = json.load(handle)
        store = ReportStore(args.store) if args.store else None
        results = scheduler.run_due(SupervisorDispatcher(default_registry()), payloads, store=store)
        print(json.dumps([{"routine": r.routine, "error": r.error,
                           "structured": r.structured is not None} for r in results], indent=2))
    elif args.command == "ledger":
        print(json.dumps(scheduler.ledger(), indent=2))
    else:
        print(json.dumps(scheduler.status(), indent=2))
    return 0


def _ticket_settings(args) -> TicketConfig:
    settings = {}
    if args.ticket_config:
        with open(args.ticket_config, encoding="utf-8") as handle:
            settings = json.load(handle)
    return TicketConfig.from_mapping(settings)


def _locate(parser, api, inbox_config, identifier):
    mailbox, message = locate_message(api, inbox_config, identifier)
    if message is None:
        parser.error("no message %r in the mailbox window" % identifier)
    return mailbox, message


def _draft_ticket(parser, args, api, inbox_config, now) -> int:
    """Draft a ticket from one email. Creates nothing without explicit approval."""
    _mailbox, message = _locate(parser, api, inbox_config, args.draft_ticket)
    config = _ticket_settings(args)
    body = fetch_body(api, message.id) or message.preview
    plan = draft_ticket(
        config, now.date(), subject=message.subject, sender=message.display,
        received=message.when.strftime("%b %d, %H:%M UTC") if message.when else "",
        body=body, url=message.url, title=args.title or "", message_id=message.id,
        received_date=message.when.date() if message.when else now.date())
    edits = {name: getattr(args, name) for name in
             ("reported_by", "reported_on", "requested_by", "record", "owner", "status")
             if getattr(args, name, None) is not None}
    if edits:
        plan = plan.with_inputs(**edits)

    if not args.approve:
        report = plan_report(plan, config, now.date())
        print(render_html.report_page(report) if args.format == "html"
              else render_text.render_markdown(report))
        if not args.title:
            suggestion = shorten(message.subject)
            print("\nSuggested title: %s" % (suggestion or "(none — the subject gave nothing usable)"))
            print("Milou will not choose the title. Re-run with --title \"...\" to set it,")
            print("then add --approve \"<your name>\" to create the ticket.")
        for name in plan.missing():
            if name != "title":
                print("Still missing: %s — supply it with --%s, or ask for it with "
                      "--draft-reply %s" % (name, name.replace("_", "-"), message.id))
        return 0

    try:
        approved = plan.approve(args.approve, now)
        # The tracker is a Word document somebody maintains by hand, so the live
        # writer is used only once a link to it is actually configured.
        document = DryRunDocumentWriter() if (args.dry_run or not config.document_url) \
            else SharePointWordWriter(config.document_url)
        results = execute(approved, ZohoWriter(), document,
                          mail_writer=DryRunMailWriter() if args.dry_run else OutlookReplyWriter())
    except (ApprovalRequired, IncompleteAction, WriteNotConfigured) as exc:
        parser.error(str(exc))
    for result in results:
        print("%s %s — %s" % ("ok  " if result.ok else "FAIL", result.action, result.detail))
    return 0 if all(result.ok for result in results) else 1


def _draft_reply(parser, args, api, inbox_config, now) -> int:
    """Draft the context reply. Sends nothing without explicit approval."""
    mailbox, message = _locate(parser, api, inbox_config, args.draft_reply)
    config = _ticket_settings(args)
    plan = draft_context_reply(
        config, subject=message.subject, sender=message.display,
        sender_address=message.sender, to=message.to, cc=message.cc, mailbox=mailbox,
        message_id=message.id, body=fetch_body(api, message.id) or message.preview,
        received_date=message.when.date() if message.when else now.date(), url=message.url)
    if args.to:
        plan = plan.with_inputs(to="\n".join(args.to))

    if not args.approve:
        report = reply_plan_report(plan, now.date())
        print(render_html.report_page(report) if args.format == "html"
              else render_text.render_markdown(report))
        print("\n--- the reply, as it would be sent ---")
        print(plan.actions[0].fields["body"])
        print("\nNothing has been sent. Add --approve \"<your name>\" to send it.")
        return 0

    writer = DryRunMailWriter() if args.dry_run else OutlookReplyWriter(
        allow_recipient_edits=bool(args.to))
    try:
        results = execute(plan.approve(args.approve, now), mail_writer=writer)
    except (ApprovalRequired, IncompleteAction, WriteNotConfigured) as exc:
        parser.error(str(exc))
    for result in results:
        print("%s %s — %s" % ("ok  " if result.ok else "FAIL", result.action, result.detail))
    return 0 if all(result.ok for result in results) else 1


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("scheduler", "status", "ledger", "run"):
        return scheduler_command(argv)
    parser = argparse.ArgumentParser(description="Generate a read-only Milou routine report.")
    parser.add_argument(
        "--routine",
        choices=(
            "news",
            "daily-global-ai-news-brief",
            "daily-wins",
            "daily-wins-recap",
            "morning-brief",
            "morning-brief-meeting-prep",
            "commitments",
            "commitments-follow-up",
            "commitments-follow-up-tracker",
            "stale-work",
            "stale-work-finder",
            "dependabot",
            "dependabot-pr-triage",
            "launch-decoder",
            "launch-decoder-24h",
            "launch-radar",
            "weekly-launch-radar",
            "travel-logistics",
            "travel-logistics-tracker",
            "github-change-radar",
            "github-radar",
            "change-radar",
            "outlook-inbox-monitor",
            "inbox",
            "outlook",
            "zoho-projects-radar",
            "zoho",
            "projects",
        ),
        default="news",
    )
    parser.add_argument("--fixture", help="JSON fixture mapping source name to article arrays or radar API responses")
    parser.add_argument("--config", help="JSON radar scope (repositories, organizations, window_hours)")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--store", help="dated archive directory; persist the generated report")
    parser.add_argument("--format", choices=("markdown", "html"), default="markdown",
                        help="markdown keeps the plain report; html renders the structured layout")
    parser.add_argument("--follow-up-days", type=int, default=None,
                        help="inbox monitor: business days of silence before a sent email is chased")
    parser.add_argument("--max-items", type=int, default=None,
                        help="inbox/zoho: hard cap on actionable lines")
    parser.add_argument("--draft-ticket", metavar="MESSAGE_ID",
                        help="inbox monitor: draft a Zoho ticket from one email. Nothing is "
                             "created; the plan is printed for review")
    parser.add_argument("--draft-reply", metavar="MESSAGE_ID",
                        help="inbox monitor: draft a reply-all asking for the context a ticket "
                             "needs. Nothing is sent; the reply is printed for review")
    parser.add_argument("--to", action="append", metavar="ADDRESS",
                        help="override the reply-all recipients; repeatable. Editing the "
                             "recipient list needs a wider Graph grant than sending as-is")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --draft-reply --approve: print the reply instead of sending it")
    parser.add_argument("--title", help="the ticket title; required before a draft can be approved")
    parser.add_argument("--reported-by", dest="reported_by",
                        help="bug tickets: the person who reported it, if the email did not say")
    parser.add_argument("--reported-on", dest="reported_on",
                        help="bug tickets: when it was reported, if the email did not say")
    parser.add_argument("--requested-by", dest="requested_by",
                        help="override the requester; defaults to the email's sender")
    parser.add_argument("--record", help="the project or record the ticket concerns")
    parser.add_argument("--owner", help="Zoho user id to assign; the default is unassigned")
    parser.add_argument("--status", help="override the ticket status")
    parser.add_argument("--approve", metavar="WHO",
                        help="approve and run a drafted plan. Requires MILOU_ZOHO_WRITE_TOKEN, "
                             "or MILOU_OUTLOOK_WRITE_TOKEN for a reply")
    parser.add_argument("--ticket-config", metavar="PATH",
                        help="JSON portal/project/status/document settings for ticket creation")
    parser.add_argument("--zoho-coverage", metavar="PATH",
                        help="inbox monitor: a Zoho config or fixture; notification mail the "
                             "Zoho radar already reported is suppressed, and anything "
                             "unmatched is reported as a coverage gap")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    structured = None
    radar_names = ("github-change-radar", "github-radar", "change-radar")
    inbox_names = ("outlook-inbox-monitor", "inbox", "outlook")
    zoho_names = ("zoho-projects-radar", "zoho", "projects")

    def _zoho(path, live_settings=None):
        """Build a Zoho api/config pair from a fixture or a live config."""
        if path:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload.get("responses"):
                return (FixtureZoho(payload["responses"], payload.get("errors", {})),
                        ZohoConfig.from_mapping(payload.get("config", payload)))
            return ZohoApi(), ZohoConfig.from_mapping(payload.get("config", payload))
        return ZohoApi(), ZohoConfig.from_mapping(live_settings or {})

    if args.routine in zoho_names:
        api, zoho_config = _zoho(args.fixture or args.config)
        if args.max_items is not None:
            zoho_config = ZohoConfig.from_mapping(
                dict(vars(zoho_config), max_items=args.max_items, endpoints=zoho_config.endpoints))
        structured = build_zoho_report(api, zoho_config, now)
        report = generate_zoho_radar(api, zoho_config, now, report=structured)
    elif args.routine in inbox_names:
        # A fixture carries its own config; a live run reads Graph with the
        # operator's token from the environment and never writes.
        if args.fixture:
            with open(args.fixture, encoding="utf-8") as handle:
                fixture = json.load(handle)
            api = FixtureGraph(fixture.get("responses", fixture), fixture.get("errors", {}))
            settings = fixture.get("config", {})
        else:
            api, settings = GraphApi(), {}
        if args.config:
            with open(args.config, encoding="utf-8") as handle:
                settings = json.load(handle)
        if args.follow_up_days is not None:
            settings = dict(settings, follow_up_days=args.follow_up_days)
        if args.max_items is not None:
            settings = dict(settings, max_items=args.max_items)
        inbox_config = InboxConfig.from_mapping(settings)
        if args.draft_ticket:
            return _draft_ticket(parser, args, api, inbox_config, now)
        if args.draft_reply:
            return _draft_reply(parser, args, api, inbox_config, now)
        coverages = []
        if args.zoho_coverage:
            zoho_api, zoho_config = _zoho(args.zoho_coverage)
            _n, activities, _errors, _count = prepare_zoho(zoho_api, zoho_config, now)
            coverages.append(coverage_from(activities, zoho_config))
        structured = build_outlook_report(api, inbox_config, now, coverages=coverages)
        report = generate_outlook_monitor(api, inbox_config, now, report=structured)
    elif args.routine in radar_names:
        if not args.config:
            parser.error("--config is required for the GitHub Change Radar")
        with open(args.config, encoding="utf-8") as handle:
            config = RadarConfig.from_mapping(json.load(handle))
        if args.fixture:
            with open(args.fixture, encoding="utf-8") as handle:
                fixture = json.load(handle)
            api = FixtureApi(fixture.get("responses", fixture), fixture.get("errors", {}))
        else:
            api = GhApi()
        # Collect once; render both formats from the same bounded result set.
        prepared = prepare_radar(api, config, now)
        report = generate_github_radar(api, config, now, prepared=prepared)
        structured = build_radar_report(api, config, now, prepared=prepared)
        canonical_label = "github-change-radar"
    else:
        if not args.fixture:
            parser.error("--fixture is required for fixture-backed routines")
        with open(args.fixture, encoding="utf-8") as handle:
            payload = json.load(handle)
    if args.routine in ("news", "daily-global-ai-news-brief"):
        brief_config = BriefConfig(limit=args.limit)
        fetcher = FixtureFetcher(payload)
        prepared = prepare_brief(SOURCES, fetcher, now, brief_config)
        report = generate_brief(SOURCES, fetcher, now, brief_config, prepared=prepared)
        structured = build_brief_report(SOURCES, fetcher, now, brief_config, prepared=prepared)
    elif args.routine in ("daily-wins", "daily-wins-recap"):
        report = generate_daily_wins(payload)
    elif args.routine in ("morning-brief", "morning-brief-meeting-prep"):
        report = generate_morning_brief(payload)
    elif args.routine in (
        "commitments",
        "commitments-follow-up",
        "commitments-follow-up-tracker",
    ):
        report = generate_commitments_tracker(payload)
    elif args.routine in ("stale-work", "stale-work-finder"):
        report = generate_stale_work_finder(payload)
    elif args.routine in ("dependabot", "dependabot-pr-triage"):
        report = generate_dependabot_pr_triage(payload)
    elif args.routine in ("launch-decoder", "launch-decoder-24h"):
        report = generate_launch_decoder(payload)
    elif args.routine in ("launch-radar", "weekly-launch-radar"):
        report = generate_launch_radar(payload)
    elif args.routine in ("travel-logistics", "travel-logistics-tracker"):
        report = generate_travel_logistics_tracker(payload)
    canonical = CANONICAL_LABELS.get(args.routine, args.routine)
    if structured is None and args.routine not in radar_names + inbox_names + zoho_names:
        # Every fixture-backed routine builds its report from the same payload.
        structured = build_routine_report(canonical, payload)
    if args.store:
        ReportStore(args.store).save(
            report,
            generated_at=now,
            metadata={"routine": canonical,
                      "fixture": args.fixture, "config": args.config,
                      "access": "read-only", "auth": "gh CLI" if args.routine in radar_names else "none",
                      "status": "authenticated-read-only" if args.routine in radar_names else "fixture"},
            report=structured,
        )
    if args.format == "html":
        if structured is None:
            parser.error("--format html is not available for %s yet; it still renders as Markdown"
                         % args.routine)
        print(render_html.report_page(structured))
        return 0
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
