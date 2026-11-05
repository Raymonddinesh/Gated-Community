"""Billing Period Application Service."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.exceptions import (
    BillingPeriodNotFoundException,
    BillingPeriodOverlapException,
    CrossTenantBillingException,
)
from apps.api.src.billing.domain.models import BillingPeriodStatus
from apps.api.src.billing.infrastructure.repositories import BillingPeriodRepository
from apps.api.src.core.exceptions import AppException
from apps.api.src.database.models.billing import BillingPeriod
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.infrastructure.repositories import PeriodRepository


class BillingPeriodService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.period_repo = BillingPeriodRepository(session)
        self.fin_period_repo = PeriodRepository(session)
        self.audit_repo = AuditRepository(session)

    async def list_periods(
        self, society_id: UUID, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[BillingPeriod]:
        return await self.period_repo.list_periods(society_id, status=status, limit=limit, offset=offset)

    async def get_period(self, period_id: UUID, society_id: UUID) -> BillingPeriod:
        period = await self.period_repo.get_by_id(period_id, society_id)
        if not period:
            raise BillingPeriodNotFoundException(period_id)
        return period

    async def create_period(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        period_code: str,
        name: str,
        start_date: date,
        end_date: date,
        billing_date: date,
        due_date: date,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> BillingPeriod:
        if end_date < start_date:
            raise AppException(
                code="INVALID_DATE_RANGE",
                message="Billing period end_date must be on or after start_date.",
                status_code=400,
            )

        # Validate that associated financial period belongs to the same society
        fin_period = await self.fin_period_repo.get_by_id(financial_period_id, society_id)
        if not fin_period:
            raise CrossTenantBillingException("Financial period does not belong to this society.")

        # Check unique period code
        existing = await self.period_repo.get_by_code(period_code, society_id)
        if existing:
            raise BillingPeriodOverlapException(period_code)

        period = await self.period_repo.create_period(
            society_id=society_id,
            financial_period_id=financial_period_id,
            period_code=period_code,
            name=name,
            start_date=start_date,
            end_date=end_date,
            billing_date=billing_date,
            due_date=due_date,
            created_by=created_by,
        )

        await self.audit_repo.log_event(
            action="BILLING_PERIOD_CREATED",
            entity_type="billing_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "period_code": period.period_code,
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "status": period.status,
            },
        )
        return period

    async def close_period(
        self,
        period_id: UUID,
        society_id: UUID,
        closed_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> BillingPeriod:
        period = await self.get_period(period_id, society_id)
        if period.status == BillingPeriodStatus.CLOSED.value:
            return period

        period.status = BillingPeriodStatus.CLOSED.value
        period.closed_at = datetime.now(UTC)
        period.closed_by = closed_by

        await self.audit_repo.log_event(
            action="BILLING_PERIOD_CLOSED",
            entity_type="billing_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=closed_by,
            correlation_id=correlation_id,
            after_state={"status": period.status},
        )
        return period
