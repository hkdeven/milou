import argparse
import json
from datetime import datetime, timezone

from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher
from .archive import ReportStore
from .routines import (generate_daily_wins, generate_morning_brief,
                       generate_commitments_tracker, generate_stale_work_finder,
                       generate_dependabot_pr_triage)


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
    else:
        report = generate_dependabot_pr_triage(payload)
    if args.store:
        ReportStore(args.store).save(
            report,
            metadata={"routine": args.routine, "fixture": args.fixture},
        )
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
