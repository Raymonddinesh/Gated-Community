"""Application Service for Complaint Status Transitions, Resolutions, and Reopenings."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.domain.concurrency import get_complaint_lock
from apps.api.src.complaints.domain.exceptions import (
    ComplaintNotFoundError,
)
from apps.api.src.complaints.domain.state_machine import validate_complaint_status_transition
from apps.api.src.complaints.infrastructure.repositories import (
    ComplaintRepository,
    ComplaintResolutionRepository,
    ComplaintStatusHistoryRepository,
)
from apps.api.src.complaints.schemas import ComplaintResolutionCreateRequest
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.complaint import (
    Complaint,
    ComplaintResolution,
    ComplaintStatusHistory,
)


class ComplaintStatusService:
    """Service handling status transitions, resolutions, reopenings, and audit histories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.complaint_repo = ComplaintRepository(session)
        self.resolution_repo = ComplaintResolutionRepository(session)
        self.history_repo = ComplaintStatusHistoryRepository(session)

    async def transition_status(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        target_status: str,
        reason: str | None = None,
        resolution_data: ComplaintResolutionCreateRequest | None = None,
    ) -> Complaint:
        """Perform a thread-safe, deterministic status transition with audit logging."""
        async with get_complaint_lock(complaint_id):
            complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
            if not complaint:
                raise ComplaintNotFoundError(complaint_id)

            from_status = complaint.status
            validate_complaint_status_transition(from_status, target_status)

            now = datetime.now(UTC)

            # Update status timestamps
            if target_status == "ACKNOWLEDGED" and not complaint.acknowledged_at:
                complaint.acknowledged_at = now
            elif target_status == "RESOLVED":
                complaint.resolved_at = now
                if resolution_data:
                    complaint.resolution_summary = resolution_data.resolution_summary
                    resolution = ComplaintResolution(
                        id=uuid.uuid4(),
                        society_id=society_id,
                        complaint_id=complaint_id,
                        resolved_by_user_id=actor_user_id,
                        resolution_summary=resolution_data.resolution_summary.strip(),
                        resolution_code=resolution_data.resolution_code.strip()
                        if resolution_data.resolution_code
                        else None,
                        resolved_at=now,
                        created_at=now,
                    )
                    await self.resolution_repo.save(resolution)
            elif target_status == "CLOSED":
                complaint.closed_at = now
            elif target_status == "REOPENED":
                complaint.reopened_at = now
            elif target_status == "CANCELLED":
                complaint.cancelled_at = now

            complaint.status = target_status
            complaint.updated_at = now
            await self.complaint_repo.save(complaint)

            # Record Status History
            history = ComplaintStatusHistory(
                id=uuid.uuid4(),
                society_id=society_id,
                complaint_id=complaint_id,
                actor_user_id=actor_user_id,
                from_status=from_status,
                to_status=target_status,
                reason=reason.strip() if reason else f"Transition to {target_status}",
                created_at=now,
            )
            await self.history_repo.save(history)

            # Audit log
            audit = AuditLog(
                id=uuid.uuid4(),
                society_id=society_id,
                actor_user_id=actor_user_id,
                action="complaint.status_changed",
                entity_type="Complaint",
                entity_id=str(complaint_id),
                after_state={
                    "complaint_number": complaint.complaint_number,
                    "from_status": from_status,
                    "to_status": target_status,
                    "reason": reason,
                },
            )
            self.session.add(audit)
            await self.session.flush()

            return complaint

    async def get_history(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> list[ComplaintStatusHistory]:
        return await self.history_repo.get_history(society_id, complaint_id)

    async def get_resolution(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> ComplaintResolution | None:
        return await self.resolution_repo.get_for_complaint(society_id, complaint_id)
