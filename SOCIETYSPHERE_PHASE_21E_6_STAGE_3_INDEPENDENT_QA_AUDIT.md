# SocietySphere Phase 21E.6 Stage 3: Background Schedulers, Outbox Dispatcher & Notification Pipeline
## Independent Architectural QA & Security Audit Report

**Auditor**: Independent Principal Distributed Systems Architect, PostgreSQL Security Auditor & Senior Python Engineer  
**Date**: November 3, 2026  
**Execution Mode**: STRICTLY READ-ONLY INDEPENDENT QA  
**Target Codebase**: `c:\SocApp`  
**Current Alembic Head**: `0025_saas_billing_automation` (Locked & Verified)  
**Final Audit Verdict**: **PASS WITH CONDITIONS**  

---

## 1. Executive Summary

This independent architectural review and security audit evaluated the implementation of **Phase 21E.6 Stage 3: Background Schedulers, Outbox Dispatcher & Notification Pipeline**. The scope encompassed distributed leader election, AMQP queue topology, message consumers, transactional outbox dispatching, stale job/notification recovery, worker supervision, and multi-tenant security under PostgreSQL 16.

The audit confirms that the core distributed state and financial idempotency guarantees are **architecturally sound**:
- **Atomic Double-Locking**: Primary Redis lease (`SET NX PX`, 30s TTL, 10s heartbeat) coupled with PostgreSQL 16 session-level advisory lock (`pg_try_advisory_lock`) on a dedicated persistent connection provides deterministic split-brain protection.
- **Financial & Idempotency Invariants**: Subscriptions cannot be double-rolled, duplicate invoices cannot be created (enforced by `uq_platform_invoices_sub_period`), duplicate dunning attempts are prevented (enforced by `uq_platform_dunning_attempts_idempotency`), and outbox notifications cannot be duplicated (enforced by `uq_notifications_society_idempotency`).
- **PostgreSQL 16 Security**: `FORCE ROW LEVEL SECURITY` is strictly enforced on tenant tables. The unprivileged `app_user` role has neither `SUPERUSER` nor `BYPASSRLS`. Tenant context is explicitly injected using `set_db_tenant_context()`.
- **Zero Schema Drift**: Zero migrations were added; Alembic head remains locked at `0025_saas_billing_automation`.

However, the audit identified **two HIGH-severity distributed runtime defects** and **one MEDIUM-severity scheduling defect** that require remediation before Stage 3 is signed off for production deployment:
1. **Consumer Supervision Hot-Loop**: `BillingOperationsConsumer.start()` and `NotificationOutboxConsumer.start()` register queue consumers and return immediately. `UnifiedWorkerRunner._supervise()` executes these in a tight `while not shutdown_event.is_set()` loop, continuously re-registering consumers against RabbitMQ without blocking.
2. **Infinite Poison Requeue on Redelivery of Committed Batches**: If a worker commits a batch run but crashes before RabbitMQ acknowledgement, RabbitMQ redelivers the message with the same `execution_id`. The second worker attempts to insert `PlatformBillingJobRun(execution_id=exec_id)`, failing with a duplicate key violation on `uq_platform_billing_job_runs_exec_id`. `BillingOperationsConsumer` catches this as a generic exception and calls `nack(requeue=True)`, trapping the message in an infinite requeue loop.
3. **Scheduler Cycle Skip on AMQP Publish Failure**: `DistributedSchedulerRunner` updates its timestamp (`_last_period_roll = now`) before verifying successful delivery of the AMQP trigger to RabbitMQ. A transient broker connection failure causes the hourly period roll to be skipped for 3600 seconds.

---

## 2. Comprehensive Area-by-Area Inspection

### 2.1 Leader Election and Fencing
- **Redis Lease Atomicity**: Verified. `RedisLeaderElector.acquire_leadership()` executes `await redis.set(self.lease_key, self.owner_token, nx=True, px=self.lease_ttl_ms)`. This uses native Redis atomic primitives (`SET NX PX`).
- **Owner Token Validation (Compare-and-Renew)**: Verified. `COMPARE_AND_RENEW_LUA` script:
  ```lua
  if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('pexpire', KEYS[1], ARGV[2])
  else
      return 0
  end
  ```
  Only extends TTL if the value in Redis strictly matches `self.owner_token`.
- **Safe Release (Compare-and-Release)**: Verified. `COMPARE_AND_RELEASE_LUA` script:
  ```lua
  if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('del', KEYS[1])
  else
      return 0
  end
  ```
  Prevents deleting a lease that has expired and been acquired by another worker.
- **Dedicated Persistent PostgreSQL Advisory Lock**: Verified. Held on `self._pg_conn = await engine.connect()` using `SELECT pg_try_advisory_lock(:lock_key)`. The connection is dedicated and never returned to the pool while the leader is active.
- **Immediate Leadership Forfeiture**: Verified. If the Redis heartbeat renewal returns `0` (expired or usurped) or if `_pg_conn.execute(SELECT 1)` fails, `_forfeit_leadership()` immediately executes:
  - `self._is_leader = False`
  - Cancels heartbeat task
  - Releases PG advisory lock and closes connection
  - Calls `on_leadership_lost()` callback which signals `DistributedSchedulerRunner` to cease dispatching.
- **Multiple Workers Mutual Exclusion**: Tested and verified on live Redis 7 and PostgreSQL 16. Competing workers fail both at Redis `SET NX` and at PostgreSQL `pg_try_advisory_lock`.

### 2.2 Stale Job Recovery
- **Healthy Long-Running Jobs**: Verified. Normal period roll or dunning evaluation batches execute within 1–10 seconds. The 120-minute threshold provides an ample buffer ($>100\times$ typical batch execution) before marking a job `FAILED`.
- **Abandoned Job Recovery**: Verified. `PlatformBillingJobRun` records in `RUNNING` status with `started_at < now - 120m` are transitioned to `FAILED` with `error_summary="TIMED_OUT: ..."`.
- **Active Outbox Processing Safety**: Verified. Outbox notification dispatch to external providers takes under 10 seconds. The 15-minute threshold ensures in-flight requests are not reclaimed prematurely.
- **Concurrency & Race Condition Prevention**: Verified. Both outbox drainage and stale notification recovery query using `SELECT FOR UPDATE SKIP LOCKED`. Active transactions hold row locks; the sweeper skips locked rows, eliminating deadlocks and update races.
- **Recovery Idempotency**: Verified. Once a record transitions from `RUNNING` $\to$ `FAILED` or `PROCESSING` $\to$ `RETRYING`, subsequent sweeper queries do not match it.

### 2.3 RabbitMQ Acknowledgement and Redelivery
- **Durable Acknowledgement Semantics**:
  - `message.ack()` is strictly invoked after database session commit (`await session.commit()`).
  - `message.reject(requeue=False)` routes unparseable poison messages to `societysphere.dlx` $\to$ `dead-letter-queue`.
- **Exact Redelivery Scenario Evaluation**:
  1. RabbitMQ message received with `execution_id = "exec-1"`.
  2. Database transaction commits: subscriptions rolled, invoices created, `PlatformBillingJobRun` committed.
  3. Worker crashes before RabbitMQ `message.ack()`.
  4. RabbitMQ requeues and redelivers message to Worker 2.
  5. Worker 2 processes the message.
  - **Financial Idempotency**: **PASSED**.
    - No duplicate invoices: `next_billing_at` already moved to the future, and `uq_platform_invoices_sub_period` rejects duplicate period invoices.
    - No duplicate dunning attempts: `uq_platform_dunning_attempts_idempotency` rejects duplicate attempts.
    - No duplicate outbox entries: `uq_notifications_society_idempotency` rejects duplicates.
  - **Consumer Process Flow**: **FAILED (Finding SS-21E6-S3-002)**.
    - Worker 2 attempts `session.add(PlatformBillingJobRun(execution_id="exec-1"))`.
    - PostgreSQL raises `IntegrityError` (`uq_platform_billing_job_runs_exec_id`).
    - Worker 2 catches the exception and executes `await message.nack(requeue=True)`.
    - The message is perpetually redelivered and nacked in an infinite loop.

### 2.4 TaskGroup and Worker Supervision
- **Crash Isolation**: Verified. `asyncio.TaskGroup` manages tasks supervised by `_supervise()`. An unhandled exception in one task is logged and restarted after a 5-second backoff without terminating unrelated tasks.
- **Graceful Shutdown**: Verified. Handlers for `SIGINT` and `SIGTERM` set `runner.shutdown_event`. The event notifies all loops, cancels pending tasks, closes AMQP channels, steps down leadership, and closes Redis/PostgreSQL connections cleanly.
- **Consumer Supervision Loop**: **FAILED (Finding SS-21E6-S3-001)**.
  - `BillingOperationsConsumer.start()` and `NotificationOutboxConsumer.start()` are asynchronous setup functions that return immediately upon registering `queue.consume()`.
  - In `_supervise()`, the coroutine finishes immediately, causing `_supervise` to loop endlessly and call `start()` thousands of times in a tight CPU-bound spin.

### 2.5 PostgreSQL Security and Multi-Tenancy
- **PostgreSQL 16 RLS**: Verified. `platform_dunning_attempts` has `FORCE ROW LEVEL SECURITY` enabled.
- **Role Permissions**: Verified on live PostgreSQL 16.
  - `postgres`: `rolsuper=True`, `rolbypassrls=True`.
  - `app_user`: `rolsuper=False`, `rolbypassrls=False`.
- **Explicit Tenant Context**: Verified. In `DunningEngineService.process_single_subscription()`, `await set_db_tenant_context(self.session, sub.society_id)` is invoked prior to querying or writing to `platform_dunning_attempts`.
- **Cross-Tenant Isolation**: Verified. Verified by live test `test_pg_dunning_attempts_force_rls` where tenant context missing fails closed (0 rows) and cross-tenant reads return `None`.

### 2.6 Observability & Metrics
- **Scheduler Metrics**: Exposes `is_leader`, `owner_token`, `last_successful_period_roll`, `period_roll_lag_seconds`, `last_successful_dunning_eval`, and `dunning_lag_seconds`.
- **Outbox Metrics**: Exposes `pending_notification_count`, `oldest_queued_age_seconds`, `sent_count`, and `failed_dead_letter_count`.
- **Queue Depths**: Queries active depths for `billing-operations-queue`, `notification-outbox-queue`, and `dead-letter-queue`.
- **PII Scrubbing**: Verified. No bank details, customer phone numbers, or emails are included in metrics payloads.
- **Missing Alerts**: Identified 5 critical production alerts missing from the operational topology (Finding SS-21E6-S3-005).

---

## 3. Detailed Audit Findings

```
+--------------------------------------------------------------------------------------------------+
|                                    STAGE 3 AUDIT FINDINGS                                        |
+---------------------+----------+-----------------------------------------------------------------+
| Finding ID          | Severity | Summary                                                         |
+---------------------+----------+-----------------------------------------------------------------+
| SS-21E6-S3-001      | HIGH     | Hot-loop in worker consumer supervision (queue.consume return)  |
| SS-21E6-S3-002      | HIGH     | Infinite poison requeue on redelivery of committed batch run    |
| SS-21E6-S3-003      | MEDIUM   | Scheduler cycle skipped for 1h on transient AMQP publish error  |
| SS-21E6-S3-004      | LOW      | Stale notification recovery does not increment retry counter    |
| SS-21E6-S3-005      | LOW      | Missing HTTP observability endpoints and Prometheus metrics     |
+---------------------+----------+-----------------------------------------------------------------+
```

### Finding SS-21E6-S3-001 (HIGH): Hot-Loop in Worker Consumer Supervision
- **Severity**: HIGH
- **Affected Files**:
  - `apps/api/src/workers/runner.py` (lines 64–88, 168–186)
  - `apps/api/src/subscriptions/automation/worker_consumers.py` (lines 124–133, 229–238)
- **Technical Evidence**:
  In `UnifiedWorkerRunner.run()`:
  ```python
  tg.create_task(
      self._supervise(
          "BillingOperationsConsumer",
          lambda: self.billing_consumer.start(active_channel),
      )
  )
  ```
  In `BillingOperationsConsumer.start(channel)`:
  ```python
  self._consumer_tag = await queue.consume(self._handle_message)
  ```
  `queue.consume()` registers a background consumer with `aio-pika` and returns the consumer tag immediately without blocking.
  In `_supervise()`:
  ```python
  while not self.shutdown_event.is_set():
      try:
          await coro_fn()
          if self.shutdown_event.is_set():
              break
  ```
  Because `coro_fn()` returns immediately, `_supervise()` loops continuously without awaiting an exit condition. This registers duplicate consumers on RabbitMQ in a tight loop, driving CPU usage to 100% and causing broker connection instability.
- **Reproduction Scenario**:
  Launch `UnifiedWorkerRunner` with live RabbitMQ. Query `rabbitmqctl list_consumers`. The consumer count escalates indefinitely within seconds.
- **Recommended Correction**:
  In `BillingOperationsConsumer.start()` and `NotificationOutboxConsumer.start()`, keep the coroutine suspended until shutdown is requested (e.g., `while self._running: await asyncio.sleep(1.0)` or await an internal `asyncio.Event`). Alternatively, have `_supervise` invoke `start()` once and then `await self.shutdown_event.wait()`.

---

### Finding SS-21E6-S3-002 (HIGH): Infinite Poison Requeue on Redelivery of Committed Batches
- **Severity**: HIGH
- **Affected Files**:
  - `apps/api/src/subscriptions/automation/worker_consumers.py` (lines 163–198)
  - `apps/api/src/subscriptions/automation/scheduler_service.py` (lines 485–499)
  - `apps/api/src/subscriptions/automation/dunning_service.py` (lines 966–980)
- **Technical Evidence**:
  When a batch job (`PERIOD_ROLL` or `DUNNING_EVAL`) commits successfully in PostgreSQL, a row in `platform_billing_job_runs` is created with unique `execution_id = exec_id`.
  If the worker process crashes after `session.commit()` but before `message.ack()`, RabbitMQ detects consumer closure and redelivers the message to a surviving worker.
  When the surviving worker invokes `process_due_subscriptions(execution_id=exec_id)`:
  ```python
  job_run = PlatformBillingJobRun(execution_id=exec_id, ...)
  self.session.add(job_run)
  await self.session.flush() # Raises IntegrityError: duplicate key uq_platform_billing_job_runs_exec_id
  ```
  In `BillingOperationsConsumer._handle_message`:
  ```python
  except Exception as exc:
      ...
      await message.nack(requeue=True)
  ```
  The worker nacks the message with `requeue=True`. RabbitMQ immediately redelivers it, causing an infinite failure loop that blocks the consumer queue.
- **Reproduction Scenario**:
  1. Trigger a billing period roll with `execution_id="sched-test-100"`.
  2. Transaction commits. Worker process is killed before `message.ack()`.
  3. Second worker receives redelivered message `"sched-test-100"`.
  4. Worker logs `IntegrityError` and calls `nack(requeue=True)` indefinitely.
- **Recommended Correction**:
  In `BillingOperationsConsumer._handle_message` (or within `process_due_subscriptions` and `process_dunning_batch`), query `PlatformBillingJobRun` for existing `execution_id`:
  ```python
  existing = (await session.execute(
      select(PlatformBillingJobRun).where(PlatformBillingJobRun.execution_id == exec_id)
  )).scalar_one_or_none()
  if existing and existing.status in ("COMPLETED", "FAILED"):
      logger.info("Execution %s already finalized (%s). Acknowledging redelivered message.", exec_id, existing.status)
      await message.ack()
      return
  ```

---

### Finding SS-21E6-S3-003 (MEDIUM): Scheduler Cycle Skip on AMQP Trigger Publish Failure
- **Severity**: MEDIUM
- **Affected Files**:
  - `apps/api/src/subscriptions/automation/scheduler_runner.py` (lines 134–146, 148–159, 161–171)
- **Technical Evidence**:
  In `DistributedSchedulerRunner._evaluate_and_dispatch`:
  ```python
  if (
      self._last_period_roll is None
      or (now - self._last_period_roll).total_seconds() >= self.period_roll_interval
  ):
      self._last_period_roll = now
      self.metrics["period_roll_triggers"] += 1
      await self._publish_trigger(...)
  ```
  `self._last_period_roll` is set to `now` before `_publish_trigger(...)` is called.
  If `_publish_trigger(...)` returns `False` or raises an exception (e.g. RabbitMQ momentary network flap), `_last_period_roll` remains updated.
  As a result, the scheduler will not re-attempt period roll until another 3600 seconds (1 hour) have passed.
- **Reproduction Scenario**:
  1. Scheduler ticks at minute 0.
  2. RabbitMQ broker is briefly unreachable.
  3. `_publish_trigger` fails.
  4. Notice that `_last_period_roll` was updated to `now`; no period roll is triggered for the next 60 minutes.
- **Recommended Correction**:
  Only update `_last_period_roll = now` if `_publish_trigger(...)` succeeds:
  ```python
  if published:
      self._last_period_roll = now
  ```

---

### Finding SS-21E6-S3-004 (LOW): Stale Notification Recovery Does Not Increment Retry Counter
- **Severity**: LOW
- **Affected Files**:
  - `apps/api/src/subscriptions/automation/worker_consumers.py` (lines 79–106)
- **Technical Evidence**:
  In `StaleJobRecoveryService.recover_stale_processing_notifications`:
  ```python
  for notif in stale_notifs:
      notif.status = "RETRYING"
      recovered_count += 1
  ```
  Notifications stuck in `PROCESSING` (>15m) are reset to `RETRYING` without parsing or incrementing `payload["retry_count"]`.
  If a malicious or corrupted notification payload causes a hard worker crash (SIGKILL, segfault, or OOM) during execution, it will be indefinitely recovered every 15 minutes and will never transition to `FAILED`.
- **Recommended Correction**:
  In `recover_stale_processing_notifications`, inspect `notif.payload`, increment `retry_count`, and if `retry_count >= max_retries`, transition the notification status directly to `FAILED`.

---

### Finding SS-21E6-S3-005 (LOW): Missing HTTP Health Endpoints & Operational Alerts
- **Severity**: LOW
- **Affected Files**:
  - `apps/api/src/workers/observability.py`
- **Technical Evidence**:
  `WorkerObservabilityService` aggregates scheduler lag, outbox depth, and DLQ counts into a sanitized snapshot, but does not expose an HTTP route on the FastAPI application for Prometheus scraping or Kubernetes liveness/readiness probes.
- **Recommended Alerts Missing**:
  1. `DLQDepthAlert`: Trigger when `dead-letter-queue` depth $> 0$.
  2. `SchedulerLagAlert`: Trigger when `period_roll_lag_seconds > 7200` or `dunning_lag_seconds > 28800`.
  3. `OutboxBacklogAlert`: Trigger when `oldest_queued_age_seconds > 300` (5 minutes) or `pending_notification_count > 500`.
  4. `LeaderFlappingAlert`: Trigger when `leadership_transitions > 3` in 1 hour.
- **Recommended Correction**:
  Mount `GET /health/workers` or `/api/v1/saas/workers/health` in FastAPI returning `WorkerObservabilityService.get_full_operational_snapshot()`.

---

## 4. Test and Migration Evidence

### 4.1 Infrastructure Environments Under Test
- **PostgreSQL**: `PostgreSQL 16.15 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit`
- **Redis**: `7.4.11` (Alpine Linux)
- **RabbitMQ**: `3.13.7` (Erlang 26.2.5.2)
- **Python Runtime**: `Python 3.11.0 (win32)`
- **Alembic Revision**: `0025_saas_billing_automation (head)` (Verified unchanged)

### 4.2 Test Execution Results
All tests were executed against live infrastructure services. No unexecuted tests are claimed as passing.

| Test Suite File | Tests Executed | Passed | Failed | Skipped | Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `tests/test_phase21e6_stage3_workers.py` | 12 | 12 | 0 | 0 | 6.58s |
| `tests/test_phase21e6_stage3_pg.py` | 5 | 5 | 0 | 0 | 6.43s |
| `tests/test_phase21e6_stage1_pg.py` | 5 | 5 | 0 | 0 | 18.22s |
| `tests/test_phase21e6_stage1_scheduler.py` | 14 | 14 | 0 | 0 | 1.84s |
| `tests/test_phase21e6_stage2_dunning.py` | 24 | 24 | 0 | 0 | 8.35s |
| `tests/test_phase21e6_stage2_pg.py` | 5 | 5 | 0 | 0 | 62.26s |
| **Total Phase 21E.6 Tests** | **65** | **65** | **0** | **0** | **103.68s** |
| **Total Phase 21E Full Regression** | **212** | **212** | **0** | **0** | **394.01s** |

*Skipped tests: 0.*

### 4.3 Static Code Analysis & Type Checking
- **Ruff**: `All checks passed!` (0 lint errors across all Stage 3 files).
- **MyPy**: `Success: no issues found in 7 source files` (0 type errors).

---

## 5. Architectural Quality Matrix

| Dimension | Architectural Standard | Status | Audit Assessment |
| :--- | :--- | :---: | :--- |
| **Mutual Exclusion** | Single active scheduler leader across distributed nodes | **VERIFIED** | Dual Redis lease + PG session advisory lock prevents split-brain |
| **At-Least-Once Delivery** | Manual ack only after DB commit; no message loss | **VERIFIED** | Messages acked after commit; poison messages dead-lettered |
| **Redelivery Idempotency** | Duplicate delivery cannot generate duplicate invoices | **VERIFIED** | Invoices, dunning attempts, and outbox entries are strictly deduplicated |
| **Consumer Supervision** | Workers supervise sub-tasks without tight CPU loops | **DEFECT** | `_supervise` hot-loops due to non-blocking `queue.consume()` (SS-21E6-S3-001) |
| **Batch Rerun Resilience** | Redelivery of committed batch run acknowledged safely | **DEFECT** | Unique constraint on `execution_id` causes infinite requeue loop (SS-21E6-S3-002) |
| **Trigger Reliability** | Transient AMQP partition retries immediately | **DEFECT** | Hourly schedule timestamp set before publish verification (SS-21E6-S3-003) |
| **Tenant Isolation** | Multi-tenant RLS preserved under worker processes | **VERIFIED** | Explicit tenant context set via `set_db_tenant_context()` |
| **Database Schema** | Locked at Alembic migration 0025 | **VERIFIED** | Zero schema drift; no new migration files created |

---

## 6. Audit Verdict & Conditions

### Final Audit Verdict: **PASS WITH CONDITIONS**

Stage 3 implementation demonstrates high architectural rigor in database idempotency, split-brain fencing, and multi-tenant security. However, authorization for production readiness and Stage 4 progression is conditional upon resolving the identified runtime findings.

### Mandatory Remediation Conditions:
1. **Remediate SS-21E6-S3-001 (High)**: Ensure `BillingOperationsConsumer.start()` and `NotificationOutboxConsumer.start()` keep their supervised tasks suspended until worker termination, preventing the `_supervise` hot-loop.
2. **Remediate SS-21E6-S3-002 (High)**: Add pre-execution check in `BillingOperationsConsumer` to detect already-finalized `execution_id` records in `PlatformBillingJobRun` and safely call `message.ack()`.
3. **Remediate SS-21E6-S3-003 (Medium)**: Only advance `self._last_period_roll` and `self._last_dunning_eval` when `EventPublisher.publish_event()` returns `True`.

*Stage 4 must NOT be started until formal architectural authorization is granted.*
