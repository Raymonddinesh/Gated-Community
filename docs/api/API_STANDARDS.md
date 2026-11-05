# SocietySphere API Standards & Guidelines

## 1. API Architecture & Versioning Strategy

All business APIs follow strict RESTful principles, explicit HTTP semantics, and path-based versioning:

- **Version 1 Base Path**: `/api/v1`
- **Future Versioning**: When non-backward-compatible breaking changes are required, a new router `/api/v2` will be introduced. Existing `/api/v1` endpoints will remain supported and deprecated gracefully over a minimum 6-month deprecation window.
- **Mobile Client Parity**: The backend automatically generates OpenAPI 3.0 specifications at `/api/v1/openapi.json`. Typed Dart/Flutter client SDKs are auto-generated to guarantee zero client-server contract drift.

## 2. Standard Request Headers

Every request processed by SocietySphere APIs supports the following standardized headers:

| Header Name | Required | Description |
|---|---|---|
| `X-Correlation-ID` / `X-Request-ID` | Recommended | Unique request trace ID. If omitted by the client, the backend middleware automatically assigns a UUIDv4 and returns it in the response. |
| `X-Society-ID` | Contextual | **Tenant-Context Hint Only**: The requested society UUID. MUST NOT be trusted as an authorization claim; the backend strictly validates user membership before applying tenant context. |
| `Authorization` | Protected routes | `Bearer <JWT_ACCESS_TOKEN>` containing cryptographically verified identity claims. |
| `Idempotency-Key` | Mutating actions | UUIDv4 string preventing duplicate processing on critical mutating operations (payments, gate passes, dues). |
| `Content-Type` | Mutating actions | `application/json` (or `multipart/form-data` for file uploads). |

> [!CAUTION]
> **Tenant Header Security Rule**: The `X-Society-ID` header is exclusively an unverified client hint. The backend validates whether the authenticated user has an active membership record in that society before establishing tenant scope. Mismatched or unauthorized hints immediately return HTTP 403.

## 3. Standard Response Headers

Every HTTP response emitted by the backend includes:

| Header Name | Example | Purpose |
|---|---|---|
| `X-Correlation-ID` | `c9406596-f6d8-4f81-a83a-d68a2bf85d68` | Matches client or server trace ID for log correlation. |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing. |
| `X-Frame-Options` | `DENY` | Prevents clickjacking attacks. |
| `X-XSS-Protection` | `1; mode=block` | Browser XSS filtering protection. |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer leakage prevention. |

## 4. Standard Error Model (RFC 7807 Compatible)

All non-2xx responses strictly conform to a consistent error schema:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "request_id": "c9406596-f6d8-4f81-a83a-d68a2bf85d68",
    "details": {
      "fields": [
        {
          "field": "email",
          "issue": "Invalid email address format"
        }
      ]
    }
  }
}
```

### Standard Error Codes:
- `VALIDATION_ERROR` (422 Unprocessable Entity)
- `AUTHENTICATION_ERROR` (401 Unauthorized)
- `AUTHORIZATION_ERROR` (403 Forbidden)
- `NOT_FOUND` (404 Not Found)
- `CONFLICT` (409 Conflict)
- `RATE_LIMITED` (429 Too Many Requests)
- `PAYLOAD_TOO_LARGE` (413 Request Entity Too Large)
- `INTERNAL_SERVER_ERROR` (500 Internal Server Error)

> **Security Rule**: In production, stack traces, database credentials, and internal framework exceptions are NEVER exposed in error payloads.

## 5. Health Probes
- `GET /health`: Returns high-level application health and uptime.
- `GET /health/live`: Lightweight process liveness probe.
- `GET /health/ready`: Backing infrastructure dependency readiness probe (PostgreSQL, Redis, RabbitMQ).
