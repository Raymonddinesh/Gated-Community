"""Resident Financial Visibility API Endpoints (Self-Service)."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.api.invoices import _to_invoice_response
from apps.api.src.billing.api.payments import _to_payment_response
from apps.api.src.billing.application.invoice_service import InvoiceService
from apps.api.src.billing.application.payment_service import PaymentService
from apps.api.src.billing.domain.models import InvoiceStatus
from apps.api.src.billing.schemas import InvoiceResponse, PaymentResponse, ReceiptResponse
from apps.api.src.core.exceptions import AuthorizationException
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.domain.models import quantize_amount

router = APIRouter(prefix="/societies/{society_id}/billing/my", tags=["Billing - Resident Self-Service"])


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_my_invoices(
    society_id: UUID,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.resident.view")),
) -> list[InvoiceResponse]:
    """Retrieve published invoices issued to the authenticated resident."""
    service = InvoiceService(db)
    # Residents can never see DRAFT or REVIEW invoices
    invoices = await service.list_invoices(
        society_id=society_id,
        responsible_user_id=current_user.id,
        status=status,
        limit=limit,
        offset=offset,
    )
    # Filter out any unpublished invoices from resident visibility
    visible = [
        inv
        for inv in invoices
        if inv.status
        in (
            InvoiceStatus.PUBLISHED.value,
            InvoiceStatus.PARTIALLY_PAID.value,
            InvoiceStatus.PAID.value,
            InvoiceStatus.OVERDUE.value,
        )
    ]
    return [_to_invoice_response(inv) for inv in visible]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_my_invoice_details(
    society_id: UUID,
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.resident.view")),
) -> InvoiceResponse:
    """Retrieve details for a specific invoice owned by the authenticated resident."""
    service = InvoiceService(db)
    invoice = await service.get_invoice(invoice_id, society_id)

    # Strict IDOR guard: Residents cannot inspect other occupants' invoices
    if invoice.responsible_user_id != current_user.id:
        raise AuthorizationException("Access forbidden: You are not authorized to view this invoice.")

    if invoice.status not in (
        InvoiceStatus.PUBLISHED.value,
        InvoiceStatus.PARTIALLY_PAID.value,
        InvoiceStatus.PAID.value,
        InvoiceStatus.OVERDUE.value,
    ):
        raise AuthorizationException("Access forbidden: Invoice has not been published.")

    return _to_invoice_response(invoice)


@router.get("/outstanding")
async def get_my_outstanding_dues(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.resident.view")),
) -> dict[str, Any]:
    """Aggregate total unpaid outstanding dues for the authenticated resident."""
    service = InvoiceService(db)
    invoices = await service.list_invoices(
        society_id=society_id,
        responsible_user_id=current_user.id,
    )
    total_outstanding = Decimal("0.0000")
    unpaid_count = 0
    for inv in invoices:
        if inv.status in (
            InvoiceStatus.PUBLISHED.value,
            InvoiceStatus.PARTIALLY_PAID.value,
            InvoiceStatus.OVERDUE.value,
        ):
            total_outstanding += inv.outstanding_amount
            if inv.outstanding_amount > Decimal("0.0000"):
                unpaid_count += 1

    return {
        "user_id": str(current_user.id),
        "total_outstanding": str(quantize_amount(total_outstanding)),
        "unpaid_invoices_count": unpaid_count,
    }


@router.get("/receipts", response_model=list[ReceiptResponse])
async def list_my_receipts(
    society_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.resident.view")),
) -> list[ReceiptResponse]:
    """List payment receipts issued to the authenticated resident."""
    service = PaymentService(db)
    receipts = await service.list_receipts(
        society_id=society_id,
        payer_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [ReceiptResponse.model_validate(r) for r in receipts]


@router.get("/payments", response_model=list[PaymentResponse])
async def list_my_payments(
    society_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.resident.view")),
) -> list[PaymentResponse]:
    """List payments recorded for the authenticated resident."""
    service = PaymentService(db)
    payments = await service.list_payments(
        society_id=society_id,
        payer_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [_to_payment_response(p) for p in payments]


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_my_payment_details(
    society_id: UUID,
    payment_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.resident.view")),
) -> PaymentResponse:
    """Retrieve details for a specific payment owned by the authenticated resident."""
    service = PaymentService(db)
    payment = await service.get_payment(payment_id, society_id)

    # Strict IDOR guard: Residents can only inspect their own payments
    if payment.payer_user_id != current_user.id:
        raise AuthorizationException("Access forbidden: You are not authorized to view this payment.")

    return _to_payment_response(payment)
