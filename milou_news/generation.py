"""Callable scheduled-generation boundary."""

import json

from .archive import ReportStore
from .config import SOURCES
from .pipeline import BriefConfig, generate_brief
from .sources import FixtureFetcher


def generate_and_store(fixture_path, store_path, limit=5, now=None):
    """Generate a fixture-backed report and persist it for a scheduler to call."""
    with open(fixture_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    report = generate_brief(SOURCES, FixtureFetcher(payload), now=now,
                            config=BriefConfig(limit=limit))
    return ReportStore(store_path).save(report, generated_at=now)
