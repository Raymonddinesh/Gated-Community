"""API Endpoints for Visitor Access Records and History."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.visitors.application.access_service import VisitorAccessService
from apps.api.src.visitors.schemas import VisitorAccessRecordResponse

router = APIRouter(tags=["Visitor Access History"])


@router.get("/visitors/access/records", response_model=dict)
async def search_access_records(
    query: str | None = Query(None, description="Search by visitor name, phone, or gate"),
    visitor_id: UUID | None = Query(None),
    unit_id: UUID | None = Query(None),
    access_type: str | None = Query(None),
    gate_identifier: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.access.view")),
) -> dict:
    """Search append-only gate access history records."""
    service = VisitorAccessService(db)
    items, total = await service.search_records(
        society_id=society_id,
        query=query,
        visitor_id=visitor_id,
        unit_id=unit_id,
        access_type=access_type,
        gate_identifier=gate_identifier,
        page=page,
        size=size,
    )
    return {
        "items": [VisitorAccessRecordResponse.model_validate(r) for r in items],
        "total": total,
        "page": page,
        "size": size,
    }
