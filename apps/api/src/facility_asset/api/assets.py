"""Assets API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.facility_asset.asset_service import AssetService
from apps.api.src.facility_asset.document_service import DocumentService
from apps.api.src.facility_asset.maintenance_link_service import MaintenanceLinkService
from apps.api.src.facility_asset.schemas import (
    AssetAssignmentCreate,
    AssetAssignmentHistoryResponse,
    AssetCreate,
    AssetDocumentCreate,
    AssetDocumentResponse,
    AssetListResponse,
    AssetLocationMove,
    AssetLocationResponse,
    AssetMaintenanceLinkCreate,
    AssetMaintenanceLinkResponse,
    AssetResponse,
    AssetStatusHistoryResponse,
    AssetStatusUpdate,
    AssetUpdate,
)

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.post(
    "",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("asset.create"))],
)
async def create_asset(
    payload: AssetCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = AssetService(db)
    return await service.create_asset(society_id, current_user.id, payload)


@router.get(
    "",
    response_model=AssetListResponse,
    dependencies=[Depends(require_permission("asset.view"))],
)
async def list_assets(
    category_id: UUID | None = Query(None),
    facility_id: UUID | None = Query(None),
    status: str | None = Query(None),
    criticality: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = AssetService(db)
    items, total = await service.list_assets(
        society_id,
        category_id=category_id,
        facility_id=facility_id,
        status=status,
        criticality=criticality,
        page=page,
        size=size,
    )
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    has_sensitive = "asset.view_sensitive" in perms

    asset_resps = []
    for a in items:
        r = AssetResponse.model_validate(a)
        if not has_sensitive:
            r.serial_number = None
        asset_resps.append(r)

    return AssetListResponse(
        items=asset_resps,
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    dependencies=[Depends(require_permission("asset.view"))],
)
async def get_asset(
    asset_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = AssetService(db)
    asset = await service.get_asset(society_id, asset_id)
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    resp = AssetResponse.model_validate(asset)
    if "asset.view_sensitive" not in perms:
        resp.serial_number = None
    return resp


@router.patch(
    "/{asset_id}",
    response_model=AssetResponse,
    dependencies=[Depends(require_permission("asset.update"))],
)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = AssetService(db)
    return await service.update_asset(society_id, asset_id, payload)


@router.post(
    "/{asset_id}/status",
    response_model=AssetResponse,
    dependencies=[Depends(require_permission("asset.status.manage"))],
)
async def update_asset_status(
    asset_id: UUID,
    payload: AssetStatusUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = AssetService(db)
    return await service.update_asset_status(society_id, current_user.id, asset_id, payload)


@router.post(
    "/{asset_id}/location",
    response_model=AssetLocationResponse,
    dependencies=[Depends(require_permission("asset.location.manage"))],
)
async def move_asset_location(
    asset_id: UUID,
    payload: AssetLocationMove,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = AssetService(db)
    return await service.move_asset_location(society_id, current_user.id, asset_id, payload)


@router.get(
    "/{asset_id}/locations",
    response_model=list[AssetLocationResponse],
    dependencies=[Depends(require_permission("asset.audit.view"))],
)
async def get_location_history(
    asset_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = AssetService(db)
    return await service.get_location_history(society_id, asset_id)


@router.post(
    "/{asset_id}/assignments",
    response_model=AssetAssignmentHistoryResponse,
    dependencies=[Depends(require_permission("asset.assignment.manage"))],
)
async def assign_asset(
    asset_id: UUID,
    payload: AssetAssignmentCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = AssetService(db)
    return await service.assign_asset(society_id, current_user.id, asset_id, payload)


@router.get(
    "/{asset_id}/assignments",
    response_model=list[AssetAssignmentHistoryResponse],
    dependencies=[Depends(require_permission("asset.audit.view"))],
)
async def get_assignment_history(
    asset_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = AssetService(db)
    return await service.get_assignment_history(society_id, asset_id)


@router.get(
    "/{asset_id}/status-history",
    response_model=list[AssetStatusHistoryResponse],
    dependencies=[Depends(require_permission("asset.audit.view"))],
)
async def get_status_history(
    asset_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = AssetService(db)
    return await service.get_status_history(society_id, asset_id)


@router.post(
    "/{asset_id}/documents",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("asset.document.manage"))],
)
async def add_asset_document(
    asset_id: UUID,
    payload: AssetDocumentCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = DocumentService(db)
    return await service.add_asset_document(society_id, current_user.id, asset_id, payload)


@router.get(
    "/{asset_id}/documents",
    response_model=list[AssetDocumentResponse],
    dependencies=[Depends(require_permission("asset.document.view"))],
)
async def list_asset_documents(
    asset_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = DocumentService(db)
    return await service.list_asset_documents(society_id, asset_id)


@router.post(
    "/{asset_id}/maintenance-links",
    response_model=AssetMaintenanceLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("asset.maintenance.link"))],
)
async def add_asset_maintenance_link(
    asset_id: UUID,
    payload: AssetMaintenanceLinkCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    payload.asset_id = asset_id
    service = MaintenanceLinkService(db)
    return await service.create_link(society_id, current_user.id, payload)


@router.get(
    "/{asset_id}/maintenance-links",
    response_model=list[AssetMaintenanceLinkResponse],
    dependencies=[Depends(require_permission("asset.view"))],
)
async def list_asset_maintenance_links(
    asset_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = MaintenanceLinkService(db)
    return await service.list_by_asset(society_id, asset_id)
