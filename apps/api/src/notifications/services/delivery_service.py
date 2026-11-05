"""Phase 20 Notification Delivery Execution & Retry Service."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.notifications import (
    NotificationDelivery,
    NotificationDeliveryAttempt,
)
from apps.api.src.notifications.enums import AttemptStatus, DeliveryStatus
from apps.api.src.notifications.providers.base import ProviderMessage
from apps.api.src.notifications.providers.factory import provider_factory
from apps.api.src.notifications.repositories import DeliveryRepository


class DeliveryService:
    """Service for executing channel deliveries, handling attempts, backoff, and retries."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DeliveryRepository(db)

    async def execute_delivery(
        self,
        society_id: uuid.UUID,
        delivery: NotificationDelivery,
        recipient_user_id: uuid.UUID,
        title: str,
        content: str,
        recipient_address: str | None = None,
    ) -> NotificationDelivery:
        provider = provider_factory.get_provider(delivery.channel)
        if not provider:
            delivery.status = DeliveryStatus.FAILED.value
            delivery.error_message = f"No provider configured for channel {delivery.channel}"
            delivery.failed_at = datetime.now()
            await self.db.flush()
            return delivery

        delivery.status = DeliveryStatus.PROCESSING.value
        delivery.attempt_count += 1
        await self.db.flush()

        msg = ProviderMessage(
            notification_id=delivery.notification_id,
            delivery_id=delivery.id,
            recipient_user_id=recipient_user_id,
            channel=delivery.channel,
            recipient_address=recipient_address or str(recipient_user_id),
            subject=title,
            content=content,
        )

        resp = await provider.send(msg)

        # Log Attempt
        attempt_status = (
            AttemptStatus.SUCCESS.value
            if resp.success
            else (
                AttemptStatus.RETRYABLE_FAILURE.value
                if resp.is_retryable
                else AttemptStatus.FAILED.value
            )
        )

        attempt = NotificationDeliveryAttempt(
            society_id=society_id,
            delivery_id=delivery.id,
            attempt_number=delivery.attempt_count,
            provider_name=resp.provider_name,
            provider_request_id=resp.provider_request_id,
            status=attempt_status,
            response_code=resp.response_code,
            error_message=resp.error_message,
            latency_ms=resp.latency_ms,
        )
        await self.repo.create_attempt(attempt)

        # Update Delivery State
        if resp.success:
            delivery.status = DeliveryStatus.DELIVERED.value
            delivery.sent_at = resp.sent_at
            delivery.delivered_at = datetime.now()
        else:
            if resp.is_retryable and delivery.attempt_count < delivery.max_attempts:
                delivery.status = DeliveryStatus.RETRYING.value
                backoff_minutes = 5 * (2 ** (delivery.attempt_count - 1))
                delivery.next_retry_at = datetime.now() + timedelta(minutes=backoff_minutes)
            else:
                delivery.status = DeliveryStatus.FAILED.value
                delivery.failed_at = datetime.now()
                delivery.error_message = resp.error_message or "Provider delivery failed."

        await self.db.flush()
        return delivery
