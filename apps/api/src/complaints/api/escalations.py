"""API Router for Complaint Escalations."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.sla_service import ComplaintSLAService
from apps.api.src.complaints.schemas import (
    ComplaintEscalationCreateRequest,
    ComplaintEscalationResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint Escalations"])


@router.post(
    "/complaints/{complaint_id}/escalate",
    response_model=ComplaintEscalationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def escalate_complaint(
    complaint_id: UUID,
    data: ComplaintEscalationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.escalate")),
) -> ComplaintEscalationResponse:
    """Manually or automatically trigger SLA escalation."""
    service = ComplaintSLAService(db)
    escalation = await service.escalate_complaint(
        society_id=society_id,
        complaint_id=complaint_id,
        triggered_by_user_id=current_user.id,
        data=data,
    )
    return ComplaintEscalationResponse.model_validate(escalation)


@router.get(
    "/complaints/{complaint_id}/escalations",
    response_model=list[ComplaintEscalationResponse],
)
async def list_escalations(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.escalate")),
) -> list[ComplaintEscalationResponse]:
    """List escalation events for a complaint."""
    service = ComplaintSLAService(db)
    escalations = await service.list_escalations(society_id, complaint_id)
    return [ComplaintEscalationResponse.model_validate(e) for e in escalations]
