"""Tests for composing a ticket description, and for the context reply.

Two things are being defended here. First, that a description says who asked,
who actually hit the problem and when — and that when the email does not say,
the gap is *visible* rather than quietly filled in. Second, that the reply asks
for what is missing and not for what the sender already told us.
"""


import json
import os
import sys
import unittest
import urllib.error
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import actions, intake
from milou_news.actions import (DryRunDocumentWriter, DryRunMailWriter, IncompleteAction,
                                OUTLOOK_WRITE_TOKEN_ENV, OutlookReplyWriter, TicketConfig,
                                WriteNotConfigured, draft_context_reply, draft_ticket, execute,
                                reply_plan_report)
from milou_news.intake import (KIND_BUG, KIND_REQUEST, Intake, classify, compose_description,
                               compose_reply, context_questions, extract_links,
                               extract_reported_on, extract_reporter, read_email,
                               reference_links, reply_all_recipients, reply_subject,
                               strip_history, summarize)

TUESDAY = date(2026, 9, 29)
CONFIG = TicketConfig.from_mapping({
    "portal": "alliedsteel", "project": "5001", "project_name": "Bldg 4 Fabrication",
    "document": "Sprint Ticket Tracker", "signature": "Deven",
})

BUG_EMAIL = """Hi Deven,

We have a problem on the Bldg 4 Fabrication project. Our estimator Jane Kowalski
reported that the weight rollup on the takeoff screen is wrong - it shows 0 lbs
for any nested assembly. She hit it on Monday.

The total must include the nested weights before we can quote.

Spec: https://example.test/sites/eng/takeoff-spec.docx

Thanks,
Marco
"""

REQUEST_EMAIL = ("Hi Deven, we would like a new report showing the backlog by sprint, "
                 "so the Monday meeting stops being guesswork. Thanks, Priya")


class ClassificationTest(unittest.TestCase):

    def test_a_defect_is_a_bug(self):
        for text in ("the export is broken", "it throws an exception on save",
                     "the totals are wrong", "users can't log in", "we get a 500 error",
                     "steps to reproduce are below"):
            with self.subTest(text=text):
                self.assertEqual(classify("", text), KIND_BUG)

    def test_an_ask_for_something_new_is_a_request(self):
        for text in ("we would like a new report", "could we have an extra field",
                     "requesting a change to the layout", "ability to export to CSV"):
            with self.subTest(text=text):
                self.assertEqual(classify("", text), KIND_REQUEST)

    def test_a_tie_goes_to_bug(self):
        # A bug needs two extra facts, so guessing "request" loses information
        # that guessing "bug" merely asks for.
        self.assertEqual(classify("", "the new report is broken"), KIND_BUG)


class ExtractionTest(unittest.TestCase):

    def test_quoted_history_and_signature_are_dropped(self):
        body = ("Please check the totals.\nThanks,\nMarco\n\n"
                "-----Original Message-----\nFrom: someone\nEntirely different subject")
        cleaned = strip_history(body)
        self.assertIn("Please check the totals", cleaned)
        self.assertNotIn("Entirely different subject", cleaned)
        self.assertNotIn("Marco", cleaned)

    def test_quoted_lines_are_dropped(self):
        self.assertNotIn("old text", strip_history("New question?\n> old text"))

    def test_links_are_collected_without_trailing_punctuation(self):
        links = extract_links("See https://example.test/a.docx, and https://example.test/b.png.")
        self.assertEqual(links, ("https://example.test/a.docx", "https://example.test/b.png"))

    def test_a_repeated_link_is_listed_once(self):
        self.assertEqual(extract_links("https://x.test/a https://x.test/a"), ("https://x.test/a",))

    def test_links_are_referenced_rather_than_repeated_in_the_context(self):
        text = reference_links("The spec is at https://x.test/a and the shot at https://x.test/b",
                               ("https://x.test/a", "https://x.test/b"))
        self.assertEqual(text, "The spec is at [doc 1] and the shot at [doc 2]")

    def test_a_load_bearing_sentence_survives_the_budget(self):
        filler = "We spoke about this yesterday. " * 20
        summary = summarize(filler + "The totals must include nested weights.", budget=80)
        self.assertIn("must include nested weights", summary)

    def test_the_reporter_is_found_in_several_phrasings(self):
        for text in ("reported by Jane Kowalski", "raised by Jane Kowalski",
                     "on behalf of Jane Kowalski", "our estimator Jane Kowalski reported",
                     "Jane Kowalski is seeing this"):
            with self.subTest(text=text):
                self.assertEqual(extract_reporter(text), "Jane Kowalski")

    def test_a_relative_date_is_resolved_against_the_email(self):
        # "yesterday" on a ticket read three weeks later is worse than no date.
        self.assertEqual(extract_reported_on("she hit it yesterday", date(2026, 9, 29)),
                         "yesterday (2026-09-28)")
        self.assertEqual(extract_reported_on("broke on Monday", date(2026, 9, 29)),
                         "Monday (2026-09-28)")

    def test_an_absolute_date_is_kept_as_written(self):
        self.assertEqual(extract_reported_on("failing since 24 Sep", date(2026, 9, 29)), "24 Sep")

    def test_nothing_is_invented_when_the_email_says_nothing(self):
        found = read_email("Export is broken", "The export is broken.", "Marco", TUESDAY)
        self.assertEqual(found.reported_by, "")
        self.assertEqual(found.reported_on, "")
        self.assertEqual(found.unknown(), ["reported_by", "reported_on"])

    def test_extracted_values_are_marked_as_guesses(self):
        found = read_email("Bug", BUG_EMAIL, "Marco Castillo", TUESDAY)
        self.assertIn("reported_by", found.guessed)
        self.assertIn("reported_on", found.guessed)
        # The sender is not a guess: it is who the mail came from.
        self.assertNotIn("requested_by", found.guessed)


class DescriptionTest(unittest.TestCase):

    def _bug(self):
        return read_email("Takeoff weight rollup is wrong", BUG_EMAIL, "Marco Castillo", TUESDAY)

    def test_a_bug_carries_reporter_and_report_date(self):
        text = compose_description(self._bug(), "Takeoff rollup", "Marco Castillo",
                                   "Sep 29, 09:40 UTC", "https://mail.test/m2")
        self.assertIn("Type: Bug report", text)
        self.assertIn("Requested by: Marco Castillo", text)
        self.assertIn("Reported by: Jane Kowalski", text)
        self.assertIn("Reported on: Monday (2026-09-28)", text)

    def test_a_request_carries_only_the_requester(self):
        text = compose_description(read_email("New backlog report", REQUEST_EMAIL, "Priya Raman",
                                              TUESDAY))
        self.assertIn("Requested by: Priya Raman", text)
        self.assertNotIn("Reported by", text)
        self.assertNotIn("Reported on", text)

    def test_a_missing_fact_is_visible_rather_than_blank(self):
        text = compose_description(read_email("Export broken", "The export is broken.", "Marco",
                                              TUESDAY))
        self.assertIn("Reported by: (not stated in the email", text)

    def test_supporting_documents_are_listed_in_their_own_section(self):
        text = compose_description(self._bug())
        self.assertIn("Supporting documents", text)
        self.assertIn("- https://example.test/sites/eng/takeoff-spec.docx", text)

    def test_the_absence_of_documents_is_stated(self):
        self.assertIn("- none shared in the email",
                      compose_description(read_email("X", "Please fix the total.", "Marco", TUESDAY)))

    def test_the_citation_back_to_the_email_survives(self):
        text = compose_description(self._bug(), "Takeoff rollup", "Marco Castillo",
                                   "Sep 29, 09:40 UTC", "https://mail.test/m2")
        self.assertIn("From: Marco Castillo", text)
        self.assertIn("Subject: Takeoff rollup", text)
        self.assertIn("Source: https://mail.test/m2", text)


class BugTicketTest(unittest.TestCase):
    """A bug ticket is incomplete until it says who reported it, and when."""

    def _plan(self, body=BUG_EMAIL, subject="Takeoff weight rollup is wrong"):
        return draft_ticket(CONFIG, TUESDAY, subject=subject, sender="Marco Castillo",
                            received="Sep 29, 09:40 UTC", body=body,
                            url="https://mail.test/m2", received_date=TUESDAY)

    def test_an_unstated_reporter_blocks_the_plan(self):
        plan = self._plan(body="The export is broken and errors out.")
        self.assertEqual(plan.missing(), ["reported_by", "reported_on", "title"])

    def test_supplying_the_missing_facts_completes_it(self):
        plan = self._plan(body="The export is broken.").with_inputs(
            title="Fix export", reported_by="Jane Kowalski", reported_on="2026-09-28")
        self.assertEqual(plan.missing(), [])

    def test_correcting_a_name_rewrites_the_description(self):
        # The description is composed, not pasted, so it cannot disagree with
        # the fields shown beside it.
        plan = self._plan().with_inputs(title="Fix rollup", reported_by="Jane Q. Kowalski")
        description = plan.actions[0].fields["description"]
        self.assertIn("Reported by: Jane Q. Kowalski", description)
        self.assertNotIn("Reported by: Jane Kowalski\n", description)

    def test_a_request_needs_no_reporter(self):
        plan = draft_ticket(CONFIG, TUESDAY, subject="New backlog report", sender="Priya Raman",
                            body=REQUEST_EMAIL, received_date=TUESDAY)
        self.assertEqual(plan.missing(), ["title"])

    def test_the_owner_defaults_to_unassigned(self):
        self.assertEqual(self._plan().actions[0].fields["owner"], "")

    def test_a_configured_owner_is_carried_and_still_editable(self):
        config = TicketConfig.from_mapping({"portal": "p", "project": "1", "default_owner": "42"})
        plan = draft_ticket(config, TUESDAY, subject="X", sender="Marco", body="please add a field")
        self.assertEqual(plan.actions[0].fields["owner"], "42")
        self.assertEqual(plan.with_inputs(owner="").actions[0].fields["owner"], "")


class ContextReplyTest(unittest.TestCase):

    def _reply(self, body=BUG_EMAIL, **overrides):
        kwargs = dict(subject="Takeoff weight rollup is wrong", sender="Marco Castillo",
                      sender_address="marco@vendor.test",
                      to=("deven@alliedbuildings.com", "ops@alliedbuildings.com"),
                      cc=("pm@vendor.test",), mailbox="deven@alliedbuildings.com",
                      message_id="m2", body=body, received_date=TUESDAY)
        kwargs.update(overrides)
        return draft_context_reply(CONFIG, **kwargs)

    def test_it_replies_to_everyone_except_you(self):
        fields = self._reply().actions[0].fields
        self.assertEqual(fields["to"], "marco@vendor.test\nops@alliedbuildings.com")
        self.assertEqual(fields["cc"], "pm@vendor.test")

    def test_the_sender_leads_and_duplicates_collapse(self):
        primary, copied = reply_all_recipients(
            "marco@vendor.test", ("MARCO@vendor.test", "ops@x.test"),
            ("ops@x.test", "me@x.test"), mailbox="me@x.test")
        self.assertEqual(primary, ("marco@vendor.test", "ops@x.test"))
        self.assertEqual(copied, ())

    def test_the_subject_is_not_double_prefixed(self):
        self.assertEqual(reply_subject("Re: Drawings"), "Re: Drawings")
        self.assertEqual(reply_subject("Drawings"), "Re: Drawings")

    def test_it_asks_only_for_what_is_missing(self):
        body = self._reply(body="The export is broken.").actions[0].fields["body"]
        self.assertIn("full name of the person who reported it", body)
        self.assertIn("date it was first reported", body)

    def test_it_does_not_ask_for_what_the_email_already_said(self):
        body = self._reply().actions[0].fields["body"]
        self.assertNotIn("full name of the person who reported it", body)
        self.assertIn("Jane Kowalski", body, "it confirms the guess instead")

    def test_it_always_asks_for_documentation(self):
        for body in (BUG_EMAIL, "The export is broken.", REQUEST_EMAIL):
            with self.subTest(body=body[:20]):
                text = self._reply(body=body).actions[0].fields["body"]
                self.assertRegex(text, r"attach th(?:at|ose)")

    def test_the_documentation_ask_is_dropped_when_documents_were_attached(self):
        questions = context_questions(read_email("x", "see https://x.test/a", "Marco", TUESDAY))
        documents = [question for question in questions if question.key == "documents"][0]
        self.assertFalse(documents.outstanding)

    def test_it_is_signed_in_your_name(self):
        self.assertTrue(self._reply().actions[0].fields["body"].rstrip().endswith("Deven"))

    def test_a_request_asks_about_the_requester_not_a_reporter(self):
        body = compose_reply(Intake(kind=KIND_REQUEST), signature="Deven")
        self.assertIn("the person who requested it", body)
        self.assertNotIn("reported", body)


class ReplySendingTest(unittest.TestCase):
    """Sending mail in someone's name is a write, and is bounded like one."""

    def _approved(self):
        return draft_context_reply(
            CONFIG, subject="Export broken", sender="Marco", sender_address="marco@vendor.test",
            to=("deven@alliedbuildings.com",), mailbox="deven@alliedbuildings.com",
            message_id="m2", body="The export is broken.").approve("Deven")

    def test_nothing_is_sent_without_approval(self):
        plan = draft_context_reply(CONFIG, subject="X", sender_address="marco@vendor.test",
                                   message_id="m2", body="broken")
        with self.assertRaises(actions.ApprovalRequired):
            execute(plan, mail_writer=DryRunMailWriter())

    def test_an_approved_reply_reaches_the_writer_once(self):
        writer = DryRunMailWriter()
        results = execute(self._approved(), mail_writer=writer)
        self.assertTrue(results[0].ok)
        self.assertEqual(len(writer.sent), 1)
        self.assertEqual(writer.sent[0]["to"], "marco@vendor.test")

    def test_sending_without_a_send_token_fails_closed(self):
        with self.assertRaises(WriteNotConfigured):
            execute(self._approved(), mail_writer=OutlookReplyWriter(environ={}))

    def test_the_read_token_cannot_be_used_to_send(self):
        writer = OutlookReplyWriter(environ={"MILOU_OUTLOOK_TOKEN": "read-only-token"})
        self.assertIsNone(writer.token, "the send path must not fall back to the read token")

    def test_the_write_token_is_its_own_variable(self):
        writer = OutlookReplyWriter(environ={OUTLOOK_WRITE_TOKEN_ENV: "send-token"})
        self.assertEqual(writer.token, "send-token")

    def test_editing_the_recipients_needs_a_wider_grant_and_says_so(self):
        plan = self._approved()
        edited = plan.with_inputs(to="someone-else@vendor.test").approve("Deven")
        with self.assertRaises(WriteNotConfigured) as caught:
            execute(edited, mail_writer=OutlookReplyWriter(token="t"))
        self.assertIn("Mail.ReadWrite", str(caught.exception))

    def test_an_allowed_recipient_edit_is_actually_applied(self):
        """replyAll would mail the thread's own list and discard the edit."""
        calls = []

        def fake_urlopen(request, timeout=None):
            payload = json.loads(request.data.decode("utf-8")) if request.data else {}
            calls.append((request.get_method(), request.full_url, payload))
            return _Response('{"id": "draft-9"}')

        original = actions.urllib.request.urlopen
        actions.urllib.request.urlopen = fake_urlopen
        try:
            writer = OutlookReplyWriter(token="t", allow_recipient_edits=True)
            result = writer.send_reply({"message_id": "m2", "original_to": "a@x.test",
                                        "to": "b@x.test", "body": "hi"})
        finally:
            actions.urllib.request.urlopen = original
        self.assertTrue(result.ok)
        paths = [url for _method, url, _payload in calls]
        self.assertTrue(any(path.endswith("/createReplyAll") for path in paths))
        self.assertTrue(any(path.endswith("/send") for path in paths))
        self.assertFalse(any(path.endswith("/replyAll") for path in paths),
                         "replyAll ignores the edited list, so it must not be used here")
        patched = [payload for method, _url, payload in calls if method == "PATCH"][0]
        self.assertEqual(patched["toRecipients"],
                         [{"emailAddress": {"address": "b@x.test"}}],
                         "the list that was shown must be the list that is mailed")

    def test_an_empty_recipient_list_is_refused(self):
        with self.assertRaises(IncompleteAction):
            OutlookReplyWriter(token="t").send_reply({"message_id": "m2", "to": "", "body": "x"})

    def test_the_reply_posts_and_never_echoes_its_token(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["method"] = request.get_method()
            captured["url"] = request.full_url
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        original = actions.urllib.request.urlopen
        actions.urllib.request.urlopen = fake_urlopen
        try:
            result = OutlookReplyWriter(token="send-secret").send_reply(
                {"message_id": "m2", "to": "a@x.test", "original_to": "a@x.test", "body": "hi"})
        finally:
            actions.urllib.request.urlopen = original
        self.assertEqual(captured["method"], "POST")
        self.assertIn("/me/messages/m2/replyAll", captured["url"])
        self.assertNotIn("send-secret", result.detail)
        self.assertFalse(result.ok)

    def test_the_review_report_says_nothing_has_been_sent(self):
        plan = draft_context_reply(CONFIG, subject="Export broken", sender="Marco",
                                   sender_address="marco@vendor.test", message_id="m2",
                                   body="The export is broken.")
        report = reply_plan_report(plan, TUESDAY)
        self.assertIn("Approval required", report.alert)
        self.assertEqual({kpi.label: kpi.value for kpi in report.kpis}["Sent"], "0")
        self.assertIn(OUTLOOK_WRITE_TOKEN_ENV, report.boundary)


class AcknowledgementDraftTest(unittest.TestCase):
    """After the ticket exists, the thread is told its number — as a draft."""

    def _plan(self, config=CONFIG, **overrides):
        kwargs = dict(subject="New backlog report", sender="Priya Raman", body=REQUEST_EMAIL,
                      message_id="m2", received_date=TUESDAY)
        kwargs.update(overrides)
        return draft_ticket(config, TUESDAY, **kwargs)

    def _approved(self):
        return self._plan().with_inputs(title="Backlog report").approve("Deven")

    def test_the_plan_gains_a_third_action(self):
        self.assertEqual([action.kind for action in self._plan().actions],
                         ["zoho.create_task", "document.append_line", "outlook.create_draft"])

    def test_the_number_is_filled_in_after_the_ticket_exists(self):
        # At draft time there is no ticket number, so the body carries a
        # placeholder rather than a made-up one.
        self.assertIn("{ticket_id}", self._plan().actions[2].fields["body"])
        mail = DryRunMailWriter()
        execute(self._approved(), _Ok(), DryRunDocumentWriter(), mail_writer=mail)
        self.assertIn("#4501993", mail.drafted[0]["body"])
        self.assertNotIn("{ticket_id}", mail.drafted[0]["body"])

    def test_it_states_the_release_date_as_a_latest(self):
        body = self._plan().actions[2].fields["body"]
        self.assertIn("Expected release date: 30 September 2026", body)
        self.assertIn("at the very latest", body)

    def test_it_points_them_at_the_ticket_rather_than_at_you(self):
        body = self._plan().actions[2].fields["body"]
        self.assertIn("change log", body)
        self.assertIn("follow it directly", body)

    def test_a_bug_says_resolved_and_a_request_says_delivered(self):
        bug = self._plan(subject="Export is broken", body="The export is broken.")
        self.assertIn("resolved at the very latest", bug.actions[2].fields["body"])
        self.assertIn("delivered at the very latest", self._plan().actions[2].fields["body"])

    def test_a_failed_ticket_never_leaves_a_draft(self):
        class _Fails:
            def create_task(self, portal, project, fields):
                return actions.ExecutionResult("zoho.create_task", False, "HTTP 403")

        mail = DryRunMailWriter()
        results = execute(self._approved(), _Fails(), DryRunDocumentWriter(), mail_writer=mail)
        self.assertEqual(len(results), 1, "execution stops rather than half-applying")
        self.assertEqual(mail.drafted, [],
                         "telling people to follow a ticket that does not exist is worse than silence")

    def test_it_can_be_switched_off(self):
        quiet = TicketConfig.from_mapping({"portal": "p", "project": "1", "acknowledge": False})
        self.assertEqual(len(self._plan(quiet).actions), 2)

    def test_no_draft_without_a_message_to_reply_to(self):
        self.assertEqual(len(self._plan(message_id="").actions), 2)

    def test_the_draft_is_created_unsent_and_never_sent(self):
        captured = []

        def fake_urlopen(request, timeout=None):
            captured.append((request.get_method(), request.full_url))
            if request.full_url.endswith("createReplyAll"):
                return _Response('{"id": "draft-1"}')
            return _Response("{}")

        original = actions.urllib.request.urlopen
        actions.urllib.request.urlopen = fake_urlopen
        try:
            result = OutlookReplyWriter(token="write-secret").create_draft(
                {"message_id": "m2", "body": "hello"})
        finally:
            actions.urllib.request.urlopen = original
        self.assertTrue(result.ok)
        self.assertEqual(result.produced["draft_id"], "draft-1")
        self.assertEqual([method for method, _url in captured], ["POST", "PATCH"])
        self.assertTrue(all("/send" not in url for _method, url in captured),
                        "a draft is never sent on your behalf")

    def test_drafting_without_a_write_token_fails_closed(self):
        with self.assertRaises(WriteNotConfigured):
            OutlookReplyWriter(environ={}).create_draft({"message_id": "m2", "body": "x"})


class _Response:
    """Minimal stand-in for the context manager urlopen returns."""

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.payload.encode("utf-8")


class MixedPlanTest(unittest.TestCase):

    def test_a_ticket_plan_never_touches_the_mailbox(self):
        plan = draft_ticket(CONFIG, TUESDAY, subject="New backlog report", sender="Priya",
                            body=REQUEST_EMAIL).with_inputs(title="Backlog report").approve("Deven")
        mail = DryRunMailWriter()
        execute(plan, _Ok(), DryRunDocumentWriter(), mail_writer=mail)
        self.assertEqual(mail.sent, [], "creating a ticket must not send anything")


class _Ok:
    def create_task(self, portal, project, fields):
        return actions.ExecutionResult("zoho.create_task", True, "created", {"ticket_id": "4501993"})


if __name__ == "__main__":
    unittest.main()
