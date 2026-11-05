# SocietySphere — Phase 21E.6 Stage 1: Automated Billing Period Roll & Renewal Invoicing Engine
## Implementation & Technical Verification Report

**Document Reference:** `SOCIETYSPHERE_PHASE_21E_6_STAGE_1_IMPLEMENTATION_REPORT.md`  
**Phase:** 21E.6 — SaaS Subscription Lifecycle Automation (Stage 1: Automated Billing Period Roll & Renewal Invoicing)  
**Author:** Principal SaaS Architect, Senior Python Engineer & Distributed Systems Engineer  
**Status:** **IMPLEMENTED & FULLY VERIFIED**  
**Date:** 2026-11-02  
**Current Alembic Head:** `0025_saas_billing_automation`  
**Live Target Database:** PostgreSQL 16 (`societysphere_dev`)

---

## 1. Executive Summary

Phase 21E.6 Stage 1 delivers an automated, horizontally scalable, crash-resilient billing period roll and renewal invoicing engine for the SocietySphere multi-tenant SaaS platform. 

The implementation enforces strict architectural boundaries:
- **Zero Real Monetary Collection:** Automated debit and e-mandate execution are explicitly segregated to future stages; invoices are issued in `ISSUED` status with compliant payment links.
- **Dunning Deferred:** Dunning retry mechanics, reminder schedules, and tenant suspension are deferred to Stage 2.
- **Idempotency Invariants:** Double-invoicing and duplicate rolls are mathematically prevented through multi-tiered defenses: composite partial unique database constraints, transaction-level distributed advisory locks, row-level locks with `SKIP LOCKED`, and SHA-256 verified tax snapshots.
- **Strict Compliance:** Renewal invoices strictly adhere to the locked Phase 21E.4A/B/C statutory tax architecture, applying SAC 998313, server-authoritative GSTTaxEngine computation (18% IGST or 9%+9% CGST/SGST), and fiscal-year sequential numbering (`SS-2627-XXXXX`).

All unit, integration, PostgreSQL 16 catalog, row-level security (RLS), concurrency, and regression test suites have passed with **100% success rate (62/62 total assertions)**. Ruff and MyPy report **zero defects**.

---

## 2. Database Migration 0025 (`0025_saas_billing_automation`)

Migration file: `apps/api/alembic/versions/20261102_0025_saas_billing_automation.py`  
Down revision: `0024_saas_billing_documents`

### 2.1 Table Schemas & Relational Ledger

#### A. `platform_billing_job_runs` (Global Execution Ledger)
Tracks platform-level background worker batch executions. Not tenant-scoped.
- `id` (UUID, PK)
- `job_type` (VARCHAR(50), NOT NULL, CHECK in `('PERIOD_ROLL', 'RENEWAL_INVOICING', 'DUNNING_EVAL')`)
- `execution_id` (VARCHAR(100), UNIQUE, NOT NULL, indexed)
- `status` (VARCHAR(30), NOT NULL, CHECK in `('RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL')`)
- `started_at` (TIMESTAMP WITHOUT TIME ZONE, NOT NULL)
- `completed_at` (TIMESTAMP WITHOUT TIME ZONE, NULL)
- `processed_count` (INTEGER, DEFAULT 0, CHECK >= 0)
- `succeeded_count` (INTEGER, DEFAULT 0, CHECK >= 0)
- `failed_count` (INTEGER, DEFAULT 0, CHECK >= 0)
- `skipped_count` (INTEGER, DEFAULT 0, CHECK >= 0)
- `error_summary` (JSONB, NULL)
- `metadata` (JSONB, NULL)

#### B. `platform_dunning_attempts` (Tenant-Scoped Dunning History Schema)
Pre-created for Stage 2 dunning worker operations, fully secured in PostgreSQL 16.
- `id` (UUID, PK)
- `society_id` (UUID, FK -> `societies.id` ON DELETE CASCADE, NOT NULL)
- `subscription_id` (UUID, FK -> `society_subscriptions.id` ON DELETE CASCADE, NOT NULL)
- `invoice_id` (UUID, FK -> `platform_invoices.id` ON DELETE SET NULL, NULL)
- `attempt_number` (INTEGER, NOT NULL, DEFAULT 1, CHECK > 0)
- `attempt_type` (VARCHAR(50), NOT NULL, CHECK in `('REMINDER_NOTICE', 'OVERDUE_WARNING', 'FINAL_NOTICE', 'DEGRADATION_WARNING', 'SUSPENSION_ACTION')`)
- `status` (VARCHAR(30), NOT NULL, CHECK in `('PENDING', 'SENT', 'FAILED', 'CANCELLED', 'RESOLVED')`)
- `channel` (VARCHAR(30), NOT NULL, DEFAULT 'EMAIL', CHECK in `('EMAIL', 'WHATSAPP', 'IN_APP', 'WEBHOOK')`)
- `idempotency_key` (VARCHAR(150), UNIQUE, NOT NULL)
- `scheduled_at` (TIMESTAMP WITHOUT TIME ZONE, NOT NULL)
- `executed_at` (TIMESTAMP WITHOUT TIME ZONE, NULL)
- `response_payload` (JSONB, NULL)
- `failure_reason` (TEXT, NULL)
- `next_retry_at` (TIMESTAMP WITHOUT TIME ZONE, NULL)
- `created_at` / `updated_at` (TIMESTAMP WITHOUT TIME ZONE, NOT NULL)

### 2.2 Row-Level Security (RLS) Verification
Migration 0025 executes:
```sql
ALTER TABLE platform_dunning_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_dunning_attempts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_platform_dunning_attempts ON platform_dunning_attempts
    AS RESTRICTIVE
    USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid)
    WITH CHECK (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```
Tested against live PostgreSQL 16 catalog:
- `relrowsecurity = True`
- `relforcerowsecurity = True`
- `app_user` confirmed `NOSUPERUSER` and `NOBYPASSRLS`.
- Missing context fails closed (0 rows returned).
- Cross-tenant reads and tampered writes return `None` or raise security violation exceptions.

### 2.3 Partial Unique Indexes & Concurrency Indexes
1. `uq_platform_invoices_sub_period`:
   `ON platform_invoices (subscription_id, period_start, period_end) WHERE status != 'VOID' AND period_start < period_end`
   Guarantees that a subscription can never receive multiple active invoices for the exact same billing period.
2. `ix_platform_invoices_idempotency_key`:
   `ON platform_invoices (idempotency_key) WHERE idempotency_key IS NOT NULL`
   Enforces platform-wide invoice generation deduplication.
3. `ix_society_subscriptions_sched_roll`:
   `ON society_subscriptions (status, auto_renew, next_billing_at)`
   Enables indexed batch retrieval of renewal candidates under high subscription volumes.

---

## 3. Core Architecture & Services

### 3.1 `AutomatedRenewalInvoicingService`
Located at `apps/api/src/subscriptions/automation/renewal_service.py`.

Key Responsibilities:
1. **Idempotency Guarantee:** Looks up existing invoices via `(subscription_id, period_start, period_end)` or `idempotency_key`.
   - If already finalized (`ISSUED`, `PAID`, etc.), reuses and returns existing invoice immediately.
   - If existing `DRAFT`, immediately finalizes it without regenerating line items.
2. **Server-Authoritative Pricing & Line Items:**
   - Extracts base plan recurring price (`monthly_price` or `annual_price`).
   - Line item description: `Platform Subscription Renewal: {plan.display_name} ({sub.billing_cycle})`.
   - SAC code: `998313` (Information technology software services).
3. **GST Tax Engine Integration:**
   - Invokes `GSTTaxEngine.calculate()` with platform state (`tax_config_service.supplier_state` = Maharashtra) and society state (`society.state`).
   - Intrastate: CGST 9% + SGST 9%.
   - Interstate: IGST 18%.
   - Reverse charge: `False`.
4. **Finalization & Legal Sequence Numbering:**
   - Invokes `InvoiceNumberingService.generate_next_number()`.
   - Formats invoice number: `SS-YY{YY+1}-XXXXX` (e.g. `SS-2627-00161`).
   - Persists immutable SHA-256 tax snapshot (`tax_snapshot` and `tax_snapshot_hash`).

### 3.2 `BillingPeriodSchedulerService`
Located at `apps/api/src/subscriptions/automation/scheduler_service.py`.

Key Responsibilities:
1. **Concurrency-Safe Candidate Detection (`detect_due_subscriptions`):**
   - Filters: `status IN ('ACTIVE', 'TRIAL')`, `auto_renew = True`, `next_billing_at <= cutoff_utc`, `Society.status != 'SUSPENDED'`, `Society.archived_at IS NULL`.
   - Concurrency locking: `SELECT ... FOR UPDATE SKIP LOCKED` (on PostgreSQL) or standard row lock (SQLite fallback).
   - Prevents multiple parallel workers from acquiring the same subscription candidate.
2. **PostgreSQL 64-Bit Transaction Advisory Locking:**
   - Obtains `pg_try_advisory_xact_lock('society_billing_roll', society_id)` to serialize all billing mutations per tenant across distributed worker instances.
3. **Anchor-Day Preservation & IST Calculation:**
   - Uses `BillingPeriodService.to_ist(starts_at).day` to preserve the original subscription anchor day.
   - Clamps month-end dates (e.g., Jan 31 $\rightarrow$ Feb 28/29 $\rightarrow$ Mar 31).
   - Normalized naive UTC storage across all period boundaries.
4. **Savepoint Error Isolation:**
   - Wraps each subscription roll in `session.begin_nested()`.
   - If one subscription fails due to an unexpected exception, its transaction rolls back cleanly to the savepoint without interrupting the remaining batch.
5. **Trial Conversion:**
   - Subscriptions in `TRIAL` status with `auto_renew=True` convert to `ACTIVE` upon the first periodic roll.
6. **Platform History & Audit Ledger:**
   - Creates `PlatformSubscriptionHistory` record recording period shift and status changes.
   - Creates `PlatformSubscriptionAuditLog` record storing `before_state` and `after_state`.
   - Logs overall batch metrics to `PlatformBillingJobRun`.

---

## 4. Verification Evidence & Test Execution

### 4.1 Test Summary
A dedicated test suite covering 15 unit, workflow, RLS, and PostgreSQL concurrency scenarios was executed against both in-memory SQLite and a live PostgreSQL 16 container.

| Test ID | Module | Scenario / Description | Result |
|---|---|---|---|
| 1 | `scheduler` | Monthly billing period roll & invoicing | **PASSED** |
| 2 | `scheduler` | Annual billing period roll & invoicing | **PASSED** |
| 3 | `scheduler` | Month-end anchor day preservation (Jan 31 $\rightarrow$ Feb 28 $\rightarrow$ Mar 31) | **PASSED** |
| 4 | `scheduler` | Leap year handling (Feb 29 anchor in leap years) | **PASSED** |
| 5 | `scheduler` | Future billing period exclusion (`next_billing_at > cutoff`) | **PASSED** |
| 6 | `scheduler` | Cancelled subscription exclusion (`status == CANCELLED`) | **PASSED** |
| 7 | `scheduler` | Administratively suspended society exclusion (`status == SUSPENDED`) | **PASSED** |
| 8 | `scheduler` | Duplicate invoice prevention under identical periods | **PASSED** |
| 9 | `scheduler` | Worker crash recovery and idempotency | **PASSED** |
| 10 | `scheduler` | Atomic invoice and immutable SHA-256 tax snapshot persistence | **PASSED** |
| 11 | `scheduler` | Trial subscription converts to `ACTIVE` upon first roll | **PASSED** |
| 12 | `pg16` | Migration 0025 catalog check (`pg_class`, `pg_indexes`, RLS flags) | **PASSED** |
| 13 | `pg16` | PostgreSQL 16 RLS cross-tenant read/write denial under `app_user` | **PASSED** |
| 14 | `pg16` | Database partial unique constraints (`uq_sub_period`, `ix_idemp_key`) | **PASSED** |
| 15 | `pg16` | Live multi-worker horizontal concurrency under `SKIP LOCKED` | **PASSED** |

### 4.2 Full Phase 21E Regression Suite Results
To ensure zero regressions across all previously approved phases, the complete Phase 21E suite was executed:
```
tests/test_phase21e4b_invoicing.py .................. [13 passed]
tests/test_phase21e4c_credit_notes.py ............... [14 passed]
tests/test_phase21e4d_documents.py .................. [15 passed]
tests/test_phase21e5_stage3_validation.py ........... [ 5 passed]
tests/test_phase21e6_stage1_scheduler.py ............ [11 passed]
tests/test_phase21e6_stage1_pg.py ................... [ 4 passed]

======================== 62 passed in 64.61s (0:01:04) ========================
```

### 4.3 Static Analysis & Code Quality
- **Ruff:** `ruff check apps/api/src/subscriptions/automation/ apps/api/alembic/versions/20261102_0025_saas_billing_automation.py tests/test_phase21e6_stage1_*.py`
  - Output: `All checks passed!`
- **MyPy:** `mypy apps/api/src/subscriptions/automation/`
  - Output: `Success: no issues found in 4 source files`

---

## 5. File Manifest

### Created / Modified Files:
1. `apps/api/alembic/versions/20261102_0025_saas_billing_automation.py`
   - Migration 0025 adding `platform_billing_job_runs`, `platform_dunning_attempts`, partial unique indexes, and RLS policies.
2. `apps/api/src/database/models/platform_billing.py`
   - Added `PlatformInvoice.idempotency_key` mapped column.
   - Added `PlatformBillingJobRun` operational ledger model.
   - Added `PlatformDunningAttempt` tenant-scoped model.
3. `apps/api/src/subscriptions/invoicing/schemas.py`
   - Updated `PlatformInvoiceCreateDraft` and `PlatformInvoiceResponse` with `idempotency_key`.
4. `apps/api/src/subscriptions/invoicing/service.py`
   - Updated `create_draft_invoice` and `_to_response` to accept, persist, and return `idempotency_key`.
5. `apps/api/src/subscriptions/automation/__init__.py`
   - Package initialization.
6. `apps/api/src/subscriptions/automation/schemas.py`
   - Automation DTOs: `BillingJobRunStatus`, `BillingJobType`, `SubscriptionRollResult`, `BillingBatchExecutionResult`.
7. `apps/api/src/subscriptions/automation/renewal_service.py`
   - Server-authoritative automated renewal invoicing service.
8. `apps/api/src/subscriptions/automation/scheduler_service.py`
   - Concurrency-safe billing period roll and batch scheduling engine.
9. `tests/test_phase21e6_stage1_scheduler.py`
   - Unit & workflow test suite for billing roll, anchor preservation, leap year clamping, exclusions, and idempotency.
10. `tests/test_phase21e6_stage1_pg.py`
    - Live PostgreSQL 16 migration, RLS, partial unique constraint, and multi-worker concurrency test suite.

---

## 6. Next Steps (Stage 2 Preparation)

Phase 21E.6 Stage 1 is fully complete and ready for formal architectural sign-off.

The foundation is now established for **Phase 21E.6 Stage 2 — Dunning Engine & Grace Period Worker**:
1. Utilization of `platform_dunning_attempts` table created in Migration 0025.
2. Automated overdue invoice detection and multi-stage dunning escalation (`REMINDER_NOTICE` $\rightarrow$ `OVERDUE_WARNING` $\rightarrow$ `FINAL_NOTICE` $\rightarrow$ `DEGRADATION_WARNING` $\rightarrow$ `SUSPENSION_ACTION`).
3. Tenant notification delivery via Phase 21E.4D email abstractions.
4. Enforcement of the 7-day grace period with automatic tenant degradation or suspension upon expiration.
