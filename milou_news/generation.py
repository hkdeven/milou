"""Callable scheduled-generation boundary."""

import json

from .archive import ReportStore
from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher
from .routines import generate_daily_wins, generate_morning_brief


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
    if routine in ("daily-wins", "daily-wins-recap"):
        report = generate_daily_wins(payload)
    elif routine in ("morning-brief", "morning-brief-meeting-prep"):
        report = generate_morning_brief(payload)
    else:
        raise ValueError("unsupported routine: %s" % routine)
    return ReportStore(store_path).save(report, generated_at=now,
                                        metadata={"routine": routine, "fixture": fixture_path})
