"""Phase 21E.6 Stage 3 — Unified Worker Process Runner.

Entrypoint:
python -m apps.api.src.workers.runner

Executes 4 independently supervised tasks under an asyncio TaskGroup:
1. Distributed Scheduler Leader (hourly period roll, 4-hourly dunning, 30s outbox, 30m stale sweeper).
2. Billing Operations Consumer (executes period roll & dunning evaluation batches).
3. Notification Outbox Dispatcher (drains pending outbox with bounded retries).
4. Stale Job Recovery Sweeper (sweeps abandoned RUNNING jobs and stuck PROCESSING notifications).

Features:
- Supervisor isolation: Recoverable exceptions in one task do NOT terminate unrelated tasks.
- Explicit cancellation & graceful shutdown via SIGINT/SIGTERM handlers.
- Safe resource disposal (RabbitMQ broker, Redis pool, PostgreSQL engine).
"""

import asyncio
import logging
import signal
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from aio_pika.abc import AbstractChannel

from apps.api.src.cache.redis_client import close_redis, init_redis
from apps.api.src.core.config import get_settings
from apps.api.src.core.logging import setup_logging
from apps.api.src.database.session import close_db, init_db
from apps.api.src.events.broker import close_broker, init_broker
from apps.api.src.events.queue_topology import setup_queue_topology
from apps.api.src.subscriptions.automation.scheduler_runner import DistributedSchedulerRunner
from apps.api.src.subscriptions.automation.worker_consumers import (
    BillingOperationsConsumer,
    NotificationOutboxConsumer,
    StaleJobRecoveryService,
)
from apps.api.src.workers.observability import WorkerObservabilityService

settings = get_settings()
setup_logging(log_level=settings.LOG_LEVEL, app_env=settings.APP_ENV)
logger = logging.getLogger("societysphere.workers.runner")


class UnifiedWorkerRunner:
    """Unified background worker supervisor coordinating schedulers, queues, and dispatchers."""

    def __init__(self) -> None:
        self.shutdown_event = asyncio.Event()
        self.scheduler_runner = DistributedSchedulerRunner()
        self.billing_consumer = BillingOperationsConsumer()
        self.outbox_consumer = NotificationOutboxConsumer()
        self.stale_sweeper = StaleJobRecoveryService()
        self.observability = WorkerObservabilityService()
        self._channel: AbstractChannel | None = None

    async def _supervise(
        self,
        task_name: str,
        coro_fn: Callable[[], Coroutine[Any, Any, None]],
        restart_delay_seconds: float = 5.0,
    ) -> None:
        """Supervise a worker coroutine, restarting upon recoverable exception until shutdown."""
        logger.info("Supervisor: started task '%s'.", task_name)
        while not self.shutdown_event.is_set():
            try:
                await coro_fn()
                if self.shutdown_event.is_set():
                    break
                logger.warning(
                    "Supervisor: task '%s' returned without shutdown event. Backing off %.1fs...",
                    task_name,
                    restart_delay_seconds,
                )
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=restart_delay_seconds)
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                logger.info("Supervisor: task '%s' cancelled.", task_name)
                break
            except Exception as exc:
                if self.shutdown_event.is_set():
                    break
                logger.error(
                    "Supervisor: task '%s' crashed with error: %s. Restarting in %.1fs...",
                    task_name,
                    exc,
                    restart_delay_seconds,
                    exc_info=True,
                )
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=restart_delay_seconds)
                except TimeoutError:
                    pass
        logger.info("Supervisor: task '%s' terminated.", task_name)

    async def _run_stale_sweeper_loop(self) -> None:
        """Periodic background task sweeping stale jobs and stuck notifications."""
        while not self.shutdown_event.is_set():
            try:
                # 1. Sweep stale running jobs (exceeded 120m)
                stale_jobs = await self.stale_sweeper.recover_stale_job_runs(max_runtime_minutes=120)
                if stale_jobs > 0:
                    logger.warning("Sweeper: recovered %d stale job runs.", stale_jobs)

                # 2. Sweep stuck PROCESSING outbox notifications (exceeded 15m)
                stale_notifs = await self.stale_sweeper.recover_stale_processing_notifications(
                    max_processing_minutes=15
                )
                if stale_notifs > 0:
                    logger.warning("Sweeper: recovered %d stuck outbox notifications.", stale_notifs)

                # Sleep 30 minutes or until shutdown
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=1800.0)
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in stale sweeper loop: %s", exc)
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=60.0)
                except TimeoutError:
                    pass

    async def _run_outbox_fallback_loop(self) -> None:
        """Fallback polling loop for notification outbox drainage when broker is not attached."""
        while not self.shutdown_event.is_set():
            try:
                await self.outbox_consumer.drain_now()
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=30.0)
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in outbox fallback drainer: %s", exc)
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=10.0)
                except TimeoutError:
                    pass

    async def run(self) -> None:
        """Main lifecycle entrypoint initializing pools, consumers, and task group."""
        logger.info("Starting UnifiedWorkerRunner [env=%s]...", settings.APP_ENV)

        # 1. Initialize Backing Infrastructure
        await init_db()
        await init_redis()
        broker_conn = await init_broker()

        # 2. Setup RabbitMQ Topology & Consumers
        has_broker = False
        if broker_conn and not broker_conn.is_closed:
            try:
                self._channel = await broker_conn.channel()
                await setup_queue_topology(self._channel)
                has_broker = True
                logger.info("RabbitMQ broker connected and queue topology initialized.")
            except Exception as exc:
                logger.warning("Failed to setup RabbitMQ topology (falling back to direct): %s", exc)
                has_broker = False

        # 3. Supervised Task Execution using TaskGroup
        try:
            async with asyncio.TaskGroup() as tg:
                # Task 1: Distributed Scheduler Leader
                tg.create_task(
                    self._supervise("SchedulerLeader", self.scheduler_runner.start)
                )

                # Task 2: Billing Operations Consumer
                if has_broker and self._channel is not None:
                    active_channel = self._channel
                    tg.create_task(
                        self._supervise(
                            "BillingOperationsConsumer",
                            lambda: self.billing_consumer.start(active_channel),
                        )
                    )

                # Task 3: Notification Outbox Dispatcher
                if has_broker and self._channel is not None:
                    active_channel = self._channel
                    tg.create_task(
                        self._supervise(
                            "NotificationOutboxConsumer",
                            lambda: self.outbox_consumer.start(active_channel),
                        )
                    )
                else:
                    # Direct polling fallback if broker is disabled/offline
                    tg.create_task(
                        self._supervise(
                            "NotificationOutboxFallback",
                            self._run_outbox_fallback_loop,
                        )
                    )

                # Task 4: Stale Job Recovery Sweeper
                tg.create_task(
                    self._supervise(
                        "StaleJobSweeper",
                        self._run_stale_sweeper_loop,
                    )
                )

                # Wait for shutdown signal
                await self.shutdown_event.wait()
                logger.info("Shutdown event signaled. TaskGroup initiating termination...")

        except* Exception as eg:
            logger.info("TaskGroup exited with exceptions: %s", eg)

        # 4. Graceful Cleanup
        await self._shutdown()

    async def _shutdown(self) -> None:
        """Gracefully release leases and close infrastructure pools."""
        logger.info("Shutting down UnifiedWorkerRunner...")

        # Stop scheduler and consumers
        await self.scheduler_runner.stop()
        if self._channel:
            await self.billing_consumer.stop(self._channel)
            await self.outbox_consumer.stop(self._channel)

        # Close infrastructure connections
        await close_broker()
        await close_redis()
        await close_db()
        logger.info("UnifiedWorkerRunner graceful shutdown complete.")


def handle_signals(runner: UnifiedWorkerRunner) -> None:
    """Attach OS termination signal handlers for graceful shutdown."""
    loop = asyncio.get_event_loop()

    def _sig_handler() -> None:
        logger.info("Received exit signal. Requesting worker runner shutdown...")
        runner.shutdown_event.set()

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _sig_handler)
    else:
        # Windows fallback
        signal.signal(signal.SIGINT, lambda s, f: _sig_handler())
        signal.signal(signal.SIGTERM, lambda s, f: _sig_handler())


async def main() -> None:
    """CLI Entrypoint callable via `python -m apps.api.src.workers.runner`."""
    runner = UnifiedWorkerRunner()
    handle_signals(runner)
    try:
        await runner.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Process interrupted by user.")
    except Exception as exc:
        logger.critical("Fatal worker error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
