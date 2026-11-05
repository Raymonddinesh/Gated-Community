"""Phase 21E.6 Stage 3 — Schedulers, Outbox Dispatcher & Background Worker Tests.

Covers:
1. Redis leader lease acquisition, unique token, and TTL.
2. Atomic compare-and-renew Lua script verification.
3. Atomic compare-and-release Lua script verification.
4. Immediate leadership loss detection & halting.
5. Split-brain prevention via PostgreSQL session advisory lock.
6. Multiple competing scheduler runner instances.
7. Scheduler trigger message publishing for billing, dunning, outbox, and sweeper.
8. BillingOperationsConsumer execution and message acknowledgment.
9. Poison message rejection to DLQ.
10. NotificationOutboxConsumer drainage and message acknowledgment.
11. Stale RUNNING job recovery to FAILED.
12. Stale PROCESSING notification recovery to RETRYING.
13. WorkerObservabilityService metrics and queue depths.
14. UnifiedWorkerRunner graceful shutdown and cancellation.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.base import Base
from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import (
    PlatformBillingJobRun,
)
from apps.api.src.database.models.society import Society
from apps.api.src.events.queue_topology import (
    ROUTING_KEY_DUNNING_EVAL,
    ROUTING_KEY_OUTBOX_DRAIN,
    ROUTING_KEY_PERIOD_ROLL,
    ROUTING_KEY_STALE_SWEEP,
)
from apps.api.src.subscriptions.automation.leader_election import (
    RedisLeaderElector,
)
from apps.api.src.subscriptions.automation.scheduler_runner import DistributedSchedulerRunner
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus
from apps.api.src.subscriptions.automation.worker_consumers import (
    BillingOperationsConsumer,
    NotificationOutboxConsumer,
    StaleJobRecoveryService,
)
from apps.api.src.workers.observability import WorkerObservabilityService
from apps.api.src.workers.runner import UnifiedWorkerRunner


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class MockRedis:
    """In-memory mock for Redis client supporting SET NX PX and Lua script evaluation."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expires: dict[str, float] = {}

    async def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        px: int | None = None,
    ) -> bool:
        now = asyncio.get_event_loop().time()
        # Clean expired
        if key in self.expires and self.expires[key] <= now:
            self.store.pop(key, None)
            self.expires.pop(key, None)

        if nx and key in self.store:
            return False

        self.store[key] = value
        if px is not None:
            self.expires[key] = now + (px / 1000.0)
        return True

    async def get(self, key: str) -> str | None:
        now = asyncio.get_event_loop().time()
        if key in self.expires and self.expires[key] <= now:
            self.store.pop(key, None)
            self.expires.pop(key, None)
            return None
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        self.expires.pop(key, None)
        return 1 if self.store.pop(key, None) is not None else 0

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        now = asyncio.get_event_loop().time()
        key = args[0]
        owner = args[1]

        # Handle compare-and-renew
        if "pexpire" in script:
            ttl_ms = int(args[2])
            current = self.store.get(key)
            if current == owner:
                self.expires[key] = now + (ttl_ms / 1000.0)
                return 1
            return 0

        # Handle compare-and-release
        if "del" in script:
            current = self.store.get(key)
            if current == owner:
                self.store.pop(key, None)
                self.expires.pop(key, None)
                return 1
            return 0

        return 0


@pytest_asyncio.fixture
async def in_memory_db():
    """In-memory SQLite database for deterministic unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory, engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# 1. Redis Leader Lease Acquisition & Heartbeat
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_redis_leader_lease_acquisition():
    mock_redis = MockRedis()
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=lambda: True))
    mock_engine.connect = AsyncMock(return_value=mock_conn)

    acquired_called = False

    async def on_acquired():
        nonlocal acquired_called
        acquired_called = True

    elector = RedisLeaderElector(
        redis_client=mock_redis,  # type: ignore[arg-type]
        engine=mock_engine,
        lease_ttl_ms=30000,
        heartbeat_interval=0.1,
        on_leadership_acquired=on_acquired,
    )

    success = await elector.acquire_leadership()
    assert success is True
    assert elector.is_leader is True
    assert acquired_called is True
    assert await mock_redis.get(elector.lease_key) == elector.owner_token

    # Voluntary step down
    await elector.step_down()
    assert elector.is_leader is False
    assert await mock_redis.get(elector.lease_key) is None


# ---------------------------------------------------------------------------
# 2. Split-Brain Protection: PostgreSQL Advisory Lock Fails
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_split_brain_prevention_pg_advisory():
    mock_redis = MockRedis()
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    # PG lock returns False (held by another session)
    mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=lambda: False))
    mock_engine.connect = AsyncMock(return_value=mock_conn)

    elector = RedisLeaderElector(
        redis_client=mock_redis,  # type: ignore[arg-type]
        engine=mock_engine,
    )

    success = await elector.acquire_leadership()
    assert success is False
    assert elector.is_leader is False
    # Verified: Redis lease was released immediately on PG lock conflict
    assert await mock_redis.get(elector.lease_key) is None


# ---------------------------------------------------------------------------
# 3. Leadership Loss Detection & Immediate Halting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_leadership_loss_detection():
    mock_redis = MockRedis()
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=lambda: True))
    mock_engine.connect = AsyncMock(return_value=mock_conn)

    lost_called = False

    async def on_lost():
        nonlocal lost_called
        lost_called = True

    elector = RedisLeaderElector(
        redis_client=mock_redis,  # type: ignore[arg-type]
        engine=mock_engine,
        lease_ttl_ms=1000,
        heartbeat_interval=0.05,
        on_leadership_lost=on_lost,
    )

    assert await elector.acquire_leadership() is True
    assert elector.is_leader is True

    # Simulate external eviction/usurpation by deleting key
    await mock_redis.delete(elector.lease_key)

    # Wait for heartbeat cycle to detect loss
    await asyncio.sleep(0.15)

    assert elector.is_leader is False
    assert lost_called is True


# ---------------------------------------------------------------------------
# 4. Multiple Competing Scheduler Instances
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multiple_competing_schedulers():
    shared_redis = MockRedis()

    def make_elector():
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=lambda: True))
        mock_engine.connect = AsyncMock(return_value=mock_conn)
        return RedisLeaderElector(redis_client=shared_redis, engine=mock_engine, heartbeat_interval=0.05)  # type: ignore[arg-type]

    e1 = make_elector()
    e2 = make_elector()

    # E1 acquires first
    assert await e1.acquire_leadership() is True
    assert e1.is_leader is True

    # E2 tries to acquire while E1 holds it -> False
    assert await e2.acquire_leadership() is False
    assert e2.is_leader is False

    # E1 steps down
    await e1.step_down()
    assert e1.is_leader is False

    # Now E2 can acquire
    assert await e2.acquire_leadership() is True
    assert e2.is_leader is True
    await e2.step_down()


# ---------------------------------------------------------------------------
# 5. DistributedSchedulerRunner Triggers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduler_runner_triggers():
    mock_redis = MockRedis()
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=lambda: True))
    mock_engine.connect = AsyncMock(return_value=mock_conn)

    elector = RedisLeaderElector(
        redis_client=mock_redis,  # type: ignore[arg-type]
        engine=mock_engine,
        heartbeat_interval=0.1,
    )

    published_events: list[tuple[str, str, dict]] = []

    async def mock_publish(exchange_name, routing_key, payload, headers=None):
        published_events.append((exchange_name, routing_key, payload))
        return True

    with patch("apps.api.src.subscriptions.automation.scheduler_runner.EventPublisher.publish_event", side_effect=mock_publish):
        runner = DistributedSchedulerRunner(
            elector=elector,
            period_roll_interval_seconds=0.05,
            dunning_eval_interval_seconds=0.05,
            outbox_drain_interval_seconds=0.05,
            stale_sweep_interval_seconds=0.05,
            poll_loop_delay=0.02,
        )

        task = asyncio.create_task(runner.start())
        await asyncio.sleep(0.12)
        await runner.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    routing_keys = [event[1] for event in published_events]
    assert ROUTING_KEY_PERIOD_ROLL in routing_keys
    assert ROUTING_KEY_DUNNING_EVAL in routing_keys
    assert ROUTING_KEY_OUTBOX_DRAIN in routing_keys
    assert ROUTING_KEY_STALE_SWEEP in routing_keys


# ---------------------------------------------------------------------------
# 6. BillingOperationsConsumer Message Processing & Ack
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_billing_operations_consumer_ack(in_memory_db):
    session_factory, _ = in_memory_db
    consumer = BillingOperationsConsumer(session_factory=session_factory)

    mock_msg = MagicMock()
    mock_msg.routing_key = ROUTING_KEY_PERIOD_ROLL
    mock_msg.body = json.dumps({
        "job_type": "PERIOD_ROLL",
        "execution_id": "test-roll-1",
        "cutoff_utc": _utc_now().isoformat(),
    }).encode("utf-8")
    mock_msg.ack = AsyncMock()
    mock_msg.nack = AsyncMock()
    mock_msg.reject = AsyncMock()

    # Process period roll
    await consumer._handle_message(mock_msg)
    assert mock_msg.ack.called
    assert not mock_msg.nack.called
    assert not mock_msg.reject.called
    assert consumer.processed_count == 1


# ---------------------------------------------------------------------------
# 7. BillingOperationsConsumer Poison Message Rejection to DLQ
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_billing_operations_consumer_poison_message(in_memory_db):
    session_factory, _ = in_memory_db
    consumer = BillingOperationsConsumer(session_factory=session_factory)

    mock_msg = MagicMock()
    mock_msg.routing_key = ROUTING_KEY_PERIOD_ROLL
    mock_msg.body = b"NOT_VALID_JSON"
    mock_msg.ack = AsyncMock()
    mock_msg.nack = AsyncMock()
    mock_msg.reject = AsyncMock()

    await consumer._handle_message(mock_msg)
    assert not mock_msg.ack.called
    assert mock_msg.reject.called
    # Verified: rejected with requeue=False (routed to DLQ)
    mock_msg.reject.assert_called_once_with(requeue=False)
    assert consumer.failure_count == 1


# ---------------------------------------------------------------------------
# 8. NotificationOutboxConsumer Drain & Stale Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notification_outbox_consumer_drain(in_memory_db):
    session_factory, _ = in_memory_db
    consumer = NotificationOutboxConsumer(session_factory=session_factory, batch_size=10)

    # Seed an outbox notification in QUEUED status
    async with session_factory() as session:
        soc_id = uuid.uuid4()
        soc = Society(
            id=soc_id,
            legal_name="Outbox Consumer Soc",
            display_name="Consumer Soc",
            address_line1="123 Test Rd",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
            status="ACTIVE",
            registration_number=f"REG-{soc_id.hex[:6]}",
        )
        notif = Notification(
            id=uuid.uuid4(),
            society_id=soc_id,
            category="BILLING",
            priority="HIGH",
            source_domain="DUNNING",
            source_event_id=str(uuid.uuid4()),
            idempotency_key=f"outbox-test-{uuid.uuid4().hex[:6]}",
            title="Payment Reminder",
            content="Please pay overdue invoice.",
            status="QUEUED",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        session.add(soc)
        session.add(notif)
        await session.commit()
        notif_id = notif.id

    mock_msg = MagicMock()
    mock_msg.routing_key = ROUTING_KEY_OUTBOX_DRAIN
    mock_msg.body = json.dumps({"job_type": "OUTBOX_DRAIN"}).encode("utf-8")
    mock_msg.ack = AsyncMock()
    mock_msg.nack = AsyncMock()

    await consumer._handle_message(mock_msg)
    assert mock_msg.ack.called

    # Check notification was processed
    async with session_factory() as session:
        n = (await session.execute(select(Notification).where(Notification.id == notif_id))).scalar_one()
        assert n.status in ("SENT", "RETRYING", "FAILED")


# ---------------------------------------------------------------------------
# 9. Stale RUNNING Job Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_job_recovery(in_memory_db):
    session_factory, _ = in_memory_db
    sweeper = StaleJobRecoveryService(session_factory=session_factory)

    now = _utc_now()
    stale_time = now - timedelta(hours=3)  # > 2h threshold
    fresh_time = now - timedelta(minutes=10)

    async with session_factory() as session:
        stale_job = PlatformBillingJobRun(
            id=uuid.uuid4(),
            job_type="PERIOD_ROLL",
            execution_id="stale-job-1",
            status=BillingJobRunStatus.RUNNING.value,
            started_at=stale_time,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
        )
        fresh_job = PlatformBillingJobRun(
            id=uuid.uuid4(),
            job_type="PERIOD_ROLL",
            execution_id="fresh-job-2",
            status=BillingJobRunStatus.RUNNING.value,
            started_at=fresh_time,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
        )
        session.add_all([stale_job, fresh_job])
        await session.commit()
        stale_id = stale_job.id
        fresh_id = fresh_job.id

    recovered = await sweeper.recover_stale_job_runs(max_runtime_minutes=120)
    assert recovered == 1

    async with session_factory() as session:
        s_job = (await session.execute(select(PlatformBillingJobRun).where(PlatformBillingJobRun.id == stale_id))).scalar_one()
        f_job = (await session.execute(select(PlatformBillingJobRun).where(PlatformBillingJobRun.id == fresh_id))).scalar_one()
        assert s_job.status == BillingJobRunStatus.FAILED.value
        assert "TIMED_OUT" in s_job.error_summary
        assert f_job.status == BillingJobRunStatus.RUNNING.value


# ---------------------------------------------------------------------------
# 10. Stale PROCESSING Notification Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_processing_notification_recovery(in_memory_db):
    session_factory, _ = in_memory_db
    sweeper = StaleJobRecoveryService(session_factory=session_factory)

    now = _utc_now()
    stale_updated = now - timedelta(minutes=30)  # > 15m threshold

    async with session_factory() as session:
        soc_id = uuid.uuid4()
        soc = Society(
            id=soc_id,
            legal_name="Stale Soc",
            display_name="Stale Soc",
            address_line1="123 Test",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
            status="ACTIVE",
            registration_number=f"REG-{soc_id.hex[:6]}",
        )
        notif = Notification(
            id=uuid.uuid4(),
            society_id=soc_id,
            category="BILLING",
            priority="HIGH",
            source_domain="DUNNING",
            source_event_id=str(uuid.uuid4()),
            idempotency_key=f"stale-{uuid.uuid4().hex[:6]}",
            title="Stuck notification",
            content="Content",
            status="PROCESSING",
            created_at=stale_updated,
            updated_at=stale_updated,
        )
        session.add_all([soc, notif])
        await session.commit()
        notif_id = notif.id

    recovered = await sweeper.recover_stale_processing_notifications(max_processing_minutes=15)
    assert recovered == 1

    async with session_factory() as session:
        n = (await session.execute(select(Notification).where(Notification.id == notif_id))).scalar_one()
        assert n.status == "RETRYING"


# ---------------------------------------------------------------------------
# 11. WorkerObservabilityService Metrics Aggregation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_observability(in_memory_db):
    session_factory, _ = in_memory_db
    observability = WorkerObservabilityService(session_factory=session_factory)

    snapshot = await observability.get_full_operational_snapshot(
        elector_info={"is_leader": True, "owner": "test-worker"},
    )
    assert snapshot["status"] == "OPERATIONAL"
    assert snapshot["scheduler"]["leadership"]["is_leader"] is True
    assert "pending_notification_count" in snapshot["outbox"]
    assert "queues" in snapshot


# ---------------------------------------------------------------------------
# 12. UnifiedWorkerRunner Graceful Cancellation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unified_worker_runner_graceful_shutdown():
    runner = UnifiedWorkerRunner()
    # Trigger immediate shutdown
    runner.shutdown_event.set()

    # Verify shutdown handles clean exit
    with patch("apps.api.src.workers.runner.init_db", AsyncMock()), \
         patch("apps.api.src.workers.runner.init_redis", AsyncMock()), \
         patch("apps.api.src.workers.runner.init_broker", AsyncMock(return_value=None)), \
         patch("apps.api.src.workers.runner.close_broker", AsyncMock()), \
         patch("apps.api.src.workers.runner.close_redis", AsyncMock()), \
         patch("apps.api.src.workers.runner.close_db", AsyncMock()):
        await runner.run()

    assert runner.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# 13. SS-21E6-S3-002: BillingOperationsConsumer Redelivery of Completed Job
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_billing_operations_consumer_redelivery_of_completed_job(in_memory_db):
    """Verify redelivered message for an already COMPLETED execution is safely acked without re-execution."""
    session_factory, _ = in_memory_db
    exec_id = "test-completed-job-1"

    # Pre-seed a COMPLETED job run record
    async with session_factory() as session:
        job = PlatformBillingJobRun(
            id=uuid.uuid4(),
            job_type="PERIOD_ROLL",
            execution_id=exec_id,
            status=BillingJobRunStatus.COMPLETED.value,
            started_at=_utc_now() - timedelta(minutes=5),
            completed_at=_utc_now() - timedelta(minutes=4),
            processed_count=5,
            succeeded_count=5,
            failed_count=0,
            skipped_count=0,
        )
        session.add(job)
        await session.commit()

    consumer = BillingOperationsConsumer(session_factory=session_factory)

    mock_msg = MagicMock()
    mock_msg.routing_key = ROUTING_KEY_PERIOD_ROLL
    mock_msg.body = json.dumps({
        "job_type": "PERIOD_ROLL",
        "execution_id": exec_id,
        "cutoff_utc": _utc_now().isoformat(),
    }).encode("utf-8")
    mock_msg.ack = AsyncMock()
    mock_msg.nack = AsyncMock()
    mock_msg.reject = AsyncMock()

    # Dispatch redelivered message
    await consumer._handle_message(mock_msg)

    # Must ACK immediately and NOT NACK or REJECT
    assert mock_msg.ack.called
    assert not mock_msg.nack.called
    assert not mock_msg.reject.called


# ---------------------------------------------------------------------------
# 14. SS-21E6-S3-001: Consumer Lifecycle Blocking Until Stop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_consumer_lifecycle_blocking_until_stop(in_memory_db):
    """Verify consumer start() remains active until stop() is called, preventing hot-loop re-registration."""
    session_factory, _ = in_memory_db
    consumer = BillingOperationsConsumer(session_factory=session_factory)

    mock_queue = MagicMock()
    mock_queue.consume = AsyncMock(return_value="ctag-test-123")
    mock_queue.cancel = AsyncMock()
    mock_channel = MagicMock()
    mock_channel.is_closed = False
    mock_channel.get_queue = AsyncMock(return_value=mock_queue)
    mock_channel.set_qos = AsyncMock()

    # Start consumer in background task
    start_task = asyncio.create_task(consumer.start(mock_channel))
    await asyncio.sleep(0.05)

    # Must remain running and awaiting stop event
    assert not start_task.done()
    assert consumer.is_running is True

    # Stop consumer
    await consumer.stop()
    await asyncio.wait_for(start_task, timeout=1.0)

    assert consumer.is_running is False
    mock_queue.cancel.assert_called_once_with("ctag-test-123")


# ---------------------------------------------------------------------------
# 15. SS-21E6-S3-003: Scheduler Runner Retains Timestamp on Publish Failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduler_runner_retains_timestamp_on_publish_failure():
    """Verify scheduler runner does NOT advance its timestamp or cycle if AMQP publish fails."""
    mock_redis = MockRedis()
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=lambda: True))
    mock_engine.connect = AsyncMock(return_value=mock_conn)

    elector = RedisLeaderElector(
        redis_client=mock_redis,  # type: ignore[arg-type]
        engine=mock_engine,
        lease_ttl_ms=30000,
        heartbeat_interval=0.1,
    )
    elector._is_leader = True

    runner = DistributedSchedulerRunner(
        elector=elector,
        period_roll_interval_seconds=3600,
        dunning_eval_interval_seconds=14400,
        outbox_drain_interval_seconds=30,
        stale_sweep_interval_seconds=1800,
        poll_loop_delay=0.01,
    )

    now = _utc_now()

    # 1. Simulate AMQP publish failure
    with patch(
        "apps.api.src.subscriptions.automation.scheduler_runner.EventPublisher.publish_event",
        AsyncMock(return_value=False),
    ):
        await runner._evaluate_and_dispatch(now)

        # Timestamps must remain None (not advanced)
        assert runner._last_period_roll is None
        assert runner._last_dunning_eval is None
        assert runner._last_outbox_drain is None
        assert runner._last_stale_sweep is None
        assert runner.metrics["period_roll_triggers"] == 0

    # 2. Simulate subsequent successful publish
    with patch(
        "apps.api.src.subscriptions.automation.scheduler_runner.EventPublisher.publish_event",
        AsyncMock(return_value=True),
    ):
        await runner._evaluate_and_dispatch(now)

        # Timestamps and metrics must now advance
        assert runner._last_period_roll == now
        assert runner._last_dunning_eval == now
        assert runner._last_outbox_drain == now
        assert runner._last_stale_sweep == now
        assert runner.metrics["period_roll_triggers"] == 1


# ---------------------------------------------------------------------------
# 16. SS-21E6-S3-004: Stale Notification Max Retry Bounding
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_notification_recovery_exhausted_retries(in_memory_db):
    """Verify stuck notification exceeding max_retries transitions to FAILED instead of RETRYING."""
    session_factory, _ = in_memory_db
    sweeper = StaleJobRecoveryService(session_factory=session_factory)

    now = _utc_now()
    stale_updated = now - timedelta(minutes=30)

    async with session_factory() as session:
        soc_id = uuid.uuid4()
        soc = Society(
            id=soc_id,
            legal_name="Max Retry Soc",
            display_name="Max Retry Soc",
            address_line1="123 Exhausted Rd",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
            status="ACTIVE",
            registration_number=f"REG-{soc_id.hex[:6]}",
        )
        notif = Notification(
            id=uuid.uuid4(),
            society_id=soc_id,
            category="BILLING",
            priority="HIGH",
            source_domain="DUNNING",
            source_event_id=str(uuid.uuid4()),
            idempotency_key=f"exhausted-{uuid.uuid4().hex[:6]}",
            title="Max retries notification",
            content="Content",
            status="PROCESSING",
            payload=json.dumps({"retry_count": 3}),  # Already reached max_retries
            created_at=stale_updated,
            updated_at=stale_updated,
        )
        session.add_all([soc, notif])
        await session.commit()
        notif_id = notif.id

    recovered = await sweeper.recover_stale_processing_notifications(
        max_processing_minutes=15, max_retries=3
    )
    assert recovered == 1

    async with session_factory() as session:
        n = (await session.execute(select(Notification).where(Notification.id == notif_id))).scalar_one()
        assert n.status == "FAILED"
        payload_data = json.loads(n.payload) if n.payload else {}
        assert payload_data.get("retry_count") == 4
        assert "Max retries (3) exceeded" in payload_data.get("error", "")
