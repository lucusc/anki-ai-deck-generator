"""Native protected stores only; no plaintext, environment or file fallback."""

import ctypes
import hashlib
import json
import subprocess
import sys
from ctypes import wintypes
from typing import Protocol

from ..models.auth import AddonError, OAuthConfig

SERVICE = "anki-ai-deck-generator.oauth"


class CredentialStore(Protocol):
    def read(self) -> str | None: ...
    def write(self, token: str) -> None: ...
    def delete(self) -> None: ...


def credential_account(config: OAuthConfig, profile: str) -> str:
    identity = [config.issuer, config.client_id, config.audience, config.scopes, profile]
    return hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()


class MacKeychain:
    def __init__(self, account: str):
        self.account = account
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        ptr = ctypes.c_void_p
        self.cf.CFStringCreateWithCString.argtypes = [ptr, ctypes.c_char_p, ctypes.c_uint32]
        self.cf.CFStringCreateWithCString.restype = ptr
        self.cf.CFDictionaryCreateMutable.argtypes = [ptr, ctypes.c_long, ptr, ptr]
        self.cf.CFDictionaryCreateMutable.restype = ptr
        self.cf.CFDictionarySetValue.argtypes = [ptr, ptr, ptr]
        self.cf.CFDictionarySetValue.restype = None
        self.cf.CFDataCreate.argtypes = [ptr, ptr, ctypes.c_long]
        self.cf.CFDataCreate.restype = ptr
        self.cf.CFDataGetLength.argtypes = [ptr]
        self.cf.CFDataGetLength.restype = ctypes.c_long
        self.cf.CFDataGetBytePtr.argtypes = [ptr]
        self.cf.CFDataGetBytePtr.restype = ptr
        self.cf.CFRelease.argtypes = [ptr]
        self.cf.CFRelease.restype = None
        for name, args in (
            ("SecItemCopyMatching", [ptr, ctypes.POINTER(ptr)]),
            ("SecItemUpdate", [ptr, ptr]),
            ("SecItemAdd", [ptr, ptr]),
            ("SecItemDelete", [ptr]),
        ):
            func = getattr(self.sec, name)
            func.argtypes = args
            func.restype = ctypes.c_int32

    def _constant(self, name: str):
        return ctypes.c_void_p.in_dll(self.sec, name).value

    def _dictionary(self):
        keys = ctypes.addressof(ctypes.c_byte.in_dll(self.cf, "kCFTypeDictionaryKeyCallBacks"))
        values = ctypes.addressof(ctypes.c_byte.in_dll(self.cf, "kCFTypeDictionaryValueCallBacks"))
        result = self.cf.CFDictionaryCreateMutable(None, 0, keys, values)
        if not result:
            raise AddonError("credential")
        return result

    def _query(self):
        query = self._dictionary()
        try:
            self.cf.CFDictionarySetValue(query, self._constant("kSecClass"), self._constant("kSecClassGenericPassword"))
            for key, text in (("kSecAttrService", SERVICE), ("kSecAttrAccount", self.account)):
                value = self.cf.CFStringCreateWithCString(None, text.encode("utf-8"), 0x08000100)
                if not value:
                    raise AddonError("credential")
                try:
                    self.cf.CFDictionarySetValue(query, self._constant(key), value)
                finally:
                    self.cf.CFRelease(value)
            return query
        except Exception:
            self.cf.CFRelease(query)
            raise

    def read(self) -> str | None:
        query = self._query()
        result = ctypes.c_void_p()
        try:
            self.cf.CFDictionarySetValue(query, self._constant("kSecReturnData"), ctypes.c_void_p.in_dll(self.cf, "kCFBooleanTrue").value)
            self.cf.CFDictionarySetValue(query, self._constant("kSecMatchLimit"), self._constant("kSecMatchLimitOne"))
            status = self.sec.SecItemCopyMatching(query, ctypes.byref(result))
            if status == -25300:  # errSecItemNotFound
                return None
            if status != 0:
                raise AddonError("credential")
            return ctypes.string_at(self.cf.CFDataGetBytePtr(result), self.cf.CFDataGetLength(result)).decode("utf-8")
        finally:
            if result.value:
                self.cf.CFRelease(result)
            self.cf.CFRelease(query)

    def write(self, token: str) -> None:
        query = self._query()
        attrs = self._dictionary()
        encoded = token.encode("utf-8")
        data = self.cf.CFDataCreate(None, encoded, len(encoded))
        try:
            if not data:
                raise AddonError("credential")
            self.cf.CFDictionarySetValue(attrs, self._constant("kSecValueData"), data)
            status = self.sec.SecItemUpdate(query, attrs)
            if status == -25300:
                self.cf.CFDictionarySetValue(query, self._constant("kSecValueData"), data)
                status = self.sec.SecItemAdd(query, None)
            if status != 0:
                raise AddonError("credential")
        finally:
            if data:
                self.cf.CFRelease(data)
            self.cf.CFRelease(attrs)
            self.cf.CFRelease(query)

    def delete(self) -> None:
        query = self._query()
        try:
            if self.sec.SecItemDelete(query) not in (0, -25300):
                raise AddonError("credential")
        finally:
            self.cf.CFRelease(query)


class WindowsCredentialManager:
    def __init__(self, account: str):
        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        self.target = f"{SERVICE}/{account}"
        self.Credential = Credential
        self.api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        pointer = ctypes.POINTER(Credential)
        self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
        self.api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        for name in ("CredReadW", "CredWriteW", "CredDeleteW"):
            getattr(self.api, name).restype = wintypes.BOOL
        self.api.CredFree.argtypes = [ctypes.c_void_p]

    def read(self) -> str | None:
        result = ctypes.POINTER(self.Credential)()
        if not self.api.CredReadW(self.target, 1, 0, ctypes.byref(result)):
            if ctypes.get_last_error() == 1168:
                return None
            raise AddonError("credential")
        try:
            return ctypes.string_at(result.contents.CredentialBlob, result.contents.CredentialBlobSize).decode("utf-8")
        finally:
            self.api.CredFree(result)

    def write(self, token: str) -> None:
        encoded = token.encode("utf-8")
        if len(encoded) > 2560:
            raise AddonError("credential")
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        credential = self.Credential()
        credential.Type = 1
        credential.TargetName = self.target
        credential.UserName = "oauth-refresh"
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE, protected for this OS user.
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = blob
        if not self.api.CredWriteW(ctypes.byref(credential), 0):
            raise AddonError("credential")

    def delete(self) -> None:
        if not self.api.CredDeleteW(self.target, 1, 0) and ctypes.get_last_error() != 1168:
            raise AddonError("credential")


class LinuxSecretService:
    def __init__(self, account: str):
        self.account = account

    def _run(self, command: list[str], token: str | None = None):
        try:
            return subprocess.run(
                ["/usr/bin/secret-tool", *command, "service", SERVICE, "account", self.account],
                input=token.encode("utf-8") if token is not None else None,
                capture_output=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise AddonError("credential") from None

    def read(self) -> str | None:
        result = self._run(["lookup"])
        if result.returncode == 1 and not result.stderr:
            return None
        if result.returncode != 0:
            raise AddonError("credential")
        # secret-tool appends one newline; do not strip token characters.
        return result.stdout.removesuffix(b"\n").decode("utf-8")

    def write(self, token: str) -> None:
        if self._run(["store", "--label=Anki AI Deck Generator sign-in"], token).returncode != 0:
            raise AddonError("credential")

    def delete(self) -> None:
        result = self._run(["clear"])
        if result.returncode != 0 and not (result.returncode == 1 and not result.stderr):
            raise AddonError("credential")


def protected_store(config: OAuthConfig, profile: str) -> CredentialStore:
    account = credential_account(config, profile)
    try:
        if sys.platform == "darwin":
            return MacKeychain(account)
        if sys.platform == "win32":
            return WindowsCredentialManager(account)
        if sys.platform.startswith("linux"):
            return LinuxSecretService(account)
    except (OSError, AttributeError):
        raise AddonError("credential") from None
    raise AddonError("credential")
