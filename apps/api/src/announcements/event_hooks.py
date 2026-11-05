"""Phase 16 Announcement Decoupled Event Hooks for Notification Readiness."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class AnnouncementEventHooks:
    """Decoupled domain event hooks for announcement lifecycle events."""

    @staticmethod
    def on_announcement_created(
        announcement_id: UUID,
        society_id: UUID,
        author_id: UUID,
        announcement_number: str,
        priority: str,
    ) -> None:
        logger.info(
            "AnnouncementEvent created: id=%s, number=%s, priority=%s, society=%s",
            announcement_id,
            announcement_number,
            priority,
            society_id,
        )

    @staticmethod
    def on_announcement_submitted(
        announcement_id: UUID,
        society_id: UUID,
        announcement_number: str,
    ) -> None:
        logger.info(
            "AnnouncementEvent submitted for review: id=%s, number=%s", announcement_id, announcement_number
        )

    @staticmethod
    def on_announcement_approved(
        announcement_id: UUID,
        society_id: UUID,
        approver_id: UUID,
        announcement_number: str,
    ) -> None:
        logger.info(
            "AnnouncementEvent approved: id=%s, number=%s, approver=%s",
            announcement_id,
            announcement_number,
            approver_id,
        )

    @staticmethod
    def on_announcement_scheduled(
        announcement_id: UUID,
        society_id: UUID,
        publish_at_iso: str,
        announcement_number: str,
    ) -> None:
        logger.info(
            "AnnouncementEvent scheduled: id=%s, number=%s, publish_at=%s",
            announcement_id,
            announcement_number,
            publish_at_iso,
        )

    @staticmethod
    def on_announcement_published(
        announcement_id: UUID,
        society_id: UUID,
        announcement_number: str,
        priority: str,
        requires_acknowledgement: bool,
    ) -> None:
        logger.info(
            "AnnouncementEvent published: id=%s, number=%s, priority=%s, requires_ack=%s",
            announcement_id,
            announcement_number,
            priority,
            requires_acknowledgement,
        )

    @staticmethod
    def on_announcement_updated(
        announcement_id: UUID,
        society_id: UUID,
        version_number: int,
    ) -> None:
        logger.info("AnnouncementEvent updated: id=%s, new_version=%d", announcement_id, version_number)

    @staticmethod
    def on_announcement_expired(
        announcement_id: UUID,
        society_id: UUID,
        announcement_number: str,
    ) -> None:
        logger.info("AnnouncementEvent expired: id=%s, number=%s", announcement_id, announcement_number)

    @staticmethod
    def on_announcement_acknowledged(
        announcement_id: UUID,
        society_id: UUID,
        user_id: UUID,
        version_number: int,
    ) -> None:
        logger.info(
            "AnnouncementEvent acknowledged: id=%s, user=%s, version=%d",
            announcement_id,
            user_id,
            version_number,
        )
