"""Maintenance Charge Rule Application Service."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.exceptions import (
    CrossTenantBillingException,
    InvalidChargeRuleException,
)
from apps.api.src.billing.domain.models import ChargeCalculationType
from apps.api.src.billing.infrastructure.repositories import ChargeRuleRepository
from apps.api.src.core.exceptions import ConflictException, NotFoundException
from apps.api.src.database.models.billing import MaintenanceChargeRule
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.infrastructure.repositories import AccountRepository


class ChargeRuleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.rule_repo = ChargeRuleRepository(session)
        self.account_repo = AccountRepository(session)
        self.audit_repo = AuditRepository(session)

    async def list_rules(self, society_id: UUID, on_date: date | None = None) -> list[MaintenanceChargeRule]:
        return await self.rule_repo.list_active_rules(society_id, on_date)

    async def get_rule_by_id(self, rule_id: UUID, society_id: UUID) -> MaintenanceChargeRule:
        rule = await self.rule_repo.get_by_id(rule_id, society_id)
        if not rule:
            raise NotFoundException(f"Charge rule '{rule_id}' not found.")
        return rule

    async def create_rule(
        self,
        society_id: UUID,
        name: str,
        code: str,
        calculation_type: str,
        rate_or_amount: Decimal,
        income_account_id: UUID,
        effective_from: date,
        effective_to: date | None = None,
        unit_type_rates: dict[str, Any] | None = None,
        description: str | None = None,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> MaintenanceChargeRule:
        # Validate calculation type
        valid_types = [t.value for t in ChargeCalculationType]
        if calculation_type not in valid_types:
            raise InvalidChargeRuleException(f"Unsupported calculation type '{calculation_type}'.")

        # Validate effective date range
        if effective_to and effective_to < effective_from:
            raise InvalidChargeRuleException("effective_to cannot be earlier than effective_from.")

        # Check unique code
        existing = await self.rule_repo.get_by_code(code, society_id)
        if existing:
            raise ConflictException(f"A charge rule with code '{code}' already exists for this society.")

        # Validate income account belongs to society
        acc = await self.account_repo.get_by_id(income_account_id, society_id)
        if not acc:
            raise CrossTenantBillingException("Income account does not belong to this society.")

        rule = await self.rule_repo.create_rule(
            society_id=society_id,
            name=name,
            code=code,
            calculation_type=calculation_type,
            rate_or_amount=rate_or_amount,
            income_account_id=income_account_id,
            effective_from=effective_from,
            effective_to=effective_to,
            unit_type_rates=unit_type_rates,
            description=description,
            created_by=created_by,
        )

        await self.audit_repo.log_event(
            action="BILLING_RULE_CREATED",
            entity_type="billing_rule",
            entity_id=str(rule.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "code": rule.code,
                "calculation_type": rule.calculation_type,
                "rate_or_amount": str(rule.rate_or_amount),
                "effective_from": rule.effective_from.isoformat(),
            },
        )
        return rule
