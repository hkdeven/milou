import argparse
import json
from datetime import datetime, timezone

from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher
from .archive import ReportStore
from .routines import (generate_daily_wins, generate_morning_brief,
                       generate_commitments_tracker, generate_stale_work_finder,
                       generate_dependabot_pr_triage, generate_launch_decoder,
                       generate_launch_radar, generate_travel_logistics_tracker)


def main(argv=None) -> int:
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
        ),
        default="news",
    )
    parser.add_argument("--fixture", required=True, help="JSON fixture mapping source name to article arrays")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--store", help="dated archive directory; persist the generated report")
    args = parser.parse_args(argv)
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
    else:
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
        }
        ReportStore(args.store).save(
            report,
            metadata={"routine": canonical_labels.get(args.routine, args.routine),
                      "fixture": args.fixture, "access": "read-only"},
        )
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
