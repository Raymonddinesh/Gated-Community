"""Global Centralized Exception Handling and RFC-Compatible Error Responses."""

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(Exception):
    """Base application exception for domain and infrastructure errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictException(AppException):
    def __init__(
        self, message: str = "Resource conflict detected", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            code="CONFLICT", message=message, status_code=status.HTTP_409_CONFLICT, details=details
        )


class AuthenticationException(AppException):
    def __init__(
        self, message: str = "Authentication required", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            code="AUTHENTICATION_ERROR",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class AuthorizationException(AppException):
    def __init__(self, message: str = "Access forbidden", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="AUTHORIZATION_ERROR",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class TenantContextMismatchException(AppException):
    """Raised when URL society ID and X-Society-ID header hint contradict each other."""

    def __init__(
        self,
        message: str = "Tenant context mismatch: URL resource and X-Society-ID header hint contradict each other.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="TENANT_CONTEXT_MISMATCH",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class TenantContextRequiredException(AppException):
    """Raised when user belongs to multiple societies and no unambiguous tenant context is provided."""

    def __init__(
        self,
        message: str = "Ambiguous tenant context: User holds memberships in multiple societies. Please supply an unambiguous X-Society-ID header or target a specific society URL.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="TENANT_CONTEXT_REQUIRED",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class RateLimitException(AppException):
    def __init__(
        self,
        message: str = "Rate limit exceeded. Please retry later.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="RATE_LIMITED",
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class ServiceUnavailableException(AppException):
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


def format_error_payload(
    code: str, message: str, request_id: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build sanitized, standard error response payload."""
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    request_id = getattr(request.state, "correlation_id", "unknown")
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_payload(exc.code, exc.message, request_id, exc.details),
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors cleanly without exposing internals."""
    request_id = getattr(request.state, "correlation_id", "unknown")
    field_errors = []
    for err in exc.errors():
        field_errors.append(
            {
                "field": ".".join(str(loc) for loc in err.get("loc", []) if loc != "body"),
                "issue": err.get("msg", "Invalid value"),
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=format_error_payload(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            request_id=request_id,
            details={"fields": field_errors},
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard Starlette / FastAPI HTTP exceptions."""
    request_id = getattr(request.state, "correlation_id", "unknown")
    code = "HTTP_ERROR"
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "AUTHENTICATION_ERROR"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "AUTHORIZATION_ERROR"

    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_payload(code=code, message=str(exc.detail), request_id=request_id),
    )


async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler ensuring internal stack traces are never leaked in responses."""
    request_id = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=format_error_payload(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please contact system administrator.",
            request_id=request_id,
        ),
    )
