"""Aggregate API Router for Visitor & Security Management Domain."""

from fastapi import APIRouter

from apps.api.src.visitors.api.access import router as access_router
from apps.api.src.visitors.api.approvals import router as approvals_router
from apps.api.src.visitors.api.documents import router as documents_router
from apps.api.src.visitors.api.gate import router as gate_router
from apps.api.src.visitors.api.invitations import router as invitations_router
from apps.api.src.visitors.api.visitors import router as visitors_router

router = APIRouter()

router.include_router(visitors_router)
router.include_router(invitations_router)
router.include_router(approvals_router)
router.include_router(gate_router)
router.include_router(access_router)
router.include_router(documents_router)
