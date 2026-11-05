"""Maintenance Charge Rules API Endpoints."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.rule_service import ChargeRuleService
from apps.api.src.billing.schemas import ChargeRuleCreateRequest, ChargeRuleResponse
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/rules", tags=["Billing - Charge Rules"])


@router.get("", response_model=list[ChargeRuleResponse])
async def list_charge_rules(
    society_id: UUID,
    on_date: date | None = Query(None, description="Filter rules active on specific date"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.rule.manage")),
) -> list[ChargeRuleResponse]:
    """List maintenance charge calculation rules for a society."""
    service = ChargeRuleService(db)
    rules = await service.list_rules(society_id, on_date)
    return [ChargeRuleResponse.model_validate(r) for r in rules]


@router.post("", response_model=ChargeRuleResponse, status_code=201)
async def create_charge_rule(
    society_id: UUID,
    payload: ChargeRuleCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("billing.rule.manage")),
) -> ChargeRuleResponse:
    """Create a new configurable maintenance charge rule."""
    service = ChargeRuleService(db)
    rule = await service.create_rule(
        society_id=society_id,
        name=payload.name,
        code=payload.code,
        calculation_type=payload.calculation_type,
        rate_or_amount=payload.rate_or_amount,
        income_account_id=payload.income_account_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        unit_type_rates=payload.unit_type_rates,
        description=payload.description,
        created_by=current_user.id,
    )
    return ChargeRuleResponse.model_validate(rule)
