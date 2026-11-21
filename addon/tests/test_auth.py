import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from http.client import HTTPConnection
from unittest.mock import Mock
from urllib.parse import parse_qs, urlencode, urlsplit

import support
from addon.models.auth import AddonError, OAuthConfig, TokenSet
from addon.services.callback import LoopbackCallback
from addon.services.credentials import credential_account
from addon.services.oauth import OAuthSession, pkce_challenge

CONFIG = {
    "issuer": "https://identity.example.test/tenant",
    "client_id": "public-client",
    "audience": "https://api.example.test",
    "scopes": ["openid", "offline_access", "study.read"],
}
METADATA = {
    "issuer": CONFIG["issuer"],
    "authorization_endpoint": "https://identity.example.test/authorize",
    "token_endpoint": "https://identity.example.test/token",
    "code_challenge_methods_supported": ["S256"],
    "authorization_response_iss_parameter_supported": True,
}
TOKENS = {
    "access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
    "token_type": "Bearer", "expires_in": 3600,
}


class Store:
    def __init__(self):
        self.value = None
        self.writes = []
        self.deleted = 0
        self.failure = False

    def read(self):
        return self.value

    def write(self, value):
        if self.failure:
            raise AddonError("credential")
        self.value = value
        self.writes.append(value)

    def delete(self):
        self.value = None
        self.deleted += 1


class FakeHttp:
    def __init__(self, tokens=None):
        self.tokens = dict(TOKENS if tokens is None else tokens)
        self.metadata = dict(METADATA)
        self.calls = []
        self.failure = None

    def request(self, url, form=None):
        self.calls.append((url, form))
        if form is None:
            return self.metadata
        if self.failure:
            raise AddonError(self.failure)
        return self.tokens


class Callback:
    redirect_uri = "http://127.0.0.1:54321/oauth/callback"

    def __init__(self, state, issuer, require_issuer):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def wait(self, cancel):
        return "synthetic-code"


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.config = OAuthConfig.from_mapping(CONFIG)
        self.store = Store()
        self.http = FakeHttp()
        self.browser = Mock(return_value=True)
        self.now = 1000
        self.session = OAuthSession(
            self.config, "Synthetic profile", http=self.http,
            store_factory=lambda config, profile: self.store,
            open_browser=self.browser, callback_factory=Callback,
            clock=lambda: self.now,
        )

    def assert_code(self, code, operation):
        with self.assertRaises(AddonError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_browser_pkce_wires_verifier_state_client_scope_and_redirect(self):
        self.session.sign_in()
        params = parse_qs(urlsplit(self.browser.call_args.args[0]).query)
        form = self.http.calls[-1][1]
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["code_challenge"], [pkce_challenge(form["code_verifier"])])
        self.assertGreaterEqual(len(form["code_verifier"]), 43)
        self.assertLessEqual(len(form["code_verifier"]), 128)
        self.assertGreaterEqual(len(params["state"][0]), 43)
        self.assertEqual(params["client_id"], [form["client_id"]])
        self.assertEqual(params["audience"], [CONFIG["audience"]])
        self.assertEqual(params["scope"], [" ".join(CONFIG["scopes"])])
        self.assertEqual(params["redirect_uri"], [form["redirect_uri"]])
        self.assertEqual(form["code"], "synthetic-code")
        self.assertEqual(form["grant_type"], "authorization_code")
        self.assertNotIn("client_secret", form)
        self.assertNotIn("code_verifier", params)
        self.assertEqual(self.store.writes, ["synthetic-refresh"])
        self.assertEqual(self.session.access_token(), "synthetic-access")
        self.assertEqual(len(self.http.calls), 2)
        first_state = params["state"]
        self.session.sign_in()
        second = parse_qs(urlsplit(self.browser.call_args.args[0]).query)
        self.assertNotEqual(first_state, second["state"])
        self.assertNotEqual(params["code_challenge"], second["code_challenge"])

    def test_refresh_rotation_expiry_and_no_refresh_response_preserves_saved_token(self):
        self.store.value = "old-refresh"
        self.assertEqual(self.session.access_token(), "synthetic-access")
        self.assertEqual(self.http.calls[-1][1]["refresh_token"], "old-refresh")
        self.assertEqual(self.store.value, "synthetic-refresh")
        self.now += 4000
        self.http.tokens = {"access_token": "new-access", "token_type": "bearer", "expires_in": 300}
        self.assertEqual(self.session.access_token(), "new-access")
        self.assertEqual(self.store.value, "synthetic-refresh")

    def test_returned_scope_may_omit_identity_scopes_but_not_api_permission(self):
        self.http.tokens["scope"] = "study.read"
        self.session.sign_in()
        self.assertEqual(self.session.access_token(), "synthetic-access")

    def test_browser_flow_through_real_listener_closes_and_exchanges_matching_code(self):
        self.session.callback_factory = LoopbackCallback
        with ThreadPoolExecutor(max_workers=1) as browser_pool:
            requests = []

            def open_browser(url):
                params = parse_qs(urlsplit(url).query)
                redirect = urlsplit(params["redirect_uri"][0])

                def browser_response():
                    connection = HTTPConnection(redirect.hostname, redirect.port, timeout=3)
                    query = urlencode({
                        "state": params["state"][0], "iss": CONFIG["issuer"],
                        "code": "synthetic-code",
                    })
                    connection.request("GET", redirect.path + "?" + query)
                    response = connection.getresponse()
                    body = response.read()
                    connection.close()
                    return response.status, body

                requests.append(browser_pool.submit(browser_response))
                return True

            self.session.open_browser = open_browser
            self.session.sign_in()
            status, body = requests[0].result(timeout=3)
            self.assertEqual(status, 200)
            self.assertNotIn(b"synthetic-code", body)
            self.assertEqual(self.http.calls[-1][1]["code"], "synthetic-code")
            self.assertEqual(self.store.value, "synthetic-refresh")

    def test_concurrent_refresh_per_session_is_single_flight(self):
        self.store.value = "old-refresh"
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.session.access_token(), range(6)))
        self.assertEqual(results, ["synthetic-access"] * 6)
        self.assertEqual(len(self.http.calls), 2)

    def test_refresh_denial_deletes_saved_credential_but_network_failure_does_not(self):
        self.store.value = "old-refresh"
        self.http.failure = "network"
        self.assert_code("network", self.session.access_token)
        self.assertEqual(self.store.value, "old-refresh")
        self.http.failure = "denied"
        self.assert_code("denied", self.session.access_token)
        self.assertIsNone(self.store.value)
        self.assert_code("signed_out", self.session.access_token)

    def test_failed_protected_write_never_accepts_access_token(self):
        self.store.failure = True
        self.assert_code("credential", self.session.sign_in)
        self.assertIsNone(self.session._tokens)
        self.assertEqual(self.store.writes, [])

    def test_unavailable_store_fails_before_browser_and_busy_signin_is_explicit(self):
        def fail_read():
            raise AddonError("credential")

        self.store.read = fail_read
        self.assert_code("credential", self.session.sign_in)
        self.browser.assert_not_called()
        self.assertEqual(self.http.calls, [])
        self.session._lock.acquire()
        try:
            self.assert_code("busy", self.session.sign_in)
        finally:
            self.session._lock.release()

    def test_browser_failure_does_not_exchange_code(self):
        self.browser.return_value = False
        self.assert_code("browser", self.session.sign_in)
        self.assertEqual(len(self.http.calls), 1)
        self.assertEqual(self.store.writes, [])

    def test_mismatched_issuer_insecure_endpoints_and_missing_pkce_fail_closed(self):
        for change in (
            {"issuer": "https://other.example.test"},
            {"token_endpoint": "http://identity.example.test/token"},
            {"authorization_endpoint": "https://identity.example.test/authorize?state=override"},
            {"code_challenge_methods_supported": ["plain"]},
        ):
            with self.subTest(change=change):
                self.http.metadata = {**METADATA, **change}
                self.assert_code("provider", self.session.sign_in)
                self.browser.assert_not_called()
                self.assertEqual(self.store.writes, [])

    def test_invalid_token_shapes_and_missing_api_scope_fail_closed(self):
        for change in (
            {"refresh_token": None}, {"access_token": ""},
            {"access_token": "not a bearer"}, {"token_type": "MAC"},
            {"expires_in": True}, {"expires_in": float("inf")}, {"expires_in": 0},
            {"scope": "openid offline_access"}, {"token_type": None},
        ):
            with self.subTest(change=change):
                self.http.tokens = {**TOKENS, **change}
                with self.assertRaises(AddonError):
                    self.session.sign_in()
                self.assertEqual(self.store.writes, [])

    def test_cancel_before_signin_and_during_exchange_does_not_accept(self):
        self.session.close()
        self.assert_code("cancelled", self.session.sign_in)
        self.assertEqual(self.http.calls, [])
        self.session.cancel.clear()
        original = self.http.request

        def request(url, form=None):
            result = original(url, form)
            if form:
                self.session.close()
            return result

        self.http.request = request
        self.assert_code("cancelled", self.session.sign_in)
        self.assertIsNone(self.session._tokens)
        self.assertEqual(self.store.writes, [])

    def test_cancel_during_store_write_removes_new_refresh_and_no_memory_session(self):
        def write(token):
            self.store.value = token
            self.session.close()

        self.store.write = write
        self.assert_code("cancelled", self.session.sign_in)
        self.assertIsNone(self.store.value)
        self.assertIsNone(self.session._tokens)

    def test_signout_clears_memory_and_protected_credential(self):
        self.session.sign_in()
        self.session.sign_out()
        self.assertIsNone(self.session._tokens)
        self.assertIsNone(self.store.value)
        self.assert_code("signed_out", self.session.access_token)

    def test_credentials_are_profile_and_deployment_scoped_and_repr_is_private(self):
        first = credential_account(self.config, "Profile one")
        self.assertNotEqual(first, credential_account(self.config, "Profile two"))
        other = OAuthConfig.from_mapping({**CONFIG, "client_id": "other-client"})
        self.assertNotEqual(first, credential_account(other, "Profile one"))
        self.assertEqual(len(first), 64)
        self.assertNotIn("Profile", first)
        self.assertNotIn("secret", repr(TokenSet("secret-access", "secret-refresh", 10)))

    def test_configuration_rejects_secret_keys_unconfigured_and_insecure_values(self):
        for change in (
            {"issuer": "http://identity.example.test"},
            {"issuer": "https://user:password@identity.example.test"},
            {"issuer": "https://identity.example.test?tenant=one"},
            {"issuer": "https://identity.example.test/#fragment"},
            {"client_secret": "private"},
            {"client_id": ""}, {"audience": ""},
            {"scopes": ["openid", "offline_access"]},
            {"scopes": ["study.read", "offline_access", "offline_access"]},
        ):
            with self.subTest(change=change):
                self.assert_code("configuration", lambda: OAuthConfig.from_mapping({**CONFIG, **change}))
        self.assert_code("configuration", lambda: OAuthConfig.from_mapping(json.loads((support.ROOT / "config.json").read_text())))


class CallbackTests(unittest.TestCase):
    def request(self, callback, query, path="/oauth/callback", host=None):
        connection = HTTPConnection("127.0.0.1", callback.server.server_port, timeout=3)
        connection.request("GET", path + "?" + urlencode(query), headers={"Host": host or callback.host})
        response = connection.getresponse()
        status, body = response.status, response.read()
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertNotIn(b"synthetic-code", body)
        connection.close()
        return status

    def test_real_loopback_rejects_bad_responses_before_matching_code(self):
        with LoopbackCallback("synthetic-state", CONFIG["issuer"], True) as callback:
            self.assertEqual(callback.server.server_address[0], "127.0.0.1")
            with ThreadPoolExecutor(max_workers=1) as pool:
                waiter = pool.submit(callback.wait, threading.Event(), 3)
                good = {"state": "synthetic-state", "iss": CONFIG["issuer"], "code": "synthetic-code"}
                for bad in (
                    {**good, "state": "wrong-state"},
                    {**good, "state": "non-ascii-\u00e9"},
                    {**good, "iss": "https://other.example.test"},
                    {"state": "synthetic-state", "code": "synthetic-code"},
                    {**good, "code": ["synthetic-code", "duplicate"]},
                    {**good, "error": "access_denied"},
                ):
                    # Duplicate fields are encoded separately.
                    if isinstance(bad.get("code"), list):
                        bad = [("state", "synthetic-state"), ("iss", CONFIG["issuer"]), ("code", "a"), ("code", "b")]
                    self.assertEqual(self.request(callback, bad), 400)
                self.assertEqual(self.request(callback, good, path="/other"), 400)
                self.assertEqual(self.request(callback, good, host="attacker.example.test"), 400)
                self.assertEqual(self.request(callback, good), 200)
                self.assertEqual(waiter.result(timeout=3), "synthetic-code")
        self.assertEqual(callback.server.fileno(), -1)

    def test_denial_cancel_and_deadline_are_explicit_and_listener_closes(self):
        with LoopbackCallback("state", CONFIG["issuer"], False) as callback:
            with ThreadPoolExecutor(max_workers=1) as pool:
                waiter = pool.submit(callback.wait, threading.Event(), 3)
                self.assertEqual(self.request(callback, {"state": "state", "error": "private-error-content"}), 200)
                with self.assertRaises(AddonError) as caught:
                    waiter.result(timeout=3)
                self.assertEqual(caught.exception.code, "denied")
                self.assertNotIn("private-error", str(caught.exception))
        with LoopbackCallback("state", CONFIG["issuer"], False) as callback:
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(AddonError) as caught:
                callback.wait(cancel)
            self.assertEqual(caught.exception.code, "cancelled")
        with LoopbackCallback("state", CONFIG["issuer"], False) as callback:
            with self.assertRaises(AddonError) as caught:
                callback.wait(threading.Event(), timeout=0)
            self.assertEqual(caught.exception.code, "timeout")


if __name__ == "__main__":
    unittest.main()
