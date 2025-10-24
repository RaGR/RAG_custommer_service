"""Authentication, authorization, and API key management utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional, Sequence, Set

import jwt
from fastapi import HTTPException, Request

from app.core.config import settings
from app.security.audit import audit_event, init_security_tables, security_db

try:
    from argon2 import PasswordHasher  # type: ignore
    from argon2.exceptions import VerifyMismatchError  # type: ignore

    _HASHER = PasswordHasher(time_cost=2, memory_cost=51200, parallelism=2, salt_len=16)
    _HASH_LIB = "argon2"
except ImportError:  # pragma: no cover - fall back when argon2 unavailable

    class VerifyMismatchError(Exception):
        """Raised when provided secret does not match stored hash."""

    class PasswordHasher:  # type: ignore
        """Fallback PBKDF2-based hasher when argon2 is unavailable."""

        def __init__(
            self,
            iterations: int = 480_000,
            hash_name: str = "sha256",
            salt_len: int = 16,
        ) -> None:
            self.iterations = iterations
            self.hash_name = hash_name
            self.salt_len = salt_len

        def hash(self, password: str) -> str:
            salt = secrets.token_bytes(self.salt_len)
            dk = hashlib.pbkdf2_hmac(self.hash_name, password.encode("utf-8"), salt, self.iterations)
            payload = "$".join(
                [
                    "pbkdf2",
                    self.hash_name,
                    str(self.iterations),
                    base64.b64encode(salt).decode("ascii"),
                    base64.b64encode(dk).decode("ascii"),
                ]
            )
            return payload

        def verify(self, hashed: str, password: str) -> bool:
            try:
                prefix, hash_name, iter_s, salt_b64, digest_b64 = hashed.split("$")
                if prefix != "pbkdf2":
                    raise ValueError
                iterations = int(iter_s)
                salt = base64.b64decode(salt_b64)
                digest = base64.b64decode(digest_b64)
            except Exception as exc:
                raise VerifyMismatchError from exc
            candidate = hashlib.pbkdf2_hmac(hash_name, password.encode("utf-8"), salt, iterations)
            if not hmac.compare_digest(candidate, digest):
                raise VerifyMismatchError
            return True

        def check_needs_rehash(self, hashed: str) -> bool:
            return False

    _HASHER = PasswordHasher()
    _HASH_LIB = "pbkdf2"

_LOGGER = logging.getLogger("app.security")
if _HASH_LIB != "argon2":  # pragma: no cover - informational
    _LOGGER.warning("argon2 library not available; falling back to PBKDF2 hashing.")


class Role(str, Enum):
    """Supported RBAC roles."""

    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    CLIENT = "CLIENT"


class AuthType(str, Enum):
    """Authentication credential type."""

    API_KEY = "api_key"
    JWT = "jwt"


@dataclass(slots=True)
class ApiKeyRecord:
    """Persistent API key metadata loaded from SQLite."""

    id: int
    name: str
    key_hash: str
    role: Role
    enabled: bool
    created_at: str
    last_used_at: Optional[str]


@dataclass(slots=True)
class SecurityContext:
    """Authenticated request principal."""

    auth_type: AuthType
    subject: str
    roles: Set[Role]
    scopes: Set[str]
    api_key_id: Optional[int] = None
    api_key_name: Optional[str] = None
    jwt_id: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    claims: Optional[dict[str, Any]] = None
    raw_api_key: Optional[str] = field(default=None, repr=False)

    def has_any_role(self, allowed: Iterable[Role]) -> bool:
        allowed_set = set(allowed)
        return bool(self.roles.intersection(allowed_set))

    def ensure_roles(self, allowed: Iterable[Role]) -> None:
        if not self.has_any_role(allowed):
            raise forbidden("insufficient_role", "User lacks required role")

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


_API_KEY_CACHE_TTL = 60.0
_CACHE_TIMESTAMP = 0.0
_API_KEY_CACHE: list[ApiKeyRecord] = []

_JWT_LEEWAY = 120  # seconds


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "detail": message})


def unauthorized(code: str, message: str) -> HTTPException:
    return _http_error(401, code, message)


def forbidden(code: str, message: str) -> HTTPException:
    return _http_error(403, code, message)


def _invalidate_api_key_cache() -> None:
    global _CACHE_TIMESTAMP, _API_KEY_CACHE
    _CACHE_TIMESTAMP = 0.0
    _API_KEY_CACHE = []


def _load_api_keys() -> list[ApiKeyRecord]:
    global _CACHE_TIMESTAMP, _API_KEY_CACHE
    now = time.monotonic()
    if now - _CACHE_TIMESTAMP < _API_KEY_CACHE_TTL and _API_KEY_CACHE:
        return _API_KEY_CACHE

    init_security_tables()
    with security_db(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT id, name, key_hash, role, enabled, created_at, last_used_at
            FROM api_keys
            """
        ).fetchall()

    records: list[ApiKeyRecord] = []
    for row in rows:
        try:
            role = Role(row["role"])
        except ValueError:
            # Skip unknown roles to avoid privilege escalation.
            continue
        records.append(
            ApiKeyRecord(
                id=row["id"],
                name=row["name"],
                key_hash=row["key_hash"],
                role=role,
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
                last_used_at=row["last_used_at"],
            )
        )

    _CACHE_TIMESTAMP = now
    _API_KEY_CACHE = records
    return records


def _update_key_hash(key_id: int, raw_key: str) -> None:
    new_hash = _HASHER.hash(raw_key)
    with security_db() as conn:
        conn.execute(
            "UPDATE api_keys SET key_hash = ?, last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_hash, key_id),
        )
    _invalidate_api_key_cache()


def _touch_last_used(key_id: int) -> None:
    with security_db() as conn:
        conn.execute(
            "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
            (key_id,),
        )


def _authenticate_api_key(raw_key: str) -> Optional[SecurityContext]:
    if not raw_key:
        return None

    records = _load_api_keys()
    for record in records:
        if not record.enabled:
            continue
        try:
            if _HASHER.verify(record.key_hash, raw_key):
                if _HASHER.check_needs_rehash(record.key_hash):
                    _update_key_hash(record.id, raw_key)
                _touch_last_used(record.id)
                return SecurityContext(
                    auth_type=AuthType.API_KEY,
                    subject=f"key:{record.id}",
                    roles={record.role},
                    scopes=set(),
                    api_key_id=record.id,
                    api_key_name=record.name,
                    raw_api_key=raw_key,
                )
        except VerifyMismatchError:
            continue

    # Static fallback for backwards compatibility
    if settings.api_key:
        if hmac.compare_digest(settings.api_key, raw_key):
            return SecurityContext(
                auth_type=AuthType.API_KEY,
                subject="key:static",
                roles={Role.ADMIN},
                scopes=set(),
                api_key_id=None,
                api_key_name="static_env_key",
                raw_api_key=raw_key,
            )

    return None


def _jwt_key_registry() -> dict[str, str]:
    """Return dict of kid -> key material."""
    registry: dict[str, str] = {}
    if settings.jwt_signing_key:
        registry[settings.jwt_kid] = settings.jwt_signing_key
    if settings.jwt_public_key:
        registry[settings.jwt_kid] = settings.jwt_public_key
    return registry


def _authenticate_jwt(token: str) -> Optional[SecurityContext]:
    token = token.strip()
    if not token:
        return None
    registry = _jwt_key_registry()
    if not registry:
        return None
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise unauthorized("invalid_token", "Malformed JWT token")

    kid = header.get("kid", settings.jwt_kid)
    key = registry.get(kid)
    if not key:
        raise unauthorized("unknown_kid", "JWT key id not recognized")

    algorithm = "RS256" if "-----BEGIN" in key else "HS256"

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=settings.jwt_aud,
            issuer=settings.jwt_iss,
            leeway=_JWT_LEEWAY,
        )
    except jwt.ExpiredSignatureError:
        raise unauthorized("token_expired", "JWT token expired")
    except jwt.InvalidAudienceError:
        raise unauthorized("invalid_audience", "JWT audience mismatch")
    except jwt.InvalidIssuerError:
        raise unauthorized("invalid_issuer", "JWT issuer mismatch")
    except jwt.PyJWTError as exc:
        raise unauthorized("invalid_token", f"JWT validation failed: {exc}") from exc

    subject = str(payload.get("sub") or "")
    if not subject:
        raise unauthorized("invalid_token", "JWT missing subject")

    raw_roles = payload.get("roles") or []
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    roles: set[Role] = set()
    for role_str in raw_roles:
        try:
            roles.add(Role(role_str))
        except ValueError:
            continue
    if not roles:
        raise forbidden("insufficient_role", "JWT lacks required role claims")

    scopes_field = payload.get("scope") or payload.get("scopes") or []
    if isinstance(scopes_field, str):
        scopes = set(scope for scope in scopes_field.split() if scope)
    else:
        scopes = set(scope for scope in scopes_field if isinstance(scope, str))

    exp_ts = payload.get("exp")
    exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if isinstance(exp_ts, (int, float)) else None

    return SecurityContext(
        auth_type=AuthType.JWT,
        subject=f"user:{subject}",
        roles=roles,
        scopes=scopes,
        jwt_id=payload.get("jti"),
        token_expires_at=exp_dt,
        claims=payload,
    )


async def authenticate_request(request: Request) -> Optional[SecurityContext]:
    """Authenticate request using API key or JWT if provided."""
    cached = getattr(request.state, "security_context", None)
    if isinstance(cached, SecurityContext):
        return cached

    raw_key = request.headers.get("X-API-Key", "")
    bearer_header = request.headers.get("Authorization", "")

    # Prefer API key when present
    if raw_key:
        context = _authenticate_api_key(raw_key)
        if context:
            request.state.security_context = context  # type: ignore[attr-defined]
            return context

    if bearer_header.startswith("Bearer "):
        token = bearer_header.split(" ", 1)[1].strip()
        context = _authenticate_jwt(token)
        if context:
            request.state.security_context = context  # type: ignore[attr-defined]
            return context

    return None


async def require_identity(request: Request, allow_anonymous: bool = False) -> Optional[SecurityContext]:
    """Return security context or raise when authentication is required."""
    context = await authenticate_request(request)
    raw_key = request.headers.get("X-API-Key")
    bearer = request.headers.get("Authorization")

    if context:
        return context

    provided_credentials = bool(raw_key or bearer)
    if allow_anonymous and not provided_credentials:
        return None

    if settings.require_api_key and not provided_credentials:
        raise unauthorized("credentials_missing", "Authentication credentials are required")

    if provided_credentials:
        raise unauthorized("invalid_credentials", "Invalid authentication credentials")

    if allow_anonymous:
        return None

    raise unauthorized("unauthorized", "Authentication required")


async def require_roles(request: Request, roles: Sequence[Role]) -> SecurityContext:
    """Authenticate request and enforce allowed roles."""
    context = await require_identity(request)
    context.ensure_roles(roles)
    return context


def hash_api_key(raw_key: str) -> str:
    """Create a hashed representation of an API key."""
    return _HASHER.hash(raw_key)


def create_api_key(name: str, role: Role) -> tuple[str, ApiKeyRecord]:
    """Create and persist a new API key, returning the plaintext for one-time display."""
    init_security_tables()
    raw_key = secrets.token_urlsafe(40)
    key_hash = hash_api_key(raw_key)
    with security_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO api_keys(name, key_hash, role, enabled)
            VALUES(?,?,?,1)
            """,
            (name, key_hash, role.value),
        )
        key_id = cur.lastrowid
        row = conn.execute(
            """
            SELECT id, name, key_hash, role, enabled, created_at, last_used_at
            FROM api_keys
            WHERE id = ?
            """,
            (key_id,),
        ).fetchone()

    _invalidate_api_key_cache()
    record = ApiKeyRecord(
        id=row["id"],
        name=row["name"],
        key_hash=row["key_hash"],
        role=Role(row["role"]),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )
    audit_event(actor="system", action="api_key_create", path="/admin/keys", status="success", note=name)
    return raw_key, record


def disable_api_key(key_id: int) -> None:
    """Disable (soft-delete) an API key."""
    with security_db() as conn:
        conn.execute("UPDATE api_keys SET enabled = 0 WHERE id = ?", (key_id,))
    _invalidate_api_key_cache()
    audit_event(actor="system", action="api_key_disable", path="/admin/keys", status="success", note=str(key_id))


def enable_api_key(key_id: int) -> None:
    """Enable an existing API key."""
    with security_db() as conn:
        conn.execute("UPDATE api_keys SET enabled = 1 WHERE id = ?", (key_id,))
    _invalidate_api_key_cache()
    audit_event(actor="system", action="api_key_enable", path="/admin/keys", status="success", note=str(key_id))


def list_api_keys(include_disabled: bool = False) -> list[dict[str, Any]]:
    """Return API key metadata without exposing sensitive hashes."""
    records = _load_api_keys()
    payload: list[dict[str, Any]] = []
    for record in records:
        if not include_disabled and not record.enabled:
            continue
        payload.append(
            {
                "id": record.id,
                "name": record.name,
                "role": record.role.value,
                "enabled": record.enabled,
                "created_at": record.created_at,
                "last_used_at": record.last_used_at,
            }
        )
    return payload
