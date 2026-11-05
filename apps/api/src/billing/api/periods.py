"""Billing Periods API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.period_service import BillingPeriodService
from apps.api.src.billing.schemas import BillingPeriodCreateRequest, BillingPeriodResponse
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/periods", tags=["Billing - Periods"])


@router.get("", response_model=list[BillingPeriodResponse])
async def list_billing_periods(
    society_id: UUID,
    status: str | None = Query(
        None, description="Filter by status (DRAFT, GENERATED, REVIEW, APPROVED, PUBLISHED, CLOSED)"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.period.create")),
) -> list[BillingPeriodResponse]:
    """List operational billing periods for a society."""
    service = BillingPeriodService(db)
    periods = await service.list_periods(society_id, status=status, limit=limit, offset=offset)
    return [BillingPeriodResponse.model_validate(p) for p in periods]


@router.post("", response_model=BillingPeriodResponse, status_code=201)
async def create_billing_period(
    society_id: UUID,
    payload: BillingPeriodCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.period.create")),
) -> BillingPeriodResponse:
    """Create a new billing period mapped to an open financial period."""
    service = BillingPeriodService(db)
    period = await service.create_period(
        society_id=society_id,
        financial_period_id=payload.financial_period_id,
        period_code=payload.period_code,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        billing_date=payload.billing_date,
        due_date=payload.due_date,
        created_by=current_user.id,
    )
    return BillingPeriodResponse.model_validate(period)


@router.put("/{period_id}/close", response_model=BillingPeriodResponse)
async def close_billing_period(
    society_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.period.create")),
) -> BillingPeriodResponse:
    """Close an operational billing period."""
    service = BillingPeriodService(db)
    period = await service.close_period(period_id, society_id, closed_by=current_user.id)
    return BillingPeriodResponse.model_validate(period)
