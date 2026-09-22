"""Tests for the read-only Outlook inbox monitor.

The routine's whole purpose is to be lossy on purpose, so most of these assert
what it *refuses* to show and that the refusals stay countable.
"""

import json
import os
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import outlook, render_html
from milou_news.outlook import (FixtureGraph, GraphApi, InboxConfig, ROUTINE_NAME,
                                build_outlook_report, business_days_between,
                                generate_outlook_monitor)

NOW = datetime(2026, 9, 22, 8, 0, 0, tzinfo=timezone.utc)
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
ME = "deven@example.test"


def _inbox_path(config):
    return outlook._folder_path("inbox", config, "receivedDateTime")


def _sent_path(config):
    return outlook._folder_path("sentitems", config, "sentDateTime")


def _msg(ident, conversation, subject, preview, sender=None, to=(ME,), cc=(),
         hours=2, classification="focused", importance="normal", sent=False):
    when = (NOW - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    body = {
        "id": ident, "conversationId": conversation, "subject": subject,
        "from": {"emailAddress": {"address": sender or "them@example.test",
                                  "name": "" if sender else "Them"}},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
        "bodyPreview": preview, "importance": importance,
        "inferenceClassification": classification,
        "webLink": "https://outlook.office365.com/mail/id/%s" % ident,
    }
    body["sentDateTime" if sent else "receivedDateTime"] = when
    return body


def _api(inbox=(), sent=(), config=None, errors=None):
    config = config or InboxConfig()
    return FixtureGraph({
        "/me": {"mail": ME, "userPrincipalName": ME},
        _inbox_path(config): {"value": list(inbox)},
        _sent_path(config): {"value": list(sent)},
    }, errors or {})


def _report(inbox=(), sent=(), config=None, errors=None):
    config = config or InboxConfig()
    return build_outlook_report(_api(inbox, sent, config, errors), config, now=NOW)


def _tier(report, label):
    return next((tier for tier in report.tiers if tier.label == label), None)


def _committed_fixture():
    with open(os.path.join(FIXTURES, "outlook.json"), encoding="utf-8") as handle:
        return json.load(handle)


class BoundedOutputTest(unittest.TestCase):
    """A busier inbox must not produce a longer report."""

    def test_output_is_capped_and_the_overflow_is_reported(self):
        inbox = [_msg("m%d" % i, "c%d" % i, "Ask %d" % i, "Could you review this?", hours=i + 1)
                 for i in range(20)]
        report = _report(inbox, config=InboxConfig(max_items=3))
        self.assertEqual(sum(tier.count for tier in report.tiers), 3)
        self.assertIn("17 more", _tier(report, "Waiting on your reply").footnote)
        self.assertIn("17 held back", report.boundary)

    def test_report_length_does_not_track_inbox_volume(self):
        small = _report([_msg("m1", "c1", "Ask", "Could you review this?")])
        big = _report([_msg("m%d" % i, "c%d" % i, "Ask %d" % i, "Could you review this?",
                            hours=i + 1) for i in range(40)])
        self.assertLessEqual(sum(t.count for t in big.tiers), InboxConfig().max_items)
        self.assertGreaterEqual(sum(t.count for t in big.tiers), sum(t.count for t in small.tiers))

    def test_cap_must_be_bounded_by_configuration(self):
        with self.assertRaises(ValueError):
            InboxConfig.from_mapping({"max_items": 0})
        with self.assertRaises(ValueError):
            InboxConfig.from_mapping({"max_items": 500})

    def test_thresholds_are_configurable_not_hard_coded(self):
        config = InboxConfig.from_mapping({"follow_up_days": 5, "max_items": 4,
                                           "lookback_days": 30})
        self.assertEqual((config.follow_up_days, config.max_items, config.lookback_days),
                         (5, 4, 30))


class SilenceTest(unittest.TestCase):
    """A quiet mailbox is a success state, never padded to look useful."""

    def test_nothing_to_do_produces_an_empty_report_with_a_note(self):
        report = _report()
        self.assertTrue(report.is_empty)
        self.assertIn("Nothing in the last", report.empty_note)
        self.assertIn("No activity to report", render_html.report_page(report))

    def test_a_full_but_irrelevant_inbox_still_produces_nothing(self):
        inbox = [
            _msg("m1", "c1", "Newsletter", "This week in steel.",
                 sender="newsletter@vendor.example.test"),
            _msg("m2", "c2", "Receipt", "Do not reply to this message.",
                 sender="no-reply@portal.example.test"),
            _msg("m3", "c3", "FYI thread", "Can you all confirm?",
                 to=("team@example.test",), cc=(ME,)),
        ]
        report = _report(inbox)
        self.assertTrue(report.is_empty, "none of this needs the user")
        self.assertEqual({kpi.label: kpi.value for kpi in report.kpis}["Excluded"], "3")


class ExclusionTest(unittest.TestCase):
    """Excluded mail is counted, never listed."""

    def test_each_exclusion_reason_is_counted(self):
        inbox = [
            _msg("m1", "c1", "CC only", "Could you confirm?", to=("team@example.test",), cc=(ME,)),
            _msg("m2", "c2", "Automated", "Could you confirm?", sender="no-reply@x.example.test"),
            _msg("m3", "c3", "Other", "Could you confirm?", classification="other"),
            _msg("m4", "c4", "No ask", "Sharing these notes for the record."),
            _msg("m5", "c5", "Answered", "Could you confirm?", hours=6),
        ]
        sent = [_msg("s5", "c5", "RE: Answered", "Confirmed, thanks.", sender=ME,
                     to=("them@example.test",), hours=2, sent=True)]
        report = _report(inbox, sent)
        counted = {segment.label: int(segment.value)
                   for bar in report.bars for segment in bar.segments}
        self.assertEqual(counted["you were only CC'd"], 1)
        self.assertEqual(counted["automated sender"], 1)
        self.assertEqual(counted["Focused Inbox: other"], 1)
        self.assertEqual(counted["no request detected"], 1)
        self.assertEqual(counted["you already replied"], 1)

    def test_excluded_subjects_never_appear_in_the_report(self):
        inbox = [_msg("m1", "c1", "CONFIDENTIAL PAYROLL", "Could you confirm?",
                      to=("team@example.test",), cc=(ME,))]
        page = render_html.report_page(_report(inbox))
        self.assertNotIn("CONFIDENTIAL PAYROLL", page)

    def test_muted_senders_are_dropped(self):
        inbox = [_msg("m1", "c1", "Ask", "Could you confirm?", sender="noisy@example.test")]
        report = _report(inbox, config=InboxConfig(mute_senders=("noisy@example.test",)))
        self.assertTrue(report.is_empty)

    def test_focused_other_can_be_opted_back_in(self):
        inbox = [_msg("m1", "c1", "Ask", "Could you confirm?", classification="other")]
        self.assertTrue(_report(inbox).is_empty)
        self.assertFalse(_report(inbox, config=InboxConfig(include_other=True)).is_empty)


class TieringTest(unittest.TestCase):

    def test_blocked_outranks_a_plain_request(self):
        inbox = [
            _msg("m1", "c1", "Question", "Could you send the drawings?", hours=1),
            _msg("m2", "c2", "Sign-off", "We cannot proceed without your approval.", hours=40),
        ]
        report = _report(inbox)
        # The blocked message is older, and still comes first.
        self.assertEqual(report.tiers[0].label, "Blocked on you")
        self.assertEqual(report.tiers[0].rows[0].tone, "critical")
        self.assertEqual(report.tiers[1].label, "Waiting on your reply")

    def test_common_blocked_phrasings_all_reach_the_top_tier(self):
        for phrase in ("We cannot proceed without your approval.",
                       "I can't move forward until you confirm.",
                       "We are blocked on you for the drawings.",
                       "This is pending your review.",
                       "Nothing ships without your sign-off.",
                       "We are waiting on you to decide."):
            with self.subTest(phrase=phrase):
                report = _report([_msg("m1", "c1", "Status", phrase)])
                self.assertEqual(report.tiers[0].label, "Blocked on you", phrase)

    def test_every_row_says_why_it_surfaced(self):
        report = _report([_msg("m1", "c1", "Ask", "Could you send the drawings?")])
        row = report.tiers[0].rows[0]
        self.assertTrue(row.flags)
        self.assertIn("addressed directly to you", row.flags[0].label)
        self.assertIn("no reply from you", row.flags[0].label)

    def test_a_row_quotes_the_sentence_that_triggered_it(self):
        report = _report([_msg("m1", "c1", "Ask",
                               "Hope you are well. Could you send the stamped drawings? Thanks.")])
        self.assertEqual(report.tiers[0].rows[0].summary,
                         "Could you send the stamped drawings?")

    def test_one_line_per_conversation(self):
        inbox = [_msg("m1", "c1", "Ask", "Could you confirm?", hours=3),
                 _msg("m2", "c1", "Ask again", "Could you confirm?", hours=1)]
        self.assertEqual(sum(tier.count for tier in _report(inbox).tiers), 1)


class FollowUpTest(unittest.TestCase):
    """Only chase mail where they owe the user, and only after the threshold."""

    SENT_ASK = dict(sender=ME, to=("them@example.test",), sent=True)

    def test_a_promise_is_owed_by_the_user_and_never_chased(self):
        sent = [_msg("s1", "c1", "Certificate", "I'll send the certificate on Monday.",
                     hours=120, **self.SENT_ASK)]
        report = _report(sent=sent)
        self.assertIsNotNone(_tier(report, "You promised"))
        self.assertIsNone(_tier(report, "No reply yet"),
                          "the user owes them, so there is nothing to chase")

    def test_a_closed_courtesy_thread_is_not_chased(self):
        sent = [_msg("s1", "c1", "RE: Notes", "Noted, thanks for writing these up.",
                     hours=120, **self.SENT_ASK)]
        report = _report(sent=sent)
        self.assertTrue(report.is_empty)
        counted = {segment.label: int(segment.value)
                   for bar in report.bars for segment in bar.segments}
        self.assertEqual(counted["sent mail that asked nothing"], 1)

    def test_an_unanswered_ask_is_chased_once_past_the_threshold(self):
        sent = [_msg("s1", "c1", "Quote", "Let me know if the schedule still works.",
                     hours=120, **self.SENT_ASK)]
        tier = _tier(_report(sent=sent), "No reply yet")
        self.assertIsNotNone(tier)
        self.assertIn("threshold is 2 business days", tier.rows[0].flags[1].label)

    def test_an_ask_below_the_threshold_is_held_back(self):
        sent = [_msg("s1", "c1", "Quote", "Let me know if that works.", hours=3, **self.SENT_ASK)]
        report = _report(sent=sent)
        self.assertIsNone(_tier(report, "No reply yet"))
        counted = {segment.label: int(segment.value)
                   for bar in report.bars for segment in bar.segments}
        self.assertEqual(counted["sent too recently to chase"], 1)

    def test_the_threshold_is_respected_when_changed(self):
        sent = [_msg("s1", "c1", "Quote", "Let me know if that works.", hours=72, **self.SENT_ASK)]
        self.assertIsNotNone(_tier(_report(sent=sent, config=InboxConfig(follow_up_days=2)),
                                   "No reply yet"))
        self.assertIsNone(_tier(_report(sent=sent, config=InboxConfig(follow_up_days=10)),
                                "No reply yet"))

    def test_friday_mail_is_not_chased_on_sunday(self):
        friday = datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(business_days_between(friday, sunday), 0)
        self.assertEqual(business_days_between(friday, datetime(2026, 9, 22, 9, 0,
                                                                tzinfo=timezone.utc)), 2)

    def test_a_reply_retires_the_follow_up(self):
        sent = [_msg("s1", "c1", "Quote", "Let me know if that works.", hours=120, **self.SENT_ASK)]
        inbox = [_msg("m1", "c1", "RE: Quote", "Looks good.", hours=4)]
        self.assertIsNone(_tier(_report(inbox, sent), "No reply yet"))


class ReadOnlyTest(unittest.TestCase):

    def test_missing_token_fails_closed(self):
        result = GraphApi(environ={}).get("/me")
        self.assertIn("MILOU_OUTLOOK_TOKEN", result.error)
        self.assertIn("fails closed", result.error)
        self.assertIsNone(result.data)

    def test_only_get_is_issued_and_the_token_is_never_echoed(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["method"] = request.get_method()
            captured["headers"] = dict(request.headers)
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        original = outlook.urllib.request.urlopen
        outlook.urllib.request.urlopen = fake_urlopen
        try:
            result = GraphApi(token="super-secret-token").get("/me")
        finally:
            outlook.urllib.request.urlopen = original
        self.assertEqual(captured["method"], "GET")
        self.assertIn("super-secret-token", str(captured["headers"]))
        self.assertNotIn("super-secret-token", result.error)
        self.assertIn("403", result.error)

    def test_access_failures_are_promoted_not_rendered_as_an_empty_inbox(self):
        config = InboxConfig()
        report = build_outlook_report(
            _api(config=config, errors={_inbox_path(config): "HTTP 403 Forbidden"}),
            config, now=NOW)
        self.assertIn("incomplete", report.alert)
        self.assertIn("403", report.alert_detail)

    def test_the_boundary_is_always_stated(self):
        self.assertIn("never sends", _report().boundary)


class CommittedFixtureTest(unittest.TestCase):

    def test_the_shipped_fixture_produces_a_short_actionable_report(self):
        fixture = _committed_fixture()
        config = InboxConfig.from_mapping(fixture["config"])
        report = build_outlook_report(FixtureGraph(fixture["responses"]), config, now=NOW)
        self.assertEqual(report.routine, ROUTINE_NAME)
        self.assertEqual([tier.label for tier in report.tiers],
                         ["Blocked on you", "Waiting on your reply", "You promised", "No reply yet"])
        self.assertEqual(sum(tier.count for tier in report.tiers), 4,
                         "ten messages must not become ten lines")
        markdown = generate_outlook_monitor(None, config, report=report)
        self.assertIn("Blocked on you", markdown)
        self.assertIn("Why mail was excluded", markdown)

    def test_the_fixture_report_renders_as_html(self):
        fixture = _committed_fixture()
        config = InboxConfig.from_mapping(fixture["config"])
        page = render_html.report_page(
            build_outlook_report(FixtureGraph(fixture["responses"]), config, now=NOW))
        self.assertIn("Outlook inbox monitor", page)
        self.assertIn("Read-only", page)
        self.assertIn("Why mail was excluded", page)


if __name__ == "__main__":
    unittest.main()
