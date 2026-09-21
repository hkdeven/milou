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
                 session_ttl=SESSION_TTL):
    token = bearer_token if bearer_token is not None else (environ or os.environ).get("MILOU_REPORT_TOKEN")
    sessions = {}

    def _session_authorized(handler):
        if not token:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(handler.headers.get("Cookie", ""))
        except Exception:
            return False
        morsel = cookie.get(SESSION_COOKIE)
        if morsel is None:
            return False
        expires = sessions.get(morsel.value)
        if expires is None:
            return False
        if expires <= time.time():
            sessions.pop(morsel.value, None)
            return False
        return True

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
                sessions[session_id] = time.time() + session_ttl
                cookie = ("%s=%s; Max-Age=%d; Path=/; Secure; HttpOnly; SameSite=Strict"
                          % (SESSION_COOKIE, session_id, session_ttl))
                self._redirect("/", cookie)
                return
            if path == "/logout":
                self._logout()
                return
            self._send(405, "Method not allowed.\n", "text/plain; charset=utf-8")

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

        def log_message(self, *_args):
            return

    return ReportHandler


def serve(store, host="127.0.0.1", port=8080, bearer_token=None, environ=None, scheduler=None):
    """Run the private server; bind localhost by default and never publish."""
    server = ThreadingHTTPServer((host, port), make_handler(store, bearer_token, environ, scheduler))
    server.serve_forever()
