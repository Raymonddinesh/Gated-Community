"""SocietySphere Backend API Entrypoint."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.src.api.v1.endpoints.health import router as health_router
from apps.api.src.api.v1.router import api_v1_router
from apps.api.src.cache.redis_client import close_redis, init_redis
from apps.api.src.core.config import get_settings
from apps.api.src.core.exceptions import (
    AppException,
    app_exception_handler,
    global_unhandled_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from apps.api.src.core.logging import setup_logging
from apps.api.src.core.middleware import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from apps.api.src.database.session import close_db, init_db
from apps.api.src.events.broker import close_broker, init_broker

settings = get_settings()
setup_logging(log_level=settings.LOG_LEVEL, app_env=settings.APP_ENV)
logger = logging.getLogger("societysphere.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and graceful shutdown lifecycle."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] environment...")

    # Initialize backing infrastructure pools
    await init_db()
    await init_redis()
    await init_broker()

    yield

    logger.info(f"Shutting down {settings.APP_NAME}...")
    await close_broker()
    await close_redis()
    await close_db()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        description="Enterprise Multi-Tenant Apartment Society Management Platform",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG or settings.APP_ENV != "production" else None,
        redoc_url="/redoc" if settings.DEBUG or settings.APP_ENV != "production" else None,
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    # 1. Security & Correlation Middlewares (Executed in reverse order of addition)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=settings.MAX_REQUEST_SIZE_BYTES)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # 2. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Request-ID"],
    )

    # 3. Trusted Host Middleware (in non-test environments)
    if settings.APP_ENV != "testing":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    # 4. Centralized Exception Handlers
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, global_unhandled_exception_handler)

    # 5. Root Health Probes
    app.include_router(health_router)

    # 6. Versioned API Router (/api/v1)
    app.include_router(api_v1_router, prefix=settings.API_PREFIX)

    return app


app = create_app()
