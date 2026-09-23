"""Tests for signing in once and staying signed in.

Access tokens last about an hour, so the property that matters is that nothing
in Milou ever holds one long enough for it to die: a token is asked for
immediately before a request, and renewed when it is close to expiring.
"""


import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import oauth
from milou_news.oauth import (Credentials, FileStore, KeychainStore, OAuthConfig, OAuthError,
                              authorize_url, microsoft, sign_in, zoho)
from milou_news.outlook import GraphApi

SECRET = "refresh-token-do-not-print"
APP = microsoft("client-123", "contoso", ["https://graph.microsoft.com/Mail.Read"])
ZOHO = zoho("zoho-client", "zoho-secret", ["ZohoProjects.tasks.READ"])


class MemoryStore:
    def __init__(self, seed=None):
        self.saved = dict(seed or {})

    def read(self, name):
        return self.saved.get(name)

    def write(self, name, record):
        self.saved[name] = dict(record)

    def forget(self, name):
        self.saved.pop(name, None)


class AuthorizeTest(unittest.TestCase):

    def test_a_refresh_token_is_actually_requested(self):
        # Without offline_access Microsoft returns an access token only, and
        # Milou would be back to an hourly re-login.
        self.assertIn("offline_access", APP.scopes)
        self.assertIn("access_type=offline",
                      authorize_url(ZOHO, "http://localhost:8765/callback", "s"))

    def test_the_url_carries_pkce_for_a_public_client(self):
        verifier, challenge = oauth._pkce()
        url = authorize_url(APP, "http://localhost:8765/callback", "state-1", challenge)
        self.assertIn("code_challenge_method=S256", url)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(challenge, expected)

    def test_a_public_client_carries_no_secret(self):
        self.assertEqual(APP.client_secret, "", "a desktop app has nothing to keep secret")


class SignInTest(unittest.TestCase):

    def _exchange(self, refresh="r1"):
        def exchange(url, form):
            self.form = dict(form)
            return {"access_token": "a1", "refresh_token": refresh, "expires_in": 3600}
        return exchange

    def test_a_completed_sign_in_is_saved_and_nothing_is_returned_to_the_caller(self):
        store = MemoryStore()
        captured = {}
        record = sign_in(APP, store, opener=lambda url: captured.update(url=url),
                         waiter=lambda port: {"code": "c", "state": _state(captured["url"])},
                         exchange=self._exchange())
        self.assertEqual(store.saved["outlook"]["refresh_token"], "r1")
        self.assertGreater(record["expires_at"], time.time())

    def test_a_redirect_from_a_different_request_is_discarded(self):
        # A mismatched state means the code did not come from the sign-in this
        # process started, so it is not to be trusted.
        store = MemoryStore()
        with self.assertRaises(OAuthError) as caught:
            sign_in(APP, store, opener=lambda url: None,
                    waiter=lambda port: {"code": "c", "state": "somebody-elses"},
                    exchange=self._exchange())
        self.assertIn("did not match", str(caught.exception))
        self.assertEqual(store.saved, {}, "nothing is saved when the redirect is suspect")

    def test_a_sign_in_without_a_refresh_token_is_refused_loudly(self):
        store = MemoryStore()
        captured = {}
        with self.assertRaises(OAuthError) as caught:
            sign_in(APP, store, opener=lambda url: captured.update(url=url),
                    waiter=lambda port: {"code": "c", "state": _state(captured["url"])},
                    exchange=self._exchange(refresh=""))
        self.assertIn("offline_access", str(caught.exception))
        self.assertEqual(store.saved, {}, "half a sign-in is worse than none")

    def test_a_refusal_at_the_provider_is_reported_in_its_own_words(self):
        with self.assertRaises(OAuthError) as caught:
            sign_in(APP, MemoryStore(), opener=lambda url: None,
                    waiter=lambda port: {"error": "access_denied",
                                         "error_description": "user cancelled"},
                    exchange=self._exchange())
        self.assertIn("user cancelled", str(caught.exception))
        self.assertIn("Nothing was saved", str(caught.exception))


class CredentialsTest(unittest.TestCase):

    def _store(self, expires_in=3600, refresh=SECRET):
        return MemoryStore({"outlook": {
            "access_token": "current", "refresh_token": refresh,
            "expires_at": int(time.time()) + expires_in}})

    def test_a_live_token_is_reused_rather_than_re_fetched(self):
        calls = []
        credentials = Credentials(APP, self._store(),
                                  exchange=lambda url, form: calls.append(form) or {})
        self.assertEqual(credentials.token(), "current")
        self.assertEqual(calls, [], "a token with an hour left needs no round trip")

    def test_a_token_near_expiry_is_renewed_before_it_is_used(self):
        # Renewed early on purpose: a token that dies between being fetched and
        # being sent produces a 401 that looks like a configuration problem.
        store = self._store(expires_in=30)
        credentials = Credentials(APP, store, exchange=lambda url, form: {
            "access_token": "fresh", "refresh_token": "rotated", "expires_in": 3600})
        self.assertEqual(credentials.token(), "fresh")
        self.assertEqual(store.saved["outlook"]["access_token"], "fresh")

    def test_an_expired_token_is_renewed(self):
        store = self._store(expires_in=-10)
        credentials = Credentials(APP, store, exchange=lambda url, form: {
            "access_token": "fresh", "expires_in": 3600})
        self.assertEqual(credentials.token(), "fresh")

    def test_a_provider_that_returns_no_new_refresh_token_keeps_the_old_one(self):
        # Zoho does not return one on a refresh; discarding it would sign the
        # user out an hour later for no reason.
        store = self._store(expires_in=-10)
        credentials = Credentials(APP, store, exchange=lambda url, form: {
            "access_token": "fresh", "expires_in": 3600})
        credentials.token()
        self.assertEqual(store.saved["outlook"]["refresh_token"], SECRET)

    def test_not_being_signed_in_says_which_command_to_run(self):
        credentials = Credentials(APP, MemoryStore())
        with self.assertRaises(OAuthError) as caught:
            credentials.token()
        self.assertIn("milou login outlook", str(caught.exception))

    def test_a_revoked_sign_in_is_explained_rather_than_raw(self):
        import urllib.error

        def refuse(url, form):
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)

        store = self._store(expires_in=-10)
        credentials = Credentials(APP, store, exchange=lambda url, form: oauth._post_form(url, form))
        original = oauth.urllib.request.urlopen
        oauth.urllib.request.urlopen = lambda request, timeout=None: refuse(request.full_url, {})
        try:
            with self.assertRaises(OAuthError) as caught:
                credentials.token()
        finally:
            oauth.urllib.request.urlopen = original
        self.assertIn(str(400), str(caught.exception))
        self.assertNotIn(SECRET, str(caught.exception), "never echo the token that was refused")


class AdapterTest(unittest.TestCase):

    def test_an_adapter_asks_for_a_token_per_request(self):
        asked = []

        class Live:
            def token(self):
                asked.append(1)
                return "fresh-%d" % len(asked)

        api = GraphApi(credentials=Live())
        captured = []

        def fake_urlopen(request, timeout=None):
            captured.append(request.headers.get("Authorization"))
            raise ValueError("stop here")

        import milou_news.outlook as outlook
        original = outlook.urllib.request.urlopen
        outlook.urllib.request.urlopen = fake_urlopen
        try:
            api.get("/me")
            api.get("/me")
        finally:
            outlook.urllib.request.urlopen = original
        self.assertEqual(len(asked), 2, "held tokens go stale; ask each time")
        self.assertEqual(captured, ["Bearer fresh-1", "Bearer fresh-2"])

    def test_a_sign_in_problem_surfaces_as_the_report_error(self):
        class Refusing:
            def token(self):
                raise OAuthError("You are not signed in to Microsoft 365 yet.")

        result = GraphApi(credentials=Refusing()).get("/me")
        self.assertIsNone(result.data)
        self.assertIn("not signed in", result.error)


class FileStoreTest(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "nested", "tokens.json")

    def tearDown(self):
        self.directory.cleanup()

    def test_tokens_are_written_private_to_this_account(self):
        store = FileStore(self.path)
        store.write("outlook", {"refresh_token": SECRET})
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(store.read("outlook")["refresh_token"], SECRET)

    def test_a_readable_token_file_is_refused_rather_than_used(self):
        store = FileStore(self.path)
        store.write("outlook", {"refresh_token": SECRET})
        os.chmod(self.path, 0o644)
        with self.assertRaises(OAuthError) as caught:
            store.read("outlook")
        self.assertIn("chmod 600", str(caught.exception))

    def test_signing_in_to_one_provider_leaves_the_other_alone(self):
        store = FileStore(self.path)
        store.write("outlook", {"refresh_token": "a"})
        store.write("zoho", {"refresh_token": "b"})
        store.forget("outlook")
        self.assertIsNone(store.read("outlook"))
        self.assertEqual(store.read("zoho")["refresh_token"], "b")


class KeychainStoreTest(unittest.TestCase):

    class _Runner:
        def __init__(self, stored=None, code=0):
            self.stored, self.code, self.calls = stored, code, []

        def __call__(self, args, payload=None):
            self.calls.append(args)

            class Result:
                pass
            result = Result()
            result.returncode = self.code
            result.stdout = self.stored or ""
            result.stderr = "" if self.code == 0 else "denied"
            return result

    def test_a_saved_item_is_read_back(self):
        runner = self._Runner(stored=json.dumps({"refresh_token": SECRET}))
        self.assertEqual(KeychainStore(runner=runner).read("outlook")["refresh_token"], SECRET)

    def test_signing_in_again_replaces_rather_than_stacks(self):
        runner = self._Runner()
        KeychainStore(runner=runner).write("outlook", {"refresh_token": SECRET})
        self.assertIn("-U", runner.calls[0], "without -U the Keychain grows a duplicate each time")

    def test_a_keychain_refusal_is_not_swallowed(self):
        with self.assertRaises(OAuthError) as caught:
            KeychainStore(runner=self._Runner(code=1)).write("outlook", {"refresh_token": "x"})
        self.assertIn("nothing was saved", str(caught.exception).lower())

    def test_a_missing_item_reads_as_not_signed_in(self):
        self.assertIsNone(KeychainStore(runner=self._Runner(code=44)).read("outlook"))


class ConfigTest(unittest.TestCase):

    def test_an_unconfigured_client_id_names_the_setting(self):
        with self.assertRaises(OAuthError) as caught:
            oauth.graph_app(OAuthConfig())
        self.assertIn("oauth.client_id", str(caught.exception))


def _state(url):
    import urllib.parse
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]


if __name__ == "__main__":
    unittest.main()
