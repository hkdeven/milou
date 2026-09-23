"""Tests for what Milou says when something goes wrong.

An error message is the part of a program a person reads at their worst
moment, so these hold three properties rather than exact wording: a message
names a cause rather than restating a status code, it says what to do next, and
it never carries a credential.
"""


import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import actions, explain
from milou_news.actions import (ApprovalRequired, IncompleteAction, OutlookReplyWriter,
                                SharePointWordWriter, TicketConfig, WriteNotConfigured,
                                ZohoWriter, draft_ticket, execute)
from milou_news.outlook import GraphApi
from milou_news.worddoc import DocumentError, append_line
from milou_news.zoho import ZohoApi

from datetime import date

TUESDAY = date(2026, 9, 29)
SECRET = "sup3r-s3cret-token-value"


class ExplainTest(unittest.TestCase):

    def test_an_expired_token_is_named_as_the_likely_cause(self):
        # 401 is the failure a person will hit most, because access tokens last
        # about an hour. "HTTP 401 Unauthorized" teaches them nothing.
        message = explain.http_failure("Microsoft Graph", "reading your mailbox", 401,
                                       "Unauthorized", "MILOU_OUTLOOK_TOKEN")
        self.assertIn("expire after about an hour", message)
        self.assertIn("MILOU_OUTLOOK_TOKEN", message)
        self.assertIn(explain.RUNBOOK, message)

    def test_a_permission_failure_names_the_scope_to_add(self):
        message = explain.http_failure("Zoho Projects", "creating the ticket", 403, "Forbidden",
                                       scope="ZohoProjects.tasks.CREATE")
        self.assertIn("ZohoProjects.tasks.CREATE", message)
        self.assertIn("valid and does not carry the permission", message)

    def test_rate_limiting_is_not_presented_as_a_mistake(self):
        message = explain.http_failure("Zoho Projects", "reading projects", 429, "Too Many")
        self.assertIn("Nothing is wrong", message)

    def test_their_outage_is_not_blamed_on_your_configuration(self):
        message = explain.http_failure("Microsoft Graph", "reading your mailbox", 503, "Busy")
        self.assertIn("their side, not", message)

    def test_a_status_code_corroborates_but_never_carries_the_message(self):
        message = explain.http_failure("Zoho Projects", "reading projects", 404, "Not Found")
        self.assertIn("(HTTP 404", message)
        self.assertNotEqual(message.strip()[:4], "HTTP")
        self.assertIn("renamed", message)

    def test_a_wiring_bug_says_it_is_a_bug(self):
        # Otherwise someone goes hunting through their Azure tenant for a
        # problem that is a missing argument.
        self.assertIn("is a bug", explain.internal("no mail writer was supplied"))

    def test_field_names_are_never_shown_to_a_person(self):
        self.assertEqual(explain.labels(["reported_by", "reported_on"]),
                         "Reported by and Reported on")
        self.assertEqual(explain.label("release_date"), "Expected release date")


class NoCredentialLeaksTest(unittest.TestCase):
    """A message about a rejected request must not carry what was rejected."""

    def _failing(self, status):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, status, "Nope", {}, None)
        return fake_urlopen

    def test_graph_failures_never_echo_the_token(self):
        original = actions.urllib.request.urlopen
        import milou_news.outlook as outlook
        outlook.urllib.request.urlopen = self._failing(401)
        try:
            result = GraphApi(token=SECRET).get("/me")
        finally:
            outlook.urllib.request.urlopen = original
        self.assertNotIn(SECRET, result.error)

    def test_zoho_failures_never_echo_the_token(self):
        import milou_news.zoho as zoho
        original = zoho.urllib.request.urlopen
        zoho.urllib.request.urlopen = self._failing(403)
        try:
            result = ZohoApi(token=SECRET).get("/restapi/portals/")
        finally:
            zoho.urllib.request.urlopen = original
        self.assertNotIn(SECRET, result.error)

    def test_write_failures_never_echo_the_token(self):
        original = actions.urllib.request.urlopen
        actions.urllib.request.urlopen = self._failing(401)
        try:
            result = ZohoWriter(token=SECRET).create_task("p", "1", {"title": "X"})
        finally:
            actions.urllib.request.urlopen = original
        self.assertNotIn(SECRET, result.detail)


class ActionableTest(unittest.TestCase):
    """Every refusal says what did not happen, and what to do about it."""

    def _plan(self, **inputs):
        config = TicketConfig.from_mapping({"portal": "p", "project": "1",
                                            "statuses": ["Open", "Ready for Development"]})
        return draft_ticket(config, TUESDAY, subject="Export is broken", sender="Marco",
                            body="The export is broken.", message_id="m1").with_inputs(**inputs)

    def test_a_missing_field_is_named_the_way_the_form_names_it(self):
        with self.assertRaises(IncompleteAction) as caught:
            self._plan(title="Fix export").approve("Deven")
        message = str(caught.exception)
        self.assertIn("Reported by and Reported on", message)
        self.assertNotIn("reported_by", message)
        self.assertIn("Nothing was done", message)
        self.assertIn("Ask for context", message, "point at the thing that gets the answer")

    def test_an_unnamed_approver_is_told_what_to_type(self):
        with self.assertRaises(ApprovalRequired) as caught:
            self._plan(title="X", reported_by="J", reported_on="Monday").approve("")
        self.assertIn("Approved by", str(caught.exception))

    def test_a_missing_credential_names_the_variable_and_the_runbook(self):
        plan = self._plan(title="X", reported_by="J", reported_on="Monday").approve("Deven")
        with self.assertRaises(WriteNotConfigured) as caught:
            execute(plan, ZohoWriter(environ={}), None, None)
        message = str(caught.exception)
        self.assertIn("MILOU_ZOHO_WRITE_TOKEN", message)
        self.assertIn(explain.RUNBOOK, message)

    def test_an_unconfigured_setting_is_named_as_a_setting(self):
        with self.assertRaises(WriteNotConfigured) as caught:
            ZohoWriter(token="t").create_task("", "1", {"title": "X"})
        self.assertIn("ticket.portal", str(caught.exception))

    def test_a_missing_document_link_names_where_to_get_it(self):
        with self.assertRaises(WriteNotConfigured) as caught:
            SharePointWordWriter(token="t").append_under_heading("d", "30 SEP SPRINT", "1 - X")
        self.assertIn("ticket.document_url", str(caught.exception))
        self.assertIn("Copy link", str(caught.exception))

    def test_a_missing_tracker_heading_says_what_it_looked_for(self):
        with self.assertRaises(DocumentError) as caught:
            append_line("<w:document><w:body></w:body></w:document>", "2 OCT SPRINT", "1 - X")
        message = str(caught.exception)
        self.assertIn("Nothing was written", message)
        self.assertIn("2 OCT SPRINT", message)

    def test_an_edited_recipient_list_explains_both_ways_out(self):
        with self.assertRaises(WriteNotConfigured) as caught:
            OutlookReplyWriter(token="t").send_reply(
                {"message_id": "m", "to": "new@x.test", "original_to": "old@x.test", "body": "x"})
        message = str(caught.exception)
        self.assertIn("Nothing was sent", message)
        self.assertIn("put the original recipients back", message.lower())
        self.assertIn("allow_recipient_edits", message)


class ConfigurationTest(unittest.TestCase):

    def test_a_bad_threshold_names_the_setting_and_the_range(self):
        from milou_news.outlook import InboxConfig
        with self.assertRaises(ValueError) as caught:
            InboxConfig.from_mapping({"max_items": 500})
        message = str(caught.exception)
        self.assertIn("inbox.max_items", message)
        self.assertIn("between 1 and 25", message)

    def test_a_default_status_outside_the_list_explains_the_fix(self):
        with self.assertRaises(ValueError) as caught:
            TicketConfig.from_mapping({"statuses": ["Open", "Closed"]})
        message = str(caught.exception)
        self.assertIn("ticket.ready_status", message)
        self.assertIn("ticket.statuses", message)
        self.assertIn("Open, Closed", message, "list what is actually available")


if __name__ == "__main__":
    unittest.main()
