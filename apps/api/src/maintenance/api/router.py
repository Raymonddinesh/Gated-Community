"""Central API Router for Maintenance & Work Order Management Domain."""

from fastapi import APIRouter

from apps.api.src.maintenance.api.assignments import router as assignments_router
from apps.api.src.maintenance.api.attachments import router as attachments_router
from apps.api.src.maintenance.api.categories import router as categories_router
from apps.api.src.maintenance.api.comments import router as comments_router
from apps.api.src.maintenance.api.escalations import router as escalations_router
from apps.api.src.maintenance.api.materials import router as materials_router
from apps.api.src.maintenance.api.resolutions import router as resolutions_router
from apps.api.src.maintenance.api.work_orders import router as work_orders_router

router = APIRouter(prefix="/maintenance", tags=["Maintenance Management"])

router.include_router(categories_router)
router.include_router(work_orders_router)
router.include_router(assignments_router)
router.include_router(comments_router)
router.include_router(attachments_router)
router.include_router(materials_router)
router.include_router(resolutions_router)
router.include_router(escalations_router)
