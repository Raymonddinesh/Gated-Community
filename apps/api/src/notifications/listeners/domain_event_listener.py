"""Phase 20 Domain Event Listener Integration."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.notifications.enums import NotificationCategory, PriorityLevel
from apps.api.src.notifications.services.orchestration_service import OrchestrationService

logger = logging.getLogger(__name__)


class DomainEventListener:
    """Listener mapping Domain Events across SocietySphere phases to Notification Intents."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.orchestration_service = OrchestrationService(db)

    async def handle_incident_alert(
        self,
        society_id: uuid.UUID,
        incident_id: uuid.UUID,
        incident_number: str,
        title: str,
        severity: str,
        category: str,
        sender_id: uuid.UUID | None = None,
    ) -> None:
        """Handle Phase 19 Emergency Incident Alert Domain Event."""
        logger.info(f"DOMAIN_EVENT: Phase 19 Incident Alert {incident_number} severity={severity}")
        priority = PriorityLevel.CRITICAL.value if severity in ("CRITICAL", "HIGH") else PriorityLevel.HIGH.value

        await self.orchestration_service.create_and_dispatch_notification(
            society_id=society_id,
            category=NotificationCategory.EMERGENCY.value,
            priority=priority,
            source_domain="incidents",
            source_event_id=str(incident_id),
            idempotency_key=f"inc-alert-{incident_id}",
            title=f"EMERGENCY: [{incident_number}] {title}",
            content=f"Emergency Incident Reported: {title}. Severity: {severity}. Category: {category}.",
            sender_id=sender_id,
            recipient_type="ALL_RESIDENTS",
        )

    async def handle_announcement_published(
        self,
        society_id: uuid.UUID,
        announcement_id: uuid.UUID,
        title: str,
        content_preview: str,
        sender_id: uuid.UUID | None = None,
    ) -> None:
        """Handle Phase 16 Announcement Published Domain Event."""
        logger.info(f"DOMAIN_EVENT: Phase 16 Announcement Published {announcement_id}")

        await self.orchestration_service.create_and_dispatch_notification(
            society_id=society_id,
            category=NotificationCategory.ANNOUNCEMENT.value,
            priority=PriorityLevel.NORMAL.value,
            source_domain="announcements",
            source_event_id=str(announcement_id),
            idempotency_key=f"ann-pub-{announcement_id}",
            title=f"Announcement: {title}",
            content=content_preview,
            sender_id=sender_id,
            recipient_type="ALL_RESIDENTS",
        )

    async def handle_billing_invoice_generated(
        self,
        society_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
        user_id: uuid.UUID,
        amount_due: float,
        due_date_str: str,
    ) -> None:
        """Handle Phase 5/6 Maintenance Billing Invoice Generated Domain Event."""
        logger.info(f"DOMAIN_EVENT: Phase 5 Invoice Generated {invoice_number} for user {user_id}")

        await self.orchestration_service.create_and_dispatch_notification(
            society_id=society_id,
            category=NotificationCategory.BILLING.value,
            priority=PriorityLevel.NORMAL.value,
            source_domain="billing",
            source_event_id=str(invoice_id),
            idempotency_key=f"inv-gen-{invoice_id}",
            title=f"New Invoice Issued: #{invoice_number}",
            content=f"Your maintenance invoice #{invoice_number} for amount ₹{amount_due:.2f} has been issued. Due date: {due_date_str}.",
            recipient_user_ids=[user_id],
        )

    async def handle_meeting_scheduled(
        self,
        society_id: uuid.UUID,
        meeting_id: uuid.UUID,
        title: str,
        meeting_date_str: str,
    ) -> None:
        """Handle Phase 18 Governance Meeting Scheduled Domain Event."""
        logger.info(f"DOMAIN_EVENT: Phase 18 Governance Meeting Scheduled {meeting_id}")

        await self.orchestration_service.create_and_dispatch_notification(
            society_id=society_id,
            category=NotificationCategory.GOVERNANCE.value,
            priority=PriorityLevel.NORMAL.value,
            source_domain="governance",
            source_event_id=str(meeting_id),
            idempotency_key=f"gov-meet-{meeting_id}",
            title=f"Committee Meeting: {title}",
            content=f"A committee meeting '{title}' has been scheduled for {meeting_date_str}.",
            recipient_type="COMMITTEE",
        )
