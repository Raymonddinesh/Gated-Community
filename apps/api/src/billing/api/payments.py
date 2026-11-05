"""Payments and Allocation API Endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.payment_service import PaymentService
from apps.api.src.billing.schemas import (
    PaymentAllocationRequest,
    PaymentAllocationResponse,
    PaymentBounceRequest,
    PaymentClearRequest,
    PaymentCreateRequest,
    PaymentRefundRequest,
    PaymentResponse,
    PaymentReverseRequest,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/payments", tags=["Billing - Payments"])


def _to_payment_response(p: Any) -> PaymentResponse:
    allocations = [
        PaymentAllocationResponse(
            id=a.id,
            payment_id=a.payment_id,
            invoice_id=a.invoice_id,
            amount=a.amount,
            allocated_at=a.allocated_at,
            status=getattr(a, "status", "ACTIVE"),
            reversed_at=getattr(a, "reversed_at", None),
            reversal_reason=getattr(a, "reversal_reason", None),
            reversal_reference=getattr(a, "reversal_reference", None),
        )
        for a in getattr(p, "allocations", [])
    ]
    return PaymentResponse(
        id=p.id,
        society_id=p.society_id,
        payer_user_id=p.payer_user_id,
        unit_id=p.unit_id,
        bank_account_id=p.bank_account_id,
        amount=p.amount,
        currency=p.currency,
        payment_date=p.payment_date,
        payment_method=p.payment_method,
        reference_number=p.reference_number,
        notes=p.notes,
        status=p.status,
        allocated_amount=p.allocated_amount,
        unallocated_amount=p.unallocated_amount,
        idempotency_key=p.idempotency_key,
        journal_entry_id=p.journal_entry_id,
        reversal_journal_entry_id=p.reversal_journal_entry_id,
        reversal_reason=p.reversal_reason,
        reversed_at=p.reversed_at,
        allocations=allocations,
        created_at=p.created_at,
    )


@router.post("", response_model=PaymentResponse, status_code=201)
async def record_payment(
    society_id: UUID,
    payload: PaymentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> PaymentResponse:
    """Record a resident payment with optional automated FIFO allocation."""
    service = PaymentService(db)
    payment = await service.record_payment(
        society_id=society_id,
        payer_user_id=payload.payer_user_id,
        amount=payload.amount,
        payment_date=payload.payment_date,
        reference_number=payload.reference_number,
        payment_method=payload.payment_method,
        unit_id=payload.unit_id,
        bank_account_id=payload.bank_account_id,
        notes=payload.notes,
        currency=payload.currency,
        idempotency_key=payload.idempotency_key,
        created_by=current_user.id,
        auto_allocate=payload.auto_allocate,
        auto_clear=payload.auto_clear,
    )
    return _to_payment_response(payment)


@router.get("", response_model=list[PaymentResponse])
async def list_payments(
    society_id: UUID,
    payer_user_id: UUID | None = Query(None),
    unit_id: UUID | None = Query(None),
    bank_account_id: UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.payment.record")),
) -> list[PaymentResponse]:
    """List recorded maintenance payments."""
    service = PaymentService(db)
    payments = await service.list_payments(
        society_id=society_id,
        payer_user_id=payer_user_id,
        unit_id=unit_id,
        bank_account_id=bank_account_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_to_payment_response(p) for p in payments]


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    society_id: UUID,
    payment_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.payment.record")),
) -> PaymentResponse:
    """Get single payment details."""
    service = PaymentService(db)
    payment = await service.get_payment(payment_id, society_id)
    return _to_payment_response(payment)


@router.post("/{payment_id}/allocate", response_model=PaymentResponse)
async def allocate_payment(
    society_id: UUID,
    payment_id: UUID,
    payload: PaymentAllocationRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.allocate")),
) -> PaymentResponse:
    """Explicitly allocate unallocated payment funds against an invoice."""
    service = PaymentService(db)
    payment = await service.allocate_payment(
        society_id=society_id,
        payment_id=payment_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        allocated_by=current_user.id,
    )
    return _to_payment_response(payment)


@router.post("/{payment_id}/clear", response_model=PaymentResponse)
async def clear_payment(
    society_id: UUID,
    payment_id: UUID,
    payload: PaymentClearRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> PaymentResponse:
    """Explicitly clear a recorded payment, posting its double-entry journal to GL."""
    service = PaymentService(db)
    payment = await service.clear_payment(
        society_id=society_id,
        payment_id=payment_id,
        cleared_by=current_user.id,
        cleared_date=payload.cleared_date if payload else None,
    )
    return _to_payment_response(payment)


@router.post("/{payment_id}/bounce", response_model=PaymentResponse)
async def bounce_payment(
    society_id: UUID,
    payment_id: UUID,
    payload: PaymentBounceRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> PaymentResponse:
    """Record instrument bounce, unwinding allocations, cancelling receipt, and reversing journal."""
    service = PaymentService(db)
    payment = await service.bounce_payment(
        society_id=society_id,
        payment_id=payment_id,
        reason=payload.reason,
        bounced_by=current_user.id,
    )
    return _to_payment_response(payment)


@router.post("/{payment_id}/reverse", response_model=PaymentResponse)
async def reverse_payment(
    society_id: UUID,
    payment_id: UUID,
    payload: PaymentReverseRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> PaymentResponse:
    """Reverse a payment, unwinding allocations non-destructively, cancelling receipts, and posting GL reversal."""
    service = PaymentService(db)
    payment = await service.reverse_payment(
        society_id=society_id,
        payment_id=payment_id,
        reason=payload.reason,
        reversed_by=current_user.id,
    )
    return _to_payment_response(payment)


@router.post("/{payment_id}/refund", response_model=PaymentResponse)
async def refund_payment(
    society_id: UUID,
    payment_id: UUID,
    payload: PaymentRefundRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> PaymentResponse:
    """Refund unallocated payment balance back to resident, posting balanced refund journal."""
    service = PaymentService(db)
    payment = await service.refund_payment(
        society_id=society_id,
        payment_id=payment_id,
        amount=payload.amount,
        reason=payload.reason,
        refunded_by=current_user.id,
    )
    return _to_payment_response(payment)
