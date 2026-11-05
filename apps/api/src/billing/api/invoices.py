"""Maintenance Invoices API Endpoints."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.invoice_service import InvoiceService
from apps.api.src.billing.schemas import (
    CreditDebitNoteCreateRequest,
    CreditDebitNoteResponse,
    InvoiceAdjustmentRequest,
    InvoiceAdjustmentResponse,
    InvoiceLineResponse,
    InvoiceResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing", tags=["Billing - Invoices"])


def _to_invoice_response(inv: Any) -> InvoiceResponse:
    lines = [
        InvoiceLineResponse(
            id=line.id,
            line_number=line.line_number,
            description=line.description,
            quantity=line.quantity,
            unit_rate=line.unit_rate,
            amount=line.amount,
            accounting_account_id=line.accounting_account_id,
            charge_rule_id=line.charge_rule_id,
            charge_rule_snapshot=line.charge_rule_snapshot,
        )
        for line in getattr(inv, "lines", [])
    ]
    adjustments = [
        InvoiceAdjustmentResponse(
            id=adj.id,
            adjustment_type=adj.adjustment_type,
            amount=adj.amount,
            reason=adj.reason,
            created_at=adj.created_at,
        )
        for adj in getattr(inv, "adjustments", [])
    ]
    return InvoiceResponse(
        id=inv.id,
        society_id=inv.society_id,
        billing_period_id=inv.billing_period_id,
        unit_id=inv.unit_id,
        unit_number=inv.unit.unit_number if getattr(inv, "unit", None) else None,
        responsible_user_id=inv.responsible_user_id,
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        subtotal=inv.subtotal,
        adjustment_total=inv.adjustment_total,
        late_fee_total=inv.late_fee_total,
        tax_total=inv.tax_total,
        grand_total=inv.grand_total,
        paid_amount=inv.paid_amount,
        outstanding_amount=inv.outstanding_amount,
        status=inv.status,
        currency=inv.currency,
        journal_entry_id=inv.journal_entry_id,
        accounting_status=inv.accounting_status,
        accounting_error=inv.accounting_error,
        published_at=inv.published_at,
        lines=lines,
        adjustments=adjustments,
        created_at=inv.created_at,
    )


@router.post("/periods/{period_id}/generate", response_model=list[InvoiceResponse], status_code=201)
async def generate_invoices(
    society_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.generate")),
) -> list[InvoiceResponse]:
    """Deterministically generate maintenance invoices for an open billing period."""
    service = InvoiceService(db)
    invoices = await service.generate_invoices_for_period(
        society_id=society_id,
        billing_period_id=period_id,
        generated_by=current_user.id,
    )
    return [_to_invoice_response(inv) for inv in invoices]


@router.post("/periods/{period_id}/approve")
async def approve_billing_period(
    society_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.approve")),
) -> dict[str, Any]:
    """Approve generated invoices in a billing period for publication."""
    service = InvoiceService(db)
    period = await service.approve_period(
        society_id=society_id,
        billing_period_id=period_id,
        approved_by=current_user.id,
    )
    return {"message": "Billing period approved", "period_id": str(period.id), "status": period.status}


@router.post("/periods/{period_id}/publish")
async def publish_billing_period(
    society_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.publish")),
) -> dict[str, Any]:
    """Publish invoices and atomically post balanced entries to Phase 4 Accounting Core."""
    service = InvoiceService(db)
    period = await service.publish_period(
        society_id=society_id,
        billing_period_id=period_id,
        published_by=current_user.id,
    )
    return {"message": "Billing period published and integrated with general ledger", "status": period.status}


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    society_id: UUID,
    billing_period_id: UUID | None = Query(None),
    unit_id: UUID | None = Query(None),
    responsible_user_id: UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.review")),
) -> list[InvoiceResponse]:
    """List maintenance invoices with filtering."""
    service = InvoiceService(db)
    invoices = await service.list_invoices(
        society_id=society_id,
        billing_period_id=billing_period_id,
        unit_id=unit_id,
        responsible_user_id=responsible_user_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_to_invoice_response(inv) for inv in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    society_id: UUID,
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.review")),
) -> InvoiceResponse:
    """Get single invoice details with line breakdowns and adjustments."""
    service = InvoiceService(db)
    invoice = await service.get_invoice(invoice_id, society_id)
    return _to_invoice_response(invoice)


@router.post("/invoices/{invoice_id}/adjustments", response_model=InvoiceResponse)
async def apply_invoice_adjustment(
    society_id: UUID,
    invoice_id: UUID,
    payload: InvoiceAdjustmentRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.adjust")),
) -> InvoiceResponse:
    """Apply an audited discount, waiver, surcharge, or correction to an invoice."""
    service = InvoiceService(db)
    updated_inv = await service.apply_adjustment(
        society_id=society_id,
        invoice_id=invoice_id,
        adjustment_type=payload.adjustment_type,
        amount=payload.amount,
        reason=payload.reason,
        created_by=current_user.id,
    )
    return _to_invoice_response(updated_inv)


@router.post("/invoices/{invoice_id}/notes", response_model=CreditDebitNoteResponse, status_code=201)
async def issue_credit_debit_note(
    society_id: UUID,
    invoice_id: UUID,
    payload: CreditDebitNoteCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.credit_note")),
) -> CreditDebitNoteResponse:
    """Issue a Credit Note or Debit Note with balanced general ledger journal integration."""
    service = InvoiceService(db)
    note = await service.issue_credit_debit_note(
        society_id=society_id,
        invoice_id=invoice_id,
        note_type=payload.note_type,
        amount=payload.amount,
        reason=payload.reason,
        created_by=current_user.id,
    )
    return CreditDebitNoteResponse.model_validate(note)


@router.post("/invoices/{invoice_id}/late-fee")
async def apply_late_fee(
    society_id: UUID,
    invoice_id: UUID,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.adjust")),
) -> dict[str, Any]:
    """Deterministically apply configured late fee to overdue invoice."""
    service = InvoiceService(db)
    check_date = as_of_date or date.today()
    fee = await service.apply_late_fees(
        society_id=society_id,
        invoice_id=invoice_id,
        as_of_date=check_date,
        applied_by=current_user.id,
    )
    return {"message": "Late fee processed", "fee_applied": str(fee)}
