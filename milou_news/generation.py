"""Callable scheduled-generation boundary."""

import json

from .archive import ReportStore
from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher
from .routines import (generate_daily_wins, generate_morning_brief,
                       generate_commitments_tracker, generate_stale_work_finder,
                       generate_dependabot_pr_triage, generate_launch_decoder,
                       generate_launch_radar, generate_travel_logistics_tracker)


def generate_and_store(fixture_path, store_path, limit=5, now=None):
    """Generate a fixture-backed report and persist it for a scheduler to call."""
    with open(fixture_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    report = generate_brief(SOURCES, FixtureFetcher(payload), now=now,
                            config=BriefConfig(limit=limit))
    return ReportStore(store_path).save(report, generated_at=now)


def generate_routine_and_store(routine, fixture_path, store_path, now=None):
    with open(fixture_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    canonical = {
        "daily-wins": "daily-wins-recap", "daily-wins-recap": "daily-wins-recap",
        "morning-brief": "morning-brief-meeting-prep", "morning-brief-meeting-prep": "morning-brief-meeting-prep",
        "commitments": "commitments-follow-up-tracker", "commitments-follow-up": "commitments-follow-up-tracker",
        "commitments-follow-up-tracker": "commitments-follow-up-tracker",
        "stale-work": "stale-work-finder", "stale-work-finder": "stale-work-finder",
        "dependabot": "dependabot-pr-triage", "dependabot-pr-triage": "dependabot-pr-triage",
        "launch-decoder": "launch-decoder", "launch-decoder-24h": "launch-decoder",
        "launch-radar": "launch-radar", "weekly-launch-radar": "launch-radar",
        "travel-logistics": "travel-logistics-tracker", "travel-logistics-tracker": "travel-logistics-tracker",
    }.get(routine, routine)
    if canonical == "daily-wins-recap":
        report = generate_daily_wins(payload)
    elif canonical == "morning-brief-meeting-prep":
        report = generate_morning_brief(payload)
    elif canonical == "commitments-follow-up-tracker":
        report = generate_commitments_tracker(payload)
    elif canonical == "stale-work-finder":
        report = generate_stale_work_finder(payload)
    elif canonical == "dependabot-pr-triage":
        report = generate_dependabot_pr_triage(payload)
    elif canonical == "launch-decoder":
        report = generate_launch_decoder(payload)
    elif canonical == "launch-radar":
        report = generate_launch_radar(payload)
    elif canonical == "travel-logistics-tracker":
        report = generate_travel_logistics_tracker(payload)
    else:
        raise ValueError("unsupported routine: %s" % routine)
    return ReportStore(store_path).save(report, generated_at=now,
                                        metadata={"routine": canonical, "fixture": fixture_path,
                                                  "access": "read-only"})
