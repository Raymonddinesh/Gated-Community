"""API Endpoints for Resident Visitor Approvals."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.visitors.application.visitor_service import VisitorService
from apps.api.src.visitors.schemas import (
    VisitorApprovalDecisionRequest,
    VisitorApprovalResponse,
)

router = APIRouter(tags=["Visitor Approvals"])


@router.post("/visitors/approvals/{approval_id}/decision", response_model=VisitorApprovalResponse)
async def decide_approval(
    approval_id: UUID,
    data: VisitorApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.approve")),
) -> VisitorApprovalResponse:
    """Resident approves or rejects a pending visitor entry request."""
    service = VisitorService(db)
    approval = await service.decide_approval(society_id, approval_id, current_user.id, data)
    return VisitorApprovalResponse.model_validate(approval)
