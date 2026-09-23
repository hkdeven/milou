"""Signing in once, and staying signed in.

Microsoft and Zoho access tokens last about an hour. Until now Milou read one
from an environment variable and used it as-is, which is fine for a single
command and useless for something you leave open: you would paste a new token
into the terminal every hour.

This is the flow that fixes it. You sign in once in a browser; Milou keeps the
**refresh** token and exchanges it for a fresh access token whenever the current
one is close to expiring. Nothing is pasted, and nothing long-lived sits in your
shell history or in a file the next `env` dump prints.

Three decisions worth stating.

**The redirect comes back to this machine.** The browser is sent to
``http://127.0.0.1:<port>/callback``, which a one-request server answers and then
shuts down. That is the flow Microsoft documents for a desktop application, and
it means the authorisation code never travels through anyone else's server.

**Microsoft is a public client with PKCE.** There is no client secret to store,
because there is nothing a stolen copy of Milou's configuration could be used
for. Zoho's OAuth does require a client secret; it is kept in the same place as
the tokens rather than in the configuration file.

**Tokens live in the Keychain on macOS.** `security(1)` ships with the system,
so this needs no dependency, and the secrets end up somewhere the operating
system already protects and the user already knows how to inspect and revoke.
Elsewhere they fall back to a file that is created 0600 and checked on every
read.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Mapping, Optional, Sequence, Tuple

from . import explain

#: Refresh this long before the token actually expires, so a request that takes
#: a moment to build does not go out with one that died in between.
EXPIRY_MARGIN = 120

#: Where the loopback redirect lands. Registered in the app registration too.
DEFAULT_PORT = 8765
REDIRECT_PATH = "/callback"


class OAuthError(Exception):
    """Raised when a sign-in or a refresh cannot be completed."""


# --------------------------------------------------------------------- stores


class KeychainStore:
    """macOS Keychain, through the `security` command that ships with it."""

    SERVICE = "milou"

    def __init__(self, service: str = SERVICE, runner=None):
        self.service = service
        self._run = runner or self._security

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin"

    @staticmethod
    def _security(args, payload=None):
        return subprocess.run(["security"] + list(args), input=payload, capture_output=True,
                              text=True, timeout=15)

    def read(self, name: str) -> Optional[dict]:
        result = self._run(["find-generic-password", "-s", self.service, "-a", name, "-w"])
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout.strip())
        except ValueError:
            return None

    def write(self, name: str, record: Mapping) -> None:
        # -U updates in place when the item already exists, so signing in again
        # replaces the tokens instead of stacking duplicates.
        result = self._run(["add-generic-password", "-U", "-s", self.service, "-a", name,
                            "-w", json.dumps(record)])
        if result.returncode != 0:
            raise OAuthError(
                "Could not save the sign-in to your Keychain (%s). Milou will not hold a "
                "token it cannot store, so nothing was saved."
                % (result.stderr.strip() or "the security command failed"))

    def forget(self, name: str) -> None:
        self._run(["delete-generic-password", "-s", self.service, "-a", name])


class FileStore:
    """A 0600 file, for machines without a Keychain.

    The permissions are enforced on write and verified on read: a token file
    that became world-readable is a problem worth refusing to use rather than
    quietly carrying on with.
    """

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def read(self, name: str) -> Optional[dict]:
        try:
            info = os.stat(self.path)
        except FileNotFoundError:
            return None
        if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise OAuthError(
                "%s holds your sign-in tokens and is readable by other accounts on this "
                "machine. Milou will not read it until that is fixed: run `chmod 600 %s`."
                % (self.path, self.path))
        try:
            with open(self.path, encoding="utf-8") as handle:
                return json.load(handle).get(name)
        except (ValueError, OSError):
            return None

    def write(self, name: str, record: Mapping) -> None:
        existing = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as handle:
                    existing = json.load(handle)
            except (ValueError, OSError):
                existing = {}
        existing[name] = dict(record)
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        # Create with the right mode from the start, rather than writing the
        # secret and then narrowing permissions a moment later.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=1)
        os.chmod(self.path, 0o600)

    def forget(self, name: str) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                existing = json.load(handle)
        except (ValueError, OSError):
            return
        existing.pop(name, None)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=1)


def default_store(path: str = "~/.milou/tokens.json"):
    """The Keychain where there is one, a private file where there is not."""
    return KeychainStore() if KeychainStore.available() else FileStore(path)


# ----------------------------------------------------------------- providers


@dataclass(frozen=True)
class OAuthApp:
    """One identity provider, as this application talks to it."""

    name: str
    label: str
    client_id: str
    authorize_url: str
    token_url: str
    scopes: Tuple[str, ...]
    #: Zoho requires one; Microsoft public clients must not have one.
    client_secret: str = ""
    #: Extra parameters the provider needs on the authorize request.
    extra_authorize: Mapping = field(default_factory=dict)
    uses_pkce: bool = True


def microsoft(client_id: str, tenant: str = "organizations",
              scopes: Sequence[str] = ()) -> OAuthApp:
    root = "https://login.microsoftonline.com/%s/oauth2/v2.0" % tenant
    return OAuthApp(
        name="outlook", label="Microsoft 365", client_id=client_id,
        authorize_url=root + "/authorize", token_url=root + "/token",
        # offline_access is what makes a refresh token come back at all.
        scopes=tuple(scopes) + ("offline_access",),
        extra_authorize={"response_mode": "query"}, uses_pkce=True)


def zoho(client_id: str, client_secret: str, scopes: Sequence[str] = (),
         region: str = "com") -> OAuthApp:
    root = "https://accounts.zoho.%s/oauth/v2" % region
    return OAuthApp(
        name="zoho", label="Zoho Projects", client_id=client_id, client_secret=client_secret,
        authorize_url=root + "/auth", token_url=root + "/token", scopes=tuple(scopes),
        # access_type=offline is Zoho's equivalent of offline_access, and it
        # only returns a refresh token when consent is re-prompted.
        extra_authorize={"access_type": "offline", "prompt": "consent"}, uses_pkce=False)


# --------------------------------------------------------------------- flow


def _pkce() -> Tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def authorize_url(app: OAuthApp, redirect_uri: str, state: str, challenge: str = "") -> str:
    query = {
        "client_id": app.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(app.scopes),
        "state": state,
    }
    query.update(app.extra_authorize)
    if app.uses_pkce and challenge:
        query.update({"code_challenge": challenge, "code_challenge_method": "S256"})
    return app.authorize_url + "?" + urllib.parse.urlencode(query)


def _post_form(url: str, form: Mapping, timeout: int = 20) -> dict:
    """Exchange at the token endpoint. Never logs or returns the request body."""
    data = urllib.parse.urlencode(form).encode("ascii")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The body of a token-endpoint error carries a useful `error` code and
        # nothing secret, but it can echo the request, so only the code is kept.
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = str(payload.get("error") or "")
        except Exception:
            detail = ""
        raise OAuthError(_token_failure(url, exc.code, detail))
    except urllib.error.URLError as exc:
        raise OAuthError(explain.unreachable("the sign-in service", "exchanging the token",
                                             str(exc.reason)))
    except (ValueError, TimeoutError):
        raise OAuthError(explain.unreadable("the sign-in service", "exchanging the token"))


def _token_failure(url: str, code: int, error: str) -> str:
    if error == "invalid_grant":
        return ("The saved sign-in is no longer accepted. That happens when the refresh token "
                "was revoked, the password changed, or it simply went unused for too long. "
                "Run `milou login` again to sign in once more.")
    if error in ("invalid_client", "unauthorized_client"):
        return ("The sign-in service did not recognise this application's client id. Check "
                "`oauth.client_id` in your console configuration against the app registration.")
    if error == "invalid_scope":
        return ("The sign-in service refused one of the requested permissions. Check the scopes "
                "on the app registration match the ones Milou asks for.")
    return ("The sign-in service refused the token request (HTTP %s%s). See %s."
            % (code, ", %s" % error if error else "", explain.RUNBOOK))


class _CallbackHandler(BaseHTTPRequestHandler):
    """Answers exactly one redirect, then lets the server stop."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.parse_qs(parsed.query)
        self.server.result = {key: values[0] for key, values in query.items()}
        ok = "code" in self.server.result
        body = (
            "<!doctype html><meta charset='utf-8'>"
            "<title>Milou</title>"
            "<body style=\"font-family:-apple-system,system-ui,sans-serif;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;"
            "background:#F2F2F6;color:#1D1D1F\">"
            "<div style=\"text-align:center;max-width:32ch\">"
            "<p style=\"font-size:19px;font-weight:600;margin:0 0 8px\">%s</p>"
            "<p style=\"font-size:14px;color:#5C5C61;margin:0\">%s</p></div></body>"
            % ("Signed in" if ok else "Sign-in did not complete",
               "You can close this tab and go back to Milou."
               if ok else "Nothing was saved. Go back to the terminal and try again.")
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def wait_for_code(port: int, timeout: int = 300) -> dict:
    """Serve one redirect on loopback and return its query parameters."""
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.result = None
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                              daemon=True)
    thread.start()
    deadline = time.time() + timeout
    try:
        while server.result is None and time.time() < deadline:
            time.sleep(0.2)
    finally:
        server.shutdown()
        server.server_close()
    if server.result is None:
        raise OAuthError(
            "The browser never came back with a sign-in, so nothing was saved. If the page "
            "did open, check that the app registration lists "
            "http://localhost:%d%s as a redirect URI for a mobile and desktop application."
            % (port, REDIRECT_PATH))
    return server.result


def sign_in(app: OAuthApp, store, port: int = DEFAULT_PORT, opener=None,
            waiter=None, exchange=None) -> dict:
    """Run the browser sign-in once and save what comes back.

    ``opener``, ``waiter`` and ``exchange`` are injectable so the whole flow can
    be exercised without a browser or a network.
    """
    redirect_uri = "http://localhost:%d%s" % (port, REDIRECT_PATH)
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce() if app.uses_pkce else ("", "")
    url = authorize_url(app, redirect_uri, state, challenge)

    (opener or webbrowser.open)(url)
    returned = (waiter or wait_for_code)(port)

    if returned.get("error"):
        raise OAuthError(
            "%s refused the sign-in (%s). Nothing was saved."
            % (app.label, returned.get("error_description") or returned["error"]))
    if not secrets.compare_digest(str(returned.get("state", "")), state):
        # A mismatched state means the redirect did not come from the request
        # this process started, so the code in it is not to be trusted.
        raise OAuthError(
            "The sign-in that came back did not match the one Milou started, so it was "
            "discarded and nothing was saved. Run `milou login` again.")

    form = {"client_id": app.client_id, "grant_type": "authorization_code",
            "code": returned.get("code", ""), "redirect_uri": redirect_uri}
    if app.client_secret:
        form["client_secret"] = app.client_secret
    if app.uses_pkce:
        form["code_verifier"] = verifier
    payload = (exchange or _post_form)(app.token_url, form)
    record = _record(payload, app)
    if not record.get("refresh_token"):
        raise OAuthError(
            "%s signed you in but did not return a refresh token, so Milou would be back to "
            "an hourly re-login. For Microsoft, check `offline_access` is in the requested "
            "scopes; for Zoho, that the consent screen was shown rather than skipped."
            % app.label)
    store.write(app.name, record)
    return record


def _record(payload: Mapping, app: OAuthApp) -> dict:
    expires_in = int(payload.get("expires_in") or 3600)
    return {
        "access_token": str(payload.get("access_token") or ""),
        "refresh_token": str(payload.get("refresh_token") or ""),
        "expires_at": int(time.time()) + expires_in,
        "scopes": " ".join(app.scopes),
        "provider": app.name,
    }


class Credentials:
    """A live access token for one provider, refreshed as needed.

    Every adapter asks this for a token immediately before a request rather than
    holding one, so a session that outlives an hour never sends a dead token.
    """

    def __init__(self, app: OAuthApp, store, exchange=None, clock=time.time):
        self.app = app
        self.store = store
        self._exchange = exchange or _post_form
        self._clock = clock
        self._lock = threading.Lock()

    def signed_in(self) -> bool:
        return bool((self.store.read(self.app.name) or {}).get("refresh_token"))

    def token(self) -> str:
        with self._lock:
            record = self.store.read(self.app.name)
            if not record:
                raise OAuthError(
                    "You are not signed in to %s yet. Run `milou login %s` once; after that "
                    "Milou keeps itself signed in." % (self.app.label, self.app.name))
            if record.get("access_token") and \
                    int(record.get("expires_at", 0)) - EXPIRY_MARGIN > self._clock():
                return record["access_token"]
            return self._refresh(record)

    def _refresh(self, record: Mapping) -> str:
        refresh_token = record.get("refresh_token")
        if not refresh_token:
            raise OAuthError(
                "The saved %s sign-in has no refresh token, so it cannot be renewed. Run "
                "`milou login %s` once more." % (self.app.label, self.app.name))
        form = {"client_id": self.app.client_id, "grant_type": "refresh_token",
                "refresh_token": refresh_token}
        if self.app.client_secret:
            form["client_secret"] = self.app.client_secret
        payload = self._exchange(self.app.token_url, form)
        fresh = _record(payload, self.app)
        # Microsoft rotates refresh tokens and Zoho does not return one on a
        # refresh at all, so the old one is kept unless a new one arrives.
        fresh["refresh_token"] = fresh["refresh_token"] or refresh_token
        if not fresh["access_token"]:
            raise OAuthError(
                "%s accepted the refresh but returned no access token. Nothing was changed; "
                "run `milou login %s` to sign in again." % (self.app.label, self.app.name))
        self.store.write(self.app.name, fresh)
        return fresh["access_token"]


@dataclass(frozen=True)
class OAuthConfig:
    """The `oauth` section of the console configuration."""

    client_id: str = ""
    tenant: str = "organizations"
    zoho_client_id: str = ""
    zoho_region: str = "com"
    port: int = DEFAULT_PORT
    token_file: str = "~/.milou/tokens.json"

    @classmethod
    def from_mapping(cls, value: Mapping) -> "OAuthConfig":
        value = value or {}
        return cls(
            client_id=str(value.get("client_id") or ""),
            tenant=str(value.get("tenant") or "organizations"),
            zoho_client_id=str(value.get("zoho_client_id") or ""),
            zoho_region=str(value.get("zoho_region") or "com"),
            port=int(value.get("port") or DEFAULT_PORT),
            token_file=str(value.get("token_file") or "~/.milou/tokens.json"),
        )


#: What each provider is asked for. Read scopes only until a write is enabled,
#: so the consent screen shows the smallest thing that works.
GRAPH_READ = ("https://graph.microsoft.com/Mail.Read",)
GRAPH_SEND = ("https://graph.microsoft.com/Mail.Send",)
GRAPH_DRAFT = ("https://graph.microsoft.com/Mail.ReadWrite",)
GRAPH_FILES = ("https://graph.microsoft.com/Files.ReadWrite.All",)
ZOHO_READ = ("ZohoProjects.portals.READ", "ZohoProjects.projects.READ",
             "ZohoProjects.activities.READ", "ZohoProjects.tasks.READ")
ZOHO_WRITE = ("ZohoProjects.tasks.CREATE",)


def graph_app(config: OAuthConfig, scopes: Sequence[str] = GRAPH_READ) -> OAuthApp:
    if not config.client_id:
        raise OAuthError(explain.not_configured(
            "oauth.client_id", "Milou does not know which Azure app registration to sign in with",
            "the Application (client) ID from the app registration overview"))
    return microsoft(config.client_id, config.tenant, scopes)


def zoho_app(config: OAuthConfig, client_secret: str,
             scopes: Sequence[str] = ZOHO_READ) -> OAuthApp:
    if not config.zoho_client_id:
        raise OAuthError(explain.not_configured(
            "oauth.zoho_client_id", "Milou does not know which Zoho client to sign in with",
            "the Client ID from the Zoho API console"))
    return zoho(config.zoho_client_id, client_secret, scopes, config.zoho_region)
