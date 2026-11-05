"""API Router for Complaint Assignments."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.assignment_service import ComplaintAssignmentService
from apps.api.src.complaints.schemas import (
    ComplaintAssignmentResponse,
    ComplaintAssignRequest,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint Assignments"])


@router.post(
    "/complaints/{complaint_id}/assign",
    response_model=ComplaintAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_complaint(
    complaint_id: UUID,
    data: ComplaintAssignRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.assign")),
) -> ComplaintAssignmentResponse:
    """Assign complaint to a user or team."""
    service = ComplaintAssignmentService(db)
    assignment = await service.assign_complaint(
        society_id=society_id,
        complaint_id=complaint_id,
        assigned_by_user_id=current_user.id,
        data=data,
    )
    return ComplaintAssignmentResponse.model_validate(assignment)
