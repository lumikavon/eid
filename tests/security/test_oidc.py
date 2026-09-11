import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import edw_api.auth as auth
from edw_api.auth import OidcVerifier, bearer_token
from edw_api.config import Settings
from edw_api.errors import ApiError


def token(private_key, *, kid="test", omit=(), **changes):
    now = int(time.time())
    claims = {
        "sub": "actor",
        "iss": "http://localhost:18080/realms/eid-local",
        "aud": "eid-web",
        "iat": now - 10,
        "nbf": now - 10,
        "exp": now + 600,
        "typ": "Bearer",
    }
    claims.update(changes)
    for claim in omit:
        claims.pop(claim)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def verifier(public_key):
    value = OidcVerifier(Settings())
    value.jwks = Mock()
    value.jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=public_key)
    return value


def test_jwks_client_uses_explicit_bounded_network_timeout(monkeypatch):
    observed = {}

    def client(uri, **kwargs):
        observed["uri"] = uri
        observed["kwargs"] = kwargs
        return Mock()

    monkeypatch.setattr(auth, "PyJWKClient", client)

    settings = Settings()
    OidcVerifier(settings)

    assert observed["uri"] == settings.oidc_jwks_url
    assert observed["kwargs"]["timeout"] == auth.OIDC_JWKS_TIMEOUT_SECONDS == 2.0


@pytest.mark.parametrize("scheme", ["bearer", "BEARER", "BeArEr"])
def test_bearer_scheme_is_case_insensitive(scheme):
    assert bearer_token(f"{scheme} valid-token") == "valid-token"


@pytest.mark.parametrize("authorization", [None, "", "Basic token", "Bearer", "Bearer   "])
def test_bearer_scheme_rejects_invalid_or_empty_credentials(authorization):
    with pytest.raises(ApiError) as caught:
        bearer_token(authorization)

    assert caught.value.code == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "other"},
        {"iss": "https://untrusted.invalid"},
        {"exp": 1},
        {"nbf": 4_000_000_000},
        {"sub": None},
    ],
)
def test_rejects_invalid_claims(changes):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ApiError) as caught:
        verifier(private.public_key()).verify(token(private, **changes))
    assert caught.value.code == "INVALID_TOKEN"


def test_valid_signature_and_claims():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert verifier(private.public_key()).verify(token(private)).subject == "actor"


def test_nbf_is_optional_but_other_claims_remain_verified():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        "sub": "actor",
        "iss": Settings().oidc_issuer,
        "aud": "eid-web",
        "iat": now - 10,
        "exp": now + 600,
        "typ": "Bearer",
    }
    encoded = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test"})
    assert verifier(private.public_key()).verify(encoded).subject == "actor"


@pytest.mark.parametrize(
    ("setting_name", "wrong_value"),
    [
        ("oidc_issuer", "https://wrong-issuer.invalid/realms/eid-local"),
        ("oidc_audience", "wrong-audience"),
    ],
)
def test_rejects_valid_token_when_runtime_oidc_contract_is_wrong(setting_name, wrong_value):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings()
    setattr(settings, setting_name, wrong_value)
    value = OidcVerifier(settings)
    value.jwks = Mock()
    value.jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=private.public_key())

    with pytest.raises(ApiError) as caught:
        value.verify(token(private))

    assert caught.value.code == "INVALID_TOKEN"


@pytest.mark.parametrize("claim", ["exp", "iat", "sub"])
def test_rejects_omitted_required_claims(claim):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(ApiError) as caught:
        verifier(private.public_key()).verify(token(private, omit=(claim,)))

    assert caught.value.code == "INVALID_TOKEN"


@pytest.mark.parametrize(
    ("typ", "omit"),
    [
        pytest.param("ID", (), id="id-token"),
        pytest.param("Refresh", (), id="refresh-token"),
        pytest.param(None, ("typ",), id="missing-token-type"),
    ],
)
def test_rejects_non_access_token_types(typ, omit):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(ApiError) as caught:
        verifier(private.public_key()).verify(token(private, typ=typ, omit=omit))

    assert caught.value.code == "INVALID_TOKEN"
    assert caught.value.status_code == 401


def test_wrong_signature():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ApiError):
        verifier(other.public_key()).verify(token(private))


def test_real_jwks_client_refreshes_rotated_key_and_rejects_wrong_signature():
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def public_jwk(private_key, kid):
        value = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
        value.update({"kid": kid, "use": "sig", "alg": "RS256"})
        return value

    state = {"keys": [public_jwk(old_key, "old-kid")], "requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"] += 1
            body = json.dumps({"keys": state["keys"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings = Settings(oidc_jwks_url=f"http://127.0.0.1:{server.server_port}/jwks")
        value = OidcVerifier(settings)
        assert value.verify(token(old_key, kid="old-kid")).subject == "actor"
        first_request_count = state["requests"]

        state["keys"] = [public_jwk(new_key, "new-kid")]
        assert value.verify(token(new_key, kid="new-kid")).subject == "actor"
        assert state["requests"] > first_request_count

        with pytest.raises(ApiError) as caught:
            value.verify(token(old_key, kid="new-kid"))
        assert caught.value.code == "INVALID_TOKEN"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
