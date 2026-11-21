import inspect
import json
from pathlib import Path
import time
from types import SimpleNamespace

import azure.functions as func
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

import auth
from function_app import app, ProcessingUnavailable


@pytest.fixture(scope="module")
def functions():
    return {function.get_function_name(): function for function in app.get_functions()}


def request(headers=None, body=b"") -> func.HttpRequest:
    return func.HttpRequest(
        method="GET", url="http://localhost/api/v1/auth-check",
        headers=headers or {}, body=body,
    )


@pytest.fixture
def signing(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for name, value in {
        "AUTH_ISSUER": "https://issuer.example.test/",
        "AUTH_AUDIENCE": "api://synthetic-api",
        "AUTH_JWKS_URL": "https://issuer.example.test/keys",
    }.items():
        monkeypatch.setenv(name, value)
    key_client = jwt.PyJWKClient("https://issuer.example.test/keys")
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "synthetic-key", "alg": "RS256", "use": "sig"})
    monkeypatch.setattr(key_client, "fetch_data", lambda: {"keys": [public_jwk]})
    monkeypatch.setattr(auth, "_key_client", lambda url: key_client)

    def sign(changes=None, omit=(), key=None, algorithm="RS256"):
        claims = {
            "iss": "https://issuer.example.test/",
            "aud": "api://synthetic-api",
            "sub": "synthetic-user",
            "iat": int(time.time()) - 1,
            "nbf": int(time.time()) - 1,
            "exp": int(time.time()) + 60,
        }
        claims.update(changes or {})
        for name in omit:
            del claims[name]
        return jwt.encode(
            claims, key or private_key, algorithm=algorithm, headers={"kid": "synthetic-key"}
        )

    return sign


def test_health_is_content_free_and_independent_of_auth(functions, monkeypatch):
    monkeypatch.delenv("AUTH_ISSUER", raising=False)
    response = functions["health"].get_user_function()(
        request({"Authorization": "secret", "X-MS-CLIENT-PRINCIPAL": "private"}, b"private")
    )
    assert response.status_code == 200
    assert json.loads(response.get_body()) == {"status": "ok"}
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("headers", [
    {}, {"X-MS-CLIENT-PRINCIPAL-ID": "forged-user"},
    {"X-MS-CLIENT-PRINCIPAL": "forged"}, {"Authorization": "Basic forged"},
    {"Authorization": "Bearer"}, {"Authorization": "Bearer a b"},
    {"Authorization": "Bearer " + "x" * 8193},
])
def test_protected_route_rejects_missing_auth_and_forged_headers(functions, headers):
    response = functions["auth_check"].get_user_function()(request(headers))
    assert response.status_code == 401
    assert json.loads(response.get_body()) == {"error": "unauthorized"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_signed_access_token_reaches_protected_handler(functions, signing):
    token = signing()
    req = request({"Authorization": f"Bearer {token}"})
    assert auth.authenticate(req) == auth.Principal(
        issuer="https://issuer.example.test/", subject="synthetic-user",
    )
    response = functions["auth_check"].get_user_function()(req)
    assert response.status_code == 200
    assert json.loads(response.get_body()) == {"status": "authenticated"}
    assert b"synthetic-user" not in response.get_body()


@pytest.mark.parametrize("changes", [
    {"iss": "https://attacker.example.test/"},
    {"aud": "public-client-not-api"},
    {"exp": int(time.time()) - 60},
    {"nbf": int(time.time()) + 3600},
    {"iat": int(time.time()) + 3600},
    {"sub": ""}, {"sub": "  "}, {"sub": 123},
])
def test_invalid_claims_fail_closed(functions, signing, changes):
    response = functions["auth_check"].get_user_function()(
        request({"Authorization": f"Bearer {signing(changes)}"})
    )
    assert response.status_code == 401
    assert json.loads(response.get_body()) == {"error": "unauthorized"}


@pytest.mark.parametrize("claim", ["exp", "iat", "iss", "aud", "sub"])
def test_required_claims_fail_closed(functions, signing, claim):
    response = functions["auth_check"].get_user_function()(
        request({"Authorization": f"Bearer {signing(omit=(claim,))}"})
    )
    assert response.status_code == 401


def test_wrong_signature_and_symmetric_algorithm_rejected(functions, signing):
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in (
        signing(key=attacker_key),
        signing(key="synthetic-test-key-not-a-credential", algorithm="HS256"),
        "not-a-token",
    ):
        response = functions["auth_check"].get_user_function()(
            request({"Authorization": f"Bearer {token}"})
        )
        assert response.status_code == 401


def test_unknown_signing_key_fails_closed(functions, signing):
    token = signing()
    header, payload, signature = token.split(".")
    unknown_header = jwt.utils.base64url_encode(
        json.dumps({"alg": "RS256", "kid": "unknown"}).encode()
    ).decode()
    response = functions["auth_check"].get_user_function()(
        request({"Authorization": f"Bearer {unknown_header}.{payload}.{signature}"})
    )
    assert response.status_code == 401
    assert json.loads(response.get_body()) == {"error": "unauthorized"}


@pytest.mark.parametrize("name,value", [
    ("AUTH_ISSUER", ""), ("AUTH_AUDIENCE", ""), ("AUTH_JWKS_URL", ""),
    ("AUTH_JWKS_URL", "http://issuer.example.test/keys"),
    ("AUTH_JWKS_URL", "https://user:password@issuer.example.test/keys"),
])
def test_unconfigured_or_insecure_auth_fails_closed(functions, signing, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    response = functions["auth_check"].get_user_function()(
        request({"Authorization": f"Bearer {signing()}"})
    )
    assert response.status_code == 503
    assert json.loads(response.get_body()) == {"error": "authentication_unavailable"}


def test_jwks_failure_is_explicit_without_content(functions, signing, monkeypatch, caplog):
    def unavailable(token):
        raise jwt.PyJWKClientConnectionError("sensitive provider detail")

    monkeypatch.setattr(
        auth, "_key_client",
        lambda url: SimpleNamespace(get_signing_key_from_jwt=unavailable),
    )
    response = functions["auth_check"].get_user_function()(
        request({"Authorization": f"Bearer {signing()}"})
    )
    assert response.status_code == 503
    assert json.loads(response.get_body()) == {"error": "authentication_unavailable"}
    assert "authentication_unavailable" in caplog.text
    assert "sensitive provider detail" not in caplog.text


def test_empty_provider_keyset_is_unavailable(functions, signing, monkeypatch):
    key_client = jwt.PyJWKClient("https://issuer.example.test/keys")
    monkeypatch.setattr(key_client, "fetch_data", lambda: {"keys": []})
    monkeypatch.setattr(auth, "_key_client", lambda url: key_client)
    response = functions["auth_check"].get_user_function()(
        request({"Authorization": f"Bearer {signing()}"})
    )
    assert response.status_code == 503
    assert json.loads(response.get_body()) == {"error": "authentication_unavailable"}


def test_worker_never_acknowledges_unsupported_processing(functions, caplog):
    class UnreadableMessage:
        def get_body(self):
            pytest.fail("Foundation must not read or log document/job payloads")

    worker = functions["generation_worker"].get_user_function()
    for _ in range(2):
        with pytest.raises(ProcessingUnavailable, match="processing_unavailable.*issue #8"):
            worker(UnreadableMessage())
    assert "processing_unavailable" in caplog.text


def test_host_discovers_only_scoped_routes_and_queue_binding(functions):
    routes = {
        name: json.loads(function.get_function_json())["bindings"]
        for name, function in functions.items()
    }
    assert set(routes) == {"health", "auth_check", "generation_worker"}
    for name, path in [("health", "health"), ("auth_check", "v1/auth-check")]:
        trigger = next(binding for binding in routes[name] if binding["type"] == "httpTrigger")
        assert trigger["route"] == path
        assert trigger["methods"] == ["GET"]
        assert trigger["authLevel"].lower() == "anonymous"
        handler_parameters = inspect.signature(functions[name].get_user_function()).parameters
        assert list(handler_parameters) == ["req"]
        assert handler_parameters["req"].annotation is func.HttpRequest
    trigger = routes["generation_worker"][0]
    assert trigger["type"] == "queueTrigger"
    assert trigger["queueName"] == "generation-jobs"
    assert trigger["connection"] == "AzureWebJobsStorage"


def test_host_limits_queue_retry_and_execution():
    host = json.loads((Path(__file__).parents[1] / "host.json").read_text())
    assert host["functionTimeout"] == "00:05:00"
    assert host["extensions"]["queues"]["maxDequeueCount"] == 3
    assert host["extensions"]["queues"]["visibilityTimeout"] == "00:01:00"
    assert host["extensions"]["queues"]["messageEncoding"] == "base64"
