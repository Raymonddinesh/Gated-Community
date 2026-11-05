"""API Version Information Endpoint."""

from fastapi import APIRouter

from apps.api.src.core.config import get_settings

router = APIRouter(tags=["System"])


@router.get("/version")
async def get_version_info() -> dict[str, str]:
    """Retrieve API versioning and runtime metadata."""
    settings = get_settings()
    return {
        "app_name": settings.APP_NAME,
        "api_version": "v1",
        "release": "0.1.0-alpha",
        "environment": settings.APP_ENV,
    }
