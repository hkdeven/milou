import json
import unittest
import tempfile
import threading
import urllib.error
import urllib.request
from http.client import HTTPConnection
from datetime import datetime, timezone

from milou_news.config import SOURCES
from milou_news.models import Routine, RoutineRegistry, default_registry
from milou_news.pipeline import BriefConfig, deduplicate, filter_fresh, generate_brief, rank
from milou_news.sources import FixtureFetcher, JsonSourceFetcher, SourceFetchError, parse_articles
from milou_news.archive import ReportStore
from milou_news.generation import generate_and_store
from milou_news.web import make_handler
from milou_news.routines import (generate_daily_wins, generate_morning_brief,
                                 generate_commitments_tracker, generate_stale_work_finder,
                                 generate_dependabot_pr_triage, generate_launch_decoder,
                                 generate_launch_radar, generate_travel_logistics_tracker)
from milou_news.supervisor import SupervisorDispatcher
from http.server import ThreadingHTTPServer


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

    def test_new_routines_are_registered_read_only(self):
        registry = default_registry()
        self.assertIn("daily-wins-recap", registry.names())
        self.assertIn("morning-brief-meeting-prep", registry.names())
        self.assertEqual(registry.get("daily-wins-recap").access, "read-only")
        self.assertEqual(registry.get("dependabot-pr-triage").access, "read-only")
        self.assertIn("launch-decoder", registry.names())
        self.assertIn("launch-radar", registry.names())
        self.assertIn("travel-logistics-tracker", registry.names())

    def test_article_roadmap_routines_are_read_only_and_cited(self):
        with open("fixtures/commitments.json", encoding="utf-8") as handle:
            report = generate_commitments_tracker(json.load(handle))
        self.assertIn("Alex", report)
        self.assertIn("messages/1", report)
        self.assertIn("Suggested follow-up", report)
        with open("fixtures/stale-work.json", encoding="utf-8") as handle:
            report = generate_stale_work_finder(json.load(handle))
        self.assertIn("Urgent", report)
        self.assertIn("pull/8", report)
        with open("fixtures/dependabot.json", encoding="utf-8") as handle:
            report = generate_dependabot_pr_triage(json.load(handle))
        self.assertIn("Security / urgent", report)
        self.assertIn("do not auto-approve", report)
        self.assertNotIn("merged", report.lower())

    def test_daily_wins_separates_facts_and_inferred_impact(self):
        with open("fixtures/activity.json", encoding="utf-8") as handle:
            report = generate_daily_wins(json.load(handle))
        self.assertLess(report.index("## Verified facts"), report.index("## Inferred impact"))
        self.assertIn("Merged accessibility fixes", report)
        self.assertIn("inferred impact:", report)
        self.assertIn("evidence](https://example.test/github/pull/42)", report)

    def test_morning_brief_contains_context_and_read_only_boundary(self):
        with open("fixtures/meetings.json", encoding="utf-8") as handle:
            report = generate_morning_brief(json.load(handle))
        for expected in ("Purpose", "Attendees", "Linked context", "Decisions",
                         "Open questions", "Commitments", "Inaccessible links",
                         "No attendees were contacted"):
            self.assertIn(expected, report)

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

    def test_archive_persists_dated_markdown_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = ReportStore(directory).save("# report\n", NOW, {"fixture": True})
            self.assertTrue(path.exists())
            self.assertEqual(len(ReportStore(directory).reports()), 1)
            self.assertEqual(ReportStore(directory).get(path.relative_to(directory))["markdown"], "# report\n")

    def test_new_launch_and_travel_routines_are_cited_and_bounded(self):
        for fixture, generator, expected in (
            ("fixtures/launch-decoder.json", generate_launch_decoder, "Direct source"),
            ("fixtures/launch-radar.json", generate_launch_radar, "confidence"),
            ("fixtures/travel-logistics.json", generate_travel_logistics_tracker, "Itinerary"),
        ):
            with open(fixture, encoding="utf-8") as handle:
                report = generator(json.load(handle))
            self.assertIn(expected, report)
            self.assertIn("read-only", report.lower())
        with open("fixtures/travel-logistics.json", encoding="UTF-8") as handle:
            report = generate_travel_logistics_tracker(json.load(handle))
        self.assertIn("never", report.lower())

    def test_report_store_keeps_same_second_reports_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(directory)
            first = store.save("# one\n", NOW, {"routine": "launch-radar"})
            second = store.save("# two\n", NOW, {"routine": "launch-radar"})
            self.assertNotEqual(first, second)
            self.assertEqual(len(store.reports()), 2)

    def test_supervisor_plan_dispatch_and_failure_visibility(self):
        dispatcher = SupervisorDispatcher(default_registry())
        result = dispatcher.dispatch("launch-decoder", {"launches": []})
        self.assertIsNotNone(result.report)
        failure = dispatcher.dispatch("launch-decoder", None)
        self.assertIsNotNone(failure.error)

    def test_generation_callable_stores_fixture_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = generate_and_store("fixtures/news.json", directory, now=NOW)
            self.assertTrue(path.exists())
            self.assertIn("Daily global AI news brief", path.read_text(encoding="utf-8"))

    def test_web_requires_token_and_renders_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReportStore(directory)
            store.save("# private\n", NOW)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, "secret"))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = "http://127.0.0.1:%d/" % server.server_port
            try:
                self.assertIn("form", urllib.request.urlopen(url).read().decode("utf-8"))
                request = urllib.request.Request(url, headers={"Authorization": ("B" + "earer") + " secret"})
                body = urllib.request.urlopen(request).read().decode("utf-8")
                self.assertIn("Milou reports", body)
                api = urllib.request.Request(url + "status", headers={"Authorization": ("B" + "earer") + " wrong"})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(api)
                self.assertEqual(error.exception.code, 401)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

    def test_web_login_cookie_and_logout(self):
        with tempfile.TemporaryDirectory() as directory:
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ReportStore(directory), "secret"))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port)
            try:
                body = "token=wrong".encode("ascii")
                connection.request("POST", "/login", body=body,
                                   headers={"Content-Type": "application/x-www-form-urlencoded",
                                            "Content-Length": str(len(body))})
                response = connection.getresponse()
                self.assertEqual(response.status, 401)
                self.assertIn("Invalid token", response.read().decode("utf-8"))

                body = "token=secret".encode("ascii")
                connection.request("POST", "/login", body=body,
                                   headers={"Content-Type": "application/x-www-form-urlencoded",
                                            "Content-Length": str(len(body))})
                response = connection.getresponse()
                self.assertEqual(response.status, 303)
                cookie = response.getheader("Set-Cookie")
                self.assertIn("HttpOnly", cookie)
                self.assertIn("Secure", cookie)
                self.assertIn("SameSite=Strict", cookie)
                session_cookie = cookie.split(";", 1)[0]
                connection.request("GET", "/", headers={"Cookie": session_cookie})
                self.assertEqual(connection.getresponse().status, 200)
                connection.request("POST", "/logout", headers={"Cookie": session_cookie})
                response = connection.getresponse()
                self.assertEqual(response.status, 303)
                connection.request("GET", "/", headers={"Cookie": session_cookie})
                self.assertIn("form", connection.getresponse().read().decode("utf-8"))
            finally:
                connection.close()
                server.shutdown()
                thread.join()
                server.server_close()

    def test_web_fails_closed_without_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ReportStore(directory), None, {}))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen("http://127.0.0.1:%d/" % server.server_port)
                self.assertEqual(error.exception.code, 503)
                request = urllib.request.Request(
                    "http://127.0.0.1:%d/login" % server.server_port,
                    data=b"token=anything",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 503)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
