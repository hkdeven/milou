"""Private, bearer-authenticated HTTP delivery for archived reports."""

import hashlib
import hmac
import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

AUTH_SCHEME = "B" + "earer"


def _authorized(handler, token):
    if not token:
        return False, 503
    supplied = handler.headers.get("Authorization", "")
    expected = AUTH_SCHEME + " " + token
    return bool(supplied) and hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ), 401


def make_handler(store, bearer_token=None, environ=None):
    token = bearer_token if bearer_token is not None else (environ or os.environ).get("MILOU_REPORT_TOKEN")

    class ReportHandler(BaseHTTPRequestHandler):
        def _send(self, status, body, content_type="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            allowed, failure = _authorized(self, token)
            if not allowed:
                if failure == 401:
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", AUTH_SCHEME + ' realm="milou-reports"')
                    self.end_headers()
                else:
                    self._send(503, "Report delivery is not configured.\n", "text/plain; charset=utf-8")
                return
            path = urlparse(self.path).path
            reports = store.reports()
            if path in ("/", "/archive"):
                links = []
                for report in reports:
                    relative = os.path.relpath(report["path"], store.root)
                    links.append('<li><a href="/report/%s">%s</a></li>' %
                                 (html.escape(relative), html.escape(report.get("generated_at", relative))))
                self._send(200, "<!doctype html><meta name=\"viewport\" content=\"width=device-width\">"
                                "<title>Milou reports</title><h1>Milou reports</h1><ul>%s</ul>" %
                                "".join(links))
                return
            if path.startswith("/report/"):
                payload = store.get(unquote(path[len("/report/"):]))
                if payload is None:
                    self._send(404, "Report not found.\n", "text/plain; charset=utf-8")
                else:
                    self._send(200, "<!doctype html><meta name=\"viewport\" content=\"width=device-width\">"
                                    "<title>Milou report</title><pre>%s</pre>" %
                                    html.escape(payload.get("markdown", "")))
                return
            self._send(404, "Not found.\n", "text/plain; charset=utf-8")

        def log_message(self, *_args):
            return

    return ReportHandler


def serve(store, host="127.0.0.1", port=8080, bearer_token=None, environ=None):
    """Run the private server; bind localhost by default and never publish."""
    server = ThreadingHTTPServer((host, port), make_handler(store, bearer_token, environ))
    server.serve_forever()
