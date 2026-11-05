"""Aggregating Router for Complaints & Helpdesk Module."""

from fastapi import APIRouter

from apps.api.src.complaints.api.assignments import router as assignments_router
from apps.api.src.complaints.api.attachments import router as attachments_router
from apps.api.src.complaints.api.categories import router as categories_router
from apps.api.src.complaints.api.comments import router as comments_router
from apps.api.src.complaints.api.complaints import router as complaints_router
from apps.api.src.complaints.api.escalations import router as escalations_router
from apps.api.src.complaints.api.sla import router as sla_router
from apps.api.src.complaints.api.status import router as status_router

router = APIRouter()

router.include_router(categories_router)
router.include_router(sla_router)
router.include_router(complaints_router)
router.include_router(status_router)
router.include_router(assignments_router)
router.include_router(comments_router)
router.include_router(attachments_router)
router.include_router(escalations_router)
