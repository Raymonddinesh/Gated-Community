"""Phase 19 Incident Categories REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.incidents.exceptions import IncidentError
from apps.api.src.incidents.incident_service import IncidentService
from apps.api.src.incidents.schemas import IncidentCategoryCreate, IncidentCategoryResponse

router = APIRouter(prefix="/incidents/categories", tags=["Incident Categories"])


@router.get("", response_model=list[IncidentCategoryResponse])
async def list_categories(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.contact.view")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    return await service.list_categories(society_id)


@router.post("", response_model=IncidentCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: Request,
    data: IncidentCategoryCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.contact.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        return await service.create_category(society_id, data)
    except IncidentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
