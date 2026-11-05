"""Phase 17 Event Domain Hooks (Decoupled Notification Readiness)."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class EventDomainHooks:
    """Emits decoupled domain events for event lifecycle changes."""

    @staticmethod
    async def emit_event_created(society_id: UUID, event_id: UUID, title: str, organizer_id: UUID) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_CREATED - society=%s event=%s title='%s' organizer=%s",
            society_id,
            event_id,
            title,
            organizer_id,
        )

    @staticmethod
    async def emit_event_approved(society_id: UUID, event_id: UUID, approver_id: UUID) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_APPROVED - society=%s event=%s approver=%s",
            society_id,
            event_id,
            approver_id,
        )

    @staticmethod
    async def emit_event_published(society_id: UUID, event_id: UUID, title: str) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_PUBLISHED - society=%s event=%s title='%s'",
            society_id,
            event_id,
            title,
        )

    @staticmethod
    async def emit_registration_opened(society_id: UUID, event_id: UUID) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_REGISTRATION_OPENED - society=%s event=%s",
            society_id,
            event_id,
        )

    @staticmethod
    async def emit_registration_confirmed(
        society_id: UUID, event_id: UUID, user_id: UUID, registration_number: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_REGISTRATION_CONFIRMED - society=%s event=%s user=%s reg_no=%s",
            society_id,
            event_id,
            user_id,
            registration_number,
        )

    @staticmethod
    async def emit_registration_cancelled(society_id: UUID, event_id: UUID, user_id: UUID) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_REGISTRATION_CANCELLED - society=%s event=%s user=%s",
            society_id,
            event_id,
            user_id,
        )

    @staticmethod
    async def emit_event_cancelled(society_id: UUID, event_id: UUID, reason: str) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_CANCELLED - society=%s event=%s reason='%s'",
            society_id,
            event_id,
            reason,
        )

    @staticmethod
    async def emit_event_started(society_id: UUID, event_id: UUID) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_STARTED - society=%s event=%s",
            society_id,
            event_id,
        )

    @staticmethod
    async def emit_event_completed(society_id: UUID, event_id: UUID) -> None:
        logger.info(
            "DOMAIN_EVENT: EVENT_COMPLETED - society=%s event=%s",
            society_id,
            event_id,
        )
