# SocietySphere Security Baseline & Hardening Specification

## 1. Zero-Trust Security Principles
SocietySphere operates under a Zero-Trust architectural model:
1. **Never Trust Client Claims**: Society IDs, role assertions, or unit ownership claims sent by clients are never accepted without server-side validation against authenticated session contexts.
2. **Backend Defense-in-Depth**: Authorization checks are strictly enforced in the backend domain layer, never reliant on frontend UI controls or route guards.
3. **Defense-in-Depth Multi-Tenancy**: Data segregation is enforced at the application context layer and physically backed by PostgreSQL Row-Level Security (RLS) in the database kernel.

### 1.1 Tenant Context Security (`X-Society-ID` Header Contract)
> [!IMPORTANT]
> The incoming `X-Society-ID` HTTP header is **strictly a client-provided tenant-context hint**, NOT an authorization credential or trusted identifier.
> 
> The backend **MUST NOT** accept or apply `X-Society-ID` without cryptographically verifying the authenticated user's active membership in that society.

The mandatory authorization and tenant resolution model:
```
Authenticated User (JWT / Session)
        ↓
User Membership Lookup (Verified in DB/Redis)
        ↓
Authorized Society/Tenant (Validates requested tenant hint against memberships)
        ↓
Backend Authorization (RBAC / ABAC / ReBAC resource checks)
        ↓
Database Row-Level Security (RLS sets `app.current_society_id`)
```
- If a user sends `X-Society-ID: <Tenant-B>` but only has membership in `<Tenant-A>`, the backend immediately rejects the request with HTTP 403 Forbidden (`AUTHORIZATION_ERROR`).
- Zero cross-tenant data leakage is permitted.

## 2. Secrets Management & Credential Safety
- **No Secrets in Source Control**: All configuration containing secrets, credentials, or encryption keys is strictly loaded via environment variables (`.env`) using Pydantic v2 `BaseSettings`.
- **Pre-Commit Isolation**: `.gitignore` strictly blocks all `.env`, `.pem`, `.key`, and credential file variants from being committed.
- **Production Validation Gate**: Application startup strictly fails in production if default/insecure secret keys (`SECRET_KEY`) are detected or if `DEBUG` is set to `True`.

## 3. Network & Transport Security
- **Strict HTTPS / TLS 1.3**: All external traffic is terminated via reverse proxy over TLS 1.3.
- **Strict Content Security Policy (CSP)**: Headers prevent malicious script injection and untrusted frame rendering.
- **Mandatory Security Headers**:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`

## 4. CORS & Host Filtering
- **Production CORS Rule**: Wildcard `allow_origins=["*"]` is strictly forbidden in production. Explicit allowed domains must be declared in `CORS_ALLOWED_ORIGINS`.
- **Trusted Host Middleware**: Protects against HTTP Host Header poisoning attacks by restricting accepted Host headers to `ALLOWED_HOSTS`.

## 5. DoS & Abuse Mitigation
- **Request Size Limiting**: `RequestSizeLimitMiddleware` inspects `Content-Length` headers and rejects payloads exceeding 10MB (`MAX_REQUEST_SIZE_BYTES`) with HTTP 413.
- **Rate Limiting Foundation**: IP and token-based rate limiting configured via Redis token-bucket / sliding-window algorithms to prevent credential brute-forcing and API denial of service.

## 6. Observability & PII Redaction
- **Log Sanitation**: Automated regex filters scrub sensitive fields from all log streams:
  - Passwords and tokens (`password`, `token`, `access_token`, `refresh_token`)
  - Payment credentials and card numbers
  - Email addresses and phone numbers
- **Safe Error Responses**: In production environments, internal database error details, stack traces, and system file paths are completely suppressed from client responses.

## 7. AI & Autonomous Agent Guardrails
- **Zero Direct Database Access**: AI assistants operate with zero raw SQL, ORM, or database access.
- **Verified Structured Interfaces Only**: AI interacts solely through authorized application services subject to the user's active RBAC permissions.
- **Deterministic Calculations First**: AI is strictly prohibited from computing financial totals, balances, or tax figures.
