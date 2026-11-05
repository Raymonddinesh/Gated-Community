"""Billing Configuration Application Service."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.exceptions import BillingConfigNotFoundException, CrossTenantBillingException
from apps.api.src.billing.infrastructure.repositories import BillingConfigRepository
from apps.api.src.database.models.billing import SocietyBillingConfig
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.infrastructure.repositories import AccountRepository


class BillingConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config_repo = BillingConfigRepository(session)
        self.account_repo = AccountRepository(session)
        self.audit_repo = AuditRepository(session)

    async def get_config(self, society_id: UUID) -> SocietyBillingConfig:
        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise BillingConfigNotFoundException(society_id)
        return config

    async def setup_or_update_config(
        self,
        society_id: UUID,
        receivable_account_id: UUID,
        income_account_id: UUID,
        currency: str = "INR",
        billing_frequency: str = "MONTHLY",
        billing_day: int = 1,
        default_due_days: int = 15,
        late_fee_enabled: bool = False,
        late_fee_type: str = "PERCENTAGE",
        late_fee_rate: Decimal = Decimal("0.0000"),
        grace_period_days: int = 0,
        max_late_fee: Decimal | None = None,
        interest_enabled: bool = False,
        auto_generate_enabled: bool = False,
        approval_required: bool = True,
        default_responsibility: str = "OWNER",
        bank_account_id: UUID | None = None,
        late_fee_income_account_id: UUID | None = None,
        actor_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> SocietyBillingConfig:
        # Validate that referenced accounts belong to the tenant
        recv_acc = await self.account_repo.get_by_id(receivable_account_id, society_id)
        if not recv_acc:
            raise CrossTenantBillingException("Receivable account does not belong to this society.")

        inc_acc = await self.account_repo.get_by_id(income_account_id, society_id)
        if not inc_acc:
            raise CrossTenantBillingException("Income account does not belong to this society.")

        if bank_account_id:
            bank_acc = await self.account_repo.get_by_id(bank_account_id, society_id)
            if not bank_acc:
                raise CrossTenantBillingException("Bank account does not belong to this society.")

        if late_fee_income_account_id:
            lf_acc = await self.account_repo.get_by_id(late_fee_income_account_id, society_id)
            if not lf_acc:
                raise CrossTenantBillingException("Late fee income account does not belong to this society.")

        config = await self.config_repo.create_or_update(
            society_id=society_id,
            receivable_account_id=receivable_account_id,
            income_account_id=income_account_id,
            currency=currency,
            billing_frequency=billing_frequency,
            billing_day=billing_day,
            default_due_days=default_due_days,
            late_fee_enabled=late_fee_enabled,
            late_fee_type=late_fee_type,
            late_fee_rate=late_fee_rate,
            grace_period_days=grace_period_days,
            max_late_fee=max_late_fee,
            interest_enabled=interest_enabled,
            auto_generate_enabled=auto_generate_enabled,
            approval_required=approval_required,
            default_responsibility=default_responsibility,
            bank_account_id=bank_account_id,
            late_fee_income_account_id=late_fee_income_account_id,
            actor_id=actor_id,
        )

        await self.audit_repo.log_event(
            action="BILLING_CONFIG_UPDATED",
            entity_type="society_billing_config",
            entity_id=str(config.id),
            society_id=society_id,
            actor_user_id=actor_id,
            correlation_id=correlation_id,
            after_state={
                "currency": config.currency,
                "billing_frequency": config.billing_frequency,
                "billing_day": config.billing_day,
                "default_due_days": config.default_due_days,
                "late_fee_enabled": config.late_fee_enabled,
                "approval_required": config.approval_required,
            },
        )
        return config
