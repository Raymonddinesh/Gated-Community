"""Phase 17 Event REST API Router Package."""

from fastapi import APIRouter

from apps.api.src.events.api.attachments import router as attachments_router
from apps.api.src.events.api.attendance import router as attendance_router
from apps.api.src.events.api.events import router as events_router
from apps.api.src.events.api.registrations import router as registrations_router

router = APIRouter()
router.include_router(events_router)
router.include_router(registrations_router)
router.include_router(attendance_router)
router.include_router(attachments_router)
