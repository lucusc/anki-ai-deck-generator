import json
import socket
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..models.auth import AddonError, https_url

MAX_RESPONSE_BYTES = 128 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward authorization codes or refresh tokens to a redirect.
        return None


class JsonHttp:
    def __init__(self):
        self._opener = build_opener(NoRedirect())

    def request(self, url: str, form: dict[str, str] | None = None) -> dict:
        https_url(url)
        body = urlencode(form).encode("ascii") if form is not None else None
        request = Request(url, data=body, headers={"Accept": "application/json"})
        if body is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self._opener.open(request, timeout=15) as response:
                if response.status != 200:
                    raise AddonError("response")
                data = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            error.close()
            raise AddonError("denied" if error.code in (400, 401, 403) else "network") from None
        except (URLError, OSError, socket.timeout, HTTPException):
            raise AddonError("network") from None
        if len(data) > MAX_RESPONSE_BYTES:
            raise AddonError("response")
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise AddonError("response") from None
        if not isinstance(result, dict):
            raise AddonError("response")
        return result
