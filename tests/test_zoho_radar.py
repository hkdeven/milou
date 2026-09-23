"""Tests for the Zoho Projects radar and its cross-routine de-duplication."""

import json
import os
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import render_html, zoho
from milou_news.coverage import Coverage, identifiers, normalize
from milou_news.models import default_registry
from milou_news.outlook import FixtureGraph, InboxConfig, build_outlook_report
from milou_news.supervisor import SupervisorDispatcher
from milou_news.zoho import (FixtureZoho, ROUTINE_NAME, ZohoApi, ZohoConfig,
                             build_zoho_report, coverage_from, generate_zoho_radar,
                             prepare)

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
ME = "deven@example.test"
NOW = datetime(2026, 9, 22, 8, 0, 0, tzinfo=timezone.utc)
PORTAL = "p1"


def _activity(ident, action, actor="other@example.test", item_id="4400001",
              item_name="Some tracked item", hours=2, assignee=ME, content="", kind="Task"):
    return {"id": ident, "activity_for": kind, "activity_type": action,
            "activity_by": actor, "item_id": item_id, "item_name": item_name,
            "assignee": assignee, "content": content,
            "activity_time": (NOW - timedelta(hours=hours)).isoformat(),
            "link": {"self": {"url": "https://projects.zoho.com/x/%s" % item_id}}}


def _config(**overrides):
    base = {"portal": PORTAL, "me": ME, "window_hours": 72, "max_items": 10}
    base.update(overrides)
    return ZohoConfig.from_mapping(base)


def _api(activities, config=None, errors=None):
    config = config or _config()
    return FixtureZoho({
        config.endpoint("projects").format(portal=PORTAL): {
            "projects": [{"id_string": "9", "name": "Project Nine"}]},
        config.endpoint("activities").format(portal=PORTAL, project="9"): {
            "activities": list(activities)},
    }, errors or {})


def _report(activities, config=None, errors=None):
    config = config or _config()
    return build_zoho_report(_api(activities, config, errors), config, now=NOW)


def _tier(report, label):
    return next((tier for tier in report.tiers if tier.label == label), None)


def _committed(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


class CommentPriorityTest(unittest.TestCase):
    """Comments lead, because they usually need a response."""

    def test_a_comment_is_the_top_tier(self):
        report = _report([_activity("1", "Comment added", content="Thoughts?")])
        self.assertEqual(report.tiers[0].label, "Comments")
        self.assertEqual(report.tiers[0].rows[0].tone, "critical")

    def test_a_comment_without_a_question_still_leads(self):
        # The user responds to comments whether or not they are direct questions,
        # so a comment is never demoted for lacking a question mark.
        report = _report([_activity("1", "Comment added", content="Adding notes for the record.")])
        self.assertEqual(report.tiers[0].label, "Comments")

    def test_a_comment_outranks_an_assignment_made_more_recently(self):
        report = _report([_activity("1", "Comment added", hours=20, content="Please look."),
                          _activity("2", "Assignee changed", hours=1, item_id="4400002")])
        self.assertEqual([tier.label for tier in report.tiers],
                         ["Comments", "Assigned to you"])

    def test_a_comment_on_another_persons_item_is_still_reported(self):
        report = _report([_activity("1", "Comment added", assignee="someone@example.test",
                                    content="FYI")])
        self.assertIsNotNone(_tier(report, "Comments"))


class ExclusionTest(unittest.TestCase):

    def test_your_own_activity_is_not_news(self):
        report = _report([_activity("1", "Comment added", actor=ME, content="My own note.")])
        self.assertTrue(report.is_empty)
        counted = {s.label: int(s.value) for b in report.bars for s in b.segments}
        self.assertEqual(counted["your own activity"], 1)

    def test_your_own_activity_can_be_opted_back_in(self):
        report = _report([_activity("1", "Comment added", actor=ME, content="Mine.")],
                         config=_config(include_own_activity=True))
        self.assertFalse(report.is_empty)

    def test_activity_outside_the_window_is_dropped_and_counted(self):
        report = _report([_activity("1", "Comment added", hours=400, content="Old.")])
        counted = {s.label: int(s.value) for b in report.bars for s in b.segments}
        self.assertEqual(counted["outside the 72-hour window"], 1)

    def test_status_changes_on_other_peoples_items_are_dropped(self):
        report = _report([_activity("1", "Status changed to Closed",
                                    assignee="someone@example.test")])
        counted = {s.label: int(s.value) for b in report.bars for s in b.segments}
        self.assertEqual(counted["not involving you"], 1)

    def test_output_is_capped(self):
        activities = [_activity(str(i), "Comment added", item_id="440%04d" % i,
                                hours=i + 1, content="Please look.") for i in range(20)]
        report = _report(activities, config=_config(max_items=3))
        self.assertEqual(sum(tier.count for tier in report.tiers), 3)
        self.assertIn("17 more", report.tiers[0].footnote)


class AccessTest(unittest.TestCase):

    def test_missing_token_fails_closed(self):
        result = ZohoApi(environ={}).get("/restapi/portals/")
        self.assertIsNone(result.data, "no token must mean no data, never a silent empty report")
        self.assertIn("MILOU_ZOHO_TOKEN", result.error)
        self.assertIn("docs/going-live.md", result.error)

    def test_only_get_is_issued_and_the_token_is_never_echoed(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["method"] = request.get_method()
            captured["auth"] = request.headers.get("Authorization", "")
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

        original = zoho.urllib.request.urlopen
        zoho.urllib.request.urlopen = fake_urlopen
        try:
            result = ZohoApi(token="zoho-secret").get("/restapi/portals/")
        finally:
            zoho.urllib.request.urlopen = original
        self.assertEqual(captured["method"], "GET")
        self.assertIn("Zoho-oauthtoken", captured["auth"])
        self.assertNotIn("zoho-secret", result.error)
        self.assertIn("401", result.error)

    def test_access_failures_are_promoted(self):
        config = _config()
        report = build_zoho_report(
            _api([], config, errors={config.endpoint("projects").format(portal=PORTAL): "HTTP 403"}),
            config, now=NOW)
        self.assertIn("incomplete", report.alert)
        self.assertIn("403", report.alert_detail)

    def test_no_portal_means_nothing_is_requested(self):
        report = build_zoho_report(_api([]), _config(portal=""), now=NOW)
        self.assertIn("no Zoho portal configured", report.alert_detail)

    def test_endpoints_are_configuration_not_constants(self):
        config = _config(endpoints={"projects": "/custom/{portal}/p/"})
        self.assertEqual(config.endpoint("projects"), "/custom/{portal}/p/")
        self.assertEqual(config.endpoint("activities"), zoho.DEFAULT_ENDPOINTS["activities"])

    def test_the_boundary_is_always_stated(self):
        self.assertIn("never comments", _report([]).boundary)


class CoverageTest(unittest.TestCase):
    """Only what the radar demonstrably reported may silence a notification."""

    def test_identifiers_ignore_short_numbers(self):
        self.assertEqual(identifiers("Task #4501001 due Q3 2026"), frozenset({"4501001", "2026"}))
        self.assertEqual(identifiers("bug 12"), frozenset())

    def test_coverage_matches_by_identifier(self):
        cover = Coverage("r", keys=frozenset({"4501001"}), domains=("zohoprojects.com",))
        self.assertTrue(cover.matches("Comment on Task #4501001"))
        self.assertFalse(cover.matches("Comment on Task #9999999"))

    def test_coverage_matches_by_title_when_no_identifier_is_quoted(self):
        cover = Coverage("r", titles=(normalize("Stamp and issue Building 4 drawings"),))
        self.assertTrue(cover.matches("Re: Stamp and issue Building 4 drawings"))
        self.assertFalse(cover.matches("Re: something unrelated entirely"))

    def test_coverage_only_owns_its_own_domains(self):
        cover = Coverage("r", domains=("zohoprojects.com",))
        self.assertTrue(cover.owns_sender("notifications@zohoprojects.com"))
        self.assertFalse(cover.owns_sender("notifications@github.com"))

    def test_coverage_publishes_only_collected_records(self):
        config = _config()
        _now, activities, _errors, _count = prepare(
            _api([_activity("1", "Comment added", item_id="4501001",
                            item_name="Stamp and issue Building 4 drawings")], config), config, NOW)
        cover = coverage_from(activities, config)
        self.assertIn("4501001", cover.keys)
        self.assertNotIn("4777123", cover.keys)
        self.assertEqual(cover.routine, ROUTINE_NAME)


class DeduplicationTest(unittest.TestCase):
    """The same event must not be reported by both routines."""

    def _mailbox(self):
        return _committed("outlook.json")

    def _zoho_coverage(self):
        fixture = _committed("zoho.json")
        config = ZohoConfig.from_mapping(fixture["config"])
        _now, activities, _errors, _count = prepare(
            FixtureZoho(fixture["responses"]), config, NOW)
        return coverage_from(activities, config)

    def _inbox(self, coverages):
        fixture = self._mailbox()
        return build_outlook_report(
            FixtureGraph(fixture["responses"]), InboxConfig.from_mapping(fixture["config"]),
            now=NOW, coverages=coverages)

    def test_without_coverage_a_zoho_notice_is_merely_automated(self):
        counted = {s.label: int(s.value) for b in self._inbox(()).bars for s in b.segments}
        self.assertEqual(counted["automated sender"], 4)
        self.assertNotIn("already reported by zoho-projects-radar", counted)

    def test_a_reported_event_is_suppressed_with_a_traceable_reason(self):
        report = self._inbox([self._zoho_coverage()])
        counted = {s.label: int(s.value) for b in report.bars for s in b.segments}
        self.assertEqual(counted["already reported by zoho-projects-radar"], 1)

    def test_an_unmatched_notification_becomes_a_visible_coverage_gap(self):
        report = self._inbox([self._zoho_coverage()])
        counted = {s.label: int(s.value) for b in report.bars for s in b.segments}
        self.assertEqual(counted["notification from zoho-projects-radar not matched to a tracked item"], 1)
        self.assertIn("coverage gap", report.alert)
        self.assertIn("missing a project", report.alert_detail)

    def test_a_coverage_gap_is_not_called_an_access_problem(self):
        report = self._inbox([self._zoho_coverage()])
        self.assertNotIn("access problem", report.alert)

    def test_suppressed_mail_never_becomes_an_action_item(self):
        report = self._inbox([self._zoho_coverage()])
        titles = " ".join(row.title for tier in report.tiers for row in tier.rows)
        self.assertNotIn("Zoho Projects", titles)

    def test_de_duplication_does_not_change_the_human_mail(self):
        without = self._inbox(())
        with_coverage = self._inbox([self._zoho_coverage()])
        self.assertEqual([tier.label for tier in without.tiers],
                         [tier.label for tier in with_coverage.tiers])
        self.assertEqual(sum(t.count for t in without.tiers),
                         sum(t.count for t in with_coverage.tiers))


class WiringTest(unittest.TestCase):

    def test_the_routine_is_registered_and_dispatchable(self):
        self.assertIn(ROUTINE_NAME, default_registry().names())
        result = SupervisorDispatcher(default_registry()).dispatch(
            ROUTINE_NAME, _committed("zoho.json"))
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.structured)
        self.assertEqual(result.structured.routine, ROUTINE_NAME)

    def test_a_scheduled_inbox_run_can_carry_zoho_coverage(self):
        payload = dict(_committed("outlook.json"), coverage={"zoho": _committed("zoho.json")})
        result = SupervisorDispatcher(default_registry()).dispatch(
            "outlook-inbox-monitor", payload)
        self.assertIsNone(result.error)
        self.assertIn("already reported by zoho-projects-radar", result.report)

    def test_the_committed_fixture_renders_in_both_formats(self):
        fixture = _committed("zoho.json")
        config = ZohoConfig.from_mapping(fixture["config"])
        report = build_zoho_report(FixtureZoho(fixture["responses"]), config, now=NOW)
        self.assertIn("Comments", generate_zoho_radar(None, config, report=report))
        self.assertIn("Zoho Projects radar", render_html.report_page(report))


if __name__ == "__main__":
    unittest.main()
