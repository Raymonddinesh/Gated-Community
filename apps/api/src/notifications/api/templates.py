"""Phase 20 Notification Templates REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.notifications.repositories import TemplateRepository
from apps.api.src.notifications.schemas import (
    NotificationTemplateCreate,
    NotificationTemplateResponse,
    NotificationTemplateVersionCreate,
    NotificationTemplateVersionResponse,
)
from apps.api.src.notifications.services.template_service import TemplateService

router = APIRouter(prefix="/notification-templates", tags=["Notification Templates"])


@router.post("", response_model=NotificationTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: Request,
    data: NotificationTemplateCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.template.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = TemplateService(db)
    vars_list = [v.strip() for v in data.allowlisted_variables.split(",")] if data.allowlisted_variables else None
    template = await service.create_template(
        society_id=society_id,
        code=data.code,
        name=data.name,
        category=data.category.value,
        description=data.description,
        allowlisted_variables=vars_list,
    )
    return NotificationTemplateResponse.model_validate(template)


@router.get("/{code}", response_model=NotificationTemplateResponse)
async def get_template(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    repo = TemplateRepository(db)
    template = await repo.get_template_by_code(society_id, code)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{code}' not found")
    return NotificationTemplateResponse.model_validate(template)


@router.post("/{template_id}/versions", response_model=NotificationTemplateVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    template_id: UUID,
    request: Request,
    data: NotificationTemplateVersionCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.template.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = TemplateService(db)
    version = await service.create_version(
        society_id=society_id,
        template_id=template_id,
        channel=data.channel.value,
        locale=data.locale,
        version=data.version,
        subject_template=data.subject_template,
        body_template=data.body_template,
        is_published=data.is_published,
    )
    return NotificationTemplateVersionResponse.model_validate(version)
