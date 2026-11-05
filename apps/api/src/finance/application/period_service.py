"""Financial Period Application Service."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import ConflictException, NotFoundException
from apps.api.src.database.models.finance import FinancialPeriod
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.domain.exceptions import (
    ClosedPeriodPostingException,
    CrossTenantFinancialException,
    InvalidFinancialPeriodDateException,
)
from apps.api.src.finance.domain.models import PeriodStatus
from apps.api.src.finance.infrastructure.repositories import PeriodRepository


class PeriodService:
    """Service orchestrating financial reporting periods and posting window boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.period_repo = PeriodRepository(session)
        self.audit_repo = AuditRepository(session)

    async def open_period(
        self,
        society_id: UUID,
        name: str,
        fiscal_year: str,
        start_date: date,
        end_date: date,
        created_by: UUID | None = None,
        currency: str = "INR",
        correlation_id: str | None = None,
    ) -> FinancialPeriod:
        """Create and open a new financial period, validating date ranges."""
        if end_date < start_date:
            raise ConflictException(
                f"Invalid date range: End date ({end_date}) cannot precede start date ({start_date})."
            )

        # Check for overlapping open periods
        existing_periods = await self.period_repo.list_periods(society_id)
        for p in existing_periods:
            if p.status == PeriodStatus.OPEN.value:
                # Overlap check
                if not (end_date < p.start_date or start_date > p.end_date):
                    raise ConflictException(
                        f"Financial period dates overlap with existing open period '{p.name}' "
                        f"({p.start_date} to {p.end_date})."
                    )

        period = await self.period_repo.create_period(
            society_id=society_id,
            name=name,
            fiscal_year=fiscal_year,
            start_date=start_date,
            end_date=end_date,
            created_by=created_by,
            currency=currency,
        )

        await self.audit_repo.log_event(
            action="FINANCE_PERIOD_CREATED",
            entity_type="financial_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={"name": name, "fiscal_year": fiscal_year, "status": period.status},
        )

        return period

    create_period = open_period

    async def close_period(
        self,
        society_id: UUID,
        period_id: UUID,
        closed_by: UUID,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> FinancialPeriod:
        """Close an active financial period, preventing future postings."""
        period = await self.period_repo.get_by_id(period_id, society_id)
        if not period:
            raise NotFoundException(f"Financial period '{period_id}' not found.")

        if period.status == PeriodStatus.CLOSED.value:
            return period

        await self.period_repo.close_period(period.id, closed_by=closed_by)

        await self.audit_repo.log_event(
            action="FINANCE_PERIOD_CLOSED",
            entity_type="financial_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=closed_by,
            correlation_id=correlation_id,
            before_state={"status": PeriodStatus.OPEN.value},
            after_state={
                "status": PeriodStatus.CLOSED.value,
                "closed_at": datetime.now(UTC).isoformat(),
                "reason": reason,
            },
        )

        period.status = PeriodStatus.CLOSED.value
        return period

    async def reopen_period(
        self,
        society_id: UUID,
        period_id: UUID,
        reopened_by: UUID,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> FinancialPeriod:
        """Reopen a closed period under privileged authorization."""
        period = await self.period_repo.get_by_id(period_id, society_id)
        if not period:
            raise NotFoundException(f"Financial period '{period_id}' not found.")

        await self.period_repo.reopen_period(period.id)

        await self.audit_repo.log_event(
            action="FINANCE_PERIOD_REOPENED",
            entity_type="financial_period",
            entity_id=str(period.id),
            society_id=society_id,
            actor_user_id=reopened_by,
            correlation_id=correlation_id,
            before_state={"status": PeriodStatus.CLOSED.value},
            after_state={"status": PeriodStatus.OPEN.value, "reason": reason},
        )

        period.status = PeriodStatus.OPEN.value
        return period

    async def validate_posting_allowed(
        self, society_id: UUID, period_id: UUID, entry_date: date
    ) -> FinancialPeriod:
        """
        Validate that the period is OPEN and that the entry date falls strictly within the period bounds.
        Raises ClosedPeriodPostingException or InvalidFinancialPeriodDateException on failure.
        """
        period = await self.period_repo.get_by_id(period_id, society_id)
        if not period:
            any_period = await self.period_repo.get_by_id(period_id)
            if any_period and any_period.society_id != society_id:
                raise CrossTenantFinancialException(
                    f"Financial period '{period_id}' belongs to a different society."
                )
            raise NotFoundException(f"Financial period '{period_id}' not found for society.")

        if period.status == PeriodStatus.CLOSED.value:
            raise ClosedPeriodPostingException(period_name=period.name, period_id=str(period.id))

        if not (period.start_date <= entry_date <= period.end_date):
            raise InvalidFinancialPeriodDateException(
                entry_date=entry_date.isoformat(),
                start_date=period.start_date.isoformat(),
                end_date=period.end_date.isoformat(),
            )

        return period
