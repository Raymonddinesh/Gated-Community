# SocietySphere Multi-Tenancy Security Specification

## 1. Security Architecture Summary

SocietySphere is built on an enterprise multi-tenant model where a **Society** forms the strict isolation boundary.
The platform enforces security using a **Defense-in-Depth** model combining:
1. Application-level task context (`contextvars`).
2. Domain membership verification (`TenantService`).
3. Repository-level tenant parameterization.
4. Database engine PostgreSQL Row-Level Security (RLS).
5. Transaction-scoped connection sanitization (`SET LOCAL`).

---

## 2. Threat Modeling & Prevented Vectors

| Threat Vector | Attack Description | Mitigation Mechanism |
| :--- | :--- | :--- |
| **Cross-Tenant ID Forgery** | An attacker belonging to Society A intercepts or modifies request headers to pass `X-Society-ID: <UUID_B>` in order to view Society B data. | `TenantService.verify_tenant_access` validates user membership against the database. Forged hints trigger HTTP 403 Forbidden with zero data disclosure. |
| **Connection Pool Contamination** | In an async connection pool, connection `conn_1` serves a query for Society A (`SET app.current_society_id = 'A'`) and is then reassigned to an unprivileged request for Society B. | `SET LOCAL` is used exclusively. PostgreSQL automatically purges transaction-scoped session variables upon commit/rollback, ensuring connection reuse is 100% sterile. |
| **Query Parameter Leakage** | A developer forgets to write `WHERE society_id = :id` in a complex JOIN or custom reporting query. | PostgreSQL Row-Level Security (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`) evaluates row visibility at the SQL kernel level, dropping non-matching rows regardless of query syntax. |
| **Scoped Namespace Collisions** | Society A and Society B both name their primary building "Tower 1" or apartment "Flat 101". | Unique constraints are composite and tenant-scoped: `UNIQUE(society_id, code)` for blocks, and `UNIQUE(society_id, block_id, unit_number)` for units. |
| **Platform Privilege Escalation** | A Society Admin attempts to perform cross-tenant operations or manage platform-wide configuration. | Role assignments strictly enforce scope separation (`ck_role_assignments_scope_validity`). Society roles require non-null `society_id` and have no access to platform endpoints. |

---

## 3. Defense-in-Depth Pipeline

```
Incoming Request
  │
  ▼
1. Extract JWT / Session Token
  │
  ▼
2. Resolve Authenticated User ID
  │
  ▼
3. Inspect X-Society-ID Header Hint
  │
  ├── Missing Hint ──> Resolve user's default active society membership
  └── Provided Hint ─> Verify User holds ACTIVE membership in requested society
         │
         ├── NOT A MEMBER ──> HTTP 403 Forbidden [HALT]
         └── VERIFIED ──────> Set async contextvar (current_tenant_id)
                                  │
                                  ▼
4. Database Session Activation (get_db_session)
  │
  ▼
5. Execute: SET LOCAL app.current_society_id = '<verified_uuid>'
  │
  ▼
6. Domain Repository Query Execution (Filtered by society_id)
  │
  ▼
7. PostgreSQL RLS Kernel Enforcement (Restrictive row filters)
  │
  ▼
8. Transaction Commit & Automatic SET LOCAL Discard
  │
  ▼
Sanitized Connection Returned to Pool
```

---

## 4. Verification & Continuous Testing

Tenant isolation is verified continuously across our automated test suite:
- `tests/test_database_schema.py`: Verifies composite uniqueness scoping across distinct societies.
- `tests/test_tenant_isolation.py`:
  - Directly tests cross-tenant rejection (`verify_tenant_access`).
  - Confirms non-members receive HTTP 403.
  - Verifies `SET LOCAL` isolation and pooling safety.
  - Verifies repository query boundaries.
- `tests/test_society_api.py`: Validates end-to-end API header validation and 404/403 security behavior on cross-tenant requests.
