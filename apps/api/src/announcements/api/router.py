"""Main Router for Announcements & Communications Module."""

from fastapi import APIRouter

from apps.api.src.announcements.api.announcements import router as announcements_router

router = APIRouter(tags=["Announcements & Communications"])

router.include_router(announcements_router)
