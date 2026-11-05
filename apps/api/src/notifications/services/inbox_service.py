"""Phase 20 In-App Notification Inbox Service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.notifications.exceptions import RecipientNotFoundError
from apps.api.src.notifications.repositories import NotificationRepository
from apps.api.src.notifications.schemas import InboxItemResponse


class InboxService:
    """Service for managing In-App Notifications Inbox."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)

    async def get_user_inbox(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InboxItemResponse]:
        items = await self.repo.get_user_inbox(society_id, user_id, unread_only, limit, offset)
        results = []
        for item in items:
            notif = item.notification
            results.append(
                InboxItemResponse(
                    id=item.id,
                    society_id=item.society_id,
                    notification_id=item.notification_id,
                    title=notif.title if notif else "",
                    content=notif.content if notif else "",
                    category=notif.category if notif else "GENERAL",
                    priority=notif.priority if notif else "NORMAL",
                    source_domain=notif.source_domain if notif else "",
                    is_read=item.is_read,
                    read_at=item.read_at,
                    created_at=item.created_at,
                )
            )
        return results

    async def get_unread_count(self, society_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return await self.repo.get_unread_count(society_id, user_id)

    async def mark_as_read(
        self, society_id: uuid.UUID, user_id: uuid.UUID, recipient_id: uuid.UUID
    ) -> None:
        rec = await self.repo.mark_as_read(society_id, user_id, recipient_id)
        if not rec:
            raise RecipientNotFoundError(f"Notification recipient item '{recipient_id}' not found.")

    async def mark_all_as_read(self, society_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return await self.repo.mark_all_as_read(society_id, user_id)
