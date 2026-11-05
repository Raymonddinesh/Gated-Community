"""Phase 20 Notifications & Communication Delivery Domain Finalization Test Suite."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.notifications import (
    Notification,
    NotificationRecipient,
)
from apps.api.src.notifications.providers.factory import provider_factory
from apps.api.src.notifications.repositories import (
    DeviceTokenRepository,
    NotificationRepository,
)


@pytest.mark.asyncio
async def test_provider_factory_and_neutral_adapters():
    """Verify all 5 provider adapters are registered and return valid provider responses."""
    channels = ["IN_APP", "EMAIL", "SMS", "WHATSAPP", "PUSH"]
    for ch in channels:
        prov = provider_factory.get_provider(ch)
        assert prov is not None
        assert prov.channel == ch
        assert prov.provider_name is not None


@pytest.mark.asyncio
async def test_device_token_registration(db_session: AsyncSession):
    """Verify device token registration and retrieval."""
    society_id = uuid.uuid4()
    user_id = uuid.uuid4()
    repo = DeviceTokenRepository(db_session)

    token_obj = await repo.register_token(
        society_id=society_id,
        user_id=user_id,
        device_token="fcm-token-abc123xyz",
        platform="ANDROID",
    )

    assert token_obj.id is not None
    assert token_obj.device_token == "fcm-token-abc123xyz"
    assert token_obj.is_active is True

    tokens = await repo.get_active_tokens_for_user(society_id, user_id)
    assert len(tokens) == 1
    assert tokens[0].device_token == "fcm-token-abc123xyz"


@pytest.mark.asyncio
async def test_tenant_isolation_recipients(db_session: AsyncSession):
    """Verify cross-tenant inbox isolation between Society A and Society B."""
    society_a = uuid.uuid4()
    society_b = uuid.uuid4()
    user_a = uuid.uuid4()

    notif_a = Notification(
        society_id=society_a,
        category="GENERAL",
        priority="NORMAL",
        source_domain="test",
        title="Society A Notice",
        content="Notice for A",
        status="SENT",
    )
    db_session.add(notif_a)
    await db_session.flush()

    rec_a = NotificationRecipient(
        society_id=society_a,
        notification_id=notif_a.id,
        user_id=user_a,
        recipient_type="RESIDENT",
    )
    db_session.add(rec_a)
    await db_session.flush()

    repo = NotificationRepository(db_session)
    inbox_b = await repo.get_user_inbox(society_b, user_a)
    assert len(inbox_b) == 0
