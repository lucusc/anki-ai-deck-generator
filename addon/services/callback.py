import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event
from urllib.parse import parse_qs, urlsplit

from ..models.auth import AddonError


class LoopbackCallback:
    """One bounded, state-bound authorization response on IPv4 loopback."""

    def __init__(self, state: str, issuer: str, require_issuer: bool):
        self.state = state
        self.issuer = issuer
        self.require_issuer = require_issuer
        self.code: str | None = None
        self.error: AddonError | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                try:
                    fields = parse_qs(parsed.query, strict_parsing=True, max_num_fields=10)
                except ValueError:
                    fields = {}
                valid = (
                    len(self.path) <= 8192
                    and not parsed.scheme and not parsed.netloc and not parsed.fragment
                    and parsed.path == "/oauth/callback"
                    and self.headers.get("Host") == outer.host
                    and all(len(values) == 1 for values in fields.values())
                    and secrets.compare_digest(
                        fields.get("state", [""])[0].encode("utf-8"), outer.state.encode("utf-8")
                    )
                    and ("iss" in fields or not outer.require_issuer)
                    and ("iss" not in fields or fields["iss"][0] == outer.issuer)
                    and (("code" in fields) != ("error" in fields))
                )
                if valid:
                    if "error" in fields:
                        outer.error = AddonError("denied")
                    else:
                        outer.code = fields["code"][0]
                message = b"Sign-in response received. Return to Anki." if valid else b"Invalid sign-in response."
                self.send_response(200 if valid else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                try:
                    self.wfile.write(message)
                except (BrokenPipeError, ConnectionResetError):
                    # The validated callback remains valid if the browser closes.
                    pass

        class Server(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(0.5)
                return connection, address

            def handle_error(self, request, client_address):
                from .privacy import event

                event("listener")

        try:
            self.server = Server(("127.0.0.1", 0), Handler)
        except OSError:
            raise AddonError("listener") from None
        self.server.timeout = 0.2
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.redirect_uri = f"http://{self.host}/oauth/callback"

    def wait(self, cancel: Event, timeout: float = 180) -> str:
        deadline = time.monotonic() + timeout
        while self.code is None and self.error is None:
            if cancel.is_set():
                raise AddonError("cancelled")
            if time.monotonic() >= deadline:
                raise AddonError("timeout")
            self.server.handle_request()
        if cancel.is_set():
            raise AddonError("cancelled")
        if self.error:
            raise self.error
        assert self.code is not None
        return self.code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.server.server_close()
