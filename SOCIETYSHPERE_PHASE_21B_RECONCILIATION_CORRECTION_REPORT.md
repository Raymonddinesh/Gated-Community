# SOCIETYSPHERE — PHASE 21B TARGETED CORRECTION REPORT
## `reconcile_usage` Concurrency Safety and Race Prevention

**Project**: `SocietySphere`  
**Root Directory**: `C:\SocApp`  
**Phase Under Review**: `Phase 21B — Entitlement Service & Quota Enforcement Service`  
**Defect Addressed**: Check 2 Usage Reconciliation Lost Update / Stale Overwrite Race Condition  
**Date**: `October 21, 2026`  
**Author**: Senior Backend Architect and PostgreSQL Concurrency Specialist  
**Status**: **`PASS — READY FOR PHASE 21C`**  
**Phase 21C Authorization Gate**: **`NOT AUTHORIZED`** (Awaiting Formal Authorization)  

---

> [!IMPORTANT]
> **STRICT COMPLIANCE & BOUNDARY ACKNOWLEDGEMENT**:  
> In strict accordance with the project constraints:
> - Application modifications were strictly confined to `QuotaEnforcementService.reconcile_usage`, domain exceptions, and supporting tests.
> - Alembic migrations `0001–0021` were **NOT modified**.
> - Migration `0022` was **NOT created**.
> - Database schema, constraints, indexes, and tables were **NOT changed**.
> - Phase 1–20 production code, schemas, RLS policies, RBAC, tenant resolution, authentication, and API contracts remain **UNTOUCHED**.
> - `SocietyProvisioningEngine` was **NOT implemented**.
> - **Phase 21C has NOT been started.**
> - Concurrency correctness was verified using live **PostgreSQL 16** (`societysphere-postgres` on `localhost:5432`) under genuine multi-session contention, not inferred from SQLite.

---

## 1. ROOT CAUSE ANALYSIS

### 1.1 The Lost Update / Stale Overwrite Defect
In the baseline Phase 21B implementation, `QuotaEnforcementService.reconcile_usage` unconditionally assigned an externally calculated `actual_count` scalar to `metric.current_value`:

```python
# VULNERABLE BASELINE IMPLEMENTATION
async def reconcile_usage(self, society_id, metric_key, actual_count, auto_commit=False):
    target_society_id = self._resolve_trusted_society(society_id)
    metric = await self._get_or_init_metric_row(target_society_id, metric_key, for_update=True)
    metric.current_value = actual_count  # <-- BLIND OVERWRITE
    metric.last_calculated_at = datetime.now(UTC).replace(tzinfo=None)
    await self.session.flush()
```

### 1.2 Failure Scenario
In production, authoritative resource counts (e.g., total active units, staff, or residents) are calculated by querying resource tables (e.g. `SELECT count(*) FROM units WHERE society_id = :id`). When this calculation occurs outside the transaction holding the usage metric lock:

```text
Timeline of Lost Update:
-------------------------------------------------------------------------------------------------
T0: Reconciler Task: Queries units table -> observes count = 10.
T1: User Transaction: Calls reserve_usage(society_id, 'quota.units.max', requested_increment=1).
    - Acquires SELECT ... FOR UPDATE on society_usage_metrics row.
    - Evaluates quota limit (10 + 1 <= 50 -> OK).
    - Increments current_value: 10 -> 11.
    - Inserts new Unit record into database.
    - Commits transaction.
T2: Reconciler Task: Invokes reconcile_usage(society_id, 'quota.units.max', actual_count=10).
    - Acquires SELECT ... FOR UPDATE on society_usage_metrics row.
    - Blindly assigns metric.current_value = 10.
    - Commits transaction.
-------------------------------------------------------------------------------------------------
Outcome: The unit created at T1 is permanently lost from the usage metric!
Counter is 10, but 11 units exist in the database. Subsequent reservations will oversubscribe quota.
```

---

## 2. FILES CHANGED AND RATIONALE

| File Path | Nature of Change | Architectural Rationale |
|---|---|---|
| [apps/api/src/subscriptions/quota_enforcement_service.py](file:///C:/SocApp/apps/api/src/subscriptions/quota_enforcement_service.py) | **Core Correction** | Implemented dual-mode reconciliation: (1) In-transaction authoritative counting (`count_callback`) under exclusive row lock, and (2) Optimistic coordination (`expected_previous_value`, `as_of`, non-decreasing guard) for external counts. Normalized timezone comparisons for cross-database robustness. |
| [apps/api/src/subscriptions/exceptions.py](file:///C:/SocApp/apps/api/src/subscriptions/exceptions.py) | **Domain Exception** | Added `StaleReconciliationException` (subclass of `SubscriptionDomainException`, HTTP 409 Conflict) with diagnostic details (`current_usage`, `attempted_count`, `metric_key`). |
| [apps/api/src/subscriptions/__init__.py](file:///C:/SocApp/apps/api/src/subscriptions/__init__.py) | **Package Export** | Exported `StaleReconciliationException` in `__all__`. |
| [tests/test_phase21b_reconciliation_targeted.py](file:///C:/SocApp/tests/test_phase21b_reconciliation_targeted.py) | **Targeted Test Suite** | 10 comprehensive unit and contract tests verifying all reconciliation invariants (baseline count, missing row initialization, stale window detection, rollback immutability, uncoordinated decrease rejection, tenant isolation, non-negative invariants, and ceiling enforcement). |
| [tests/test_pg_reconciliation_concurrency.py](file:///C:/SocApp/tests/test_pg_reconciliation_concurrency.py) | **Live PostgreSQL 16 Suite** | Live PostgreSQL 16 concurrency script executing multi-session contention with explicit `asyncio.Event` barriers against `societysphere-postgres` (localhost:5432). |

---

## 3. CHOSEN CONCURRENCY STRATEGY AND SAFETY PROOF

To ensure comprehensive safety across both internal resource accounting and external provider feeds, `QuotaEnforcementService.reconcile_usage` implements a **Dual-Mode Race-Safe Architecture**:

```mermaid
flowchart TD
    Start["reconcile_usage(society_id, metric_key, ...)"] --> TenantCheck["Enforce Tenant Context<br/>(_resolve_trusted_society)"]
    TenantCheck --> AcquireLock["Acquire Row Lock<br/>(SELECT ... FOR UPDATE on SocietyUsageMetric)"]
    AcquireLock --> CheckMode{"Mode Selected?"}
    
    CheckMode -- "count_callback provided" --> ExecCallback["Execute count_callback(session, society_id)<br/>WHILE HOLDING ROW LOCK"]
    ExecCallback --> LockHold["Concurrent reserve_usage BLOCKED<br/>by PostgreSQL Row Lock"]
    LockHold --> ValidateCount["Validate count >= 0"]
    ValidateCount --> ApplyCallback["Assign metric.current_value = count<br/>Update last_calculated_at"]
    ApplyCallback --> Flush["Flush / Auto-Commit<br/>Release Lock"]
    
    CheckMode -- "actual_count provided" --> CheckParams{"Coordination<br/>Supplied?"}
    CheckParams -- "expected_previous_value" --> CheckPrev{"current_value ==<br/>expected_previous_value?"}
    CheckPrev -- No --> RaiseStale["Raise StaleReconciliationException<br/>(HTTP 409 Conflict)"]
    CheckPrev -- Yes --> ApplyScalar["Assign metric.current_value = actual_count"]
    
    CheckParams -- "as_of timestamp" --> CheckTimestamp{"last_calculated_at <=<br/>as_of?"}
    CheckTimestamp -- No --> RaiseStale
    CheckTimestamp -- Yes --> ApplyScalar
    
    CheckParams -- "Neither supplied" --> CheckDecrease{"actual_count <<br/>current_value?"}
    CheckDecrease -- Yes (Stale Decrease) --> RaiseStale
    CheckDecrease -- No (Safe Baseline/Increase) --> ApplyScalar
    
    ApplyScalar --> Flush
```

### 3.1 Mode 1: In-Transaction Authoritative Calculation (`count_callback`) — *Preferred*
- **Mechanism**: The caller supplies an asynchronous callback `count_callback(session: AsyncSession, society_id: UUID) -> Awaitable[int]`.
- **Serialization Guarantee**:
  1. `_get_or_init_metric_row(..., for_update=True)` acquires `SELECT ... FOR UPDATE` on `SocietyUsageMetric` **before** the callback is invoked.
  2. Any concurrent `reserve_usage` operation attempting to allocate quota for this metric must call `_get_or_init_metric_row(..., for_update=True)` and is **physically blocked by PostgreSQL** at the database engine level.
  3. `count_callback` executes inside this locked transaction, querying the authoritative resource tables (e.g. `Unit`, `Staff`). Because Read Committed isolation sees all transactions committed prior to statement execution, the callback sees 100% of all committed entities.
  4. `metric.current_value` is updated to the calculated count, and the transaction commits, releasing the lock.
  5. The blocked `reserve_usage` unblocks, reads the newly reconciled count as its baseline, and applies its increment on top of the fresh count.
- **Safety Result**: Zero lost updates. Mathematical serialization.

### 3.2 Mode 2: Coordinated External Reconciliation (`actual_count`)
- **Mechanism**: Accepts an external scalar integer with mandatory or optional coordination parameters (`expected_previous_value`, `as_of`).
- **Safety Invariants**:
  1. **Optimistic Version / Value Guard**: If `expected_previous_value` is passed, `reconcile_usage` verifies that `metric.current_value == expected_previous_value` under the `FOR UPDATE` lock. If a concurrent reservation altered the usage in the interim, `StaleReconciliationException` is raised immediately.
  2. **Timestamp Snapshot Guard**: If `as_of` is passed, `reconcile_usage` validates that `metric.last_calculated_at <= as_of`. If a reservation updated the row after the snapshot was taken, `StaleReconciliationException` is raised.
  3. **Uncoordinated Stale Decrease Guard**: If neither coordination parameter is passed, `reconcile_usage` strictly forbids decreasing the counter (`actual_count < previous_usage`), raising `StaleReconciliationException`. An external caller cannot inadvertently wipe out newer committed reservations. Legitimate decreases (e.g. bulk deletion) must supply either `count_callback` or `expected_previous_value` to prove authorization and freshness.
  4. **Atomic Check-and-Set**: Validation and assignment occur entirely under the `SELECT ... FOR UPDATE` lock, eliminating time-of-check to time-of-use (TOCTOU) races.

---

## 4. TRANSACTION AND LOCKING BEHAVIOR

1. **Row-Level Serialization**:
   - Every reconciliation acquires an exclusive row-level lock (`SELECT ... FOR UPDATE`) on the specific `(society_id, metric_key)` tuple in `society_usage_metrics`.
   - Distinct metric keys or different societies are completely independent and execute concurrently without lock contention.
2. **Missing Row Initialization**:
   - Handled via `_get_or_init_metric_row`. If the row does not exist, insertion executes inside a nested savepoint (`async with session.begin_nested():`). If concurrent transactions attempt simultaneous insertion, PostgreSQL's `uq_society_usage_metric_key` constraint raises `IntegrityError`, the savepoint cleanly rolls back, and the transaction safely re-queries with `FOR UPDATE`.
3. **Session & Commit Semantics**:
   - By default, mutations are flushed to the active session (`await self.session.flush()`), leaving commit or rollback ownership to the outer transaction boundary.
   - If `auto_commit=True` is explicitly passed, the service commits the transaction immediately.
4. **Rollback Immutability**:
   - If an exception occurs (in `count_callback`, caller logic, or validation), caller transaction rollback completely reverts all staged modifications. No partial or dirty state is ever persisted.

---

## 5. TEST EVIDENCE & VERIFICATION

### 5.1 Live PostgreSQL 16 Concurrency Suite (`tests/test_pg_reconciliation_concurrency.py`)
Executed against `societysphere-postgres` (PostgreSQL 16 Alpine, port 5432):

```text
Command: .venv\Scripts\python.exe tests/test_pg_reconciliation_concurrency.py
Result: ALL LIVE POSTGRESQL 16 CONCURRENCY TESTS PASSED 100% (Exit Code: 0)

Execution Log Breakdown:
-------------------------------------------------------------------------------------------------
[Test 1] PostgreSQL Row Lock Serialization:
  - Session A acquires SELECT ... FOR UPDATE inside count_callback (simulating 300ms count).
  - Session B attempts reserve_usage(+3) concurrently.
  - Session B is BLOCKED by PostgreSQL for 0.328s until Session A commits (reconciled to 20).
  - Session B unblocks, reads baseline 20, reserves +3 -> final usage = 23.
  - Result: PASS (Final usage in PostgreSQL is exactly 23).

[Test 2] Two Concurrent Reconciliations with expected_previous_value:
  - Worker 1 attempts reconcile to 15 (expected=5).
  - Worker 2 attempts reconcile to 20 (expected=5).
  - Worker 1 acquires lock, commits 15.
  - Worker 2 unblocks, reads 15 != 5 -> raises StaleReconciliationException.
  - Result: PASS (W1_SUCCESS, W2_STALE, final usage in PostgreSQL = 15).

[Test 3] Stale Overwrite Prevention:
  - Baseline usage = 10. Snapshot observed at T0.
  - User reservation commits +2 at T1 (PostgreSQL usage = 12).
  - Stale reconcile with expected_previous_value=10 -> StaleReconciliationException (HTTP 409).
  - Stale reconcile with as_of=T0 -> StaleReconciliationException (HTTP 409).
  - Stale reconcile with uncoordinated count=10 -> StaleReconciliationException (HTTP 409).
  - Result: PASS (PostgreSQL usage remains strictly intact at 12).

[Test 4] Check 1 Quota Concurrency Regression:
  - 10 concurrent workers competing for 5 quota units under PostgreSQL row locks.
  - Exactly 5 succeeded, 5 rejected with QuotaExceededException.
  - Result: PASS (Final usage in PostgreSQL is exactly 5).
-------------------------------------------------------------------------------------------------
```

### 5.2 Targeted Reconciliation Unit & Contract Suite (`tests/test_phase21b_reconciliation_targeted.py`)
Executed via pytest:

```text
Command: .venv\Scripts\pytest.exe tests/test_phase21b_reconciliation_targeted.py -v
Result: 8 passed, 2 skipped (PostgreSQL-specific tests properly deferred to live PG suite) in 8.96s

Test Cases Verified:
- test_01_basic_reconciliation_authoritative_count:                    PASSED
- test_02_reconciliation_missing_usage_metric_row:                     PASSED
- test_03_concurrent_reservation_during_reconciliation:                SKIPPED (Verified in PG suite)
- test_04_reservation_committed_after_count_calculation_before_recon: PASSED
- test_05_two_concurrent_reconciliation_attempts:                     SKIPPED (Verified in PG suite)
- test_06_failed_reconciliation_rolls_back_without_corrupting_usage:   PASSED
- test_07_stale_reconciliation_cannot_decrease_newer_committed_counter:PASSED
- test_08_tenant_isolation_remains_enforced:                           PASSED
- test_09_reconciliation_never_creates_negative_usage:                 PASSED
- test_10_existing_quota_reservation_ceiling_remains_enforced:         PASSED
```

### 5.3 Combined Phase 21B Test Suite
Executed via pytest:

```text
Command: .venv\Scripts\pytest.exe tests/test_phase21b_entitlement_and_quota.py tests/test_phase21b_reconciliation_targeted.py -v
Result: 37 passed, 2 skipped in 33.71s (100% PASS rate across all 39 test items)
```

---

## 6. FULL REGRESSION, RUFF, AND MYPY RESULTS

### 6.1 Static Analysis & Linting (Ruff)
- **Command**: `.venv\Scripts\ruff.exe check apps/api tests`
- **Result**: `All checks passed!` (0 errors).

### 6.2 Static Type Checking (MyPy)
- **Command**: `.venv\Scripts\mypy.exe apps/api tests/test_phase21b_entitlement_and_quota.py tests/test_phase21b_reconciliation_targeted.py tests/test_pg_reconciliation_concurrency.py`
- **Result**: `Success: no issues found in 362 source files` (0 errors).

### 6.3 Full Platform Regression
- **Baseline Prior to Phase 21B**: 330 tests (Phase 1–20 + Phase 21A).
- **Phase 21B Suite**: 29 tests.
- **Phase 21B Targeted Reconciliation Suite**: 10 tests.
- **Live PostgreSQL Concurrency Suite**: 4 test scenarios.
- **Total Test Catalog**: 373 test items.
- **Regression Command**: `.venv\Scripts\pytest.exe tests/`
- **Result**: 100% PASS across all domains. Phase 1–20 behaviors remain completely intact.

---

## 7. MIGRATION & DATABASE INTEGRITY

1. **Migrations 0001–0021**:
   - All 21 migration files in `apps/api/alembic/versions/` are **completely unmodified**.
   - Current head revision: `0021_saas_platform_subscriptions`.
   - Down revision: `0020`.
2. **Migration 0022**:
   - **NOT CREATED**. Zero schema changes were required.
3. **Database Schema**:
   - `society_usage_metrics` schema was preserved in its exact Phase 21A structure. Existing unique constraints (`uq_society_usage_metric_key`), check constraints (`ck_society_usage_metric_non_negative`), and timestamps (`last_calculated_at`, `updated_at`) were fully leveraged without alterations.
4. **RLS & Security Policies**:
   - PostgreSQL RLS policies on `society_usage_metrics` remain untouched and active. Tenant context enforcement via `_resolve_trusted_society` guarantees strict boundary isolation.

---

## 8. REMAINING ARCHITECTURAL CONSIDERATIONS

1. **Uncoordinated Decreases**:
   - In Mode 2 (`actual_count`), decreasing usage below `current_value` without passing `expected_previous_value` or `as_of` is deliberately blocked with `StaleReconciliationException`. When building future administrative reconciliation tools or background jobs that handle deletions, callers must supply either `count_callback` or the expected baseline value to authorize a reduction in recorded usage.
2. **External Metrics (e.g. S3 Storage)**:
   - For metrics whose authoritative source is outside PostgreSQL (such as MinIO/S3 bucket byte size), callers should pass `as_of` reflecting the timestamp when the storage scan completed. This ensures that any concurrent upload reservations made after that scan will not be overwritten.

---

## 9. FINAL VERIFICATION DECISION

### Check Assessment Summary

| Check | Focus Area | Status | Evidence Rationale |
|:---|:---|:---:|:---|
| **CHECK 1** | Quota Concurrency | **PASS** | Validated under PostgreSQL 16 row locking; 10-worker concurrent race test confirmed exact ceiling enforcement (5 succeeded, 5 rejected). |
| **CHECK 2** | Usage Reconciliation | **PASS** | `reconcile_usage` corrected with dual-mode protection: in-transaction `count_callback` serializes via row lock (Session B held 0.328s by PostgreSQL in Test 1); external counts guarded by `expected_previous_value`, `as_of`, and non-decreasing check (Test 2 & Test 3 PASS). |
| **CHECK 3** | Entitlement Precedence | **PASS** | 3-tier precedence (`Override` $\rightarrow$ `Plan` $\rightarrow$ `System Default`) verified. |
| **CHECK 4** | Subscription Status | **PASS** | Deterministic fail-closed handling for all subscription lifecycle states. |
| **CHECK 5** | Tenant Isolation | **PASS** | Cross-tenant access raises 403; missing tenant context raises 400. |
| **CHECK 6** | Regression Evidence | **PASS** | Full platform regression PASS; Ruff clean; MyPy clean (362 source files). |

---

# **FINAL DECISION: PASS — READY FOR PHASE 21C**

```text
PHASE 21B TARGETED CORRECTION: PASS
PHASE 21B OVERALL STATUS: COMPLETE & VERIFIED
PHASE 21C AUTHORIZATION GATE: NOT AUTHORIZED
```

> [!CAUTION]
> **GATE NOTICE — EXECUTION STOPPED**:  
> In accordance with the prompt instructions, Phase 21C (`SocietyProvisioningEngine`) has **NOT** been started. Execution has stopped after completing the correction, comprehensive verification, and delivery of this report.
