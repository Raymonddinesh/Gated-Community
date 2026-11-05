"""Phase 21B — Entitlement Service Domain Layer.

Centralized domain service evaluating features, limits, and quotas according to
strict precedence:
1. Applicable society-specific overrides (SocietyFeatureOverride / SocietyQuotaOverride)
2. Applicable subscription-plan entitlements (SubscriptionPlanEntitlement via SocietySubscription)
3. Explicit conservative system default (fails closed, access denied, limit 0)
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.core.exceptions import AuthorizationException, TenantContextRequiredException
from apps.api.src.core.tenant_context import get_current_tenant_id
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyFeatureOverride,
    SocietyQuotaOverride,
    SocietySubscription,
    SubscriptionPlanEntitlement,
)
from apps.api.src.subscriptions.enums import EntitlementSource, EntitlementType, SubscriptionStatus
from apps.api.src.subscriptions.exceptions import InvalidEntitlementConfigException
from apps.api.src.subscriptions.schemas import EffectiveEntitlement, EffectiveQuota

logger = logging.getLogger("societysphere.subscriptions.entitlement")


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class EntitlementService:
    """Domain service evaluating society feature and quota entitlements.

    Transaction & ORM Safety:
    - All methods in this service are READ-ONLY.
    - No rows are locked or mutated.
    - No database commits are performed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _resolve_trusted_society(self, society_id: UUID | None) -> UUID:
        """Enforce strict tenant boundary check using trusted tenant context."""
        current_tenant = get_current_tenant_id()
        if current_tenant is None:
            raise TenantContextRequiredException(
                "Active tenant context is required for entitlement evaluation."
            )
        if society_id is not None and society_id != current_tenant:
            raise AuthorizationException(
                f"Cross-tenant access forbidden: Cannot operate on society '{society_id}' "
                f"within active tenant context '{current_tenant}'."
            )
        return current_tenant

    async def get_effective_entitlement(
        self,
        society_id: UUID | None,
        entitlement_key: str,
        as_of: datetime | None = None,
    ) -> EffectiveEntitlement:
        """Resolve effective entitlement via the canonical three-tier precedence rules:

        1. Society Override (Feature or Quota)
        2. Subscription Plan Entitlement
        3. Conservative System Default (Fail-Closed)
        """
        target_society_id = self._resolve_trusted_society(society_id)
        now = _ensure_utc(as_of) or datetime.now(UTC)

        # ----------------------------------------------------------------------
        # 1. PRECEDENCE TIER 1: Applicable Society-Specific Override
        # ----------------------------------------------------------------------

        # Check Feature Overrides
        feature_override_stmt = select(SocietyFeatureOverride).where(
            SocietyFeatureOverride.society_id == target_society_id,
            SocietyFeatureOverride.feature_key == entitlement_key,
        )
        result = await self.session.execute(feature_override_stmt)
        feature_override = result.scalar_one_or_none()

        if feature_override is not None:
            effective_from = _ensure_utc(feature_override.effective_from)
            effective_until = _ensure_utc(feature_override.effective_until)

            # Check time-window boundaries
            is_future = effective_from is not None and effective_from > now
            is_expired = effective_until is not None and effective_until < now

            if not is_future and not is_expired:
                logger.debug(
                    f"Entitlement '{entitlement_key}' resolved via FeatureOverride "
                    f"for society {target_society_id}: {feature_override.is_enabled}"
                )
                return EffectiveEntitlement(
                    entitlement_key=entitlement_key,
                    entitlement_type=EntitlementType.BOOLEAN,
                    value=str(feature_override.is_enabled).lower(),
                    source=EntitlementSource.OVERRIDE,
                    is_enabled=feature_override.is_enabled,
                    limit=None,
                    is_unlimited=False,
                    society_id=target_society_id,
                    plan_code=None,
                    override_id=feature_override.id,
                    diagnostics={"override_reason": feature_override.override_reason},
                )

        # Check Quota Overrides
        quota_override_stmt = select(SocietyQuotaOverride).where(
            SocietyQuotaOverride.society_id == target_society_id,
            SocietyQuotaOverride.quota_key == entitlement_key,
        )
        quota_result = await self.session.execute(quota_override_stmt)
        quota_override: SocietyQuotaOverride | None = quota_result.scalar_one_or_none()

        if quota_override is not None:
            effective_from = _ensure_utc(quota_override.effective_from)
            effective_until = _ensure_utc(quota_override.effective_until)

            is_future = effective_from is not None and effective_from > now
            is_expired = effective_until is not None and effective_until < now

            if not is_future and not is_expired:
                logger.debug(
                    f"Entitlement '{entitlement_key}' resolved via QuotaOverride "
                    f"for society {target_society_id}: limit={quota_override.max_limit}"
                )
                return EffectiveEntitlement(
                    entitlement_key=entitlement_key,
                    entitlement_type=EntitlementType.NUMERIC,
                    value=str(quota_override.max_limit),
                    source=EntitlementSource.OVERRIDE,
                    is_enabled=quota_override.max_limit > 0,
                    limit=quota_override.max_limit,
                    is_unlimited=False,
                    society_id=target_society_id,
                    plan_code=None,
                    override_id=quota_override.id,
                    diagnostics={"override_reason": quota_override.override_reason},
                )

        # ----------------------------------------------------------------------
        # 2. PRECEDENCE TIER 2: Active Plan Entitlement via Subscription
        # ----------------------------------------------------------------------
        sub_stmt = (
            select(SocietySubscription)
            .options(
                selectinload(SocietySubscription.plan).selectinload(
                    PlatformSubscriptionPlan.entitlements
                )
            )
            .where(SocietySubscription.society_id == target_society_id)
        )
        sub_result = await self.session.execute(sub_stmt)
        subscription = sub_result.scalar_one_or_none()

        if subscription is None:
            logger.debug(
                f"No subscription found for society {target_society_id}; failing closed."
            )
            return EffectiveEntitlement(
                entitlement_key=entitlement_key,
                entitlement_type=EntitlementType.BOOLEAN,
                value="false",
                source=EntitlementSource.SYSTEM_DEFAULT,
                is_enabled=False,
                limit=0,
                is_unlimited=False,
                society_id=target_society_id,
                plan_code=None,
                override_id=None,
                diagnostics={"reason": "NO_SUBSCRIPTION"},
            )

        # Evaluate subscription lifecycle state
        sub_status = subscription.status.upper()
        if sub_status in (SubscriptionStatus.SUSPENDED.value, SubscriptionStatus.CANCELLED.value):
            logger.debug(
                f"Subscription for society {target_society_id} is {sub_status}; denying access."
            )
            return EffectiveEntitlement(
                entitlement_key=entitlement_key,
                entitlement_type=EntitlementType.BOOLEAN,
                value="false",
                source=EntitlementSource.SYSTEM_DEFAULT,
                is_enabled=False,
                limit=0,
                is_unlimited=False,
                society_id=target_society_id,
                plan_code=subscription.plan.plan_code if subscription.plan else None,
                override_id=None,
                diagnostics={"reason": f"SUBSCRIPTION_{sub_status}"},
            )

        # Evaluate trial expiry
        if sub_status == SubscriptionStatus.TRIAL.value and subscription.trial_ends_at is not None:
            trial_end = _ensure_utc(subscription.trial_ends_at)
            if trial_end is not None and trial_end < now:
                logger.debug(
                    f"Trial expired for society {target_society_id} at {trial_end}; denying access."
                )
                return EffectiveEntitlement(
                    entitlement_key=entitlement_key,
                    entitlement_type=EntitlementType.BOOLEAN,
                    value="false",
                    source=EntitlementSource.SYSTEM_DEFAULT,
                    is_enabled=False,
                    limit=0,
                    is_unlimited=False,
                    society_id=target_society_id,
                    plan_code=subscription.plan.plan_code if subscription.plan else None,
                    override_id=None,
                    diagnostics={"reason": "TRIAL_EXPIRED"},
                )

        # Evaluate plan availability
        plan = subscription.plan
        if plan is None or not plan.is_active or plan.archived_at is not None:
            logger.debug(
                f"Plan for society {target_society_id} is inactive or archived; denying access."
            )
            return EffectiveEntitlement(
                entitlement_key=entitlement_key,
                entitlement_type=EntitlementType.BOOLEAN,
                value="false",
                source=EntitlementSource.SYSTEM_DEFAULT,
                is_enabled=False,
                limit=0,
                is_unlimited=False,
                society_id=target_society_id,
                plan_code=plan.plan_code if plan else None,
                override_id=None,
                diagnostics={"reason": "PLAN_INACTIVE"},
            )

        # Find matching entitlement definition in plan catalog
        matching_entitlement: SubscriptionPlanEntitlement | None = None
        for ent in plan.entitlements:
            if ent.entitlement_key == entitlement_key:
                matching_entitlement = ent
                break

        if matching_entitlement is not None:
            raw_type = matching_entitlement.entitlement_type.upper()
            raw_val = matching_entitlement.entitlement_value.strip()

            if raw_type == EntitlementType.BOOLEAN.value:
                val_lower = raw_val.lower()
                if val_lower in ("true", "1", "yes"):
                    is_en = True
                elif val_lower in ("false", "0", "no"):
                    is_en = False
                else:
                    raise InvalidEntitlementConfigException(
                        f"Invalid boolean value '{raw_val}' configured for entitlement '{entitlement_key}'."
                    )
                return EffectiveEntitlement(
                    entitlement_key=entitlement_key,
                    entitlement_type=EntitlementType.BOOLEAN,
                    value=val_lower,
                    source=EntitlementSource.PLAN,
                    is_enabled=is_en,
                    limit=None,
                    is_unlimited=False,
                    society_id=target_society_id,
                    plan_code=plan.plan_code,
                    override_id=None,
                    diagnostics={"plan_id": str(plan.id)},
                )

            elif raw_type == EntitlementType.NUMERIC.value:
                try:
                    numeric_limit = int(raw_val)
                    if numeric_limit < 0:
                        raise ValueError("Negative numeric limit")
                except ValueError:
                    raise InvalidEntitlementConfigException(
                        f"Invalid numeric value '{raw_val}' configured for entitlement '{entitlement_key}'."
                    )
                return EffectiveEntitlement(
                    entitlement_key=entitlement_key,
                    entitlement_type=EntitlementType.NUMERIC,
                    value=str(numeric_limit),
                    source=EntitlementSource.PLAN,
                    is_enabled=numeric_limit > 0,
                    limit=numeric_limit,
                    is_unlimited=False,
                    society_id=target_society_id,
                    plan_code=plan.plan_code,
                    override_id=None,
                    diagnostics={"plan_id": str(plan.id)},
                )

            elif raw_type == EntitlementType.UNLIMITED.value:
                return EffectiveEntitlement(
                    entitlement_key=entitlement_key,
                    entitlement_type=EntitlementType.UNLIMITED,
                    value="UNLIMITED",
                    source=EntitlementSource.PLAN,
                    is_enabled=True,
                    limit=None,
                    is_unlimited=True,
                    society_id=target_society_id,
                    plan_code=plan.plan_code,
                    override_id=None,
                    diagnostics={"plan_id": str(plan.id)},
                )

            else:
                raise InvalidEntitlementConfigException(
                    f"Unsupported entitlement type '{raw_type}' for key '{entitlement_key}'."
                )

        # ----------------------------------------------------------------------
        # 3. PRECEDENCE TIER 3: Explicit Conservative System Default
        # ----------------------------------------------------------------------
        logger.debug(
            f"Entitlement '{entitlement_key}' not defined in plan '{plan.plan_code}' "
            f"or overrides; failing closed."
        )
        return EffectiveEntitlement(
            entitlement_key=entitlement_key,
            entitlement_type=EntitlementType.BOOLEAN,
            value="false",
            source=EntitlementSource.SYSTEM_DEFAULT,
            is_enabled=False,
            limit=0,
            is_unlimited=False,
            society_id=target_society_id,
            plan_code=plan.plan_code,
            override_id=None,
            diagnostics={"reason": "ENTITLEMENT_NOT_CONFIGURED"},
        )

    async def can_use_feature(
        self,
        society_id: UUID | None,
        feature_key: str,
        as_of: datetime | None = None,
    ) -> bool:
        """Evaluate whether a feature flag is effectively enabled for a society."""
        eff = await self.get_effective_entitlement(society_id, feature_key, as_of=as_of)
        return eff.is_enabled

    async def get_limit(
        self,
        society_id: UUID | None,
        quota_key: str,
        as_of: datetime | None = None,
    ) -> int | None:
        """Retrieve configured numeric limit for a quota key.

        Returns None if explicitly UNLIMITED.
        Returns 0 or positive integer for finite limits.
        """
        eff = await self.get_effective_entitlement(society_id, quota_key, as_of=as_of)
        if eff.is_unlimited:
            return None
        return eff.limit if eff.limit is not None else 0

    async def check_limit(
        self,
        society_id: UUID | None,
        quota_key: str,
        current_value: int,
        as_of: datetime | None = None,
    ) -> bool:
        """Check whether current_value satisfies the effective quota ceiling."""
        eff = await self.get_effective_entitlement(society_id, quota_key, as_of=as_of)
        if not eff.is_enabled:
            return False
        if eff.is_unlimited:
            return True
        if eff.limit is None:
            return False
        return current_value <= eff.limit

    async def get_effective_quota(
        self,
        society_id: UUID | None,
        quota_key: str,
        as_of: datetime | None = None,
    ) -> EffectiveQuota:
        """Resolve effective quota availability and limits for quota enforcement."""
        eff = await self.get_effective_entitlement(society_id, quota_key, as_of=as_of)
        return EffectiveQuota(
            quota_key=quota_key,
            is_allowed=eff.is_enabled,
            is_unlimited=eff.is_unlimited,
            max_limit=eff.limit,
            source=eff.source,
            society_id=eff.society_id,
            plan_code=eff.plan_code,
        )
