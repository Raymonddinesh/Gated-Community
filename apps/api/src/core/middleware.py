"""Security, Correlation ID, and Observability Middleware."""

import logging
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from apps.api.src.core.exceptions import format_error_payload

logger = logging.getLogger("societysphere.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates unique X-Correlation-ID across the request lifecycle."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        header_correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")
        correlation_id = header_correlation_id if header_correlation_id else str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces enterprise security headers on all HTTP responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects incoming payloads exceeding the configured size limit."""

    def __init__(self, app, max_size_bytes: int = 10 * 1024 * 1024) -> None:
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size_bytes:
            req_id = getattr(request.state, "correlation_id", "unknown")
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content=format_error_payload(
                    code="PAYLOAD_TOO_LARGE",
                    message=f"Request entity exceeds maximum permitted limit of {self.max_size_bytes} bytes.",
                    request_id=req_id,
                ),
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs structured metrics for each processed HTTP request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Skip spamming access logs on simple liveness health probes
        if request.url.path not in ("/health/live",):
            log_record = logging.LogRecord(
                name="societysphere.access",
                level=logging.INFO,
                pathname=__file__,
                lineno=0,
                msg=f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
                args=(),
                exc_info=None,
            )
            log_record.correlation_id = correlation_id  # type: ignore
            log_record.http_method = request.method  # type: ignore
            log_record.path = request.url.path  # type: ignore
            log_record.status_code = response.status_code  # type: ignore
            log_record.duration_ms = duration_ms  # type: ignore
            logger.handle(log_record)

        return response
