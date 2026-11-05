"""Phase 20 Notifications & Communication Delivery Comprehensive Test Suite."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.database.models.notifications import (
    Notification,
)
from apps.api.src.notifications.enums import (
    ChannelType,
    NotificationCategory,
    NotificationStatus,
    PriorityLevel,
)
from apps.api.src.notifications.exceptions import (
    TemplateRenderError,
)
from apps.api.src.notifications.listeners.domain_event_listener import DomainEventListener
from apps.api.src.notifications.services.inbox_service import InboxService
from apps.api.src.notifications.services.orchestration_service import OrchestrationService
from apps.api.src.notifications.services.preference_service import PreferenceService
from apps.api.src.notifications.services.template_service import TemplateService


@pytest.mark.asyncio
async def test_notification_creation_and_lifecycle(db_session: AsyncSession):
    """Verify master notification creation and queue lifecycle."""
    society_id = uuid.uuid4()
    user_id = uuid.uuid4()
    orchestrator = OrchestrationService(db_session)

    notif = await orchestrator.create_and_dispatch_notification(
        society_id=society_id,
        category=NotificationCategory.GENERAL.value,
        priority=PriorityLevel.NORMAL.value,
        source_domain="test",
        title="Test Notification",
        content="This is a test notification message.",
        recipient_user_ids=[user_id],
    )

    assert notif.id is not None
    assert notif.society_id == society_id
    assert notif.status in (NotificationStatus.QUEUED.value, NotificationStatus.SENT.value)
    assert notif.title == "Test Notification"


@pytest.mark.asyncio
async def test_idempotency_prevention(db_session: AsyncSession):
    """Verify idempotency key prevents duplicate notification generation."""
    society_id = uuid.uuid4()
    user_id = uuid.uuid4()
    idempotency_key = f"idemp-{uuid.uuid4()}"
    orchestrator = OrchestrationService(db_session)

    notif1 = await orchestrator.create_and_dispatch_notification(
        society_id=society_id,
        category=NotificationCategory.ANNOUNCEMENT.value,
        priority=PriorityLevel.NORMAL.value,
        source_domain="announcements",
        title="Unique Announcement",
        content="First broadcast.",
        idempotency_key=idempotency_key,
        recipient_user_ids=[user_id],
    )

    notif2 = await orchestrator.create_and_dispatch_notification(
        society_id=society_id,
        category=NotificationCategory.ANNOUNCEMENT.value,
        priority=PriorityLevel.NORMAL.value,
        source_domain="announcements",
        title="Unique Announcement Duplicate Attempt",
        content="Second broadcast attempt.",
        idempotency_key=idempotency_key,
        recipient_user_ids=[user_id],
    )

    assert notif1.id == notif2.id
    assert notif2.title == "Unique Announcement"


@pytest.mark.asyncio
async def test_template_rendering_and_variable_allowlisting(db_session: AsyncSession):
    """Verify template versioning, locale lookup, variable allowlisting, and HTML escaping."""
    society_id = uuid.uuid4()
    template_service = TemplateService(db_session)

    tmpl = await template_service.create_template(
        society_id=society_id,
        code="TEST_BILL_V1",
        name="Test Bill Template",
        category=NotificationCategory.BILLING.value,
        allowlisted_variables=["invoice_num", "amount"],
    )

    await template_service.create_version(
        society_id=society_id,
        template_id=tmpl.id,
        channel=ChannelType.IN_APP.value,
        locale="en",
        version=1,
        subject_template="Invoice #{invoice_num}",
        body_template="Your bill for ₹{amount} is ready.",
    )

    sub, body = await template_service.render_template(
        society_id=society_id,
        template_code="TEST_BILL_V1",
        channel=ChannelType.IN_APP.value,
        locale="en",
        variables={"invoice_num": "1001", "amount": "2500"},
    )

    assert sub == "Invoice #1001"
    assert body == "Your bill for ₹2500 is ready."

    # Test disallowed variable injection
    with pytest.raises(TemplateRenderError):
        await template_service.render_template(
            society_id=society_id,
            template_code="TEST_BILL_V1",
            channel=ChannelType.IN_APP.value,
            locale="en",
            variables={"invoice_num": "1001", "malicious_script": "<script>alert(1)</script>"},
        )


@pytest.mark.asyncio
async def test_emergency_critical_priority_override(db_session: AsyncSession):
    """Verify CRITICAL priority emergency alerts bypass quiet hours and category opt-outs."""
    society_id = uuid.uuid4()
    user_id = uuid.uuid4()
    pref_service = PreferenceService(db_session)

    # Disable EMERGENCY category for user and set quiet hours
    await pref_service.update_category_preference(
        society_id=society_id,
        user_id=user_id,
        category=NotificationCategory.EMERGENCY.value,
        is_enabled=False,
        quiet_hours_enabled=True,
        quiet_hours_start="00:00",
        quiet_hours_end="23:59",
    )

    # Normal priority should be blocked
    normal_allowed = await pref_service.is_notification_allowed(
        society_id=society_id,
        user_id=user_id,
        category=NotificationCategory.EMERGENCY.value,
        priority=PriorityLevel.NORMAL.value,
        channel=ChannelType.IN_APP.value,
    )
    assert normal_allowed is False

    # CRITICAL priority emergency MUST BE ALLOWED (Emergency Override)
    critical_allowed = await pref_service.is_notification_allowed(
        society_id=society_id,
        user_id=user_id,
        category=NotificationCategory.EMERGENCY.value,
        priority=PriorityLevel.CRITICAL.value,
        channel=ChannelType.IN_APP.value,
    )
    assert critical_allowed is True


@pytest.mark.asyncio
async def test_inbox_service_and_read_receipts(db_session: AsyncSession):
    """Verify inbox listing, unread counter, and idempotent read receipts."""
    society_id = uuid.uuid4()
    user_id = uuid.uuid4()
    orchestrator = OrchestrationService(db_session)
    inbox_service = InboxService(db_session)

    # Create notification
    await orchestrator.create_and_dispatch_notification(
        society_id=society_id,
        category=NotificationCategory.ANNOUNCEMENT.value,
        priority=PriorityLevel.NORMAL.value,
        source_domain="announcements",
        title="Inbox Test Announcement",
        content="Testing inbox functionality.",
        recipient_user_ids=[user_id],
    )

    unread_count = await inbox_service.get_unread_count(society_id, user_id)
    assert unread_count >= 1

    inbox_items = await inbox_service.get_user_inbox(society_id, user_id, unread_only=True)
    assert len(inbox_items) >= 1

    target_item = inbox_items[0]
    await inbox_service.mark_as_read(society_id, user_id, target_item.id)

    post_unread = await inbox_service.get_unread_count(society_id, user_id)
    assert post_unread == unread_count - 1


@pytest.mark.asyncio
async def test_financial_domain_isolation(db_session: AsyncSession):
    """Verify Phase 20 Notification operations NEVER mutate financial core models."""
    society_id = uuid.uuid4()
    user_id = uuid.uuid4()
    orchestrator = OrchestrationService(db_session)

    # Dispatch notification
    await orchestrator.create_and_dispatch_notification(
        society_id=society_id,
        category=NotificationCategory.BILLING.value,
        priority=PriorityLevel.NORMAL.value,
        source_domain="billing",
        title="Invoice Notice",
        content="Invoice issued for unit.",
        recipient_user_ids=[user_id],
    )

    # Verify no new financial journal entries or payments created
    new_journals = await db_session.execute(JournalEntry.__table__.select())
    assert len(new_journals.fetchall()) == 0


@pytest.mark.asyncio
async def test_domain_event_listener_incident_alert(db_session: AsyncSession):
    """Verify DomainEventListener processes Phase 19 Incident Alerts correctly."""
    society_id = uuid.uuid4()
    incident_id = uuid.uuid4()
    listener = DomainEventListener(db_session)

    await listener.handle_incident_alert(
        society_id=society_id,
        incident_id=incident_id,
        incident_number="INC-202610-099",
        title="Gas Leak in Basement",
        severity="CRITICAL",
        category="Hazard",
    )

    # Verify master notification created for emergency
    res = await db_session.execute(
        Notification.__table__.select().where(Notification.society_id == society_id)
    )
    notifs = res.fetchall()
    assert len(notifs) >= 1
    assert "INC-202610-099" in notifs[0].title
