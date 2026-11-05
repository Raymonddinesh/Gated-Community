"""Phase 21E.6 Stage 3 — Autonomous Distributed Scheduler Runner.

Executes:
- Hourly Billing Period Roll at minute 0 (3600s).
- Dunning & Suspension Evaluation every 4 hours (14400s).
- Notification Outbox Drainage every 30 seconds.
- Stale Job Sweeper every 30 minutes (1800s).
- Publishes job triggers to RabbitMQ topic exchange 'societysphere.jobs'.
- Employs RedisLeaderElector with session-level PostgreSQL advisory lock fencing.
- Halts scheduling immediately if leadership is lost.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from apps.api.src.events.broker import EventPublisher
from apps.api.src.events.queue_topology import (
    JOBS_EXCHANGE,
    ROUTING_KEY_DUNNING_EVAL,
    ROUTING_KEY_OUTBOX_DRAIN,
    ROUTING_KEY_PERIOD_ROLL,
    ROUTING_KEY_STALE_SWEEP,
)
from apps.api.src.subscriptions.automation.leader_election import RedisLeaderElector

logger = logging.getLogger("societysphere.subscriptions.automation.scheduler_runner")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class DistributedSchedulerRunner:
    """Distributed background scheduler publishing periodic job triggers when elected leader."""

    def __init__(
        self,
        elector: RedisLeaderElector | None = None,
        period_roll_interval_seconds: float = 3600.0,  # 1 hour
        dunning_eval_interval_seconds: float = 14400.0,  # 4 hours
        outbox_drain_interval_seconds: float = 30.0,  # 30 seconds
        stale_sweep_interval_seconds: float = 1800.0,  # 30 minutes
        poll_loop_delay: float = 1.0,
    ) -> None:
        self.elector = elector or RedisLeaderElector(
            on_leadership_acquired=self._on_leadership_acquired,
            on_leadership_lost=self._on_leadership_lost,
        )
        self.period_roll_interval = period_roll_interval_seconds
        self.dunning_eval_interval = dunning_eval_interval_seconds
        self.outbox_drain_interval = outbox_drain_interval_seconds
        self.stale_sweep_interval = stale_sweep_interval_seconds
        self.poll_loop_delay = poll_loop_delay

        self._running: bool = False
        self._last_period_roll: datetime | None = None
        self._last_dunning_eval: datetime | None = None
        self._last_outbox_drain: datetime | None = None
        self._last_stale_sweep: datetime | None = None

        self.metrics: dict[str, Any] = {
            "period_roll_triggers": 0,
            "dunning_eval_triggers": 0,
            "outbox_drain_triggers": 0,
            "stale_sweep_triggers": 0,
            "leadership_transitions": 0,
            "last_tick_utc": None,
        }

    async def _on_leadership_acquired(self) -> None:
        logger.info("SchedulerRunner: ACQUIRED leadership. Initializing schedule timers.")
        self.metrics["leadership_transitions"] += 1
        # Trigger an immediate outbox drain and period roll check upon becoming leader to catch up
        self._last_outbox_drain = None

    async def _on_leadership_lost(self) -> None:
        logger.warning("SchedulerRunner: LOST leadership. Halting trigger dispatching.")
        self.metrics["leadership_transitions"] += 1

    async def start(self) -> None:
        """Run the scheduler loop continuously until cancelled."""
        self._running = True
        logger.info("DistributedSchedulerRunner starting (Instance: %s)...", self.elector.owner_token)

        while self._running:
            try:
                now = _utc_now()
                self.metrics["last_tick_utc"] = now.isoformat()

                # 1. Maintain / Attempt Leadership
                if not self.elector.is_leader:
                    await self.elector.acquire_leadership()
                    if not self.elector.is_leader:
                        # Follower mode: sleep and try again on next iteration
                        await asyncio.sleep(self.poll_loop_delay * 3)
                        continue

                # 2. Leader Active: Evaluate Schedules
                await self._evaluate_and_dispatch(now)

                await asyncio.sleep(self.poll_loop_delay)

            except asyncio.CancelledError:
                logger.info("DistributedSchedulerRunner cancelled.")
                break
            except Exception as exc:
                logger.error("Error in DistributedSchedulerRunner loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.poll_loop_delay * 2)

        # Cleanup
        await self.stop()

    async def _evaluate_and_dispatch(self, now: datetime) -> None:
        """Check all scheduled milestones and emit RabbitMQ trigger messages."""
        if not self.elector.is_leader:
            return

        # 1. Outbox Drainage (~30s)
        if (
            self._last_outbox_drain is None
            or (now - self._last_outbox_drain).total_seconds() >= self.outbox_drain_interval
        ):
            if await self._publish_trigger(
                routing_key=ROUTING_KEY_OUTBOX_DRAIN,
                job_type="OUTBOX_DRAIN",
                cutoff_utc=now,
            ):
                self._last_outbox_drain = now
                self.metrics["outbox_drain_triggers"] += 1
            else:
                logger.warning(
                    "Failed to publish OUTBOX_DRAIN trigger; retaining schedule timestamp to retry next poll tick"
                )

        # 2. Billing Period Roll (Hourly at minute 0)
        if (
            self._last_period_roll is None
            or (now - self._last_period_roll).total_seconds() >= self.period_roll_interval
        ):
            if await self._publish_trigger(
                routing_key=ROUTING_KEY_PERIOD_ROLL,
                job_type="PERIOD_ROLL",
                cutoff_utc=now,
            ):
                self._last_period_roll = now
                self.metrics["period_roll_triggers"] += 1
            else:
                logger.warning(
                    "Failed to publish PERIOD_ROLL trigger; retaining schedule timestamp to retry next poll tick"
                )

        # 3. Dunning Evaluation (Every 4 Hours)
        if (
            self._last_dunning_eval is None
            or (now - self._last_dunning_eval).total_seconds() >= self.dunning_eval_interval
        ):
            if await self._publish_trigger(
                routing_key=ROUTING_KEY_DUNNING_EVAL,
                job_type="DUNNING_EVAL",
                cutoff_utc=now,
            ):
                self._last_dunning_eval = now
                self.metrics["dunning_eval_triggers"] += 1
            else:
                logger.warning(
                    "Failed to publish DUNNING_EVAL trigger; retaining schedule timestamp to retry next poll tick"
                )

        # 4. Stale Job Sweeper (Every 30 Minutes)
        if (
            self._last_stale_sweep is None
            or (now - self._last_stale_sweep).total_seconds() >= self.stale_sweep_interval
        ):
            if await self._publish_trigger(
                routing_key=ROUTING_KEY_STALE_SWEEP,
                job_type="STALE_SWEEP",
                cutoff_utc=now,
            ):
                self._last_stale_sweep = now
                self.metrics["stale_sweep_triggers"] += 1
            else:
                logger.warning(
                    "Failed to publish STALE_SWEEP trigger; retaining schedule timestamp to retry next poll tick"
                )

    async def _publish_trigger(
        self,
        routing_key: str,
        job_type: str,
        cutoff_utc: datetime,
    ) -> bool:
        """Publish a durable execution trigger message to RabbitMQ."""
        exec_id = f"sched-{job_type.lower()}-{uuid4().hex[:10]}"
        payload = {
            "job_type": job_type,
            "execution_id": exec_id,
            "cutoff_utc": cutoff_utc.isoformat(),
            "triggered_at": _utc_now().isoformat(),
            "leader_id": self.elector.owner_token,
        }

        logger.debug(
            "Emitting trigger for '%s' (Execution ID: %s, Routing Key: %s)",
            job_type,
            exec_id,
            routing_key,
        )

        try:
            success = await EventPublisher.publish_event(
                exchange_name=JOBS_EXCHANGE,
                routing_key=routing_key,
                payload=payload,
                headers={"job_type": job_type, "execution_id": exec_id},
            )
            return bool(success)
        except Exception as exc:
            logger.error("Exception publishing trigger for '%s': %s", job_type, exc)
            return False

    async def stop(self) -> None:
        """Gracefully step down and stop runner."""
        self._running = False
        await self.elector.step_down()
        logger.info("DistributedSchedulerRunner stopped.")
