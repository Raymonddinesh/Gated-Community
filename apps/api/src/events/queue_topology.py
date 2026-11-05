"""RabbitMQ Queue & Exchange Topology Declaration for SocietySphere Background Workers.

Declares:
- Exchange: societysphere.jobs (Topic, durable)
- Exchange: societysphere.dlx (Direct, durable)
- Dead-Letter Queue: dead-letter-queue (durable, bound to societysphere.dlx with 'dlq')
- Queue: billing-operations-queue (durable, DLX-enabled, bound to job.billing.*)
- Queue: notification-outbox-queue (durable, DLX-enabled, bound to job.notifications.*)
"""

import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue

logger = logging.getLogger("societysphere.events.queue_topology")

JOBS_EXCHANGE = "societysphere.jobs"
DLX_EXCHANGE = "societysphere.dlx"
DLQ_ROUTING_KEY = "dlq"

BILLING_OPERATIONS_QUEUE = "billing-operations-queue"
NOTIFICATION_OUTBOX_QUEUE = "notification-outbox-queue"
DEAD_LETTER_QUEUE = "dead-letter-queue"

# Routing keys
ROUTING_KEY_PERIOD_ROLL = "job.billing.period_roll"
ROUTING_KEY_DUNNING_EVAL = "job.billing.dunning_eval"
ROUTING_KEY_OUTBOX_DRAIN = "job.notifications.outbox_drain"
ROUTING_KEY_STALE_SWEEP = "job.maintenance.stale_jobs"


async def setup_queue_topology(
    channel: AbstractChannel,
) -> dict[str, Any]:
    """Declare exchanges, queues, DLQ bindings, and arguments for the worker pipeline."""
    logger.info("Declaring RabbitMQ worker topology...")

    # 1. Declare Topic Exchange & Dead-Letter Exchange
    jobs_exchange: AbstractExchange = await channel.declare_exchange(
        JOBS_EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    dlx_exchange: AbstractExchange = await channel.declare_exchange(
        DLX_EXCHANGE,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    # 2. Declare Dead Letter Queue (DLQ)
    dlq: AbstractQueue = await channel.declare_queue(
        DEAD_LETTER_QUEUE,
        durable=True,
    )
    await dlq.bind(dlx_exchange, routing_key=DLQ_ROUTING_KEY)

    # 3. Declare Billing Operations Queue (DLX-protected)
    billing_queue: AbstractQueue = await channel.declare_queue(
        BILLING_OPERATIONS_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_EXCHANGE,
            "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
            "x-max-priority": 10,
        },
    )
    await billing_queue.bind(jobs_exchange, routing_key=ROUTING_KEY_PERIOD_ROLL)
    await billing_queue.bind(jobs_exchange, routing_key=ROUTING_KEY_DUNNING_EVAL)

    # 4. Declare Notification Outbox Queue (DLX-protected)
    outbox_queue: AbstractQueue = await channel.declare_queue(
        NOTIFICATION_OUTBOX_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_EXCHANGE,
            "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
        },
    )
    await outbox_queue.bind(jobs_exchange, routing_key=ROUTING_KEY_OUTBOX_DRAIN)

    logger.info(
        "RabbitMQ topology successfully declared: %s, %s, %s, %s, %s",
        JOBS_EXCHANGE,
        DLX_EXCHANGE,
        BILLING_OPERATIONS_QUEUE,
        NOTIFICATION_OUTBOX_QUEUE,
        DEAD_LETTER_QUEUE,
    )

    return {
        "jobs_exchange": jobs_exchange,
        "dlx_exchange": dlx_exchange,
        "billing_queue": billing_queue,
        "outbox_queue": outbox_queue,
        "dlq": dlq,
    }
