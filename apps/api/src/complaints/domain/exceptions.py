"""Domain Exceptions for Complaints & Helpdesk Domain."""

import uuid
from typing import Any

from apps.api.src.core.exceptions import AppException


class ComplaintDomainError(AppException):
    """Base exception for complaint domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "COMPLAINT_DOMAIN_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class ComplaintNotFoundError(ComplaintDomainError):
    """Raised when a complaint is not found in the target society."""

    def __init__(self, complaint_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Complaint with ID '{complaint_id}' not found",
            code="COMPLAINT_NOT_FOUND",
            status_code=404,
        )


class ComplaintCategoryNotFoundError(ComplaintDomainError):
    """Raised when a complaint category is not found."""

    def __init__(self, category_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Complaint category with ID '{category_id}' not found",
            code="COMPLAINT_CATEGORY_NOT_FOUND",
            status_code=404,
        )


class ComplaintSubcategoryNotFoundError(ComplaintDomainError):
    """Raised when a complaint subcategory is not found."""

    def __init__(self, subcategory_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Complaint subcategory with ID '{subcategory_id}' not found",
            code="COMPLAINT_SUBCATEGORY_NOT_FOUND",
            status_code=404,
        )


class ComplaintSLAPolicyNotFoundError(ComplaintDomainError):
    """Raised when an SLA policy is not found."""

    def __init__(self, policy_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Complaint SLA policy with ID '{policy_id}' not found",
            code="COMPLAINT_SLA_POLICY_NOT_FOUND",
            status_code=404,
        )


class InvalidComplaintStatusTransitionError(ComplaintDomainError):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, from_status: str | None, to_status: str) -> None:
        super().__init__(
            message=f"Invalid status transition from '{from_status}' to '{to_status}'",
            code="INVALID_STATUS_TRANSITION",
            status_code=400,
        )


class CrossSocietyComplaintError(ComplaintDomainError):
    """Raised when an entity belongs to a different society."""

    def __init__(self, message: str = "Cross-society complaint relationship detected") -> None:
        super().__init__(
            message=message,
            code="CROSS_SOCIETY_COMPLAINT_ERROR",
            status_code=400,
        )


class ComplaintAccessDeniedError(ComplaintDomainError):
    """Raised when a user attempts an unauthorized complaint operation."""

    def __init__(self, message: str = "Access denied to complaint resource") -> None:
        super().__init__(
            message=message,
            code="COMPLAINT_ACCESS_DENIED",
            status_code=403,
        )


class ComplaintCommentAccessDeniedError(ComplaintDomainError):
    """Raised when a resident attempts to post or view internal comments."""

    def __init__(
        self, message: str = "Internal comments are restricted to authorized helpdesk users"
    ) -> None:
        super().__init__(
            message=message,
            code="COMPLAINT_COMMENT_ACCESS_DENIED",
            status_code=403,
        )


class ComplaintAttachmentError(ComplaintDomainError):
    """Raised when attachment validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="COMPLAINT_ATTACHMENT_ERROR",
            status_code=400,
        )


class ComplaintSLAError(ComplaintDomainError):
    """Raised when SLA calculations fail."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="COMPLAINT_SLA_ERROR",
            status_code=400,
        )


class ComplaintEscalationError(ComplaintDomainError):
    """Raised when an invalid escalation state operation occurs."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="COMPLAINT_ESCALATION_ERROR",
            status_code=400,
        )
