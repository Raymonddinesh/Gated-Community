"""Visitor domain specific exceptions inheriting from AppException."""

import uuid
from typing import Any

from apps.api.src.core.exceptions import AppException


class VisitorDomainError(AppException):
    """Base exception for visitor domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "VISITOR_DOMAIN_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class VisitorNotFoundError(VisitorDomainError):
    """Visitor not found."""

    def __init__(self, visitor_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Visitor with ID '{visitor_id}' not found",
            code="VISITOR_NOT_FOUND",
            status_code=404,
        )


class VisitorInvitationNotFoundError(VisitorDomainError):
    """Visitor invitation not found."""

    def __init__(self, invitation_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Visitor invitation with ID '{invitation_id}' not found",
            code="INVITATION_NOT_FOUND",
            status_code=404,
        )


class VisitorApprovalNotFoundError(VisitorDomainError):
    """Visitor approval record not found."""

    def __init__(self, approval_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Visitor approval record with ID '{approval_id}' not found",
            code="APPROVAL_NOT_FOUND",
            status_code=404,
        )


class VisitorAccessRecordNotFoundError(VisitorDomainError):
    """Visitor access record not found."""

    def __init__(self, record_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Visitor access record with ID '{record_id}' not found",
            code="ACCESS_RECORD_NOT_FOUND",
            status_code=404,
        )


class VisitorDocumentNotFoundError(VisitorDomainError):
    """Visitor document not found."""

    def __init__(self, document_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Visitor document with ID '{document_id}' not found",
            code="DOCUMENT_NOT_FOUND",
            status_code=404,
        )


class InvalidVisitorStatusError(VisitorDomainError):
    """Illegal status transition or invalid status."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="INVALID_VISITOR_STATUS",
            status_code=400,
        )


class VisitorAccessDeniedError(VisitorDomainError):
    """Visitor entry or action denied."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Visitor entry denied: {reason}",
            code="VISITOR_ACCESS_DENIED",
            status_code=403,
            details={"reason": reason},
        )


class VisitorAccessRecordImmutableError(VisitorDomainError):
    """Visitor access records are append-only audit logs and cannot be modified or deleted."""

    def __init__(self) -> None:
        super().__init__(
            message="Visitor access records are immutable audit logs and cannot be deleted",
            code="ACCESS_RECORD_IMMUTABLE",
            status_code=400,
        )


class CrossSocietyVisitorError(VisitorDomainError):
    """Attempted cross-society visitor association or operation."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="CROSS_SOCIETY_VISITOR_ERROR",
            status_code=404,
        )
