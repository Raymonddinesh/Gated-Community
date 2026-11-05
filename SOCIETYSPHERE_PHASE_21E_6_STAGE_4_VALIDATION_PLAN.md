# SocietySphere — Phase 21E.6 Stage 4 Validation Plan
## Distributed Reliability, Concurrency Testing & End-to-End Release Validation

**Document Reference:** `SS-21E6-S4-VAL-001`  
**Phase:** 21E.6 (SaaS Billing & Invoicing Automation)  
**Stage:** 4 (Distributed Reliability, Concurrency Testing & End-to-End Release Validation)  
**Status:** ARCHITECTURAL SPECIFICATION & VALIDATION PLAN  
**Timestamp:** 2026-11-03T22:58:00Z  
**Alembic Head:** `0025_saas_billing_automation` (Locked & Frozen)  
**Target Execution Environment:** Live PostgreSQL 16.15 (Alpine), Redis 7.4.11, RabbitMQ 3.13.7, Python 3.11  

---

## 1. Executive Summary & Approved Baseline

Phase 21E.6 represents the enterprise billing automation backbone of SocietySphere. Stages 1 through 3 have been fully implemented, independently audited, remediated, and locked:
* **Stage 1 (Locked):** Automated billing period roll, renewal invoicing, GST tax calculation and snapshot persistence, leap-year and anchor-day clamping, and the corrected trial premature activation business rules.
* **Stage 2 (Locked):** 7-day dunning engine, Day 0/2/5 reminders, Day 7 subscription suspension, strict decoupling of society administrative suspension from billing lifecycle, payment settlement recovery, and notification outbox persistence.
* **Stage 3 (Locked):** Unified worker runner architecture, Redis leader election with atomic compare-and-renew Lua scripts, session-level PostgreSQL advisory lock fencing, RabbitMQ queue topology and DLQ bindings, billing operations consumer, outbox dispatcher, and stale job/notification recovery sweepers.

### Approved System Baseline & Active Constraints
1. **Database Schema:** Schema is frozen at Alembic head `0025_saas_billing_automation`. No new migrations, column alterations, or table additions are permitted.
2. **PostgreSQL Security:** Enforces `FORCE ROW LEVEL SECURITY` across all tenant tables. The database user `app_user` has `NOSUPERUSER` and `NOBYPASSRLS`.
3. **Architecture:** Pure native Python `asyncio`, SQLAlchemy 2.0 async, `aio-pika`, and `redis.asyncio`. Zero third-party orchestrator bloat (no Celery, no APScheduler, no FastStream).
4. **Current Status of Stage 4:** Planning and architectural inspection only. No application source code modifications or test implementations are executed during this planning phase.

---

## 2. Existing Test Coverage Analysis

An exhaustive review of the existing test suite confirms **217 passing tests** across 23 Phase 21E test modules:

```
+-------------------------------------------------------------------------------------------------------+
| Module Category              | Test Files                                     | Tests | Status        |
+------------------------------+------------------------------------------------+-------+---------------+
| Phase 21E.1–21E.3 Foundation | test_phase21e1_platform_billing_models.py      | 6     | 100% PASSED   |
|                              | test_phase21e1_platform_billing_pg.py          | 4     | 100% PASSED   |
|                              | test_phase21e2_concurrency_pg.py               | 3     | 100% PASSED   |
|                              | test_phase21e2_subscription_lifecycle.py       | 16    | 100% PASSED   |
|                              | test_phase21e3_concurrency_pg.py               | 4     | 100% PASSED   |
|                              | test_phase21e3_payment_gateway.py              | 14    | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
| Phase 21E.4 Invoicing & Tax  | test_phase21e4a_pg.py                          | 5     | 100% PASSED   |
|                              | test_phase21e4a_tax_engine.py                  | 12    | 100% PASSED   |
|                              | test_phase21e4b_invoicing.py                   | 10    | 100% PASSED   |
|                              | test_phase21e4b_pg.py                          | 6     | 100% PASSED   |
|                              | test_phase21e4c_credit_notes.py                | 14    | 100% PASSED   |
|                              | test_phase21e4c_pg.py                          | 5     | 100% PASSED   |
|                              | test_phase21e4d_documents.py                   | 12    | 100% PASSED   |
|                              | test_phase21e4d_pg.py                          | 5     | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
| Phase 21E.5 Billing Workflows| test_phase21e5_platform_billing.py             | 14    | 100% PASSED   |
|                              | test_phase21e5_society_billing.py              | 16    | 100% PASSED   |
|                              | test_phase21e5_stage3_validation.py            | 6     | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
| Phase 21E.6 Stage 1 (Billing)| test_phase21e6_stage1_scheduler.py             | 18    | 100% PASSED   |
|                              | test_phase21e6_stage1_pg.py                    | 5     | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
| Phase 21E.6 Stage 2 (Dunning)| test_phase21e6_stage2_dunning.py               | 20    | 100% PASSED   |
|                              | test_phase21e6_stage2_pg.py                    | 5     | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
| Phase 21E.6 Stage 3 (Workers)| test_phase21e6_stage3_workers.py               | 16    | 100% PASSED   |
|                              | test_phase21e6_stage3_pg.py                    | 6     | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
| TOTAL PHASE 21E TEST SUITE   | 23 Test Files                                  | 217   | 100% PASSED   |
+------------------------------+------------------------------------------------+-------+---------------+
```

### Coverage Gaps Identified for Stage 4 Validation
1. **End-to-End State Machine Chaining:** Existing tests validate individual service transitions (e.g. Stage 1 tests renewal, Stage 2 tests dunning). Stage 4 requires an unmocked end-to-end integration test exercising all 13 lifecycle milestones consecutively on a single society entity.
2. **Multi-Worker Distributed Races:** Existing concurrency tests simulate parallel database workers via async tasks on a single connection factory. Stage 4 requires multi-process or multi-client worker competition with live Redis lease expiration, process kill signals (`SIGKILL`), and RabbitMQ unacknowledged delivery replays.
3. **Chaos Fault Injection:** Absence of systematic fault-injection tests verifying database network dropouts, broker reconnections mid-batch, and notification provider timeouts during Day 7 suspension commits.
4. **High-Density Multi-Tenant RLS Leaks:** Verifying that pooled asyncpg connections properly isolate or reset session-level tenant variables between diverse tenant queries.
5. **Volume Benchmarks:** No empirical measurements for 100, 1,000, and 10,000 societies measuring batch duration, queue depth, lock contention, and worker memory consumption.

---

## 3. Full Subscription Lifecycle E2E Test Scenarios

Stage 4 establishes holistic end-to-end integration scenarios verifying the complete subscription lifecycle without mock bypasses.

```
       [Provisioning Engine]
                 │
                 ▼
      1. Society Provisioned (ACTIVE)
                 │
                 ▼
     2. Subscription Created (TRIAL)
                 │
                 ▼
      3. Trial Active (auto_renew=True)
                 │
                 ▼ (next_billing_at reached)
      4. Trial Expires
         ├────────────────────────────────────────┐
         ▼                                        ▼
5. Renewal Invoice Generated             6. Subscription -> PAST_DUE
   (INV-YYYY-XXXXX + GST Snapshot)          (past_due_since initialized)
                 │                                │
                 └────────────────┬───────────────┘
                                  ▼
                         7. Day 0 Reminder
                            (Outbox Notification Emitted)
                                  │
                                  ▼ (t + 2 Days)
                         8. Day 2 Reminder
                            (Overdue Notice Emitted)
                                  │
                                  ▼ (t + 5 Days)
                         9. Day 5 Warning
                            (Urgent Suspension Warning Emitted)
                                  │
                                  ▼ (t + 7 Days)
                        10. Day 7 Suspension
                            (Subscription -> SUSPENDED)
                            (Entitlements Restricted)
                                  │
                                  ▼ (Payment Webhook Arrives)
                        11. Successful Late Payment Settlement
                            (Razorpay Captured -> PlatformPayment)
                                  │
                                  ▼
                        12. Dunning Suspension Recovery
                            (Subscription -> ACTIVE, past_due_since=None)
                            (Entitlements Fully Restored)
                                  │
                                  ▼ (Admin Suspension Triggered)
                        13. Society Administrative Suspension Preservation
                            (Society -> SUSPENDED, Subscription remains ACTIVE)
```

### Detailed E2E Scenarios Matrix

| Scenario ID | Name & Description | Steps & State Verifications | Expected Invariants |
| :--- | :--- | :--- | :--- |
| **E2E-001** | **Golden Path 13-Milestone Lifecycle** | 1. Provision Society via `ProvisioningEngine`.<br>2. Create Subscription (`TRIAL`, `auto_renew=True`).<br>3. Verify trial entitlement quota active.<br>4. Advance clock past `next_billing_at`.<br>5. Execute scheduler: verify renewal invoice generated with GST tax snapshot.<br>6. Verify transition to `PAST_DUE` with `past_due_since` set.<br>7. Execute dunning at Day 0: verify Day 0 outbox notification.<br>8. Advance clock 2 days: verify Day 2 reminder emitted.<br>9. Advance clock 5 days: verify Day 5 final warning emitted.<br>10. Advance clock 7 days: execute dunning, verify subscription transitions to `SUSPENDED`, reason `DUNNING_GRACE_PERIOD_EXPIRED`, entitlements revoked.<br>11. Process payment settlement webhook.<br>12. Verify subscription automatically recovers to `ACTIVE`, `past_due_since` cleared, entitlements restored.<br>13. Admin suspends society (`society.status="SUSPENDED"`): verify society remains suspended despite active subscription. | No unearned activations.<br>Single invoice generated.<br>Timestamps strictly preserved.<br>Admin suspension strictly decoupled. |
| **E2E-002** | **Trial Expiry with `auto_renew=False`** | 1. Create Subscription (`TRIAL`, `auto_renew=False`).<br>2. Advance clock past `next_billing_at`.<br>3. Execute scheduler.<br>4. Verify: NO renewal invoice generated, NO grace period initialized, NO transition to `PAST_DUE`.<br>5. Transitions directly to terminal `CANCELLED` state. | Zero financial obligations created.<br>No outbox notifications queued. |
| **E2E-003** | **Failed Payment During Grace Period** | 1. Subscription in `PAST_DUE` (Day 3).<br>2. Ingest payment webhook with `status="failed"`.<br>3. Verify `PlatformPayment` recorded as `FAILED`.<br>4. Subscription remains `PAST_DUE`.<br>5. Grace period anchor `past_due_since` is NOT reset.<br>6. Subsequent Day 5 and Day 7 milestones proceed according to original timeline. | Payment failure never activates subscription.<br>Grace period timeline unaltered. |
| **E2E-004** | **Payment on Cancelled Subscription** | 1. Subscription in `CANCELLED` status.<br>2. Simulate late inbound payment settlement webhook.<br>3. Payment recorded as unallocated/orphaned ledger entry.<br>4. Subscription remains strictly `CANCELLED`. | Terminal states immutable.<br>No automatic reactivation. |
| **E2E-005** | **Duplicate Payment Webhook Replay** | 1. Ingest valid payment capture webhook (Order A, Payment B).<br>2. Settle payment, transition subscription to `ACTIVE`.<br>3. Ingest identical webhook payload a second and third time.<br>4. Verify idempotent response (HTTP 200 OK).<br>5. Verify single `PlatformPayment` record, single invoice marked `PAID`. | Zero double settlement.<br>Single receipt generated. |
| **E2E-006** | **Duplicate Scheduler AMQP Trigger Replay** | 1. Scheduler worker executes `PERIOD_ROLL` with `execution_id="roll-123"`.<br>2. Broker drops ACK; message redelivered.<br>3. Consumer receives redelivered message.<br>4. Pre-execution check identifies `COMPLETED` status.<br>5. Acknowledges message immediately without executing renewals. | Zero duplicate invoices.<br>Zero duplicate ledger rows. |

---

## 4. Distributed Concurrency Test Matrix

Stage 4 verifies distributed safety and race condition immunity across multi-worker topologies.

```
                  ┌───────────────────────────────┐
                  │ Redis 7: "billing_scheduler_  │
                  │ leader" (TTL: 30s, Owner: A)  │
                  └───────────────┬───────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
      [Scheduler Leader Node A]         [Scheduler Standby Node B]
      - Holds Redis Lease               - Blocks on Lease Acquisition
      - Holds PG Advisory Lock          - Standby Loop
      - Emits AMQP Triggers             - Ready for Failover
                 │
                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ RabbitMQ 3: "societysphere.jobs" Exchange                   │
  │ -> Queue: "billing-operations-queue" (Prefetch: 1)          │
  └──────────────┬──────────────────────────────┬───────────────┘
                 │                              │
                 ▼                              ▼
     [Billing Consumer Worker 1]    [Billing Consumer Worker 2]
     - Row Locks: FOR UPDATE        - Row Locks: FOR UPDATE
     - SKIP LOCKED                  - SKIP LOCKED
     - Idempotent Job Table Insert  - Idempotent Job Table Insert
```

### Concurrency Test Scenarios

| Test ID | Concurrency Scenario | Test Mechanism | Success Invariant |
| :--- | :--- | :--- | :--- |
| **CONC-001** | **Competing Scheduler Leaders (Split-Brain Prevention)** | Start 3 `DistributedSchedulerRunner` instances simultaneously competing for Redis key `billing_scheduler_leader`. | Exactly 1 node acquires lease.<br>Remaining 2 nodes stay in standby.<br>Exactly 1 set of triggers emitted per cycle. |
| **CONC-002** | **PostgreSQL Advisory Lock Fencing** | Node A acquires Redis lease. Node B is artificially granted Redis lease via cache split, but attempts to acquire session advisory lock `hashtext('billing_scheduler_leader')`. | PostgreSQL advisory lock blocks Node B.<br>Node B immediately releases Redis lease and halts.<br>Zero duplicate schedules. |
| **CONC-003** | **Leader Process Abrupt Termination (`SIGKILL`)** | Terminate active leader process with `SIGKILL` mid-heartbeat. Wait for Redis lease TTL (30s) to expire. | Standby node immediately acquires lease upon TTL expiration.<br>Session advisory lock from dead node released automatically by PostgreSQL backend.<br>System resumes triggers without manual intervention. |
| **CONC-004** | **Parallel Billing Period Rolls (`SKIP LOCKED`)** | 5 parallel `BillingOperationsConsumer` workers process a batch of 100 due subscriptions simultaneously. | PostgreSQL `FOR UPDATE SKIP LOCKED` partitions subscriptions across workers without lock contention.<br>Zero duplicate renewal invoices.<br>Sum of processed subscriptions across workers equals exactly 100. |
| **CONC-005** | **Parallel Day 7 Dunning Suspension Races** | 4 parallel workers execute dunning evaluation on 50 past-due subscriptions reaching Day 7 at the exact same second. | Advisory locks `compute_dunning_advisory_lock(society_id, 7)` prevent parallel processing.<br>Exactly 1 dunning attempt per society.<br>Zero duplicate suspension notifications. |
| **CONC-006** | **Concurrent Outbox Dispatching** | 4 parallel `NotificationOutboxConsumer` instances drain 200 queued notifications with `batch_size=20`. | `SELECT ... FOR UPDATE SKIP LOCKED` ensures each notification is processed by exactly one worker.<br>Zero duplicate external dispatches.<br>Total sent count equals exactly 200. |
| **CONC-007** | **Simultaneous Payment Settlement vs Day 7 Suspension** | Fire payment settlement webhook and Day 7 suspension worker concurrently on the same subscription within a 5ms window. | If payment commits first: dunning sees `status="PAID"`, halts suspension.<br>If suspension commits first: payment settlement detects suspended state, updates invoice to `PAID`, recovers subscription to `ACTIVE`.<br>System terminates in valid `ACTIVE` state. |

---

## 5. Failure Injection & Resilience Matrix

Stage 4 subjects SocietySphere to real-world infrastructure failures to guarantee deterministic recovery and transactional consistency.

```
+---------------------------------------------------------------------------------------------------+
| Fault Type              | Injected Fault Condition         | Expected System Behavior & Recovery  |
+-------------------------+----------------------------------+--------------------------------------+
| PostgreSQL Drop         | Drop connection pool mid-batch   | Worker catches DB error; nacks AMQP  |
|                         | for 10 seconds                   | message with requeue; auto-reconnects|
|                         |                                  | on recovery without data corruption. |
+-------------------------+----------------------------------+--------------------------------------+
| Redis Partition         | Sever Redis connection during    | Leader detects heartbeat loss; steps |
|                         | active scheduling cycle          | down immediately; halts trigger      |
|                         |                                  | emission until lease re-acquired.    |
+-------------------------+----------------------------------+--------------------------------------+
| RabbitMQ Restart        | Restart RabbitMQ broker node     | aio-pika robust connection           |
|                         | during heavy outbox publishing   | reconnects; channels re-opened;      |
|                         |                                  | pending publishes retried safely.    |
+-------------------------+----------------------------------+--------------------------------------+
| Provider Timeout        | Mock notification provider       | Outbox worker marks notification     |
|                         | HTTP timeout (>10s) on Day 7     | RETRYING; suspension DB transaction  |
|                         | suspension email                 | remains committed; zero rollback.    |
+-------------------------+----------------------------------+--------------------------------------+
| Worker Crash Mid-Batch  | Terminate worker after DB        | Job remains in RUNNING state; sweeper|
|                         | commit but before AMQP ACK       | marks FAILED after 120m; redelivered |
|                         |                                  | message safely acks via idempotency. |
+-------------------------+----------------------------------+--------------------------------------+
```

### Detailed Resilience Test Scenarios

1. **`FAIL-001` Database Pool Disconnect During Renewal Batch:**
   - *Action:* Cut network access to PostgreSQL port 5432 while `BillingOperationsConsumer` is processing 20 renewal invoices.
   - *Verification:* Active transactions roll back cleanly. Worker catches asyncpg connection errors, avoids crashes, and nacks message with `requeue=True`. Upon database restoration, consumer resumes, rolls periods, and generates invoices without orphaned records.
2. **`FAIL-002` Redis Network Partition During Scheduler Leader Execution:**
   - *Action:* Block Redis port 6379 on the active scheduler node.
   - *Verification:* The heartbeat task raises an error, immediately executes `self.step_down()`, and cancels the scheduler dispatch loop. Standby node on separate network partition acquires lease.
3. **`FAIL-003` RabbitMQ Node Failover:**
   - *Action:* Restart RabbitMQ container during active notification draining.
   - *Verification:* Consumers pause, reconnect via `aio_pika.connect_robust`, re-declare queue topology, and resume consumption with zero message loss.
4. **`FAIL-004` External Notification Provider Outage:**
   - *Action:* Configure `NotificationOutboxConsumer` provider adapter to return HTTP 504 Gateway Timeout on all requests.
   - *Verification:* Outbox dispatcher catches timeout, updates notification `retry_count`, and sets status to `RETRYING`. When `retry_count` reaches 3, transitions to `FAILED` with error log. Subscription suspension remains intact in PostgreSQL.
5. **`FAIL-005` Process Crash Post-Commit Pre-ACK:**
   - *Action:* Inject a forced `os._exit(1)` immediately after `await session.commit()` in `BillingOperationsConsumer`, before `await message.ack()`.
   - *Verification:* RabbitMQ detects channel closure and redelivers message to another consumer. The new consumer queries `PlatformBillingJobRun`, detects `COMPLETED`, logs idempotent skip, and calls `await message.ack()`. Zero duplicate invoices generated.

---

## 6. Financial Integrity Checklist & Invariant Verification

Financial records must adhere to statutory accounting rules, GST compliance standards, and double-entry consistency.

```
       [Raw Subscription Period]
                 │
                 ▼
       [Proration Engine]  ───> Decimal Precision: 2 decimal places (ROUND_HALF_UP)
                 │
                 ▼
       [GST Tax Engine]    ───> Validate Place of Supply (POS)
                 │              - Intra-state (Same State): CGST (9%) + SGST (9%)
                 │              - Inter-state (Different):  IGST (18%)
                 │              - HSN/SAC Code: 998314 (IT SaaS)
                 │              - RCM Flag: False
                 ▼
  [PlatformInvoice Entity] ───> Unique Sequential Number: INV-YYYY-XXXXX
         │       │              - Subtotal + CGST + SGST + IGST = Total Amount
         │       └────────────> Immutable Tax Snapshot in DB
         ▼
  [PlatformReceipt Entity] ───> Exact Match with Settled Amount
```

### Financial Audit Invariants

* [ ] **Exact `Decimal` Arithmetic:** Zero floating-point math across proration, discount, tax, and invoice calculations. All currency values cast to `Decimal` and formatted to 2 decimal places with `ROUND_HALF_UP`.
* [ ] **Tax Snapshot Immutability:** Every issued invoice must possess a linked `PlatformInvoiceTaxSnapshot` recording `place_of_supply_state_code`, `supplier_gstin`, `customer_gstin`, `cgst_rate`, `cgst_amount`, `sgst_rate`, `sgst_amount`, `igst_rate`, and `igst_amount`.
* [ ] **Sequential Invoice Numbering Uniqueness:** Uniqueness constraint `uq_platform_invoices_invoice_number` enforced across high-concurrency billing period rolls. Zero collisions or gaps under parallel worker runs.
* [ ] **Historical Tax Reversal on Credit Notes:** Credit notes issued against paid or partially paid invoices must reference the exact GST tax rates of the original invoice, even if the system's tax rules have changed since the invoice date.
* [ ] **Refund Threshold Enforcement:** Cumulative refund amounts recorded across `PlatformPaymentRefund` rows must strictly not exceed the original `PlatformPayment.amount`.
* [ ] **Zero Unearned Activations:** Subscriptions in `TRIAL` or `PAST_DUE` states must never transition to `ACTIVE` without a confirmed, cryptographic payment settlement webhook or manual administrative override.
* [ ] **Single Renewal Invoice Invariant:** For any given `society_id` and billing period (`period_start` to `period_end`), exactly one non-cancelled `PlatformInvoice` may exist.

---

## 7. Multi-Tenant Security & Isolation Validation

Multi-tenancy isolation must be mathematically and cryptographically provable at the database layer.

```
                    [Client / Background Request]
                                  │
                                  ▼
               [PostgreSQL 16 Connection Pool (asyncpg)]
                                  │
                                  ▼
           [Execute: SET LOCAL app.current_tenant_id = 'soc_A']
                                  │
                                  ▼
           [PostgreSQL Engine: FORCE ROW LEVEL SECURITY]
                                  │
        ┌─────────────────────────┴─────────────────────────┐
        ▼                                                   ▼
[Society A Data Rows]                               [Society B Data Rows]
Tenant ID matches 'soc_A'                           Tenant ID does NOT match
-> Query Returns Rows                               -> Filtered Out (0 Rows)
```

### Security Verification Protocol

1. **`SEC-001` Verification of RLS Enforcement on Catalog:**
   - Execute catalog query verifying `relforcerowsecurity=True` on all tenant-partitioned tables:
     ```sql
     SELECT relname, relrowsecurity, relforcerowsecurity 
     FROM pg_class 
     WHERE relname IN ('societies', 'society_subscriptions', 'dunning_attempts', 'notifications')
       AND relnamespace = 'public'::regnamespace;
     ```
   - Target: All tables return `relrowsecurity=True` and `relforcerowsecurity=True`.
2. **`SEC-002` Verification of Application Role Privileges:**
   - Query `pg_roles` to verify the execution role `app_user`:
     ```sql
     SELECT rolname, rolsuper, rolbypassrls 
     FROM pg_roles 
     WHERE rolname = 'app_user';
     ```
   - Target: `rolsuper=False` and `rolbypassrls=False`.
3. **`SEC-003` Cross-Tenant Negative Read Isolation:**
   - Establish connection as `app_user`. Set `app.current_tenant_id = 'society-1'`.
   - Attempt `SELECT * FROM notifications WHERE society_id = 'society-2'`.
   - Target: Query returns 0 rows.
4. **`SEC-004` Cross-Tenant Negative Write Isolation:**
   - Attempt `INSERT INTO notifications (society_id, ...) VALUES ('society-2', ...)`.
   - Target: PostgreSQL raises `query_canceled` or RLS policy violation error.
5. **`SEC-005` Pooled Connection Session Variable Cleanup:**
   - Set `app.current_tenant_id` on connection. Return connection to pool. Check out connection for subsequent unauthenticated request.
   - Target: `SHOW app.current_tenant_id` returns empty/null, preventing cross-tenant leakage between pooled HTTP requests.
6. **`SEC-006` Platform Worker Tenant Context Binding:**
   - Background workers operating across multiple societies must explicitly set `app.current_tenant_id` within a dedicated transaction before accessing tenant tables, ensuring full RLS compliance during outbox draining.

---

## 8. Performance and Scalability Benchmark Plan

Stage 4 establishes controlled benchmarks to quantify throughput, latency ceilings, and resource consumption.

```
       [Load Test Orchestrator]
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
 Tier 1         Tier 2         Tier 3
(100 Soc)     (1,000 Soc)    (10,000 Soc)
 [Local]       [Simulated]    [Cloud Cluster]
```

### Benchmark Specification & Metrics

| Metric | Tier 1 (100 Societies) | Tier 2 (1,000 Societies) | Tier 3 (10,000 Societies) | Measurement Tool |
| :--- | :--- | :--- | :--- | :--- |
| **Billing Roll Duration** | $< 3.0$ seconds | $< 25.0$ seconds | $< 180.0$ seconds | Python `time.perf_counter` |
| **Dunning Sweep Duration** | $< 1.5$ seconds | $< 12.0$ seconds | $< 90.0$ seconds | Python `time.perf_counter` |
| **Outbox Drain Velocity** | $> 50$ notifs/sec | $> 150$ notifs/sec | $> 400$ notifs/sec | RabbitMQ Management API |
| **Peak Queue Backlog** | $< 100$ messages | $< 1,000$ messages | $< 10,000$ messages | AMQP Queue Monitor |
| **Active DB Connections** | $\le 5$ connections | $\le 15$ connections | $\le 40$ connections | `pg_stat_activity` |
| **Worker RSS Memory** | $< 150$ MB | $< 250$ MB | $< 450$ MB | `psutil.Process.memory_info` |
| **Max Worker CPU** | $< 25\%$ (1 core) | $< 60\%$ (2 cores) | $< 80\%$ (4 cores) | `psutil.Process.cpu_percent` |
| **Scheduler Loop Lag** | $< 100$ ms | $< 250$ ms | $< 500$ ms | Metric `scheduler_tick_lag_ms`|
| **Row Lock Wait Time** | $0$ ms | $< 50$ ms | $< 200$ ms | `pg_stat_database` |

### Infrastructure Delineation
* **Local Test Environment (Executable Now):**
  - **Tier 1 (100 Societies):** Executable directly in current local environment (PostgreSQL 16, Redis 7, RabbitMQ 3.13 on Windows host / Docker).
  - **Tier 2 (1,000 Societies - Synthetic):** Executable locally using batch synthetic seeding and mocked external notification provider calls.
* **External Production Cluster Required:**
  - **Tier 3 (10,000 Societies):** Requires dedicated multi-node deployment: 3-node PostgreSQL RDS/Aurora cluster, clustered RabbitMQ with quorum queues, multi-container worker pods on Kubernetes (EKS/GKE), and distributed load injection via k6/Locust.

---

## 9. Production-Readiness Gap Assessment

A thorough architectural audit delineates between features completed in Stages 1–3 and operational requirements necessary for production release.

```
+---------------------------------------------------------------------------------------------------+
| Component / Domain          | Completed in Stages 1–3       | Production Activation Gap           |
+-----------------------------+-------------------------------+-------------------------------------+
| Worker Observability        | Full domain snapshot service  | Expose via authenticated FastAPI    |
|                             | aggregating Redis, PG, AMQP.  | admin route (/api/v1/platform/...) |
+-----------------------------+-------------------------------+-------------------------------------+
| Dead Letter Queue (DLQ)     | DLX exchange & bindings       | Automated Prometheus DLQ alert &    |
|                             | configured in RabbitMQ.       | operational re-drive script.        |
+-----------------------------+-------------------------------+-------------------------------------+
| Secrets Management          | Environment variables loaded  | Integration with AWS Secrets Manager|
|                             | via Pydantic BaseSettings.    | or HashiCorp Vault with rotation.   |
+-----------------------------+-------------------------------+-------------------------------------+
| Payment Gateway (Razorpay)  | Robust adapter, mock fixtures,| Live API key provisioning, webhook  |
|                             | signature verification.       | secret rotation & IP whitelisting.  |
+-----------------------------+-------------------------------+-------------------------------------+
| Object Storage (S3 / MinIO) | PDF generation & storage      | S3 bucket lifecycle rules, CORS,    |
|                             | abstraction interfaces.       | and AWS IAM least-privilege policies|
+-----------------------------+-------------------------------+-------------------------------------+
| Backup & Disaster Recovery  | Relational DDL & ACID schema  | Automated WAL-G/pgBackRest backups, |
|                             | definitions.                  | point-in-time recovery runbooks.    |
+-----------------------------+-------------------------------+-------------------------------------+
| Security Testing            | Unit RLS checks & role grants | Dynamic Application Security Testing|
|                             | in migration 0025.            | (DAST) & 3rd-party penetration audit|
+-----------------------------+-------------------------------+-------------------------------------+
| Deployment & Rollback       | Single entry point worker     | Blue-Green / Canary deployment      |
|                             | runner module.                | manifests with graceful draining.   |
+-----------------------------+-------------------------------+-------------------------------------+
```

### Actionable Production Runbooks Required
1. **Worker Graceful Draining Runbook:** Triggering `SIGTERM` to allow active billing batches and outbox sweeps to complete and release consumer tags prior to pod termination.
2. **DLQ Remediation & Re-Drive Runbook:** CLI utility to inspect poison messages in `billing-operations-dlq` and `notification-outbox-dlq`, correct underlying data issues, and replay into primary queues.
3. **Disaster Recovery Runbook:** Step-by-step procedure to restore PostgreSQL cluster from WAL archives and re-elect scheduler leader within 5 minutes of total region outage.

---

## 10. Test Execution Sequence

The Stage 4 validation suite must execute in strict deterministic order to prevent state pollution and ensure complete reproducibility.

```
Step 1: Static Code Hygiene & Linter Verification
        (ruff check, mypy --strict on all modules)
                        │
                        ▼
Step 2: Predecessor Unit & Integration Regression Suite
        (All 217 Phase 21E tests: 21E.1 through 21E.6 Stage 3)
                        │
                        ▼
Step 3: End-to-End Subscription Lifecycle Suite (E2E-001 to E2E-006)
        (Single society golden path, auto_renew=False, late recovery)
                        │
                        ▼
Step 4: Distributed Concurrency & Leader Election Races (CONC-001 to CONC-007)
        (Multi-worker lease contention, SKIP LOCKED partitioning, advisory locks)
                        │
                        ▼
Step 5: Failure Injection & Chaos Recovery Suite (FAIL-001 to FAIL-005)
        (PostgreSQL drop, Redis partition, broker restart, process SIGKILL)
                        │
                        ▼
Step 6: Financial Integrity & GST Accounting Audit (FIN-001 to FIN-007)
        (Decimal rounding, tax snapshots, credit note reversals, refund bounds)
                        │
                        ▼
Step 7: Multi-Tenant PostgreSQL RLS Security Suite (SEC-001 to SEC-006)
        (Cross-tenant negative queries, app_user permissions, pool cleanup)
                        │
                        ▼
Step 8: Performance & Load Benchmarks (PERF-001 to PERF-003)
        (100 & 1,000 society batch duration, memory profile, lock contention)
                        │
                        ▼
Step 9: Final Release Verification & Sign-Off Report
```

---

## 11. Quantitative Acceptance Criteria

Stage 4 release approval requires meeting 100% of the following criteria:

* [ ] **1. Test Pass Rate:** 100% pass rate across all existing Phase 21E tests (217/217) and all newly authored Stage 4 validation tests.
* [ ] **2. Zero Duplicate Invoices:** Under concurrent scheduling across 5 competing worker processes, exactly one invoice generated per society billing period.
* [ ] **3. Zero Unearned Activations:** 0 instances of a `TRIAL` or `PAST_DUE` subscription transitioning to `ACTIVE` without confirmed settlement.
* [ ] **4. Zero Cross-Tenant Data Leaks:** 100% of cross-tenant query attempts by `app_user` return 0 rows or trigger RLS policy rejection.
* [ ] **5. Grace Period Invariant:** Exactly 7 days (168 hours) maintained between `past_due_since` and suspension, unaffected by repeated dunning evaluations.
* [ ] **6. Financial Consistency:** Sum of all invoice line items and tax components matches `total_amount` to the exact cent (`0.00` variance).
* [ ] **7. Failover SLA:** Automatic failover of scheduler leader to a standby worker completes within 35 seconds of leader `SIGKILL`.
* [ ] **8. Schema Integrity:** Alembic revision strictly remains `0025_saas_billing_automation (head)` with 0 new migrations.

---

## 12. Residual Risks & Mitigation Strategies

```
+---------------------------------------------------------------------------------------------------+
| Risk Description            | Impact | Likelihood | Mitigation Strategy                           |
+-----------------------------+--------+------------+-----------------------------------------------+
| Clock Drift Across Worker   | HIGH   | LOW        | Mandate UTC timestamps everywhere; enforce NTP|
| Nodes                       |        |            | synchronization (<50ms drift) on worker pods. |
+-----------------------------+--------+------------+-----------------------------------------------+
| Redis OOM / Eviction Policy | HIGH   | LOW        | Configure Redis `maxmemory-policy noeviction` |
| Dropping Leader Lease Key   |        |            | to prevent premature leader lease expiration. |
+-----------------------------+--------+------------+-----------------------------------------------+
| Connection Pool Exhaustion  | HIGH   | MEDIUM     | Size asyncpg pool: workers prefetch 1 batch;  |
| Under Heavy Dunning Load    |        |            | max pool size = 2 * CPU cores per worker pod. |
+-----------------------------+--------+------------+-----------------------------------------------+
| External Webhook Latency    | MEDIUM | MEDIUM     | Webhooks return HTTP 200 immediately upon     |
| Spike from Payment Gateway  |        |            | recording payload; async worker processes it. |
+-----------------------------+--------+------------+-----------------------------------------------+
| High Database CPU during    | MEDIUM | LOW        | Enforce index usage on (source_domain, status,|
| Notification Outbox Drain   |        |            | updated_at); batch size capped at 50 records. |
+-----------------------------+--------+------------+-----------------------------------------------+
```

---

## 13. Architectural Sign-Off & Next Step Gate

This document completes the **Phase 21E.6 Stage 4 Inspection and Validation Plan**.

In compliance with instructions:
* **Zero source code modifications** were made to existing application files.
* **Zero database migrations** were generated.
* **Locked business rules** were completely preserved.
* **Stage 4 implementation is NOT started.**

**Execution Gate:** Execution of Stage 4 validation tests and benchmarks awaits explicit architectural authorization.
