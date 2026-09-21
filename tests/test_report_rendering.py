"""Tests for the structured report model and its HTML renderer."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import render_html
from milou_news.archive import ReportStore
from milou_news.config import SOURCES
from milou_news.github_radar import FixtureApi, RadarConfig, build_radar_report, generate_github_radar
from milou_news.pipeline import MAX_SCORE, WEIGHTS, BriefConfig, build_brief_report
from milou_news.report import Bar, Report, Row, Segment, Signal, Tier, humanize_age
from milou_news.models import Article, default_registry
from milou_news.routines import build_routine_report
from milou_news.scheduler import Scheduler
from milou_news.supervisor import SupervisorDispatcher
from milou_news.sources import FetchResult, FixtureFetcher
from milou_news.web import make_handler

NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _news_report(now=NOW):
    with open(os.path.join(FIXTURES, "news.json"), encoding="utf-8") as handle:
        payload = json.load(handle)
    return build_brief_report(SOURCES, FixtureFetcher(payload), now=now, config=BriefConfig())


def _article(title, slug, region, significance, evidence, discussion, key=None, hours=1):
    return Article(title=title, url="https://example.test/%s" % slug, outlet="",
                   published_at=NOW - timedelta(hours=hours), summary="s",
                   regions=(region,), topics=("ai",), significance=significance,
                   evidence=evidence, discussion=discussion, non_us=True, event_key=key)


class _StubFetcher:
    """Serves hand-built articles per source name, for cases the fixture cannot show."""

    def __init__(self, by_outlet):
        self.by_outlet = by_outlet

    def fetch(self, source):
        articles = []
        for article in self.by_outlet.get(source.name, ()):
            article.outlet = source.name
            articles.append(article)
        return FetchResult(source, articles, "")


def _built_report(by_outlet, limit=5, now=NOW):
    return build_brief_report(SOURCES, _StubFetcher(by_outlet), now=now,
                              config=BriefConfig(limit=limit))


def _radar_api(now=NOW):
    """Two events: an older high-risk delete and a newer, merely notable close."""
    older = (now - timedelta(hours=40)).isoformat()
    newer = (now - timedelta(hours=2)).isoformat()
    return FixtureApi({
        "/user": {"login": "octocat"},
        "/users/octocat/events?per_page=100": [],
        "/repos/acme/app/events?per_page=100": [
            {"id": "1", "type": "DeleteEvent", "created_at": older,
             "repo": {"name": "acme/app"}, "payload": {"ref": "release/2.14"},
             "actor": {"login": "dana"}},
            {"id": "2", "type": "PullRequestEvent", "created_at": newer,
             "repo": {"name": "acme/app"},
             "payload": {"action": "closed", "pull_request": {
                 "title": "Cache tier lookups", "html_url": "https://example.test/pr/1",
                 "state": "closed", "labels": [{"name": "performance"}]}},
             "actor": {"login": "sam"}},
        ],
    })


RADAR_CONFIG = RadarConfig(repositories=("acme/app",), organizations=(), window_hours=168,
                           primary_organizations=())


class ReportModelTest(unittest.TestCase):

    def test_round_trips_through_json(self):
        report = _news_report()
        restored = Report.from_dict(json.loads(json.dumps(report.to_dict())))
        self.assertEqual(restored.title, report.title)
        self.assertEqual([t.label for t in restored.tiers], [t.label for t in report.tiers])
        self.assertEqual(restored.tiers[0].rows[0].score, report.tiers[0].rows[0].score)
        original_meter = report.tiers[0].rows[0].meter
        self.assertIsNotNone(restored.tiers[0].rows[0].meter)
        self.assertEqual(len(restored.tiers[0].rows[0].meter.segments),
                         len(original_meter.segments))

    def test_from_dict_tolerates_missing_and_unknown_keys(self):
        restored = Report.from_dict({"title": "X", "tiers": [{"label": "T", "rows": [{}]}],
                                     "unexpected": 1})
        self.assertEqual(restored.title, "X")
        self.assertEqual(restored.tiers[0].rows[0].title, "")
        self.assertTrue(restored.is_empty is False)

    def test_from_dict_rejects_non_mapping(self):
        with self.assertRaises(ValueError):
            Report.from_dict(["not", "a", "mapping"])

    def test_humanize_age_bands(self):
        self.assertEqual(humanize_age(NOW - timedelta(minutes=30), NOW), "30m ago")
        self.assertEqual(humanize_age(NOW - timedelta(hours=14), NOW), "14h ago")
        self.assertEqual(humanize_age(NOW - timedelta(days=3), NOW), "3d ago")
        self.assertEqual(humanize_age(None, NOW), "")

    def test_empty_tiers_are_never_rendered(self):
        report = Report(title="T", routine="r", tiers=[Tier("Empty"), Tier("Full", [Row("x")])])
        self.assertEqual([t.label for t in report.populated_tiers()], ["Full"])


class RadarReportTest(unittest.TestCase):

    def test_consequence_outranks_recency(self):
        report = build_radar_report(_radar_api(), RADAR_CONFIG, now=NOW)
        labels = [tier.label for tier in report.tiers]
        self.assertEqual(labels[0], "Needs attention")
        self.assertIn("Notable", labels)
        # The high-risk row is older, yet still sorts above the newer notable one.
        self.assertIn("release/2.14", report.tiers[0].rows[0].title)
        self.assertEqual(report.tiers[0].rows[0].tone, "critical")

    def test_kpis_and_type_distribution(self):
        report = build_radar_report(_radar_api(), RADAR_CONFIG, now=NOW)
        kpis = {kpi.label: kpi.value for kpi in report.kpis}
        self.assertEqual(kpis["Changes"], "2")
        self.assertEqual(kpis["High risk"], "1")
        self.assertEqual(kpis["Notable"], "1")
        bar = report.bars[0]
        self.assertEqual(bar.kind, "sequential")
        # Magnitude bars are ordered, so the ramp reads light to dark in sequence.
        self.assertEqual([segment.value for segment in bar.segments],
                         sorted([segment.value for segment in bar.segments], reverse=True))

    def test_empty_fields_are_dropped_from_rows(self):
        report = build_radar_report(_radar_api(), RADAR_CONFIG, now=NOW)
        rows = [row for tier in report.tiers for row in tier.rows]
        self.assertTrue(all("unknown" not in row.byline for row in rows))
        self.assertTrue(all("None" not in row.byline for row in rows))

    def test_missing_committer_never_prints_as_none(self):
        api = FixtureApi({
            "/user": {"login": "octocat"},
            "/users/octocat/events?per_page=100": [],
            "/repos/acme/app/events?per_page=100": [
                {"id": "9", "type": "PushEvent", "created_at": NOW.isoformat(),
                 "repo": {"name": "acme/app"},
                 "payload": {"ref": "main", "commits": [{"sha": "abc1234", "message": "tidy"}]}},
            ],
        })
        markdown = generate_github_radar(api, RADAR_CONFIG, NOW)
        self.assertNotIn("committer: None", markdown)
        report = build_radar_report(api, RADAR_CONFIG, now=NOW)
        rows = [row for tier in report.tiers for row in tier.rows]
        self.assertTrue(all("None" not in row.byline for row in rows))

    def test_markdown_and_structure_share_one_collection(self):
        api = _radar_api()
        from milou_news.github_radar import prepare
        prepared = prepare(api, RADAR_CONFIG, NOW)
        markdown = generate_github_radar(api, RADAR_CONFIG, NOW, prepared=prepared)
        report = build_radar_report(api, RADAR_CONFIG, NOW, prepared=prepared)
        self.assertIn("GitHub Change Radar", markdown)
        self.assertEqual(report.total_rows, 2)

    def test_api_failures_become_a_promoted_alert(self):
        api = FixtureApi({"/user": {"login": "octocat"}},
                         errors={"/users/octocat/events?per_page=100": "HTTP 404"})
        report = build_radar_report(api, RADAR_CONFIG, now=NOW)
        self.assertIn("incomplete", report.alert)
        self.assertIn("404", report.alert_detail)


class BriefReportTest(unittest.TestCase):

    def test_score_meter_matches_the_ranking_weights(self):
        report = _news_report()
        row = report.tiers[0].rows[0]
        widths = sum(segment.value for segment in row.meter.segments)
        # Scaling the bar back by the ceiling must reproduce the score on the card.
        self.assertEqual("%.2f" % (widths / 100.0 * MAX_SCORE), row.score)
        self.assertEqual([s.label for s in row.meter.segments][:len(WEIGHTS)],
                         [label for _, _, label in WEIGHTS])

    def test_non_us_bonus_is_texture_not_hue(self):
        report = _news_report()
        bonus = [segment for row in report.tiers[0].rows for segment in row.meter.segments
                 if segment.label == "non-US bonus"]
        self.assertTrue(bonus)
        self.assertTrue(all(segment.texture for segment in bonus))

    def test_diversity_promotion_is_visible(self):
        # Two strong items share a region, so a weaker third region gets promoted
        # ahead of the second — correct, and invisible unless it is marked.
        report = _built_report({
            "Rest of World": [_article("Lead", "row", "Africa", 0.95, 0.95, 0.95)],
            "Nikkei Asia": [_article("Same region", "nikkei", "Africa", 0.9, 0.9, 0.9)],
            "Euractiv": [_article("New region", "eur", "Europe", 0.3, 0.3, 0.3)],
        }, limit=3)
        rows = report.tiers[0].rows
        promoted = [row for row in rows if row.marker == "up"]
        demoted = [row for row in rows if row.marker == "down"]
        self.assertTrue(promoted, "a lower-scoring item is promoted for region diversity")
        self.assertTrue(demoted)
        # The promoted item really does score below the one it was placed above.
        self.assertLess(float(promoted[0].score), float(demoted[0].score))
        self.assertTrue(any("region" in flag.label for flag in promoted[0].flags))

    def test_ranking_decides_which_duplicate_survives(self):
        report = _news_report()
        considered = [tier for tier in report.tiers if tier.label.startswith("Considered")][0]
        duplicate = [row for row in considered.rows if row.category == "duplicate"][0]
        # The weaker regional account is dropped; the better-evidenced original
        # is kept, whatever order the sources happen to be configured in.
        self.assertEqual(duplicate.source, "South China Morning Post")
        self.assertIn("Euractiv", duplicate.byline)
        self.assertIn("corroborates", duplicate.byline)
        kept = [row for row in report.tiers[0].rows if "evaluation guidance" in row.title][0]
        self.assertEqual(kept.source, "Euractiv")

    def test_dropped_duplicate_still_reports_a_signal_it_led_on(self):
        # Ranking picks the survivor overall, so a dropped account can still lead
        # on one signal. That trade must stay visible.
        report = _built_report({
            "Rest of World": [_article("Widely covered", "row", "Africa", 1.0, 0.5, 1.0,
                                       key="shared")],
            "Euractiv": [_article("Widely covered", "eur", "Europe", 0.1, 1.0, 0.1,
                                  key="shared")],
        })
        considered = [tier for tier in report.tiers if tier.label.startswith("Considered")][0]
        duplicate = [row for row in considered.rows if row.category == "duplicate"][0]
        self.assertEqual(duplicate.source, "Euractiv")
        self.assertTrue(any("evidence" in flag.label for flag in duplicate.flags),
                        "the dropped account led on evidence; say so")

    def test_partition_duplicates_reports_pairs(self):
        report = _news_report()
        self.assertEqual({kpi.label: kpi.value for kpi in report.kpis}["Deduplicated"], "1")

    def test_stale_articles_are_listed_as_considered(self):
        report = _news_report()
        considered = [tier for tier in report.tiers if tier.label.startswith("Considered")][0]
        self.assertTrue(any(row.category == "stale" for row in considered.rows))

    def test_source_failures_are_promoted(self):
        report = _news_report()
        self.assertIn("incomplete", report.alert)
        self.assertIn("IEEE Spectrum", report.alert_detail)


class RoutineReportTest(unittest.TestCase):
    """The eight fixture-backed routines, built from their committed fixtures."""

    def _fixture(self, name):
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
            return json.load(handle)

    def _build(self, routine, fixture):
        return build_routine_report(routine, self._fixture(fixture))

    def test_every_routine_has_a_builder_and_renders(self):
        for routine, fixture in (("daily-wins-recap", "activity.json"),
                                 ("morning-brief-meeting-prep", "meetings.json"),
                                 ("commitments-follow-up-tracker", "commitments.json"),
                                 ("stale-work-finder", "stale-work.json"),
                                 ("dependabot-pr-triage", "dependabot.json"),
                                 ("launch-decoder", "launch-decoder.json"),
                                 ("launch-radar", "launch-radar.json"),
                                 ("travel-logistics-tracker", "travel-logistics.json")):
            with self.subTest(routine=routine):
                report = self._build(routine, fixture)
                self.assertIsNotNone(report, "%s has no builder" % routine)
                self.assertEqual(report.routine, routine)
                self.assertTrue(report.kpis)
                self.assertTrue(report.boundary, "every routine states its boundary")
                page = render_html.report_page(report)
                self.assertIn(report.title, page)

    def test_unknown_routine_has_no_builder(self):
        self.assertIsNone(build_routine_report("not-a-routine", {}))

    def test_daily_wins_keeps_facts_and_inference_apart(self):
        report = self._build("daily-wins-recap", "activity.json")
        labels = [tier.label for tier in report.tiers]
        self.assertEqual(labels[0], "Verified facts")
        self.assertIn("Inferred impact", labels)
        inferred = [tier for tier in report.tiers if tier.label == "Inferred impact"][0]
        self.assertEqual(inferred.tone, "notable")
        self.assertTrue(all(any("Inferred" in flag.label for flag in row.flags)
                            for row in inferred.rows),
                        "an inference must never read as a measured fact")

    def test_daily_wins_flags_a_win_with_no_evidence(self):
        report = build_routine_report("daily-wins-recap", {
            "activities": [{"title": "Unverifiable", "status": "completed"}]})
        row = report.tiers[0].rows[0]
        self.assertTrue(any(flag.tone == "coverage" for flag in row.flags))

    def test_stale_work_tiers_by_urgency(self):
        report = self._build("stale-work-finder", "stale-work.json")
        tones = [tier.tone for tier in report.tiers]
        self.assertEqual(tones, sorted(tones, key=["critical", "notable", "quiet"].index),
                         "urgent work sorts above work that merely needs watching")

    def test_dependabot_marks_failing_checks_critical(self):
        report = build_routine_report("dependabot-pr-triage", {
            "pull_requests": [{"title": "Bump lib", "severity": "low",
                               "checks": "failing", "conflicts": "yes"}]})
        row = [r for tier in report.tiers for r in tier.rows][0]
        self.assertTrue(any(signal.tone == "critical" and "checks" in signal.label
                            for signal in row.signals))
        self.assertTrue(any("human investigation" in flag.label for flag in row.flags))

    def test_dependabot_security_outranks_age(self):
        report = build_routine_report("dependabot-pr-triage", {
            "pull_requests": [{"title": "Old routine bump", "severity": "low",
                               "created_at": "2000-01-01T00:00:00Z", "checks": "passing"},
                              {"title": "Fresh security fix", "severity": "critical",
                               "checks": "passing"}]})
        self.assertEqual(report.tiers[0].label, "Security")
        self.assertIn("security", report.tiers[0].rows[0].title.lower())

    def test_morning_brief_preserves_what_must_not_be_lost(self):
        report = self._build("morning-brief-meeting-prep", "meetings.json")
        flags = [flag.label for row in report.tiers[0].rows for flag in row.flags]
        self.assertTrue(any(label.startswith("Commitment") for label in flags))
        self.assertTrue(any(label.startswith("Open question") for label in flags))
        self.assertTrue(any("Inaccessible link" in label for label in flags))
        kpis = {kpi.label: kpi.tone for kpi in report.kpis}
        self.assertEqual(kpis["Inaccessible"], "coverage")

    def test_travel_keeps_open_items_separate_from_itinerary(self):
        report = self._build("travel-logistics-tracker", "travel-logistics.json")
        labels = [tier.label for tier in report.tiers]
        self.assertIn("Itinerary", labels)
        outstanding = [tier for tier in report.tiers if tier.label.startswith("Open items")]
        self.assertTrue(outstanding)
        self.assertEqual(outstanding[0].tone, "notable")

    def test_empty_payload_reports_nothing_without_inventing_rows(self):
        for routine in ("daily-wins-recap", "morning-brief-meeting-prep",
                        "commitments-follow-up-tracker", "stale-work-finder",
                        "dependabot-pr-triage", "launch-decoder", "launch-radar",
                        "travel-logistics-tracker"):
            with self.subTest(routine=routine):
                report = build_routine_report(routine, {})
                self.assertTrue(report.is_empty)
                self.assertTrue(report.empty_note)
                self.assertIn("No activity to report", render_html.report_page(report))


class HtmlRenderTest(unittest.TestCase):

    def test_renders_tiers_bars_and_boundary(self):
        page = render_html.report_page(_news_report())
        self.assertIn("Daily global AI news brief", page)
        self.assertIn("Geographic spread", page)
        self.assertIn("Considered, not selected", page)
        self.assertIn("Read-only", page)
        self.assertIn("Scope &amp; boundary", page)

    def test_escapes_untrusted_report_text(self):
        report = Report(title="T", routine="r", tiers=[Tier(
            "Tier", [Row(title="<script>alert(1)</script>", byline='" onload="x',
                         signals=[Signal("<img src=x>")])])])
        page = render_html.report_page(report)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('" onload="x', page)

    def test_only_http_urls_become_links(self):
        report = Report(title="T", routine="r", tiers=[Tier(
            "Tier", [Row(title="a", url="javascript:alert(1)"),
                     Row(title="b", url="https://example.test/ok")])])
        page = render_html.report_page(report)
        self.assertNotIn("javascript:", page)
        self.assertIn("https://example.test/ok", page)

    def test_empty_report_is_concise_but_keeps_warnings(self):
        report = Report(title="T", routine="r", empty_note="Scanned 48 repositories.",
                        alert="1 coverage gap — this report is incomplete")
        page = render_html.report_page(report)
        self.assertIn("No activity to report", page)
        self.assertIn("Scanned 48 repositories.", page)
        self.assertIn("incomplete", page)

    def test_sequential_bar_labels_use_readable_ink(self):
        bar = Bar("Changes by type", [Segment(str(i), float(6 - i), str(6 - i), i)
                                      for i in range(6)], kind="sequential")
        page = render_html.document("t", render_html._bar(bar))
        # Dark steps take white labels; light steps take dark ink.
        self.assertIn("color:#FFFFFF", page)
        self.assertIn("color:#1D1D1F", page)

    def test_index_page_lists_reports_and_handles_empty(self):
        page = render_html.index_page([{"href": "/report/a.json", "generated_at": "2026-09-11",
                                        "routine": "daily-global-ai-news-brief", "status": "fixture"}])
        self.assertIn("daily-global-ai-news-brief", page)
        self.assertIn("Milou reports", page)
        self.assertIn("No reports stored yet", render_html.index_page([]))

    def test_login_page_never_echoes_a_token(self):
        page = render_html.login_page("Invalid token.")
        self.assertIn("Invalid token.", page)
        self.assertIn('type="password"', page)
        self.assertIn("<form", page)


class ScheduledRunTest(unittest.TestCase):
    """A scheduled run must keep what it produced, not just record that it ran."""

    CONFIG = {"routines": [{"name": "daily-wins-recap", "cadence": "daily", "at": "00:00",
                            "timezone": "UTC", "enabled": True, "access": "read-only"}]}
    PAYLOAD = {"daily-wins-recap": {"activities": [
        {"title": "Shipped the thing", "status": "completed",
         "url": "https://example.test/1", "inferred_impact": "Probably helps"}]}}

    def _scheduler(self, directory):
        scheduler = Scheduler(os.path.join(directory, "s.sqlite3"), default_registry())
        scheduler.configure(self.CONFIG)
        return scheduler

    def test_dispatch_carries_the_structured_report(self):
        result = SupervisorDispatcher(default_registry()).dispatch(
            "daily-wins-recap", self.PAYLOAD["daily-wins-recap"])
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.structured)
        self.assertEqual(result.structured.routine, "daily-wins-recap")
        self.assertIn("Daily wins", result.report)

    def test_dispatch_failure_still_reports_no_structure(self):
        result = SupervisorDispatcher(default_registry()).dispatch("daily-wins-recap", "not a mapping")
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.structured)

    def test_scheduled_run_stores_the_report_and_records_its_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(os.path.join(directory, "reports"))
            scheduler = self._scheduler(directory)
            results = scheduler.run_due(SupervisorDispatcher(default_registry()),
                                        self.PAYLOAD, now=NOW, store=store)
            self.assertEqual(len(results), 1)
            self.assertIsNotNone(results[0].structured)
            entry = scheduler.ledger()[0]
            self.assertEqual(entry["status"], "success")
            self.assertTrue(entry["report_path"], "the ledger must point at what the run produced")
            stored = store.reports()[0]
            self.assertIn("report", stored, "the structure is kept, not just the Markdown")
            self.assertEqual(stored["metadata"]["status"], "scheduled")

    def test_scheduled_run_without_a_store_still_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = self._scheduler(directory)
            results = scheduler.run_due(SupervisorDispatcher(default_registry()),
                                        self.PAYLOAD, now=NOW)
            self.assertEqual(len(results), 1)
            entry = scheduler.ledger()[0]
            self.assertEqual(entry["status"], "success")
            self.assertIsNone(entry["report_path"])

    def test_storage_failure_fails_the_run_rather_than_passing_silently(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = os.path.join(directory, "reports")
            with open(blocker, "w", encoding="utf-8") as handle:
                handle.write("not a directory")
            scheduler = self._scheduler(directory)
            scheduler.run_due(SupervisorDispatcher(default_registry()), self.PAYLOAD,
                              now=NOW, store=ReportStore(blocker))
            entry = scheduler.ledger()[0]
            self.assertEqual(entry["status"], "failed")
            self.assertIn("report not stored", entry["error"])


class ArchiveIntegrationTest(unittest.TestCase):

    def test_structured_report_is_stored_and_served_as_html(self):
        report = _news_report()
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(directory)
            store.save("# markdown\n", NOW, {"routine": "daily-global-ai-news-brief"}, report=report)
            stored = store.reports()[0]
            self.assertIn("report", stored)

            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, "secret"))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                base = "http://127.0.0.1:%d" % server.server_port
                headers = {"Authorization": ("B" + "earer") + " secret"}
                index = urllib.request.urlopen(
                    urllib.request.Request(base + "/", headers=headers)).read().decode("utf-8")
                self.assertIn("daily-global-ai-news-brief", index)
                path = index.split('href="/report/', 1)[1].split('"', 1)[0]
                page = urllib.request.urlopen(urllib.request.Request(
                    base + "/report/" + path, headers=headers)).read().decode("utf-8")
                self.assertIn("Geographic spread", page)
                self.assertIn("Read-only", page)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

    def test_report_without_structure_falls_back_to_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(directory)
            store.save("# legacy report\n", NOW, {"routine": "legacy"})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, "secret"))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                base = "http://127.0.0.1:%d" % server.server_port
                headers = {"Authorization": ("B" + "earer") + " secret"}
                index = urllib.request.urlopen(
                    urllib.request.Request(base + "/", headers=headers)).read().decode("utf-8")
                path = index.split('href="/report/', 1)[1].split('"', 1)[0]
                page = urllib.request.urlopen(urllib.request.Request(
                    base + "/report/" + path, headers=headers)).read().decode("utf-8")
                self.assertIn("legacy report", page)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
