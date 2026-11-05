"""Phase 21E.2 — Subscription Lifecycle Domain Service.

Centralized state machine and lifecycle manager for SocietySubscription:
- Supported states: TRIAL, ACTIVE, PAST_DUE, SUSPENDED, CANCELLED.
- Strict transition matrix validation with domain-conflict HTTP 409 rejections.
- Pessimistic row locking via SELECT ... FOR UPDATE.
- CANCELLED is a terminal state; payment events or reactivation requests never revive it.
- Complete audit logging in PlatformSubscriptionHistory and PlatformSubscriptionAuditLog.
- Absolute decoupling: Society.status and SocietySubscription.status are strictly independent.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import (
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.subscription import SocietySubscription
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.exceptions import (
    InvalidSubscriptionTransitionException,
    SubscriptionAlreadyCancelledException,
    SubscriptionNotFoundException,
)
from apps.api.src.subscriptions.schemas import (
    SubscriptionTransitionRequest,
    SubscriptionTransitionResponse,
)

logger = logging.getLogger("societysphere.subscriptions.lifecycle")


def _utc_now() -> datetime:
    """Normalize datetime to naive UTC for consistent PostgreSQL comparison."""
    return datetime.now(UTC).replace(tzinfo=None)


class SubscriptionLifecycleService:
    """Domain service managing the subscription state machine and audit lifecycle."""

    # Explicit allowed transitions mapping: Current Status -> Set of permitted next statuses
    PERMITTED_TRANSITIONS: dict[str, set[str]] = {
        SubscriptionStatus.TRIAL: {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.CANCELLED,
        },
        SubscriptionStatus.ACTIVE: {
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.CANCELLED,
        },
        SubscriptionStatus.PAST_DUE: {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.CANCELLED,
        },
        SubscriptionStatus.SUSPENDED: {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.CANCELLED,
        },
        SubscriptionStatus.CANCELLED: set(),  # TERMINAL STATE: zero outgoing transitions permitted
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_subscription_for_update(
        self,
        society_id: UUID,
    ) -> SocietySubscription:
        """Acquire an exclusive row-level lock on the society's subscription."""
        stmt = (
            select(SocietySubscription)
            .where(SocietySubscription.society_id == society_id)
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        sub = res.scalar_one_or_none()
        if not sub:
            raise SubscriptionNotFoundException(society_id=society_id)
        return sub

    def validate_transition(self, current_status: str, target_status: str, society_id: UUID | None = None) -> None:
        """Validate whether a transition from current_status to target_status is permitted.

        Raises:
            SubscriptionAlreadyCancelledException: If attempting to transition from CANCELLED.
            InvalidSubscriptionTransitionException: If transition is prohibited by matrix or already in state.
        """
        if current_status == SubscriptionStatus.CANCELLED:
            raise SubscriptionAlreadyCancelledException(society_id=society_id)

        if current_status == target_status:
            raise InvalidSubscriptionTransitionException(
                from_status=current_status,
                to_status=target_status,
                message=f"Subscription is already in '{current_status}' status. Duplicate transition rejected.",
            )

        permitted = self.PERMITTED_TRANSITIONS.get(current_status, set())
        if target_status not in permitted:
            raise InvalidSubscriptionTransitionException(
                from_status=current_status,
                to_status=target_status,
                message=(
                    f"Illegal state transition from '{current_status}' to '{target_status}'. "
                    f"Permitted next states: {sorted(list(permitted))}."
                ),
            )

    async def transition_subscription(
        self,
        society_id: UUID,
        request: SubscriptionTransitionRequest,
    ) -> SubscriptionTransitionResponse:
        """Atomically transition a subscription to a new lifecycle state.

        Guarantees:
        - Pessimistic row locking with SELECT ... FOR UPDATE.
        - State machine validation.
        - Mutates status and relevant lifecycle timestamps.
        - Appends immutable PlatformSubscriptionHistory record.
        - Appends sensitive-redacted PlatformSubscriptionAuditLog record.
        - Decoupled from Society.status (zero mutation on Society table).
        """
        sub = await self.get_subscription_for_update(society_id)
        now_dt = _utc_now()
        previous_status = sub.status
        target_status = request.to_status.strip().upper()

        # Validate transition eligibility
        self.validate_transition(previous_status, target_status, society_id=society_id)

        # Snapshot before state
        before_state: dict[str, Any] = {
            "status": previous_status,
            "billing_cycle": sub.billing_cycle,
            "auto_renew": sub.auto_renew,
            "past_due_since": sub.past_due_since.isoformat() if sub.past_due_since else None,
            "suspended_at": sub.suspended_at.isoformat() if sub.suspended_at else None,
            "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
            "cancellation_reason": sub.cancellation_reason,
        }

        # Apply state-specific timestamp adjustments
        sub.status = target_status

        if target_status == SubscriptionStatus.PAST_DUE:
            if sub.past_due_since is None:
                sub.past_due_since = now_dt

        elif target_status == SubscriptionStatus.ACTIVE:
            # Payment settlement or reactivation clears delinquency / suspension flags
            sub.past_due_since = None
            sub.suspended_at = None

        elif target_status == SubscriptionStatus.SUSPENDED:
            sub.suspended_at = now_dt

        elif target_status == SubscriptionStatus.CANCELLED:
            sub.cancelled_at = now_dt
            sub.cancellation_reason = request.reason
            sub.auto_renew = False

        after_state: dict[str, Any] = {
            "status": target_status,
            "billing_cycle": sub.billing_cycle,
            "auto_renew": sub.auto_renew,
            "past_due_since": sub.past_due_since.isoformat() if sub.past_due_since else None,
            "suspended_at": sub.suspended_at.isoformat() if sub.suspended_at else None,
            "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
            "cancellation_reason": sub.cancellation_reason,
        }

        # 1. Record in PlatformSubscriptionHistory
        history_entry = PlatformSubscriptionHistory(
            society_id=society_id,
            subscription_id=sub.id,
            previous_plan_id=sub.plan_id,
            new_plan_id=sub.plan_id,
            previous_status=previous_status,
            new_status=target_status,
            previous_cycle=sub.billing_cycle,
            new_cycle=sub.billing_cycle,
            transition_reason=request.reason,
            changed_by=request.actor_id,
            effective_at=now_dt,
        )
        self.session.add(history_entry)

        # 2. Record in PlatformSubscriptionAuditLog
        audit_entry = PlatformSubscriptionAuditLog(
            society_id=society_id,
            entity_type="SUBSCRIPTION",
            entity_id=sub.id,
            action="SUBSCRIPTION_STATUS_CHANGED",
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            correlation_id=request.correlation_id,
            before_state=before_state,
            after_state=after_state,
        )
        self.session.add(audit_entry)

        await self.session.flush()

        logger.info(
            "Subscription %s (Society: %s) transitioned from %s to %s. Reason: %s",
            sub.id,
            society_id,
            previous_status,
            target_status,
            request.reason,
        )

        return SubscriptionTransitionResponse(
            subscription_id=sub.id,
            society_id=society_id,
            previous_status=previous_status,
            current_status=target_status,
            transition_reason=request.reason,
            executed_at=now_dt,
        )

    async def transition_status(
        self,
        society_id: UUID,
        target_status: str | SubscriptionStatus,
        reason: str,
        actor_id: str | None = None,
        target_plan_id: UUID | None = None,
    ) -> SubscriptionTransitionResponse:
        """Convenience method to transition status directly with parameters."""
        status_str = target_status.value if isinstance(target_status, SubscriptionStatus) else str(target_status)

        # If target_plan_id provided, validate plan exists and is active
        if target_plan_id:
            from apps.api.src.database.models.subscription import PlatformSubscriptionPlan
            from apps.api.src.subscriptions.exceptions import PlanInactiveException, PlanNotFoundException

            plan_stmt = select(PlatformSubscriptionPlan).where(PlatformSubscriptionPlan.id == target_plan_id)
            plan = (await self.session.execute(plan_stmt)).scalar_one_or_none()
            if not plan:
                raise PlanNotFoundException(plan_identifier=str(target_plan_id))
            if not plan.is_active or plan.archived_at is not None:
                raise PlanInactiveException(plan_code=plan.plan_code)

        actor_uuid: UUID | None = None
        if actor_id:
            try:
                actor_uuid = UUID(actor_id)
            except (ValueError, AttributeError):
                actor_uuid = None

        request = SubscriptionTransitionRequest(
            to_status=status_str,
            reason=reason,
            actor_id=actor_uuid,
            actor_type="USER" if actor_id else "SYSTEM",
        )
        return await self.transition_subscription(society_id, request)

