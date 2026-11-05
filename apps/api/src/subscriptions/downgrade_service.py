"""Phase 21E.2 — Subscription Downgrade Service.

Manages scheduled plan downgrades effective at the next renewal boundary:
- Validates target plan exists, is active, and is distinct from current plan.
- Reuses QuotaEnforcementService to validate current tenant usage against target plan quotas.
- Rejects downgrade with DowngradeQuotaViolationException (HTTP 409) if current usage exceeds limits.
- Checks and prevents duplicate downgrade requests.
- Preserves existing entitlements and active plan unchanged until renewal boundary.
- Records scheduled transition in PlatformSubscriptionHistory and PlatformSubscriptionAuditLog.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SubscriptionPlanEntitlement,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.enums import EntitlementType
from apps.api.src.subscriptions.exceptions import (
    DowngradeQuotaViolationException,
    DuplicateDowngradeRequestException,
    PlanInactiveException,
    PlanNotFoundException,
    ProrationCalculationException,
    SubscriptionAlreadyCancelledException,
    SubscriptionNotFoundException,
)
from apps.api.src.subscriptions.quota_enforcement_service import QuotaEnforcementService
from apps.api.src.subscriptions.schemas import ScheduledDowngradeResponse

logger = logging.getLogger("societysphere.subscriptions.downgrade")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SubscriptionDowngradeService:
    """Domain service managing scheduled plan downgrades and quota pre-checks."""

    def __init__(
        self,
        session: AsyncSession,
        quota_service: QuotaEnforcementService | None = None,
    ) -> None:
        self.session = session
        self.quota_service = quota_service or QuotaEnforcementService(session)

    async def schedule_downgrade(
        self,
        society_id: UUID,
        target_plan_id: UUID,
        reason: str,
        actor_id: UUID | str | None = None,
    ) -> ScheduledDowngradeResponse:
        """Schedule a plan downgrade effective at the next billing cycle renewal boundary.

        Guarantees:
        - Evaluates current usage against target plan quotas.
        - Preserves current plan and entitlements immediately.
        - Prevents duplicate scheduled requests.
        - Appends scheduled event to PlatformSubscriptionHistory and audit logs.
        """
        # 1. Fetch active subscription with row lock
        stmt = (
            select(SocietySubscription)
            .where(SocietySubscription.society_id == society_id)
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        sub = res.scalar_one_or_none()
        if not sub:
            raise SubscriptionNotFoundException(society_id=society_id)

        if sub.status == "CANCELLED":
            raise SubscriptionAlreadyCancelledException(society_id=society_id)

        if target_plan_id == sub.plan_id:
            raise ProrationCalculationException("Target plan must be different from current plan.")

        # 2. Fetch target plan
        target_plan_stmt = select(PlatformSubscriptionPlan).where(
            PlatformSubscriptionPlan.id == target_plan_id
        )
        target_res = await self.session.execute(target_plan_stmt)
        target_plan = target_res.scalar_one_or_none()
        if not target_plan:
            raise PlanNotFoundException(plan_identifier=str(target_plan_id))

        if not target_plan.is_active or target_plan.archived_at is not None:
            raise PlanInactiveException(plan_code=target_plan.plan_code)

        # 3. Check for existing duplicate scheduled downgrade
        hist_stmt = (
            select(PlatformSubscriptionHistory)
            .where(
                PlatformSubscriptionHistory.society_id == society_id,
                PlatformSubscriptionHistory.subscription_id == sub.id,
                PlatformSubscriptionHistory.transition_reason.like("SCHEDULED_DOWNGRADE%"),
                PlatformSubscriptionHistory.effective_at >= _utc_now(),
            )
            .order_by(PlatformSubscriptionHistory.effective_at.desc())
        )
        hist_res = await self.session.execute(hist_stmt)
        existing_downgrade = hist_res.scalar_one_or_none()
        if existing_downgrade:
            raise DuplicateDowngradeRequestException(
                scheduled_plan_id=existing_downgrade.new_plan_id
            )

        # 4. Quota Pre-check against target plan
        ent_stmt = select(SubscriptionPlanEntitlement).where(
            SubscriptionPlanEntitlement.plan_id == target_plan_id
        )
        ent_res = await self.session.execute(ent_stmt)
        target_entitlements = ent_res.scalars().all()

        violations: dict[str, dict[str, Any]] = {}
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)
            for ent in target_entitlements:
                if ent.entitlement_type == EntitlementType.NUMERIC or ent.entitlement_key.startswith("quota."):
                    try:
                        target_limit = int(ent.entitlement_value)
                    except (ValueError, TypeError):
                        continue

                    current_usage = await self.quota_service.get_current_usage(
                        society_id, ent.entitlement_key
                    )
                    if current_usage > target_limit:
                        violations[ent.entitlement_key] = {
                            "quota_key": ent.entitlement_key,
                            "current_usage": current_usage,
                            "target_limit": target_limit,
                        }

        if violations:
            raise DowngradeQuotaViolationException(
                target_plan_code=target_plan.plan_code,
                violations=violations,
            )


        actor_uuid: UUID | None = None
        if actor_id:
            if isinstance(actor_id, UUID):
                actor_uuid = actor_id
            else:
                try:
                    actor_uuid = UUID(str(actor_id))
                except (ValueError, AttributeError):
                    actor_uuid = None

        # 5. Record scheduled downgrade in PlatformSubscriptionHistory
        effective_date = sub.current_period_end

        history_entry = PlatformSubscriptionHistory(
            society_id=society_id,
            subscription_id=sub.id,
            previous_plan_id=sub.plan_id,
            new_plan_id=target_plan_id,
            previous_status=sub.status,
            new_status=sub.status,  # Active status is preserved until effective_date
            previous_cycle=sub.billing_cycle,
            new_cycle=sub.billing_cycle,
            transition_reason=f"SCHEDULED_DOWNGRADE: {reason}",
            changed_by=actor_uuid,
            effective_at=effective_date,
        )
        self.session.add(history_entry)

        # 6. Audit log
        audit_entry = PlatformSubscriptionAuditLog(
            society_id=society_id,
            entity_type="SUBSCRIPTION",
            entity_id=sub.id,
            action="SCHEDULE_DOWNGRADE",
            actor_type="USER" if actor_id else "SYSTEM",
            actor_id=actor_uuid,
            before_state={"current_plan_id": str(sub.plan_id)},
            after_state={
                "scheduled_plan_id": str(target_plan_id),
                "target_plan_code": target_plan.plan_code,
                "effective_date": effective_date.isoformat(),
                "reason": reason,
            },
        )
        self.session.add(audit_entry)

        await self.session.flush()

        logger.info(
            "Scheduled downgrade for society %s to plan %s effective at %s",
            society_id,
            target_plan.plan_code,
            effective_date,
        )

        return ScheduledDowngradeResponse(
            subscription_id=sub.id,
            society_id=society_id,
            current_plan_id=sub.plan_id,
            scheduled_plan_id=target_plan_id,
            target_plan_code=target_plan.plan_code,
            effective_date=effective_date,
            reason=reason,
            status="SCHEDULED",
        )

