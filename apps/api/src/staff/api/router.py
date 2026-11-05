"""Aggregated Staff API Router."""

from fastapi import APIRouter

from apps.api.src.staff.api.documents import router as documents_router
from apps.api.src.staff.api.profiles import router as profiles_router
from apps.api.src.staff.api.roles import router as roles_router
from apps.api.src.staff.api.teams import router as teams_router

router = APIRouter(prefix="/staff", tags=["Staff & Workforce Management"])

router.include_router(profiles_router)
router.include_router(roles_router)
router.include_router(teams_router)
router.include_router(documents_router)
