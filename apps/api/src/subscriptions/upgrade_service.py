"""Phase 21E.2 — Subscription Upgrade Calculation Service.

Calculates immediate mid-cycle plan upgrades:
- Resolves current and target plan pricing based on billing cycle (MONTHLY vs ANNUAL).
- Calculates second-accurate unused subscription credit using ProrationEngine.
- Calculates target plan charge for the remaining cycle duration.
- Evaluates net payable amount with minimum charge guard (< ₹1.00).
- Pure calculation and audit preview: does not activate subscription or capture payments.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.subscriptions.exceptions import (
    PlanInactiveException,
    PlanNotFoundException,
    ProrationCalculationException,
    SubscriptionAlreadyCancelledException,
    SubscriptionNotFoundException,
)
from apps.api.src.subscriptions.proration_engine import ProrationEngine
from apps.api.src.subscriptions.schemas import UpgradeCalculationResult

MINIMUM_GATEWAY_CHARGE = Decimal("1.00")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SubscriptionUpgradeService:
    """Domain service calculating plan upgrade charges and prorated credits."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _get_plan_rate(self, plan: PlatformSubscriptionPlan, cycle: str) -> Decimal:
        """Resolve plan base price for specified billing cycle."""
        if cycle == "ANNUAL":
            return Decimal(str(plan.annual_price))
        return Decimal(str(plan.monthly_price))

    async def calculate_upgrade(
        self,
        society_id: UUID,
        target_plan_id: UUID,
        effective_at: datetime | None = None,
        *,
        as_of_time: datetime | None = None,
    ) -> UpgradeCalculationResult:
        """Calculate the prorated credit and net payable amount for an immediate plan upgrade.

        Args:
            society_id: The tenant society's identifier.
            target_plan_id: UUID of the target upgrade plan.
            effective_at: Optional exact calculation timestamp (defaults to current UTC time).
            as_of_time: Optional alias for effective_at.

        Returns:
            UpgradeCalculationResult with credit, charge, net payable, and proration fraction.
        """
        # 1. Fetch active subscription
        sub_stmt = select(SocietySubscription).where(SocietySubscription.society_id == society_id)
        sub_res = await self.session.execute(sub_stmt)
        subscription = sub_res.scalar_one_or_none()
        if not subscription:
            raise SubscriptionNotFoundException(society_id=society_id)

        if subscription.status == "CANCELLED":
            raise SubscriptionAlreadyCancelledException(society_id=society_id)

        # 2. Fetch current plan
        curr_plan_stmt = select(PlatformSubscriptionPlan).where(
            PlatformSubscriptionPlan.id == subscription.plan_id
        )
        curr_res = await self.session.execute(curr_plan_stmt)
        current_plan = curr_res.scalar_one_or_none()
        if not current_plan:
            raise PlanNotFoundException(plan_identifier=str(subscription.plan_id))

        # 3. Fetch target plan
        target_plan_stmt = select(PlatformSubscriptionPlan).where(
            PlatformSubscriptionPlan.id == target_plan_id
        )
        target_res = await self.session.execute(target_plan_stmt)
        target_plan = target_res.scalar_one_or_none()
        if not target_plan:
            raise PlanNotFoundException(plan_identifier=str(target_plan_id))

        if not target_plan.is_active or target_plan.archived_at is not None:
            raise PlanInactiveException(plan_code=target_plan.plan_code)

        if target_plan.id == current_plan.id:
            raise ProrationCalculationException("Target plan must be different from current plan.")

        # 4. Resolve rates and timestamps
        eff_dt = as_of_time or effective_at or _utc_now()
        cycle = subscription.billing_cycle
        current_rate = self._get_plan_rate(current_plan, cycle)
        target_rate = self._get_plan_rate(target_plan, cycle)

        period_start = subscription.current_period_start
        period_end = subscription.current_period_end

        # 5. Proration calculations
        # Unused credit from current plan
        credit_result = ProrationEngine.calculate_proration(
            eligible_amount=current_rate,
            period_start=period_start,
            period_end=period_end,
            effective_at=eff_dt,
        )

        # Target plan charge for remaining duration
        charge_result = ProrationEngine.calculate_proration(
            eligible_amount=target_rate,
            period_start=period_start,
            period_end=period_end,
            effective_at=eff_dt,
        )

        unused_credit = credit_result.prorated_amount
        target_charge = charge_result.prorated_amount

        # Net payable calculation
        raw_net = target_charge - unused_credit
        net_payable = max(Decimal("0.00"), raw_net)

        # Minimum charge evaluation (< ₹1.00 waived for gateway processing)
        is_waived = False
        if Decimal("0.00") < net_payable < MINIMUM_GATEWAY_CHARGE:
            is_waived = True

        return UpgradeCalculationResult(
            current_plan_id=current_plan.id,
            current_plan_code=current_plan.plan_code,
            target_plan_id=target_plan.id,
            target_plan_code=target_plan.plan_code,
            current_plan_rate=current_rate,
            target_plan_rate=target_rate,
            unused_credit=unused_credit,
            target_charge=target_charge,
            net_payable=net_payable,
            proration_fraction=credit_result.unused_fraction,
            effective_at=eff_dt,
            period_start=period_start,
            period_end=period_end,
            is_minimum_charge_waived=is_waived,
        )

    async def apply_upgrade(
        self,
        society_id: UUID,
        target_plan_id: UUID,
        actor_id: str | None = None,
        reason: str = "Plan upgrade",
    ) -> UpgradeCalculationResult:
        """Apply an immediate mid-cycle plan upgrade:
        1. Calculates proration details via calculate_upgrade.
        2. Mutates subscription plan_id under row lock.
        3. Appends PlatformSubscriptionHistory entry.
        4. Appends PlatformSubscriptionAuditLog entry.
        """
        from apps.api.src.database.models.platform_billing import (
            PlatformSubscriptionAuditLog,
            PlatformSubscriptionHistory,
        )

        # Row lock subscription
        sub_stmt = (
            select(SocietySubscription)
            .where(SocietySubscription.society_id == society_id)
            .with_for_update()
        )
        sub_res = await self.session.execute(sub_stmt)
        subscription = sub_res.scalar_one_or_none()
        if not subscription:
            raise SubscriptionNotFoundException(society_id=society_id)

        calc = await self.calculate_upgrade(society_id, target_plan_id)
        previous_plan_id = subscription.plan_id
        subscription.plan_id = target_plan_id
        now_dt = _utc_now()

        actor_uuid: UUID | None = None
        if actor_id:
            try:
                actor_uuid = UUID(actor_id)
            except (ValueError, AttributeError):
                actor_uuid = None

        history_entry = PlatformSubscriptionHistory(
            society_id=society_id,
            subscription_id=subscription.id,
            previous_plan_id=previous_plan_id,
            new_plan_id=target_plan_id,
            previous_status=subscription.status,
            new_status=subscription.status,
            previous_cycle=subscription.billing_cycle,
            new_cycle=subscription.billing_cycle,
            transition_reason=f"UPGRADE: {reason}",
            changed_by=actor_uuid,
            effective_at=now_dt,
        )
        self.session.add(history_entry)

        audit_entry = PlatformSubscriptionAuditLog(
            society_id=society_id,
            entity_type="SUBSCRIPTION",
            entity_id=subscription.id,
            action="UPGRADE_APPLIED",
            actor_type="USER" if actor_id else "SYSTEM",
            actor_id=actor_uuid,
            before_state={"plan_id": str(previous_plan_id)},
            after_state={"plan_id": str(target_plan_id), "net_payable": str(calc.net_payable)},
        )
        self.session.add(audit_entry)
        await self.session.flush()

        return calc

