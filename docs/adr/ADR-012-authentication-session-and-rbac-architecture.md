# ADR-012: Authentication, Rotating Session Security, and Multi-Tenant RBAC Architecture

## Status
Accepted

## Context
In Phase 2, SocietySphere established a shared-database, tenant-discriminator architecture backed by PostgreSQL Row-Level Security (RLS) and global user identities decoupled from tenant memberships.

In Phase 3, the platform required a production-grade authentication, session management, and role-based access control (RBAC) foundation that satisfies the following core architectural requirements:
1. **Decoupled Identity vs. Authorization**: Authentication identifies a global human user; tenant authorization determines their permitted actions within an active society context.
2. **Replay-Immune Session Lifecycles**: Refresh tokens must rotate on every use, with automatic family revocation if an expired or stolen token is replayed.
3. **Stateless Scalability with Instant Revocation**: Short-lived JWT access tokens enable fast request handling while session table tracking allows instant revocation upon logout, password reset, or account suspension.
4. **Privilege Escalation and IDOR Prevention**: Tenant context hints must never be trusted blindly as proof of authorization; role assignments must enforce strict scope rules.

## Decision

We have designed and implemented Phase 3 Authentication and Session Architecture according to the following specifications:

1. **Argon2id Password Cryptography**:
   - Standardized on Argon2id conforming to RFC 9106 ($t=3, m=65536, p=4, \text{salt}=16\text{B}$).
   - Enforce server-side password complexity policies (8 to 128 chars, blacklist against dictionary passwords).
   - Implement constant-time dummy verification (`verify_dummy_password()`) to neutralize username enumeration via timing attacks.

2. **Session and Refresh Token Family Architecture**:
   - Generate opaque refresh tokens with 384 bits of CSPRNG entropy (`secrets.token_urlsafe(48)`).
   - Store exclusively SHA-256 digests (`VARCHAR(64)`) in the `user_sessions` database table. Raw tokens are never persisted.
   - Group sessions into cryptographic `family_id` chains. If an already-rotated/revoked token hash is submitted, the backend immediately invalidates the entire family and audits `AUTH_REFRESH_REPLAY_DETECTED`.

3. **Short-Lived Access Tokens Without Authoritative Claims**:
   - JWT access tokens have a 15-minute lifespan (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`), signed via HMAC-SHA256 (`HS256`).
   - Access tokens strictly contain identity identifiers (`sub` = user_id, `sid` = session_id). They do **not** carry tenant roles or permission lists. All tenant-scoped authorization is resolved dynamically per request and enforced via PostgreSQL RLS.

4. **Multi-Tenant RBAC & Scope Enforcement**:
   - Roles are partitioned into `PLATFORM` scope (society_id = NULL) and `SOCIETY` scope (society_id != NULL) with database check constraints.
   - Non-`SUPER_ADMIN` users cannot assign `SUPER_ADMIN` or platform roles (privilege escalation guard).
   - Users must hold an active `UserSocietyMembership` in a society before receiving roles in that society.

5. **Single-Use Cryptographic Password Reset**:
   - Single-use 384-bit tokens stored as SHA-256 digests in `password_reset_tokens` with strict 15-minute expiration.
   - Generic responses on reset requests to prevent user enumeration.
   - Successful reset atomically revokes all active sessions for the user across all devices.

## Consequences

### Positive
- **Guaranteed Tenant Isolation**: Complete elimination of cross-tenant privilege leaks or data tampering through dual verification (backend service + database RLS).
- **Proactive Threat Neutralization**: Automatic invalidation of entire session families upon token theft or replay detection.
- **Accurate Privilege State**: Zero permission desynchronization; role revocations take effect immediately without waiting for access tokens to expire.
- **MFA Ready**: Data structures and state transitions are ready for future TOTP/SMS second-factor layers without database migrations.

### Negative / Trade-offs
- **Session Lookup Overhead**: Every authenticated request evaluates session revocation status via database or Redis cache. This trade-off is accepted as necessary for enterprise-grade security and instant session termination.
