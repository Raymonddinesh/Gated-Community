"""Phase 18 Governance REST API Router Package."""

from fastapi import APIRouter

from apps.api.src.governance.api.action_items import router as action_items_router
from apps.api.src.governance.api.attachments import router as attachments_router
from apps.api.src.governance.api.committees import router as committees_router
from apps.api.src.governance.api.meetings import router as meetings_router
from apps.api.src.governance.api.minutes import router as minutes_router
from apps.api.src.governance.api.resolutions import router as resolutions_router

router = APIRouter()
router.include_router(committees_router)
router.include_router(meetings_router)
router.include_router(resolutions_router)
router.include_router(minutes_router)
router.include_router(action_items_router)
router.include_router(attachments_router)
