# SocietySphere — Phase 21E.6 Stage 1: Automated Billing Period Roll & Renewal Invoicing Engine
## Independent Final Architectural Audit & QA Verification Report

**Document Reference:** `SOCIETYSPHERE_PHASE_21E_6_STAGE_1_FINAL_AUDIT.md`  
**Phase:** 21E.6 — SaaS Subscription Lifecycle Automation (Stage 1)  
**Role:** Independent Principal SaaS Architect & Senior QA Lead  
**Audit Mode:** STRICT READ-ONLY AUDIT (Source code, migrations, and tests untouched)  
**Date:** 2026-11-02  
**Current Alembic Head:** `0025_saas_billing_automation`  
**Target Environment:** PostgreSQL 16 (`societysphere_dev`) & In-Memory SQLite  

---

## Executive Summary & Verdict

This read-only audit provides a comprehensive evaluation of **SocietySphere Phase 21E.6 Stage 1: Automated Billing Period Roll & Renewal Invoicing Engine**.

### Audit Verdict: **APPROVED WITH ARCHITECTURAL CONDITION**

| Area | Status | Key Observation |
|---|---|---|
| **1. Trial Subscription Conversion** | ⚠️ **FINDING** | `TRIAL` $\rightarrow$ `ACTIVE` occurs upon invoice generation without payment settlement confirmation. Remediation required for Stage 2. |
| **2. Billing Period Atomicity** | ✅ **VERIFIED** | Enclosed within savepoint isolation (`begin_nested()`); period advancement and invoice generation are strictly atomic. |
| **3. Invoice Idempotency** | ✅ **VERIFIED** | Dual partial unique indexes (`uq_platform_invoices_sub_period`, `ix_platform_invoices_idempotency_key`) mathematically prevent duplicate active invoices. |
| **4. Migration 0025 & RLS** | ✅ **VERIFIED** | Upgrade, downgrade, re-upgrade verified on PostgreSQL 16. `platform_dunning_attempts` enforces ENABLE & FORCE RLS; `app_user` is `NOSUPERUSER`/`NOBYPASSRLS`. |
| **5. Regression Test Suites** | ✅ **VERIFIED** | Full repository suite: **568 passed, 2 skipped, 0 failed** in 21m 45s. Phase 21E suite: **162 passed, 0 failed**. Stage 1: **15 passed, 0 failed**. |
| **6. Scope Isolation** | ✅ **VERIFIED** | Stage 2 dunning workers are NOT implemented; automated debit/monetary collection is completely disabled. |

---

## 1. Trial Subscription Conversion & State Machine Audit

### 1.1 Lifecycle Transition Matrix Inspection
The canonical state machine in [`apps/api/src/subscriptions/subscription_lifecycle_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/subscription_lifecycle_service.py#L48-L70) governs transitions for `SocietySubscription`:

```python
PERMITTED_TRANSITIONS = {
    SubscriptionStatus.TRIAL: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.CANCELLED,
    },
    ...
}
```

The matrix legally permits a transition from `TRIAL` to `ACTIVE`. However, the domain contract for *when* that transition may occur is governed by [`apps/api/src/subscriptions/payments/settlement_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/payments/settlement_service.py#L244-L250):

```python
elif sub and sub.status == SubscriptionStatus.TRIAL.value:
    # Transition TRIAL -> ACTIVE on confirmed first billing payment
    lifecycle_service = SubscriptionLifecycleService(self.session)
    await lifecycle_service.transition_status(
        society_id=society_id,
        target_status=SubscriptionStatus.ACTIVE,
        reason=f"{inv_desc} settled; trial converted to active",
    )
```

### 1.2 Auditor Finding: Unintended Free Activation Vulnerability
In [`apps/api/src/subscriptions/automation/scheduler_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/automation/scheduler_service.py#L233-L248):

```python
# 8. Advance Subscription Period & State
previous_status = sub.status
new_status = "ACTIVE" if previous_status == "TRIAL" else previous_status
...
sub.status = new_status
sub.current_period_start = new_period_start
sub.current_period_end = new_period_end
sub.next_billing_at = new_period_end
```

**Architectural Analysis & Defect Identification:**
1. When a tenant’s trial reaches its end (`sub.next_billing_at <= cutoff_utc`), `scheduler_service.py` rolls the subscription into the next billing period and generates a renewal invoice.
2. The generated renewal invoice is created in **`ISSUED`** status with `amount_due == grand_total` and `amount_paid == 0.00`. No payment has yet been received.
3. However, `scheduler_service.py` sets `sub.status = "ACTIVE"` immediately upon invoice issuance.
4. **Vulnerability:** If the tenant never pays the issued renewal invoice, their subscription has already been converted to `ACTIVE`, granting full plan entitlements and quotas without payment settlement.
5. `auto_renew=True` indicates customer intent to renew, but does **NOT** equal payment completion. In interactive payment mode (payment links), payment settlement remains the authoritative gatekeeper for active status.

### 1.3 Mandatory Remediation Condition for Stage 2
- **Rule:** A `TRIAL` subscription must **NOT** become `ACTIVE` merely because `auto_renew=True` or because a renewal invoice was issued.
- **Design Requirement for Stage 2:**
  - Upon trial expiry, the scheduler issues the renewal invoice.
  - The subscription status should transition to **`PAST_DUE`** (or enter a trial grace period), placing the subscription into the Stage 2 dunning pipeline.
  - Transition to `ACTIVE` must remain strictly delegated to [`PaymentSettlementService.settle_payment()`](file:///c:/SocApp/apps/api/src/subscriptions/payments/settlement_service.py#L244) upon confirmed receipt of payment.

---

## 2. Billing Period Atomicity & Failure Simulation

### 2.1 Transactional Safety Analysis
In [`apps/api/src/subscriptions/automation/scheduler_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/automation/scheduler_service.py#L365-L382):
- Each subscription roll executes inside `async with self.session.begin_nested():` (a PostgreSQL savepoint).
- Within this savepoint:
  1. Row lock acquired: `SELECT ... FOR UPDATE`.
  2. Distributed advisory lock acquired: `SELECT pg_try_advisory_xact_lock(...)`.
  3. Invoice generated and finalized via `self.renewal_service.generate_renewal_invoice()`.
  4. Subscription period boundaries updated: `current_period_start`, `current_period_end`, `next_billing_at`.
  5. Audit log and history entries recorded.
  6. `await self.session.flush()`.
- If an unhandled exception occurs, the savepoint rolls back both the invoice and the period updates atomically.
- At the end of the batch, `await self.session.commit()` persists the entire batch ledger and operational run record.

### 2.2 Critical Failure Point Simulations

| Failure Injection Point | System State Upon Failure | Retry Behavior | Outcome |
|---|---|---|---|
| **Point A: Crash before invoice creation** | Subscription locked in memory; no DB changes written. | Worker rolls back connection. Next worker picks up subscription since `next_billing_at <= cutoff` is unchanged. | ✅ Safe. Zero side effects. |
| **Point B: Crash after invoice created, before period update** | Invoice created in draft; uncommitted inside savepoint. | Transaction rolled back by DB server upon connection termination. Invoice and period both discard. | ✅ Safe. No orphan invoice. |
| **Point C: Crash after period update, before savepoint exit** | Period updated and invoice finalized in local session buffer; uncommitted. | Savepoint / connection rollback discards both changes. Subscription remains due. | ✅ Safe. Zero partial state. |
| **Point D: Worker process hard kill (SIGKILL) mid-batch** | PostgreSQL server automatically aborts and rolls back uncommitted transaction. | All subscriptions in the uncommitted batch remain at their prior `next_billing_at`. Subsequent run restarts batch cleanly. | ✅ Safe. Crash-resilient. |

**Evidence:** Verified in [`tests/test_phase21e6_stage1_scheduler.py::test_scheduler_recovery_after_worker_crash`](file:///c:/SocApp/tests/test_phase21e6_stage1_scheduler.py#L396).

---

## 3. Invoice Idempotency & Concurrency Defenses

### 3.1 Multi-Tiered Defenses Against Duplicate Invoicing

```
[ Worker Request ]
       │
       ▼
1. PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED  ──► Prevents parallel workers from selecting same subscription
       │
       ▼
2. 64-bit Advisory Lock: pg_try_advisory_xact_lock ──► Serializes multi-process execution per society
       │
       ▼
3. Pre-check: get_existing_renewal_invoice()   ──► Reuses already finalized invoice or finalizes draft
       │
       ▼
4. DB Constraint: ix_platform_invoices_idempotency_key ──► Rejects duplicate idempotency keys
       │
       ▼
5. DB Constraint: uq_platform_invoices_sub_period  ──► Rejects duplicate non-VOID invoices for identical period
```

### 3.2 Constraints Detail
- **`uq_platform_invoices_sub_period`**:
  `ON platform_invoices (subscription_id, period_start, period_end) WHERE status != 'VOID' AND period_start < period_end`
  - Prevents multiple non-VOID invoices from being generated for the same periodic window.
  - The `status != 'VOID'` predicate ensures that if an invoice was legitimately voided due to billing adjustments, a replacement invoice can be legally issued.
- **`ix_platform_invoices_idempotency_key`**:
  `ON platform_invoices (idempotency_key) WHERE idempotency_key IS NOT NULL`
  - Idempotency key pattern: `renewal:{subscription_id}:{period_start.isoformat()}:{period_end.isoformat()}`.
  - Guarantees deterministic deduplication at the database level.
- **Number Sequence Monotonicity**:
  - `InvoiceNumberingService` allocates numbers sequentially using row locks on `platform_invoice_sequences`.
  - Voiding an invoice never resets or reuses the sequence number. Numbers remain strictly monotonic and audit-compliant.

**Evidence:** Verified in [`tests/test_phase21e6_stage1_pg.py::test_database_invoice_idempotency_constraints`](file:///c:/SocApp/tests/test_phase21e6_stage1_pg.py#L316) and [`test_concurrent_scheduler_workers_pg`](file:///c:/SocApp/tests/test_phase21e6_stage1_pg.py#L399).

---

## 4. Migration 0025 & PostgreSQL 16 Security Catalog

### 4.1 Migration Verification
Migration file: [`apps/api/alembic/versions/20261102_0025_saas_billing_automation.py`](file:///c:/SocApp/apps/api/alembic/versions/20261102_0025_saas_billing_automation.py)  
Down revision: `0024_saas_billing_documents`

Live verification commands executed against PostgreSQL 16 (`societysphere_dev`):
1. `alembic -c apps/api/alembic.ini downgrade -1` $\rightarrow$ Successfully downgraded to `0024_saas_billing_documents` (Code 0).
2. `alembic -c apps/api/alembic.ini upgrade head` $\rightarrow$ Successfully re-applied `0025_saas_billing_automation` (Code 0).
3. Current revision confirmed: `0025_saas_billing_automation (head)`.

### 4.2 PostgreSQL 16 Catalog Inspection

```sql
SELECT relname, relrowsecurity, relforcerowsecurity 
FROM pg_class 
WHERE relname IN ('platform_billing_job_runs', 'platform_dunning_attempts');
```

| Table Name | relrowsecurity | relforcerowsecurity | Audit Assessment |
|---|---|---|---|
| `platform_billing_job_runs` | `False` | `False` | ✅ Correct. Platform-internal global operational ledger. Not tenant-scoped. |
| `platform_dunning_attempts` | `True` | `True` | ✅ Verified. Tenant-scoped table enforces strict RLS and FORCE RLS. |

### 4.3 Database Role Privileges (`app_user`)

```sql
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_user';
```
- `rolname`: `app_user`
- `rolsuper`: `False` (`NOSUPERUSER`)
- `rolbypassrls`: `False` (`NOBYPASSRLS`)

**Live Isolation Tests:**
- Missing tenant context: Queries return `0` rows (fails closed).
- Setting context to Tenant A: Can view Tenant A's dunning attempts.
- Setting context to Tenant B: Querying Tenant A's records returns `None` (cross-tenant read blocked).
- Tampered writes: Inserting record for Tenant A while context is Tenant B raises an RLS check violation.

**Evidence:** Verified in [`tests/test_phase21e6_stage1_pg.py::test_pg16_rls_dunning_attempts_isolation`](file:///c:/SocApp/tests/test_phase21e6_stage1_pg.py#L243).

---

## 5. Comprehensive Test Execution & Regression Analysis

### 5.1 Test Execution Results by Suite

| Test Suite | Environment | Total | Passed | Failed | Skipped | Duration |
|---|---|---|---|---|---|---|
| **Phase 21E.6 Stage 1 Dedicated** | PostgreSQL 16 & In-Memory | 15 | **15** | 0 | 0 | 15.95s |
| **Phase 21E Regression Suite** | PostgreSQL 16 & In-Memory | 162 | **162** | 0 | 0 | 131.26s |
| **Full Repository Test Suite** | Full System (PG + SQLite) | 570 | **568** | 0 | **2** | 1305.11s (21m 45s) |

### 5.2 Breakdown by Test Fixture Environment
- **Live PostgreSQL 16 Tests:**
  - `test_phase21e6_stage1_pg.py` (4 tests)
  - `test_phase21e4b_pg.py`, `test_phase21e4c_pg.py`, `test_phase21e4d_pg.py` (12 tests)
  - `test_pg_reconciliation_concurrency.py` (2 tests)
  - `test_phase21c_provisioning_concurrency_pg.py`, `test_phase21d_platform_admin_concurrency_pg.py` (4 tests)
  - `test_phase21e2_concurrency_pg.py`, `test_phase21e3_concurrency_pg.py` (4 tests)
  - All PostgreSQL 16 live tests passed with zero failures.
- **In-Memory SQLite Unit & Workflow Tests:**
  - 542 passed tests across all repository domains (auth, billing, finance, maintenance, resident, staff, visitor, vehicle, vendor, and subscriptions).
- **Mocked / Unit Service Tests:**
  - Document PDF generator, email dispatcher, and payment gateway adapters executed under mocked external I/O fixtures with verified deterministic responses.

### 5.3 Detailed Skipped Tests Investigation
Exactly **two tests were skipped** across the entire 570-test repository suite. Both reside in [`tests/test_phase21b_reconciliation_targeted.py`](file:///c:/SocApp/tests/test_phase21b_reconciliation_targeted.py):

1. **`test_03_concurrent_reservation_during_reconciliation`** ([line 184](file:///c:/SocApp/tests/test_phase21b_reconciliation_targeted.py#L184))
   - **Reason:** `Row-level lock serialization requires PostgreSQL (SELECT ... FOR UPDATE is a no-op in SQLite)`
2. **`test_05_two_concurrent_reconciliation_attempts`** ([line 314](file:///c:/SocApp/tests/test_phase21b_reconciliation_targeted.py#L314))
   - **Reason:** `Row-level lock serialization requires PostgreSQL (SELECT ... FOR UPDATE is a no-op in SQLite)`

**Root Cause Investigation (Phase 21B Timing Behavior):**
- In SQLite, the `SELECT ... FOR UPDATE` row-locking clause is parsed as a no-op. SQLite does not support row-level locks or `SKIP LOCKED`; it uses coarse database-level file locks.
- When concurrent asynchronous coroutines interleave simulated reconciliation and quota reservation operations against an in-memory SQLite database, SQLite either fails to serialize them (producing race conditions) or locks the entire connection table (producing `sqlite3.OperationalError: database is locked`).
- **Resolution Status:** This skip is an intentional, documented design condition from Phase 21B. The corresponding live multi-connection concurrency scenarios are comprehensively tested and verified on live PostgreSQL 16 in [`tests/test_pg_reconciliation_concurrency.py`](file:///c:/SocApp/tests/test_pg_reconciliation_concurrency.py), where both tests pass with 100% reliability.
- **Auditor Action:** The skip condition was inspected in read-only mode and confirmed valid. It was neither modified nor suppressed.

### 5.4 Static Analysis & Code Quality Audits
- **Ruff:**
  - Command: `ruff check .`
  - Result: `All checks passed!` (0 errors across entire repository).
- **MyPy:**
  - Command: `mypy apps/api/src/`
  - Result: `Success: no issues found in 395 source files` (0 type errors).

---

## 6. Scope Boundaries & Defense Invariants

The implementation strictly honors the architectural boundaries established for Phase 21E.6 Stage 1:

1. **Zero Dunning Execution:**
   - The table `platform_dunning_attempts` was provisioned in Migration 0025, but no dunning background workers, retry loops, notification escalations, or suspension jobs have been implemented.
   - Stage 2 dunning remains fully deferred.
2. **Zero Automated Monetary Collection:**
   - Invoices are generated strictly in `ISSUED` status.
   - No payment gateway debit requests (`razorpay.payment.capture`, e-mandate presentation, or bank debit) are invoked.
   - Invoices are delivered with interactive payment links awaiting customer-initiated settlement.
3. **No Overlapping Logic:**
   - Stage 1 cleanly leverages existing services: `GSTTaxEngine`, `InvoiceNumberingService`, `PlaceOfSupplyService`, `BillingPeriodService`, and `PlatformInvoiceService`.

---

## 7. Audit Recommendations for Stage 2 Authorization

Before authorizing implementation of **Phase 21E.6 Stage 2 (Dunning Engine & Grace Period Worker)**, the development team must incorporate the following requirements:

1. **Fix Trial Conversion Invariant:**
   Modify `scheduler_service.py` to ensure that expiring trials do not prematurely convert to `ACTIVE` upon invoice issuance. Expired trials must transition to `PAST_DUE` (with a 7-day grace period), converting to `ACTIVE` solely when payment settlement is confirmed by `PaymentSettlementService`.
2. **Integrate Dunning Worker with `platform_dunning_attempts`:**
   Implement the Stage 2 worker to query overdue invoices, evaluate grace period thresholds (7 days), and schedule structured escalations (`REMINDER_NOTICE` $\rightarrow$ `OVERDUE_WARNING` $\rightarrow$ `FINAL_NOTICE` $\rightarrow$ `DEGRADATION_WARNING` $\rightarrow$ `SUSPENSION_ACTION`).
3. **Preserve Phase 21E.4D Email Pipeline:**
   Reuse the existing transactional email and document orchestrator services for all dunning communications.
