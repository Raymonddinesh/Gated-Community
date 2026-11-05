"""API Router for Complaint SLA Policies."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.complaint_service import ComplaintService
from apps.api.src.complaints.schemas import (
    ComplaintSLAPolicyCreateRequest,
    ComplaintSLAPolicyResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint SLA Policies"])


@router.post(
    "/complaint-sla-policies",
    response_model=ComplaintSLAPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sla_policy(
    data: ComplaintSLAPolicyCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.sla.manage")),
) -> ComplaintSLAPolicyResponse:
    """Create a new SLA policy."""
    service = ComplaintService(db)
    policy = await service.create_sla_policy(society_id, data)
    return ComplaintSLAPolicyResponse.model_validate(policy)


@router.get(
    "/complaint-sla-policies",
    response_model=list[ComplaintSLAPolicyResponse],
)
async def list_sla_policies(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.sla.manage")),
) -> list[ComplaintSLAPolicyResponse]:
    """List SLA policies in society."""
    service = ComplaintService(db)
    policies = await service.list_sla_policies(society_id)
    return [ComplaintSLAPolicyResponse.model_validate(p) for p in policies]
