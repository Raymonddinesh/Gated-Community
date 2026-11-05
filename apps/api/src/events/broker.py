"""RabbitMQ Event Broker and Background Job Foundation using aio-pika."""

import json
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from apps.api.src.core.config import get_settings

logger = logging.getLogger("societysphere.broker")

_connection: AbstractRobustConnection | None = None
_channel: AbstractChannel | None = None


async def init_broker() -> AbstractRobustConnection | None:
    """Initialize robust RabbitMQ connection and channel."""
    global _connection, _channel
    settings = get_settings()

    if not settings.RABBITMQ_ENABLED:
        logger.info("RabbitMQ is disabled in configuration.")
        return None

    try:
        _connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=settings.RABBITMQ_CONNECTION_TIMEOUT,
        )
        _channel = await _connection.channel()
        logger.info("RabbitMQ robust connection established.")
        return _connection
    except Exception as exc:
        logger.warning(f"RabbitMQ connection warning (broker may be offline in dev): {exc}")
        return None


async def close_broker() -> None:
    """Close RabbitMQ connection cleanly at application shutdown."""
    global _connection, _channel
    if _connection and not _connection.is_closed:
        logger.info("Closing RabbitMQ connection...")
        await _connection.close()
        _connection = None
        _channel = None


async def check_broker_health() -> bool:
    """Probe RabbitMQ connectivity."""
    settings = get_settings()
    if not settings.RABBITMQ_ENABLED:
        return True  # If explicitly disabled, consider healthy

    global _connection
    if _connection is not None and not _connection.is_closed:
        return True

    try:
        temp_conn = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=settings.RABBITMQ_CONNECTION_TIMEOUT,
        )
        await temp_conn.close()
        return True
    except Exception:
        return False


class EventPublisher:
    """Abstract event and background job publisher."""

    @staticmethod
    async def publish_event(
        exchange_name: str,
        routing_key: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> bool:
        """
        Publish message to RabbitMQ exchange.
        In future modules, jobs will be routed with DLQ (Dead Letter Queue) and retry headers.
        """
        global _channel
        if _channel is None or _channel.is_closed:
            logger.warning(f"Cannot publish event to '{exchange_name}': RabbitMQ channel unavailable.")
            return False

        try:
            exchange = await _channel.declare_exchange(
                exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
            )
            message_body = json.dumps(payload).encode("utf-8")
            message = aio_pika.Message(
                body=message_body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers=headers or {},
            )
            await exchange.publish(message, routing_key=routing_key)
            logger.debug(f"Event published to {exchange_name}:{routing_key}")
            return True
        except Exception as exc:
            logger.error(f"Failed to publish event to {exchange_name}:{routing_key}: {exc}")
            return False
