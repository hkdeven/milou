import argparse
import json
import sys
from datetime import datetime, timezone

from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher
from .archive import ReportStore
from .routines import (generate_daily_wins, generate_morning_brief,
                       generate_commitments_tracker, generate_stale_work_finder,
                       generate_dependabot_pr_triage, generate_launch_decoder,
                       generate_launch_radar, generate_travel_logistics_tracker)
from .scheduler import Scheduler
from .models import default_registry
from .supervisor import SupervisorDispatcher
from .github_radar import FixtureApi, GhApi, RadarConfig, generate_github_radar


def scheduler_command(argv):
    parser = argparse.ArgumentParser(description="Manage the local durable routine scheduler.")
    parser.add_argument("command", choices=("scheduler", "status", "ledger", "run"))
    parser.add_argument("--database", default="milou-scheduler.sqlite3")
    parser.add_argument("--config", help="JSON scheduler configuration")
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
        results = scheduler.run_due(SupervisorDispatcher(default_registry()), payloads)
        print(json.dumps([{"routine": r.routine, "error": r.error} for r in results], indent=2))
    elif args.command == "ledger":
        print(json.dumps(scheduler.ledger(), indent=2))
    else:
        print(json.dumps(scheduler.status(), indent=2))
    return 0


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
        ),
        default="news",
    )
    parser.add_argument("--fixture", help="JSON fixture mapping source name to article arrays or radar API responses")
    parser.add_argument("--config", help="JSON radar scope (repositories, organizations, window_hours)")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--store", help="dated archive directory; persist the generated report")
    args = parser.parse_args(argv)
    radar_names = ("github-change-radar", "github-radar", "change-radar")
    if args.routine in radar_names:
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
        report = generate_github_radar(api, config)
        canonical_label = "github-change-radar"
    else:
        if not args.fixture:
            parser.error("--fixture is required for fixture-backed routines")
        with open(args.fixture, encoding="utf-8") as handle:
            payload = json.load(handle)
    if args.routine in ("news", "daily-global-ai-news-brief"):
        report = generate_brief(SOURCES, FixtureFetcher(payload), config=BriefConfig(limit=args.limit))
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
    if args.store:
        canonical_labels = {
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
        }
        ReportStore(args.store).save(
            report,
            metadata={"routine": canonical_labels.get(args.routine, args.routine),
                      "fixture": args.fixture, "config": args.config,
                      "access": "read-only", "auth": "gh CLI" if args.routine in radar_names else "none",
                      "status": "authenticated-read-only" if args.routine in radar_names else "fixture"},
        )
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
