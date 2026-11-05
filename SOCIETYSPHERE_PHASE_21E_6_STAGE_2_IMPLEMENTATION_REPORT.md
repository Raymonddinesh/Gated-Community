# SocietySphere Phase 21E.6 — Stage 2: Dunning Engine & Grace Period Suspension Automation
## Formal Implementation Report

**Author**: Principal SaaS Architect, Senior Backend Engineer & Application Security Specialist  
**Date**: November 3, 2026  
**Status**: APPROVED & IMPLEMENTED  
**Alembic Head**: `0025_saas_billing_automation` (Zero schema migrations added)  
**Execution Environment**: Python 3.11.0, PostgreSQL 16 (Port 5432)

---

## 1. Executive Summary

Phase 21E.6 Stage 2 delivers the enterprise-grade automated dunning and subscription suspension engine for SocietySphere SaaS. It operationalizes a strict 7-day grace period anchored immutably to `SocietySubscription.past_due_since`, evaluates escalating reminder milestones across omnichannel communication channels (Email, In-App, SMS, WhatsApp), executes authoritative subscription suspensions at Day 7 grace expiry via `SubscriptionLifecycleService`, enforces zero-compromise late payment recovery provenance verification via `PaymentSettlementService`, and guarantees multi-worker horizontal concurrency and tenant isolation via `SELECT ... FOR UPDATE SKIP LOCKED`, 64-bit PostgreSQL transaction-scoped advisory locks, and PostgreSQL 16 `FORCE ROW LEVEL SECURITY`.

### Key Technical Achievements
1. **Immutable Grace Period Anchor**: All dunning stages (`DAY_0_REMINDER`, `DAY_2_REMINDER`, `DAY_5_WARNING`, `DAY_7_SUSPENSION`) calculate duration strictly against `sub.past_due_since` in UTC. Repeated scheduler or dunning runs never modify, extend, or reset `past_due_since`.
2. **Deterministic Idempotency**: Dunning attempts enforce unique idempotency keys formatted as `dunning:{subscription_id}:{invoice_id}:{stage}`. Re-executions within the same milestone return `SKIPPED` (`STAGE_ALREADY_EXECUTED`) with zero duplicate attempts and zero duplicate notifications.
3. **Pessimistic Suspension Guard & Settlement Verification**: Before transitioning an overdue subscription to `SUSPENDED` at Day 7, the engine checks for captured payments awaiting settlement (`PlatformPayment.status == 'CAPTURED', is_settled == False`). If an in-flight payment exists, suspension is bypassed (`PAYMENT_SETTLEMENT_PENDING`), preventing erroneous lockouts.
4. **Mandatory Late Payment Recovery Provenance Check**: In `PaymentSettlementService`, a late payment on a `SUSPENDED` subscription restores `ACTIVE` status **if and only if** provenance verification confirms the suspension was triggered by the automated dunning engine on the settled invoice (authoritative `PlatformSubscriptionHistory` transition reason starting with `DUNNING_` and unprivileged actor, paired with a matching `PlatformDunningAttempt`). Administrative suspensions (e.g., fraud, TOS violations) are strictly preserved as `SUSPENDED`.
5. **Decoupled Society Domain State**: Throughout all dunning reminder dispatches and Day 7 subscription suspension executions, `Society.status` remains strictly untouched (`ACTIVE`). Administratively suspended societies (`Society.status == 'SUSPENDED'`) are excluded by candidate detection queries.
6. **Zero Migration Footprint**: Utilizes the approved catalog established in Migration 0025 (`platform_billing_job_runs`, `platform_dunning_attempts`, `uq_platform_invoices_sub_period`). Alembic head remains locked at `0025_saas_billing_automation`.
7. **Comprehensive Test Validation**:
   - 15 Unit tests in [test_phase21e6_stage2_dunning.py](file:///c:/SocApp/tests/test_phase21e6_stage2_dunning.py): 15 Passed (100%).
   - 4 Live PostgreSQL 16 tests in [test_phase21e6_stage2_pg.py](file:///c:/SocApp/tests/test_phase21e6_stage2_pg.py): 4 Passed (100%).
   - 42 Combined Phase 21E.6 tests: 42 Passed (100%).
   - 189 Phase 21E regression tests across 21 test files: 189 Passed (100%).
   - Static analysis: Ruff (0 errors), Mypy (0 errors across 19 source files).

---

## 2. Dunning Milestone Schedule & State Machine

The dunning state machine is implemented in `apps/api/src/subscriptions/automation/dunning_service.py` via `DunningEngineService.determine_dunning_stage`.

### Milestone Transitions

| Milestone | Elapsed Time ($\Delta t$) | Remaining Grace | Required Action | Attempt Record Type | Invariant Checked |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Day 0** | $0 \le \Delta t < 48\text{ h}$ | 7 days | Initial Overdue Reminder | `DAY_0_REMINDER` | `status == PAST_DUE`, `past_due_since` set |
| **Day 2** | $48\text{ h} \le \Delta t < 120\text{ h}$ | 5 days | Mid-Grace Warning Reminder | `DAY_2_REMINDER` | Prior Day 0 attempt verified, no duplicate |
| **Day 5** | $120\text{ h} \le \Delta t < 168\text{ h}$ | 2 days | Urgent Final Warning | `DAY_5_WARNING` | Imminent suspension notice issued |
| **Day 7** | $\Delta t \ge 168\text{ h}$ (7 days) | 0 days | Grace Expiry & Suspension | `DAY_7_SUSPENSION` | Check unsettled captured payments; execute suspension |

### Idempotency Key Specification
Every attempt calculates a deterministic SHA-256-backed key:
$$\text{key} = \text{dunning:}\{\text{subscription\_id}\}\text{:}\{\text{invoice\_id}\}\text{:}\{\text{stage}\}$$

If an attempt with this key and `status == 'SUCCEEDED'` exists in `platform_dunning_attempts`, the candidate execution short-circuits with `status = SKIPPED` and `skip_reason = STAGE_ALREADY_EXECUTED`.

---

## 3. Mandatory Late Payment Recovery Architecture

A critical architectural mandate for Phase 21E.6 Stage 2 is preventing unauthorized reactivation of administratively suspended subscriptions while ensuring lawful late recovery for dunning suspensions.

### Provenance Verification Logic
Implemented in [settlement_service.py](file:///c:/SocApp/apps/api/src/subscriptions/payments/settlement_service.py#L247-L313):

```python
elif sub and sub.status == SubscriptionStatus.SUSPENDED.value:
    # 1. Query latest transition into SUSPENDED from immutable PlatformSubscriptionHistory
    stmt_hist = (
        select(PlatformSubscriptionHistory)
        .where(
            PlatformSubscriptionHistory.society_id == society_id,
            PlatformSubscriptionHistory.subscription_id == sub.id,
        )
        .order_by(
            PlatformSubscriptionHistory.effective_at.desc(),
            PlatformSubscriptionHistory.created_at.desc(),
        )
        .limit(1)
    )
    latest_hist = (await self.session.execute(stmt_hist)).scalar_one_or_none()

    # 2. Query Day 7 suspension attempt from PlatformDunningAttempt
    stmt_dunning = (
        select(PlatformDunningAttempt)
        .where(
            PlatformDunningAttempt.society_id == society_id,
            PlatformDunningAttempt.subscription_id == sub.id,
            PlatformDunningAttempt.invoice_id == (invoice.id if invoice else None),
            PlatformDunningAttempt.attempt_type.in_(["DAY_7_SUSPENSION", "SUSPENSION_EXECUTION"]),
            PlatformDunningAttempt.status == "SUCCEEDED",
        )
        .order_by(PlatformDunningAttempt.executed_at.desc())
        .limit(1)
    )
    dunning_att = (await self.session.execute(stmt_dunning)).scalar_one_or_none()

    is_dunning_suspension = (
        latest_hist is not None
        and latest_hist.new_status == SubscriptionStatus.SUSPENDED.value
        and latest_hist.transition_reason.startswith("DUNNING_")
        and latest_hist.changed_by is None
        and dunning_att is not None
    )

    if is_dunning_suspension:
        lifecycle_service = SubscriptionLifecycleService(self.session)
        await lifecycle_service.transition_status(
            society_id=society_id,
            target_status=SubscriptionStatus.ACTIVE,
            reason=f"{inv_desc} settled via {gateway_provider}; dunning suspension lifted",
            actor_id=None,
        )
    else:
        logger.warning(
            "Subscription %s is SUSPENDED for non-dunning/administrative reasons. "
            "Payment settled but subscription was NOT reactivated.",
            sub.id,
        )
```

### Lifecycle Recovery Matrix

| Current Subscription Status | Payment Settlement Event | Provenance Condition Met? | Resulting Subscription Status | Financial / Ledger Action |
| :--- | :--- | :--- | :--- | :--- |
| **`PAST_DUE`** | Invoice Paid in Full | N/A | **`ACTIVE`** | Invoice `PAID`, Payment `CAPTURED` & `is_settled=True` |
| **`SUSPENDED`** (Dunning) | Invoice Paid in Full | **Yes** (`transition_reason` starts with `DUNNING_`, matching attempt exists) | **`ACTIVE`** | Suspension lifted; `PlatformSubscriptionHistory` records `ACTIVE` |
| **`SUSPENDED`** (Admin / Fraud) | Invoice Paid in Full | **No** (Admin actor ID present, no dunning attempt) | **`SUSPENDED`** | Payment settled to invoice; subscription remains `SUSPENDED` |
| **`CANCELLED`** | Late Gateway Payment | **No** (Terminal state) | **`CANCELLED`** | Payment marked orphaned; automated refund initiated via `RefundService` |
| **Any** (`Society.status == SUSPENDED`) | Invoice Paid in Full | Any | Sub updated per rule | `Society.status` remains **`SUSPENDED`** (Strict Decoupling) |

---

## 4. Multi-Worker Concurrency & Database Security

### Concurrency Isolation Architecture
1. **Batch Selection Locking**:
   - `DunningEngineService.detect_dunning_candidates` issues `SELECT ... FROM society_subscriptions WHERE status = 'PAST_DUE' ... FOR UPDATE SKIP LOCKED`.
   - When multiple background workers poll for overdue subscriptions, each candidate is acquired by exactly one worker.
2. **Deterministic 64-bit Advisory Locks**:
   - PostgreSQL `pg_try_advisory_xact_lock` requires a signed 64-bit integer (`bigint`).
   - Standardized algorithm in `compute_advisory_lock_key`:
     $$\text{key} = \text{int.from\_bytes}(\text{sha256}(\text{key\_str})[:8], \text{byteorder}=\text{"big"}, \text{signed}=\text{True})$$
   - Range strictly bounded to $[-2^{63}, 2^{63} - 1]$, eliminating 32-bit CRC collision and truncation defects.
3. **Transaction Savepoint Boundary**:
   - In `process_dunning_batch`, each subscription execution is isolated within an `async with self.session.begin_nested()` transaction savepoint.
   - An unhandled exception on an individual tenant never aborts or corrupts processing for other tenants in the batch.

### PostgreSQL 16 FORCE ROW LEVEL SECURITY Validation
Verified against live PostgreSQL 16 using an unprivileged application role:
```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname = 'platform_dunning_attempts';
-- Returns: relrowsecurity = True, relforcerowsecurity = True
```
1. **Unprivileged Role**: `app_user` verified as `NOSUPERUSER` and `NOBYPASSRLS`.
2. **Fail-Closed Behavior**: Queries executed under `app_user` without setting `app.current_society_id` return exactly 0 rows.
3. **Tenant Read Isolation**: Setting tenant context to Society A permits viewing Society A attempts; Society B attempts remain completely invisible.
4. **Cross-Tenant Write Denial**: Attempting to insert a dunning attempt with Society B's ID while scoped to Society A fails with an RLS check violation.

---

## 5. File Inventory & Implementation Artifacts

### Implemented & Modified Source Modules

| File Path | Component | Description |
| :--- | :--- | :--- |
| [`dunning_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/automation/dunning_service.py) | `DunningEngineService` | Primary autonomous dunning engine managing candidate detection, milestone schedule, notification dispatch, and Day 7 suspension. |
| [`settlement_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/payments/settlement_service.py) | `PaymentSettlementService` | Updated with authoritative late payment recovery provenance check, distinguishing dunning suspensions from administrative suspensions. |
| [`scheduler_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/automation/scheduler_service.py) | `BillingPeriodSchedulerService` | Standardized advisory lock computation to 64-bit SHA-256 integer. Cleaned unused imports. |
| [`__init__.py`](file:///c:/SocApp/apps/api/src/subscriptions/automation/__init__.py) | Package Exports | Exported `DunningEngineService`, `DunningStage`, and `compute_advisory_lock_key`. |

### Test Suites

| File Path | Tests | Coverage | Result |
| :--- | :--- | :--- | :--- |
| [`test_phase21e6_stage2_dunning.py`](file:///c:/SocApp/tests/test_phase21e6_stage2_dunning.py) | 15 | Unit tests: schedule boundaries, Day 0/2/5/7 flows, idempotency, anchor preservation, payment suspension guard, late recovery provenance, cancelled orphan refund, batch ledger, notification resilience. | **15 Passed** (100%) |
| [`test_phase21e6_stage2_pg.py`](file:///c:/SocApp/tests/test_phase21e6_stage2_pg.py) | 4 | Live PostgreSQL 16 tests: 64-bit advisory locking mutual exclusion, FORCE RLS tenant isolation, 4-worker concurrent reminders, 4-worker concurrent suspensions. | **4 Passed** (100%) |
| [`test_phase21e6_stage1_scheduler.py`](file:///c:/SocApp/tests/test_phase21e6_stage1_scheduler.py) | 18 | Stage 1 unit tests: billing period rolling, statutory renewal invoicing, anchor day, leap year, trial auto-renew rules. | **18 Passed** (100%) |
| [`test_phase21e6_stage1_pg.py`](file:///c:/SocApp/tests/test_phase21e6_stage1_pg.py) | 5 | Stage 1 live PostgreSQL 16 tests: migration catalog, RLS, idempotency constraints, concurrency. | **5 Passed** (100%) |

---

## 6. Verification Results

### 1. Phase 21E.6 Stage 2 Direct Test Suite
Command: `.venv\Scripts\pytest.exe tests/test_phase21e6_stage2_dunning.py tests/test_phase21e6_stage2_pg.py -v`
```
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-8.4.2, pluggy-1.6.0 -- C:\SocApp\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\SocApp
configfile: pyproject.toml
plugins: anyio-4.15.1, asyncio-0.26.0, cov-5.0.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 19 items

tests/test_phase21e6_stage2_dunning.py::test_determine_dunning_stage_boundaries PASSED [  5%]
tests/test_phase21e6_stage2_dunning.py::test_compute_advisory_lock_key PASSED [ 10%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_day_0_reminder_flow PASSED [ 15%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_day_2_reminder_flow PASSED [ 21%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_day_5_warning_flow PASSED [ 26%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_day_7_suspension_flow PASSED [ 31%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_idempotency_prevents_duplicate_attempts PASSED [ 36%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_preserves_past_due_since_strictly PASSED [ 42%]
tests/test_phase21e6_stage2_dunning.py::test_captured_payment_blocks_day_7_suspension PASSED [ 47%]
tests/test_phase21e6_stage2_dunning.py::test_late_payment_recovery_reactivates_dunning_suspended_subscription PASSED [ 52%]
tests/test_phase21e6_stage2_dunning.py::test_late_payment_rejects_administrative_suspension PASSED [ 57%]
tests/test_phase21e6_stage2_dunning.py::test_late_payment_on_cancelled_subscription_orphaned PASSED [ 63%]
tests/test_phase21e6_stage2_dunning.py::test_society_status_strictly_decoupled_and_excluded PASSED [ 68%]
tests/test_phase21e6_stage2_dunning.py::test_dunning_batch_execution_ledger PASSED [ 73%]
tests/test_phase21e6_stage2_dunning.py::test_notification_provider_failure_resilience PASSED [ 78%]
tests/test_phase21e6_stage2_pg.py::test_pg_advisory_locking_mutual_exclusion PASSED [ 84%]
tests/test_phase21e6_stage2_pg.py::test_pg_dunning_attempts_force_rls PASSED [ 89%]
tests/test_phase21e6_stage2_pg.py::test_concurrent_dunning_reminder_workers_pg PASSED [ 94%]
tests/test_phase21e6_stage2_pg.py::test_concurrent_dunning_suspension_workers_pg PASSED [100%]

============================= 19 passed in 25.15s =============================
```

### 2. Full Phase 21E.6 Test Suite (Stage 1 + Stage 2)
Command: `.venv\Scripts\pytest.exe tests/test_phase21e6* -v`
```
============================= 42 passed in 37.66s =============================
```

### 3. Full Phase 21E Overall Regression Suite
Command: `.venv\Scripts\pytest.exe (Get-ChildItem tests\*21e* | ForEach-Object { $_.FullName }) -q`
```
189 passed in 174.30s (0:02:54)
```

### 4. Static Analysis & Type Checking
- **Ruff**: `.venv\Scripts\ruff.exe check apps/api/src/subscriptions/ tests/test_phase21e6*`
  ```
  All checks passed!
  ```
- **Mypy**: `.venv\Scripts\mypy.exe apps/api/src/subscriptions/automation/ apps/api/src/subscriptions/payments/`
  ```
  Success: no issues found in 19 source files
  ```

---

## 7. Mandatory Constraints Compliance Verification

1. **Strict 7-Day Grace Period**: Every stage is evaluated as offset from `sub.past_due_since`. No scheduler execution ever resets or extends `past_due_since`. *(Verified)*
2. **Settlement Provenance Invariant**: `SUSPENDED` subscriptions reactivate if and only if suspended by dunning on the paid invoice. Administrative suspensions are preserved. *(Verified)*
3. **Pessimistic Suspension Lock**: Day 7 suspension evaluates `PlatformPayment.status == 'CAPTURED', is_settled == False` before suspending. *(Verified)*
4. **Tenant Security**: `platform_dunning_attempts` enforces `FORCE ROW LEVEL SECURITY`. Unprivileged `app_user` fails closed. *(Verified)*
5. **Horizontal Concurrency**: Multi-worker test with 4 parallel asynchronous workers proved zero deadlocks, zero duplicate attempts, and atomic milestone evaluation. *(Verified)*
6. **Zero Migration Invariant**: Alembic head remains `0025_saas_billing_automation`. *(Verified)*
7. **No Automatic Recurring Debit**: No automated debit or e-mandate execution was authorized or implemented. Standard collection relies on interactive payment links and webhook reconciliation. *(Verified)*

---

## 8. Conclusion & Sign-Off

Phase 21E.6 Stage 2 is **fully implemented, verified against live PostgreSQL 16, regression-tested against the complete Phase 21E billing suite, and locked**.

Per operating guidelines, **execution stops here**. Awaiting formal architectural review before proceeding to subsequent stages.
