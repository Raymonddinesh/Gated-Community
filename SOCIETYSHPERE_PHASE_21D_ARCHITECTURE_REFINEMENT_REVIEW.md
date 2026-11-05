# SocietySphere Phase 21D Architecture Refinement & Security Gate Review

**Document ID:** `SOCIETYSPHERE-PHASE-21D-REV-001`  
**Date:** October 29, 2026  
**Reviewer:** Principal SaaS Architect, Distributed Concurrency & PostgreSQL Security Specialist  
**Status:** **COMPLETE — APPROVE WITH CONDITIONS**  
**Evaluation Scope:** Phase 21D Architecture Proposal (`SOCIETYSPHERE-PHASE-21D-ARCH-001`) against repository implementation (Phases 1–21C, Migrations 0001–0021).  
**Preceding Verifications:** Phase 21A (Approved), Phase 21B (PASS), Phase 21C (PASS).

---

## 1. Executive Summary & Verification Verdict

The architecture proposal for **Phase 21D: SaaS Platform Administration API** has undergone comprehensive read-only architectural and security verification against the production repository, database migrations (`0001`–`0021`), and PostgreSQL Row-Level Security (RLS) enforcement policies.

### Final Determination: **APPROVE WITH CONDITIONS**

Phase 21D implementation is conceptually sound and achieves its primary goal of zero database migrations. However, authorization to proceed with implementation is **strictly conditional** upon resolving two critical architectural discrepancies identified during verification:
1. **RLS Correction for Provisioning Logs**: The proposal incorrectly assumed `society_provisioning_logs` could be queried outside tenant RLS. Migration `0021` placed `society_provisioning_logs` under `FORCE ROW LEVEL SECURITY`. Diagnostic queries must execute within an explicit `tenant_context(society_id)` and `set_db_tenant_context(session, society_id)`.
2. **Strict Decoupling of Society and Subscription State Machines**: The proposal assumed society reactivation would automatically synchronize `SocietySubscription.status` to `ACTIVE`. This violates lifecycle independence. A society reactivation must **never** reactivate a `CANCELLED` subscription or bypass `PAST_DUE` commercial restrictions.

---

## 2. Review 1 — Platform Administrator Authorization

### 2.1 Threat Modeling & Authorization Guarantees
* **URL Society ID Isolation**: A society UUID in a path parameter (e.g. `/api/v1/platform/societies/{society_id}`) provides routing context only; it **never** grants access or establishes authorization.
* **Explicit Role Verification**: Platform endpoints reject any request lacking an authenticated session and an explicit platform-scoped role assignment:
  $$\text{User} \longrightarrow \text{RoleAssignment}(\text{scope\_type} = \text{'PLATFORM'}, \text{society\_id} = \text{NULL}) \longrightarrow \text{Role}(\text{code} = \text{'SUPER\_ADMIN'})$$
* **Tenant Sandboxing for Admins**: Platform administrators do not receive unrestricted bypass into tenant-owned operational data (units, payments, resident profiles). Administrative visibility is strictly confined to high-level metadata, subscription statuses, quota metrics, and provisioning diagnostics.
* **Safe Failure Modes**: Unauthenticated requests fail with `HTTP 401 Unauthorized` (`MISSING_CREDENTIALS` / `SESSION_REVOKED`). Authenticated users lacking `SUPER_ADMIN` (e.g., standard residents, society admins) fail with `HTTP 403 Forbidden` (`AUTHORIZATION_ERROR`). Non-existent society UUIDs fail with `HTTP 404 Not Found`.

### 2.2 Endpoint-by-Endpoint Authorization Matrix

| Endpoint | HTTP Method | Path Parameter | Required Role | Required Scope | RLS Strategy | Failure Codes |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **List Societies** | `GET` | None | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Unscoped (Global Table) | `401`, `403` |
| **Get Society Detail** | `GET` | `{society_id}` | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Unscoped (Global Table) | `401`, `403`, `404` |
| **Suspend Society** | `POST` | `{society_id}` | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Scoped via `tenant_context` for Subscriptions & Audit | `401`, `403`, `404`, `409` |
| **Reactivate Society** | `POST` | `{society_id}` | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Scoped via `tenant_context` for Subscriptions & Audit | `401`, `403`, `404`, `409` |
| **Subscription Overview** | `GET` | `{society_id}` | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Scoped via `tenant_context` (Phase 21B Services) | `401`, `403`, `404` |
| **Provisioning Diagnostics** | `GET` | `{society_id}` | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Scoped via `tenant_context` (`FORCE RLS`) | `401`, `403`, `404` |
| **Retry Provisioning** | `POST` | `{society_id}` | `SUPER_ADMIN` | `PLATFORM` (`society_id IS NULL`) | Engine-managed transaction & advisory locks | `401`, `403`, `404`, `409`, `422` |

---

## 3. Review 2 — Global Records and Tenant RLS Classification

### 3.1 Table Tenancy & Policy Inspection

| Model | Table Name | Migration Source | Tenancy Classification | RLS Status | RLS Policy Definition |
| :--- | :--- | :---: | :--- | :---: | :--- |
| `Society` | `societies` | `0002` (L46-65) | **Global Platform Data** | **DISABLED** | No RLS policy. Accessible globally across all tenants. |
| `SocietySubscription` | `society_subscriptions` | `0021` (L85-124) | **Tenant-Owned Data** | **FORCED** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` |
| `SocietyProvisioningLog` | `society_provisioning_logs` | `0021` (L233-285) | **Tenant-Owned Data** | **FORCED** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` |
| `AuditLog` | `audit_logs` | `0002` (L335-411) | **Hybrid (Platform / Tenant)** | **ENABLED** | `society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` |
| `SocietyUsageMetric` | `society_usage_metrics` | `0021` (L203-231) | **Tenant-Owned Data** | **FORCED** | `society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` |
| `RoleAssignment` | `role_assignments` | `0002` (L292-333) | **Hybrid (Platform / Tenant)** | **ENABLED** | `scope_type = 'PLATFORM' OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid` |
| `PlatformSubscriptionPlan` | `platform_subscription_plans` | `0021` (L23-50) | **Global Platform Catalog** | **DISABLED** | No RLS policy. Reference catalog data. |
| `SubscriptionPlanEntitlement`| `subscription_plan_entitlements` | `0021` (L51-83) | **Global Platform Catalog** | **DISABLED** | No RLS policy. Reference catalog data. |

### 3.2 Architectural Correction: Provisioning Diagnostics RLS
* **Identified Flaw in Initial Proposal**: The proposal assumed global queries on `society_provisioning_logs` could run outside tenant RLS.
* **Verified Database Reality**: In migration `0021` (lines 278–284), `society_provisioning_logs` is explicitly listed in `tenant_tables` with `FORCE ROW LEVEL SECURITY`. When `app.current_society_id` is unset or empty, PostgreSQL returns **0 rows** even to table owners and administrative queries.
* **Correction Required**: `get_provisioning_diagnostics` MUST establish tenant context:
  ```python
  async with tenant_context(society_id):
      await set_db_tenant_context(session, society_id)
      # Executes within target society sandbox under unprivileged app_user
      logs = await session.execute(
          select(SocietyProvisioningLog)
          .where(SocietyProvisioningLog.society_id == society_id)
          .order_by(SocietyProvisioningLog.started_at.asc())
      )
  ```
* **Zero Privilege Escalation**: No `SUPERUSER` or `BYPASSRLS` privileges are granted or required. The unprivileged database role (`app_user`) safely navigates tenant boundaries via transaction-local `set_config('app.current_society_id', :val, true)`.

---

## 4. Review 3 — Society and Subscription Lifecycle State Machines

### 4.1 Strict Decoupling Principle
`Society.status` and `SocietySubscription.status` serve completely separate domain purposes and must **never** be merged:
* `Society.status` governs **tenant application access**: whether residents, guards, and society committee members can resolve the tenant context and use the platform.
* `SocietySubscription.status` governs **commercial entitlement validity**: whether the tenant is in trial, active billing, past-due grace, or cancelled.

```
+-----------------------------------------------------------------------------------+
|                            SOCIETY LIFECYCLE (Access)                             |
|                                                                                   |
|                   +------------+        suspend()        +---------------+        |
|                   |   ACTIVE   | ----------------------> |   SUSPENDED   |        |
|                   +------------+ <---------------------- +---------------+        |
|                                       reactivate()                                |
+-----------------------------------------------------------------------------------+
                                          |
                                   (Independent)
                                          |
+-----------------------------------------------------------------------------------+
|                        SUBSCRIPTION LIFECYCLE (Billing)                           |
|                                                                                   |
|           +-----------+    billing    +------------+    non-payment   +----------+|
|           |   TRIAL   | ------------> |   ACTIVE   | ---------------> | PAST_DUE ||
|           +-----------+               +------------+                  +----------+|
|                 |                           |                               |     |
|                 +---------------------------+-------------------------------+     |
|                                             |                                     |
|                                             v cancel()                            |
|                                     +---------------+                             |
|                                     |   CANCELLED   | (Terminal)                  |
|                                     +---------------+                             |
+-----------------------------------------------------------------------------------+
```

### 4.2 Comprehensive Lifecycle Interaction Matrix

| Current Society Status | Current Subscription Status | Proposed Admin Operation | Permitted? | Resulting Society Status | Resulting Subscription Status | Invariant & Justification |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `ACTIVE` | `ACTIVE` | `suspend` | **YES** | `SUSPENDED` | `ACTIVE` (or `suspended_at` timestamp recorded) | Tenant access blocked immediately. Commercial subscription remains intact. |
| `SUSPENDED` | `ACTIVE` | `reactivate` | **YES** | `ACTIVE` | `ACTIVE` | Tenant access restored. Subscription continues normally. |
| `ACTIVE` | `TRIAL` | `suspend` | **YES** | `SUSPENDED` | `TRIAL` | Tenant access blocked. Trial continues clocking or remains frozen. |
| `SUSPENDED` | `TRIAL` | `reactivate` | **YES** | `ACTIVE` | `TRIAL` | Tenant access restored. Entitlement service evaluates `trial_ends_at`. |
| `ACTIVE` | `PAST_DUE` | `suspend` | **YES** | `SUSPENDED` | `PAST_DUE` | Administrative freeze following non-payment notices. |
| `SUSPENDED` | `PAST_DUE` | `reactivate` | **YES** | `ACTIVE` | **`PAST_DUE`** | **CRITICAL**: Reactivation does NOT clear past-due debt or bypass restriction. |
| `ACTIVE` | `CANCELLED` | `suspend` | **YES** | `SUSPENDED` | `CANCELLED` | Administrative freeze of an offboarded society. |
| `SUSPENDED` | `CANCELLED` | `reactivate` | **YES** | `ACTIVE` | **`CANCELLED`** | **CRITICAL**: Reactivation does NOT purchase a new plan. Features remain fail-closed (0 limits). |
| `ACTIVE` | Any | `reactivate` | **NO** | `ACTIVE` | Unchanged | **409 Conflict**: `SOCIETY_ALREADY_ACTIVE`. |
| `SUSPENDED` | Any | `suspend` | **NO** | `SUSPENDED` | Unchanged | **409 Conflict**: `SOCIETY_ALREADY_SUSPENDED`. |

### 4.3 Concurrency & Transactional Invariants
1. **Row Locks**: Status mutations must execute inside an ACID transaction utilizing pessimistic row locks:
   ```sql
   SELECT id, status FROM societies WHERE id = :society_id FOR UPDATE;
   ```
2. **Mandatory Justification**: `reason` string must have a minimum length of 10 non-whitespace characters.
3. **Audit Immutability**: All status transitions emit an append-only `AuditLog` entry recording `actor_user_id`, `before_state`, `after_state`, `diff`, and administrative `reason`.

---

## 5. Review 4 — Provisioning Retry Eligibility & Idempotency

### 5.1 Retry State Evaluation

| Provisioning State | Onboarding Status | Retry Eligible? | HTTP Response | Mechanism & Safety |
| :--- | :--- | :---: | :---: | :--- |
| **Completed** | `COMPLETED` | **NO** | `409 Conflict` | Engine checks `AuditLog` or `Society.onboarding_status == 'COMPLETED'`. Returns `PROVISIONING_ALREADY_COMPLETED`. |
| **In Progress** | `IN_PROGRESS` | **NO** | `409 Conflict` | `pg_try_advisory_xact_lock` fails. Returns `CONCURRENT_PROVISIONING_IN_PROGRESS` with `Retry-After: 5`. |
| **Failed (Rolled Back)**| None / `FAILED` | **YES** | `201 Created` | Prior transaction completely rolled back. Zero orphaned entities exist. Retrying runs standard 9-step atomic engine. |
| **Permanent Validation Failure**| Rejected | **NO** | `422 Unprocessable` / `400 Bad Request` | Input schema or reference catalog error (e.g., non-existent plan code). Cannot retry without corrected payload. |

### 5.2 Prevention of Duplicate Entities
Because Phase 21C implemented the complete 9-step provisioning lifecycle inside a single PostgreSQL transaction:
* Any step failure triggers `session.rollback()`.
* No partial rows in `societies`, `blocks`, `units`, `user_society_memberships`, `role_assignments`, `society_subscriptions`, or `society_usage_metrics` survive the failure.
* Retrying executes against a clean slate. Unique constraints (`uq_society_subscriptions_society_id`, `uq_society_usage_metric_key`, `uq_membership_user_society`) provide kernel-level duplicate prevention.
* In-flight collisions are blocked by non-blocking 64-bit advisory locks (`pg_try_advisory_xact_lock`).

---

## 6. Review 5 — Zero-Migration Verification

Every database operation, query, filter, sort, and foreign-key relation in Phase 21D was cross-referenced against Alembic migrations `0001` through `0021`.

### Verification Findings:
* **`societies`** (Migration `0002`): Columns `id`, `legal_name`, `display_name`, `registration_number`, `status`, `onboarding_status`, `city`, `state`, `postal_code`, `created_at`, `updated_at`, `archived_at` fully exist.
* **`society_subscriptions`** (Migration `0021`): Columns `id`, `society_id`, `plan_id`, `status`, `starts_at`, `trial_ends_at`, `current_period_start`, `current_period_end`, `past_due_since`, `suspended_at`, `cancelled_at`, `cancellation_reason` fully exist.
* **`society_provisioning_logs`** (Migration `0021`): Columns `id`, `society_id`, `provisioning_request_id`, `step_key`, `status`, `message`, `correlation_id`, `started_at`, `completed_at` fully exist.
* **`audit_logs`** (Migration `0002`): Columns `id`, `society_id`, `actor_user_id`, `action`, `entity_type`, `entity_id`, `request_id`, `correlation_id`, `before_state`, `after_state`, `diff`, `created_at` fully exist.
* **`role_assignments`** (Migration `0002`): Columns `id`, `user_id`, `role_id`, `society_id`, `scope_type`, `assigned_at`, `status` fully exist.

**Conclusion**: **ZERO MIGRATIONS REQUIRED**. Creating migration `0022` is completely unnecessary and forbidden.

---

## 7. Review 6 — Final Acceptance Gate & Test Plan

### 7.1 Mandatory Implementation Conditions

> [!IMPORTANT]
> **Condition 1 (Provisioning Diagnostics RLS Binding)**:  
> `get_provisioning_diagnostics` MUST establish `tenant_context(society_id)` and `set_db_tenant_context(session, society_id)` prior to querying `society_provisioning_logs`.

> [!IMPORTANT]
> **Condition 2 (Lifecycle State Decoupling)**:  
> Society suspend/reactivate actions must NOT automatically overwrite `SocietySubscription.status`. Reactivating an administratively suspended society MUST preserve `CANCELLED` and `PAST_DUE` commercial states.

> [!IMPORTANT]
> **Condition 3 (Advisory Lock Serialization)**:  
> Provisioning retries and lifecycle state mutations must utilize transaction-local advisory locks (`pg_try_advisory_xact_lock`) or pessimistic row locks (`FOR UPDATE`) to prevent concurrent race conditions.

> [!IMPORTANT]
> **Condition 4 (Zero Migration Integrity)**:  
> Do not modify migrations `0001`–`0021`. Do not create migration `0022`.

### 7.2 Required Test Coverage Suite
1. **Unit & Fast Integration Tests** (`tests/test_phase21d_platform_admin.py`):
   * Authentication & Role Enforcement: 401 when unauthenticated, 403 when authenticated as Resident / Society Admin, 200 when `SUPER_ADMIN`.
   * Directory Filtering & Pagination: Search by name, filter by status, sorting by `created_at`.
   * Lifecycle Invariants:
     * `ACTIVE` $\rightarrow$ `SUSPENDED` with audit emission.
     * `SUSPENDED` $\rightarrow$ `ACTIVE` with audit emission.
     * Duplicate suspension returns 409 Conflict.
     * Duplicate reactivation returns 409 Conflict.
     * Reactivating a society with a `CANCELLED` subscription keeps the subscription `CANCELLED`.
     * Reactivating a society with a `PAST_DUE` subscription keeps the subscription `PAST_DUE`.
     * Short reason (< 10 chars) rejected with 422/400.
   * Provisioning Diagnostics: Correct step ordering and error sanitization.
   * Subscription Overview: Correct delegation to `EntitlementService` and `QuotaEnforcementService`.
2. **Live PostgreSQL 16 Concurrency & RLS Tests** (`tests/test_phase21d_platform_admin_concurrency_pg.py`):
   * Multi-session concurrency test: Concurrent suspension requests against the same society serialize on `FOR UPDATE`; exactly one succeeds (200), other fails with 409 Conflict.
   * Multi-session retry test: Concurrent retry requests serialize on advisory lock; one runs, second receives 409 Conflict with `Retry-After`.
   * Unprivileged `app_user` RLS verification: Verifies `society_provisioning_logs` and `society_subscriptions` cannot be read without `app.current_society_id`.
   * Connection pool cleanup test: Verifies `app.current_society_id` does not leak across pooled sessions.

---

## 8. Formal Gate Recommendation

### Verdict: **APPROVE WITH CONDITIONS**
Implementation of Phase 21D (SaaS Platform Administration API) may be authorized subject to the strict adherence to the four mandatory conditions outlined in Section 7.1.
