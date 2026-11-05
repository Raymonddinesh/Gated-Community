"""Phase 21E.6 Stage 3 — Background Worker Consumers & Message Dispatchers.

Implements:
- BillingOperationsConsumer: Processes billing period roll & dunning evaluation jobs.
- NotificationOutboxConsumer: Drains pending outbox notifications with bounded retry & stale recovery.
- StaleJobRecoveryService: Identifies and marks stale/crashed PlatformBillingJobRun records as FAILED.
- Reliable Message Acknowledgement:
  * message.ack() only after database commit.
  * message.nack(requeue=True) on transient database exceptions.
  * message.reject(requeue=False) to DLQ on deserialization / poison message failures.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractQueue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import PlatformBillingJobRun
from apps.api.src.database.session import get_session_factory
from apps.api.src.events.queue_topology import (
    BILLING_OPERATIONS_QUEUE,
    NOTIFICATION_OUTBOX_QUEUE,
    ROUTING_KEY_DUNNING_EVAL,
    ROUTING_KEY_PERIOD_ROLL,
)
from apps.api.src.subscriptions.automation.dunning_service import DunningEngineService
from apps.api.src.subscriptions.automation.scheduler_service import BillingPeriodSchedulerService
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus

logger = logging.getLogger("societysphere.subscriptions.automation.consumers")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class StaleJobRecoveryService:
    """Detects abandoned/crashed job runs and recovers stale notifications."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self.session_factory = session_factory or get_session_factory()

    async def recover_stale_job_runs(self, max_runtime_minutes: int = 120) -> int:
        """Scan PlatformBillingJobRun for records stuck in RUNNING beyond threshold."""
        stale_threshold = _utc_now() - timedelta(minutes=max_runtime_minutes)
        async with self.session_factory() as session:
            stmt = (
                select(PlatformBillingJobRun)
                .where(
                    PlatformBillingJobRun.status == BillingJobRunStatus.RUNNING.value,
                    PlatformBillingJobRun.started_at < stale_threshold,
                )
                .with_for_update(skip_locked=True)
            )
            res = await session.execute(stmt)
            stale_jobs = res.scalars().all()

            recovered_count = 0
            now = _utc_now()
            for job in stale_jobs:
                job.status = BillingJobRunStatus.FAILED.value
                job.completed_at = now
                job.error_summary = (
                    f"TIMED_OUT: Job exceeded max runtime ({max_runtime_minutes}m). "
                    f"Automatically marked FAILED by StaleJobRecoveryService."
                )
                recovered_count += 1
                logger.warning("Stale job %s (type=%s) marked FAILED.", job.execution_id, job.job_type)

            if recovered_count > 0:
                await session.commit()
            return recovered_count

    async def recover_stale_processing_notifications(
        self,
        max_processing_minutes: int = 15,
        max_retries: int = 3,
    ) -> int:
        """Reset outbox notifications stuck in PROCESSING status back to RETRYING, bounded by max_retries."""
        stale_threshold = _utc_now() - timedelta(minutes=max_processing_minutes)
        async with self.session_factory() as session:
            stmt = (
                select(Notification)
                .where(
                    Notification.source_domain == "DUNNING",
                    Notification.status == "PROCESSING",
                    Notification.updated_at < stale_threshold,
                )
                .with_for_update(skip_locked=True)
            )
            res = await session.execute(stmt)
            stale_notifs = res.scalars().all()

            recovered_count = 0
            now = _utc_now()
            for notif in stale_notifs:
                payload = json.loads(notif.payload or "{}")
                retry_count = int(payload.get("retry_count", 0)) + 1
                limit = int(payload.get("max_retries", max_retries))
                payload["retry_count"] = retry_count
                payload["recovered_from_stale_processing_at"] = now.isoformat()

                if retry_count >= limit:
                    notif.status = "FAILED"
                    payload["error"] = f"Max retries ({limit}) exceeded"
                    notif.payload = json.dumps(payload)
                    logger.warning(
                        "Stale outbox notification %s reached max retries (%d/%d). Marked FAILED.",
                        notif.id,
                        retry_count,
                        limit,
                    )
                else:
                    notif.status = "RETRYING"
                    notif.payload = json.dumps(payload)
                    logger.warning(
                        "Stale outbox notification %s reset from PROCESSING to RETRYING (attempt %d/%d).",
                        notif.id,
                        retry_count,
                        limit,
                    )
                recovered_count += 1

            if recovered_count > 0:
                await session.commit()
            return recovered_count


class BillingOperationsConsumer:
    """RabbitMQ consumer executing scheduled billing renewals and dunning evaluations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        queue_name: str = BILLING_OPERATIONS_QUEUE,
    ) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.queue_name = queue_name
        self._running: bool = False
        self._consumer_tag: str | None = None
        self._stop_event: asyncio.Event | None = None
        self.processed_count: int = 0
        self.failure_count: int = 0

    @property
    def is_running(self) -> bool:
        """Indicate whether the consumer is actively running and awaiting messages."""
        return self._running

    async def start(self, channel: aio_pika.abc.AbstractChannel) -> None:
        """Start consuming messages from the billing operations queue and keep task alive."""
        self._running = True
        self._stop_event = asyncio.Event()
        queue: AbstractQueue = await channel.get_queue(self.queue_name)
        # Prefetch count 1: Process one batch at a time to prevent database exhaustion
        await channel.set_qos(prefetch_count=1)

        logger.info("BillingOperationsConsumer started on queue '%s'...", self.queue_name)
        self._consumer_tag = await queue.consume(self._handle_message)
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("BillingOperationsConsumer task cancelled.")
            raise
        finally:
            self._running = False
            if channel and not channel.is_closed and self._consumer_tag:
                try:
                    await queue.cancel(self._consumer_tag)
                except Exception:
                    pass
                self._consumer_tag = None

    async def _handle_message(self, message: AbstractIncomingMessage) -> None:
        """Process incoming billing operation message with execution idempotency."""
        routing_key = message.routing_key
        try:
            body = json.loads(message.body.decode("utf-8"))
        except Exception as exc:
            logger.error("Poison message received on %s (JSON decode error): %s. Rejecting to DLQ.", routing_key, exc)
            self.failure_count += 1
            await message.reject(requeue=False)
            return

        job_type = body.get("job_type")
        exec_id = body.get("execution_id")
        cutoff_raw = body.get("cutoff_utc")

        try:
            cutoff_utc = datetime.fromisoformat(cutoff_raw) if cutoff_raw else _utc_now()
            if cutoff_utc.tzinfo is not None:
                cutoff_utc = cutoff_utc.replace(tzinfo=None)
        except Exception:
            cutoff_utc = _utc_now()

        logger.info(
            "BillingOperationsConsumer processing '%s' (routing_key=%s, exec_id=%s)",
            job_type,
            routing_key,
            exec_id,
        )

        # 1. Authoritative check for execution_id idempotency / redelivery
        if exec_id:
            async with self.session_factory() as session:
                existing_job = (
                    await session.execute(
                        select(PlatformBillingJobRun).where(
                            PlatformBillingJobRun.execution_id == exec_id
                        )
                    )
                ).scalar_one_or_none()
                if existing_job:
                    if existing_job.status == BillingJobRunStatus.COMPLETED.value:
                        logger.info(
                            "Billing job '%s' (exec_id=%s) already COMPLETED. Acknowledging redelivered message without duplicate execution.",
                            job_type,
                            exec_id,
                        )
                        self.processed_count += 1
                        await message.ack()
                        return
                    elif existing_job.status == BillingJobRunStatus.RUNNING.value:
                        # Follow lease / ownership and recovery policy: do not execute concurrently
                        now = _utc_now()
                        stale_threshold = now - timedelta(minutes=120)
                        if existing_job.started_at and existing_job.started_at > stale_threshold:
                            logger.warning(
                                "Billing job '%s' (exec_id=%s) is currently active and RUNNING. Nacking to delay concurrent execution.",
                                job_type,
                                exec_id,
                            )
                            await message.nack(requeue=True)
                            return
                        else:
                            # Stale RUNNING job (> 120m): Transition to FAILED before retry
                            logger.warning(
                                "Billing job '%s' (exec_id=%s) is stale (>120m). Marking FAILED before retry.",
                                job_type,
                                exec_id,
                            )
                            existing_job.status = BillingJobRunStatus.FAILED.value
                            existing_job.completed_at = now
                            existing_job.error_summary = "TIMED_OUT: Aborted stale job before retry."
                            await session.commit()
                    elif existing_job.status == BillingJobRunStatus.FAILED.value:
                        logger.warning(
                            "Billing job '%s' (exec_id=%s) previously FAILED (%s). Rejecting to DLQ to prevent poison loop.",
                            job_type,
                            exec_id,
                            existing_job.error_summary,
                        )
                        self.failure_count += 1
                        await message.reject(requeue=False)
                        return

        try:
            if routing_key == ROUTING_KEY_PERIOD_ROLL or job_type == "PERIOD_ROLL":
                async with self.session_factory() as session:
                    service = BillingPeriodSchedulerService(session=session)
                    await service.process_due_subscriptions(
                        cutoff_utc=cutoff_utc,
                        execution_id=exec_id,
                    )
            elif routing_key == ROUTING_KEY_DUNNING_EVAL or job_type == "DUNNING_EVAL":
                async with self.session_factory() as session:
                    dunning = DunningEngineService(session=session)
                    await dunning.process_dunning_batch(
                        cutoff_utc=cutoff_utc,
                        execution_id=exec_id,
                    )
            else:
                logger.warning("Unrecognized routing key '%s' on %s. Rejecting.", routing_key, self.queue_name)
                await message.reject(requeue=False)
                return

            # Acknowledge after successful execution & commit
            self.processed_count += 1
            await message.ack()

        except Exception as exc:
            self.failure_count += 1
            logger.error(
                "Transient error processing billing job '%s' (exec_id=%s): %s. Nacking with requeue.",
                job_type,
                exec_id,
                exc,
                exc_info=True,
            )
            # Requeue on transient DB error
            await message.nack(requeue=True)

    async def stop(self, channel: aio_pika.abc.AbstractChannel | None = None) -> None:
        """Stop consumer."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if channel and not channel.is_closed and self._consumer_tag:
            try:
                queue = await channel.get_queue(self.queue_name)
                await queue.cancel(self._consumer_tag)
            except Exception:
                pass
            self._consumer_tag = None
        logger.info("BillingOperationsConsumer stopped.")


class NotificationOutboxConsumer:
    """RabbitMQ consumer & worker draining transactional outbox notifications."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        queue_name: str = NOTIFICATION_OUTBOX_QUEUE,
        batch_size: int = 50,
    ) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.queue_name = queue_name
        self.batch_size = batch_size
        self._running: bool = False
        self._consumer_tag: str | None = None
        self._stop_event: asyncio.Event | None = None
        self.drained_count: int = 0
        self.failure_count: int = 0
        self.sweeper = StaleJobRecoveryService(self.session_factory)

    @property
    def is_running(self) -> bool:
        """Indicate whether the consumer is actively running and awaiting messages."""
        return self._running

    async def start(self, channel: aio_pika.abc.AbstractChannel) -> None:
        """Start consuming messages from notification outbox queue and keep task alive."""
        self._running = True
        self._stop_event = asyncio.Event()
        queue: AbstractQueue = await channel.get_queue(self.queue_name)
        # Prefetch count 10 for concurrent outbox draining
        await channel.set_qos(prefetch_count=10)

        logger.info("NotificationOutboxConsumer started on queue '%s'...", self.queue_name)
        self._consumer_tag = await queue.consume(self._handle_message)
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("NotificationOutboxConsumer task cancelled.")
            raise
        finally:
            self._running = False
            if channel and not channel.is_closed and self._consumer_tag:
                try:
                    await queue.cancel(self._consumer_tag)
                except Exception:
                    pass
                self._consumer_tag = None

    async def _handle_message(self, message: AbstractIncomingMessage) -> None:
        """Process outbox drain trigger message."""
        try:
            # 1. First recover any stale PROCESSING notifications
            await self.sweeper.recover_stale_processing_notifications(max_processing_minutes=15)

            # 2. Drain pending QUEUED and RETRYING notifications
            async with self.session_factory() as session:
                dunning = DunningEngineService(session=session)
                count = await dunning.drain_pending_outbox(batch_size=self.batch_size)
                await session.commit()
                self.drained_count += count
                logger.debug("NotificationOutboxConsumer drained %d notifications.", count)

            await message.ack()

        except Exception as exc:
            self.failure_count += 1
            logger.error("Error in NotificationOutboxConsumer drain: %s", exc, exc_info=True)
            await message.nack(requeue=True)

    async def drain_now(self) -> int:
        """Direct execution fallback for outbox drainage when message broker is not active."""
        await self.sweeper.recover_stale_processing_notifications(max_processing_minutes=15)
        async with self.session_factory() as session:
            dunning = DunningEngineService(session=session)
            count = await dunning.drain_pending_outbox(batch_size=self.batch_size)
            await session.commit()
            self.drained_count += count
            return count

    async def stop(self, channel: aio_pika.abc.AbstractChannel | None = None) -> None:
        """Stop consumer."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if channel and not channel.is_closed and self._consumer_tag:
            try:
                queue = await channel.get_queue(self.queue_name)
                await queue.cancel(self._consumer_tag)
            except Exception:
                pass
            self._consumer_tag = None
        logger.info("NotificationOutboxConsumer stopped.")
