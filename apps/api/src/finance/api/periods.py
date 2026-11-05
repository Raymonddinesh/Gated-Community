"""Financial Periods API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.application.period_service import PeriodService
from apps.api.src.finance.infrastructure.repositories import PeriodRepository
from apps.api.src.finance.schemas import (
    PeriodCloseRequest,
    PeriodCreateRequest,
    PeriodReopenRequest,
    PeriodResponse,
)

router = APIRouter(prefix="/societies/{society_id}/finance/periods", tags=["Finance - Periods"])


@router.get("", response_model=list[PeriodResponse])
async def list_periods(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> list[PeriodResponse]:
    """List all financial periods for a society."""
    repo = PeriodRepository(db)
    periods = await repo.list_periods(society_id)
    return [PeriodResponse.model_validate(p) for p in periods]


@router.post("", response_model=PeriodResponse, status_code=201)
async def create_period(
    society_id: UUID,
    payload: PeriodCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.account.manage")),
) -> PeriodResponse:
    """Create a new financial period."""
    service = PeriodService(db)
    period = await service.create_period(
        society_id=society_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        fiscal_year=payload.fiscal_year,
        currency=payload.currency,
        created_by=current_user.id,
    )
    return PeriodResponse.model_validate(period)


@router.get("/{period_id}", response_model=PeriodResponse)
async def get_period(
    society_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> PeriodResponse:
    """Get financial period details by ID."""
    repo = PeriodRepository(db)
    period = await repo.get_by_id(society_id, period_id)
    if not period:
        raise NotFoundException(f"Financial period '{period_id}' not found.")
    return PeriodResponse.model_validate(period)


@router.post("/{period_id}/close", response_model=PeriodResponse)
async def close_period(
    society_id: UUID,
    period_id: UUID,
    payload: PeriodCloseRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.period.close")),
) -> PeriodResponse:
    """Close an open financial period, locking it against new journal postings."""
    service = PeriodService(db)
    reason = payload.reason if payload else None
    period = await service.close_period(
        society_id=society_id,
        period_id=period_id,
        closed_by=current_user.id,
        reason=reason,
    )
    return PeriodResponse.model_validate(period)


@router.post("/{period_id}/reopen", response_model=PeriodResponse)
async def reopen_period(
    society_id: UUID,
    period_id: UUID,
    payload: PeriodReopenRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.period.close")),
) -> PeriodResponse:
    """Reopen a closed financial period with mandatory audited justification."""
    service = PeriodService(db)
    period = await service.reopen_period(
        society_id=society_id,
        period_id=period_id,
        reopened_by=current_user.id,
        reason=payload.reason,
    )
    return PeriodResponse.model_validate(period)
