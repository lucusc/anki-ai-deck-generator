from dataclasses import dataclass
from functools import lru_cache
import json
import logging
import os
from typing import Callable
from urllib.parse import urlsplit

import azure.functions as func
import jwt
from jwt import PyJWKClient


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str


class AuthenticationError(Exception):
    pass


class AuthenticationUnavailable(Exception):
    pass


def json_response(payload: dict[str, str], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


def _https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
    except ValueError:
        return False


@lru_cache(maxsize=4)
def _key_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, timeout=5, lifespan=300)


def authenticate(req: func.HttpRequest) -> Principal:
    authorization = req.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or len(parts[1]) > 8192:
        raise AuthenticationError("A valid bearer access token is required.")
    token = parts[1]
    issuer = os.environ.get("AUTH_ISSUER", "")
    audience = os.environ.get("AUTH_AUDIENCE", "")
    jwks_url = os.environ.get("AUTH_JWKS_URL", "")
    if not _https_url(issuer) or not audience.strip() or not _https_url(jwks_url):
        raise AuthenticationUnavailable("Configure the API identity provider.")

    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise AuthenticationError("Unsupported access token.")
        if not header["kid"].strip() or len(header["kid"]) > 128:
            raise AuthenticationError("Invalid signing key identifier.")
        key = _key_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except (jwt.PyJWKClientConnectionError, jwt.PyJWKError, jwt.PyJWKSetError) as exc:
        raise AuthenticationUnavailable("Identity provider signing keys unavailable.") from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise AuthenticationError("Invalid access token.") from exc

    subject = claims["sub"]
    if not isinstance(subject, str) or not subject.strip():
        raise AuthenticationError("Access token user identity is required.")
    return Principal(issuer=issuer, subject=subject)


def require_auth(
    handler: Callable[[func.HttpRequest, Principal], func.HttpResponse],
) -> Callable[[func.HttpRequest], func.HttpResponse]:
    def authenticated(req: func.HttpRequest) -> func.HttpResponse:
        try:
            principal = authenticate(req)
        except AuthenticationError:
            response = json_response({"error": "unauthorized"}, 401)
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        except AuthenticationUnavailable:
            logging.error("authentication_unavailable: configure or restore the API identity provider")
            return json_response({"error": "authentication_unavailable"}, 503)
        return handler(req, principal)

    # Expose only the bound HTTP argument to the Functions worker's signature check.
    authenticated.__name__ = handler.__name__
    return authenticated
