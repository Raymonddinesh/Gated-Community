"""Phase 20 Notifications & Communication Delivery Repositories."""

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.notifications import (
    Notification,
    NotificationChannelPreference,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
    NotificationTemplateVersion,
    UserDeviceToken,
)


class NotificationRepository:
    """Repository for Notifications and Recipients."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(self, notification: Notification) -> Notification:
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def get_by_id(self, society_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
        stmt = (
            select(Notification)
            .where(
                and_(
                    Notification.society_id == society_id,
                    Notification.id == notification_id,
                )
            )
            .options(
                selectinload(Notification.recipients),
                selectinload(Notification.deliveries),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, society_id: uuid.UUID, idempotency_key: str
    ) -> Notification | None:
        stmt = select(Notification).where(
            and_(
                Notification.society_id == society_id,
                Notification.idempotency_key == idempotency_key,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def create_recipient(self, recipient: NotificationRecipient) -> NotificationRecipient:
        self.db.add(recipient)
        await self.db.flush()
        return recipient

    async def create_recipients_bulk(
        self, recipients: list[NotificationRecipient]
    ) -> list[NotificationRecipient]:
        self.db.add_all(recipients)
        await self.db.flush()
        return recipients

    async def get_user_inbox(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[NotificationRecipient]:
        conditions = [
            NotificationRecipient.society_id == society_id,
            NotificationRecipient.user_id == user_id,
        ]
        if unread_only:
            conditions.append(NotificationRecipient.is_read == False)  # noqa: E712

        stmt = (
            select(NotificationRecipient)
            .where(and_(*conditions))
            .options(selectinload(NotificationRecipient.notification))
            .order_by(NotificationRecipient.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_unread_count(self, society_id: uuid.UUID, user_id: uuid.UUID) -> int:
        stmt = select(func.count(NotificationRecipient.id)).where(
            and_(
                NotificationRecipient.society_id == society_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_read == False,  # noqa: E712
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar() or 0

    async def mark_as_read(
        self, society_id: uuid.UUID, user_id: uuid.UUID, recipient_id: uuid.UUID
    ) -> NotificationRecipient | None:
        stmt = select(NotificationRecipient).where(
            and_(
                NotificationRecipient.society_id == society_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.id == recipient_id,
            )
        )
        res = await self.db.execute(stmt)
        recipient = res.scalar_one_or_none()
        if recipient and not recipient.is_read:
            recipient.is_read = True
            recipient.read_at = datetime.now()
            await self.db.flush()
        return recipient

    async def mark_all_as_read(self, society_id: uuid.UUID, user_id: uuid.UUID) -> int:
        stmt = (
            update(NotificationRecipient)
            .where(
                and_(
                    NotificationRecipient.society_id == society_id,
                    NotificationRecipient.user_id == user_id,
                    NotificationRecipient.is_read == False,  # noqa: E712
                )
            )
            .values(is_read=True, read_at=datetime.now())
        )
        res = await self.db.execute(stmt)
        await self.db.flush()
        return getattr(res, "rowcount", 0) or 0


class TemplateRepository:
    """Repository for Templates and Versions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_template(self, template: NotificationTemplate) -> NotificationTemplate:
        self.db.add(template)
        await self.db.flush()
        return template

    async def get_template_by_code(
        self, society_id: uuid.UUID | None, code: str
    ) -> NotificationTemplate | None:
        # Match society specific template, or fallback to global template (society_id IS NULL)
        stmt = (
            select(NotificationTemplate)
            .where(
                and_(
                    NotificationTemplate.code == code,
                    NotificationTemplate.is_active == True,  # noqa: E712
                    (NotificationTemplate.society_id == society_id)
                    | (NotificationTemplate.society_id.is_(None)),
                )
            )
            .options(selectinload(NotificationTemplate.versions))
            .order_by(NotificationTemplate.society_id.desc().nullslast())
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def create_version(
        self, version: NotificationTemplateVersion
    ) -> NotificationTemplateVersion:
        self.db.add(version)
        await self.db.flush()
        return version

    async def get_published_version(
        self,
        template_id: uuid.UUID,
        channel: str,
        locale: str = "en",
    ) -> NotificationTemplateVersion | None:
        # Try exact locale first
        stmt = select(NotificationTemplateVersion).where(
            and_(
                NotificationTemplateVersion.template_id == template_id,
                NotificationTemplateVersion.channel == channel,
                NotificationTemplateVersion.locale == locale,
                NotificationTemplateVersion.is_published == True,  # noqa: E712
            )
        ).order_by(NotificationTemplateVersion.version.desc())
        res = await self.db.execute(stmt)
        version = res.scalars().first()

        # Fallback to English if requested locale not found
        if not version and locale != "en":
            stmt_fallback = select(NotificationTemplateVersion).where(
                and_(
                    NotificationTemplateVersion.template_id == template_id,
                    NotificationTemplateVersion.channel == channel,
                    NotificationTemplateVersion.locale == "en",
                    NotificationTemplateVersion.is_published == True,  # noqa: E712
                )
            ).order_by(NotificationTemplateVersion.version.desc())
            res_fb = await self.db.execute(stmt_fallback)
            version = res_fb.scalars().first()

        return version


class PreferenceRepository:
    """Repository for User Preferences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_preference(
        self, society_id: uuid.UUID, user_id: uuid.UUID, category: str
    ) -> NotificationPreference | None:
        stmt = select(NotificationPreference).where(
            and_(
                NotificationPreference.society_id == society_id,
                NotificationPreference.user_id == user_id,
                NotificationPreference.category == category,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def set_preference(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        is_enabled: bool,
        quiet_hours_enabled: bool = False,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
    ) -> NotificationPreference:
        pref = await self.get_preference(society_id, user_id, category)
        if not pref:
            pref = NotificationPreference(
                society_id=society_id,
                user_id=user_id,
                category=category,
            )
            self.db.add(pref)

        pref.is_enabled = is_enabled
        pref.quiet_hours_enabled = quiet_hours_enabled
        pref.quiet_hours_start = quiet_hours_start
        pref.quiet_hours_end = quiet_hours_end
        await self.db.flush()
        return pref

    async def get_channel_preference(
        self, society_id: uuid.UUID, user_id: uuid.UUID, category: str, channel: str
    ) -> NotificationChannelPreference | None:
        stmt = select(NotificationChannelPreference).where(
            and_(
                NotificationChannelPreference.society_id == society_id,
                NotificationChannelPreference.user_id == user_id,
                NotificationChannelPreference.category == category,
                NotificationChannelPreference.channel == channel,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def set_channel_preference(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        channel: str,
        is_enabled: bool,
    ) -> NotificationChannelPreference:
        pref = await self.get_channel_preference(society_id, user_id, category, channel)
        if not pref:
            pref = NotificationChannelPreference(
                society_id=society_id,
                user_id=user_id,
                category=category,
                channel=channel,
            )
            self.db.add(pref)

        pref.is_enabled = is_enabled
        await self.db.flush()
        return pref


class DeliveryRepository:
    """Repository for Deliveries and Attempts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self.db.add(delivery)
        await self.db.flush()
        return delivery

    async def create_deliveries_bulk(
        self, deliveries: list[NotificationDelivery]
    ) -> list[NotificationDelivery]:
        self.db.add_all(deliveries)
        await self.db.flush()
        return deliveries

    async def create_attempt(
        self, attempt: NotificationDeliveryAttempt
    ) -> NotificationDeliveryAttempt:
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_deliveries_by_notification(
        self, society_id: uuid.UUID, notification_id: uuid.UUID
    ) -> list[NotificationDelivery]:
        stmt = (
            select(NotificationDelivery)
            .where(
                and_(
                    NotificationDelivery.society_id == society_id,
                    NotificationDelivery.notification_id == notification_id,
                )
            )
            .options(selectinload(NotificationDelivery.attempts))
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class DeviceTokenRepository:
    """Repository for Mobile Device Tokens."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_token(
        self, society_id: uuid.UUID, user_id: uuid.UUID, device_token: str, platform: str
    ) -> UserDeviceToken:
        stmt = select(UserDeviceToken).where(
            and_(
                UserDeviceToken.society_id == society_id,
                UserDeviceToken.user_id == user_id,
                UserDeviceToken.device_token == device_token,
            )
        )
        res = await self.db.execute(stmt)
        token_obj = res.scalar_one_or_none()

        if not token_obj:
            token_obj = UserDeviceToken(
                society_id=society_id,
                user_id=user_id,
                device_token=device_token,
                platform=platform,
                is_active=True,
            )
            self.db.add(token_obj)
        else:
            token_obj.is_active = True
            token_obj.platform = platform
            token_obj.last_used_at = datetime.now()

        await self.db.flush()
        return token_obj

    async def get_active_tokens_for_user(
        self, society_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[UserDeviceToken]:
        stmt = select(UserDeviceToken).where(
            and_(
                UserDeviceToken.society_id == society_id,
                UserDeviceToken.user_id == user_id,
                UserDeviceToken.is_active == True,  # noqa: E712
            )
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
