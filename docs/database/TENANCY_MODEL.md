# SocietySphere Multi-Tenancy Architecture Model

## 1. Primary Tenant Boundary

In SocietySphere, the **Society** is the primary tenant boundary.
A `Society` represents an independent legal housing cooperative, apartment owners association, or gated residential community.

Each society operates as an isolated organizational and data domain:
- Accounting ledgers and financial transactions are strictly segregated.
- Resident, tenant, and visitor records must never leak between societies.
- Maintenance tickets, gate access, and committee approvals belong solely to the society where they occurred.

---

## 2. Decoupled Identity Model (`User != Society Membership`)

A critical architectural distinction in SocietySphere is that **Users are global**, whereas **Memberships and Roles are tenant-scoped**:

```
                  ┌──────────────────────┐
                  │     Global User      │
                  │ (email/phone identity│
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌────────────────────────┐       ┌────────────────────────┐
│  Society A Membership  │       │  Society B Membership  │
│  Role: SECRETARY       │       │  Role: RESIDENT        │
│  Unit: Flat 402        │       │  Unit: Flat 104        │
└────────────────────────┘       └────────────────────────┘
```

### Architectural Rationale:
1. **Real-World Property Ownership:** Individuals frequently own flats in one society while renting or residing in another, or manage family apartments in different complexes.
2. **Single Credential:** A user logs in once with a single identity rather than managing separate logins per society.
3. **Strict Authorization Partitioning:** Access permissions are evaluated dynamically based on the verified tenant context for the active request. Having administrative privileges in Society A grants zero access to Society B.

---

## 3. Defense-in-Depth Isolation Layers

Tenant isolation is enforced across three distinct layers:

### Layer 1: Application-Level Tenant Context & Validation

1. **Context Tracking:** The active tenant identifier is propagated safely using Python's `contextvars` in `apps/api/src/core/tenant_context.py`. Because `contextvars` are native to Python's `asyncio` event loop, each concurrent async request maintains completely isolated context.
2. **`TenantService.verify_tenant_access(user_id, requested_society_id)`:**
   - Any client-provided tenant hint (e.g., `X-Society-ID` header) is treated as **untrusted user input**.
   - The backend validates that the authenticated user possesses an **ACTIVE** membership in the requested society.
   - If no verified active membership exists (and the user is not a Platform Super Admin), the request is rejected immediately with **HTTP 403 Forbidden**.

### Layer 2: Domain Repository Scoping

Every query constructed in the database repository layer explicitly binds to the verified tenant boundary:
```python
# All spatial and membership queries include society_id filtering:
stmt = select(Block).where(Block.society_id == verified_society_id)
```
This guarantees that query generation is explicitly tenant-scoped even before reaching the database engine.

### Layer 3: Database Engine Row-Level Security (PostgreSQL RLS)

At the database engine level, PostgreSQL Row-Level Security (RLS) is enabled on all tenant-owned tables (`blocks`, `floors`, `units`, `user_society_memberships`, `unit_occupancies`, `resident_profiles`, `audit_logs`).

```sql
ALTER TABLE blocks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON blocks
    AS RESTRICTIVE
    USING (
        society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid
    );
```

Even if an application developer inadvertently wrote `SELECT * FROM units`, PostgreSQL will filter the returned rows strictly to those matching `app.current_society_id`.

---

## 4. Connection Pooling Safety (`SET LOCAL`)

In modern async web applications using connection pools (such as `asyncpg` with SQLAlchemy), pooled physical database connections are reused across multiple requests.

If a session executes `SET app.current_society_id = 'tenant-A'`, that setting could contaminate the physical connection when returned to the pool, risking cross-tenant data leakage on the next request.

### The Solution: Transaction-Scoped `SET LOCAL`
SocietySphere mandates transaction-scoped setting:
```python
await session.execute(text("SET LOCAL app.current_society_id = :val"), {"val": str(society_id)})
```

In PostgreSQL:
- `SET LOCAL` is valid **only for the duration of the current transaction block**.
- Upon `COMMIT`, `ROLLBACK`, or closing the session, PostgreSQL automatically and unconditionally clears the setting back to default.
- The connection is returned to the pool completely sanitized.

---

## 5. Client Tenant Hint (`X-Society-ID`) Security Contract

1. The `X-Society-ID` HTTP header is strictly an **unverified routing hint**.
2. Frontend applications send this hint to inform the backend which of the user's authorized societies is currently active in the UI workspace.
3. **Security Principle:** The backend NEVER trusts the `X-Society-ID` header as an authorization grant. Every request verifies membership before establishing the tenant context and issuing `SET LOCAL`.
