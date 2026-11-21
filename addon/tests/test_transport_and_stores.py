import ctypes
import io
import logging
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

import support
from addon.models.auth import AddonError
from addon.services.credentials import LinuxSecretService, MacKeychain
from addon.services.http import JsonHttp, MAX_RESPONSE_BYTES, NoRedirect
from addon.services.privacy import LOGGER, event


class TransportTests(unittest.TestCase):
    def response(self, data):
        response = Mock(status=200)
        response.read.return_value = data
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_form_encoded_request_and_bounded_json_response(self):
        http = JsonHttp()
        opener = Mock()
        http._opener = opener
        response = self.response(b'{"access_token":"synthetic"}')
        opener.open.return_value = response
        result = http.request("https://identity.example.test/token", {"code": "a+b&c", "code_verifier": "synthetic"})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(parse_qs(request.data.decode()), {"code": ["a+b&c"], "code_verifier": ["synthetic"]})
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        self.assertEqual(result, {"access_token": "synthetic"})

    def test_invalid_json_oversized_and_nonobject_responses_have_safe_errors(self):
        http = JsonHttp()
        http._opener = Mock()
        for data in (b"private-not-json", b"[]", b"x" * (MAX_RESPONSE_BYTES + 1), b"\xff"):
            http._opener.open.return_value = self.response(data)
            with self.assertRaises(AddonError) as caught:
                http.request("https://identity.example.test/token")
            self.assertEqual(caught.exception.code, "response")
            self.assertNotIn("private", str(caught.exception))

    def test_http_failure_never_exposes_provider_body_and_redirects_never_followed(self):
        http = JsonHttp()
        http._opener = Mock()
        for status, expected in ((400, "denied"), (401, "denied"), (500, "network"), (302, "network")):
            http._opener.open.side_effect = HTTPError(
                "https://private.example.test/token?code=private-code", status,
                "private-description", {}, io.BytesIO(b"private-token"),
            )
            with self.assertRaises(AddonError) as caught:
                http.request("https://identity.example.test/token", {"refresh_token": "private-refresh"})
            self.assertEqual(caught.exception.code, expected)
            self.assertNotIn("private", str(caught.exception))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "http://attacker.example.test"))

    def test_logger_allows_only_fixed_events_without_private_fields(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        LOGGER.addHandler(handler)
        old_level = LOGGER.level
        LOGGER.setLevel(logging.INFO)
        try:
            event("loaded")
            event("credential")
            with self.assertRaises(ValueError):
                event("private-token")
            self.assertEqual(
                stream.getvalue(),
                "anki_ai_deck_generator event=loaded\nanki_ai_deck_generator event=credential\n",
            )
        finally:
            LOGGER.setLevel(old_level)
            LOGGER.removeHandler(handler)


class StoreTests(unittest.TestCase):
    def test_linux_uses_secret_service_with_token_on_stdin_not_argv(self):
        store = LinuxSecretService("synthetic-account")
        with patch("addon.services.credentials.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
            store.write("synthetic-refresh-token")
            args = run.call_args.args[0]
            self.assertEqual(args[0], "/usr/bin/secret-tool")
            self.assertIn("store", args)
            self.assertNotIn("synthetic-refresh-token", " ".join(args))
            self.assertEqual(run.call_args.kwargs["input"], b"synthetic-refresh-token")
            self.assertTrue(run.call_args.kwargs["capture_output"])
            run.return_value = subprocess.CompletedProcess([], 0, b"synthetic-refresh-token\n", b"")
            self.assertEqual(store.read(), "synthetic-refresh-token")
            run.return_value = subprocess.CompletedProcess([], 1, b"", b"")
            self.assertIsNone(store.read())
            store.delete()
            self.assertIn("clear", run.call_args.args[0])

    def test_linux_locked_missing_and_timed_out_stores_fail_without_file_fallback(self):
        store = LinuxSecretService("synthetic-account")
        with patch("addon.services.credentials.subprocess.run") as run:
            for failure in (
                subprocess.CompletedProcess([], 1, b"", b"private-store-error"),
                FileNotFoundError("private-path"),
                subprocess.TimeoutExpired("private-command", 15),
            ):
                run.side_effect = failure if isinstance(failure, Exception) else None
                run.return_value = failure
                with self.assertRaises(AddonError) as caught:
                    store.read()
                self.assertEqual(caught.exception.code, "credential")
                self.assertNotIn("private", str(caught.exception))
            run.side_effect = None
            run.return_value = subprocess.CompletedProcess([], 2, b"", b"private")
            for action in (lambda: store.write("synthetic-token"), store.delete):
                with self.assertRaises(AddonError):
                    action()

    @unittest.skipUnless(sys.platform == "darwin", "CoreFoundation available only on macOS")
    def test_mac_native_bindings_and_query_memory_without_touching_keychain(self):
        store = MacKeychain("synthetic-account")
        query = store._query()
        self.assertTrue(query)
        store.cf.CFRelease(query)
        data = b"synthetic-token"
        pointer = store.cf.CFDataCreate(None, data, len(data))
        try:
            self.assertEqual(store.cf.CFDataGetLength(pointer), len(data))
            self.assertEqual(ctypes.string_at(store.cf.CFDataGetBytePtr(pointer), len(data)), data)
        finally:
            store.cf.CFRelease(pointer)


if __name__ == "__main__":
    unittest.main()
