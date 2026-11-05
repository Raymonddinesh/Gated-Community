# SocietySphere Phase 21E.6 — Stage 2: Dunning Engine & Grace Period Suspension QA Remediation Report

**Date:** November 3, 2026  
**Author:** Principal SaaS Architect, Senior Python Engineer & PostgreSQL Transactional Systems Engineer  
**Status:** **REMEDIATION COMPLETED & VERIFIED (PASS WITH CONDITIONS CLEARED)**  
**Target Alembic Head:** `0025_saas_billing_automation` (STRICTLY UNCHANGED)  
**Applicable Standards:** PostgreSQL 16 ACID Concurrency, Force Row Level Security, Transactional Outbox Pattern  

---

## 1. Executive Summary & Authorization Scope

Following the independent QA audit of **Phase 21E.6 Stage 2: Dunning Engine & Grace Period Suspension Automation**, authorization was granted to correct exclusively the three identified findings. No work on Stage 3 was initiated, no locked prior phases were altered, and no database schema migrations were created.

### Audit Findings Addressed

| Finding ID | Severity | Affected Component | Core Issue | Remediation Status |
| :--- | :--- | :--- | :--- | :--- |
| **Finding 1** | **HIGH** | `DunningEngineService.dispatch_notifications` | External provider network timeouts/exceptions could bubble into the database transaction and roll back Day 7 subscription suspensions. | **RESOLVED & VERIFIED** |
| **Finding 2** | **MEDIUM** | `DunningEngineService` Notification Dispatch | Lack of durable transactional outbox risked silent message drops if workers terminated between lifecycle commit and provider dispatch. | **RESOLVED & VERIFIED** |
| **Finding 3** | **MEDIUM** | `test_concurrent_dunning_reminder_workers_pg` | Test asserted global table counts without isolating candidates, failing when executed against persistent databases with pre-existing overdue rows. | **RESOLVED & VERIFIED** |

---

## 2. Technical Remediation Implementation

### Finding 1: Provider Exception Decoupling & Suspension Atomicity

#### Architectural Defect
In the original Stage 2 implementation, external communication providers (Email, SMS, WhatsApp) were invoked within or directly adjacent to the suspension execution path. If a provider raised an unexpected network exception or timed out, the transaction was at risk of rolling back the `SUSPENDED` state transition and the `PlatformDunningAttempt` audit log.

#### Implementation
In [`apps/api/src/subscriptions/automation/dunning_service.py`](file:///c:/SocApp/apps/api/src/subscriptions/automation/dunning_service.py):
1. **Transaction Segregation:** The subscription state change to `SUSPENDED` (via `SubscriptionLifecycleService.suspend_subscription`), the `PlatformDunningAttempt` ledger record, and the durable `Notification` outbox record are committed atomically to the database first.
2. **Resilient Provider Dispatch Wrapper:** All communication provider invocations (`send()` for Email, SMS, WhatsApp, and In-App) are individually wrapped in explicit exception isolation handlers (`try...except Exception as exc:`). Provider timeouts, network resets, or authentication errors are captured, logged, and appended to the outbox error log rather than propagating up the call stack.
3. **Suspension Invariant Guarantee:** Even under total provider failure or fatal unhandled exceptions during dispatch, the subscription remains permanently committed as `SUSPENDED` in PostgreSQL, with an immutable record in `PlatformSubscriptionHistory` (`transition_reason="DUNNING_GRACE_PERIOD_EXPIRED: Automatic suspension at Day 7 for unpaid invoice..."`).

---

### Finding 2: Durable Transactional Outbox Pattern

#### Architectural Defect
Without a persistent outbox, a worker process crash or restart immediately following the database transaction commit would drop in-flight notifications without an audit trail or retry mechanism.

#### Implementation
Rather than generating redundant tables or migrations, we leveraged the existing approved Phase 20 `Notification` table (`notifications`), which is already deployed in PostgreSQL 16 with `FORCE ROW LEVEL SECURITY`, tenant isolation, and `(society_id, idempotency_key)` uniqueness constraints:

1. **Atomic Outbox Enqueue:**
   During both reminder (Day 0, 2, 5) and suspension (Day 7) evaluations, a `Notification` entity is created and committed in the exact same database transaction as the subscription lifecycle transition:
   ```python
   outbox_entry = Notification(
       id=outbox_id,
       society_id=sub.society_id,
       category="BILLING",
       priority="CRITICAL" if stage == DunningStage.DAY_7_SUSPENSION else "HIGH",
       source_domain="DUNNING",
       source_event_id=str(attempt_id),
       idempotency_key=f"dunning-outbox:{attempt_id}",
       title=subject,
       content=body,
       payload=json.dumps({
           "attempt_id": str(attempt_id),
           "subscription_id": str(sub.id),
           "society_id": str(sub.society_id),
           "invoice_id": str(active_inv.id) if active_inv else None,
           "stage": stage.value,
           "grace_days_remaining": grace_days_remaining,
           "recipient_email": recip_email,
           "recipient_user_id": str(recip_user_id) if recip_user_id else None,
           "recipient_phone": recip_phone,
           "retry_count": 0,
           "max_retries": 3,
       }),
       status="QUEUED",
       created_at=now,
       updated_at=now,
   )
   self.session.add(outbox_entry)
   await self.session.flush()
   ```

2. **Decoupled Outbox Drainage Service:**
   Implemented `DunningEngineService.drain_pending_outbox()` and `DunningEngineService.dispatch_outbox_notification()`:
   * **Row-Level Concurrency:** Queries pending notifications (`status IN ('QUEUED', 'RETRYING')`) using `SELECT ... FOR UPDATE SKIP LOCKED` to allow horizontally scaled background workers to process batches concurrently without contention.
   * **Bounded Exponential Backoff Retries:** Tracks `retry_count` in notification payload. If dispatch fails across all providers, status transitions to `RETRYING` until `max_retries=3` is reached, at which point status transitions to `FAILED`.
   * **Deduplication Protection:** If a notification is already in `SENT` or `FAILED` status, redundant dispatch calls return immediately without re-invoking providers.
   * **Audit Synchronization:** Automatically synchronizes `PlatformDunningAttempt.metadata_json` with dispatched channels, outbox status, error messages, and retry counts.

---

### Finding 3: PostgreSQL Persistent Database Test Isolation

#### Architectural Defect
In persistent database environments (e.g., PostgreSQL 16 `societysphere_dev`), prior test runs or concurrent suites leave residual rows in `society_subscriptions` and `platform_invoices`. Tests asserting exact row counts or batch sizes without scoping were prone to candidate saturation.

#### Implementation
1. **Targeted Batch Selection:** Updated `DunningEngineService.detect_dunning_candidates` and `DunningEngineService.process_dunning_batch` to accept an optional `subscription_ids: list[UUID] | None = None` parameter. When provided, the query restricts candidates strictly to the requested subscriptions while retaining `SELECT ... FOR UPDATE SKIP LOCKED`.
2. **Targeted Outbox Drainage:** Updated `DunningEngineService.drain_pending_outbox` to accept `notification_ids: list[UUID] | None = None` and `society_id: UUID | None = None`.
3. **PG Concurrency Suite Isolation:** In [`tests/test_phase21e6_stage2_pg.py`](file:///c:/SocApp/tests/test_phase21e6_stage2_pg.py):
   * `test_concurrent_dunning_reminder_workers_pg` scopes worker execution to `subscription_ids=sub_ids`.
   * `test_concurrent_dunning_suspension_workers_pg` scopes worker execution to `subscription_ids=sub_ids`.
   * Added `test_concurrent_dunning_outbox_workers_pg` testing 4 parallel workers concurrently draining 4 outbox notifications under `SKIP LOCKED` row-level locks, verifying exact single delivery and zero race conditions.
4. **Plan Code Uniqueness:** In [`tests/test_phase21e6_stage1_pg.py`](file:///c:/SocApp/tests/test_phase21e6_stage1_pg.py), updated plan seeding to utilize `plan_code=f"PG_PLAN_{plan_id.hex}"` to eliminate persistent unique constraint collisions.

---

## 3. Comprehensive Verification & Audit Results

### 3.1 Unit & Regression Test Verification

Added 5 dedicated regression test cases in [`tests/test_phase21e6_stage2_dunning.py`](file:///c:/SocApp/tests/test_phase21e6_stage2_dunning.py):
1. `test_provider_timeout_during_day_7_suspension`: Validates that a complete network timeout during provider dispatch does NOT roll back Day 7 suspension; subscription remains `SUSPENDED`, attempt is `SUCCEEDED`, and outbox transitions to `RETRYING`.
2. `test_provider_exception_after_suspension_commits`: Validates that a catastrophic unhandled `RuntimeError` during outbox dispatch preserves `SUSPENDED` status and logs `PlatformSubscriptionHistory` with `DUNNING_GRACE_PERIOD_EXPIRED`.
3. `test_outbox_event_survives_worker_restart_and_succeeds_on_retry`: Validates that if a worker process crashes immediately after database commit (`auto_drain_outbox=False`), the queued outbox record persists in PostgreSQL and is successfully dispatched by a restarted worker.
4. `test_outbox_bounded_retry_exhaustion`: Validates that outbox retries are bounded to 3 attempts, transitioning to `FAILED` upon exhaustion and being ignored by subsequent drain runs.
5. `test_outbox_deduplication_protection`: Validates that redundant dispatch attempts against already `SENT` notifications do not re-dispatch to communication providers.

**Unit Test Execution Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-8.4.2, pluggy-1.6.0
collected 20 items

tests/test_phase21e6_stage2_dunning.py ....................              [100%]
============================== 20 passed in 43.44s ==============================
```

---

### 3.2 Persistent PostgreSQL 16 Concurrency Verification (5 Consecutive Runs)

As mandated by Finding 3, [`tests/test_phase21e6_stage2_pg.py`](file:///c:/SocApp/tests/test_phase21e6_stage2_pg.py) was executed across 5 consecutive runs against persistent PostgreSQL 16 on port 5432:

```
Run 1: 5 passed in 4.89s (Advisory Locks, RLS, Concurrent Reminders, Concurrent Suspensions, Concurrent Outbox Drainage)
Run 2: 5 passed in 5.49s (100% Pass)
Run 3: 5 passed in 7.70s (100% Pass)
Run 4: 5 passed in 4.83s (100% Pass)
Run 5: 5 passed in 5.42s (100% Pass)
```
**Outcome:** **5/5 consecutive runs passed without a single failure or race condition.**

---

### 3.3 Full Phase 21E.6 & Phase 21E Regression Verification

1. **Phase 21E.6 Full Suite (Stage 1 & Stage 2):**
   ```
   tests/test_phase21e6_stage1_pg.py .....
   tests/test_phase21e6_stage1_scheduler.py ...................
   tests/test_phase21e6_stage2_dunning.py ....................
   tests/test_phase21e6_stage2_pg.py .....
   ============================== 48 passed in 63.76s ==============================
   ```

2. **Phase 21E End-to-End Regression Suite (Phase 21E.1 through 21E.6):**
   ```
   ============================= test session starts =============================
   collected 195 items
   195 passed in 167.11s (0:02:47)
   ```
   **Zero regressions across all 195 test cases covering billing models, subscriptions, payments, tax engine, invoicing, credit notes, documents, admin APIs, scheduler, and dunning engine.**

---

### 3.4 Static Analysis & Linter Verification

1. **Ruff Check:**
   ```powershell
   .venv\Scripts\ruff check apps/api/src/subscriptions/automation/dunning_service.py tests/test_phase21e6_stage2_dunning.py tests/test_phase21e6_stage2_pg.py
   # All checks passed!
   ```

2. **MyPy Strict Typing:**
   ```powershell
   .venv\Scripts\mypy apps/api/src/subscriptions/automation/dunning_service.py tests/test_phase21e6_stage2_dunning.py tests/test_phase21e6_stage2_pg.py
   # Success: no issues found in 3 source files
   ```

3. **Alembic Schema Head:**
   ```powershell
   .venv\Scripts\alembic -c apps/api/alembic.ini current
   # 0025_saas_billing_automation (head)
   ```
   Strictly locked at Migration 0025. Zero unauthorized database migrations created.

---

## 4. Verification Check Matrix

| Item | Requirement | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **1** | External provider exceptions isolated from suspension transaction | Unit test `test_provider_timeout_during_day_7_suspension` & `test_provider_exception_after_suspension_commits` | **PASS** |
| **2** | Subscription suspension commits independently of provider availability | Verified `SUSPENDED` status and `PlatformSubscriptionHistory` persist on timeout | **PASS** |
| **3** | Durable transactional outbox records notification intent before dispatch | Reused `Notification` table with `status='QUEUED'` and atomic flush | **PASS** |
| **4** | Decoupled outbox drainage with `SELECT ... FOR UPDATE SKIP LOCKED` | Unit test `test_outbox_event_survives_worker_restart_and_succeeds_on_retry` & PG concurrency test | **PASS** |
| **5** | Bounded exponential backoff retries with terminal `FAILED` status | Unit test `test_outbox_bounded_retry_exhaustion` (max 3 retries) | **PASS** |
| **6** | Idempotency & deduplication on redundant outbox dispatch | Unit test `test_outbox_deduplication_protection` | **PASS** |
| **7** | Candidate isolation on persistent PostgreSQL 16 | Concurrency tests in `test_phase21e6_stage2_pg.py` run with `subscription_ids` filter | **PASS** |
| **8** | 5 consecutive clean runs against persistent PostgreSQL 16 | 5 repeated runs of `test_phase21e6_stage2_pg.py` (5/5 passed each run) | **PASS** |
| **9** | Full Phase 21E regression safety | 195/195 tests passed in 167s across Phase 21E.1–21E.6 | **PASS** |
| **10** | Zero schema drift / Alembic lock preserved | Confirmed head: `0025_saas_billing_automation` | **PASS** |

---

## 5. Architectural Conclusion & Next Steps

All three findings from the Stage 2 Independent QA Audit have been comprehensively remediated, unit-tested, and verified against persistent PostgreSQL 16 concurrency benchmarks.

In accordance with execution instructions:
* Execution is **HALTED**.
* Stage 3 has **NOT** been started.
* SocietySphere Phase 21E.6 Stage 2 is **READY FOR FORMAL ARCHITECTURAL RELEASE AND STAGE 3 AUTHORIZATION**.
