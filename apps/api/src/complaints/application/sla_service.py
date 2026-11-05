"""Application Service for SLA Monitoring and Escalations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.domain.concurrency import get_complaint_lock
from apps.api.src.complaints.domain.exceptions import (
    ComplaintEscalationError,
    ComplaintNotFoundError,
)
from apps.api.src.complaints.infrastructure.repositories import (
    ComplaintEscalationRepository,
    ComplaintRepository,
)
from apps.api.src.complaints.schemas import ComplaintEscalationCreateRequest
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.complaint import ComplaintEscalation


class ComplaintSLAService:
    """Service handling SLA escalation checks and resolution tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.complaint_repo = ComplaintRepository(session)
        self.escalation_repo = ComplaintEscalationRepository(session)

    async def escalate_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        triggered_by_user_id: uuid.UUID | None,
        data: ComplaintEscalationCreateRequest,
    ) -> ComplaintEscalation:
        """Trigger an SLA breach escalation. Idempotent against duplicate active escalations."""
        async with get_complaint_lock(complaint_id):
            complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
            if not complaint:
                raise ComplaintNotFoundError(complaint_id)

            active = await self.escalation_repo.get_active_escalation(society_id, complaint_id)
            if active:
                raise ComplaintEscalationError(
                    f"Complaint '{complaint.complaint_number}' already has an active escalation (Level {active.escalation_level})"
                )

            now = datetime.now(UTC)
            escalation = ComplaintEscalation(
                id=uuid.uuid4(),
                society_id=society_id,
                complaint_id=complaint_id,
                escalation_level=1,
                escalation_reason=data.escalation_reason.strip(),
                triggered_by_user_id=triggered_by_user_id,
                target_user_id=data.target_user_id,
                target_role=data.target_role.strip() if data.target_role else "SOCIETY_ADMIN",
                status="ACTIVE",
                triggered_at=now,
                created_at=now,
            )
            await self.escalation_repo.save(escalation)

            # Audit event
            audit = AuditLog(
                id=uuid.uuid4(),
                society_id=society_id,
                actor_user_id=triggered_by_user_id,
                action="complaint.escalated",
                entity_type="ComplaintEscalation",
                entity_id=str(escalation.id),
                after_state={
                    "complaint_number": complaint.complaint_number,
                    "reason": data.escalation_reason,
                    "target_role": data.target_role,
                },
            )
            self.session.add(audit)
            await self.session.flush()

            return escalation

    async def list_escalations(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> list[ComplaintEscalation]:
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)
        return await self.escalation_repo.list_for_complaint(society_id, complaint_id)
