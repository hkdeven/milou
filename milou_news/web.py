"""Private HTTP delivery for archived reports.

Browser sessions are deliberately kept in the server process.  Bearer
authentication remains available for API and CLI clients.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import actions as write_actions
from . import console as console_module
from . import render_html
from .report import Report

AUTH_SCHEME = "B" + "earer"
SESSION_COOKIE = "milou_session"
SESSION_TTL = 3600


def _bearer_authorized(handler, token):
    if not token:
        return False, 503
    supplied = handler.headers.get("Authorization", "")
    expected = AUTH_SCHEME + " " + token
    return bool(supplied) and hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ), 401


def make_handler(store, bearer_token=None, environ=None, scheduler=None,
                 session_ttl=SESSION_TTL, console=None):
    token = bearer_token if bearer_token is not None else (environ or os.environ).get("MILOU_REPORT_TOKEN")
    #: session id -> {"expires": float, "csrf": str}
    sessions = {}

    def _session(handler):
        if not token:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(handler.headers.get("Cookie", ""))
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        if morsel is None:
            return None
        record = sessions.get(morsel.value)
        if record is None:
            return None
        if record["expires"] <= time.time():
            sessions.pop(morsel.value, None)
            return None
        return record

    def _session_authorized(handler):
        return _session(handler) is not None

    def _authorized(handler):
        allowed, failure = _bearer_authorized(handler, token)
        return (allowed, failure) if allowed else (
            (True, 200) if _session_authorized(handler) else (False, failure)
        )

    class ReportHandler(BaseHTTPRequestHandler):
        def _send(self, status, body, content_type="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _login_form(self, status=200, message=""):
            self._send(status, render_html.login_page(message))

        def _redirect(self, location, cookie=None):
            self.send_response(303)
            self.send_header("Location", location)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _logout(self):
            cookie = SimpleCookie()
            cookie[SESSION_COOKIE] = ""
            cookie[SESSION_COOKIE]["path"] = "/"
            cookie[SESSION_COOKIE]["max-age"] = 0
            cookie[SESSION_COOKIE]["secure"] = True
            cookie[SESSION_COOKIE]["httponly"] = True
            cookie[SESSION_COOKIE]["samesite"] = "Strict"
            self._redirect("/", cookie.output(header="").strip())

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/login":
                if not token:
                    self._send(503, "Report delivery is not configured.\n",
                               "text/plain; charset=utf-8")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    form = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=False)
                except (ValueError, UnicodeDecodeError):
                    form = {}
                supplied = form.get("token", [""])[0]
                if not hmac.compare_digest(supplied, token):
                    self._login_form(401, "Invalid token.")
                    return
                session_id = secrets.token_urlsafe(32)
                sessions[session_id] = {"expires": time.time() + session_ttl,
                                        "csrf": secrets.token_urlsafe(32)}
                cookie = ("%s=%s; Max-Age=%d; Path=/; Secure; HttpOnly; SameSite=Strict"
                          % (SESSION_COOKIE, session_id, session_ttl))
                self._redirect("/", cookie)
                return
            if path == "/logout":
                self._logout()
                return
            if console is not None and path in ("/action/ticket", "/action/reply"):
                self._action(path, console)
                return
            self._send(405, "Method not allowed.\n", "text/plain; charset=utf-8")

        def _form(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    return {}
                return parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            except (ValueError, UnicodeDecodeError):
                return {}

        def _action(self, path, console):
            """A write request. Authenticated session, valid CSRF, named approver.

            Bearer tokens are deliberately not accepted here. They exist so a
            script can fetch a report; letting one create a ticket would widen
            a read credential into a write credential by accident.
            """
            record = _session(self)
            if record is None:
                self._login_form(401, "Sign in again before acting on a message.")
                return
            form = self._form()
            supplied = form.get("csrf", [""])[0]
            if not supplied or not hmac.compare_digest(supplied, record["csrf"]):
                self._send(403, "This form has expired. Reload the page and try again.\n",
                           "text/plain; charset=utf-8")
                return
            single = {name: values[0] for name, values in form.items()}
            single["ask"] = form.get("ask", [])
            single["acknowledge"] = form.get("acknowledge", [""])[0]
            handler = _ticket_action if path == "/action/ticket" else _reply_action
            status, body = handler(console, single, record["csrf"])
            self._send(status, body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/logout":
                self._logout()
                return
            allowed, failure = _authorized(self)
            if not allowed:
                if failure == 401:
                    if path == "/":
                        self._login_form()
                        return
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", AUTH_SCHEME + ' realm="milou-reports"')
                    self.end_headers()
                else:
                    self._send(503, "Report delivery is not configured.\n", "text/plain; charset=utf-8")
                return
            if console is not None:
                record = _session(self)
                csrf = record["csrf"] if record else ""
                if path == "/routine" or path.startswith("/routine/"):
                    self._routine(console, path[len("/routine/"):], csrf)
                    return
                if path == "/action/ticket" or path == "/action/reply":
                    if record is None:
                        self._login_form(401, "Sign in again before acting on a message.")
                        return
                    query = parse_qs(urlparse(self.path).query)
                    single = {"message": query.get("message", [""])[0], "ask": []}
                    handler = _ticket_action if path == "/action/ticket" else _reply_action
                    status, body = handler(console, single, csrf)
                    self._send(status, body)
                    return
            if path in ("/status", "/health"):
                payload = scheduler.status() if scheduler else {"archive": "healthy", "scheduler": "not configured"}
                self._send(200, json.dumps(payload, indent=2) + "\n", "application/json; charset=utf-8")
                return
            reports = store.reports()
            if path in ("/", "/archive"):
                entries = []
                for report in reports:
                    relative = os.path.relpath(report["path"], store.root)
                    metadata = report.get("metadata", {})
                    entries.append({
                        "href": "/report/" + quote(relative),
                        "generated_at": report.get("generated_at", relative),
                        "routine": metadata.get("routine", "report"),
                        "status": metadata.get("status", "stored"),
                    })
                self._send(200, render_html.index_page(entries))
                return
            if path.startswith("/report/"):
                payload = store.get(unquote(path[len("/report/"):]))
                if payload is None:
                    self._send(404, "Report not found.\n", "text/plain; charset=utf-8")
                    return
                label = payload.get("metadata", {}).get("routine", "report")
                status = payload.get("metadata", {}).get("status", "stored")
                structured = payload.get("report")
                if structured:
                    try:
                        self._send(200, render_html.report_page(Report.from_dict(structured)))
                        return
                    except (ValueError, TypeError, KeyError):
                        pass  # fall back to the stored Markdown rather than 500
                self._send(200, render_html.markdown_page(label, status, payload.get("markdown", "")))
                return
            self._send(404, "Not found.\n", "text/plain; charset=utf-8")

        def _routine(self, console, key, csrf):
            """One routine's report, inside the application shell."""
            key = unquote(key) or console_module.INBOX
            views = console.views()
            entry = next((view for view in views if view["key"] == key), None)
            if entry is None:
                self._send(404, "No such routine.\n", "text/plain; charset=utf-8")
                return
            generated, headline = "", None
            try:
                report = console.report(key)
            except console_module.UnknownRoutine as exc:
                body = render_html.result_panel("This routine is not available", [
                    _Note("configuration", str(exc))], back="/routine/" + console_module.INBOX)
            else:
                generated = report.generated
                headline = console.headline(report)
                body = render_html.render_report(report)
                if entry.get("actions"):
                    body = _with_actions(console, report, body, csrf)
            self._send(200, render_html.shell(
                views, key, body, who=getattr(console.config, "approver", ""),
                crumb=entry["name"], cadence=entry["cadence"], generated=generated,
                headline=headline))

        def log_message(self, *_args):
            return

    return ReportHandler


class _Note:
    """A stand-in result, so a configuration problem renders like any other."""

    def __init__(self, action, detail):
        self.action, self.detail, self.ok = action, detail, False


def _with_actions(console, report, body, csrf):
    """Put the two actions on every inbox row the report actually shows.

    The renderer knows nothing about actions — it renders reports. Rather than
    teaching it, the row's own citation link is used to find where each button
    belongs, which keeps buttons out of every other report that has links too.
    """
    for tier in report.populated_tiers():
        for row in tier.rows:
            if not row.url:
                continue
            identifier = row.url.rstrip("/").rsplit("/", 1)[-1]
            anchor = render_html._link(row.url)
            if not anchor or anchor not in body:
                continue
            buttons = (
                '<span class="row-actions">'
                '<a class="btn btn-sm btn-ticket" href="/action/ticket?message=%s">'
                'Create ticket</a>'
                '<a class="btn btn-sm btn-reply" href="/action/reply?message=%s">'
                'Ask for context</a></span>' % (quote(identifier), quote(identifier)))
            body = body.replace(anchor, buttons + anchor, 1)
    return body


def _ticket_action(console, form, csrf):
    """Draft, refresh, or create. Only ``intent=create`` changes anything."""
    identifier = form.get("message", "")
    plan, message = console.ticket_plan(identifier, form)
    if plan is None:
        return 404, render_html.document(
            "Milou", "<div class='wrap'><p>That message is no longer in the mailbox window.</p></div>")
    available = console.can_write()
    live = available["zoho"]
    error = ""
    if form.get("intent") == "create":
        approver = (form.get("approver") or "").strip()
        try:
            results = console.create_ticket(plan, approver)
        except (write_actions.ApprovalRequired, write_actions.IncompleteAction,
                write_actions.WriteNotConfigured) as exc:
            error = str(exc)
        else:
            # A rehearsal must never report itself as a ticket somebody can go
            # and open. The heading follows what was actually configured to
            # write, not whether the steps returned ok.
            title = _outcome(all(result.ok for result in results), live,
                             "Ticket created", "Nothing was created — this was a rehearsal",
                             "This stopped part way")
            return 200, render_html.shell(
                console.views(), console_module.INBOX,
                render_html.result_panel(title, results,
                                         back="/routine/" + console_module.INBOX),
                crumb="Create ticket")
    return 200, render_html.shell(
        console.views(), console_module.INBOX,
        render_html.ticket_form(plan, console.config.ticket, message, csrf,
                                statuses=console.config.statuses,
                                owners=console.config.owners,
                                sprints=console.sprints(),
                                approver=form.get("approver") or console.config.approver,
                                live=live, error=error),
        crumb="Create ticket")


def _reply_action(console, form, csrf):
    """Draft, refresh, or send. Only ``intent=send`` sends anything."""
    identifier = form.get("message", "")
    plan, message, questions = console.reply_plan(identifier, form)
    if plan is None:
        return 404, render_html.document(
            "Milou", "<div class='wrap'><p>That message is no longer in the mailbox window.</p></div>")
    live = console.can_write()["outlook"]
    error = ""
    if form.get("intent") == "send":
        approver = (form.get("approver") or "").strip()
        try:
            results = console.send_reply(plan, approver)
        except (write_actions.ApprovalRequired, write_actions.IncompleteAction,
                write_actions.WriteNotConfigured) as exc:
            error = str(exc)
        else:
            title = _outcome(all(result.ok for result in results), live,
                             "Reply sent", "Nothing was sent — this was a rehearsal",
                             "This did not send")
            return 200, render_html.shell(
                console.views(), console_module.INBOX,
                render_html.result_panel(title, results,
                                         back="/routine/" + console_module.INBOX),
                crumb="Ask for context")
    return 200, render_html.shell(
        console.views(), console_module.INBOX,
        render_html.reply_form(plan, message, csrf, questions=questions,
                               approver=form.get("approver") or console.config.approver,
                               live=live, error=error),
        crumb="Ask for context")


def _outcome(ok: bool, live: bool, done: str, rehearsed: str, failed: str) -> str:
    """What to call the result, given whether a credential was configured."""
    if not ok:
        return failed
    return done if live else rehearsed




def serve(store, host="127.0.0.1", port=8080, bearer_token=None, environ=None, scheduler=None,
          console=None):
    """Run the private server; bind localhost by default and never publish."""
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(store, bearer_token, environ, scheduler, console=console))
    server.serve_forever()
