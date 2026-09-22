"""Tests for sprint scheduling and the write-approval boundary.

These cover the first consequential actions in the project, so most of them
assert that nothing happens: without approval, without a title, or without a
write-scoped credential.
"""


import os
import sys
import unittest
import urllib.error
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import actions
from milou_news.actions import (ApprovalRequired, DryRunDocumentWriter, IncompleteAction,
                                TicketConfig, WriteNotConfigured, ZohoWriter, document_line,
                                draft_ticket, execute, plan_report, shorten)
from milou_news.sprints import MONTHS, next_sprint, sprint_for, sprint_name, upcoming

CONFIG = TicketConfig.from_mapping({
    "portal": "alliedsteel", "project": "5001", "project_name": "Bldg 4 Fabrication",
    "document": "Sprint Ticket Tracker",
})
# 2026-09-29 is a Tuesday, so the example in the brief maps onto it directly.
TUESDAY = date(2026, 9, 29)
WEDNESDAY = date(2026, 9, 30)


class SprintRuleTest(unittest.TestCase):
    """Sprints start Wednesday; a ticket belongs to the next one strictly after."""

    def test_tuesday_work_is_picked_up_the_next_morning(self):
        start, tag = sprint_for(TUESDAY)
        self.assertEqual(start, WEDNESDAY)
        self.assertEqual(tag, "30 SEP SPRINT")

    def test_monday_work_is_picked_up_that_week(self):
        self.assertEqual(next_sprint(date(2026, 9, 28)), WEDNESDAY)

    def test_wednesday_work_has_missed_that_sprint(self):
        # The sprint began this morning, so the work waits a full week.
        self.assertEqual(next_sprint(WEDNESDAY), date(2026, 10, 7))
        self.assertEqual(sprint_for(WEDNESDAY)[1], "7 OCT SPRINT")

    def test_everything_after_tuesday_goes_to_the_following_wednesday(self):
        for offset, day_name in enumerate(("Wednesday", "Thursday", "Friday",
                                           "Saturday", "Sunday"), start=0):
            with self.subTest(day=day_name):
                created = WEDNESDAY + timedelta(days=offset)
                self.assertEqual(next_sprint(created), date(2026, 10, 7))

    def test_every_weekday_lands_on_a_wednesday(self):
        for offset in range(21):
            created = date(2026, 9, 21) + timedelta(days=offset)
            self.assertEqual(next_sprint(created).weekday(), 2)
            self.assertGreater(next_sprint(created), created,
                               "a sprint is always strictly in the future")

    def test_the_tag_has_no_leading_zero_and_is_locale_independent(self):
        self.assertEqual(sprint_name(date(2026, 10, 2)), "2 OCT SPRINT")
        self.assertEqual(sprint_name(date(2026, 10, 14)), "14 OCT SPRINT")
        self.assertEqual(len(MONTHS), 12)

    def test_upcoming_sprints_are_a_week_apart(self):
        sprints = upcoming(TUESDAY, 3)
        self.assertEqual([tag for _start, tag in sprints],
                         ["30 SEP SPRINT", "7 OCT SPRINT", "14 OCT SPRINT"])


class TitleSuggestionTest(unittest.TestCase):

    def test_reply_and_bracket_noise_is_stripped(self):
        self.assertEqual(shorten("RE: [External] Warehouse drawings"), "Warehouse drawings")
        self.assertEqual(shorten("Fwd: Anchor bolt layout"), "Anchor bolt layout")

    def test_leading_filler_is_dropped(self):
        self.assertEqual(shorten("Request for the stamped drawings"), "Stamped drawings")

    def test_the_suggestion_is_short(self):
        long_subject = "Please could you review and confirm the revised anchor bolt layout drawings"
        self.assertLessEqual(len(shorten(long_subject).split()), 6)

    def test_an_empty_subject_yields_no_suggestion(self):
        self.assertEqual(shorten(""), "")
        self.assertEqual(shorten("Re: [FYI]"), "")


class DocumentLineTest(unittest.TestCase):

    def test_only_the_last_four_digits_are_used(self):
        self.assertEqual(document_line("4501993", "Issue drawings"), "1993 - Issue drawings")

    def test_a_short_id_is_used_as_is(self):
        self.assertEqual(document_line("998", "Issue drawings"), "998 - Issue drawings")

    def test_non_numeric_characters_are_ignored(self):
        self.assertEqual(document_line("TASK-4501993", "X"), "1993 - X")


class DraftTest(unittest.TestCase):

    def _plan(self, **overrides):
        kwargs = dict(subject="Warehouse drawings for Bldg 4", sender="M. Castillo",
                      received="Sep 29, 09:40 UTC",
                      body="Could you send the stamped drawings for Building 4?",
                      url="https://outlook.office365.com/mail/id/m2")
        kwargs.update(overrides)
        return draft_ticket(CONFIG, TUESDAY, **kwargs)

    def test_the_ticket_carries_the_required_fields(self):
        create = self._plan().actions[0]
        self.assertEqual(create.fields["status"], "Ready for Development")
        self.assertEqual(create.fields["tag"], "30 SEP SPRINT")
        self.assertEqual(create.fields["release_date"], "2026-09-30")

    def test_the_release_date_matches_the_sprint_tag(self):
        create = self._plan().actions[0]
        start, tag = sprint_for(TUESDAY)
        self.assertEqual(create.fields["release_date"], start.isoformat())
        self.assertEqual(create.fields["tag"], tag)

    def test_the_email_scope_and_citation_are_carried_over(self):
        description = self._plan().actions[0].fields["description"]
        self.assertIn("stamped drawings for Building 4", description)
        self.assertIn("From: M. Castillo", description)
        self.assertIn("Subject: Warehouse drawings for Bldg 4", description)
        self.assertIn("https://outlook.office365.com/mail/id/m2", description)

    def test_the_document_action_targets_the_sprint_heading(self):
        record = self._plan().actions[1]
        self.assertEqual(record.fields["heading"], "30 SEP SPRINT")
        # The line is not pre-formatted: the ticket number does not exist yet,
        # so truncating to its last four digits at draft time is meaningless.
        self.assertNotIn("line", record.fields)

    def test_the_title_is_never_invented(self):
        plan = self._plan()
        self.assertEqual(plan.missing(), ["title"])
        self.assertEqual(plan.actions[0].fields["title"], "")

    def test_supplying_the_title_completes_the_plan(self):
        plan = self._plan().with_inputs(title="Issue Bldg 4 drawings")
        self.assertEqual(plan.missing(), [])
        self.assertEqual(plan.actions[0].fields["title"], "Issue Bldg 4 drawings")


class ApprovalBoundaryTest(unittest.TestCase):
    """Nothing reaches an external system without an explicit, bound approval."""

    def _ready(self):
        return draft_ticket(CONFIG, TUESDAY, subject="Warehouse drawings",
                            sender="M. Castillo",
                            body="Please send them").with_inputs(title="Issue drawings")

    def test_execution_without_approval_is_refused(self):
        with self.assertRaises(ApprovalRequired):
            execute(self._ready(), ZohoWriter(token="t"), DryRunDocumentWriter())

    def test_approval_without_a_title_is_refused(self):
        plan = draft_ticket(CONFIG, TUESDAY, subject="Warehouse drawings",
                            sender="M. Castillo")
        with self.assertRaises(IncompleteAction):
            plan.approve("Deven")

    def test_approval_requires_an_identified_approver(self):
        with self.assertRaises(ApprovalRequired):
            self._ready().approve("")

    def test_editing_a_plan_clears_its_approval(self):
        approved = self._ready().approve("Deven")
        self.assertTrue(approved.approved)
        edited = approved.with_inputs(title="Something else entirely")
        self.assertFalse(edited.approved,
                         "an approved plan must not be editable without re-approval")
        with self.assertRaises(ApprovalRequired):
            execute(edited, ZohoWriter(token="t"), DryRunDocumentWriter())

    def test_a_write_without_a_write_token_fails_closed(self):
        approved = self._ready().approve("Deven")
        with self.assertRaises(WriteNotConfigured):
            execute(approved, ZohoWriter(environ={}), DryRunDocumentWriter())

    def test_the_read_token_cannot_be_used_to_write(self):
        writer = ZohoWriter(environ={"MILOU_ZOHO_TOKEN": "read-only-token"})
        self.assertIsNone(writer.token, "the write path must not fall back to the read token")

    def test_an_unconfigured_portal_is_refused(self):
        plan = draft_ticket(TicketConfig(), TUESDAY, subject="X",
                            sender="M. Castillo").with_inputs(title="X")
        with self.assertRaises(WriteNotConfigured):
            execute(plan.approve("Deven"), ZohoWriter(token="t"), DryRunDocumentWriter())


class ExecutionTest(unittest.TestCase):

    class _Writer:
        def __init__(self, ok=True, identifier="4501993"):
            self.ok, self.identifier, self.calls = ok, identifier, []

        def create_task(self, portal, project, fields):
            self.calls.append((portal, project, dict(fields)))
            return actions.ExecutionResult(
                "zoho.create_task", self.ok,
                "created" if self.ok else "Zoho returned HTTP 403 Forbidden",
                {"ticket_id": self.identifier} if self.ok else {})

    def _approved(self, title="Issue Bldg 4 drawings"):
        return draft_ticket(CONFIG, TUESDAY, subject="Warehouse drawings", sender="M. Castillo",
                            body="Please send them").with_inputs(title=title).approve("Deven")

    def test_the_document_line_uses_the_created_ticket_number(self):
        document = DryRunDocumentWriter()
        results = execute(self._approved(), self._Writer(), document)
        self.assertTrue(all(result.ok for result in results))
        _target, heading, line = document.appended[0]
        self.assertEqual(heading, "30 SEP SPRINT")
        self.assertEqual(line, "1993 - Issue Bldg 4 drawings")

    def test_a_failed_ticket_never_writes_a_document_line(self):
        document = DryRunDocumentWriter()
        results = execute(self._approved(), self._Writer(ok=False), document)
        self.assertFalse(results[0].ok)
        self.assertEqual(len(results), 1, "execution stops rather than half-applying")
        self.assertEqual(document.appended, [],
                         "a tracker line for a ticket that does not exist is worse than none")

    def test_the_writer_receives_the_configured_fields(self):
        writer = self._Writer()
        execute(self._approved(), writer, DryRunDocumentWriter())
        portal, project, fields = writer.calls[0]
        self.assertEqual((portal, project), ("alliedsteel", "5001"))
        self.assertEqual(fields["status"], "Ready for Development")
        self.assertEqual(fields["tag"], "30 SEP SPRINT")

    def test_the_zoho_writer_posts_and_never_echoes_its_token(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["method"] = request.get_method()
            captured["auth"] = request.headers.get("Authorization", "")
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        original = actions.urllib.request.urlopen
        actions.urllib.request.urlopen = fake_urlopen
        try:
            result = ZohoWriter(token="write-secret").create_task("p", "1", {"title": "X"})
        finally:
            actions.urllib.request.urlopen = original
        self.assertEqual(captured["method"], "POST")
        self.assertNotIn("write-secret", result.detail)
        self.assertFalse(result.ok)


class PlanReportTest(unittest.TestCase):

    def test_the_review_report_says_nothing_has_happened(self):
        report = plan_report(draft_ticket(CONFIG, TUESDAY, subject="Warehouse drawings",
                                          sender="M. Castillo"), CONFIG, TUESDAY)
        self.assertIn("Approval required", report.alert)
        self.assertIn("changed nothing", report.alert_detail)
        self.assertEqual(report.tiers[0].label, "Nothing has been created yet")

    def test_the_report_names_the_sprint_and_what_is_missing(self):
        report = plan_report(draft_ticket(CONFIG, TUESDAY, subject="Warehouse drawings",
                                          sender="M. Castillo"), CONFIG, TUESDAY)
        kpis = {kpi.label: kpi.value for kpi in report.kpis}
        self.assertEqual(kpis["Sprint"], "30 SEP SPRINT")
        self.assertEqual(kpis["Status"], "Ready for Development")
        self.assertEqual(kpis["Waiting on you"], "1")


if __name__ == "__main__":
    unittest.main()
