import json
import unittest
from datetime import datetime, timezone

from milou_news.config import SOURCES
from milou_news.models import Routine, RoutineRegistry
from milou_news.pipeline import BriefConfig, deduplicate, filter_fresh, generate_brief, rank
from milou_news.sources import FixtureFetcher, JsonSourceFetcher, SourceFetchError, parse_articles


NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


class NewsBriefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("fixtures/news.json", encoding="utf-8") as handle:
            cls.payload = json.load(handle)

    def test_registry_is_explicit_and_read_only(self):
        registry = RoutineRegistry()
        registry.register(Routine("test", "1", "test"))
        self.assertEqual(registry.get("test").access, "read-only")
        with self.assertRaises(ValueError):
            registry.register(Routine("test", "2", "duplicate"))

    def test_source_parser_reports_invalid_payload(self):
        with self.assertRaises(SourceFetchError):
            parse_articles({"not": "an array"}, SOURCES[0])

    def test_fetcher_preserves_source_failure(self):
        result = JsonSourceFetcher(opener=lambda _: b"{bad").fetch(SOURCES[0])
        self.assertIn("JSONDecodeError", result.error)
        self.assertFalse(result.articles)

    def test_freshness_and_deduplication(self):
        fresh = FixtureFetcher(self.payload).fetch(SOURCES[5]).articles
        old = FixtureFetcher(self.payload).fetch(SOURCES[1]).articles
        self.assertEqual(len(filter_fresh(fresh + old, NOW, 24)), 1)
        duplicate = FixtureFetcher(self.payload).fetch(SOURCES[4]).articles
        unique, removed = deduplicate(fresh + duplicate)
        self.assertEqual(len(unique), 1)
        self.assertEqual(removed, 1)

    def test_ranking_exposes_signals_and_non_us_weight(self):
        articles = FixtureFetcher(self.payload).fetch(SOURCES[0]).articles
        ranked = rank(articles, NOW)
        self.assertIn("global_discussion", ranked[0].score_signals)
        self.assertGreater(ranked[0].score_signals["non_us_weight"], 0)

    def test_report_has_citations_failures_and_diversity(self):
        report = generate_brief(
            SOURCES, FixtureFetcher(self.payload), now=NOW,
            config=BriefConfig(limit=3),
        )
        self.assertIn("https://example.test/row/clinics", report)
        self.assertIn("regions represented: Africa, East Asia, North America", report)
        self.assertIn("Not included:", report)
        self.assertIn("Unavailable sources:", report)


if __name__ == "__main__":
    unittest.main()
