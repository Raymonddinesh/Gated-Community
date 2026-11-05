"""Phase 18 Governance Attachment REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.governance.exceptions import GovernanceError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import GovernanceAttachmentCreate, GovernanceAttachmentResponse

router = APIRouter(prefix="/governance/attachments", tags=["Governance Attachments"])


@router.post("", response_model=GovernanceAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def create_attachment(
    request: Request,
    data: GovernanceAttachmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.update")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        attachment = await service.create_attachment(society_id, uploaded_by=current_user.id, data=data)
        return attachment
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[GovernanceAttachmentResponse])
async def list_attachments(
    request: Request,
    meeting_id: UUID | None = Query(None),
    resolution_id: UUID | None = Query(None),
    committee_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    attachments = await service.list_attachments(
        society_id=society_id,
        meeting_id=meeting_id,
        resolution_id=resolution_id,
        committee_id=committee_id,
    )
    return attachments
