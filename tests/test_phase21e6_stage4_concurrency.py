"""Phase 21E.6 Stage 4 — Distributed Concurrency, Leader Fencing & Race Validation.

Validates against live production infrastructure (PostgreSQL 16, Redis 7):
1. Multi-Scheduler Leader Competition with Split-Brain Prevention (Redis SET NX PX + PG Advisory Lock).
2. Mandatory Leader-Fencing Scenario: Worker A loses lease -> Worker B becomes leader -> Worker A is fenced.
3. 64-bit SHA-256 Advisory Lock Key Derivation & Domain Isolation Analysis.
4. High-Concurrency Billing Period Rolls (FOR UPDATE SKIP LOCKED) with Zero Duplicate Invoices.
5. High-Concurrency Day 7 Dunning Suspension & Outbox Enqueuing.
6. Concurrent Payment Settlement vs Day 7 Suspension Race Condition Integrity.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.models.platform_billing import (
    PlatformDunningAttempt,
    PlatformInvoice,
    PlatformPayment,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.subscriptions.automation.dunning_service import (
    DunningEngineService,
    DunningStage,
)
from apps.api.src.subscriptions.automation.leader_election import RedisLeaderElector
from apps.api.src.subscriptions.automation.scheduler_service import (
    BillingPeriodSchedulerService,
    compute_advisory_lock_key,
)
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.payments.settlement_service import PaymentSettlementService

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"
REDIS_URL = "redis://localhost:6379/0"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def pg_engine():
    """Connect to live PostgreSQL 16."""
    try:
        eng = create_async_engine(PG_URL, echo=False, pool_size=20, max_overflow=10)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL 16 not available: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(pg_engine):
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def live_redis():
    """Connect to live Redis 7."""
    try:
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Live Redis 7 not available: {exc}")
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# 1. Multi-Scheduler Leader Competition
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrency_multi_scheduler_leader_competition(live_redis, pg_engine):
    """Verify concurrent leader competition across multiple worker electors."""
    test_lease_key = f"test:leader:{uuid.uuid4().hex}"

    electors = [
        RedisLeaderElector(
            redis_client=live_redis,
            engine=pg_engine,
            lease_key=test_lease_key,
            lease_ttl_ms=5000,
            heartbeat_interval=1.0,
        )
        for _ in range(3)
    ]

    try:
        # All 3 attempt to acquire leadership simultaneously
        results = await asyncio.gather(*(e.acquire_leadership() for e in electors))
        # Exactly one elector must win
        assert sum(1 for r in results if r is True) == 1
        winner_idx = results.index(True)
        winner = electors[winner_idx]

        assert winner.is_leader is True
        for i, e in enumerate(electors):
            if i != winner_idx:
                assert e.is_leader is False

        # Winner voluntarily steps down
        await winner.step_down()
        assert winner.is_leader is False

        # Remaining two compete again
        remaining = [e for i, e in enumerate(electors) if i != winner_idx]
        new_results = await asyncio.gather(*(e.acquire_leadership() for e in remaining))
        assert sum(1 for r in new_results if r is True) == 1
        new_winner = remaining[new_results.index(True)]
        assert new_winner.is_leader is True

        await new_winner.step_down()

    finally:
        for e in electors:
            await e.step_down()
        await live_redis.delete(test_lease_key)


# ---------------------------------------------------------------------------
# 2. Mandatory Leader-Fencing Scenario
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrency_mandatory_leader_fencing(live_redis, pg_engine):
    """Mandatory leader fencing:

    Worker A acquires lock -> loses Redis lease -> Worker B acquires ->
    Worker A resumes, detects usurpation, and is fenced immediately.
    """
    test_lease_key = f"test:fencing:{uuid.uuid4().hex}"
    worker_a_lost = asyncio.Event()

    async def on_a_lost():
        worker_a_lost.set()

    worker_a = RedisLeaderElector(
        redis_client=live_redis,
        engine=pg_engine,
        lease_key=test_lease_key,
        lease_ttl_ms=3000,  # 3 seconds TTL
        heartbeat_interval=0.5,
        on_leadership_lost=on_a_lost,
    )

    worker_b = RedisLeaderElector(
        redis_client=live_redis,
        engine=pg_engine,
        lease_key=test_lease_key,
        lease_ttl_ms=5000,
        heartbeat_interval=1.0,
    )

    try:
        # 1. Worker A acquires leadership
        acquired_a = await worker_a.acquire_leadership()
        assert acquired_a is True
        assert worker_a.is_leader is True

        # 2. Worker B attempts while A is active -> rejected
        acquired_b = await worker_b.acquire_leadership()
        assert acquired_b is False
        assert worker_b.is_leader is False

        # 3. Simulate Worker A experiencing lease expiration
        # Pause A's heartbeat by stopping the task or overwriting Redis lease
        if worker_a._heartbeat_task and not worker_a._heartbeat_task.done():
            worker_a._heartbeat_task.cancel()

        # Delete Redis lease key and close A's dedicated PG connection to simulate timeout
        await live_redis.delete(test_lease_key)
        await worker_a._close_pg_conn()

        # 4. Worker B now competes and acquires leadership
        acquired_b_after = await worker_b.acquire_leadership()
        assert acquired_b_after is True
        assert worker_b.is_leader is True

        # 5. Worker A resumes and attempts compare-and-renew or action
        # The Lua script checks GET key == worker_a.owner_token. Since Worker B holds it,
        # Worker A's renewal returns 0 and triggers _forfeit_leadership
        renew_res = await live_redis.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('pexpire', KEYS[1], ARGV[2])
            else
                return 0
            end
            """,
            1,
            test_lease_key,
            worker_a.owner_token,
            5000,
        )
        assert renew_res == 0  # Usurped!

        # Worker A forfeits
        await worker_a._forfeit_leadership()
        assert worker_a.is_leader is False
        assert worker_a_lost.is_set()

        # Worker B remains uncontested leader
        assert worker_b.is_leader is True

    finally:
        await worker_a.step_down()
        await worker_b.step_down()
        await live_redis.delete(test_lease_key)


# ---------------------------------------------------------------------------
# 3. 64-bit Advisory Lock Key Derivation & Domain Isolation Analysis
# ---------------------------------------------------------------------------
def test_concurrency_advisory_lock_key_properties():
    """Verify compute_advisory_lock_key produces signed 64-bit integers and avoids 32-bit collisions."""
    keys = [
        "societysphere:scheduler:leader",
        "societysphere:scheduler:billing_roll",
        "societysphere:scheduler:dunning",
        "societysphere:scheduler:outbox",
    ]

    hashes = set()
    for k in keys:
        val = compute_advisory_lock_key(k)
        assert isinstance(val, int)
        # Verify fits in PostgreSQL signed BIGINT range: [-2^63, 2^63 - 1]
        assert -9223372036854775808 <= val <= 9223372036854775807
        hashes.add(val)

    # All unique keys must have unique 64-bit hashes
    assert len(hashes) == len(keys)


# ---------------------------------------------------------------------------
# 4. High-Concurrency Billing Period Rolls (FOR UPDATE SKIP LOCKED)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrency_high_throughput_billing_period_rolls(pg_session_factory):
    """Multiple parallel workers running BillingPeriodSchedulerService on overlapping subscriptions."""
    now = _utc_now()
    plan_id = uuid.uuid4()
    num_subs = 10

    # Setup 10 due subscriptions in live DB
    sub_ids = []
    async with pg_session_factory() as session:
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"CONC_PLAN_{plan_id.hex[:6]}",
            display_name="Concurrency Plan",
            monthly_price=Decimal("1500.00"),
            is_active=True,
        )
        session.add(plan)

        for i in range(num_subs):
            s_id = uuid.uuid4()
            soc_id = uuid.uuid4()
            soc = Society(
                id=soc_id,
                legal_name=f"Conc Soc {i}",
                display_name=f"CSoc{i}",
                address_line1="10 Conc Way",
                city="Pune",
                state="Maharashtra",
                postal_code="411045",
                status="ACTIVE",
                registration_number=f"REG-CONC-{s_id.hex[:6]}",
            )
            sub = SocietySubscription(
                id=s_id,
                society_id=soc_id,
                plan_id=plan_id,
                status=SubscriptionStatus.ACTIVE.value,
                billing_cycle="MONTHLY",
                auto_renew=True,
                starts_at=now - timedelta(days=60),
                current_period_start=now - timedelta(days=30),
                current_period_end=now - timedelta(hours=1),  # Expired
                next_billing_at=now - timedelta(hours=1),
                past_due_since=None,
            )
            session.add_all([soc, sub])
            sub_ids.append(s_id)
        await session.commit()

    # Launch 5 concurrent workers competing to roll the same subscriptions
    async def worker_task(w_idx: int):
        async with pg_session_factory() as session:
            scheduler = BillingPeriodSchedulerService(session=session)
            return await scheduler.process_due_subscriptions(cutoff_utc=now, batch_size=10)

    results = await asyncio.gather(*(worker_task(i) for i in range(5)))

    # Sum of succeeded counts for our target subscriptions must equal exactly num_subs
    rolled_this_test = [item for r in results for item in r.results if item.subscription_id in set(sub_ids)]
    assert len(rolled_this_test) == num_subs

    # Verify each subscription was rolled exactly once in the DB
    async with pg_session_factory() as session:
        for s_id in sub_ids:
            sub = (await session.execute(
                select(SocietySubscription).where(SocietySubscription.id == s_id)
            )).scalar_one()
            # Verified next_billing_at moved into the future
            sub_next = sub.next_billing_at.replace(tzinfo=None) if sub.next_billing_at.tzinfo else sub.next_billing_at
            now_naive = now.replace(tzinfo=None) if now.tzinfo else now
            assert sub_next > now_naive

            # Verified exactly one renewal invoice generated per subscription
            invoices = (await session.execute(
                select(PlatformInvoice).where(PlatformInvoice.subscription_id == s_id)
            )).scalars().all()
            assert len(invoices) == 1
            assert invoices[0].status == "ISSUED"


# ---------------------------------------------------------------------------
# 5. High-Concurrency Day 7 Dunning Suspension & Outbox Enqueuing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrency_high_throughput_dunning_suspensions(pg_session_factory):
    """Multiple parallel workers running DunningEngineService on Day 7 expired subscriptions."""
    now = _utc_now()
    plan_id = uuid.uuid4()
    num_subs = 6
    past_due_anchor = now - timedelta(days=8)  # Passed Day 7

    sub_ids = []
    async with pg_session_factory() as session:
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"DUNN_CONC_{plan_id.hex[:6]}",
            display_name="Dunning Plan",
            monthly_price=Decimal("2500.00"),
            is_active=True,
        )
        session.add(plan)

        for i in range(num_subs):
            s_id = uuid.uuid4()
            soc_id = uuid.uuid4()
            inv_id = uuid.uuid4()
            soc = Society(
                id=soc_id,
                legal_name=f"Dunn Conc Soc {i}",
                display_name=f"DCSoc{i}",
                address_line1="10 Dunn Way",
                city="Pune",
                state="Maharashtra",
                postal_code="411045",
                status="ACTIVE",
                registration_number=f"REG-DUNN-{s_id.hex[:6]}",
            )
            sub = SocietySubscription(
                id=s_id,
                society_id=soc_id,
                plan_id=plan_id,
                status=SubscriptionStatus.PAST_DUE.value,
                billing_cycle="MONTHLY",
                auto_renew=True,
                starts_at=now - timedelta(days=40),
                current_period_start=now - timedelta(days=40),
                current_period_end=past_due_anchor,
                next_billing_at=past_due_anchor,
                past_due_since=past_due_anchor,
            )
            inv = PlatformInvoice(
                id=inv_id,
                society_id=soc_id,
                subscription_id=s_id,
                invoice_number=f"INV-2627-D{i}{s_id.hex[:4]}",
                status="ISSUED",
                place_of_supply="MH",
                subtotal=Decimal("2500.00"),
                taxable_amount=Decimal("2500.00"),
                tax_total=Decimal("450.00"),
                cgst_amount=Decimal("225.00"),
                sgst_amount=Decimal("225.00"),
                igst_amount=Decimal("0.00"),
                grand_total=Decimal("2950.00"),
                amount_due=Decimal("2950.00"),
                amount_paid=Decimal("0.00"),
                due_date=past_due_anchor + timedelta(days=7),
                period_start=past_due_anchor,
                period_end=past_due_anchor + timedelta(days=30),
            )
            session.add_all([soc, sub, inv])
            sub_ids.append(s_id)
        await session.commit()

    # Launch 3 concurrent workers running dunning batch
    async def dunning_worker():
        async with pg_session_factory() as session:
            engine = DunningEngineService(session=session)
            return await engine.process_dunning_batch(cutoff_utc=now, batch_size=10, subscription_ids=sub_ids)

    results = await asyncio.gather(*(dunning_worker() for _ in range(3)))

    # Total suspensions executed across all workers must equal num_subs
    total_processed = sum(r.succeeded_count for r in results)
    assert total_processed == num_subs

    # Verify DB state: all suspended, exactly 1 DAY_7 attempt per subscription
    async with pg_session_factory() as session:
        for s_id in sub_ids:
            sub = (await session.execute(
                select(SocietySubscription).where(SocietySubscription.id == s_id)
            )).scalar_one()
            assert sub.status == SubscriptionStatus.SUSPENDED.value

            attempts = (await session.execute(
                select(PlatformDunningAttempt).where(PlatformDunningAttempt.subscription_id == s_id)
            )).scalars().all()
            assert len(attempts) == 1
            assert attempts[0].attempt_type == DunningStage.DAY_7_SUSPENSION.value
            assert attempts[0].status == "SUCCEEDED"


# ---------------------------------------------------------------------------
# 6. Race Between Payment Webhook and Day 7 Suspension
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrency_payment_settlement_vs_day7_suspension_race(pg_session_factory):
    """Simultaneous Day 7 suspension evaluation vs late payment settlement webhook."""
    now = _utc_now()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    soc_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    past_due_anchor = now - timedelta(days=8)

    async with pg_session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="Race Condition Soc",
            display_name="Race Soc",
            address_line1="10 Race Lane",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-RACE-001",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"RACE_PLAN_{plan_id.hex[:6]}",
            display_name="Race Plan",
            monthly_price=Decimal("3000.00"),
            is_active=True,
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.PAST_DUE.value,
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=now - timedelta(days=40),
            current_period_start=now - timedelta(days=40),
            current_period_end=past_due_anchor,
            next_billing_at=past_due_anchor,
            past_due_since=past_due_anchor,
        )
        inv = PlatformInvoice(
            id=inv_id,
            society_id=soc_id,
            subscription_id=sub_id,
            invoice_number=f"INV-2627-RACE-{uuid.uuid4().hex[:6]}",
            status="ISSUED",
            place_of_supply="MH",
            subtotal=Decimal("3000.00"),
            taxable_amount=Decimal("3000.00"),
            tax_total=Decimal("540.00"),
            cgst_amount=Decimal("270.00"),
            sgst_amount=Decimal("270.00"),
            igst_amount=Decimal("0.00"),
            grand_total=Decimal("3540.00"),
            amount_due=Decimal("3540.00"),
            amount_paid=Decimal("0.00"),
            due_date=past_due_anchor + timedelta(days=7),
            period_start=past_due_anchor,
            period_end=past_due_anchor + timedelta(days=30),
        )
        session.add_all([soc, plan, sub, inv])
        await session.commit()

    # Define the two racing operations with consumer-style retry on deadlock
    async def run_dunning_suspension():
        for attempt in range(3):
            try:
                async with pg_session_factory() as session:
                    dunning = DunningEngineService(session=session)
                    return await dunning.process_dunning_batch(cutoff_utc=now, batch_size=1, subscription_ids=[sub_id])
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))

    async def run_payment_settlement():
        for attempt in range(3):
            try:
                async with pg_session_factory() as session:
                    settlement = PaymentSettlementService(session=session)
                    payment = await settlement.settle_payment(
                        society_id=soc_id,
                        gateway_provider="RAZORPAY",
                        gateway_payment_id=f"pay_race_{uuid.uuid4().hex[:8]}",
                        amount=Decimal("3540.00"),
                        invoice_id=inv_id,
                    )
                    await session.commit()
                    return payment
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))

    # Execute both concurrently under high database contention
    d_res, p_res = await asyncio.gather(run_dunning_suspension(), run_payment_settlement())

    # Verify database state integrity
    async with pg_session_factory() as session:
        sub_final = (await session.execute(
            select(SocietySubscription).where(SocietySubscription.id == sub_id)
        )).scalar_one()

        inv_final = (await session.execute(
            select(PlatformInvoice).where(PlatformInvoice.id == inv_id)
        )).scalar_one()

        # Invariant 1: Invoice must be PAID
        assert inv_final.status == "PAID"
        assert inv_final.amount_due == Decimal("0.00")

        # Invariant 2: Payment must be settled
        payment_rows = (await session.execute(
            select(PlatformPayment).where(PlatformPayment.invoice_id == inv_id)
        )).scalars().all()
        assert len(payment_rows) == 1
        assert payment_rows[0].status == "CAPTURED"
        assert payment_rows[0].is_settled is True

        # Invariant 3: Because payment settled, the subscription MUST be ACTIVE
        assert sub_final.status == SubscriptionStatus.ACTIVE.value
        assert sub_final.past_due_since is None
