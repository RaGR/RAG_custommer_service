from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from contextlib import nullcontext

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.routers import dm
from app.security import auth, hmac_sig, rate_limit
from app.security.audit import init_security_tables


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    test_db = tmp_path / "test.sqlite"
    monkeypatch.setattr(settings, "db_path", str(test_db))
    monkeypatch.setattr(dm, "DB_PATH", str(test_db))

    class DummyVector:
        def search(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(dm, "VEC", DummyVector())
    monkeypatch.setattr(dm, "search_fts", lambda _conn, _q, k=None: [])
    monkeypatch.setattr(dm, "connect", lambda _path: nullcontext(None))

    async def fake_llm(prompt: str) -> str:
        return "ok"

    monkeypatch.setattr(dm, "ask_llm", fake_llm)

    auth._invalidate_api_key_cache()
    rate_limit._BUCKETS.clear()
    rate_limit.ratelimit_block_total = 0
    rate_limit._TENANT_CACHE.clear()
    hmac_sig._NONCE_CACHE.clear()

    settings.require_api_key = True
    settings.api_key = ""
    settings.hmac_required = False
    settings.hmac_window_sec = 300
    settings.auth_mode = "api_key"
    settings.max_request_body_bytes = 65_536
    settings.rl_bucket_size = 2
    settings.rl_refill_per_sec = 0.0
    rate_limit._BUCKETS.clear()

    init_security_tables()
    dm._feedback_table_init()

    api = TestClient(app)
    yield api
    api.close()


def issue_key(role: auth.Role = auth.Role.CLIENT, name: str = "test"):
    return auth.create_api_key(name, role)


def simulate_payload(text: str = "در مورد کرم سوال دارم"):
    return {"sender_id": "u1", "message_id": "m1", "text": text}


def build_hmac_headers(api_key: str, method: str, path: str, body_bytes: bytes):
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    digest = hashlib.sha256(body_bytes).hexdigest()
    canonical = f"{ts}.{nonce}.{method}.{path}.{digest}"
    signature = hmac.new(api_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Timestamp": ts,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


def stash_settings(*names):
    return {name: getattr(settings, name) for name in names}


def restore_settings(snapshot):
    for name, value in snapshot.items():
        setattr(settings, name, value)


def build_token(roles, **claims):
    payload = {
        "sub": claims.get("sub", "user-1"),
        "roles": roles,
        "iss": settings.jwt_iss,
        "aud": settings.jwt_aud,
        "exp": claims.get("exp", int(time.time()) + 600),
    }
    for key, value in claims.items():
        payload[key] = value
    return jwt.encode(
        payload,
        settings.jwt_signing_key,
        algorithm="HS256",
        headers={"kid": settings.jwt_kid or "test"},
    )


def test_simulate_requires_api_key(client: TestClient):
    response = client.post("/simulate_dm", json=simulate_payload())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "credentials_missing"


def test_simulate_accepts_valid_api_key(client: TestClient):
    key, _ = issue_key()
    response = client.post(
        "/simulate_dm",
        json=simulate_payload(),
        headers={"X-API-Key": key},
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "ok"


def test_disabled_key_rejected(client: TestClient):
    key, record = issue_key()
    auth.disable_api_key(record.id)
    response = client.post(
        "/simulate_dm",
        json=simulate_payload(),
        headers={"X-API-Key": key},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_metrics_requires_admin_role(client: TestClient):
    key, _ = issue_key(role=auth.Role.CLIENT)
    response = client.get("/metrics", headers={"X-API-Key": key})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


def test_metrics_with_admin_key(client: TestClient):
    key, _ = issue_key(role=auth.Role.ADMIN)
    response = client.get("/metrics", headers={"X-API-Key": key})
    assert response.status_code == 200
    assert "requests_total" in response.text


def test_rate_limit_exceeded(client: TestClient):
    settings.rl_bucket_size = 2
    settings.rl_refill_per_sec = 0.0
    rate_limit._BUCKETS.clear()
    rate_limit._TENANT_CACHE.clear()
    key, _ = issue_key()
    headers = {"X-API-Key": key}
    for _ in range(2):
        ok_response = client.post("/simulate_dm", json=simulate_payload(), headers=headers)
        assert ok_response.status_code == 200

    response = client.post("/simulate_dm", json=simulate_payload(), headers=headers)
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "rate_limited"
    assert "Retry-After" in response.headers


def test_body_size_limit_enforced(client: TestClient):
    key, _ = issue_key()
    original = settings.max_request_body_bytes
    settings.max_request_body_bytes = 32
    try:
        response = client.post(
            "/simulate_dm",
            json=simulate_payload("x" * 200),
            headers={"X-API-Key": key},
        )
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "payload_too_large"
    finally:
        settings.max_request_body_bytes = original


def test_security_headers_present(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"].startswith("default-src")


def test_cors_allows_known_origin(client: TestClient):
    response = client.options(
        "/simulate_dm",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"


def test_cors_blocks_unlisted_origin(client: TestClient):
    response = client.options(
        "/simulate_dm",
        headers={
            "Origin": "http://evil.test",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_hmac_signature_enforced(client: TestClient):
    settings.hmac_required = True
    key, _ = issue_key()
    payload = simulate_payload()
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": key,
    }
    headers.update(build_hmac_headers(key, "POST", "/simulate_dm", body))

    ok_resp = client.post("/simulate_dm", data=body, headers=headers)
    assert ok_resp.status_code == 200

    replay_resp = client.post("/simulate_dm", data=body, headers=headers)
    assert replay_resp.status_code == 401
    assert replay_resp.json()["detail"]["code"] == "hmac_replay"

    old_ts = str(int(time.time()) - (settings.hmac_window_sec + 10))
    nonce = uuid.uuid4().hex
    digest = hashlib.sha256(body).hexdigest()
    stale_signature = hmac.new(
        key.encode("utf-8"),
        f"{old_ts}.{nonce}.POST./simulate_dm.{digest}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    stale_headers = {
        "Content-Type": "application/json",
        "X-API-Key": key,
        "X-Timestamp": old_ts,
        "X-Nonce": nonce,
        "X-Signature": stale_signature,
    }
    stale_resp = client.post("/simulate_dm", data=body, headers=stale_headers)
    assert stale_resp.status_code == 401
    assert stale_resp.json()["detail"]["code"] == "hmac_window_violation"
    settings.hmac_required = False


def test_jwt_allows_client_role(client: TestClient):
    snapshot = stash_settings(
        "require_api_key",
        "auth_mode",
        "jwt_signing_key",
        "jwt_public_key",
        "jwt_kid",
        "jwt_iss",
        "jwt_aud",
    )
    settings.require_api_key = False
    settings.auth_mode = "jwt"
    settings.jwt_signing_key = "secret-signing-key"
    settings.jwt_kid = "kid1"
    settings.jwt_iss = "test-issuer"
    settings.jwt_aud = "test-aud"

    token = build_token(["CLIENT"])
    response = client.post(
        "/simulate_dm",
        json=simulate_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    restore_settings(snapshot)
    assert response.status_code == 200


def test_jwt_expired_token_denied(client: TestClient):
    snapshot = stash_settings(
        "require_api_key",
        "auth_mode",
        "jwt_signing_key",
        "jwt_public_key",
        "jwt_kid",
        "jwt_iss",
        "jwt_aud",
    )
    settings.require_api_key = False
    settings.auth_mode = "jwt"
    settings.jwt_signing_key = "secret"
    settings.jwt_kid = "kid1"
    settings.jwt_iss = "issuer"
    settings.jwt_aud = "aud"

    token = build_token(["CLIENT"], exp=int(time.time()) - 600)
    response = client.post(
        "/simulate_dm",
        json=simulate_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    restore_settings(snapshot)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "token_expired"


def test_jwt_wrong_audience(client: TestClient):
    snapshot = stash_settings(
        "require_api_key",
        "auth_mode",
        "jwt_signing_key",
        "jwt_public_key",
        "jwt_kid",
        "jwt_iss",
        "jwt_aud",
    )
    settings.require_api_key = False
    settings.auth_mode = "jwt"
    settings.jwt_signing_key = "secret"
    settings.jwt_kid = "kid1"
    settings.jwt_iss = "issuer"
    settings.jwt_aud = "aud"

    token = build_token(["CLIENT"], aud="other")
    response = client.post(
        "/simulate_dm",
        json=simulate_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    restore_settings(snapshot)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_audience"


def test_jwt_role_mismatch_for_metrics(client: TestClient):
    snapshot = stash_settings(
        "require_api_key",
        "auth_mode",
        "jwt_signing_key",
        "jwt_public_key",
        "jwt_kid",
        "jwt_iss",
        "jwt_aud",
    )
    settings.require_api_key = False
    settings.auth_mode = "jwt"
    settings.jwt_signing_key = "secret"
    settings.jwt_kid = "kid1"
    settings.jwt_iss = "issuer"
    settings.jwt_aud = "aud"

    token = build_token(["CLIENT"])
    response = client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    restore_settings(snapshot)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_role"


def test_security_selftest_requires_admin(client: TestClient):
    key, _ = issue_key(role=auth.Role.ADMIN)
    response = client.get("/security/selftest", headers={"X-API-Key": key})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "security_tables" in data["checks"]


def test_security_selftest_forbidden_without_admin(client: TestClient):
    key, _ = issue_key(role=auth.Role.CLIENT)
    response = client.get("/security/selftest", headers={"X-API-Key": key})
    assert response.status_code == 403


def test_logs_do_not_include_raw_api_key(client: TestClient, caplog: pytest.LogCaptureFixture):
    key, _ = issue_key()
    with caplog.at_level("INFO"):
        response = client.post(
            "/simulate_dm",
            json=simulate_payload(),
            headers={"X-API-Key": key},
        )
        assert response.status_code == 200
    for record in caplog.records:
        message = record.getMessage()
        assert key not in message
        for value in record.__dict__.values():
            if isinstance(value, str):
                assert key not in value
