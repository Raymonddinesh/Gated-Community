"""Bank and Cash Reconciliation API Endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.integrity_service import IntegrityReconciliationService
from apps.api.src.billing.application.reconciliation_service import ReconciliationService
from apps.api.src.billing.schemas import (
    ReconciliationItemCreateRequest,
    ReconciliationItemResponse,
    ReconciliationMatchRequest,
    ReconciliationSessionCreateRequest,
    ReconciliationSessionResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/reconciliation", tags=["Billing - Reconciliation"])


def _to_item_response(item: Any) -> ReconciliationItemResponse:
    return ReconciliationItemResponse(
        id=item.id,
        session_id=item.session_id,
        payment_id=item.payment_id,
        transaction_date=item.transaction_date,
        reference_number=item.reference_number,
        description=item.description,
        statement_amount=item.statement_amount,
        recorded_amount=item.recorded_amount,
        discrepancy_amount=item.discrepancy_amount,
        match_status=item.match_status,
        notes=item.notes,
        matched_at=item.matched_at,
    )


def _to_session_response(s: Any) -> ReconciliationSessionResponse:
    items = [_to_item_response(i) for i in getattr(s, "items", [])]
    return ReconciliationSessionResponse(
        id=s.id,
        society_id=s.society_id,
        session_number=s.session_number,
        account_id=s.account_id,
        statement_reference=s.statement_reference,
        statement_start_date=s.statement_start_date,
        statement_end_date=s.statement_end_date,
        opening_balance=s.opening_balance,
        closing_balance=s.closing_balance,
        reconciled_amount=s.reconciled_amount,
        unreconciled_amount=s.unreconciled_amount,
        status=s.status,
        notes=s.notes,
        closed_at=s.closed_at,
        items=items,
        created_at=s.created_at,
    )


@router.post("", response_model=ReconciliationSessionResponse, status_code=201)
async def create_reconciliation_session(
    society_id: UUID,
    payload: ReconciliationSessionCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> ReconciliationSessionResponse:
    """Create a new manual Bank or Cash Account reconciliation session."""
    service = ReconciliationService(db)
    session = await service.create_session(
        society_id=society_id,
        account_id=payload.account_id,
        statement_reference=payload.statement_reference,
        statement_start_date=payload.statement_start_date,
        statement_end_date=payload.statement_end_date,
        opening_balance=payload.opening_balance,
        closing_balance=payload.closing_balance,
        notes=payload.notes,
        created_by=current_user.id,
    )
    return _to_session_response(session)


@router.get("", response_model=list[ReconciliationSessionResponse])
async def list_reconciliation_sessions(
    society_id: UUID,
    account_id: UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.payment.record")),
) -> list[ReconciliationSessionResponse]:
    """List reconciliation sessions for an account."""
    service = ReconciliationService(db)
    sessions = await service.list_sessions(
        society_id=society_id,
        account_id=account_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_to_session_response(s) for s in sessions]


@router.get("/integrity", response_model=dict[str, Any])
async def verify_billing_integrity(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.payment.record")),
) -> dict[str, Any]:
    """Audit mathematical and ledger consistency of billing invoices, payments, and outstanding balances."""
    service = IntegrityReconciliationService(db)
    return await service.verify_society_billing_integrity(society_id)


@router.get("/{session_id}", response_model=ReconciliationSessionResponse)
async def get_reconciliation_session(
    society_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.payment.record")),
) -> ReconciliationSessionResponse:
    """Retrieve details and matched items for a reconciliation session."""
    service = ReconciliationService(db)
    session = await service.get_session(session_id, society_id)
    return _to_session_response(session)


@router.post("/{session_id}/items", response_model=ReconciliationItemResponse, status_code=201)
async def add_statement_item(
    society_id: UUID,
    session_id: UUID,
    payload: ReconciliationItemCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> ReconciliationItemResponse:
    """Add a statement line item to a reconciliation session."""
    service = ReconciliationService(db)
    item = await service.add_statement_item(
        society_id=society_id,
        session_id=session_id,
        transaction_date=payload.transaction_date,
        reference_number=payload.reference_number,
        description=payload.description,
        statement_amount=payload.statement_amount,
        payment_id=payload.payment_id,
        notes=payload.notes,
        matched_by=current_user.id,
    )
    return _to_item_response(item)


@router.post("/{session_id}/items/{item_id}/match", response_model=ReconciliationItemResponse)
async def match_statement_item(
    society_id: UUID,
    session_id: UUID,
    item_id: UUID,
    payload: ReconciliationMatchRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> ReconciliationItemResponse:
    """Match a statement item against a recorded Payment."""
    service = ReconciliationService(db)
    item = await service.match_item(
        society_id=society_id,
        session_id=session_id,
        item_id=item_id,
        payment_id=payload.payment_id,
        matched_by=current_user.id,
    )
    return _to_item_response(item)


@router.post("/{session_id}/close", response_model=ReconciliationSessionResponse)
async def close_reconciliation_session(
    society_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.payment.record")),
) -> ReconciliationSessionResponse:
    """Close and finalize a reconciliation session."""
    service = ReconciliationService(db)
    session = await service.close_session(
        society_id=society_id,
        session_id=session_id,
        closed_by=current_user.id,
    )
    return _to_session_response(session)
