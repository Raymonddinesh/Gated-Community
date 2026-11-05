"""Billing Configuration API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.config_service import BillingConfigService
from apps.api.src.billing.schemas import BillingConfigCreateUpdateRequest, BillingConfigResponse
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/config", tags=["Billing - Configuration"])


@router.get("", response_model=BillingConfigResponse)
async def get_billing_config(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.config.manage")),
) -> BillingConfigResponse:
    """Retrieve billing configuration for a society."""
    service = BillingConfigService(db)
    config = await service.get_config(society_id)
    return BillingConfigResponse.model_validate(config)


@router.put("", response_model=BillingConfigResponse)
async def update_billing_config(
    society_id: UUID,
    payload: BillingConfigCreateUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.config.manage")),
) -> BillingConfigResponse:
    """Create or update society billing configuration."""
    service = BillingConfigService(db)
    config = await service.setup_or_update_config(
        society_id=society_id,
        receivable_account_id=payload.receivable_account_id,
        income_account_id=payload.income_account_id,
        currency=payload.currency,
        billing_frequency=payload.billing_frequency,
        billing_day=payload.billing_day,
        default_due_days=payload.default_due_days,
        late_fee_enabled=payload.late_fee_enabled,
        late_fee_type=payload.late_fee_type,
        late_fee_rate=payload.late_fee_rate,
        grace_period_days=payload.grace_period_days,
        max_late_fee=payload.max_late_fee,
        interest_enabled=payload.interest_enabled,
        auto_generate_enabled=payload.auto_generate_enabled,
        approval_required=payload.approval_required,
        default_responsibility=payload.default_responsibility,
        bank_account_id=payload.bank_account_id,
        late_fee_income_account_id=payload.late_fee_income_account_id,
        actor_id=current_user.id,
    )
    return BillingConfigResponse.model_validate(config)
