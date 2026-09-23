"""Tests for the navigable application and its two write routes.

The console is the first place a write can be triggered by a click rather than
a typed command, so most of what is asserted here is refusal: no session, no
CSRF token, no approver, no write credential, wrong status — none of them get
through, and none of them fail silently.
"""


import json
import os
import sys
import unittest
import http.client
import tempfile
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from threading import Thread

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import render_html
from milou_news.actions import (DryRunDocumentWriter, DryRunMailWriter,
                                TicketConfig, execute)
from milou_news.archive import ReportStore
from milou_news.console import INBOX, Console, ConsoleConfig, UnknownRoutine
from milou_news.outlook import FixtureGraph, InboxConfig
from milou_news.web import make_handler
from milou_news.zoho import FixtureZoho, ZohoConfig

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
NOW = datetime(2026, 9, 22, 15, 40, tzinfo=timezone.utc)
STATUSES = ["Open", "Ready for Development", "In Progress", "Released"]


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


def console(environ=None, payloads=None):
    outlook, zoho = fixture("outlook.json"), fixture("zoho.json")
    config = ConsoleConfig(
        inbox=InboxConfig.from_mapping(outlook["config"]),
        zoho=ZohoConfig.from_mapping(zoho.get("config", zoho)),
        ticket=TicketConfig.from_mapping({
            "portal": "alliedsteel", "project": "5001", "project_name": "Bldg 4 Fabrication",
            "statuses": STATUSES, "signature": "Deven", "document": "Sprint tracker"}),
        owners=("A. Rivera", "D. Nguyen"), approver="Deven",
        payloads=payloads or {"daily-wins-recap": fixture("activity.json")})
    return Console(config, graph=FixtureGraph(outlook["responses"]),
                   zoho=FixtureZoho(zoho["responses"], zoho.get("errors", {})),
                   environ=environ if environ is not None else {})


class ReportViewTest(unittest.TestCase):

    def test_the_navigation_lists_every_routine_once(self):
        keys = [view["key"] for view in console().views()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(INBOX, keys)
        self.assertEqual(keys[0], INBOX, "the inbox leads, because it is what replaces email")

    def test_only_the_inbox_carries_actions(self):
        acting = [view["key"] for view in console().views() if view["actions"]]
        self.assertEqual(acting, [INBOX])

    def test_a_routine_is_built_by_its_own_routine(self):
        report = console().report(INBOX, NOW)
        self.assertEqual(report.routine, "outlook-inbox-monitor")
        self.assertTrue(report.tiers)

    def test_the_zoho_radar_covers_the_inbox(self):
        # The console wires the radar's coverage into the monitor, so a Zoho
        # notification that the radar already reported is not shown twice.
        report = console().report(INBOX, NOW)
        excluded = [segment.label for bar in report.bars for segment in bar.segments]
        self.assertIn("already reported by zoho-projects-radar", excluded)

    def test_an_unknown_routine_is_refused_rather_than_guessed(self):
        with self.assertRaises(UnknownRoutine):
            console().report("no-such-routine", NOW)

    def test_a_routine_without_a_configured_scope_says_so(self):
        with self.assertRaises(UnknownRoutine):
            console().report("github-change-radar", NOW)


class WriteCredentialTest(unittest.TestCase):

    def test_without_tokens_every_action_is_a_rehearsal(self):
        available = console().can_write()
        self.assertEqual(available, {"zoho": False, "outlook": False, "document": False})
        zoho, document, mail = console().writers()
        self.assertEqual(type(zoho).__name__, "_DryRunZoho")
        self.assertEqual(type(mail).__name__, "DryRunMailWriter")
        self.assertEqual(type(document).__name__, "DryRunDocumentWriter")

    def test_a_rehearsal_says_so_instead_of_inventing_a_ticket_number(self):
        plan, _message = console().ticket_plan("m2", {"title": "Issue drawings"}, NOW)
        results = console().create_ticket(plan, "Deven")
        self.assertTrue(results[0].ok)
        self.assertIn("dry run", results[0].detail)
        self.assertIn("MILOU_ZOHO_WRITE_TOKEN", results[0].detail)

    def test_each_credential_is_picked_up_separately(self):
        writers = console(environ={"MILOU_ZOHO_WRITE_TOKEN": "z"}).can_write()
        self.assertEqual(writers, {"zoho": True, "outlook": False, "document": False})


class TicketPlanTest(unittest.TestCase):

    def test_the_form_edits_are_applied_to_the_plan(self):
        plan, _message = console().ticket_plan(
            "m10", {"title": "Nested weight rollup", "reported_by": "J. Kowalski",
                    "reported_on": "2026-09-21"}, NOW)
        self.assertEqual(plan.missing(), [])
        self.assertEqual(plan.actions[0].fields["title"], "Nested weight rollup")

    def test_a_bug_without_its_reporter_cannot_be_created(self):
        plan, _message = console().ticket_plan("m2", {"kind_choice": "bug", "title": "X"}, NOW)
        self.assertIn("reported_by", plan.missing())

    def test_flipping_the_type_changes_what_is_required(self):
        as_request, _m = console().ticket_plan("m10", {"kind_choice": "request", "title": "X"}, NOW)
        self.assertEqual(as_request.missing(), [])

    def test_the_acknowledgement_can_be_switched_off_per_ticket(self):
        with_draft, _m = console().ticket_plan("m2", {"title": "X"}, NOW)
        without, _m2 = console().ticket_plan("m2", {"title": "X", "acknowledge": ""}, NOW)
        self.assertIn("outlook.create_draft", [a.kind for a in with_draft.actions])
        self.assertNotIn("outlook.create_draft", [a.kind for a in without.actions])

    def test_a_message_outside_the_window_is_not_invented(self):
        plan, message = console().ticket_plan("nope", {}, NOW)
        self.assertIsNone(plan)
        self.assertIsNone(message)


class ReplyPlanTest(unittest.TestCase):

    def test_the_questions_default_to_what_is_missing(self):
        _plan, _message, questions = console().reply_plan("m2", {}, NOW)
        self.assertTrue(any(question.outstanding for question in questions))

    def test_unticking_a_question_rewrites_the_message(self):
        plan, _m, _q = console().reply_plan("m2", {"ask": ["record"]}, NOW)
        none, _m2, _q2 = console().reply_plan("m2", {"ask": []}, NOW)
        self.assertIn("project name or record title", plan.actions[0].fields["body"])
        self.assertNotIn("project name or record title", none.actions[0].fields["body"])

    def test_you_are_never_a_recipient_of_your_own_reply(self):
        plan, _m, _q = console().reply_plan("m10", {}, NOW)
        self.assertNotIn("deven@example.test", plan.actions[0].fields["to"])


class ApprovedTextIsWrittenTest(unittest.TestCase):
    """What the form showed must be what the write carries.

    A form resubmits every field, so "a narrative field was supplied" cannot
    mean "recompose the description" — that would overwrite a hand-edited one
    on the very submission that approves it.
    """

    def _form(self, **overrides):
        instance = console()
        plan, message = instance.ticket_plan("m10", {}, NOW)
        create = plan.actions[0].fields
        draft = [a for a in plan.actions if a.kind == "outlook.create_draft"][0]
        form = {"title": "Rollup", "requested_by": create["requested_by"],
                "reported_by": create["reported_by"], "reported_on": create["reported_on"],
                "record": create["record"], "status": create["status"],
                "description": create["description"],
                "composed_description": create["description"],
                "ack_body": draft.fields["body"], "composed_ack": draft.fields["body"]}
        form.update(overrides)
        return instance, form

    def test_an_edited_description_survives_approval(self):
        instance, form = self._form(description="Redacted by hand.")
        plan, _message = instance.ticket_plan("m10", form, NOW)
        self.assertEqual(plan.actions[0].fields["description"], "Redacted by hand.")

    def test_an_untouched_description_still_follows_the_fields(self):
        instance, form = self._form(reported_by="Someone Else")
        plan, _message = instance.ticket_plan("m10", form, NOW)
        self.assertIn("Reported by: Someone Else", plan.actions[0].fields["description"])

    def test_an_edited_acknowledgement_is_the_one_drafted(self):
        instance, form = self._form(ack_body="Short version. #{ticket_id}")
        plan, _message = instance.ticket_plan("m10", form, NOW)
        draft = [a for a in plan.actions if a.kind == "outlook.create_draft"][0]
        self.assertEqual(draft.fields["body"], "Short version. #{ticket_id}")
        mail = DryRunMailWriter()
        execute(plan.with_inputs(title="Rollup").approve("Deven"), _Created(),
                DryRunDocumentWriter(), mail_writer=mail)
        self.assertIn("Short version. #4501993", mail.drafted[0]["body"])

    def test_an_edited_reply_body_is_not_recomposed_away(self):
        instance = console()
        plan, _m, _q = instance.reply_plan("m2", {}, NOW)
        composed = plan.actions[0].fields["body"]
        edited, _m2, _q2 = instance.reply_plan(
            "m2", {"body": "Just the one question, please.", "composed_body": composed}, NOW)
        self.assertEqual(edited.actions[0].fields["body"], "Just the one question, please.")

    def test_an_untouched_reply_body_still_follows_the_ticks(self):
        instance = console()
        plan, _m, _q = instance.reply_plan("m2", {}, NOW)
        composed = plan.actions[0].fields["body"]
        refreshed, _m2, _q2 = instance.reply_plan(
            "m2", {"ask": [], "body": composed, "composed_body": composed}, NOW)
        self.assertNotEqual(refreshed.actions[0].fields["body"], composed)

    def test_the_form_carries_what_it_displayed(self):
        instance = console()
        plan, message = instance.ticket_plan("m10", {}, NOW)
        html = render_html.ticket_form(plan, instance.config.ticket, message, "tok")
        self.assertIn('name="composed_description"', html)
        self.assertIn('name="composed_ack"', html)


class _Created:
    def create_task(self, portal, project, fields):
        from milou_news import actions as write_actions
        return write_actions.ExecutionResult("zoho.create_task", True, "created",
                                             {"ticket_id": "4501993"})


class RenderTest(unittest.TestCase):

    def test_the_shell_marks_the_open_routine(self):
        page = render_html.shell(console().views(), INBOX, "<p>body</p>", crumb="Inbox")
        self.assertIn('aria-current="page"', page)
        self.assertIn("Outlook inbox monitor", page)

    def test_no_routine_is_badged_with_a_number_nobody_computed(self):
        # Only the open routine is built, so a sidebar badge on one item would
        # read as eleven quiet routines.
        page = render_html.shell(console().views(), INBOX, "<p>body</p>", crumb="Inbox")
        self.assertNotIn('class="nav-badge', page)  # the class is in the CSS; no element uses it

    def test_the_open_routines_headline_is_shown_where_it_is_true(self):
        instance = console()
        report = instance.report(INBOX, NOW)
        page = render_html.shell(instance.views(), INBOX, "<p>body</p>", crumb="Inbox",
                                 headline=instance.headline(report))
        self.assertIn("Needs you", page)

    def test_the_ticket_form_states_that_nothing_has_happened(self):
        instance = console()
        plan, message = instance.ticket_plan("m10", {}, NOW)
        html = render_html.ticket_form(plan, instance.config.ticket, message, "tok",
                                       statuses=STATUSES, sprints=instance.sprints(NOW))
        self.assertIn("Nothing is created until you press Create", html)
        self.assertIn('name="csrf" value="tok"', html)
        self.assertIn("would be a dry run", html)

    def test_the_ticket_form_disables_create_while_something_is_missing(self):
        instance = console()
        plan, message = instance.ticket_plan("m10", {"reported_by": "", "reported_on": ""}, NOW)
        html = render_html.ticket_form(plan, instance.config.ticket, message, "tok")
        self.assertIn("waiting on:", html)
        self.assertIn('value="create" disabled', html)

    def test_the_reply_form_carries_the_original_recipients(self):
        instance = console()
        plan, message, questions = instance.reply_plan("m10", {}, NOW)
        html = render_html.reply_form(plan, message, "tok", questions=questions)
        self.assertIn('name="original_to"', html,
                      "the server must be able to tell whether you edited the list")
        self.assertIn("Nothing is sent until you press Send", html)


class RoutesTest(unittest.TestCase):
    """The HTTP surface, driven the way a browser drives it."""

    def setUp(self):
        self.store = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(ReportStore(self.store.name), "secret", console=console()))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.cleanup()

    def _request(self, method, path, body=None, cookie=None, bearer=None):
        """Raw HTTP: redirects are not followed, so a 303 stays a 303."""
        connection = http.client.HTTPConnection(*self.server.server_address)
        headers = {}
        if cookie:
            headers["Cookie"] = cookie
        if bearer:
            headers["Authorization"] = "B" + "earer " + bearer
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read().decode("utf-8")
        connection.close()
        return response.status, dict(response.getheaders()), payload

    def _sign_in(self):
        status, headers, _body = self._request("POST", "/login", "token=secret")
        self.assertEqual(status, 303)
        cookie = SimpleCookie()
        cookie.load(headers.get("Set-Cookie", ""))
        return "milou_session=" + cookie["milou_session"].value

    def test_a_routine_renders_inside_the_shell(self):
        _status, _h, page = self._request("GET", "/routine/" + INBOX, cookie=self._sign_in())
        self.assertIn("Outlook inbox monitor", page)
        self.assertIn('class="nav-item"', page)

    def test_inbox_rows_carry_both_actions(self):
        _status, _h, page = self._request("GET", "/routine/" + INBOX, cookie=self._sign_in())
        self.assertIn("/action/ticket?message=m10", page)
        self.assertIn("/action/reply?message=m10", page)

    def test_other_reports_carry_no_action_buttons(self):
        _status, _h, page = self._request("GET", "/routine/daily-wins-recap",
                                          cookie=self._sign_in())
        self.assertNotIn("/action/ticket", page)

    def test_an_unsigned_visitor_sees_no_report(self):
        status, _h, _b = self._request("GET", "/routine/" + INBOX)
        self.assertEqual(status, 401)

    def test_an_unknown_routine_is_a_404(self):
        status, _h, _b = self._request("GET", "/routine/nope", cookie=self._sign_in())
        self.assertEqual(status, 404)

    def test_a_write_without_a_session_is_refused(self):
        status, _h, _b = self._request("POST", "/action/ticket",
                                       "message=m2&intent=create&approver=Deven")
        self.assertEqual(status, 401)

    def test_a_write_without_the_csrf_token_is_refused(self):
        status, _h, _b = self._request("POST", "/action/ticket",
                                       "message=m2&intent=create&approver=Deven",
                                       cookie=self._sign_in())
        self.assertEqual(status, 403)

    def test_a_write_with_a_forged_csrf_token_is_refused(self):
        status, _h, _b = self._request(
            "POST", "/action/ticket", "csrf=guess&message=m2&intent=create&approver=Deven",
            cookie=self._sign_in())
        self.assertEqual(status, 403)

    def test_a_bearer_token_cannot_write(self):
        # A read credential must not become a write credential by being reused.
        status, _h, _b = self._request("POST", "/action/ticket", "message=m2&intent=create",
                                       bearer="secret")
        self.assertEqual(status, 401)

    def _csrf(self, cookie, path="/action/ticket?message=m10"):
        _status, _h, page = self._request("GET", path, cookie=cookie)
        marker = 'name="csrf" value="'
        start = page.index(marker) + len(marker)
        return page[start:page.index('"', start)], page

    def test_the_form_opens_with_a_usable_token(self):
        cookie = self._sign_in()
        token, page = self._csrf(cookie)
        self.assertTrue(token)
        self.assertIn("Takeoff weight rollup", page)

    def test_refreshing_recomposes_the_description_without_creating_anything(self):
        cookie = self._sign_in()
        token, _page = self._csrf(cookie)
        body = ("csrf=%s&message=m10&intent=refresh&title=Rollup&reported_by=J.+Q.+Kowalski"
                "&reported_on=2026-09-21&approver=Deven" % token)
        _status, _h, page = self._request("POST", "/action/ticket", body, cookie=cookie)
        self.assertIn("Reported by: J. Q. Kowalski", page)
        self.assertIn("Nothing is created until you press Create", page)

    def test_creating_without_an_approver_is_refused_and_says_why(self):
        cookie = self._sign_in()
        token, _page = self._csrf(cookie)
        body = ("csrf=%s&message=m10&intent=create&title=Rollup&reported_by=J&reported_on=X"
                "&approver=" % token)
        _status, _h, page = self._request("POST", "/action/ticket", body, cookie=cookie)
        self.assertIn("approval needs a name", page)
        self.assertIn("Nothing was done", page, "say what did not happen, first")
        self.assertIn("This could not be done", page)

    def test_creating_reports_every_step_including_the_rehearsal(self):
        cookie = self._sign_in()
        token, _page = self._csrf(cookie)
        body = ("csrf=%s&message=m10&intent=create&title=Rollup&reported_by=J.+Kowalski"
                "&reported_on=2026-09-21&approver=Deven&acknowledge=1" % token)
        _status, _h, page = self._request("POST", "/action/ticket", body, cookie=cookie)
        self.assertIn("zoho.create_task", page)
        self.assertIn("document.append_line", page)
        self.assertIn("outlook.create_draft", page)
        self.assertIn("dry run", page)
        self.assertIn("this was a rehearsal", page,
                      "a rehearsal must never be reported as a created ticket")
        self.assertNotIn("Ticket created", page)

    def test_a_status_the_portal_does_not_have_is_refused_before_the_write(self):
        cookie = self._sign_in()
        token, _page = self._csrf(cookie)
        body = ("csrf=%s&message=m10&intent=create&title=Rollup&reported_by=J&reported_on=X"
                "&status=Ready+for+QA&approver=Deven" % token)
        _status, _h, page = self._request("POST", "/action/ticket", body, cookie=cookie)
        self.assertIn("not one your Zoho portal offers", page)
        self.assertIn("Ready for Development", page, "it lists the real options")

    def test_sending_a_reply_reports_what_it_would_have_sent(self):
        cookie = self._sign_in()
        token, _page = self._csrf(cookie, "/action/reply?message=m10")
        body = ("csrf=%s&message=m10&intent=send&approver=Deven&to=t.brennan%%40example.test"
                "&original_to=t.brennan%%40example.test&body=Hello&subject=Re:+x" % token)
        _status, _h, page = self._request("POST", "/action/reply", body, cookie=cookie)
        self.assertIn("outlook.reply_all", page)
        self.assertIn("dry run", page)
        self.assertIn("this was a rehearsal", page)
        self.assertNotIn("Reply sent", page)

    def test_sending_without_an_approver_is_refused(self):
        cookie = self._sign_in()
        token, _page = self._csrf(cookie, "/action/reply?message=m10")
        body = ("csrf=%s&message=m10&intent=send&approver=&to=a%%40b.test"
                "&original_to=a%%40b.test&body=Hello" % token)
        _status, _h, page = self._request("POST", "/action/reply", body, cookie=cookie)
        self.assertIn("approval needs a name", page)


if __name__ == "__main__":
    unittest.main()


class LaunchSignInTest(unittest.TestCase):
    """The one-time link a double-clicked application opens.

    It is a secret in a URL, which is a real cost, so the properties that make
    it acceptable are the ones worth pinning: single use, short-lived, and
    honoured only from this machine.
    """

    def setUp(self):
        self.store = tempfile.TemporaryDirectory()
        self.nonce = "launch-nonce-value"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(ReportStore(self.store.name), "secret", console=console(),
                         launch_nonce=self.nonce))
        Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.cleanup()

    def _get(self, path, cookie=None):
        connection = http.client.HTTPConnection(*self.server.server_address)
        connection.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, body

    def test_the_link_signs_you_in(self):
        status, headers, _body = self._get("/?signin=" + self.nonce)
        self.assertEqual(status, 303)
        self.assertIn("milou_session=", headers.get("Set-Cookie", ""))

    def test_it_is_spent_on_first_use(self):
        self._get("/?signin=" + self.nonce)
        status, headers, _body = self._get("/?signin=" + self.nonce)
        self.assertNotEqual(status, 303, "a link in a browser history must not work twice")
        self.assertNotIn("milou_session=", headers.get("Set-Cookie", ""))

    def test_a_wrong_link_does_not_sign_anyone_in(self):
        status, headers, _body = self._get("/?signin=guessed")
        self.assertNotIn("milou_session=", headers.get("Set-Cookie", ""))
        self.assertNotEqual(status, 303)
