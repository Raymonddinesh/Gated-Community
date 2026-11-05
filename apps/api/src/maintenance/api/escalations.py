"""API Router for Work Order Escalations."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderEscalation
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.escalation_service import WorkOrderEscalationService
from apps.api.src.maintenance.schemas import WorkOrderEscalationResponse

router = APIRouter(prefix="/work-orders/{work_order_id}/escalate", tags=["Work Order Escalations"])


@router.post("", response_model=WorkOrderEscalationResponse, status_code=status.HTTP_201_CREATED)
async def escalate_work_order(
    work_order_id: uuid.UUID,
    reason: str = Query("SLA target exceeded"),
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderEscalation:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.escalate" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to escalate work order.")

    service = WorkOrderEscalationService(db)
    return await service.trigger_escalation(work_order_id, society_id, reason, current_user)
