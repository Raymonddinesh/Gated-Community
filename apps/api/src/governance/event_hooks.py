"""Phase 18 Governance Domain Hooks (Decoupled Notification Readiness)."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class GovernanceDomainHooks:
    """Emits decoupled domain events for governance lifecycle changes."""

    @staticmethod
    async def emit_meeting_created(
        society_id: UUID, meeting_id: UUID, meeting_number: str, title: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: MEETING_CREATED - society=%s meeting=%s no=%s title='%s'",
            society_id,
            meeting_id,
            meeting_number,
            title,
        )

    @staticmethod
    async def emit_meeting_notice_published(society_id: UUID, meeting_id: UUID, meeting_number: str) -> None:
        logger.info(
            "DOMAIN_EVENT: MEETING_NOTICE_PUBLISHED - society=%s meeting=%s no=%s",
            society_id,
            meeting_id,
            meeting_number,
        )

    @staticmethod
    async def emit_quorum_result(
        society_id: UUID, meeting_id: UUID, status: str, present: int, required: int
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: QUORUM_RESULT - society=%s meeting=%s status=%s present=%d required=%d",
            society_id,
            meeting_id,
            status,
            present,
            required,
        )

    @staticmethod
    async def emit_resolution_proposed(
        society_id: UUID, resolution_id: UUID, resolution_number: str, title: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: RESOLUTION_PROPOSED - society=%s resolution=%s no=%s title='%s'",
            society_id,
            resolution_id,
            resolution_number,
            title,
        )

    @staticmethod
    async def emit_resolution_result(
        society_id: UUID, resolution_id: UUID, status: str, votes_for: int, votes_against: int
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: RESOLUTION_RESULT - society=%s resolution=%s status=%s for=%d against=%d",
            society_id,
            resolution_id,
            status,
            votes_for,
            votes_against,
        )

    @staticmethod
    async def emit_minutes_published(society_id: UUID, meeting_id: UUID, version: int) -> None:
        logger.info(
            "DOMAIN_EVENT: MINUTES_PUBLISHED - society=%s meeting=%s version=%d",
            society_id,
            meeting_id,
            version,
        )

    @staticmethod
    async def emit_action_item_created(
        society_id: UUID, action_item_id: UUID, title: str, assigned_to: UUID
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: GOVERNANCE_ACTION_ITEM_CREATED - society=%s item=%s title='%s' assignee=%s",
            society_id,
            action_item_id,
            title,
            assigned_to,
        )
