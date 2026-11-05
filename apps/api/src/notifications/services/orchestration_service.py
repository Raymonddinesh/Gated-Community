"""Phase 20 Notification Orchestration Service Engine."""

import math
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.notifications import (
    Notification,
    NotificationBatch,
    NotificationDelivery,
    NotificationRecipient,
)
from apps.api.src.notifications.enums import (
    ChannelType,
    DeliveryStatus,
    NotificationStatus,
    RecipientType,
)
from apps.api.src.notifications.repositories import (
    DeliveryRepository,
    NotificationRepository,
)
from apps.api.src.notifications.services.audience_service import AudienceService
from apps.api.src.notifications.services.delivery_service import DeliveryService
from apps.api.src.notifications.services.preference_service import PreferenceService
from apps.api.src.notifications.services.template_service import TemplateService


class OrchestrationService:
    """Central Notification Orchestration Engine."""

    BATCH_SIZE = 500  # Max recipients per batch for scalable fan-out

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notif_repo = NotificationRepository(db)
        self.delivery_repo = DeliveryRepository(db)
        self.audience_service = AudienceService(db)
        self.preference_service = PreferenceService(db)
        self.template_service = TemplateService(db)
        self.delivery_service = DeliveryService(db)

    async def create_and_dispatch_notification(
        self,
        society_id: uuid.UUID,
        category: str,
        priority: str,
        source_domain: str,
        title: str,
        content: str,
        source_event_id: str | None = None,
        idempotency_key: str | None = None,
        payload: str | None = None,
        sender_id: uuid.UUID | None = None,
        recipient_user_ids: list[uuid.UUID] | None = None,
        recipient_type: str = RecipientType.RESIDENT.value,
        template_code: str | None = None,
        template_vars: dict[str, str] | None = None,
        channels: list[str] | None = None,
    ) -> Notification:
        """Create master notification, resolve audience & preferences, and queue channel deliveries."""
        # 1. Strong Idempotency Check
        if idempotency_key:
            existing = await self.notif_repo.get_by_idempotency_key(society_id, idempotency_key)
            if existing:
                return existing

        # 2. Render Template if template_code provided
        final_title = title
        final_content = content
        if template_code:
            target_channel = channels[0] if channels else ChannelType.IN_APP.value
            rendered_sub, rendered_body = await self.template_service.render_template(
                society_id, template_code, target_channel, "en", template_vars
            )
            if rendered_sub:
                final_title = rendered_sub
            final_content = rendered_body

        # 3. Create Master Notification
        notification = Notification(
            society_id=society_id,
            category=category,
            priority=priority,
            source_domain=source_domain,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key,
            title=final_title,
            content=final_content,
            payload=payload,
            sender_id=sender_id,
            status=NotificationStatus.CREATED.value,
        )
        notification = await self.notif_repo.create_notification(notification)

        # 4. Resolve Audience User IDs
        target_user_ids = await self.audience_service.resolve_recipients(
            society_id, recipient_type, recipient_user_ids
        )
        if not target_user_ids:
            notification.status = NotificationStatus.CANCELLED.value
            await self.db.flush()
            return notification

        # 5. Batch Fan-Out Preparation
        target_channels = channels or [ChannelType.IN_APP.value]
        total_recipients = len(target_user_ids)
        total_batches = math.ceil(total_recipients / self.BATCH_SIZE)

        # Create NotificationBatch records
        for b_idx in range(total_batches):
            b_count = min(self.BATCH_SIZE, total_recipients - b_idx * self.BATCH_SIZE)
            batch_obj = NotificationBatch(
                society_id=society_id,
                notification_id=notification.id,
                batch_index=b_idx + 1,
                total_batches=total_batches,
                recipient_count=b_count,
                status="PROCESSING",
            )
            self.db.add(batch_obj)

        # 6. Process Recipients & Deliveries
        created_recipients = []
        created_deliveries = []

        for user_id in target_user_ids:
            rec_obj = NotificationRecipient(
                society_id=society_id,
                notification_id=notification.id,
                user_id=user_id,
                recipient_type=recipient_type,
                is_read=False,
            )
            self.db.add(rec_obj)
            await self.db.flush()
            created_recipients.append(rec_obj)

            # Evaluate Preferences per Channel
            for ch in target_channels:
                is_allowed = await self.preference_service.is_notification_allowed(
                    society_id, user_id, category, priority, ch
                )
                deliv_status = (
                    DeliveryStatus.QUEUED.value if is_allowed else DeliveryStatus.SUPPRESSED.value
                )

                deliv_obj = NotificationDelivery(
                    society_id=society_id,
                    notification_id=notification.id,
                    recipient_id=rec_obj.id,
                    channel=ch,
                    status=deliv_status,
                    attempt_count=0,
                    max_attempts=3,
                )
                self.db.add(deliv_obj)
                created_deliveries.append(deliv_obj)

        await self.db.flush()

        # Update Master Notification Status
        notification.status = NotificationStatus.QUEUED.value
        await self.db.flush()

        # 7. Immediate Delivery Execution for QUEUED deliveries
        for deliv in created_deliveries:
            if deliv.status == DeliveryStatus.QUEUED.value:
                user_id = next(r.user_id for r in created_recipients if r.id == deliv.recipient_id)
                await self.delivery_service.execute_delivery(
                    society_id=society_id,
                    delivery=deliv,
                    recipient_user_id=user_id,
                    title=final_title,
                    content=final_content,
                )

        notification.status = NotificationStatus.SENT.value
        await self.db.flush()
        return notification
