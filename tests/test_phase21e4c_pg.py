"""Phase 21E.4C — Live PostgreSQL 16 Credit Note Concurrency, Pessimistic Locking & RLS Tests.

Validates against live PostgreSQL 16:
1. Concurrency and Pessimistic Row Locking on PlatformCreditNoteSequence:
   - Parallel workers allocating credit note numbers concurrently serialize on SELECT ... FOR UPDATE.
   - Yields strictly unique, consecutive credit note numbers without race conditions or deadlocks.
2. Unique Constraint Enforcement:
   - Database constraint 'uq_platform_credit_notes_number' prohibits duplicate credit note numbers.
3. Transaction Rollback Atomicity:
   - An uncommitted credit note issuance transaction rolls back sequence progression and leaves credit note in DRAFT.
4. Tenant Isolation with PostgreSQL FORCE ROW LEVEL SECURITY:
   - Unprivileged app_user (NOSUPERUSER NOBYPASSRLS) cannot access another tenant's credit notes,
     credit note items, or immutable tax snapshots stored in PlatformSubscriptionAuditLog.
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformCreditNote,
    PlatformCreditNoteItem,
    PlatformCreditNoteSequence,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.credit_notes.exceptions import (
    CreditNoteExceedsEligibleBalanceException,
)
from apps.api.src.subscriptions.credit_notes.numbering import (
    CreditNoteNumberingService,
    get_financial_year,
)
from apps.api.src.subscriptions.credit_notes.schemas import (
    PlatformCreditNoteCreateDraft,
)
from apps.api.src.subscriptions.credit_notes.service import PlatformCreditNoteService
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
)
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceItemCreate as InvItemCreate,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyService,
    TaxSnapshot,
    TaxSnapshotService,
    tax_config_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21e4c_pg")

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def pg_engine():
    """Connect to live PostgreSQL 16 container, skipping if unreachable."""
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
    """Factory yielding isolated sessions connected to PostgreSQL 16."""
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def ensure_app_user_role(pg_session_factory):
    """Ensure non-superuser app_user role exists with permissions on public schema."""
    async with pg_session_factory() as session:
        await session.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
                        CREATE ROLE app_user NOSUPERUSER NOBYPASSRLS;
                    END IF;
                    GRANT USAGE ON SCHEMA public TO app_user;
                    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
                END
                $$;
                """
            )
        )
        await session.commit()


@pytest_asyncio.fixture
def invoice_service():
    pos_service = PlaceOfSupplyService()
    tax_engine = GSTTaxEngine(tax_config_service)
    num_service = InvoiceNumberingService()
    return PlatformInvoiceService(
        tax_engine=tax_engine,
        pos_service=pos_service,
        numbering_service=num_service,
    )


@pytest_asyncio.fixture
def credit_note_service_factory(pg_session_factory):
    tax_engine = GSTTaxEngine(tax_config_service)
    num_service = CreditNoteNumberingService()

    def _make(session: AsyncSession):
        return PlatformCreditNoteService(
            session=session,
            numbering_service=num_service,
            tax_engine=tax_engine,
        )

    return _make


async def _seed_test_society_and_subscription(
    session: AsyncSession, state: str = "Maharashtra"
) -> tuple[uuid.UUID, uuid.UUID]:
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    now = _utc_now()

    soc = Society(
        id=soc_id,
        legal_name=f"PG Credit Note Test Society {soc_id.hex[:6]}",
        display_name=f"PG CN Soc {soc_id.hex[:6]}",
        address_line1="Test Marine Drive",
        city="Mumbai",
        state=state,
        postal_code="400020",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PG_CN_TEST_{soc_id.hex[:6]}",
        display_name="PG CN Test Plan",
        monthly_price=Decimal("10000.00"),
    )
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status="ACTIVE",
        starts_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    session.add_all([soc, plan, sub])
    await session.commit()
    return soc_id, sub_id


async def _seed_and_finalize_invoice(
    session: AsyncSession,
    invoice_svc: PlatformInvoiceService,
    soc_id: uuid.UUID,
    sub_id: uuid.UUID,
) -> uuid.UUID:
    now = _utc_now()
    payload = PlatformInvoiceCreateDraft(
        society_id=soc_id,
        subscription_id=sub_id,
        billing_cycle="MONTHLY",
        period_start=now,
        period_end=now,
        due_date=date.today(),
        items=[
            InvItemCreate(
                description="Platform SaaS Cloud Hosting Fee",
                unit_price=Decimal("10000.00"),
                sac_code="998314",
            )
        ],
    )
    draft = await invoice_svc.create_draft_invoice(session, payload)
    final = await invoice_svc.finalize_invoice(session, draft.id)
    await session.commit()
    return final.id


# ==============================================================================
# 1. Concurrency & Pessimistic Row Locking on CreditNoteSequence
# ==============================================================================


@pytest.mark.asyncio
async def test_concurrent_credit_note_numbering_sequential_locking(pg_session_factory):
    """Multiple concurrent workers allocating credit note numbers serialize via SELECT ... FOR UPDATE.

    Verifies:
    1. Zero deadlocks or race condition collisions.
    2. Zero duplicate credit note numbers.
    3. Strictly consecutive sequence progression without skipped numbers.
    """
    num_service = CreditNoteNumberingService(prefix="SS-CN")
    num_concurrent_workers = 8
    now = _utc_now()
    fy = get_financial_year(now)

    async def worker_allocate(worker_id: int) -> tuple[str, str]:
        async with pg_session_factory() as session:
            async with session.begin():
                number, allocated_fy = await num_service.allocate_credit_note_number(
                    session=session,
                    transaction_date=now,
                )
                await asyncio.sleep(0.01)  # brief sleep to test locking concurrency
                return number, allocated_fy

    # Launch all workers simultaneously
    results = await asyncio.gather(*(worker_allocate(i) for i in range(num_concurrent_workers)))

    allocated_numbers = [r[0] for r in results]
    allocated_fys = [r[1] for r in results]

    # Verify no duplicate numbers
    assert len(allocated_numbers) == len(set(allocated_numbers)), "Collisions detected in concurrent allocations!"

    # Verify all correspond to same FY
    assert all(f == fy for f in allocated_fys)

    # Extract sequence integers
    sequences = sorted(int(num.split("-")[-1]) for num in allocated_numbers)
    # Check strictly monotonic progression
    for i in range(len(sequences) - 1):
        assert sequences[i + 1] == sequences[i] + 1, f"Gap in sequence: {sequences[i]} -> {sequences[i+1]}"


# ==============================================================================
# 2. Unique Constraint Enforcement on Credit Note Number
# ==============================================================================


@pytest.mark.asyncio
async def test_credit_note_unique_number_constraint_enforcement(
    pg_session_factory, invoice_service
):
    """Database unique constraint 'uq_platform_credit_notes_number' prohibits duplicate credit note numbers."""
    async with pg_session_factory() as session:
        soc_id, sub_id = await _seed_test_society_and_subscription(session)
        inv_id = await _seed_and_finalize_invoice(session, invoice_service, soc_id, sub_id)

    now = _utc_now()
    duplicate_number = f"SS-CN-TEST-DUP-{uuid.uuid4().hex[:6]}"

    # 1. Insert first credit note with duplicate_number
    async with pg_session_factory() as session:
        cn1 = PlatformCreditNote(
            id=uuid.uuid4(),
            society_id=soc_id,
            invoice_id=inv_id,
            credit_note_number=duplicate_number,
            fiscal_year="2627",
            status="ISSUED",
            taxable_amount=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            tax_total=Decimal("180.00"),
            grand_total=Decimal("1180.00"),
            currency_code="INR",
            reason="Duplicate test 1",
            issued_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(cn1)
        await session.commit()

    # 2. Attempt to insert second credit note with the identical credit_note_number
    async with pg_session_factory() as session:
        cn2 = PlatformCreditNote(
            id=uuid.uuid4(),
            society_id=soc_id,
            invoice_id=inv_id,
            credit_note_number=duplicate_number,
            fiscal_year="2627",
            status="ISSUED",
            taxable_amount=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            tax_total=Decimal("180.00"),
            grand_total=Decimal("1180.00"),
            currency_code="INR",
            reason="Duplicate test 2",
            issued_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(cn2)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()

        err_msg = str(exc_info.value).lower()
        assert "uq_platform_credit_notes_number" in err_msg or "unique constraint" in err_msg


# ==============================================================================
# 3. Transaction Rollback Atomicity
# ==============================================================================


@pytest.mark.asyncio
async def test_credit_note_transaction_rollback_atomicity(
    pg_session_factory, invoice_service, credit_note_service_factory
):
    """An aborted/rolled-back issuance transaction preserves both credit note state and sequence counter."""
    async with pg_session_factory() as session:
        soc_id, sub_id = await _seed_test_society_and_subscription(session)
        inv_id = await _seed_and_finalize_invoice(session, invoice_service, soc_id, sub_id)

        cn_svc = credit_note_service_factory(session)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=inv_id,
                reason="Rollback atomicity test",
                taxable_amount=Decimal("2000.00"),
            )
        )
        await session.commit()
        draft_id = draft.id

    fy = get_financial_year(_utc_now())

    # Get current sequence before attempt
    async with pg_session_factory() as session:
        seq_row = await session.get(PlatformCreditNoteSequence, fy)
        initial_seq = seq_row.current_sequence if seq_row else 0

    # Simulate an error causing rollback during issuance transaction
    try:
        async with pg_session_factory() as session:
            async with session.begin():
                cn_svc = credit_note_service_factory(session)
                await cn_svc.issue_credit_note(draft_id)
                # Force intentional failure before commit
                raise RuntimeError("Simulated crash before commit during credit note issue")
    except RuntimeError:
        pass

    # Verify credit note remains in DRAFT and has no credit_note_number
    async with pg_session_factory() as session:
        cn_after = await session.get(PlatformCreditNote, draft_id)
        assert cn_after.status == "DRAFT"
        assert cn_after.credit_note_number is None

        # Verify sequence counter was NOT permanently incremented
        seq_after = await session.get(PlatformCreditNoteSequence, fy)
        after_seq = seq_after.current_sequence if seq_after else 0
        assert after_seq == initial_seq, f"Sequence counter incremented despite rollback: {after_seq} != {initial_seq}"


# ==============================================================================
# 4. PostgreSQL FORCE ROW LEVEL SECURITY Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_unprivileged_app_user_credit_note_rls_isolation(
    pg_session_factory, invoice_service, credit_note_service_factory, ensure_app_user_role
):
    """Under unprivileged role 'app_user', PostgreSQL FORCE ROW LEVEL SECURITY isolates credit notes and items."""
    async with pg_session_factory() as session:
        soc_a_id, sub_a_id = await _seed_test_society_and_subscription(session, state="Maharashtra")
        soc_b_id, sub_b_id = await _seed_test_society_and_subscription(session, state="Karnataka")

        inv_a_id = await _seed_and_finalize_invoice(session, invoice_service, soc_a_id, sub_a_id)

        # Create and issue credit note for Tenant A
        cn_svc = credit_note_service_factory(session)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=inv_a_id,
                reason="Tenant A rebate",
                taxable_amount=Decimal("3000.00"),
            )
        )
        issued_a = await cn_svc.issue_credit_note(draft.id)
        await session.commit()
        cn_a_id = issued_a.id
        allocated_cn_number = issued_a.credit_note_number

    # 1. Tenant B connects as unprivileged app_user -> cannot see Tenant A's credit note or items
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_b_id):
            await set_db_tenant_context(session, soc_b_id)

            # Query PlatformCreditNote
            cn_leak = (
                await session.execute(
                    select(PlatformCreditNote).where(PlatformCreditNote.id == cn_a_id)
                )
            ).scalar_one_or_none()
            assert cn_leak is None, "FORCE RLS violation: Tenant B accessed Tenant A's credit note!"

            # Query PlatformCreditNoteItem
            item_leak = (
                await session.execute(
                    select(PlatformCreditNoteItem).where(PlatformCreditNoteItem.credit_note_id == cn_a_id)
                )
            ).scalars().all()
            assert len(item_leak) == 0, "FORCE RLS violation: Tenant B accessed Tenant A's credit note items!"

            # Query PlatformSubscriptionAuditLog (credit note tax snapshot)
            snapshot_leak = (
                await session.execute(
                    select(PlatformSubscriptionAuditLog).where(
                        PlatformSubscriptionAuditLog.entity_id == cn_a_id,
                        PlatformSubscriptionAuditLog.entity_type == "CREDIT_NOTE_TAX_SNAPSHOT",
                    )
                )
            ).scalar_one_or_none()
            assert snapshot_leak is None, "FORCE RLS violation: Tenant B accessed Tenant A's credit note tax snapshot!"

    # 2. Tenant A connects as unprivileged app_user -> accesses own credit note, items, and tax snapshot
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_a_id):
            await set_db_tenant_context(session, soc_a_id)

            cn_a_read = (
                await session.execute(
                    select(PlatformCreditNote).where(PlatformCreditNote.id == cn_a_id)
                )
            ).scalar_one_or_none()
            assert cn_a_read is not None, "Tenant A must access their own credit note"
            assert cn_a_read.credit_note_number == allocated_cn_number
            assert cn_a_read.status == "ISSUED"

            items_a_read = (
                await session.execute(
                    select(PlatformCreditNoteItem).where(PlatformCreditNoteItem.credit_note_id == cn_a_id)
                )
            ).scalars().all()
            assert len(items_a_read) >= 1
            assert items_a_read[0].taxable_amount == Decimal("3000.00")

            snapshot_row = (
                await session.execute(
                    select(PlatformSubscriptionAuditLog).where(
                        PlatformSubscriptionAuditLog.entity_id == cn_a_id,
                        PlatformSubscriptionAuditLog.entity_type == "CREDIT_NOTE_TAX_SNAPSHOT",
                    )
                )
            ).scalar_one_or_none()
            assert snapshot_row is not None, "Tenant A must access their own credit note tax snapshot"
            assert snapshot_row.after_state is not None

            # Verify cryptographic SHA-256 digest of retrieved tax snapshot
            restored = TaxSnapshot(**snapshot_row.after_state)
            assert TaxSnapshotService.verify_snapshot_integrity(restored) is True


# ==============================================================================
# 5. Concurrent Partial Credit Notes & Over-Credit Prevention
# ==============================================================================


@pytest.mark.asyncio
async def test_concurrent_partial_credit_notes_overcredit_prevention(
    pg_session_factory, invoice_service, credit_note_service_factory
):
    """Two concurrent workers trying to issue partial credits that collectively exceed invoice balance serialize safely.

    Verifies:
    1. Exactly one worker succeeds and commits their partial credit.
    2. The competing worker is safely rejected with CreditNoteExceedsEligibleBalanceException.
    3. Aggregate issued credits NEVER exceed the invoice grand total under concurrency.
    """
    async with pg_session_factory() as session:
        soc_id, sub_id = await _seed_test_society_and_subscription(session)
        # Invoice grand total = ₹11,800.00 (taxable ₹10,000 + 18% tax)
        inv_id = await _seed_and_finalize_invoice(session, invoice_service, soc_id, sub_id)

        cn_svc = credit_note_service_factory(session)

        # Worker 1 draft: ₹7,000 taxable (grand total ₹8,260.00)
        draft1 = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=inv_id,
                reason="Partial rebate A (concurrent)",
                taxable_amount=Decimal("7000.00"),
            )
        )
        # Worker 2 draft: ₹7,000 taxable (grand total ₹8,260.00)
        # Both together = ₹16,520 > ₹11,800 invoice balance!
        draft2 = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=inv_id,
                reason="Partial rebate B (concurrent)",
                taxable_amount=Decimal("7000.00"),
            )
        )
        await session.commit()
        d1_id = draft1.id
        d2_id = draft2.id

    async def issue_worker(draft_id: uuid.UUID):
        async with pg_session_factory() as s:
            async with s.begin():
                svc = credit_note_service_factory(s)
                return await svc.issue_credit_note(draft_id)

    # Execute concurrent issuance
    results = await asyncio.gather(
        issue_worker(d1_id),
        issue_worker(d2_id),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1, f"Expected exactly 1 success under concurrency, got {len(successes)}. Failures: {repr(failures)}"
    assert len(failures) == 1, f"Expected exactly 1 failure under concurrency, got {len(failures)}"
    assert isinstance(failures[0], CreditNoteExceedsEligibleBalanceException), (
        f"Expected CreditNoteExceedsEligibleBalanceException, got {type(failures[0])}: {failures[0]}"
    )

    # Verify database state
    async with pg_session_factory() as session:
        from apps.api.src.database.models.platform_billing import PlatformInvoice
        inv = await session.get(PlatformInvoice, inv_id)
        assert inv is not None
        assert inv.credits_applied == Decimal("8260.00"), (
            f"Over-credit detected! credits_applied={inv.credits_applied} (must be 8260.00)"
        )
        assert inv.amount_due == Decimal("3540.00")

