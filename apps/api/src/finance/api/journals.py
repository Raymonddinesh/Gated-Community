"""Journal Entries API endpoints."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.infrastructure.repositories import JournalRepository
from apps.api.src.finance.schemas import (
    JournalEntryCreateRequest,
    JournalEntryResponse,
    JournalLineResponse,
    JournalReverseRequest,
)

router = APIRouter(prefix="/societies/{society_id}/finance/journals", tags=["Finance - Journal Entries"])


def _to_journal_response(journal: Any) -> JournalEntryResponse:
    lines = []
    for line in journal.lines:
        lines.append(
            JournalLineResponse(
                id=line.id,
                journal_entry_id=line.journal_entry_id,
                account_id=line.account_id,
                account_code=line.account.account_code if getattr(line, "account", None) else None,
                account_name=line.account.account_name if getattr(line, "account", None) else None,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                description=line.description,
            )
        )
    return JournalEntryResponse(
        id=journal.id,
        society_id=journal.society_id,
        financial_period_id=journal.financial_period_id,
        journal_number=journal.journal_number,
        entry_date=journal.entry_date,
        description=journal.description,
        status=journal.status,
        source_type=journal.source_type,
        source_record_id=journal.source_record_id,
        reference_number=journal.reference_number,
        total_debit=journal.total_debit,
        total_credit=journal.total_credit,
        currency=journal.currency,
        posted_at=journal.posted_at,
        posted_by=journal.posted_by,
        reversed_entry_id=journal.reversed_entry_id,
        reversal_reason=journal.reversal_reason,
        idempotency_key=journal.idempotency_key,
        lines=lines,
        created_at=journal.created_at,
        updated_at=journal.updated_at,
    )


@router.get("", response_model=list[JournalEntryResponse])
async def list_journals(
    society_id: UUID,
    status: str | None = Query(None, description="Filter by status (DRAFT, POSTED, REVERSED)"),
    period_id: UUID | None = Query(None, description="Filter by financial period ID"),
    start_date: date | None = Query(None, description="Start date filter"),
    end_date: date | None = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> list[JournalEntryResponse]:
    """List journal entries for a society."""
    repo = JournalRepository(db)
    journals = await repo.list_journals(
        society_id=society_id,
        status=status,
        period_id=period_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return [_to_journal_response(j) for j in journals]


@router.post("", response_model=JournalEntryResponse, status_code=201)
async def create_journal(
    society_id: UUID,
    payload: JournalEntryCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.journal.create")),
) -> JournalEntryResponse:
    """Create a draft double-entry journal."""
    service = JournalService(db)
    lines_data = [
        {
            "account_id": line.account_id,
            "debit_amount": line.debit_amount,
            "credit_amount": line.credit_amount,
            "description": line.description,
        }
        for line in payload.lines
    ]
    journal = await service.create_draft_journal(
        society_id=society_id,
        financial_period_id=payload.financial_period_id,
        entry_date=payload.entry_date,
        description=payload.description,
        lines_data=lines_data,
        source_type=payload.source_type,
        source_record_id=payload.source_record_id,
        reference_number=payload.reference_number,
        currency=payload.currency,
        idempotency_key=payload.idempotency_key,
        created_by=current_user.id,
    )
    # Reload with lines and accounts
    repo = JournalRepository(db)
    reloaded = await repo.get_by_id(journal.id, society_id)
    return _to_journal_response(reloaded or journal)


@router.get("/{journal_id}", response_model=JournalEntryResponse)
async def get_journal(
    society_id: UUID,
    journal_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> JournalEntryResponse:
    """Get single journal entry by ID including its debit/credit line items."""
    repo = JournalRepository(db)
    journal = await repo.get_by_id(journal_id, society_id)
    if not journal:
        raise NotFoundException(f"Journal entry '{journal_id}' not found.")
    return _to_journal_response(journal)


@router.post("/{journal_id}/post", response_model=JournalEntryResponse)
async def post_journal(
    society_id: UUID,
    journal_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.journal.post")),
) -> JournalEntryResponse:
    """Post a draft journal entry to the immutable permanent ledger."""
    service = JournalService(db)
    journal = await service.post_journal(
        society_id=society_id,
        journal_id=journal_id,
        posted_by=current_user.id,
    )
    repo = JournalRepository(db)
    reloaded = await repo.get_by_id(journal.id, society_id)
    return _to_journal_response(reloaded or journal)


@router.post("/{journal_id}/reverse", response_model=JournalEntryResponse)
async def reverse_journal(
    society_id: UUID,
    journal_id: UUID,
    payload: JournalReverseRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.journal.reverse")),
) -> JournalEntryResponse:
    """Create and post a balanced reversal entry for an existing posted journal."""
    service = JournalService(db)
    reversal = await service.reverse_journal(
        society_id=society_id,
        journal_id=journal_id,
        reason=payload.reason,
        reversed_by=current_user.id,
    )
    repo = JournalRepository(db)
    reloaded = await repo.get_by_id(reversal.id, society_id)
    return _to_journal_response(reloaded or reversal)
