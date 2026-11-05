"""Phase 19 Emergency Contacts REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.incidents.exceptions import IncidentError, IncidentNotFoundError
from apps.api.src.incidents.incident_service import IncidentService
from apps.api.src.incidents.schemas import (
    EmergencyContactCreate,
    EmergencyContactResponse,
    EmergencyContactUpdate,
)

router = APIRouter(prefix="/emergency-contacts", tags=["Emergency Contacts"])


@router.get("", response_model=list[EmergencyContactResponse])
async def list_emergency_contacts(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.contact.view")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    return await service.list_emergency_contacts(society_id)


@router.post("", response_model=EmergencyContactResponse, status_code=status.HTTP_201_CREATED)
async def create_emergency_contact(
    request: Request,
    data: EmergencyContactCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.contact.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        return await service.create_emergency_contact(society_id, data)
    except IncidentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.put("/{contact_id}", response_model=EmergencyContactResponse)
async def update_emergency_contact(
    contact_id: UUID,
    data: EmergencyContactUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.contact.manage")),
):
    service = IncidentService(db)
    try:
        return await service.update_emergency_contact(contact_id, data)
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except IncidentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
