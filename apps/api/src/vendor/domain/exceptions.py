"""Vendor Domain Exceptions."""

from typing import Any

from fastapi import status

from apps.api.src.core.exceptions import (
    AppException,
    AuthorizationException,
    ConflictException,
    NotFoundException,
)


class VendorException(AppException):
    """Base exception for Vendor domain."""

    def __init__(
        self,
        message: str,
        code: str = "VENDOR_ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class VendorNotFoundException(NotFoundException, VendorException):
    def __init__(self, vendor_id: str):
        super().__init__(message=f"Vendor profile '{vendor_id}' not found.")


class VendorCategoryNotFoundException(NotFoundException, VendorException):
    def __init__(self, category_id: str):
        super().__init__(message=f"Vendor category '{category_id}' not found.")


class VendorDuplicateCodeException(ConflictException, VendorException):
    def __init__(self, code: str):
        super().__init__(message=f"Vendor code '{code}' already exists in this society.")


class VendorDuplicateCategoryCodeException(ConflictException, VendorException):
    def __init__(self, code: str):
        super().__init__(message=f"Vendor category code '{code}' already exists in this society.")


class VendorInvalidStatusTransitionException(VendorException):
    def __init__(self, current_status: str, target_status: str, reason: str | None = None):
        msg = f"Invalid vendor status transition from '{current_status}' to '{target_status}'."
        if reason:
            msg += f" {reason}"
        super().__init__(message=msg, code="INVALID_STATUS_TRANSITION")


class VendorNotActiveForAssignmentException(VendorException):
    def __init__(self, vendor_id: str, status_val: str):
        super().__init__(
            message=f"Vendor '{vendor_id}' cannot be assigned to work order because status is '{status_val}' (must be ACTIVE).",
            code="VENDOR_NOT_ACTIVE",
        )


class VendorDocumentNotFoundException(NotFoundException, VendorException):
    def __init__(self, document_id: str):
        super().__init__(message=f"Vendor document '{document_id}' not found.")


class VendorAccessDeniedException(AuthorizationException, VendorException):
    def __init__(self, message: str = "Access denied to vendor resource."):
        super().__init__(message=message)
