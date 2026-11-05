"""Application Service for Complaint Assignments."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.domain.concurrency import get_complaint_lock
from apps.api.src.complaints.domain.exceptions import (
    ComplaintNotFoundError,
    CrossSocietyComplaintError,
)
from apps.api.src.complaints.infrastructure.repositories import (
    ComplaintAssignmentRepository,
    ComplaintRepository,
)
from apps.api.src.complaints.schemas import ComplaintAssignRequest
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.complaint import ComplaintAssignment
from apps.api.src.database.models.membership import UserSocietyMembership


class ComplaintAssignmentService:
    """Service managing complaint assignments and target validation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.complaint_repo = ComplaintRepository(session)
        self.assignment_repo = ComplaintAssignmentRepository(session)

    async def assign_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        assigned_by_user_id: uuid.UUID,
        data: ComplaintAssignRequest,
    ) -> ComplaintAssignment:
        """Assign complaint to a user or team within the same society."""
        async with get_complaint_lock(complaint_id):
            complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
            if not complaint:
                raise ComplaintNotFoundError(complaint_id)

            # Validate assigned_to_user_id belongs to same society if provided
            if data.assigned_to_user_id:
                mem_res = await self.session.execute(
                    select(UserSocietyMembership).where(
                        UserSocietyMembership.user_id == data.assigned_to_user_id,
                        UserSocietyMembership.society_id == society_id,
                        UserSocietyMembership.membership_status == "ACTIVE",
                    )
                )
                if not mem_res.scalar_one_or_none():
                    from apps.api.src.database.repositories.authorization_repository import (
                        AuthorizationRepository,
                    )

                    authz_repo = AuthorizationRepository(self.session)
                    roles = await authz_repo.get_user_roles(data.assigned_to_user_id, None)
                    if not any(r.code == "SUPER_ADMIN" for r in roles):
                        raise CrossSocietyComplaintError(
                            f"Assigned user '{data.assigned_to_user_id}' does not have active membership in this society"
                        )

            now = datetime.now(UTC)

            # Deactivate previous assignments
            await self.assignment_repo.deactivate_previous_assignments(society_id, complaint_id)

            assignment = ComplaintAssignment(
                id=uuid.uuid4(),
                society_id=society_id,
                complaint_id=complaint_id,
                assigned_by_user_id=assigned_by_user_id,
                target_type=data.target_type.value,
                assigned_to_user_id=data.assigned_to_user_id,
                assigned_to_role=data.assigned_to_role.strip() if data.assigned_to_role else None,
                assigned_to_team=data.assigned_to_team.strip() if data.assigned_to_team else None,
                assigned_at=now,
                notes=data.notes.strip() if data.notes else None,
                is_current=True,
                created_at=now,
            )
            await self.assignment_repo.save(assignment)

            # Update complaint assignment metadata and status if OPEN/ACKNOWLEDGED
            complaint.assigned_at = now
            if complaint.status in ("OPEN", "ACKNOWLEDGED"):
                complaint.status = "ASSIGNED"
            complaint.updated_at = now
            await self.complaint_repo.save(complaint)

            # Audit log
            audit = AuditLog(
                id=uuid.uuid4(),
                society_id=society_id,
                actor_user_id=assigned_by_user_id,
                action="complaint.assigned",
                entity_type="Complaint",
                entity_id=str(complaint_id),
                after_state={
                    "assigned_to_user_id": str(data.assigned_to_user_id)
                    if data.assigned_to_user_id
                    else None,
                    "target_type": data.target_type.value,
                    "assigned_to_team": data.assigned_to_team,
                },
            )
            self.session.add(audit)
            await self.session.flush()

            return assignment
