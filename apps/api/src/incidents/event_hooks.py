"""Phase 19 Incident Management Domain Event Hooks (Decoupled Notification Readiness)."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class IncidentDomainHooks:
    """Emits provider-neutral domain events for incident lifecycle changes."""

    @staticmethod
    async def emit_incident_reported(
        society_id: UUID, incident_id: UUID, incident_number: str, severity: str, title: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_REPORTED - society=%s incident=%s number=%s severity=%s title='%s'",
            society_id,
            incident_id,
            incident_number,
            severity,
            title,
        )

    @staticmethod
    async def emit_incident_triaged(
        society_id: UUID, incident_id: UUID, incident_number: str, severity: str, triaged_by_id: UUID
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_TRIAGED - society=%s incident=%s number=%s severity=%s triaged_by=%s",
            society_id,
            incident_id,
            incident_number,
            severity,
            triaged_by_id,
        )

    @staticmethod
    async def emit_incident_acknowledged(
        society_id: UUID, incident_id: UUID, incident_number: str, responder_id: UUID, responder_role: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_ACKNOWLEDGED - society=%s incident=%s number=%s responder=%s role=%s",
            society_id,
            incident_id,
            incident_number,
            responder_id,
            responder_role,
        )

    @staticmethod
    async def emit_responder_assigned(
        society_id: UUID, incident_id: UUID, incident_number: str, responder_type: str, assigned_id: UUID
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: RESPONDER_ASSIGNED - society=%s incident=%s number=%s type=%s assigned=%s",
            society_id,
            incident_id,
            incident_number,
            responder_type,
            assigned_id,
        )

    @staticmethod
    async def emit_incident_escalated(
        society_id: UUID,
        incident_id: UUID,
        incident_number: str,
        escalation_level: int,
        target_role: str,
        reason: str,
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_ESCALATED - society=%s incident=%s number=%s level=%d target_role=%s reason='%s'",
            society_id,
            incident_id,
            incident_number,
            escalation_level,
            target_role,
            reason,
        )

    @staticmethod
    async def emit_incident_contained(society_id: UUID, incident_id: UUID, incident_number: str) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_CONTAINED - society=%s incident=%s number=%s",
            society_id,
            incident_id,
            incident_number,
        )

    @staticmethod
    async def emit_incident_resolved(
        society_id: UUID, incident_id: UUID, incident_number: str, resolver_id: UUID
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_RESOLVED - society=%s incident=%s number=%s resolver=%s",
            society_id,
            incident_id,
            incident_number,
            resolver_id,
        )

    @staticmethod
    async def emit_incident_closed(
        society_id: UUID, incident_id: UUID, incident_number: str, closed_by_id: UUID
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_CLOSED - society=%s incident=%s number=%s closed_by=%s",
            society_id,
            incident_id,
            incident_number,
            closed_by_id,
        )

    @staticmethod
    async def emit_incident_override_applied(
        society_id: UUID, incident_id: UUID, incident_number: str, overridden_by_id: UUID, reason: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: INCIDENT_OVERRIDE_APPLIED - society=%s incident=%s number=%s overridden_by=%s reason='%s'",
            society_id,
            incident_id,
            incident_number,
            overridden_by_id,
            reason,
        )

    @staticmethod
    async def emit_work_order_required(society_id: UUID, incident_id: UUID, incident_number: str) -> None:
        logger.info(
            "DOMAIN_EVENT: WORK_ORDER_REQUIRED - society=%s incident=%s number=%s",
            society_id,
            incident_id,
            incident_number,
        )

    @staticmethod
    async def emit_governance_review_required(
        society_id: UUID, incident_id: UUID, incident_number: str
    ) -> None:
        logger.info(
            "DOMAIN_EVENT: GOVERNANCE_REVIEW_REQUIRED - society=%s incident=%s number=%s",
            society_id,
            incident_id,
            incident_number,
        )
