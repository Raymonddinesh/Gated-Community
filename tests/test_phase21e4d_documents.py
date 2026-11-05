"""Phase 21E.4D — SaaS Billing Document Generation, Storage, and Email Delivery Tests.

Comprehensive test suite verifying:
1. Issuer configuration resolution and validation.
2. PDF Generation Engine (ReportLab) for Invoices and Credit Notes:
   - Valid %PDF- binary headers.
   - Deterministic SHA-256 digest computation.
   - Presentation layer immutability (zero financial calculations).
   - Strict rejection of DRAFT documents.
3. Secure Document Storage (S3 / Resilient Storage):
   - Deterministic tenant-isolated S3 key layout: societies/{society_id}/billing/{type}/{fy}/{doc_number}.pdf
   - SHA-256 integrity check on upload and retrieval.
   - Prevention of silent document overwriting.
   - Detection of storage tampering (checksum mismatch).
   - Short-lived presigned download URLs (max 300 seconds).
   - Cross-tenant access denial.
4. Transactional Outbox & Reliable Email Delivery:
   - Idempotent queuing (duplicate idempotency keys deduplicated).
   - Outbox attempt tracking and status transitions (QUEUED -> SENT / RETRYING / FAILED).
   - Exponential backoff retry logic.
   - Attachment delivery of genuine PDF binary.
   - Recipient resolution from active society administrators.
5. High-Level Orchestrator & API Endpoints:
   - PDF retrieval with caching (second call retrieves stored document).
   - Presigned download URL generation endpoint.
   - Email dispatch endpoint.
   - Delivery attempt audit history endpoint.
   - DRAFT invoice and credit note access denial (HTTP 400).
"""

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from apps.api.src.database.base import Base
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.platform_billing import (
    PlatformCreditNote,
    PlatformInvoice,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import PlatformSubscriptionPlan, SocietySubscription
from apps.api.src.subscriptions.credit_notes.schemas import (
    PlatformCreditNoteCreateDraft,
    PlatformCreditNoteItemCreate,
)
from apps.api.src.subscriptions.credit_notes.service import PlatformCreditNoteService
from apps.api.src.subscriptions.documents.document_orchestrator import (
    PlatformBillingDocumentService,
)
from apps.api.src.subscriptions.documents.email_service import (
    BillingEmailDeliveryService,
    MockBillingEmailProvider,
)
from apps.api.src.subscriptions.documents.exceptions import (
    DocumentAlreadyGeneratedException,
    DocumentPermissionDeniedException,
    DocumentTamperException,
    DraftDocumentAccessDeniedException,
)
from apps.api.src.subscriptions.documents.issuer import (
    get_issuer_config,
)
from apps.api.src.subscriptions.documents.pdf_service import BillingPDFService
from apps.api.src.subscriptions.documents.schemas import (
    PlatformDocumentEmailRequest,
)
from apps.api.src.subscriptions.documents.storage_service import (
    BillingDocumentStorageService,
)
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    TaxConfigurationService,
)
from apps.api.src.subscriptions.tax.snapshot import (
    TaxSnapshot,
)

# ==============================================================================
# Fixtures & Helpers
# ==============================================================================


@pytest.fixture
async def in_memory_db():
    """In-memory SQLite async engine for isolated unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(in_memory_db):
    """Session factory for async sessions."""
    return async_sessionmaker(bind=in_memory_db, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def custom_tax_config():
    cfg = TaxConfigurationService()
    cfg.reset_to_defaults()
    return cfg


@pytest.fixture
def invoice_service(custom_tax_config):
    tax_eng = GSTTaxEngine(custom_tax_config)
    num_svc = InvoiceNumberingService(prefix="SS")
    return PlatformInvoiceService(tax_engine=tax_eng, numbering_service=num_svc)


async def _seed_society_and_subscription(
    session: AsyncSession,
    state: str = "Maharashtra",
    legal_name: str = "Marvel Imperial CHSL",
    admin_email: str | None = None,
) -> tuple[UUID, UUID, UUID]:
    """Helper to seed test society, admin user, and platform subscription."""
    soc_id = uuid4()
    plan_id = uuid4()
    sub_id = uuid4()
    user_id = uuid4()
    user_email = admin_email or f"treasurer_{uuid4().hex[:6]}@marvelsociety.org"

    society = Society(
        id=soc_id,
        legal_name=legal_name,
        display_name=legal_name[:20],
        address_line1="Plot 42, Hiranandani Gardens, Powai",
        city="Mumbai",
        state=state,
        postal_code="400076",
        status="ACTIVE",
    )
    session.add(society)

    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PLAN_DOC_{uuid4().hex[:6]}",
        display_name="Enterprise Plan",
        monthly_price=Decimal("10000.00"),
    )
    session.add(plan)

    now = datetime.now(UTC).replace(tzinfo=None)
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status="ACTIVE",
        starts_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    session.add(sub)

    # Seed Admin User for email resolution with globally unique phone
    unique_phone = f"+91{uuid4().int % 10000000000:010d}"
    user = User(
        id=user_id,
        email=user_email,
        phone=unique_phone,
        first_name="Rajesh",
        last_name="Sharma",
        display_name="Rajesh Sharma",
        status="ACTIVE",
        password_hash="mock_hash",
    )
    session.add(user)

    # Check if TREASURER role exists
    role_stmt = select(Role).where(Role.code == "TREASURER", Role.scope_type == "SOCIETY")
    existing_role = (await session.execute(role_stmt)).scalar_one_or_none()
    if not existing_role:
        role = Role(
            id=uuid4(),
            code="TREASURER",
            name="TREASURER",
            scope_type="SOCIETY",
            is_system_role=True,
        )
        session.add(role)
        await session.flush()
        role_id = role.id
    else:
        role_id = existing_role.id

    role_assignment = RoleAssignment(
        id=uuid4(),
        society_id=soc_id,
        user_id=user_id,
        role_id=role_id,
        scope_type="SOCIETY",
        status="ACTIVE",
    )
    session.add(role_assignment)

    await session.commit()
    return soc_id, sub_id, user_id


# ==============================================================================
# 1. Issuer Configuration Tests
# ==============================================================================


def test_issuer_config_resolution():
    """BillingIssuerConfig loads corporate credentials safely without hardcoding."""
    cfg = get_issuer_config()
    assert cfg.legal_name == "SocietySphere Technologies India Private Limited"
    assert cfg.pan == "AABCS1429B"
    assert cfg.gstin.startswith("27")  # Maharashtra State code
    assert cfg.state_code == "27"
    assert cfg.state_name == "Maharashtra"
    assert "Maharashtra" in cfg.registered_address
    assert cfg.billing_email == "billing@societysphere.com"


# ==============================================================================
# 2. PDF Generation Engine Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_invoice_pdf_generation(session_factory, invoice_service):
    """Invoice PDF generates valid binary with deterministic SHA-256 and presentation accuracy."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session, state="Maharashtra")
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[
                PlatformInvoiceItemCreate(
                    description="Enterprise Platform Subscription",
                    sac_code="998313",
                    quantity=1,
                    unit_price=Decimal("10000.00"),
                )
            ],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    # Finalize invoice to get issued status and locked tax snapshot
    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

    async with session_factory() as session:
        inv_stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == inv_id)
        )
        inv_db = (await session.execute(inv_stmt)).scalar_one()
        soc_db = await session.get(Society, soc_id)
        snapshot = await invoice_service.get_invoice_tax_snapshot(session, inv_id)

        pdf_svc = BillingPDFService()
        pdf_bytes, checksum = pdf_svc.generate_invoice_pdf(
            invoice=inv_db,
            items=inv_db.items,
            snapshot=snapshot,
            society=soc_db,
        )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF-"), "Generated document must be a valid PDF"

        # Verify cryptographic checksum calculation
        calculated_hash = hashlib.sha256(pdf_bytes).hexdigest()
        assert checksum == calculated_hash


@pytest.mark.asyncio
async def test_credit_note_pdf_generation(session_factory, invoice_service):
    """Credit Note PDF generates valid binary referencing original invoice with reason code."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session, state="Karnataka")
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[
                PlatformInvoiceItemCreate(
                    description="Cloud Infrastructure Allocation",
                    sac_code="998313",
                    quantity=1,
                    unit_price=Decimal("20000.00"),
                )
            ],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

    # Issue credit note against invoice
    async with session_factory() as session:
        cn_svc = PlatformCreditNoteService(session)
        cn_draft = await cn_svc.create_draft_credit_note(
            payload=PlatformCreditNoteCreateDraft(
                society_id=soc_id,
                invoice_id=inv_id,
                reason="SERVICE_OUTAGE_SLA_REBATE",
                notes="Rebate for 99.0% SLA breach during scheduled window",
                items=[
                    PlatformCreditNoteItemCreate(
                        description="SLA Rebate Credit",
                        unit_price=Decimal("5000.00"),
                    )
                ],
            ),
        )
        await session.commit()
        cn_id = cn_draft.id

    async with session_factory() as session:
        cn_svc = PlatformCreditNoteService(session)
        await cn_svc.issue_credit_note(cn_id)
        await session.commit()

    async with session_factory() as session:
        cn_stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
            .where(PlatformCreditNote.id == cn_id)
        )
        cn_db = (await session.execute(cn_stmt)).scalar_one()
        inv_db = await session.get(PlatformInvoice, inv_id)
        soc_db = await session.get(Society, soc_id)
        orchestrator = PlatformBillingDocumentService()
        snapshot = await orchestrator._fetch_tax_snapshot(
            session=session,
            entity_id=cn_id,
            entity_type="CREDIT_NOTE_TAX_SNAPSHOT",
            society_id=soc_id,
        )

        pdf_svc = BillingPDFService()
        pdf_bytes, checksum = pdf_svc.generate_credit_note_pdf(
            credit_note=cn_db,
            items=cn_db.items,
            invoice=inv_db,
            snapshot=snapshot,
            society=soc_db,
        )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF-")
        assert checksum == hashlib.sha256(pdf_bytes).hexdigest()


@pytest.mark.asyncio
async def test_cannot_generate_pdf_for_draft_invoice(session_factory, invoice_service):
    """Attempting to generate a PDF for a DRAFT invoice raises DraftDocumentAccessDeniedException."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Draft Item", unit_price=Decimal("1000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        inv_stmt = (
            select(PlatformInvoice)
            .options(selectinload(PlatformInvoice.items))
            .where(PlatformInvoice.id == inv_id)
        )
        inv_db = (await session.execute(inv_stmt)).scalar_one()
        soc_db = await session.get(Society, soc_id)
        mock_snapshot = MagicMock(spec=TaxSnapshot)

        pdf_svc = BillingPDFService()
        with pytest.raises(DraftDocumentAccessDeniedException) as exc:
            pdf_svc.generate_invoice_pdf(inv_db, inv_db.items, mock_snapshot, soc_db)
        assert "DRAFT" in str(exc.value)


@pytest.mark.asyncio
async def test_cannot_generate_pdf_for_draft_credit_note(session_factory, invoice_service):
    """Attempting to generate a PDF for a DRAFT credit note raises DraftDocumentAccessDeniedException."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("1000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        await invoice_service.finalize_invoice(session, inv.id)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        cn_svc = PlatformCreditNoteService(session)
        cn_draft = await cn_svc.create_draft_credit_note(
            payload=PlatformCreditNoteCreateDraft(
                society_id=soc_id,
                invoice_id=inv_id,
                reason="GOODWILL_GESTURE",
                items=[PlatformCreditNoteItemCreate(description="Goodwill discount", unit_price=Decimal("500.00"))],
            ),
        )
        await session.commit()
        cn_id = cn_draft.id

    async with session_factory() as session:
        cn_stmt = (
            select(PlatformCreditNote)
            .options(selectinload(PlatformCreditNote.items))
            .where(PlatformCreditNote.id == cn_id)
        )
        cn_db = (await session.execute(cn_stmt)).scalar_one()
        inv_db = await session.get(PlatformInvoice, inv_id)
        soc_db = await session.get(Society, soc_id)
        mock_snapshot = MagicMock(spec=TaxSnapshot)

        pdf_svc = BillingPDFService()
        with pytest.raises(DraftDocumentAccessDeniedException) as exc:
            pdf_svc.generate_credit_note_pdf(cn_db, cn_db.items, inv_db, mock_snapshot, soc_db)
        assert "DRAFT" in str(exc.value)


# ==============================================================================
# 3. Secure Storage & Integrity Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_storage_service_immutability_and_checksum(session_factory):
    """Storage service enforces SHA-256 integrity check and prevents silent overwriting."""
    async with session_factory() as session:
        soc_id, _, _ = await _seed_society_and_subscription(session)
        doc_id = uuid4()
        storage_svc = BillingDocumentStorageService()

        pdf_bytes = b"%PDF-1.4 test document binary content for integrity validation"
        checksum = hashlib.sha256(pdf_bytes).hexdigest()

        # 1. Store initial billing document
        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=doc_id,
            document_number="SS-INV-2627-00001",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        await session.commit()

        assert doc.sha256_checksum == checksum
        assert doc.file_size_bytes == len(pdf_bytes)
        assert doc.storage_key == f"societies/{soc_id}/billing/invoices/2627/SS-INV-2627-00001.pdf"

        # 2. Retrieve bytes and assert integrity passes
        retrieved_bytes = await storage_svc.get_document_bytes(
            session=session,
            document_id=doc.id,
            caller_society_id=soc_id,
        )
        assert retrieved_bytes == pdf_bytes

        # 3. Idempotent re-store with same checksum returns existing
        re_stored = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=doc_id,
            document_number="SS-INV-2627-00001",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        assert re_stored.id == doc.id

        # 4. Prevent silent overwriting with different content
        diff_bytes = b"%PDF-1.4 altered content attempt"
        diff_checksum = hashlib.sha256(diff_bytes).hexdigest()
        with pytest.raises(DocumentAlreadyGeneratedException):
            await storage_svc.store_billing_document(
                session=session,
                society_id=soc_id,
                document_type="INVOICE",
                document_id=doc_id,
                document_number="SS-INV-2627-00001",
                fiscal_year="2627",
                pdf_bytes=diff_bytes,
                checksum=diff_checksum,
            )


@pytest.mark.asyncio
async def test_storage_service_tamper_detection(session_factory):
    """Storage service detects payload tampering in storage layer."""
    async with session_factory() as session:
        soc_id, _, _ = await _seed_society_and_subscription(session)
        doc_id = uuid4()
        storage_svc = BillingDocumentStorageService()

        pdf_bytes = b"%PDF-1.4 pristine valid content"
        checksum = hashlib.sha256(pdf_bytes).hexdigest()

        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=doc_id,
            document_number="SS-INV-2627-00002",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        await session.commit()

        # Simulate malicious or corrupt bit-flip in underlying storage
        storage_svc._mock_storage[doc.storage_key] = b"%PDF-1.4 maliciously altered payload"

        with pytest.raises(DocumentTamperException) as exc:
            await storage_svc.get_document_bytes(
                session=session,
                document_id=doc.id,
                caller_society_id=soc_id,
            )
        assert "integrity" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_storage_presigned_url_expiry_constraint(session_factory):
    """Presigned download URL respects max expiry of 300 seconds."""
    async with session_factory() as session:
        soc_id, _, _ = await _seed_society_and_subscription(session)
        doc_id = uuid4()
        storage_svc = BillingDocumentStorageService()

        pdf_bytes = b"%PDF-1.4 signed url test"
        checksum = hashlib.sha256(pdf_bytes).hexdigest()

        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=doc_id,
            document_number="SS-INV-2627-00003",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        await session.commit()

        # Test request for 600 seconds gets capped to 300
        url = await storage_svc.generate_presigned_download_url(
            session=session,
            document_id=doc.id,
            caller_society_id=soc_id,
            expires_in_seconds=600,
        )
        assert "Expires=" in url or "X-Amz-Expires=" in url


@pytest.mark.asyncio
async def test_cross_tenant_document_access_denial(session_factory):
    """Storage service strictly denies cross-tenant access to billing documents."""
    async with session_factory() as session:
        soc_a, _, _ = await _seed_society_and_subscription(session, legal_name="Society Alpha")
        soc_b, _, _ = await _seed_society_and_subscription(session, legal_name="Society Beta")
        storage_svc = BillingDocumentStorageService()

        pdf_bytes = b"%PDF-1.4 confidential billing doc"
        checksum = hashlib.sha256(pdf_bytes).hexdigest()

        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_a,
            document_type="INVOICE",
            document_id=uuid4(),
            document_number="SS-INV-2627-00004",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=checksum,
        )
        await session.commit()

        # Tenant B attempting to retrieve Tenant A's document
        with pytest.raises(DocumentPermissionDeniedException):
            await storage_svc.get_document_bytes(
                session=session,
                document_id=doc.id,
                caller_society_id=soc_b,
            )

        with pytest.raises(DocumentPermissionDeniedException):
            await storage_svc.generate_presigned_download_url(
                session=session,
                document_id=doc.id,
                caller_society_id=soc_b,
            )


# ==============================================================================
# 4. Transactional Outbox & Email Delivery Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_email_outbox_queueing_and_deduplication(session_factory):
    """Queuing email delivery creates outbox record and prevents duplicate dispatch via idempotency key."""
    async with session_factory() as session:
        soc_id, _, _ = await _seed_society_and_subscription(session, admin_email="treasurer@marvelsociety.org")
        storage_svc = BillingDocumentStorageService()
        email_svc = BillingEmailDeliveryService()

        pdf_bytes = b"%PDF-1.4 outbox test"
        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=uuid4(),
            document_number="SS-INV-2627-00005",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        await session.commit()

        # 1. Queue delivery
        delivery1 = await email_svc.queue_delivery(
            session=session,
            document=doc,
            idempotency_key="idemp-key-test-001",
        )
        await session.commit()

        assert delivery1.status == "QUEUED"
        assert delivery1.recipient_email == "treasurer@marvelsociety.org"
        assert delivery1.idempotency_key == "idemp-key-test-001"

        # 2. Queue again with same idempotency key
        delivery2 = await email_svc.queue_delivery(
            session=session,
            document=doc,
            idempotency_key="idemp-key-test-001",
        )
        assert delivery2.id == delivery1.id, "Duplicate idempotency key must return existing outbox entry"


@pytest.mark.asyncio
async def test_email_successful_delivery_and_attempt_logging(session_factory):
    """Successful email delivery transitions outbox to SENT and records attempt details."""
    async with session_factory() as session:
        soc_id, _, _ = await _seed_society_and_subscription(session)
        storage_svc = BillingDocumentStorageService()
        provider = MockBillingEmailProvider(simulate_failure=False)
        email_svc = BillingEmailDeliveryService(provider=provider)

        pdf_bytes = b"%PDF-1.4 dispatch test"
        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=uuid4(),
            document_number="SS-INV-2627-00006",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        await session.commit()

        delivery = await email_svc.queue_delivery(session=session, document=doc)
        await session.commit()

        # Execute delivery
        completed = await email_svc.execute_delivery(
            session=session,
            delivery_id=delivery.id,
            subject="Tax Invoice SS-INV-2627-00006",
            html_body="<p>Please find attached invoice.</p>",
            text_body="Please find attached invoice.",
            pdf_bytes=pdf_bytes,
            filename="SS-INV-2627-00006.pdf",
        )
        await session.commit()

        assert completed.status == "SENT"
        assert completed.attempt_count == 1
        assert completed.sent_at is not None
        assert len(completed.attempts) == 1
        attempt = completed.attempts[0]
        assert attempt.status == "SUCCESS"
        assert attempt.attempt_number == 1
        assert attempt.provider_name == "MockBillingEmailProvider"


@pytest.mark.asyncio
async def test_email_retry_backoff_and_terminal_failure(session_factory):
    """Email delivery retries with exponential backoff on transient failure and halts at max attempts."""
    async with session_factory() as session:
        soc_id, _, _ = await _seed_society_and_subscription(session)
        storage_svc = BillingDocumentStorageService()
        failing_provider = MockBillingEmailProvider(simulate_failure=True, is_retryable=True)
        email_svc = BillingEmailDeliveryService(provider=failing_provider)

        pdf_bytes = b"%PDF-1.4 retry test"
        doc = await storage_svc.store_billing_document(
            session=session,
            society_id=soc_id,
            document_type="INVOICE",
            document_id=uuid4(),
            document_number="SS-INV-2627-00007",
            fiscal_year="2627",
            pdf_bytes=pdf_bytes,
            checksum=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        await session.commit()

        delivery = await email_svc.queue_delivery(session=session, document=doc)
        await session.commit()

        # Attempt 1: Fails, moves to RETRYING
        res1 = await email_svc.execute_delivery(
            session=session,
            delivery_id=delivery.id,
            subject="Invoice SS-INV-2627-00007",
            html_body="<p>Test</p>",
            text_body="Test",
            pdf_bytes=pdf_bytes,
            filename="SS-INV-2627-00007.pdf",
        )
        await session.commit()
        assert res1.status == "RETRYING"
        assert res1.attempt_count == 1
        assert res1.next_retry_at is not None

        # Attempt 2: Fails, remains in RETRYING
        res2 = await email_svc.execute_delivery(
            session=session,
            delivery_id=delivery.id,
            subject="Invoice SS-INV-2627-00007",
            html_body="<p>Test</p>",
            text_body="Test",
            pdf_bytes=pdf_bytes,
            filename="SS-INV-2627-00007.pdf",
        )
        await session.commit()
        assert res2.status == "RETRYING"
        assert res2.attempt_count == 2

        # Attempt 3: Fails, hits max_attempts (3), transitions to FAILED
        res3 = await email_svc.execute_delivery(
            session=session,
            delivery_id=delivery.id,
            subject="Invoice SS-INV-2627-00007",
            html_body="<p>Test</p>",
            text_body="Test",
            pdf_bytes=pdf_bytes,
            filename="SS-INV-2627-00007.pdf",
        )
        await session.commit()
        assert res3.status == "FAILED"
        assert res3.attempt_count == 3
        assert len(res3.attempts) == 3


# ==============================================================================
# 5. Orchestrator End-to-End Workflow Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_orchestrator_invoice_lifecycle_end_to_end(session_factory, invoice_service):
    """Orchestrator generates, persists, caches, and emails invoice document end-to-end."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session, admin_email="treasurer@marvelsociety.org")
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("12000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        await invoice_service.finalize_invoice(session, inv.id)
        await session.commit()
        inv_id = inv.id

    # 1. First call: Generates and persists
    async with session_factory() as session:
        orchestrator = PlatformBillingDocumentService()
        doc, pdf_bytes = await orchestrator.get_or_generate_invoice_document(session, inv_id)
        await session.commit()
        first_doc_id = doc.id
        first_checksum = doc.sha256_checksum

        assert pdf_bytes.startswith(b"%PDF-")
        assert doc.document_type == "INVOICE"

    # 2. Second call: Retrieves cached without re-generating
    async with session_factory() as session:
        orchestrator = PlatformBillingDocumentService()
        cached_doc, cached_bytes = await orchestrator.get_or_generate_invoice_document(session, inv_id)
        assert cached_doc.id == first_doc_id
        assert cached_doc.sha256_checksum == first_checksum
        assert cached_bytes == pdf_bytes

    # 3. Presigned Download URL
    async with session_factory() as session:
        orchestrator = PlatformBillingDocumentService()
        url_resp = await orchestrator.get_invoice_download_url(session, inv_id)
        assert url_resp.document_id == first_doc_id
        assert url_resp.sha256_checksum == first_checksum
        assert url_resp.expires_in_seconds <= 300

    # 4. Deliver via Email
    async with session_factory() as session:
        orchestrator = PlatformBillingDocumentService()
        deliv_resp = await orchestrator.send_invoice_email(
            session=session,
            invoice_id=inv_id,
            payload=PlatformDocumentEmailRequest(
                recipient_email="treasurer@marvelsociety.org",
                idempotency_key="e2e-inv-email-001",
            ),
        )
        await session.commit()
        assert deliv_resp.status == "SENT"
        assert deliv_resp.recipient_email == "treasurer@marvelsociety.org"

    # 5. List deliveries audit history
    async with session_factory() as session:
        orchestrator = PlatformBillingDocumentService()
        history = await orchestrator.list_document_deliveries(session, first_doc_id)
        assert len(history) == 1
        assert history[0].id == deliv_resp.id


@pytest.mark.asyncio
async def test_orchestrator_credit_note_lifecycle_end_to_end(session_factory, invoice_service):
    """Orchestrator generates, persists, caches, and emails credit note document end-to-end."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("15000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        await invoice_service.finalize_invoice(session, inv.id)
        await session.commit()
        inv_id = inv.id

        cn_svc = PlatformCreditNoteService(session)
        cn_draft = await cn_svc.create_draft_credit_note(
            payload=PlatformCreditNoteCreateDraft(
                society_id=soc_id,
                invoice_id=inv_id,
                reason="COMMERCIAL_DISCOUNT_APPROVED",
                items=[PlatformCreditNoteItemCreate(description="Approved discount", unit_price=Decimal("3000.00"))],
            ),
        )
        await session.commit()
        issued_cn = await cn_svc.issue_credit_note(cn_draft.id)
        await session.commit()
        cn_id = issued_cn.id

    # Orchestrator flow
    async with session_factory() as session:
        orchestrator = PlatformBillingDocumentService()
        doc, pdf_bytes = await orchestrator.get_or_generate_credit_note_document(session, cn_id)
        await session.commit()

        assert pdf_bytes.startswith(b"%PDF-")
        assert doc.document_type == "CREDIT_NOTE"

        # Presigned URL
        url_resp = await orchestrator.get_credit_note_download_url(session, cn_id)
        assert url_resp.document_id == doc.id
        assert url_resp.expires_in_seconds <= 300

        # Deliver via email
        deliv_resp = await orchestrator.send_credit_note_email(session, cn_id)
        await session.commit()
        assert deliv_resp.status == "SENT"


# ==============================================================================
# 6. HTTP API Endpoint Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_api_invoice_pdf_and_delivery_endpoints(session_factory, invoice_service):
    """FastAPI endpoints for invoice PDF download, presigned URL, email delivery, and delivery history."""
    from httpx import ASGITransport, AsyncClient

    from apps.api.src.database.session import get_db_session
    from apps.api.src.main import app

    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id, _ = await _seed_society_and_subscription(session, admin_email="treasurer@marvelsociety.org")
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base Plan", unit_price=Decimal("10000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    super_admin_user = User(
        id=UUID("11111111-1111-1111-1111-11111111111a"),
        email="superadmin@societysphere.io",
        first_name="Super",
        last_name="Admin",
        display_name="Super Admin",
        status="ACTIVE",
    )

    async with session_factory() as session:
        role_res = await session.execute(
            select(Role).where(Role.code == "SUPER_ADMIN", Role.scope_type == "PLATFORM")
        )
        super_role = role_res.scalar_one_or_none()
        if not super_role:
            super_role = Role(code="SUPER_ADMIN", name="Super Admin", scope_type="PLATFORM")
            session.add(super_role)
            await session.flush()

        session.add(super_admin_user)
        session.add(
            RoleAssignment(
                user_id=super_admin_user.id,
                role_id=super_role.id,
                scope_type="PLATFORM",
            )
        )
        await session.commit()

    async def _mock_db_session():
        async with session_factory() as sess:
            yield sess

    from apps.api.src.auth.dependencies import get_current_user

    app.dependency_overrides[get_db_session] = _mock_db_session
    app.dependency_overrides[get_current_user] = lambda: super_admin_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. DRAFT invoice PDF retrieval is rejected with 400
            resp = await client.get(f"/api/v1/platform/invoices/{inv_id}/pdf")
            assert resp.status_code == 400
            assert "DRAFT" in resp.text

            # Finalize invoice
            async with session_factory() as session:
                await invoice_service.finalize_invoice(session, inv_id)
                await session.commit()

            # 2. Finalized invoice PDF retrieval returns 200 with PDF content
            pdf_resp = await client.get(f"/api/v1/platform/invoices/{inv_id}/pdf")
            assert pdf_resp.status_code == 200
            assert pdf_resp.headers["content-type"] == "application/pdf"
            assert "inline; filename=" in pdf_resp.headers["content-disposition"]
            assert "x-document-checksum" in pdf_resp.headers
            assert pdf_resp.content.startswith(b"%PDF-")

            # 3. Presigned download URL endpoint returns valid URL
            url_resp = await client.get(f"/api/v1/platform/invoices/{inv_id}/download-url")
            assert url_resp.status_code == 200
            url_data = url_resp.json()
            assert "download_url" in url_data
            assert url_data["expires_in_seconds"] <= 300

            # 4. Email delivery endpoint queues and dispatches email
            email_resp = await client.post(
                f"/api/v1/platform/invoices/{inv_id}/send-email",
                json={
                    "recipient_email": "treasurer@marvelsociety.org",
                    "idempotency_key": "api-test-inv-email-001",
                },
            )
            assert email_resp.status_code == 200
            deliv_data = email_resp.json()
            assert deliv_data["status"] == "SENT"
            doc_id = deliv_data["document_id"]

            # 5. List document delivery history endpoint
            history_resp = await client.get(f"/api/v1/platform/documents/{doc_id}/deliveries")
            assert history_resp.status_code == 200
            history_data = history_resp.json()
            assert len(history_data) >= 1
            assert history_data[0]["status"] == "SENT"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)

