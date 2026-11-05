"""Chart of Accounts API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.application.account_service import AccountService
from apps.api.src.finance.infrastructure.repositories import AccountRepository
from apps.api.src.finance.schemas import (
    AccountCreateRequest,
    AccountResponse,
    AccountUpdateRequest,
)

router = APIRouter(prefix="/societies/{society_id}/finance/accounts", tags=["Finance - Chart of Accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    society_id: UUID,
    account_type: str | None = Query(None, description="Filter by account type"),
    include_inactive: bool = Query(False, description="Include deactivated accounts"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> list[AccountResponse]:
    """List chart of accounts for a society."""
    repo = AccountRepository(db)
    accounts = await repo.list_accounts(
        society_id=society_id,
        account_type=account_type,
        include_inactive=include_inactive,
    )
    return [AccountResponse.model_validate(a) for a in accounts]


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    society_id: UUID,
    payload: AccountCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.account.manage")),
) -> AccountResponse:
    """Create a new account in the Chart of Accounts."""
    service = AccountService(db)
    account = await service.create_account(
        society_id=society_id,
        account_code=payload.account_code,
        account_name=payload.account_name,
        account_type=payload.account_type,
        normal_balance=payload.normal_balance,
        parent_account_id=payload.parent_account_id,
        sub_type=payload.sub_type,
        currency=payload.currency,
        is_system_account=payload.is_system_account,
        created_by=current_user.id,
    )
    return AccountResponse.model_validate(account)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    society_id: UUID,
    account_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> AccountResponse:
    """Get account details by ID."""
    repo = AccountRepository(db)
    account = await repo.get_by_id(account_id, society_id)
    if not account:
        raise NotFoundException(f"Account '{account_id}' not found.")
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    society_id: UUID,
    account_id: UUID,
    payload: AccountUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.account.manage")),
) -> AccountResponse:
    """Update mutable properties of an account."""
    service = AccountService(db)
    if payload.is_active is False:
        deactivated = await service.deactivate_account(society_id, account_id, deactivated_by=current_user.id)
        return AccountResponse.model_validate(deactivated)

    repo = AccountRepository(db)
    account = await repo.get_by_id(account_id, society_id)
    if not account:
        raise NotFoundException(f"Account '{account_id}' not found.")
    if payload.account_name:
        account.account_name = payload.account_name
    if payload.sub_type is not None:
        account.sub_type = payload.sub_type
    if payload.is_active is True:
        account.is_active = True
    await db.commit()
    await db.refresh(account)

    return AccountResponse.model_validate(account)
