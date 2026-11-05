"""Operational Society Expenses API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.application.expense_service import ExpenseService
from apps.api.src.finance.infrastructure.repositories import ExpenseRepository
from apps.api.src.finance.schemas import (
    ExpenseApproveRequest,
    ExpenseCreateRequest,
    ExpenseResponse,
)

router = APIRouter(prefix="/societies/{society_id}/finance/expenses", tags=["Finance - Expenses"])


@router.get("", response_model=list[ExpenseResponse])
async def list_expenses(
    society_id: UUID,
    status: str | None = Query(None, description="Filter by status (DRAFT, APPROVED, POSTED, CANCELLED)"),
    period_id: UUID | None = Query(None, description="Filter by financial period ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> list[ExpenseResponse]:
    """List operational expenses for a society."""
    repo = ExpenseRepository(db)
    expenses = await repo.list_expenses(
        society_id=society_id,
        status=status,
        period_id=period_id,
        limit=limit,
        offset=offset,
    )
    return [ExpenseResponse.model_validate(e) for e in expenses]


@router.post("", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    society_id: UUID,
    payload: ExpenseCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.expense.create")),
) -> ExpenseResponse:
    """Create a draft operational expense."""
    service = ExpenseService(db)
    expense = await service.create_expense(
        society_id=society_id,
        financial_period_id=payload.financial_period_id,
        expense_date=payload.expense_date,
        category_account_id=payload.category_account_id,
        paid_from_account_id=payload.paid_from_account_id,
        description=payload.description,
        amount=payload.amount,
        currency=payload.currency,
        reference_number=payload.reference_number,
        vendor_name=payload.vendor_name,
        created_by=current_user.id,
    )
    return ExpenseResponse.model_validate(expense)


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    society_id: UUID,
    expense_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> ExpenseResponse:
    """Get expense details by ID."""
    repo = ExpenseRepository(db)
    expense = await repo.get_by_id(expense_id, society_id)
    if not expense:
        raise NotFoundException(f"Expense '{expense_id}' not found.")
    return ExpenseResponse.model_validate(expense)


@router.post("/{expense_id}/approve", response_model=ExpenseResponse)
async def approve_expense(
    society_id: UUID,
    expense_id: UUID,
    payload: ExpenseApproveRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.expense.approve")),
) -> ExpenseResponse:
    """Approve a draft expense for posting."""
    service = ExpenseService(db)
    expense = await service.approve_expense(
        expense_id=expense_id,
        society_id=society_id,
        approved_by=current_user.id,
    )
    return ExpenseResponse.model_validate(expense)


@router.post("/{expense_id}/post", response_model=ExpenseResponse)
async def post_expense(
    society_id: UUID,
    expense_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.journal.post")),
) -> ExpenseResponse:
    """Post an approved expense by automatically creating a balanced double-entry journal."""
    service = ExpenseService(db)
    expense = await service.post_expense(
        expense_id=expense_id,
        society_id=society_id,
        posted_by=current_user.id,
    )
    return ExpenseResponse.model_validate(expense)
