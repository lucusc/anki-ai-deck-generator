import base64
import hashlib
import math
import secrets
import time
import webbrowser
from threading import Event, Lock
from typing import Callable
from urllib.parse import urlencode, urlsplit

from ..models.auth import AddonError, OAuthConfig, TokenSet, https_url
from .callback import LoopbackCallback
from .credentials import CredentialStore, protected_store
from .http import JsonHttp


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


class OAuthSession:
    def __init__(
        self,
        config: OAuthConfig,
        profile: str,
        *,
        http=None,
        store_factory: Callable[[OAuthConfig, str], CredentialStore] = protected_store,
        open_browser: Callable[[str], bool] = webbrowser.open,
        callback_factory=LoopbackCallback,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.config = config
        self.profile = profile
        self.http = http if http is not None else JsonHttp()
        self.store_factory = store_factory
        self.open_browser = open_browser
        self.callback_factory = callback_factory
        self.clock = clock
        self.cancel = Event()
        self._lock = Lock()
        self._state_lock = Lock()
        self._tokens: TokenSet | None = None

    def _check_cancel(self):
        if self.cancel.is_set():
            raise AddonError("cancelled")

    def _metadata(self) -> dict:
        metadata = self.http.request(self.config.issuer.rstrip("/") + "/.well-known/openid-configuration")
        methods = metadata.get("code_challenge_methods_supported")
        if (
            metadata.get("issuer") != self.config.issuer
            or not isinstance(methods, list) or "S256" not in methods
        ):
            raise AddonError("provider")
        for key in ("authorization_endpoint", "token_endpoint"):
            try:
                endpoint = https_url(metadata.get(key))
            except AddonError:
                raise AddonError("provider") from None
            if urlsplit(endpoint).query:
                raise AddonError("provider")
        return metadata

    def _parse_tokens(self, response: dict, *, initial: bool) -> TokenSet:
        access = response.get("access_token")
        refresh = response.get("refresh_token")
        expires = response.get("expires_in")
        token_type = response.get("token_type")
        if (
            not isinstance(token_type, str) or token_type.lower() != "bearer"
            or not isinstance(access, str) or not access
            or any(not 0x21 <= ord(c) <= 0x7E for c in access)
            or (refresh is not None and (
                not isinstance(refresh, str) or not refresh
                or any(not 0x21 <= ord(c) <= 0x7E for c in refresh)
            ))
            or (initial and refresh is None)
            or isinstance(expires, bool) or not isinstance(expires, (int, float))
            or not math.isfinite(expires) or expires <= 30 or expires > 86400
        ):
            raise AddonError("response")
        returned_scope = response.get("scope")
        api_scopes = set(self.config.scopes) - {"openid", "offline_access", "profile", "email"}
        if returned_scope is not None and (
            not isinstance(returned_scope, str)
            or not api_scopes.issubset(returned_scope.split())
        ):
            raise AddonError("denied")
        return TokenSet(access, refresh, self.clock() + expires - 30)

    def _accept(self, tokens: TokenSet, store: CredentialStore):
        self._check_cancel()
        self._tokens = None
        if tokens.refresh_token is not None:
            store.write(tokens.refresh_token)
        with self._state_lock:
            cancelled = self.cancel.is_set()
            if not cancelled:
                self._tokens = tokens
        if cancelled:
            if tokens.refresh_token is not None:
                store.delete()
            raise AddonError("cancelled")

    def sign_in(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise AddonError("busy")
        try:
            self._check_cancel()
            store = self.store_factory(self.config, self.profile)
            # Fail before opening the browser if the protected store is inaccessible.
            store.read()
            metadata = self._metadata()
            self._check_cancel()
            state = secrets.token_urlsafe(32)
            verifier = secrets.token_urlsafe(64)
            with self.callback_factory(
                state, self.config.issuer,
                metadata.get("authorization_response_iss_parameter_supported") is True,
            ) as callback:
                params = {
                    "response_type": "code", "client_id": self.config.client_id,
                    "redirect_uri": callback.redirect_uri, "scope": " ".join(self.config.scopes),
                    "audience": self.config.audience, "state": state,
                    "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256",
                }
                if not self.open_browser(metadata["authorization_endpoint"] + "?" + urlencode(params)):
                    raise AddonError("browser")
                code = callback.wait(self.cancel)
                self._check_cancel()
                response = self.http.request(metadata["token_endpoint"], {
                    "grant_type": "authorization_code", "client_id": self.config.client_id,
                    "code": code, "redirect_uri": callback.redirect_uri, "code_verifier": verifier,
                })
                self._accept(self._parse_tokens(response, initial=True), store)
        finally:
            self._lock.release()

    def access_token(self) -> str:
        """Worker-thread only; serializes refreshes and never persists access tokens."""
        with self._lock:
            with self._state_lock:
                self._check_cancel()
                if self._tokens is not None and self._tokens.expires_at > self.clock():
                    return self._tokens.access_token
            self._tokens = None
            store = self.store_factory(self.config, self.profile)
            refresh = store.read()
            if not refresh:
                raise AddonError("signed_out")
            metadata = self._metadata()
            self._check_cancel()
            try:
                response = self.http.request(metadata["token_endpoint"], {
                    "grant_type": "refresh_token", "client_id": self.config.client_id,
                    "refresh_token": refresh, "scope": " ".join(self.config.scopes),
                })
            except AddonError as error:
                if error.code == "denied":
                    store.delete()
                raise
            tokens = self._parse_tokens(response, initial=False)
            self._accept(tokens, store)
            return tokens.access_token

    def sign_out(self) -> None:
        with self._lock:
            self._tokens = None
            self.store_factory(self.config, self.profile).delete()

    def close(self) -> None:
        with self._state_lock:
            self.cancel.set()
            self._tokens = None
