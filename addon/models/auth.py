from dataclasses import dataclass, field
from urllib.parse import urlsplit


class AddonError(Exception):
    """Only fixed, content-free messages may cross the UI/log boundary."""

    MESSAGES = {
        "configuration": "Configure issuer, public client ID, API audience and API scope in Tools > Add-ons > Config. See addon-development.md.",
        "provider": "The identity provider returned incompatible metadata. Check the configured issuer and PKCE/loopback public-client registration.",
        "network": "Sign-in could not reach the identity provider. Check your connection and try again.",
        "response": "The identity provider returned an invalid or oversized response. Check its OAuth configuration.",
        "denied": "Sign-in was denied or the credential expired. Sign in again in your browser.",
        "timeout": "Browser sign-in timed out. Try again and complete sign-in within three minutes.",
        "cancelled": "Sign-in cancelled. No new session was accepted.",
        "browser": "The system browser could not be opened. Set a default browser and try again.",
        "listener": "The local sign-in callback could not start. Allow Anki to listen on the loopback interface and retry.",
        "credential": "The protected OS credential store is unavailable or locked. Unlock Keychain, Windows Credential Manager or Linux Secret Service and retry. No file fallback is used.",
        "signed_out": "No saved sign-in is available. Use Sign in with browser.",
        "busy": "An authentication operation is already running. Wait or cancel it.",
        "unsupported": "This add-on targets Anki 25.09 and 26.09.4 (Qt6). Install a target version; see addon-development.md for release verification limits.",
        "startup": "Anki AI Deck Generator could not start. Reinstall the add-on and check its documented Anki version targets.",
        "internal": "Anki AI Deck Generator encountered an unexpected error. Retry, then report the content-free error code internal.",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self.MESSAGES[code])


def https_url(value: object) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 0x20 for c in value):
        raise AddonError("configuration")
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise AddonError("configuration") from None
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.fragment
        or port == 0
    ):
        raise AddonError("configuration")
    return value


@dataclass(frozen=True)
class OAuthConfig:
    issuer: str
    client_id: str
    audience: str
    scopes: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: object) -> "OAuthConfig":
        if not isinstance(raw, dict) or set(raw) != {"issuer", "client_id", "audience", "scopes"}:
            raise AddonError("configuration")
        issuer = https_url(raw["issuer"])
        if urlsplit(issuer).query:
            raise AddonError("configuration")
        for key in ("client_id", "audience"):
            value = raw[key]
            if not isinstance(value, str) or not value or any(c.isspace() for c in value):
                raise AddonError("configuration")
        scopes = raw["scopes"]
        if (
            not isinstance(scopes, list)
            or not scopes
            or any(not isinstance(s, str) or not s or any(c.isspace() for c in s) for s in scopes)
            or len(scopes) != len(set(scopes))
            or "offline_access" not in scopes
            or not set(scopes) - {"openid", "offline_access", "profile", "email"}
        ):
            raise AddonError("configuration")
        return cls(issuer, raw["client_id"], raw["audience"], tuple(scopes))


@dataclass(frozen=True, repr=False)
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_at: float

    def __repr__(self) -> str:
        return "TokenSet(<redacted>)"
