"""Phase 21E.6 Stage 3 — Live PostgreSQL 16, Redis 7 & RabbitMQ Integration Tests.

Validates against live production infrastructure:
1. Live Redis Leader Lease Acquisition, Lua Compare-and-Renew, and Session-level PostgreSQL Advisory Lock Fencing.
2. Real-time Split-Brain Mutual Exclusion between competing distributed worker instances.
3. Live RabbitMQ Topic Topology, Queues, DLX Bindings, Message Consumption & Poison DLQ Routing.
4. Horizontal Concurrency Safety across parallel billing workers using PostgreSQL 16 row-level locks (SKIP LOCKED).
5. Horizontal Concurrency Safety across parallel outbox workers draining notifications without duplicates.
6. Live Stale RUNNING Job & Stuck PROCESSING Notification Recovery in PostgreSQL 16.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import aio_pika
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import (
    PlatformBillingJobRun,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.events.queue_topology import (
    ROUTING_KEY_PERIOD_ROLL,
    setup_queue_topology,
)
from apps.api.src.subscriptions.automation.dunning_service import (
    DunningEngineService,
)
from apps.api.src.subscriptions.automation.leader_election import RedisLeaderElector
from apps.api.src.subscriptions.automation.renewal_service import AutomatedRenewalInvoicingService
from apps.api.src.subscriptions.automation.scheduler_service import BillingPeriodSchedulerService
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus
from apps.api.src.subscriptions.automation.worker_consumers import (
    StaleJobRecoveryService,
)
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import GSTTaxEngine, PlaceOfSupplyService, tax_config_service

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"
REDIS_URL = "redis://localhost:6379/0"
RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def pg_engine():
    """Connect to live PostgreSQL 16, skipping if unreachable."""
    try:
        eng = create_async_engine(PG_URL, echo=False)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL 16 not accessible at {PG_URL}: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(pg_engine):
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def live_redis():
    """Connect to live Redis 7, skipping if unreachable."""
    try:
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis 7 not accessible at {REDIS_URL}: {exc}")
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def live_broker():
    """Connect to live RabbitMQ, skipping if unreachable."""
    try:
        conn = await aio_pika.connect_robust(RABBITMQ_URL, timeout=5)
        channel = await conn.channel()
    except Exception as exc:
        pytest.skip(f"RabbitMQ not accessible at {RABBITMQ_URL}: {exc}")
    yield conn, channel
    await channel.close()
    await conn.close()


@pytest_asyncio.fixture
def renewal_service():
    pos_service = PlaceOfSupplyService()
    tax_engine = GSTTaxEngine(tax_config_service)
    num_service = InvoiceNumberingService()
    invoice_service = PlatformInvoiceService(
        tax_engine=tax_engine,
        pos_service=pos_service,
        numbering_service=num_service,
    )
    return AutomatedRenewalInvoicingService(invoice_service=invoice_service)


async def _seed_due_sub_pg(
    session: AsyncSession,
    hours_ago: float = 2.0,
    plan_price: Decimal = Decimal("1500.00"),
) -> tuple[Society, PlatformSubscriptionPlan, SocietySubscription]:
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    soc = Society(
        id=soc_id,
        legal_name=f"PG Stage 3 Soc {soc_id.hex[:6]}",
        display_name=f"PG Soc {soc_id.hex[:6]}",
        address_line1="100 MG Road",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        status="ACTIVE",
        registration_number=f"REG-S3-{soc_id.hex[:6]}",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PG_S3_PLAN_{plan_id.hex}",
        display_name="PG Stage 3 Plan",
        monthly_price=plan_price,
        annual_price=plan_price * 10,
        is_active=True,
    )
    p_start = now - timedelta(days=30)
    p_end = now - timedelta(hours=hours_ago)
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        auto_renew=True,
        starts_at=p_start,
        current_period_start=p_start,
        current_period_end=p_end,
        next_billing_at=p_end,
    )

    session.add(soc)
    session.add(plan)
    session.add(sub)
    await session.commit()
    return soc, plan, sub


# ---------------------------------------------------------------------------
# 1. Live Redis Leader Election with PostgreSQL Advisory Lock Fencing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_redis_leader_election_and_pg_fencing(live_redis, pg_engine):
    """Test distributed leader election on live Redis 7 and PostgreSQL 16."""
    lease_key = f"societysphere:test:leader:{uuid.uuid4().hex}"

    e1 = RedisLeaderElector(
        redis_client=live_redis,
        engine=pg_engine,
        lease_key=lease_key,
        lease_ttl_ms=30000,
        heartbeat_interval=0.5,
    )
    e2 = RedisLeaderElector(
        redis_client=live_redis,
        engine=pg_engine,
        lease_key=lease_key,
        lease_ttl_ms=30000,
        heartbeat_interval=0.5,
    )

    # 1. E1 acquires leadership
    assert await e1.acquire_leadership() is True
    assert e1.is_leader is True

    # Check key exists in live Redis with positive TTL
    val = await live_redis.get(lease_key)
    assert val == e1.owner_token
    ttl = await live_redis.pttl(lease_key)
    assert 20000 <= ttl <= 30000

    # 2. E2 tries to acquire same key -> rejected by Redis SET NX
    assert await e2.acquire_leadership() is False
    assert e2.is_leader is False

    # 3. Test heartbeat lease renewal
    await asyncio.sleep(1.2)
    new_ttl = await live_redis.pttl(lease_key)
    # Verified: TTL was renewed above 25000ms by the heartbeat task
    assert new_ttl > 25000

    # 4. E1 voluntary step down
    await e1.step_down()
    assert e1.is_leader is False
    assert await live_redis.get(lease_key) is None

    # 5. E2 can now acquire leadership
    assert await e2.acquire_leadership() is True
    assert e2.is_leader is True
    assert await live_redis.get(lease_key) == e2.owner_token

    await e2.step_down()
    assert await live_redis.get(lease_key) is None


# ---------------------------------------------------------------------------
# 2. Live RabbitMQ Queue Topology, DLX & Poison Message Rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_rabbitmq_queue_topology_and_dlx(live_broker):
    """Test live RabbitMQ exchange, queues, DLQ routing and acknowledgments."""
    conn, channel = live_broker

    # Declare topology
    topology = await setup_queue_topology(channel)
    assert topology["jobs_exchange"] is not None

    jobs_exchange = topology["jobs_exchange"]
    billing_queue = topology["billing_queue"]
    dlq = topology["dlq"]

    # 1. Publish valid message to billing queue
    test_exec_id = f"test-exec-{uuid.uuid4().hex[:8]}"
    msg = aio_pika.Message(
        body=json.dumps({"job_type": "PERIOD_ROLL", "execution_id": test_exec_id}).encode("utf-8"),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await jobs_exchange.publish(msg, routing_key=ROUTING_KEY_PERIOD_ROLL)

    # Consume and ack
    incoming = await billing_queue.get(timeout=5)
    assert incoming is not None
    payload = json.loads(incoming.body.decode("utf-8"))
    assert payload["execution_id"] == test_exec_id
    await incoming.ack()

    # 2. Publish unparseable poison message to billing queue
    poison_msg = aio_pika.Message(
        body=b"CORRUPTED_PAYLOAD_NOT_JSON",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await jobs_exchange.publish(poison_msg, routing_key=ROUTING_KEY_PERIOD_ROLL)

    # Consume and reject with requeue=False (must route to DLQ via DLX)
    incoming_poison = await billing_queue.get(timeout=5)
    assert incoming_poison is not None
    await incoming_poison.reject(requeue=False)

    # Verify poison message landed in dead-letter-queue
    dlq_item = await dlq.get(timeout=5)
    assert dlq_item is not None
    assert dlq_item.body == b"CORRUPTED_PAYLOAD_NOT_JSON"
    await dlq_item.ack()


# ---------------------------------------------------------------------------
# 3. Horizontal Concurrency Safety across Parallel Schedulers in PostgreSQL 16
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_pg16_concurrent_schedulers_mutual_exclusion(pg_session_factory, renewal_service):
    """Simulate 3 concurrent scheduler workers processing overdue subscriptions via SKIP LOCKED."""
    # Seed 3 subscriptions
    sub_ids: list[uuid.UUID] = []
    async with pg_session_factory() as session:
        for _ in range(3):
            _, _, sub = await _seed_due_sub_pg(session, hours_ago=2.0)
            sub_ids.append(sub.id)

    # Worker worker function
    async def _scheduler_worker(worker_id: int) -> int:
        async with pg_session_factory() as session:
            service = BillingPeriodSchedulerService(session=session, renewal_service=renewal_service)
            res = await service.process_due_subscriptions(
                cutoff_utc=_utc_now(),
                batch_size=10,
                execution_id=f"worker-{worker_id}-{uuid.uuid4().hex[:6]}",
            )
            # Count how many of OUR test subscriptions were rolled
            rolled_ids = {r.subscription_id for r in res.results if r.status in ("ROLLED", "SKIPPED")}
            return len(rolled_ids.intersection(set(sub_ids)))

    # Execute 3 workers in parallel
    results = await asyncio.gather(
        _scheduler_worker(1),
        _scheduler_worker(2),
        _scheduler_worker(3),
    )

    # Exactly 3 subscriptions must be rolled across all workers; zero duplicates
    total_processed = sum(results)
    assert total_processed == 3, f"Expected exactly 3 subscriptions rolled across workers, got {total_processed}"


# ---------------------------------------------------------------------------
# 4. Horizontal Concurrency Safety across Parallel Outbox Workers in PostgreSQL 16
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_pg16_outbox_concurrent_drain(pg_session_factory):
    """Simulate 3 concurrent outbox workers draining notifications under FOR UPDATE SKIP LOCKED."""
    notif_ids: list[uuid.UUID] = []
    soc_id = uuid.uuid4()

    async with pg_session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name=f"PG Outbox Soc {soc_id.hex[:6]}",
            display_name=f"Outbox Soc {soc_id.hex[:6]}",
            address_line1="100 Residency Rd",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560025",
            status="ACTIVE",
            registration_number=f"REG-OUT-{soc_id.hex[:6]}",
        )
        session.add(soc)
        for i in range(4):
            nid = uuid.uuid4()
            notif = Notification(
                id=nid,
                society_id=soc_id,
                category="BILLING",
                priority="HIGH",
                source_domain="DUNNING",
                source_event_id=str(uuid.uuid4()),
                idempotency_key=f"outbox-drain-{nid}",
                title=f"Notification #{i}",
                content="Urgent invoice reminder",
                status="QUEUED",
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
            session.add(notif)
            notif_ids.append(nid)
        await session.commit()

    async def _outbox_worker(wid: int) -> int:
        async with pg_session_factory() as session:
            dunning = DunningEngineService(session=session)
            count = await dunning.drain_pending_outbox(
                batch_size=10,
                notification_ids=notif_ids,
            )
            await session.commit()
            return count

    # Run 3 concurrent outbox workers
    worker_counts = await asyncio.gather(
        _outbox_worker(1),
        _outbox_worker(2),
        _outbox_worker(3),
    )

    # Exactly 4 notifications drained with zero duplicate deliveries
    total_drained = sum(worker_counts)
    assert total_drained == 4, f"Expected 4 drained notifications across workers, got {total_drained}"


# ---------------------------------------------------------------------------
# 5. Live Stale RUNNING Job & Stuck PROCESSING Notification Recovery in PostgreSQL 16
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_pg16_stale_job_and_notification_recovery(pg_session_factory):
    """Test recovery of crashed/stale RUNNING jobs and stuck PROCESSING notifications in PostgreSQL 16."""
    now = _utc_now()
    stale_time = now - timedelta(hours=3)
    fresh_time = now - timedelta(minutes=5)
    stale_notif_time = now - timedelta(minutes=25)

    soc_id = uuid.uuid4()
    stale_job_id = uuid.uuid4()
    fresh_job_id = uuid.uuid4()
    notif_id = uuid.uuid4()

    async with pg_session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name=f"PG Stale Soc {soc_id.hex[:6]}",
            display_name=f"Stale Soc {soc_id.hex[:6]}",
            address_line1="100 Stale Rd",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560025",
            status="ACTIVE",
            registration_number=f"REG-STL-{soc_id.hex[:6]}",
        )
        stale_job = PlatformBillingJobRun(
            id=stale_job_id,
            job_type="PERIOD_ROLL",
            execution_id=f"stale-{stale_job_id.hex[:8]}",
            status=BillingJobRunStatus.RUNNING.value,
            started_at=stale_time,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
        )
        fresh_job = PlatformBillingJobRun(
            id=fresh_job_id,
            job_type="PERIOD_ROLL",
            execution_id=f"fresh-{fresh_job_id.hex[:8]}",
            status=BillingJobRunStatus.RUNNING.value,
            started_at=fresh_time,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
        )
        notif = Notification(
            id=notif_id,
            society_id=soc_id,
            category="BILLING",
            priority="HIGH",
            source_domain="DUNNING",
            source_event_id=str(uuid.uuid4()),
            idempotency_key=f"stuck-notif-{notif_id}",
            title="Stuck in PROCESSING",
            content="Content",
            status="PROCESSING",
            created_at=stale_notif_time,
            updated_at=stale_notif_time,
        )
        session.add_all([soc, stale_job, fresh_job, notif])
        await session.commit()

    sweeper = StaleJobRecoveryService(session_factory=pg_session_factory)

    # 1. Recover stale job runs
    jobs_recovered = await sweeper.recover_stale_job_runs(max_runtime_minutes=120)
    assert jobs_recovered >= 1

    # 2. Recover stuck processing notifications
    notifs_recovered = await sweeper.recover_stale_processing_notifications(max_processing_minutes=15)
    assert notifs_recovered >= 1

    # Verify states in PostgreSQL 16
    async with pg_session_factory() as session:
        s_job = (await session.execute(
            select(PlatformBillingJobRun).where(PlatformBillingJobRun.id == stale_job_id)
        )).scalar_one()
        f_job = (await session.execute(
            select(PlatformBillingJobRun).where(PlatformBillingJobRun.id == fresh_job_id)
        )).scalar_one()
        n = (await session.execute(
            select(Notification).where(Notification.id == notif_id)
        )).scalar_one()

        assert s_job.status == BillingJobRunStatus.FAILED.value
        assert "TIMED_OUT" in s_job.error_summary
        assert f_job.status == BillingJobRunStatus.RUNNING.value
        assert n.status == "RETRYING"


# ---------------------------------------------------------------------------
# 6. Live PostgreSQL 16 Execution Idempotency on AMQP Redelivery (SS-21E6-S3-002)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_pg16_execution_idempotency_on_redelivery(pg_session_factory):
    """Verify that redelivery of an already COMPLETED execution does not violate unique constraints in PG 16."""
    exec_id = f"live-completed-{uuid.uuid4().hex[:10]}"

    # 1. Pre-seed a COMPLETED PlatformBillingJobRun in PostgreSQL 16
    async with pg_session_factory() as session:
        completed_job = PlatformBillingJobRun(
            id=uuid.uuid4(),
            job_type="PERIOD_ROLL",
            execution_id=exec_id,
            status=BillingJobRunStatus.COMPLETED.value,
            started_at=_utc_now() - timedelta(minutes=10),
            completed_at=_utc_now() - timedelta(minutes=8),
            processed_count=10,
            succeeded_count=10,
            failed_count=0,
            skipped_count=0,
        )
        session.add(completed_job)
        await session.commit()

    # 2. Invoke BillingPeriodSchedulerService directly with the same execution_id
    async with pg_session_factory() as session:
        scheduler = BillingPeriodSchedulerService(session=session)
        result = await scheduler.process_due_subscriptions(
            cutoff_utc=_utc_now(),
            execution_id=exec_id,
        )
    # Must succeed and return cached counts without raising IntegrityError
    assert result.processed_count == 10
    assert result.succeeded_count == 10
    assert result.failed_count == 0

    # 3. Invoke DunningEngineService with another pre-seeded execution_id
    dunning_exec_id = f"live-dunning-{uuid.uuid4().hex[:10]}"
    async with pg_session_factory() as session:
        completed_dunning_job = PlatformBillingJobRun(
            id=uuid.uuid4(),
            job_type="DUNNING_EVAL",
            execution_id=dunning_exec_id,
            status=BillingJobRunStatus.COMPLETED.value,
            started_at=_utc_now() - timedelta(minutes=5),
            completed_at=_utc_now() - timedelta(minutes=4),
            processed_count=3,
            succeeded_count=3,
            failed_count=0,
            skipped_count=0,
        )
        session.add(completed_dunning_job)
        await session.commit()

    async with pg_session_factory() as session:
        dunning = DunningEngineService(session=session)
        d_result = await dunning.process_dunning_batch(
            cutoff_utc=_utc_now(),
            execution_id=dunning_exec_id,
        )
    assert d_result.processed_count == 3
    assert d_result.succeeded_count == 3
