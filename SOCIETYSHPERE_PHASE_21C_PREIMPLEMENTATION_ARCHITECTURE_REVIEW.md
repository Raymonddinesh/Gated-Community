# SOCIETYSPHERE — PHASE 21C PRE-IMPLEMENTATION ARCHITECTURE REVIEW

**Document ID**: `SOCIETYSPHERE-PHASE-21C-ARCH-REVIEW-001`  
**Review Date**: 2026-10-27  
**Reviewers**: Principal Backend Architect, PostgreSQL Security Reviewer, Distributed Concurrency Specialist  
**Target Specification**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md`  
**Target System**: Phase 21C — Society Provisioning Engine  
**Baseline Verified**: Migrations `0001–0021`, Phases 1–21B (371 tests PASS)  
**Execution Context**: PostgreSQL 16 Alpine, SQLAlchemy 2.0 Async, asyncpg  
**Review Status**: **COMPLETE**  
**Final Determination**: **APPROVE WITH CONDITIONS**

---

## EXECUTIVE SUMMARY

A formal, strictly read-only pre-implementation architecture review of the **Phase 21C Society Provisioning Engine Architecture Proposal** was conducted. The review evaluated the proposal against the live codebase, the active PostgreSQL 16 container, and Alembic migrations `0001` through `0021`.

The architecture proposal is fundamentally sound and well-architected. It establishes a robust, all-or-nothing transactional boundary, preserves the zero-RLS-bypass mandate, integrates cleanly with Phase 21B domain services, and requires **zero new database migrations** (no Migration `0022`).

However, the review identified four critical technical conditions that must be incorporated into the final implementation plan:
1. **PostgreSQL Parameterization Defect in `session.py`**: The statement `SET LOCAL app.current_society_id = :val` produces a `syntax error at or near "$1"` under `asyncpg` on live PostgreSQL because PostgreSQL's utility `SET` grammar rejects bind parameters. The technically correct parameterized method is `SELECT set_config('app.current_society_id', :val, true)`.
2. **Locking Semantics (Blocking vs. Non-Blocking)**: The proposal claimed `pg_advisory_xact_lock` (which blocks) while simultaneously claiming that concurrent in-progress requests return HTTP 409 Conflict. To achieve immediate HTTP 409 without exhausting connection pools, `pg_try_advisory_xact_lock` must be used.
3. **Idempotency Payload Fingerprinting**: To comply with RFC 9440 idempotency standards, reusing an idempotency key with a mutated payload must return HTTP 422 `IDEMPOTENCY_PAYLOAD_MISMATCH` rather than blindly replaying the original result.
4. **Lack of Database-Level Uniqueness on `legal_name`**: Because `societies.legal_name` lacks a unique constraint in Migration `0002`, duplicate prevention relies on serialization via advisory locks combined with an explicit case-normalized query.

---

## REVIEW 1 — TRANSACTIONAL ATOMICITY

### Finding 1.1: Single Database Transaction Boundary
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/src/database/models/society.py#L24-L96` and `apps/api/src/database/models/subscription.py#L135-L374`
* **Evidence from Source Inspection**:
  - The root `Society` model (`societies` table) and all tenant-owned models (`society_subscriptions`, `society_usage_metrics`, `society_provisioning_logs`, `user_society_memberships`, `role_assignments`, `blocks`) are defined within the same SQLAlchemy declarative base (`Base`) and map to the same PostgreSQL relational database.
  - In `Society` (`society.py#L32-L36`), the primary key `id` is a UUID generated on object initialization (`default=uuid.uuid4`). When `session.flush()` is called after creating the root `Society` object, `society.id` is fully populated and available to all downstream foreign-key relationships within the exact same `AsyncSession` transaction.
  - No separate connection, transaction, or database engine is required to link tenant-owned records to the global society record.
* **Risk & Required Correction**: None. Atomicity across the root society and tenant-scoped tables within a single `AsyncSession` is verified.

### Finding 1.2: Identification of Provisioning Steps & Tables Modified
* **Finding Status**: **PASS**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-2.2`
* **Evidence from Source Inspection**:
  The nine discrete steps, their target tables, table scopes, and transaction boundaries are verified as follows:

| Step Sequence | Step Key | Target Table(s) | Table Scope | Session / Transaction Used |
| :--- | :--- | :--- | :--- | :--- |
| **Step 01** | `VALIDATE_INPUT` | `platform_subscription_plans`, `societies` | Global (Read-only) | Main `AsyncSession` (Active Tx) |
| **Step 02** | `CREATE_SOCIETY_ROOT` | `societies` | Global (Unscoped) | Main `AsyncSession` (Active Tx) |
| **Step 03** | `BIND_TENANT_RLS` | None (GUC `app.current_society_id`) | Session GUC | Main `AsyncSession` (Active Tx) |
| **Step 04** | `ASSIGN_SUBSCRIPTION` | `society_subscriptions` | Tenant RLS | Main `AsyncSession` (Active Tx) |
| **Step 05** | `INIT_USAGE_METRICS` | `society_usage_metrics` | Tenant RLS | Main `AsyncSession` (Active Tx) |
| **Step 06** | `PROVISION_ADMIN_USER` | `users`, `user_society_memberships` | Global + Tenant RLS | Main `AsyncSession` (Active Tx) |
| **Step 07** | `ASSIGN_ADMIN_ROLE` | `role_assignments` | Tenant RLS | Main `AsyncSession` (Active Tx) |
| **Step 08** | `INIT_SPATIAL_BASELINE`| `blocks` | Tenant RLS | Main `AsyncSession` (Active Tx) |
| **Step 09** | `FINALIZE_ONBOARDING` | `societies`, `society_provisioning_logs`| Global + Tenant RLS | Main `AsyncSession` (Active Tx) |

* **Risk & Required Correction**: None. All nine steps modify tables accessible via the single session and commit together at Step 09.

### Finding 1.3: Isolation of External Side Effects
* **Finding Status**: **PASS WITH CONDITIONS**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21_ARCHITECTURE_SPECIFICATION.md#L326-L340` and `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-8`
* **Evidence from Source Inspection**:
  - Provisioning involves sending welcome emails/SMS with administrative setup credentials and publishing events (`SOCIETY_PROVISIONED`).
  - External network calls (SMTP servers, Twilio SMS API, external webhooks) CANNOT participate in a PostgreSQL two-phase commit or ACID transaction.
  - If external network calls are executed inside the database transaction:
    1. A slow email/SMS provider holds open the database transaction, retaining row locks and connection pool resources for seconds.
    2. If the external call succeeds but the database transaction subsequently fails to commit, the user receives credentials for a society that was rolled back (phantom notification).
* **Risk & Required Correction**:
  - **Risk**: Phantom external notifications or connection pool exhaustion.
  - **Required Correction**: Any notification, email, SMS, or event dispatch MUST be scheduled strictly post-commit (`after_commit` hook or background task queue). Under no circumstances shall network I/O occur within the atomic database transaction block.

---

## REVIEW 2 — POSTGRESQL ROW-LEVEL SECURITY (RLS)

### Finding 2.1: Verification of Referenced Tables & RLS Policies
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/alembic/versions/20261002_0002_multi_tenancy.py#L368-L411` and `apps/api/alembic/versions/20261010_0021_saas_platform_subscriptions.py#L270-L285`
* **Evidence from Source Inspection**:
  All referenced tables were inspected in their respective Alembic migration scripts:
  - `societies`: RLS NOT enabled (unscoped global root).
  - `users`: RLS NOT enabled (unscoped global identity).
  - `platform_subscription_plans`: RLS NOT enabled (unscoped global catalog).
  - `subscription_plan_entitlements`: RLS NOT enabled (unscoped global catalog).
  - `blocks`: `ENABLE ROW LEVEL SECURITY;` Policy `tenant_isolation_blocks` (`USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`).
  - `user_society_memberships`: `ENABLE ROW LEVEL SECURITY;` Policy `tenant_isolation_user_society_memberships` (`USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`).
  - `role_assignments`: `ENABLE ROW LEVEL SECURITY;` Policy `tenant_isolation_role_assignments` (`USING (scope_type = 'PLATFORM' OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`).
  - `audit_logs`: `ENABLE ROW LEVEL SECURITY;` Policy `tenant_isolation_audit_logs` (`USING (society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`).
  - `society_subscriptions`: `ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` Policy `society_subscriptions_tenant_isolation` (`USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`).
  - `society_feature_overrides`: `ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` Policy `society_feature_overrides_tenant_isolation`.
  - `society_quota_overrides`: `ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` Policy `society_quota_overrides_tenant_isolation`.
  - `society_usage_metrics`: `ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` Policy `society_usage_metrics_tenant_isolation`.
  - `society_provisioning_logs`: `ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` Policy `society_provisioning_logs_tenant_isolation`.
* **Risk & Required Correction**: None. Policies correctly filter on `app.current_society_id`.

### Finding 2.2: Enforcement of FORCE ROW LEVEL SECURITY & Non-Superuser Execution
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/alembic/versions/20261010_0021_saas_platform_subscriptions.py#L279-L280`
* **Evidence from Source Inspection**:
  - Migration 0021 explicitly runs `ALTER TABLE {table} FORCE ROW LEVEL SECURITY;` for all five subscription tenant tables.
  - In PostgreSQL, `FORCE ROW LEVEL SECURITY` mandates that RLS policies are applied even if the session is connected as the table owner.
  - The production database role (`societysphere_app`) is not granted `SUPERUSER` or `BYPASSRLS`. Therefore, RLS evaluation is strictly mandatory across all tenant table writes.
* **Risk & Required Correction**: None.

### Finding 2.3: Trusted Tenant-Context Mechanism & Client Injection Immunity
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/src/auth/dependencies.py#L129-L176` and `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-6.2`
* **Evidence from Source Inspection**:
  - The provisioning endpoint `/api/v1/platform/societies/provision` is guarded by `require_role("SUPER_ADMIN")` or `require_permission("platform:society:create")`.
  - The newly created `society_id` is NOT accepted from client input; it is generated server-side during Step 2 (`uuid.uuid4()`).
  - The server then directly sets this trusted, server-generated `society_id` into the transaction context. An untrusted client has zero ability to supply an arbitrary tenant ID to bypass isolation.
* **Risk & Required Correction**: None.

### Finding 2.4: Context Cleanup Across Commit, Rollback, and Connection Pooling
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/src/database/session.py#L54-L66` and `apps/api/src/core/tenant_context.py#L46-L54`
* **Evidence from Source Inspection**:
  - When transaction-local setting is used in PostgreSQL (`is_local = true`), the configuration parameter automatically reverts to its session-level default (`""`) as soon as the transaction commits or rolls back.
  - Python contextvars are managed via `set_current_tenant_id()` and reset via `reset_current_tenant_id(token)` inside a mandatory `finally:` block.
  - When connections are returned to the SQLAlchemy connection pool, no residual tenant context remains on the physical connection or the async worker task.
* **Risk & Required Correction**: None.

### Finding 2.5: Technically Correct Parameterized Tenant Setting in PostgreSQL: **FAIL (Correction Required)**
* **Finding Status**: **FAIL**
* **File Path & Location**: `apps/api/src/database/session.py#L65`
* **Evidence from Source Inspection & Live Testing**:
  - The current implementation in `session.py` attempts:
    ```python
    val = str(society_id) if society_id else ""
    await session.execute(text("SET LOCAL app.current_society_id = :val"), {"val": val})
    ```
  - In `tests/test_tenant_isolation.py#L162-L194`, this was tested solely using an `AsyncMock()` where the SQL string was checked with assertions, never executing on live PostgreSQL.
  - **Live PostgreSQL Execution Probe**:
    When executed against live PostgreSQL 16 Alpine via `asyncpg`, this raises:
    ```
    sqlalchemy.exc.ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) syntax error at or near "$1"
    [SQL: SET LOCAL app.current_society_id = $1]
    [parameters: ('11111111-1111-1111-1111-111111111111',)]
    ```
  - **Root Cause**: In PostgreSQL's SQL parser, utility statements (`SET`) do not support prepared statement bind variables (`$1`).
  - **Live Verification of Correct Alternative**:
    Executing `SELECT set_config('app.current_society_id', :val, true)` against live PostgreSQL 16 succeeded immediately and returned the assigned UUID cleanly:
    ```
    set_config result: 22222222-2222-2222-2222-222222222222
    ```
* **Risk & Required Correction**:
  - **Risk**: High. The provisioning engine will crash on Step 3 with `ProgrammingError` on live PostgreSQL.
  - **Required Correction**: `apps/api/src/database/session.py#L65` must be updated to use:
    ```python
    await session.execute(
        text("SELECT set_config('app.current_society_id', :val, true)"),
        {"val": str(society_id) if society_id else ""},
    )
    ```

---

## REVIEW 3 — ADVISORY LOCKS AND IDEMPOTENCY

### Finding 3.1: Advisory Lock Keys & Hash-Collision Safety
* **Finding Status**: **PASS**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-5.3`
* **Evidence from Source Inspection**:
  - The proposal employs two transactional advisory locks:
    1. `hashtext('idempotency:' || :idempotency_key)`
    2. `hashtext('society:' || lower(trim(:legal_name)))`
  - In PostgreSQL, `hashtext()` produces a signed 32-bit integer (`int4`).
  - **Collision Impact Analysis**:
    If two distinct keys hash to the same 32-bit integer, Transaction 2 will wait for Transaction 1 to complete (temporary serialization). Once Transaction 1 commits, Transaction 2 acquires the lock, executes its query against `society_provisioning_logs` and `societies` using the actual string keys, discovers no conflict, and proceeds.
  - **Conclusion**: Hash collisions on advisory locks cause brief execution latency, NOT data corruption or logical failure.
  - **Recommended Hardening**: To minimize the probability of false lock contention, use a 64-bit bigint lock:
    `pg_try_advisory_xact_lock(:int64_hash)`.

### Finding 3.2: Durable Duplicate-Prevention Constraints Audit
* **Finding Status**: **PASS WITH CONDITIONS**
* **File Path & Location**: `apps/api/alembic/versions/20261002_0002_multi_tenancy.py#L46-L68` and `apps/api/alembic/versions/20261010_0021_saas_platform_subscriptions.py#L125-L260`
* **Evidence from Source Inspection**:
  - `societies.legal_name`: Has **NO unique constraint** or unique index in Migration 0002.
  - `societies.registration_number`: Has an index (`ix_societies_registration_number`), but it is **NOT unique** (`unique=False`).
  - Other tables DO have durable unique constraints:
    * `society_subscriptions`: `uq_society_subscriptions_society_id` (Unique).
    * `society_usage_metrics`: `uq_society_usage_metric_key` (Unique on `society_id, metric_key`).
    * `user_society_memberships`: `uq_membership_user_society` (Unique on `user_id, society_id`).
    * `role_assignments`: `ix_role_assignments_user_society_role` (Unique index on `user_id, role_id, society_id`).
    * `users`: `ix_users_email` (Unique index on `email`).
* **Risk & Required Correction**:
  - **Risk**: Because `societies.legal_name` lacks a database unique constraint, database-level constraint enforcement cannot be the sole duplicate defense for society names.
  - **Required Correction**: The provisioning engine must serialize society creation using the advisory lock AND execute an explicit case-insensitive query (`WHERE lower(trim(legal_name)) = lower(trim(:name)) AND archived_at IS NULL`) inside the lock before inserting.

### Finding 3.3: Idempotency Payload Mutation Handling (RFC 9440)
* **Finding Status**: **CONDITIONS REQUIRED**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-5.2`
* **Evidence from Source Inspection**:
  - The proposal specifies that if an idempotency key is found in status `COMPLETED`, the cached society response is returned.
  - However, the proposal does not specify payload verification. If a client submits `idempotency_key = "abc-123"` with `plan_code="FREE"` and later re-submits `idempotency_key = "abc-123"` with `plan_code="ENTERPRISE"`:
    Returning the "FREE" society as if the "ENTERPRISE" request succeeded violates RFC 9440 idempotency semantics and creates billing discrepancies.
* **Risk & Required Correction**:
  - **Risk**: Silent acceptance of mutated payloads under reused idempotency keys.
  - **Required Correction**: The provisioning engine must compute `payload_hash = sha256(canonical_json(payload))`. If an existing completed key is encountered:
    * If `payload_hash` matches: return HTTP 200 OK with cached response.
    * If `payload_hash` differs: return **HTTP 422 Unprocessable Entity** with code `IDEMPOTENCY_PAYLOAD_MISMATCH`.

---

## REVIEW 4 — CONCURRENT REQUEST SEMANTICS

### Finding 4.1: Reconciliation of Lock Blocking vs. HTTP 409 Conflict
* **Finding Status**: **CONDITIONS REQUIRED**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-5.2` and `#Section-12.3`
* **Evidence from Source Inspection**:
  - The proposal claimed that concurrent in-progress requests return HTTP 409 Conflict, but proposed using `pg_advisory_xact_lock()`.
  - Under PostgreSQL, `pg_advisory_xact_lock()` is a **blocking** function. If Transaction 1 holds the lock, Transaction 2 blocks until Transaction 1 commits or rolls back.
  - Under `READ COMMITTED` isolation, Transaction 2 cannot observe Transaction 1's uncommitted rows while blocked. By the time Transaction 2 unblocks, Transaction 1 has committed, meaning Transaction 2 observes `status = 'COMPLETED'` and returns HTTP 200, never returning HTTP 409!
* **Risk & Required Correction**:
  - **Risk**: Concurrent requests block worker threads and connection pool slots for the full duration of provisioning (up to 15s) instead of failing fast.
  - **Required Correction**: The engine must use the **non-blocking** advisory lock function:
    ```sql
    SELECT pg_try_advisory_xact_lock(hashtext('idempotency:' || :key));
    ```
    If `pg_try_advisory_xact_lock()` returns `FALSE`, another worker is actively holding the lock. The transaction rolls back immediately and returns **HTTP 409 Conflict** with:
    * `code: "PROVISIONING_IN_PROGRESS"`
    * Header: `Retry-After: 5`

### Finding 4.2: Concurrency Matrix & State Resolution
* **Finding Status**: **PASS**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-7`
* **Evidence from Source Inspection**:
  The recommended behavior matrix resolves all client scenarios deterministically:

| Client Scenario | Database Lock State | Log State in DB | HTTP Status Code | Response Body / Headers |
| :--- | :--- | :--- | :--- | :--- |
| **First Submission** | `pg_try_advisory_xact_lock` = TRUE | None | **201 Created** | Full provisioned society response. |
| **Completed Replay** | Key exists in DB | `COMPLETED` | **200 OK** | Cached provisioned society response (`is_idempotent_replay: true`). |
| **Concurrent In-Progress** | `pg_try_advisory_xact_lock` = FALSE | In-flight / Not visible | **409 Conflict** | `code: "PROVISIONING_IN_PROGRESS"`, Header: `Retry-After: 5`. |
| **Replay with Mutated Body** | Key exists in DB | `COMPLETED` (hash mismatch) | **422 Unprocessable** | `code: "IDEMPOTENCY_PAYLOAD_MISMATCH"`. |
| **Previous Run Failed** | Key not in DB (rolled back) | No row (rolled back) | **201 Created** | Fresh provisioning executed cleanly. |

---

## REVIEW 5 — PHASE 21B INTEGRATION

### Finding 5.1: EntitlementService & QuotaEnforcementService Reuse
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/src/subscriptions/entitlement_service.py#L43-L80` and `apps/api/src/subscriptions/quota_enforcement_service.py#L38-L100`
* **Evidence from Source Inspection**:
  - `EntitlementService` and `QuotaEnforcementService` implemented in Phase 21B are fully reusable without modification.
  - `EntitlementService.get_effective_entitlement()` verifies that newly assigned subscription tiers resolve valid feature and quota entitlements.
  - In `apps/api/src/subscriptions/enums.py#L45-L52`, the canonical quota keys are strictly defined:
    * `QuotaKey.UNITS_MAX = "quota.units.max"`
    * `QuotaKey.RESIDENTS_MAX = "quota.residents.max"`
    * `QuotaKey.STAFF_MAX = "quota.staff.max"`
    * `QuotaKey.STORAGE_BYTES_MAX = "quota.storage.bytes.max"`
* **Risk & Required Correction**: None.

### Finding 5.2: Baseline Metric Initialization & Authorization Integrity
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/src/subscriptions/quota_enforcement_service.py#L72-L115`
* **Evidence from Source Inspection**:
  - `QuotaEnforcementService._get_or_init_metric_row()` expects rows in `society_usage_metrics` or initializes them on demand.
  - By inserting all four canonical metric keys with `current_value = 0` during provisioning Step 5 (`INIT_USAGE_METRICS`), the provisioning engine eliminates the possibility of insert collisions when downstream Phase 1–20 services first execute `reserve_usage()`.
  - Because Step 3 establishes `SET LOCAL app.current_society_id = :society_id`, inserting into `society_usage_metrics` fully satisfies the RLS policy:
    `USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)`.
* **Risk & Required Correction**: None.

---

## REVIEW 6 — SCHEMA AND MIGRATION AUDIT

### Finding 6.1: Verification of Schema Across Migrations 0001–0021
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/alembic/versions/20261002_0002_multi_tenancy.py` and `apps/api/alembic/versions/20261010_0021_saas_platform_subscriptions.py`
* **Evidence from Source Inspection**:
  Every table, column, index, foreign key, and constraint referenced by the proposal exists in the codebase:
  1. `societies`: Defined in Migration 0002. All 17 columns present (`onboarding_status`, `status`, `registration_number`, address columns).
  2. `users`: Defined in Migration 0002. All 13 columns present (`email`, `phone`, `password_hash`, `status`). Unique indexes on email/phone.
  3. `platform_subscription_plans`: Defined in Migration 0021. Seed plans (`FREE`, `STANDARD`, `ENTERPRISE`) populated.
  4. `subscription_plan_entitlements`: Defined in Migration 0021.
  5. `society_subscriptions`: Defined in Migration 0021. Unique on `society_id`.
  6. `society_usage_metrics`: Defined in Migration 0021. Unique on `(society_id, metric_key)`.
  7. `society_provisioning_logs`: Defined in Migration 0021. Columns `provisioning_request_id`, `step_key`, `status`, `started_at`, `completed_at`, `correlation_id`.
  8. `user_society_memberships`: Defined in Migration 0002. Unique on `(user_id, society_id)`.
  9. `role_assignments`: Defined in Migration 0002. Unique on `(user_id, role_id, society_id)`.
  10. `blocks`: Defined in Migration 0002. Unique on `(society_id, code)`.
  11. `audit_logs`: Defined in Migration 0002.
* **Risk & Required Correction**: None.

### Finding 6.2: Evaluation of Migration 0022 Requirement
* **Finding Status**: **PASS**
* **File Path & Location**: `apps/api/alembic/versions/`
* **Evidence from Source Inspection**:
  - Migration 0021 anticipated the provisioning lifecycle and already created `society_provisioning_logs` with all necessary step-tracking fields and indexes.
  - No new tables, altered columns, or additional database indexes are required.
* **Determination**: **MIGRATION 0022 IS GENUINELY UNNECESSARY.** Migrations 0001–0021 remain strictly unchanged.

---

## REVIEW 7 — FAILURE RECOVERY AND AUDITING

### Finding 7.1: Step-by-Step Failure Trace & Atomicity
* **Finding Status**: **PASS**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-8.1`
* **Evidence from Source Inspection**:
  If an exception occurs at any point during Steps 1 through 9:
  - An immediate `await session.rollback()` is invoked.
  - PostgreSQL transaction rollback reverts all uncommitted writes in reverse order.
  - The database is guaranteed to have 0 orphan rows in `societies`, `society_subscriptions`, `society_usage_metrics`, `user_society_memberships`, `role_assignments`, or `blocks`.
* **Risk & Required Correction**: None.

### Finding 7.2: Out-of-Band Failure Auditing Pattern
* **Finding Status**: **PASS**
* **File Path & Location**: `SOCIETYSHPERE_PHASE_21C_ARCHITECTURE_PROPOSAL.md#Section-8.2`
* **Evidence from Source Inspection**:
  - When `session.rollback()` reverts the main transaction, all in-transaction rows in `society_provisioning_logs` are reverted as well.
  - To preserve diagnostic evidence of failed attempts:
    In the `except Exception as exc:` block following rollback, the engine opens a dedicated, un-scoped audit write to `audit_logs`:
    * `society_id = None` (Permitted by policy `tenant_isolation_audit_logs`: `USING (society_id IS NULL OR ...)`).
    * `action = "SOCIETY_PROVISIONING_FAILED"`.
    * `entity_type = "society"`.
    * `entity_id = str(provisioning_request_id)`.
    * `actor_user_id = current_user.id`.
    * `after_state = {"error_type": exc.__class__.__name__, "failed_step": current_step_key}`.
* **Risk & Required Correction**: None.

### Finding 7.3: Credential Sanitization & Secret Redaction
* **Finding Status**: **PASS WITH CONDITIONS**
* **File Path & Location**: `apps/api/src/database/models/audit.py#L67-L78`
* **Evidence from Source Inspection**:
  - `audit_logs` records JSON payloads in `before_state` and `after_state`.
  - If a user password or activation token is generated during Step 6, it MUST NOT be written to `audit_logs`, `society_provisioning_logs`, or application logs.
* **Risk & Required Correction**:
  - **Risk**: Leaking credentials or plaintext tokens in audit logs.
  - **Required Correction**: Any generated password hash, raw credential, or authentication token must be explicitly stripped from audit logging dictionaries before inserting into `audit_logs`.

---

## CONDITIONS FOR IMPLEMENTATION AUTHORIZATION

The architecture proposal is **APPROVED WITH CONDITIONS**. Implementation of Phase 21C may proceed ONLY when the following four conditions are incorporated:

1. **Parameterization Correction in `session.py`**:
   In `apps/api/src/database/session.py`, replace `SET LOCAL app.current_society_id = :val` with:
   ```python
   await session.execute(
       text("SELECT set_config('app.current_society_id', :val, true)"),
       {"val": str(society_id) if society_id else ""},
   )
   ```
2. **Non-Blocking Advisory Lock Implementation**:
   Use `pg_try_advisory_xact_lock(hashtext('idempotency:' || :key))` to return HTTP 409 Conflict with `Retry-After: 5` immediately when another worker holds the lock, preventing connection pool starvation.
3. **Idempotency Payload Fingerprint Validation (RFC 9440)**:
   Compute `sha256(canonical_json(payload))`. If an existing idempotency key is submitted with a modified payload, return **HTTP 422 Unprocessable Entity** (`IDEMPOTENCY_PAYLOAD_MISMATCH`).
4. **Zero-RLS-Bypass & Migration Lock Adherence**:
   Strictly preserve existing Migrations `0001–0021`. No new migrations shall be created, and no database permissions granting `BYPASSRLS` shall be introduced.

---

## FINAL DETERMINATION

```
================================================================================
FINAL ARCHITECTURE REVIEW DETERMINATION:
  APPROVE WITH CONDITIONS
================================================================================
Phase 21C implementation may be authorized subject to incorporating the 4 conditions above.
No code implementation has begun. Awaiting explicit authorization to proceed.
================================================================================
```
