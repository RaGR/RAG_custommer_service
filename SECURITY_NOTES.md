# Security Architecture Notes

## Overview

- **Authentication**  
  - Primary mode: Argon2-hashed API keys stored in SQLite (`api_keys`). When Argon2 is not available at runtime, the service falls back to PBKDF2-SHA256 with high iteration count (warning emitted) so tests still run. Roles are enforced at request time (CLIENT, ANALYST, ADMIN).  
  - Optional JWT Bearer support (`AUTH_MODE=jwt`) using HS256 or RS256. Tokens must include `iss`, `aud`, `sub`, and at least one role. Key rotation is handled by `kid` lookups against an in-memory registry.

- **Request Integrity**  
  - When `HMAC_REQUIRED=true`, clients with API keys must sign requests using `X-Signature`, `X-Timestamp`, `X-Nonce`. Nonces are cached per key and expire on the configured window (default 300 s) to prevent replay.

- **Rate Limiting**  
  - Token bucket per identity (API key id, JWT `sub`, or IP). Defaults via env, with tenant overrides stored in `tenant_limits`. Over-limit responses return HTTP 429 plus `Retry-After`.

- **Authorization**  
  - RBAC policies:
    - `/simulate_dm`, `/feedback`: CLIENT, ANALYST, or ADMIN.
    - `/metrics`: ADMIN or ANALYST.
    - `/admin/api-keys/*`, `/security/selftest`: ADMIN only.
  - Security context is cached on `request.state` to avoid duplicate verification and to support logging/HMAC.

- **Middleware & Headers**  
  - `BodySizeLimitMiddleware` enforces `MAX_REQUEST_BODY_BYTES`.  
  - `SecurityHeadersMiddleware` injects CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy, and Referrer-Policy.  
  - CORS origins are restricted via env (`CORS_ORIGINS`), exposing minimal methods/headers.

- **Logging & Privacy**  
  - Structured JSON logs with hashed identities, request id, roles, latency, rate-limit tokens, and provider metrics. No secrets, raw prompts, or API keys are emitted.  
  - LLM calls are timed and routed through an in-memory circuit breaker with per-provider failure counters.

- **Audit & Admin**  
  - Privileged actions (API key lifecycle) are recorded in the `audit` table.  
  - `/admin/api-keys` endpoints allow admins to create/enable/disable keys; plaintext keys are only returned once.  
  - `/security/selftest` verifies schema, headers, and configuration without leaking secrets.

- **Testing**  
  - `pytest` suite exercises API key auth, JWT validation (expiry/audience/roles), HMAC error cases, rate limiting, CORS/headers, body size enforcement, and log redaction.

## Trade-offs & Future Work

- In-memory nonce cache and rate-limit buckets are process-local; a shared cache (Redis) would be needed for multi-instance deployments.  
- Argon2 verification currently iterates enabled keys; acceptable for small sets but could be optimized with key prefixes or lookup tables.  
- JWT key registry reads from env on process start; dynamic rotation would require hot reload or KMS integration.  
- Circuit breaker statistics reset on restart; persisting state or exporting to metrics backend would improve observability.  
- Admin API authenticates via the same API key mechanism; consider separate admin identity provider for stricter separation of duties.
