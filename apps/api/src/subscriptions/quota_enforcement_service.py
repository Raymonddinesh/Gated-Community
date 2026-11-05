"""Phase 21B — Quota Enforcement Domain Service.

Race-safe, transaction-bound quota evaluation and atomic reservation service.
Guarantees:
- Strict tenant isolation using trusted tenant context (get_current_tenant_id).
- Atomic, concurrency-safe usage reservations using PostgreSQL SELECT ... FOR UPDATE.
- Safe concurrent initialization of missing usage metric rows via savepoints.
- Explicit non-negative invariants and fail-closed security for unconfigured quotas.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import AuthorizationException, TenantContextRequiredException
from apps.api.src.core.tenant_context import get_current_tenant_id
from apps.api.src.database.models.subscription import SocietyUsageMetric
from apps.api.src.subscriptions.entitlement_service import EntitlementService
from apps.api.src.subscriptions.exceptions import (
    InvalidUsageIncrementException,
    QuotaExceededException,
    StaleReconciliationException,
)
from apps.api.src.subscriptions.schemas import (
    EffectiveQuota,
    UsageDiagnostic,
    UsageReservationResult,
)

logger = logging.getLogger("societysphere.subscriptions.quota")


class QuotaEnforcementService:
    """Domain service managing race-safe quota checks, limits, and atomic usage reservations.

    Transaction & ORM Safety:
    - Reads (`get_current_usage`, `check_quota`, `get_usage_diagnostics`):
      Non-locking queries; safe to run in any transaction state.
    - Mutations (`reserve_usage`, `reconcile_usage`):
      Acquires explicit row-level lock (`SELECT ... FOR UPDATE`);
      flushes changes to the session; leaves commit ownership to caller's transaction
      (unless `auto_commit=True` is explicitly specified).
    """

    def __init__(
        self,
        session: AsyncSession,
        entitlement_service: EntitlementService | None = None,
    ) -> None:
        self.session = session
        self.entitlement_service = entitlement_service or EntitlementService(session)

    def _resolve_trusted_society(self, society_id: UUID | None) -> UUID:
        """Enforce strict tenant boundary check using trusted tenant context."""
        current_tenant = get_current_tenant_id()
        if current_tenant is None:
            raise TenantContextRequiredException(
                "Active tenant context is required for quota enforcement operations."
            )
        if society_id is not None and society_id != current_tenant:
            raise AuthorizationException(
                f"Cross-tenant access forbidden: Cannot operate on society '{society_id}' "
                f"within active tenant context '{current_tenant}'."
            )
        return current_tenant

    async def _get_or_init_metric_row(
        self,
        society_id: UUID,
        metric_key: str,
        for_update: bool = True,
    ) -> SocietyUsageMetric:
        """Retrieve existing usage metric row or atomically initialize it.

        Concurrency Safety:
        Uses a nested savepoint (`begin_nested()`) when inserting a missing metric row.
        If another concurrent transaction inserts the same (society_id, metric_key)
        simultaneously, the unique constraint violation triggers a savepoint rollback,
        and this transaction cleanly re-queries the row with `FOR UPDATE`.
        """
        stmt = select(SocietyUsageMetric).where(
            SocietyUsageMetric.society_id == society_id,
            SocietyUsageMetric.metric_key == metric_key,
        )
        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        metric = result.scalar_one_or_none()

        if metric is None:
            try:
                async with self.session.begin_nested():
                    metric = SocietyUsageMetric(
                        society_id=society_id,
                        metric_key=metric_key,
                        current_value=0,
                        last_calculated_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    self.session.add(metric)
                    await self.session.flush()
            except IntegrityError:
                # Concurrent transaction inserted the row first; re-query with lock
                result = await self.session.execute(stmt)
                metric = result.scalar_one()

        return metric

    async def get_current_usage(self, society_id: UUID | None, metric_key: str) -> int:
        """Retrieve the current recorded usage count for a metric key without locking."""
        target_society_id = self._resolve_trusted_society(society_id)
        stmt = select(SocietyUsageMetric.current_value).where(
            SocietyUsageMetric.society_id == target_society_id,
            SocietyUsageMetric.metric_key == metric_key,
        )
        result = await self.session.execute(stmt)
        val = result.scalar_one_or_none()
        return val if val is not None else 0

    async def get_effective_quota(
        self,
        society_id: UUID | None,
        quota_key: str,
        as_of: datetime | None = None,
    ) -> EffectiveQuota:
        """Resolve effective quota ceiling and status via EntitlementService."""
        target_society_id = self._resolve_trusted_society(society_id)
        return await self.entitlement_service.get_effective_quota(
            target_society_id, quota_key, as_of=as_of
        )

    async def check_quota(
        self,
        society_id: UUID | None,
        quota_key: str,
        requested_increment: int = 1,
        as_of: datetime | None = None,
    ) -> bool:
        """Non-locking read check to evaluate if a requested increment is within quota."""
        target_society_id = self._resolve_trusted_society(society_id)
        if requested_increment < 0:
            raise InvalidUsageIncrementException("Requested increment must not be negative.")

        effective = await self.get_effective_quota(target_society_id, quota_key, as_of=as_of)
        if not effective.is_allowed:
            return False
        if effective.is_unlimited:
            return True
        if effective.max_limit is None:
            return False

        current = await self.get_current_usage(target_society_id, quota_key)
        return (current + requested_increment) <= effective.max_limit

    async def reserve_usage(
        self,
        society_id: UUID | None,
        quota_key: str,
        requested_increment: int = 1,
        as_of: datetime | None = None,
        auto_commit: bool = False,
    ) -> UsageReservationResult:
        """Atomically validate quota availability and increment the usage counter.

        Concurrency & Rollback Guarantees:
        1. Validates requested increment is non-negative.
        2. Resolves effective quota ceiling from EntitlementService.
        3. Locks the tenant's usage metric row with SELECT ... FOR UPDATE.
        4. Verifies (current_value + requested_increment) <= max_limit.
        5. If quota is exceeded, raises QuotaExceededException without modifying the counter.
        6. If allowed, increments current_value and flushes to the database session.
        7. If caller rolls back the transaction, the usage increment is completely reverted.
        """
        target_society_id = self._resolve_trusted_society(society_id)
        if requested_increment < 0:
            raise InvalidUsageIncrementException("Requested increment must not be negative.")

        effective = await self.get_effective_quota(target_society_id, quota_key, as_of=as_of)

        if not effective.is_allowed:
            raise QuotaExceededException(
                quota_key=quota_key,
                current_usage=0,
                requested_increment=requested_increment,
                max_limit=0,
                society_id=target_society_id,
                message=f"Subscription or plan does not permit quota allocation for '{quota_key}'.",
            )

        # Acquire exclusive row-level lock on the usage metric record
        metric = await self._get_or_init_metric_row(
            target_society_id, quota_key, for_update=True
        )
        previous_usage = metric.current_value

        # Handle zero increment (no-op check)
        if requested_increment == 0:
            if not effective.is_unlimited and effective.max_limit is not None:
                if previous_usage > effective.max_limit:
                    raise QuotaExceededException(
                        quota_key=quota_key,
                        current_usage=previous_usage,
                        requested_increment=0,
                        max_limit=effective.max_limit,
                        society_id=target_society_id,
                    )
            return UsageReservationResult(
                quota_key=quota_key,
                previous_usage=previous_usage,
                requested_increment=0,
                new_usage=previous_usage,
                max_limit=effective.max_limit,
                is_unlimited=effective.is_unlimited,
                society_id=target_society_id,
            )

        # Handle finite limit verification
        if not effective.is_unlimited:
            max_limit = effective.max_limit if effective.max_limit is not None else 0
            new_usage = previous_usage + requested_increment
            if new_usage > max_limit:
                logger.warning(
                    f"Quota exceeded for '{quota_key}' in society {target_society_id}: "
                    f"current={previous_usage}, requested=+{requested_increment}, limit={max_limit}"
                )
                raise QuotaExceededException(
                    quota_key=quota_key,
                    current_usage=previous_usage,
                    requested_increment=requested_increment,
                    max_limit=max_limit,
                    society_id=target_society_id,
                )
        else:
            new_usage = previous_usage + requested_increment
            max_limit = None

        # Apply mutation atomically
        metric.current_value = new_usage
        metric.last_calculated_at = datetime.now(UTC).replace(tzinfo=None)
        await self.session.flush()

        if auto_commit:
            await self.session.commit()

        logger.info(
            f"Quota reserved for '{quota_key}' in society {target_society_id}: "
            f"{previous_usage} -> {new_usage} (limit={max_limit})"
        )

        return UsageReservationResult(
            quota_key=quota_key,
            previous_usage=previous_usage,
            requested_increment=requested_increment,
            new_usage=new_usage,
            max_limit=max_limit,
            is_unlimited=effective.is_unlimited,
            society_id=target_society_id,
        )

    async def reconcile_usage(
        self,
        society_id: UUID | None,
        metric_key: str,
        actual_count: int | None = None,
        *,
        count_callback: Callable[[AsyncSession, UUID], Awaitable[int]] | None = None,
        expected_previous_value: int | None = None,
        as_of: datetime | None = None,
        auto_commit: bool = False,
    ) -> int:
        """Synchronously reconcile usage metric counter against verified resource count.

        Concurrency & Freshness Guarantees:
        1. Strict Tenant Isolation: Enforces active tenant context via _resolve_trusted_society.
        2. Row-Level Serialization: Acquires exclusive row-level lock (SELECT ... FOR UPDATE)
           on the target SocietyUsageMetric record.
        3. Authoritative In-Transaction Counting (Preferred):
           If `count_callback` is provided, it is executed inside the active transaction while
           holding the row lock. Because the row lock is held throughout, concurrent `reserve_usage`
           calls are blocked and cannot race or be lost.
        4. Coordinated External Count Reconciliation:
           If an external `actual_count` is provided:
           - Validates non-negative invariant (`actual_count >= 0`).
           - If `expected_previous_value` is specified: verifies that `metric.current_value`
             matches `expected_previous_value`. If another transaction modified the counter,
             raises `StaleReconciliationException`.
           - If `as_of` timestamp is specified: verifies that `metric.last_calculated_at <= as_of`.
             If another transaction updated the metric after `as_of`, raises `StaleReconciliationException`.
           - If neither coordination parameter is passed: guards against stale regressions where
             `actual_count < metric.current_value`, raising `StaleReconciliationException`
             to prevent stale external counts from decreasing a newer committed counter.
        5. Atomicity & Rollback:
           Flushes changes to the session; caller rollback fully reverts the update.
        """
        target_society_id = self._resolve_trusted_society(society_id)

        if actual_count is None and count_callback is None:
            raise InvalidUsageIncrementException(
                "Either actual_count or count_callback must be provided for reconciliation."
            )
        if actual_count is not None and count_callback is not None:
            raise InvalidUsageIncrementException(
                "Cannot provide both actual_count and count_callback for reconciliation."
            )

        # 1. Acquire exclusive row lock on usage metric record (or safely initialize if missing)
        metric = await self._get_or_init_metric_row(
            target_society_id, metric_key, for_update=True
        )
        previous_usage = metric.current_value

        # 2. Determine target reconciled count
        if count_callback is not None:
            reconciled_count = await count_callback(self.session, target_society_id)
            if reconciled_count < 0:
                raise InvalidUsageIncrementException("Reconciled usage count cannot be negative.")
        else:
            assert actual_count is not None
            if actual_count < 0:
                raise InvalidUsageIncrementException("Reconciled usage count cannot be negative.")

            # Freshness / coordination validation
            if expected_previous_value is not None and previous_usage != expected_previous_value:
                logger.warning(
                    f"Stale reconciliation rejected for '{metric_key}' in society {target_society_id}: "
                    f"current usage {previous_usage} does not match expected {expected_previous_value}."
                )
                raise StaleReconciliationException(
                    metric_key=metric_key,
                    current_usage=previous_usage,
                    attempted_count=actual_count,
                    society_id=target_society_id,
                    message=(
                        f"Stale reconciliation rejected for '{metric_key}': current usage {previous_usage} "
                        f"does not match expected previous usage {expected_previous_value}."
                    ),
                )

            if as_of is not None:
                norm_as_of = as_of.replace(tzinfo=None) if as_of.tzinfo is not None else as_of
                norm_last_calc = (
                    metric.last_calculated_at.replace(tzinfo=None)
                    if metric.last_calculated_at.tzinfo is not None
                    else metric.last_calculated_at
                )
                if norm_last_calc > norm_as_of:
                    logger.warning(
                        f"Stale reconciliation rejected for '{metric_key}' in society {target_society_id}: "
                        f"metric last calculated at {metric.last_calculated_at} is newer than as_of {as_of}."
                    )
                    raise StaleReconciliationException(
                        metric_key=metric_key,
                        current_usage=previous_usage,
                        attempted_count=actual_count,
                        society_id=target_society_id,
                        message=(
                            f"Stale reconciliation rejected for '{metric_key}': metric was updated at "
                            f"{metric.last_calculated_at}, which is newer than reconciliation snapshot {as_of}."
                        ),
                    )

            # Uncoordinated count cannot decrease a newer committed counter
            if expected_previous_value is None and as_of is None and actual_count < previous_usage:
                logger.warning(
                    f"Stale reconciliation rejected for '{metric_key}' in society {target_society_id}: "
                    f"attempted count {actual_count} cannot decrease current usage {previous_usage} "
                    f"without explicit coordination (count_callback, expected_previous_value, or as_of)."
                )
                raise StaleReconciliationException(
                    metric_key=metric_key,
                    current_usage=previous_usage,
                    attempted_count=actual_count,
                    society_id=target_society_id,
                    message=(
                        f"Stale reconciliation rejected for '{metric_key}': attempted count {actual_count} "
                        f"cannot decrease current usage {previous_usage} without explicit coordination."
                    ),
                )

            reconciled_count = actual_count

        # 3. Apply reconciled count atomically under row lock
        metric.current_value = reconciled_count
        metric.last_calculated_at = datetime.now(UTC).replace(tzinfo=None)
        await self.session.flush()

        if auto_commit:
            await self.session.commit()

        logger.info(
            f"Usage reconciled for '{metric_key}' in society {target_society_id}: "
            f"{previous_usage} -> {reconciled_count}."
        )
        return metric.current_value


    async def get_usage_diagnostics(
        self,
        society_id: UUID | None,
        metric_key: str,
        as_of: datetime | None = None,
    ) -> UsageDiagnostic:
        """Provide detailed diagnostics and utilization percentage for a metric key."""
        target_society_id = self._resolve_trusted_society(society_id)
        stmt = select(SocietyUsageMetric).where(
            SocietyUsageMetric.society_id == target_society_id,
            SocietyUsageMetric.metric_key == metric_key,
        )
        result = await self.session.execute(stmt)
        metric = result.scalar_one_or_none()

        current_val = metric.current_value if metric else 0
        last_calc = (
            metric.last_calculated_at
            if metric
            else datetime.now(UTC).replace(tzinfo=None)
        )

        effective = await self.get_effective_quota(target_society_id, metric_key, as_of=as_of)

        utilization: float | None = None
        if not effective.is_unlimited and effective.max_limit and effective.max_limit > 0:
            utilization = round((current_val / effective.max_limit) * 100.0, 2)

        return UsageDiagnostic(
            metric_key=metric_key,
            current_value=current_val,
            last_calculated_at=last_calc,
            quota_limit=effective.max_limit,
            is_unlimited=effective.is_unlimited,
            utilization_percentage=utilization,
            society_id=target_society_id,
        )
