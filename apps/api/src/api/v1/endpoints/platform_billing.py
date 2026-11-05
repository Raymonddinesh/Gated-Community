"""Phase 21E.3 — Platform SaaS Commercial Billing and Payment Gateway Endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_role
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.platform_billing import PlatformCreditNote, PlatformInvoice
from apps.api.src.database.session import get_db_session
from apps.api.src.subscriptions.billing_admin_service import PlatformBillingAdminService
from apps.api.src.subscriptions.billing_api_schemas import (
    PaginatedResponse,
    PlatformBillingAdjustmentCreate,
    PlatformBillingAdjustmentResponse,
    PlatformPaymentDetailResponse,
    PlatformPaymentListItemResponse,
    PlatformPlanCreateRequest,
    PlatformPlanUpdateRequest,
    PlatformRefundListItemResponse,
    PlatformSubscriptionListItemResponse,
    PlatformSubscriptionPlanResponse,
    SocietyAdvanceBalanceResponse,
)
from apps.api.src.subscriptions.credit_notes import (
    CreditNotePreviewResponse,
    CreditNoteTaxSnapshotVerificationResponse,
    PlatformCreditNoteCreateDraft,
    PlatformCreditNotePreviewRequest,
    PlatformCreditNoteResponse,
    PlatformCreditNoteService,
    PlatformCreditNoteUpdateDraft,
    PlatformCreditNoteVoidRequest,
)
from apps.api.src.subscriptions.documents import (
    PlatformBillingDocumentService,
    PlatformDocumentDeliveryResponse,
    PlatformDocumentDownloadUrlResponse,
    PlatformDocumentEmailRequest,
)
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceResponse,
    PlatformInvoiceUpdateDraft,
    PlatformInvoiceVoidRequest,
    TaxSnapshotVerificationResponse,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.payments.exceptions import (
    InvoiceNotFoundException,
    WebhookSignatureVerificationException,
)
from apps.api.src.subscriptions.payments.order_service import PaymentOrderService
from apps.api.src.subscriptions.payments.reconciliation_service import PaymentReconciliationService
from apps.api.src.subscriptions.payments.refund_service import RefundService
from apps.api.src.subscriptions.payments.schemas import (
    PaymentOrderCreateRequest,
    PaymentOrderResponse,
    PaymentVerificationRequest,
    PaymentVerificationResponse,
    ReconciliationReportResponse,
    RefundInitiationRequest,
    RefundResponse,
    WebhookIngestResponse,
)
from apps.api.src.subscriptions.payments.verification_service import PaymentVerificationService
from apps.api.src.subscriptions.payments.webhook_ingestion_service import WebhookIngestionService
from apps.api.src.subscriptions.schemas import (
    SubscriptionTransitionRequest,
    SubscriptionTransitionResponse,
)
from apps.api.src.subscriptions.subscription_lifecycle_service import SubscriptionLifecycleService

logger = logging.getLogger("societysphere.api.platform_billing")

router = APIRouter(prefix="/platform", tags=["Platform SaaS Commercial Billing"])


# ==============================================================================
# 1. Inbound Gateway Webhook Endpoint
# ==============================================================================


@router.post(
    "/webhooks/{provider}",
    response_model=WebhookIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest Payment Gateway Webhook",
)
async def ingest_gateway_webhook(
    provider: str,
    request: Request,
    x_razorpay_signature: str | None = Header(None, alias="X-Razorpay-Signature"),
    session: AsyncSession = Depends(get_db_session),
) -> WebhookIngestResponse:
    """Ingest, verify, and durably persist inbound payment gateway webhooks.

    Security & Guarantees:
    - Raw request body verification using provider-specific HMAC-SHA256 signature.
    - Zero trust on unverified payloads: invalid signatures immediately rejected with HTTP 401.
    - Durable persistence in PlatformWebhookEvent table before HTTP 200 acknowledgment.
    - Primary duplicate protection via UNIQUE(gateway_provider, event_id).
    - Separation of ingestion and background processing.
    """
    raw_body = await request.body()
    signature = (
        x_razorpay_signature
        or request.headers.get("x-razorpay-signature")
        or request.headers.get("X-Signature")
    )

    if not signature:
        logger.warning("Webhook request missing signature header for provider '%s'", provider)
        raise WebhookSignatureVerificationException(provider=provider)

    ingest_service = WebhookIngestionService(session)
    return await ingest_service.ingest_webhook(
        gateway_provider=provider,
        raw_body=raw_body,
        signature_header=signature,
    )


# ==============================================================================
# 2. Server-Side Payment Order Creation
# ==============================================================================


@router.post(
    "/payments/orders",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Server-Side Checkout Payment Order",
)
async def create_payment_order(
    payload: PaymentOrderCreateRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentOrderResponse:
    """Create a server-authoritative checkout payment order for an issued platform invoice.

    Security & Guarantees:
    - Amount is authoritative and determined directly from invoice.amount_due (zero frontend tampering).
    - Checks invoice status; rejects already paid, void, or uncollectible invoices.
    - Idempotency key prevents duplicate active payment attempts.
    - Persists PlatformPaymentAttempt under tenant context.
    """
    # Resolve society_id from invoice
    stmt = select(PlatformInvoice.society_id).where(PlatformInvoice.id == payload.invoice_id)
    soc_res = await session.execute(stmt)
    society_id = soc_res.scalar_one_or_none()
    if not society_id:
        raise InvoiceNotFoundException(invoice_id=payload.invoice_id)

    order_svc = PaymentOrderService(session)
    return await order_svc.create_payment_order(
        society_id=society_id,
        invoice_id=payload.invoice_id,
        idempotency_key=payload.idempotency_key,
    )


# ==============================================================================
# 3. Server-Side Payment Verification & Settlement
# ==============================================================================


@router.post(
    "/payments/verify",
    response_model=PaymentVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Checkout Signature and Settle Payment",
)
async def verify_payment(
    payload: PaymentVerificationRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentVerificationResponse:
    """Cryptographically verify payment checkout signature and execute atomic settlement.

    Security & Guarantees:
    - Verifies checkout signature HMAC-SHA256(order_id|payment_id).
    - Authoritative out-of-band verification against payment gateway API.
    - Atomic settlement: records PlatformPayment, updates PlatformInvoice, evaluates subscription lifecycle.
    - Decoupling invariant: Society administrative suspension is never overturned by payment settlement.
    """
    stmt = select(PlatformInvoice.society_id).where(PlatformInvoice.id == payload.invoice_id)
    soc_res = await session.execute(stmt)
    society_id = soc_res.scalar_one_or_none()
    if not society_id:
        raise InvoiceNotFoundException(invoice_id=payload.invoice_id)

    verification_svc = PaymentVerificationService(session)
    return await verification_svc.verify_and_settle(
        society_id=society_id,
        invoice_id=payload.invoice_id,
        gateway_order_id=payload.gateway_order_id,
        gateway_payment_id=payload.gateway_payment_id,
        signature=payload.signature,
    )


# ==============================================================================
# 4. Outbound Refund Initiation
# ==============================================================================


@router.post(
    "/payments/{payment_id}/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate Full or Partial Payment Refund",
)
async def initiate_refund(
    payment_id: UUID,
    payload: RefundInitiationRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> RefundResponse:
    """Initiate a full or partial refund for a captured payment.

    Security & Guarantees:
    - Verifies available balance (amount - refunded_amount).
    - Executes outbound refund call to gateway.
    - Updates payment.status (PARTIALLY_REFUNDED / REFUNDED) and appends PlatformRefund.
    - Mandatory Rule: Never automatically generates a credit note.
    """
    from apps.api.src.database.models.platform_billing import PlatformPayment

    stmt = select(PlatformPayment.society_id).where(PlatformPayment.id == payment_id)
    soc_res = await session.execute(stmt)
    society_id = soc_res.scalar_one_or_none()
    if not society_id:
        raise InvoiceNotFoundException(invoice_id=payment_id)

    refund_svc = RefundService(session)
    return await refund_svc.initiate_refund(
        society_id=society_id,
        payment_id=payment_id,
        amount=payload.amount,
        reason=payload.reason,
        initiated_by=str(current_user.id),
    )


# ==============================================================================
# 5. Financial Reconciliation Pass
# ==============================================================================


@router.post(
    "/reconciliation",
    response_model=ReconciliationReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Financial Reconciliation Pass",
)
async def run_reconciliation(
    society_id: UUID | None = Query(None, description="Optional society filter"),
    provider: str = Query("RAZORPAY", description="Gateway provider"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationReportResponse:
    """Execute an independent reconciliation pass between internal records and gateway states.

    Security & Guarantees:
    - Non-mutating: detects and flags discrepancies without silent database alterations.
    - Detects missing provider captures, duplicate captures, amount/currency mismatches,
      and orphaned payments on cancelled subscriptions.
    """
    reconciliation_svc = PaymentReconciliationService(session)
    return await reconciliation_svc.reconcile(
        society_id=society_id,
        provider_name=provider,
    )


# ==============================================================================
# 6. Platform Invoices Lifecycle Endpoints (Phase 21E.4B)
# ==============================================================================


@router.post(
    "/invoices/draft",
    response_model=PlatformInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Draft Platform Invoice",
)
async def create_draft_invoice(
    payload: PlatformInvoiceCreateDraft,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformInvoiceResponse:
    """Create a new platform invoice in DRAFT status."""
    invoice_svc = PlatformInvoiceService()
    res = await invoice_svc.create_draft_invoice(
        session=session,
        payload=payload,
        actor_id=current_user.id,
        actor_type="USER",
    )
    await session.commit()
    return res


@router.get(
    "/invoices",
    response_model=PaginatedResponse[PlatformInvoiceResponse],
    status_code=status.HTTP_200_OK,
    summary="List Platform Invoices",
)
async def list_invoices(
    society_id: UUID | None = Query(None, description="Optional society filter"),
    invoice_status: str | None = Query(None, alias="status", description="Optional status filter"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    limit: int | None = Query(None, ge=1, le=100, description="Legacy limit parameter"),
    offset: int | None = Query(None, ge=0, description="Legacy offset parameter"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformInvoiceResponse]:
    """List platform invoices with standardized pagination and filtering."""
    eff_page_size = limit if limit is not None else page_size
    eff_offset = offset if offset is not None else (page - 1) * eff_page_size
    eff_page = (eff_offset // eff_page_size) + 1 if limit is not None else page

    count_stmt = select(func.count(PlatformInvoice.id))
    if society_id:
        count_stmt = count_stmt.where(PlatformInvoice.society_id == society_id)
    if invoice_status:
        count_stmt = count_stmt.where(PlatformInvoice.status == invoice_status.strip().upper())
    total = (await session.execute(count_stmt)).scalar() or 0
    pages = (total + eff_page_size - 1) // eff_page_size if total > 0 else 1

    invoice_svc = PlatformInvoiceService()
    items = await invoice_svc.list_invoices(
        session=session,
        society_id=society_id,
        status=invoice_status,
        limit=eff_page_size,
        offset=eff_offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=eff_page,
        page_size=eff_page_size,
        pages=pages,
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=PlatformInvoiceResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Platform Invoice",
)
async def get_invoice(
    invoice_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformInvoiceResponse:
    """Retrieve full details of a platform invoice including line items."""
    invoice_svc = PlatformInvoiceService()
    return await invoice_svc.get_invoice(
        session=session,
        invoice_id=invoice_id,
    )


@router.patch(
    "/invoices/{invoice_id}",
    response_model=PlatformInvoiceResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Draft Platform Invoice",
)
async def update_draft_invoice(
    invoice_id: UUID,
    payload: PlatformInvoiceUpdateDraft,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformInvoiceResponse:
    """Update editable fields on a DRAFT platform invoice."""
    invoice_svc = PlatformInvoiceService()
    res = await invoice_svc.update_draft_invoice(
        session=session,
        invoice_id=invoice_id,
        payload=payload,
        actor_id=current_user.id,
        actor_type="USER",
    )
    await session.commit()
    return res


@router.post(
    "/invoices/{invoice_id}/finalize",
    response_model=PlatformInvoiceResponse,
    status_code=status.HTTP_200_OK,
    summary="Finalize Invoice (DRAFT -> ISSUED)",
)
async def finalize_invoice(
    invoice_id: UUID,
    request: Request,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformInvoiceResponse:
    """Atomically finalize a DRAFT invoice to ISSUED status.

    - Allocates official financial-year sequential invoice number.
    - Generates and persists immutable TaxSnapshot with SHA-256 digest.
    - Updates invoice financial totals and records auditable state transition.
    """
    invoice_svc = PlatformInvoiceService()
    ip_addr = request.client.host if request.client else None
    res = await invoice_svc.finalize_invoice(
        session=session,
        invoice_id=invoice_id,
        actor_id=current_user.id,
        actor_type="USER",
        ip_address=ip_addr,
    )
    await session.commit()
    return res


@router.post(
    "/invoices/{invoice_id}/void",
    response_model=PlatformInvoiceResponse,
    status_code=status.HTTP_200_OK,
    summary="Void Platform Invoice",
)
async def void_invoice(
    invoice_id: UUID,
    payload: PlatformInvoiceVoidRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformInvoiceResponse:
    """Void an issued or draft invoice, permanently retaining history and invoice number."""
    invoice_svc = PlatformInvoiceService()
    res = await invoice_svc.void_invoice(
        session=session,
        invoice_id=invoice_id,
        reason=payload.reason,
        actor_id=current_user.id,
        actor_type="USER",
    )
    await session.commit()
    return res


@router.get(
    "/invoices/{invoice_id}/tax-snapshot/verify",
    response_model=TaxSnapshotVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Invoice Tax Snapshot Integrity",
)
async def verify_invoice_tax_snapshot(
    invoice_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> TaxSnapshotVerificationResponse:
    """Cryptographically verify the immutable SHA-256 digest of an invoice's tax snapshot."""
    invoice_svc = PlatformInvoiceService()
    return await invoice_svc.verify_invoice_tax_snapshot(
        session=session,
        invoice_id=invoice_id,
    )


# ==============================================================================
# 5. SaaS Credit Notes (Phase 21E.4C)
# ==============================================================================


@router.post(
    "/credit-notes/draft",
    response_model=PlatformCreditNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Draft Platform Credit Note",
)
async def create_draft_credit_note(
    payload: PlatformCreditNoteCreateDraft,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformCreditNoteResponse:
    """Create a DRAFT credit note against an ISSUED invoice."""
    cn_svc = PlatformCreditNoteService(session)
    res = await cn_svc.create_draft_credit_note(
        payload=payload,
        creator_user_id=current_user.id,
    )
    await session.commit()
    return res


@router.get(
    "/credit-notes/{credit_note_id}",
    response_model=PlatformCreditNoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Platform Credit Note",
)
async def get_credit_note(
    credit_note_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformCreditNoteResponse:
    """Retrieve full details of a credit note including line items."""
    cn_svc = PlatformCreditNoteService(session)
    return await cn_svc.get_credit_note(credit_note_id=credit_note_id)


@router.put(
    "/credit-notes/draft/{credit_note_id}",
    response_model=PlatformCreditNoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Draft Platform Credit Note",
)
async def update_draft_credit_note(
    credit_note_id: UUID,
    payload: PlatformCreditNoteUpdateDraft,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformCreditNoteResponse:
    """Update editable fields on an unissued DRAFT credit note."""
    cn_svc = PlatformCreditNoteService(session)
    res = await cn_svc.update_draft_credit_note(
        credit_note_id=credit_note_id,
        payload=payload,
    )
    await session.commit()
    return res


@router.post(
    "/credit-notes/preview",
    response_model=CreditNotePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate / Preview Credit Note Calculation",
)
async def preview_credit_note(
    payload: PlatformCreditNotePreviewRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> CreditNotePreviewResponse:
    """Simulate credit note calculation, taxes, and resulting invoice balance adjustments."""
    cn_svc = PlatformCreditNoteService(session)
    return await cn_svc.calculate_preview(payload=payload)


@router.post(
    "/credit-notes/{credit_note_id}/issue",
    response_model=PlatformCreditNoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue Platform Credit Note (DRAFT -> ISSUED)",
)
async def issue_credit_note(
    credit_note_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformCreditNoteResponse:
    """Atomically issue a DRAFT credit note.

    - Allocates sequential credit note number under row-level lock.
    - Reverses tax using original invoice TaxSnapshot.
    - Persists immutable credit note TaxSnapshot in audit log.
    - Adjusts invoice balance (and records ADVANCE_BALANCE if payment was already captured).
    """
    cn_svc = PlatformCreditNoteService(session)
    res = await cn_svc.issue_credit_note(
        credit_note_id=credit_note_id,
        issuer_user_id=current_user.id,
    )
    await session.commit()
    return res


@router.post(
    "/credit-notes/{credit_note_id}/void",
    response_model=PlatformCreditNoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Void Platform Credit Note",
)
async def void_credit_note(
    credit_note_id: UUID,
    payload: PlatformCreditNoteVoidRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformCreditNoteResponse:
    """Void an issued credit note, permanently retaining number and reversing invoice balance adjustments."""
    cn_svc = PlatformCreditNoteService(session)
    res = await cn_svc.void_credit_note(
        credit_note_id=credit_note_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return res


@router.get(
    "/credit-notes/{credit_note_id}/tax-snapshot/verify",
    response_model=CreditNoteTaxSnapshotVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Credit Note Tax Snapshot Cryptographic Integrity",
)
async def verify_credit_note_tax_snapshot(
    credit_note_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> CreditNoteTaxSnapshotVerificationResponse:
    """Cryptographically verify the immutable SHA-256 digest of an issued credit note's tax snapshot."""
    cn_svc = PlatformCreditNoteService(session)
    return await cn_svc.get_credit_note_tax_snapshot(credit_note_id=credit_note_id)


@router.get(
    "/credit-notes",
    response_model=PaginatedResponse[PlatformCreditNoteResponse],
    status_code=status.HTTP_200_OK,
    summary="List Platform Credit Notes",
)
async def list_credit_notes(
    society_id: UUID | None = Query(None, description="Filter by society/tenant ID"),
    invoice_id: UUID | None = Query(None, description="Filter by invoice ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status (DRAFT, ISSUED, VOID)"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    limit: int | None = Query(None, ge=1, le=100, description="Legacy limit parameter"),
    offset: int | None = Query(None, ge=0, description="Legacy offset parameter"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformCreditNoteResponse]:
    """List credit notes matching optional filters with standardized pagination."""
    eff_page_size = limit if limit is not None else page_size
    eff_offset = offset if offset is not None else (page - 1) * eff_page_size
    eff_page = (eff_offset // eff_page_size) + 1 if limit is not None else page

    count_stmt = select(func.count(PlatformCreditNote.id))
    if society_id:
        count_stmt = count_stmt.where(PlatformCreditNote.society_id == society_id)
    if invoice_id:
        count_stmt = count_stmt.where(PlatformCreditNote.invoice_id == invoice_id)
    if status_filter:
        count_stmt = count_stmt.where(PlatformCreditNote.status == status_filter.upper())
    total = (await session.execute(count_stmt)).scalar() or 0
    pages = (total + eff_page_size - 1) // eff_page_size if total > 0 else 1

    cn_svc = PlatformCreditNoteService(session)
    items = await cn_svc.list_credit_notes(
        society_id=society_id,
        invoice_id=invoice_id,
        status=status_filter,
        limit=eff_page_size,
        offset=eff_offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=eff_page,
        page_size=eff_page_size,
        pages=pages,
    )


# ==============================================================================
# 8. Platform Billing Documents & Delivery Endpoints (Phase 21E.4D)
# ==============================================================================


@router.get(
    "/invoices/{invoice_id}/pdf",
    status_code=status.HTTP_200_OK,
    summary="Retrieve or Generate Platform Invoice PDF",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Binary PDF document content",
        }
    },
)
async def get_invoice_pdf(
    invoice_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Retrieve existing finalized invoice PDF or generate, store, and return bytes.

    Security & Guarantees:
    - Never generates or returns PDFs for DRAFT invoices (HTTP 400).
    - Computes and verifies SHA-256 checksum on generated content.
    - Subsequent calls retrieve stored binary without re-rendering.
    """
    doc_svc = PlatformBillingDocumentService()
    doc, pdf_bytes = await doc_svc.get_or_generate_invoice_document(
        session=session,
        invoice_id=invoice_id,
        caller_society_id=None,
    )
    await session.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc.document_number}.pdf"',
            "X-Document-Checksum": doc.sha256_checksum,
            "X-Document-ID": str(doc.id),
        },
    )


@router.get(
    "/invoices/{invoice_id}/download-url",
    response_model=PlatformDocumentDownloadUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Presigned Download URL for Platform Invoice PDF",
)
async def get_invoice_download_url(
    invoice_id: UUID,
    expires_in_seconds: int = Query(300, ge=60, le=300, description="URL validity in seconds (max 300)"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDownloadUrlResponse:
    """Generate a short-lived presigned download URL for the invoice PDF."""
    doc_svc = PlatformBillingDocumentService()
    res = await doc_svc.get_invoice_download_url(
        session=session,
        invoice_id=invoice_id,
        caller_society_id=None,
        expires_in_seconds=expires_in_seconds,
    )
    await session.commit()
    return res


@router.post(
    "/invoices/{invoice_id}/send-email",
    response_model=PlatformDocumentDeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Deliver Platform Invoice via Email",
)
async def send_invoice_email(
    invoice_id: UUID,
    payload: PlatformDocumentEmailRequest | None = None,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDeliveryResponse:
    """Queue and execute reliable transactional email delivery of finalized invoice PDF."""
    doc_svc = PlatformBillingDocumentService()
    res = await doc_svc.send_invoice_email(
        session=session,
        invoice_id=invoice_id,
        caller_society_id=None,
        payload=payload,
    )
    await session.commit()
    return res


@router.get(
    "/credit-notes/{credit_note_id}/pdf",
    status_code=status.HTTP_200_OK,
    summary="Retrieve or Generate Platform Credit Note PDF",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Binary PDF document content",
        }
    },
)
async def get_credit_note_pdf(
    credit_note_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Retrieve existing issued credit note PDF or generate, store, and return bytes.

    Security & Guarantees:
    - Never generates or returns PDFs for DRAFT credit notes (HTTP 400).
    - Preserves references to original invoice and reason code.
    - Enforces cryptographic snapshot consistency.
    """
    doc_svc = PlatformBillingDocumentService()
    doc, pdf_bytes = await doc_svc.get_or_generate_credit_note_document(
        session=session,
        credit_note_id=credit_note_id,
        caller_society_id=None,
    )
    await session.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc.document_number}.pdf"',
            "X-Document-Checksum": doc.sha256_checksum,
            "X-Document-ID": str(doc.id),
        },
    )


@router.get(
    "/credit-notes/{credit_note_id}/download-url",
    response_model=PlatformDocumentDownloadUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Presigned Download URL for Platform Credit Note PDF",
)
async def get_credit_note_download_url(
    credit_note_id: UUID,
    expires_in_seconds: int = Query(300, ge=60, le=300, description="URL validity in seconds (max 300)"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDownloadUrlResponse:
    """Generate a short-lived presigned download URL for the credit note PDF."""
    doc_svc = PlatformBillingDocumentService()
    res = await doc_svc.get_credit_note_download_url(
        session=session,
        credit_note_id=credit_note_id,
        caller_society_id=None,
        expires_in_seconds=expires_in_seconds,
    )
    await session.commit()
    return res


@router.post(
    "/credit-notes/{credit_note_id}/send-email",
    response_model=PlatformDocumentDeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Deliver Platform Credit Note via Email",
)
async def send_credit_note_email(
    credit_note_id: UUID,
    payload: PlatformDocumentEmailRequest | None = None,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDeliveryResponse:
    """Queue and execute reliable transactional email delivery of issued credit note PDF."""
    doc_svc = PlatformBillingDocumentService()
    res = await doc_svc.send_credit_note_email(
        session=session,
        credit_note_id=credit_note_id,
        caller_society_id=None,
        payload=payload,
    )
    await session.commit()
    return res


@router.get(
    "/documents/{document_id}/deliveries",
    response_model=list[PlatformDocumentDeliveryResponse],
    status_code=status.HTTP_200_OK,
    summary="List Document Delivery Attempts",
)
async def list_document_deliveries(
    document_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> list[PlatformDocumentDeliveryResponse]:
    """Retrieve full delivery outbox history and provider attempt logs for a billing document."""
    doc_svc = PlatformBillingDocumentService()
    return await doc_svc.list_document_deliveries(
        session=session,
        document_id=document_id,
        caller_society_id=None,
    )


# ==============================================================================
# 9. Platform Subscription Plans Catalog CRUD & Entitlements (Phase 21E.5)
# ==============================================================================


@router.get(
    "/plans",
    response_model=list[PlatformSubscriptionPlanResponse],
    status_code=status.HTTP_200_OK,
    summary="List Platform Subscription Plans",
)
async def list_subscription_plans(
    include_archived: bool = Query(False, description="Include archived plans"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> list[PlatformSubscriptionPlanResponse]:
    """List subscription plans in global catalog with entitlements."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_plans(include_archived=include_archived, is_active=is_active)


@router.get(
    "/plans/{plan_id}",
    response_model=PlatformSubscriptionPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Platform Subscription Plan",
)
async def get_subscription_plan(
    plan_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformSubscriptionPlanResponse:
    """Retrieve full details of a subscription plan including feature and quota entitlements."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.get_plan(plan_id=plan_id)


@router.post(
    "/plans",
    response_model=PlatformSubscriptionPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Platform Subscription Plan",
)
async def create_subscription_plan(
    payload: PlatformPlanCreateRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformSubscriptionPlanResponse:
    """Create a new subscription plan with entitlements in global catalog."""
    admin_svc = PlatformBillingAdminService(session)
    res = await admin_svc.create_plan(payload=payload, actor_id=current_user.id)
    await session.commit()
    return res


@router.patch(
    "/plans/{plan_id}",
    response_model=PlatformSubscriptionPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Platform Subscription Plan",
)
async def update_subscription_plan(
    plan_id: UUID,
    payload: PlatformPlanUpdateRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformSubscriptionPlanResponse:
    """Update editable fields or entitlements on an existing subscription plan."""
    admin_svc = PlatformBillingAdminService(session)
    res = await admin_svc.update_plan(plan_id=plan_id, payload=payload, actor_id=current_user.id)
    await session.commit()
    return res


@router.post(
    "/plans/{plan_id}/archive",
    response_model=PlatformSubscriptionPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive Platform Subscription Plan",
)
async def archive_subscription_plan(
    plan_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformSubscriptionPlanResponse:
    """Soft-archive a subscription plan to prevent new subscriptions while preserving existing contracts."""
    admin_svc = PlatformBillingAdminService(session)
    res = await admin_svc.archive_plan(plan_id=plan_id, actor_id=current_user.id)
    await session.commit()
    return res


# ==============================================================================
# 10. Global Platform Subscription Monitoring (Phase 21E.5)
# ==============================================================================


@router.get(
    "/subscriptions",
    response_model=PaginatedResponse[PlatformSubscriptionListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List Global Society Subscriptions",
)
async def list_global_subscriptions(
    society_id: UUID | None = Query(None, description="Optional society filter"),
    subscription_status: str | None = Query(None, alias="status", description="Optional status filter"),
    plan_code: str | None = Query(None, description="Optional plan code filter"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformSubscriptionListItemResponse]:
    """Paginated global monitoring of all society subscriptions across the platform."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_subscriptions(
        society_id=society_id,
        status=subscription_status,
        plan_code=plan_code,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/subscriptions/{society_id}/transition",
    response_model=SubscriptionTransitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Administrative Subscription State Transition",
)
async def transition_subscription_state(
    society_id: UUID,
    payload: SubscriptionTransitionRequest,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionTransitionResponse:
    """Administratively transition a society's subscription state with audit logging."""
    lifecycle_svc = SubscriptionLifecycleService(session)
    payload.actor_id = current_user.id
    payload.actor_type = "USER"
    res = await lifecycle_svc.transition_subscription(society_id=society_id, request=payload)
    await session.commit()
    return res


# ==============================================================================
# 11. Global Payment Transactions & Refunds (Phase 21E.5)
# ==============================================================================


@router.get(
    "/payments",
    response_model=PaginatedResponse[PlatformPaymentListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List Global Payment Transactions",
)
async def list_global_payments(
    society_id: UUID | None = Query(None, description="Optional society filter"),
    invoice_id: UUID | None = Query(None, description="Optional invoice filter"),
    payment_status: str | None = Query(None, alias="status", description="Optional payment status filter"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformPaymentListItemResponse]:
    """Paginated global listing of all captured payment transactions across all tenants."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_payments(
        society_id=society_id,
        invoice_id=invoice_id,
        status=payment_status,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=PlatformPaymentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Payment Transaction Details",
)
async def get_payment_detail(
    payment_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformPaymentDetailResponse:
    """Retrieve detailed payment transaction record including refund audit history."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.get_payment_detail(payment_id=payment_id)


@router.get(
    "/refunds",
    response_model=PaginatedResponse[PlatformRefundListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List Global Payment Refunds",
)
async def list_global_refunds(
    society_id: UUID | None = Query(None, description="Optional society filter"),
    payment_id: UUID | None = Query(None, description="Optional payment filter"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformRefundListItemResponse]:
    """Paginated global listing of all outbound payment refunds."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_refunds(
        society_id=society_id,
        payment_id=payment_id,
        page=page,
        page_size=page_size,
    )


# ==============================================================================
# 12. Manual Billing Adjustments & Advance Balances (Phase 21E.5)
# ==============================================================================


@router.get(
    "/societies/{society_id}/adjustments",
    response_model=PaginatedResponse[PlatformBillingAdjustmentResponse],
    status_code=status.HTTP_200_OK,
    summary="List Society Billing Adjustments",
)
async def list_society_adjustments(
    society_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformBillingAdjustmentResponse]:
    """List billing adjustments (credits, waivers, proration credits) for a society."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_adjustments(society_id=society_id, page=page, page_size=page_size)


@router.post(
    "/societies/{society_id}/adjustments",
    response_model=PlatformBillingAdjustmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Manual Billing Adjustment",
)
async def create_society_adjustment(
    society_id: UUID,
    payload: PlatformBillingAdjustmentCreate,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformBillingAdjustmentResponse:
    """Create a manual billing adjustment (goodwill waiver, advance credit) with audit log."""
    admin_svc = PlatformBillingAdminService(session)
    res = await admin_svc.create_adjustment(
        society_id=society_id,
        payload=payload,
        actor_id=current_user.id,
    )
    await session.commit()
    return res


@router.get(
    "/societies/{society_id}/advance-balance",
    response_model=SocietyAdvanceBalanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Society Advance Credit Balance",
)
async def get_society_advance_balance(
    society_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyAdvanceBalanceResponse:
    """Retrieve aggregated advance credit balance and ledger totals for a society."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.get_society_advance_balance(society_id=society_id)




