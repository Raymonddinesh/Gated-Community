# SocietySphere Tenant Context Resolution Contract

## 1. Executive Summary

In a multi-tenant platform where users can belong to multiple societies concurrently, resolving the active tenant context must follow a **deterministic, unambiguous, and fail-safe** protocol.

This document defines the canonical tenant resolution pipeline, exact precedence rules, conflict error contracts, and database session binding.

---

## 2. Canonical Precedence Hierarchy

The active tenant for any incoming HTTP request is resolved strictly in the following order:

```
┌────────────────────────────────────────────────────────┐
│ 1. URL Society Parameter (/societies/{society_id}/...) │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│ 2. X-Society-ID HTTP Header Hint                       │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│ 3. Authenticated User's Single Active Membership       │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│ 4. Transaction-Scoped Database Context (SET LOCAL)     │
└────────────────────────────────────────────────────────┘
```

---

## 3. Deterministic Resolution Protocol

### Scenario A: URL Society ID is Present
*Example:* `GET /api/v1/societies/aaaa-1111/blocks`
1. The URL parameter `society_id` identifies the target resource tenant.
2. If `X-Society-ID` is **also supplied**:
   - If `X-Society-ID == URL society_id`: Target tenant is confirmed.
   - If `X-Society-ID != URL society_id`: **IMMEDIATE REJECTION**. The request contradicts itself.
     - **HTTP Status:** `400 Bad Request`
     - **Error Code:** `TENANT_CONTEXT_MISMATCH`
     - **Message:** `"Tenant context mismatch: URL resource specifies society '{url_id}' but X-Society-ID header specifies '{header_id}'."`
3. The backend validates that the authenticated caller has active membership in the target society (or holds platform `SUPER_ADMIN`). If not:
   - **HTTP Status:** `403 Forbidden`
   - **Error Code:** `AUTHORIZATION_ERROR`

---

### Scenario B: URL Society ID is Absent, but `X-Society-ID` is Present
*Example:* `GET /api/v1/blocks/{block_id}/floors` with `X-Society-ID: aaaa-1111`
1. The `X-Society-ID` header serves as the requested tenant hint.
2. The backend validates that the authenticated caller has an active membership in `aaaa-1111` (or is a platform `SUPER_ADMIN`).
3. If valid, the target tenant is bound to `aaaa-1111`.
4. If the caller does not belong to `aaaa-1111`:
   - **HTTP Status:** `403 Forbidden`
   - **Error Code:** `AUTHORIZATION_ERROR`
   - **Zero cross-tenant disclosure.**

---

### Scenario C: Neither URL Society ID nor `X-Society-ID` is Present
*Example:* User accesses a tenant-dependent endpoint without specifying a society context.
1. The backend inspects the authenticated caller's active memberships in the database:
   - **Case 1: User belongs to 0 societies:**
     - If user is an ordinary resident: **HTTP 403 Forbidden** (`AUTHORIZATION_ERROR`).
     - If user is a Platform `SUPER_ADMIN`: **HTTP 400 Bad Request** (`TENANT_CONTEXT_REQUIRED`). A Super Admin must explicitly choose a target society context before querying tenant resources.
   - **Case 2: User belongs to exactly 1 society:**
     - Unambiguous. The single society is automatically resolved as the active tenant context.
   - **Case 3: User belongs to 2 or more societies:**
     - **STRICT PROHIBITION:** The backend must **NEVER** silently choose an arbitrary society (e.g. "first created" or "most recently accessed").
     - **HTTP Status:** `400 Bad Request`
     - **Error Code:** `TENANT_CONTEXT_REQUIRED`
     - **Message:** `"Ambiguous tenant context: User holds active memberships in multiple societies. An explicit X-Society-ID header or URL society parameter is required."`
     - **Payload Details:** Includes `available_societies` array containing valid society UUIDs for the frontend workspace selector modal.

---

## 4. Standardized Error Response Specifications

### 4.1 Tenant Context Mismatch Error
```json
{
  "error": {
    "code": "TENANT_CONTEXT_MISMATCH",
    "message": "Tenant context mismatch: URL resource specifies society 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' but X-Society-ID header specifies 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'.",
    "request_id": "req_8f1c34a2-e612-4d2b-b6b9",
    "details": {
      "url_society_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "header_society_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    }
  }
}
```

### 4.2 Tenant Context Required (Ambiguity) Error
```json
{
  "error": {
    "code": "TENANT_CONTEXT_REQUIRED",
    "message": "Ambiguous tenant context: User holds active memberships in multiple societies. An explicit X-Society-ID header or URL society parameter is required.",
    "request_id": "req_1d7b89aa-5523-4e89-a212",
    "details": {
      "available_societies": [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
      ]
    }
  }
}
```

---

## 5. Database Tenant Context Application

Once the target society is verified and resolved by `TenantService`:
1. The active society UUID is stored in the async task context variable (`set_current_tenant_id`).
2. When the FastAPI request handler checks out a database session from `get_db_session()`:
   ```python
   await session.execute(text("SET LOCAL app.current_society_id = :val"), {"val": str(resolved_society_id)})
   ```
3. PostgreSQL Row-Level Security activates for the lifetime of that transaction.
4. Upon transaction commit/rollback, PostgreSQL resets `app.current_society_id` to empty string.
5. The connection is sanitized before returning to the connection pool.
