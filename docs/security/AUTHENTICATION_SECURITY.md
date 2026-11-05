# Authentication Security Architecture

## 1. Overview & Core Philosophy

SocietySphere implements a multi-tenant authentication architecture that strictly isolates **Identity Verification (Authentication)** from **Tenant Authorization**. 

```
                                +-------------------+
                                |   Client Request  |
                                +---------+---------+
                                          |
                                    (Credentials)
                                          v
                                +-------------------+
                                | Global User Store |
                                |  (Single Identity)|
                                +---------+---------+
                                          |
                                   (Authenticated)
                                          v
                                +-------------------+
                                | Active Session    |
                                | (Rotating Refresh)|
                                +---------+---------+
                                          |
                    +---------------------+---------------------+
                    |                                           |
                    v                                           v
      +---------------------------+               +---------------------------+
      |  Tenant Context Society A |               |  Tenant Context Society B |
      |  (UserSocietyMembership)  |               |  (UserSocietyMembership)  |
      |  Role: SECRETARY          |               |  Role: RESIDENT           |
      +---------------------------+               +---------------------------+
```

### Core Tenets
1. **Global Identity, Local Authority**: A user possesses exactly one platform-wide identity record (`users` table). Access to apartment society resources is governed strictly through verified `UserSocietyMembership` associations.
2. **Untrusted Client Inputs**: HTTP headers (`X-Society-ID`), URL parameters, and client-supplied bodies are treated strictly as **context hints**. Authorization is resolved dynamically server-side via membership and RBAC verification.
3. **Defense-in-Depth Storage**: Raw passwords and unhashed tokens are never persisted in databases, logs, caches, or traces.

---

## 2. Password Security & Argon2id Specification

All user passwords are encrypted using the Argon2id algorithm, configured in compliance with RFC 9106 standards:

| Parameter | Configuration | Security Objective |
| :--- | :--- | :--- |
| **Algorithm** | `Argon2id` | Hybrid defense against both side-channel cache attacks and GPU cracking |
| **Time Cost ($t$)** | `3` iterations | Compute hardness preventing high-speed brute force |
| **Memory Cost ($m$)** | `65536 KiB` (64 MiB) | High memory-hardness neutralizing ASIC and FPGA acceleration |
| **Parallelism ($p$)** | `4` lanes | Leverages multicore processing securely |
| **Salt Length** | `16 bytes` (128 bits) | Cryptographically secure CSPRNG salt generated per user |
| **Hash Length** | `32 bytes` (256 bits) | Truncation-resistant output digest |

### Password Policy
The server enforces the following mandatory policy constraints before accepting passwords during creation or updates:
- **Minimum Length**: 8 characters (configured via `AUTH_PASSWORD_MIN_LENGTH`).
- **Maximum Length**: 128 characters (protects against hashing DoS attacks via `AUTH_PASSWORD_MAX_LENGTH`).
- **Dictionary Blacklist**: Known weak passwords (e.g., `password`, `12345678`, `admin123`, `societysphere`) are unconditionally rejected.

### Timing Attack Mitigation (Constant-Time Dummy Verification)
To prevent username enumeration via response latency timing attacks, when an identifier is submitted that does not correspond to an existing account, the system executes a constant-time dummy Argon2id calculation against a pre-computed hash (`verify_dummy_password()`). This equalizes response latencies across both valid and invalid identifiers.

---

## 3. JWT Access Tokens

Short-lived JSON Web Tokens (JWT) are issued to client applications for stateless request authorization:
- **Lifetime**: 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`).
- **Signature Algorithm**: HMAC-SHA256 (`HS256`) signed with `SECRET_KEY` (minimum 32-character high-entropy secret).
- **Token Claims Payload**:
  ```json
  {
    "sub": "11111111-1111-1111-1111-11111111111a",
    "sid": "22222222-2222-2222-2222-22222222222a",
    "jti": "33333333-3333-3333-3333-33333333333a",
    "type": "access",
    "iat": 1790937600,
    "exp": 1790938500
  }
  ```
- **Claim Design Principle**: JWTs deliberately do **not** contain tenant IDs, roles, or permission strings. Because role assignments, suspensions, and tenant permissions can change instantaneously, embedding authorization claims in access tokens causes privilege lag and security desynchronization. Instead, permissions are resolved dynamically against the active database session and PostgreSQL RLS.

---

## 4. Rate Limiting & Abuse Prevention

All public authentication endpoints are protected by rate limiters backed by Redis atomic sliding windows (with in-memory fallbacks):
- **`/api/v1/auth/login`**: Max 10 attempts per minute per IP (`AUTH_LOGIN_RATE_LIMIT_PER_MINUTE`). Exceeding returns HTTP 429 (`RATE_LIMITED`).
- **`/api/v1/auth/refresh`**: Max 30 attempts per minute per IP (`AUTH_REFRESH_RATE_LIMIT_PER_MINUTE`).
- **`/api/v1/auth/password-reset/request`**: Max 5 attempts per minute per identifier (`AUTH_PASSWORD_RESET_RATE_LIMIT_PER_MINUTE`).
