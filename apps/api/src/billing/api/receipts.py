"""Receipts API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.payment_service import PaymentService
from apps.api.src.billing.schemas import ReceiptCancelRequest, ReceiptResponse
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/receipts", tags=["Billing - Receipts"])


@router.get("", response_model=list[ReceiptResponse])
async def list_receipts(
    society_id: UUID,
    payer_user_id: UUID | None = Query(None),
    unit_id: UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.receipt.view")),
) -> list[ReceiptResponse]:
    """List issued payment receipts."""
    service = PaymentService(db)
    receipts = await service.list_receipts(
        society_id=society_id,
        payer_user_id=payer_user_id,
        unit_id=unit_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [ReceiptResponse.model_validate(r) for r in receipts]


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    society_id: UUID,
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.receipt.view")),
) -> ReceiptResponse:
    """Get single receipt by ID."""
    service = PaymentService(db)
    receipt = await service.get_receipt(receipt_id, society_id)
    return ReceiptResponse.model_validate(receipt)


@router.post("/{receipt_id}/cancel", response_model=ReceiptResponse)
async def cancel_receipt(
    society_id: UUID,
    receipt_id: UUID,
    payload: ReceiptCancelRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> ReceiptResponse:
    """Cancel an issued payment receipt without deleting historical record."""
    service = PaymentService(db)
    receipt = await service.cancel_receipt(
        receipt_id=receipt_id,
        society_id=society_id,
        reason=payload.reason,
        cancelled_by=current_user.id,
    )
    return ReceiptResponse.model_validate(receipt)
