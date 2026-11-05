"""Phase 19 Incident Management Core REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.incidents.exceptions import (
    IncidentError,
    IncidentNotFoundError,
    InvalidIncidentStateError,
    VoiceDurationExceededError,
)
from apps.api.src.incidents.incident_service import IncidentService
from apps.api.src.incidents.schemas import (
    IncidentAcknowledgementCreate,
    IncidentAcknowledgementResponse,
    IncidentActionCreate,
    IncidentActionResponse,
    IncidentActionUpdate,
    IncidentAssignmentCreate,
    IncidentAssignmentResponse,
    IncidentAttachmentCreate,
    IncidentAttachmentResponse,
    IncidentCreate,
    IncidentEscalationCreate,
    IncidentEscalationResponse,
    IncidentOverrideRequest,
    IncidentResponse,
    IncidentTriageRequest,
    PresignedUploadUrlRequest,
    PresignedUploadUrlResponse,
)

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.post("/report", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def report_incident(
    request: Request,
    data: IncidentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.report")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "RESIDENT")
        incident = await service.report_incident(
            society_id=society_id,
            reporter_id=current_user.id,
            reporter_role=user_role,
            data=data,
        )
        return incident
    except VoiceDurationExceededError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
    except IncidentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    request: Request,
    incident_status: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    category_id: UUID | None = Query(None),
    reported_by_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.view")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    incidents = await service.list_incidents(
        society_id=society_id,
        status=incident_status,
        severity=severity,
        category_id=category_id,
        reported_by_id=reported_by_id,
        limit=limit,
        offset=offset,
    )
    return incidents


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    request: Request,
    incident_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.view")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        return await service.get_incident(society_id, incident_id)
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/triage", response_model=IncidentResponse)
async def triage_incident(
    request: Request,
    incident_id: UUID,
    data: IncidentTriageRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.triage")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "STAFF")
        return await service.triage_incident(
            society_id=society_id,
            incident_id=incident_id,
            triaged_by_id=current_user.id,
            triaged_by_role=user_role,
            data=data,
        )
    except InvalidIncidentStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/acknowledge", response_model=IncidentAcknowledgementResponse)
async def acknowledge_incident(
    request: Request,
    incident_id: UUID,
    data: IncidentAcknowledgementCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.acknowledge")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        return await service.acknowledge_incident(
            society_id=society_id,
            incident_id=incident_id,
            responder_id=current_user.id,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/assign", response_model=IncidentAssignmentResponse)
async def assign_responder(
    request: Request,
    incident_id: UUID,
    data: IncidentAssignmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.assign")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "ADMIN")
        return await service.assign_responder(
            society_id=society_id,
            incident_id=incident_id,
            assigned_by_id=current_user.id,
            assigned_by_role=user_role,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/escalate", response_model=IncidentEscalationResponse)
async def escalate_incident(
    request: Request,
    incident_id: UUID,
    data: IncidentEscalationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.escalate")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "RESPONDER")
        return await service.escalate_incident(
            society_id=society_id,
            incident_id=incident_id,
            triggered_by_id=current_user.id,
            triggered_by_role=user_role,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/contain", response_model=IncidentResponse)
async def contain_hazard(
    request: Request,
    incident_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.respond")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "RESPONDER")
        return await service.contain_hazard(
            society_id=society_id,
            incident_id=incident_id,
            actor_id=current_user.id,
            actor_role=user_role,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    request: Request,
    incident_id: UUID,
    reason: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.resolve")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "STAFF")
        return await service.resolve_incident(
            society_id=society_id,
            incident_id=incident_id,
            resolver_id=current_user.id,
            resolver_role=user_role,
            reason=reason,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/close", response_model=IncidentResponse)
async def close_incident(
    request: Request,
    incident_id: UUID,
    reason: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.close")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "ADMIN")
        return await service.close_incident(
            society_id=society_id,
            incident_id=incident_id,
            closed_by_id=current_user.id,
            closed_by_role=user_role,
            reason=reason,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/override", response_model=IncidentResponse)
async def apply_administrative_override(
    request: Request,
    incident_id: UUID,
    data: IncidentOverrideRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.override")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "ADMIN")
        return await service.apply_administrative_override(
            society_id=society_id,
            incident_id=incident_id,
            overridden_by_id=current_user.id,
            overridden_by_role=user_role,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post(
    "/{incident_id}/actions", response_model=IncidentActionResponse, status_code=status.HTTP_201_CREATED
)
async def create_action(
    request: Request,
    incident_id: UUID,
    data: IncidentActionCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.action.create")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        return await service.create_action(
            society_id=society_id,
            incident_id=incident_id,
            created_by_id=current_user.id,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.put("/actions/{action_id}", response_model=IncidentActionResponse)
async def update_action(
    request: Request,
    action_id: UUID,
    data: IncidentActionUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.action.update")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        return await service.update_action(
            society_id=society_id,
            action_id=action_id,
            updated_by_id=current_user.id,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{incident_id}/attachments/presigned-url", response_model=PresignedUploadUrlResponse)
async def generate_presigned_upload_url(
    request: Request,
    incident_id: UUID,
    data: PresignedUploadUrlRequest,
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.report")),
):
    society_id: UUID = request.state.tenant_id
    if data.duration_seconds and data.duration_seconds > 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voice note duration exceeds maximum allowed server limit (60 seconds)",
        )
    storage_path = f"societies/{society_id}/incidents/{incident_id}/{data.file_size_bytes}_{data.file_name}"
    upload_url = f"https://storage.societysphere.internal/{storage_path}?upload_token=mock"
    return PresignedUploadUrlResponse(
        upload_url=upload_url, storage_path=storage_path, expires_in_seconds=900
    )


@router.post(
    "/{incident_id}/attachments",
    response_model=IncidentAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_attachment(
    request: Request,
    incident_id: UUID,
    data: IncidentAttachmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("incident.report")),
):
    society_id: UUID = request.state.tenant_id
    service = IncidentService(db)
    try:
        user_role = getattr(current_user, "role", "USER")
        return await service.create_attachment(
            society_id=society_id,
            incident_id=incident_id,
            uploaded_by_id=current_user.id,
            uploaded_by_role=user_role,
            data=data,
        )
    except IncidentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
