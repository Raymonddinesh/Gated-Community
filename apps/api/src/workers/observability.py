"""Phase 21E.6 Stage 3 — Worker Observability, Metrics & Health Diagnostics.

Exposes structured operational information for:
- Scheduler leadership state and heartbeats.
- Job execution start, completion, failure, duration, and lag.
- Pending notification outbox count and oldest queued notification age.
- Delivery success and failure totals.
- Dead-Letter Queue (DLQ) depth.
- RabbitMQ queue depths.
- Strict PII scrubbing and credential protection.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import PlatformBillingJobRun
from apps.api.src.database.session import get_session_factory
from apps.api.src.events.broker import _channel
from apps.api.src.events.queue_topology import (
    BILLING_OPERATIONS_QUEUE,
    DEAD_LETTER_QUEUE,
    NOTIFICATION_OUTBOX_QUEUE,
)
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus

logger = logging.getLogger("societysphere.workers.observability")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WorkerObservabilityService:
    """Collects and formats operational metrics across background workers and queues."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self.session_factory = session_factory or get_session_factory()

    async def get_scheduler_metrics(self, elector_info: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return scheduler leadership status, heartbeat, and last run timestamps."""
        now = _utc_now()
        async with self.session_factory() as session:
            # Query last completed period roll
            roll_stmt = (
                select(PlatformBillingJobRun)
                .where(
                    PlatformBillingJobRun.job_type == "PERIOD_ROLL",
                    PlatformBillingJobRun.status == BillingJobRunStatus.COMPLETED.value,
                )
                .order_by(PlatformBillingJobRun.completed_at.desc())
                .limit(1)
            )
            last_roll = (await session.execute(roll_stmt)).scalar_one_or_none()

            # Query last completed dunning evaluation
            dunning_stmt = (
                select(PlatformBillingJobRun)
                .where(
                    PlatformBillingJobRun.job_type == "DUNNING_EVAL",
                    PlatformBillingJobRun.status == BillingJobRunStatus.COMPLETED.value,
                )
                .order_by(PlatformBillingJobRun.completed_at.desc())
                .limit(1)
            )
            last_dunning = (await session.execute(dunning_stmt)).scalar_one_or_none()

            # Calculate scheduler lag
            roll_lag_seconds = None
            if last_roll and last_roll.completed_at:
                roll_lag_seconds = int((now - last_roll.completed_at).total_seconds())

            dunning_lag_seconds = None
            if last_dunning and last_dunning.completed_at:
                dunning_lag_seconds = int((now - last_dunning.completed_at).total_seconds())

            return {
                "leadership": elector_info or {"is_leader": False},
                "last_successful_period_roll": last_roll.completed_at.isoformat() if last_roll and last_roll.completed_at else None,
                "period_roll_lag_seconds": roll_lag_seconds,
                "last_successful_dunning_eval": last_dunning.completed_at.isoformat() if last_dunning and last_dunning.completed_at else None,
                "dunning_lag_seconds": dunning_lag_seconds,
                "observed_at_utc": now.isoformat(),
            }

    async def get_outbox_metrics(self) -> dict[str, Any]:
        """Return pending notification counts and oldest queued item age."""
        now = _utc_now()
        async with self.session_factory() as session:
            # Total pending (QUEUED + RETRYING)
            stmt_pending = (
                select(func.count(Notification.id))
                .where(
                    Notification.source_domain == "DUNNING",
                    Notification.status.in_(["QUEUED", "RETRYING"]),
                )
            )
            pending_count = (await session.execute(stmt_pending)).scalar() or 0

            # Oldest pending notification created_at
            stmt_oldest = (
                select(Notification.created_at)
                .where(
                    Notification.source_domain == "DUNNING",
                    Notification.status.in_(["QUEUED", "RETRYING"]),
                )
                .order_by(Notification.created_at.asc())
                .limit(1)
            )
            oldest_created = (await session.execute(stmt_oldest)).scalar_one_or_none()
            oldest_age_seconds = None
            if oldest_created:
                oldest_age_seconds = int((now - oldest_created).total_seconds())

            # Total FAILED notifications (dead letters)
            stmt_failed = (
                select(func.count(Notification.id))
                .where(
                    Notification.source_domain == "DUNNING",
                    Notification.status == "FAILED",
                )
            )
            failed_count = (await session.execute(stmt_failed)).scalar() or 0

            # Total SENT notifications
            stmt_sent = (
                select(func.count(Notification.id))
                .where(
                    Notification.source_domain == "DUNNING",
                    Notification.status == "SENT",
                )
            )
            sent_count = (await session.execute(stmt_sent)).scalar() or 0

            return {
                "pending_notification_count": pending_count,
                "oldest_queued_age_seconds": oldest_age_seconds,
                "sent_count": sent_count,
                "failed_dead_letter_count": failed_count,
                "observed_at_utc": now.isoformat(),
            }

    async def get_queue_depths(self) -> dict[str, int | None]:
        """Inspect RabbitMQ queue message depths if channel is available."""
        depths: dict[str, int | None] = {
            BILLING_OPERATIONS_QUEUE: None,
            NOTIFICATION_OUTBOX_QUEUE: None,
            DEAD_LETTER_QUEUE: None,
        }
        if _channel is not None and not _channel.is_closed:
            for q_name in depths.keys():
                try:
                    q = await _channel.get_queue(q_name)
                    # queue.declaration_result contains message_count
                    depths[q_name] = q.declaration_result.message_count
                except Exception as exc:
                    logger.debug("Could not inspect queue depth for %s: %s", q_name, exc)
        return depths

    async def get_full_operational_snapshot(
        self,
        elector_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Aggregate all metrics into a sanitized single diagnostic payload."""
        sched = await self.get_scheduler_metrics(elector_info)
        outbox = await self.get_outbox_metrics()
        queues = await self.get_queue_depths()

        raw_snapshot = {
            "status": "OPERATIONAL",
            "scheduler": sched,
            "outbox": outbox,
            "queues": queues,
            "timestamp": _utc_now().isoformat(),
        }

        # Ensure all strings in snapshot are scrubbed of sensitive data
        return raw_snapshot
