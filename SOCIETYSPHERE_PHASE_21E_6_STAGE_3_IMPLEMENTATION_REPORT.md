# SocietySphere Phase 21E.6 Stage 3: Background Schedulers, Outbox Dispatcher & Notification Pipeline
## Formal Implementation & Verification Report

**Author**: Principal SaaS Architect & Senior Distributed Systems Engineer  
**Date**: November 3, 2026  
**Status**: COMPLETE & VERIFIED  
**Alembic Head**: `0025_saas_billing_automation` (Locked & Strictly Preserved)  
**Verification Summary**: 65/65 Phase 21E.6 Tests Passing | 212/212 Full Phase 21E Regression Tests Passing | 0 Lint / 0 Type Errors  

---

## 1. Executive Summary

Phase 21E.6 Stage 3 completes the production-grade background scheduling, messaging, and outbox distribution layer for SocietySphere's multi-tenant SaaS billing platform. Building directly on the locked foundations of Stage 1 (Billing Period Roll Engine) and Stage 2 (Dunning Engine & Grace Period Suspension), Stage 3 transitions the platform from manually invoked workflows into an autonomous, resilient, distributed event-driven system.

### Key Architectural Pillars Delivered:
1. **Single Unified Worker Entry Point (`python -m apps.api.src.workers.runner`)**:
   - Structured around `asyncio.TaskGroup` supervising four independent tasks: (a) Distributed Scheduler Leader, (b) Billing Operations Consumer, (c) Notification Outbox Consumer, and (d) Stale Job Sweeper.
   - Comprehensive crash isolation: a recoverable error or transient network blip in one task never terminates unrelated tasks.
   - Robust OS signal trapping (`SIGINT`, `SIGTERM`) with cooperative task cancellation and deterministic resource disposal.
2. **Dual-Tier Leader Election with Split-Brain Fencing**:
   - Primary lease in Redis 7 (`SET NX PX`, 30s TTL, 10s heartbeat) managed via atomic Lua renewal and release scripts.
   - Secondary split-brain fencing via PostgreSQL 16 session-level advisory locks (`pg_try_advisory_lock`) maintained over a dedicated physical connection.
   - Instantaneous leadership abdication upon lease renewal failure or PostgreSQL connection severance.
3. **Resilient RabbitMQ Topology (`aio-pika`)**:
   - Durable topic exchange `societysphere.jobs` and dead-letter exchange `societysphere.dlx`.
   - Dedicated queues: `billing-operations-queue` (priority 10, max priority 10, DLX configured) and `notification-outbox-queue` (DLX configured), bound to `dead-letter-queue`.
   - Transactional acknowledgment semantics: manual `ack()` strictly after database commit, `nack(requeue=True)` for transient database locks, and immediate `reject(requeue=False)` for unparseable poison messages.
4. **Resilient Notification Outbox Pipeline**:
   - Drains the Phase 20 `Notification` table using `SELECT FOR UPDATE SKIP LOCKED` for lock contention avoidance.
   - Bounded retries (maximum 3 attempts) with exponential backoff (`30s * 2^attempt`) and terminal dead-lettering (`status="FAILED"`).
5. **Autonomous Stale Job & Notification Recovery**:
   - Background sweeper recovering crashed `PlatformBillingJobRun` records stranded in `RUNNING` for over 120 minutes $\to$ marked `FAILED` with `TIMED_OUT`.
   - Stuck outbox notifications in `PROCESSING` for over 15 minutes $\to$ reset to `RETRYING`.
6. **Multi-Tenant Security & Zero-Schema Drift**:
   - PostgreSQL 16 `FORCE ROW LEVEL SECURITY` strictly preserved with `set_db_tenant_context()`.
   - Zero database migrations introduced; Alembic head remains locked at `0025_saas_billing_automation`.

---

## 2. Component Implementation Breakdown

```
+--------------------------------------------------------------------------------------------------+
|                                    UnifiedWorkerRunner                                           |
|                           (asyncio.TaskGroup / Graceful Signals)                                 |
+--------------------------------------------------------------------------------------------------+
          |                               |                                |
          v                               v                                v
+--------------------+        +-----------------------+        +-----------------------+
|  Scheduler Leader  |        |  Billing Ops Consumer |        | Outbox Dispatcher     |
|  - Redis Lease     |        |  - Consume AMQP Jobs  |        |  - Drain Notification |
|  - PG Advisory Lock|        |  - Period Roll Batch  |        |  - Provider Dispatch  |
|  - Crons / Tickers |        |  - Dunning Batch      |        |  - 3x Bounded Retry   |
+--------------------+        +-----------------------+        +-----------------------+
          |                               ^                                ^
          | [Publish AMQP Messages]       |                                |
          +-------------------------------+--------------------------------+
                                          |
                              +-----------------------+
                              | Stale Sweeper Service |
                              | - Stale Jobs > 120m   |
                              | - Stuck Notifs > 15m  |
                              +-----------------------+
```

### 2.1 Distributed Leader Election (`apps/api/src/subscriptions/automation/leader_election.py`)
- **Redis Lease**: Acquired with key `societysphere:scheduler:leader`, 30,000ms TTL, owner token UUID, and 10.0s heartbeat background loop.
- **Atomic Lua Scripts**:
  - `COMPARE_AND_RENEW_LUA`: Verifies token match before extending TTL by 30,000ms.
  - `COMPARE_AND_RELEASE_LUA`: Verifies token match before removing key on graceful step-down.
- **PostgreSQL Session Advisory Lock**:
  - Employs dedicated `AsyncConnection` running `SELECT pg_try_advisory_lock(987654321)`.
  - Guarantees mutual exclusion even during Redis partitions or multi-node split-brain scenarios.
  - Upon lease expiration or loss, immediately clears `is_leader=False`, releases advisory lock, and stops job publication.

### 2.2 AMQP Queue Topology (`apps/api/src/events/queue_topology.py`)
- **Exchanges**:
  - `societysphere.jobs`: Topic exchange, durable.
  - `societysphere.dlx`: Direct exchange, durable.
- **Queues**:
  - `billing-operations-queue`: Durable, `x-dead-letter-exchange="societysphere.dlx"`, `x-dead-letter-routing-key="dlq"`, `x-max-priority=10`. Bound to `billing.period_roll` and `billing.dunning_eval`.
  - `notification-outbox-queue`: Durable, `x-dead-letter-exchange="societysphere.dlx"`, `x-dead-letter-routing-key="dlq"`. Bound to `outbox.drain`.
  - `dead-letter-queue`: Durable, bound to `societysphere.dlx` with key `dlq`.

### 2.3 Distributed Scheduler Runner (`apps/api/src/subscriptions/automation/scheduler_runner.py`)
- Supervised by leader state. Only executes scheduling loops while `leader_elector.is_leader` is `True`.
- **Interval Timers**:
  - Hourly at minute 0 (`3600s`): Publishes `billing.period_roll` with execution ID.
  - Every 4 hours (`14400s`): Publishes `billing.dunning_eval`.
  - Every 30 seconds (`30s`): Publishes `outbox.drain`.
  - Every 30 minutes (`1800s`): Runs `StaleJobRecoveryService.run_sweeper_pass()`.

### 2.4 Worker Consumers (`apps/api/src/subscriptions/automation/worker_consumers.py`)
- **`BillingOperationsConsumer`**:
  - Consumes from `billing-operations-queue`.
  - Processes `PERIOD_ROLL` via `BillingPeriodSchedulerService.process_due_subscriptions()`.
  - Processes `DUNNING_EVAL` via `DunningEngineService.process_dunning_batch()`.
  - Explicit acknowledgments: commits DB transaction, then calls `message.ack()`. Catches unparseable JSON or schema errors and calls `message.reject(requeue=False)` to forward to DLQ.
- **`NotificationOutboxConsumer`**:
  - Consumes from `notification-outbox-queue` or falls back to direct timer drain.
  - Calls `recover_stale_processing_notifications()`, then invokes `dunning_service.drain_pending_outbox()`.
  - Explicitly commits the database session and acknowledges message.
- **`StaleJobRecoveryService`**:
  - `recover_stale_job_runs(max_runtime_minutes=120)`: Transitions `PlatformBillingJobRun` records in `RUNNING` status beyond 120 minutes to `FAILED` with `error_summary="EXECUTION_TIMED_OUT"`.
  - `recover_stale_processing_notifications(max_processing_minutes=15)`: Transitions `Notification` records stranded in `PROCESSING` beyond 15 minutes back to `RETRYING`.

### 2.5 Unified Worker Entry Point (`apps/api/src/workers/runner.py`)
- Executable via:
  ```bash
  python -m apps.api.src.workers.runner
  ```
- Configurable environment flags:
  - `RUN_SCHEDULER_LEADER=true`
  - `RUN_BILLING_CONSUMER=true`
  - `RUN_OUTBOX_CONSUMER=true`
  - `RUN_STALE_SWEEPER=true`
- Registers signal listeners (`SIGINT`, `SIGTERM`) on Unix and Windows, cleanly cancelling tasks, awaiting sub-service termination, stepping down leadership, closing AMQP channels, and terminating Redis/DB engines without leaking file descriptors.

### 2.6 Worker Observability (`apps/api/src/workers/observability.py`)
- **`WorkerObservabilityService`**:
  - `get_metrics()`: Exposes node ID, scheduler leadership status, queue depths, active job runs, oldest pending outbox notification age, and total sent/retrying/failed counts.
  - Strict PII masking: No tenant payment details, recipient phone numbers, or email addresses are leaked into health dumps or logs.

---

## 3. Comprehensive Verification & Test Results

### 3.1 Worker Unit Test Suite (`tests/test_phase21e6_stage3_workers.py`)
All 12 isolated unit tests passed in 6.58 seconds:
```
tests/test_phase21e6_stage3_workers.py::test_redis_leader_lease_acquisition PASSED        [ 8%]
tests/test_phase21e6_stage3_workers.py::test_split_brain_prevention_pg_advisory PASSED   [16%]
tests/test_phase21e6_stage3_workers.py::test_leadership_loss_detection PASSED            [25%]
tests/test_phase21e6_stage3_workers.py::test_multiple_competing_schedulers PASSED        [33%]
tests/test_phase21e6_stage3_workers.py::test_scheduler_runner_triggers PASSED            [41%]
tests/test_phase21e6_stage3_workers.py::test_billing_operations_consumer_ack PASSED      [50%]
tests/test_phase21e6_stage3_workers.py::test_billing_operations_consumer_poison_message PASSED [58%]
tests/test_phase21e6_stage3_workers.py::test_notification_outbox_consumer_drain PASSED   [66%]
tests/test_phase21e6_stage3_workers.py::test_stale_job_recovery PASSED                     [75%]
tests/test_phase21e6_stage3_workers.py::test_stale_processing_notification_recovery PASSED [83%]
tests/test_phase21e6_stage3_workers.py::test_worker_observability PASSED                 [91%]
tests/test_phase21e6_stage3_workers.py::test_unified_worker_runner_graceful_shutdown PASSED [100%]
```

### 3.2 Live Multi-Service Integration Test Suite (`tests/test_phase21e6_stage3_pg.py`)
Executed directly against live PostgreSQL 16 (port 5432), Redis 7 (port 6379), and RabbitMQ (port 5672):
```
tests/test_phase21e6_stage3_pg.py::test_live_redis_leader_election_and_pg_fencing PASSED [ 20%]
tests/test_phase21e6_stage3_pg.py::test_live_rabbitmq_queue_topology_and_dlx PASSED      [ 40%]
tests/test_phase21e6_stage3_pg.py::test_live_pg16_concurrent_schedulers_mutual_exclusion PASSED [ 60%]
tests/test_phase21e6_stage3_pg.py::test_live_pg16_outbox_concurrent_drain PASSED         [ 80%]
tests/test_phase21e6_stage3_pg.py::test_live_pg16_stale_job_and_notification_recovery PASSED [100%]
```

### 3.3 Full Phase 21E.6 Test Suite (Stages 1, 2, and 3)
Complete validation of all billing automation, dunning, and worker systems across 65 tests:
```
======================= 65 passed in 103.68s (0:01:43) ========================
- Stage 1 PG & Scheduler Tests: 19 passed
- Stage 2 Dunning & PG Tests: 29 passed
- Stage 3 Worker & PG Tests: 17 passed
```

### 3.4 Full Phase 21E Regression Test Suite
Execution of all 23 test suites spanning Phase 21E.1 through Phase 21E.6:
```
======================= 212 passed in 394.01s (0:06:34) =======================
Zero failures. Zero regressions across the entire SaaS billing engine.
```

### 3.5 Static Analysis & Type Checking
- **Ruff**: `All checks passed!` (0 lint errors).
- **Mypy**: `Success: no issues found in 7 source files` (0 type errors).
- **Alembic**: `0025_saas_billing_automation (head)` (Zero migrations added, strictly locked).

---

## 4. Architecture Verification Matrix

| Architectural Invariant | Requirement | Verification Result |
| :--- | :--- | :--- |
| **Unified Worker Topology** | Single process entry point with TaskGroup crash isolation | **CONFIRMED** (`runner.py` with 4 isolated supervised tasks) |
| **Scheduler Frequencies** | Hourly roll, 4h dunning, 30s outbox, 30m stale sweeper | **CONFIRMED** (Deterministic intervals in `scheduler_runner.py`) |
| **Dual-Tier Leader Election** | Redis lease + PG session advisory lock fencing | **CONFIRMED** (`RedisLeaderElector` validated on live Redis 7 + PG 16) |
| **AMQP Topology & DLQ** | Topic jobs exchange, DLX direct exchange, poison DLQ | **CONFIRMED** (`setup_queue_topology` validated on live RabbitMQ) |
| **Outbox Bounded Retries** | Max 3 attempts, exponential backoff, dead-lettering | **CONFIRMED** (`drain_pending_outbox` validated with `FOR UPDATE SKIP LOCKED`) |
| **Crash Recovery** | Stale jobs > 120m $\to$ FAILED; stuck notifs > 15m $\to$ RETRYING | **CONFIRMED** (`StaleJobRecoveryService` live test verified) |
| **Tenant Isolation** | PostgreSQL 16 FORCE RLS preserved with context | **CONFIRMED** (`set_db_tenant_context` respected across workers) |
| **Zero Migration Drift** | No new schema modifications or Alembic migrations | **CONFIRMED** (Alembic head strictly `0025_saas_billing_automation`) |

---

## 5. Artifacts and Source Code Reference

1. Unified Worker Runner: [runner.py](file:///c:/SocApp/apps/api/src/workers/runner.py)
2. Distributed Leader Election: [leader_election.py](file:///c:/SocApp/apps/api/src/subscriptions/automation/leader_election.py)
3. RabbitMQ Topology: [queue_topology.py](file:///c:/SocApp/apps/api/src/events/queue_topology.py)
4. Scheduler Runner: [scheduler_runner.py](file:///c:/SocApp/apps/api/src/subscriptions/automation/scheduler_runner.py)
5. Worker Consumers & Stale Sweeper: [worker_consumers.py](file:///c:/SocApp/apps/api/src/subscriptions/automation/worker_consumers.py)
6. Worker Observability: [observability.py](file:///c:/SocApp/apps/api/src/workers/observability.py)
7. Worker Unit Tests: [test_phase21e6_stage3_workers.py](file:///c:/SocApp/tests/test_phase21e6_stage3_workers.py)
8. Live PG/Redis/RabbitMQ Tests: [test_phase21e6_stage3_pg.py](file:///c:/SocApp/tests/test_phase21e6_stage3_pg.py)

---

## 6. Formal Sign-Off

Phase 21E.6 Stage 3 (Background Schedulers, Outbox Dispatcher & Notification Pipeline) is hereby **COMPLETE**, **FULLY VERIFIED**, and **READY FOR FORMAL ARCHITECTURAL REVIEW**.

*No changes to locked Phases 1–20 or Phase 21E Stages 1–2 have been made. Development on Stage 4 has not commenced.*
