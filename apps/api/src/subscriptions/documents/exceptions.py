"""Phase 21E.4D — Billing Document and Delivery Exceptions Hierarchy."""

import uuid

from apps.api.src.core.exceptions import AppException


class BillingDocumentException(AppException):
    """Base exception for billing document storage, rendering, and delivery operations."""

    def __init__(self, message: str, code: str = "BILLING_DOCUMENT_ERROR", status_code: int = 400) -> None:
        super().__init__(code=code, message=message, status_code=status_code)
        self.code = code


class DraftDocumentAccessDeniedException(BillingDocumentException):
    """Raised when an attempt is made to render, store, or email a DRAFT financial document."""

    def __init__(self, document_type: str, document_id: uuid.UUID, status: str) -> None:
        super().__init__(
            message=f"Cannot generate or deliver document for {document_type} '{document_id}' in '{status}' status. Document must be finalized/issued first.",
            code="DRAFT_DOCUMENT_ACCESS_DENIED",
            status_code=400,
        )
        self.document_type = document_type
        self.document_id = document_id
        self.status = status


class DocumentNotFoundException(BillingDocumentException):
    """Raised when a billing document is not found or inaccessible."""

    def __init__(self, document_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Billing document '{document_id}' was not found.",
            code="DOCUMENT_NOT_FOUND",
            status_code=404,
        )
        self.document_id = str(document_id)


class DocumentAlreadyGeneratedException(BillingDocumentException):
    """Raised when an immutable issued document already exists and regeneration is prohibited."""

    def __init__(self, document_type: str, document_number: str) -> None:
        super().__init__(
            message=f"Document {document_type} '{document_number}' has already been generated and persisted. Silent overwrite prohibited.",
            code="DOCUMENT_ALREADY_EXISTS",
            status_code=409,
        )
        self.document_type = document_type
        self.document_number = document_number


class DocumentStorageException(BillingDocumentException):
    """Raised on object storage upload, retrieval, or presigning errors."""

    def __init__(self, operation: str, storage_key: str, reason: str) -> None:
        super().__init__(
            message=f"Object storage failure during {operation} on '{storage_key}': {reason}",
            code="STORAGE_OPERATION_FAILED",
            status_code=502,
        )
        self.operation = operation
        self.storage_key = storage_key
        self.reason = reason


class DocumentTamperException(BillingDocumentException):
    """Raised when SHA-256 integrity checksum verification fails."""

    def __init__(self, document_id: str, expected_hash: str, actual_hash: str) -> None:
        super().__init__(
            message=f"Document integrity verification failed for '{document_id}'. Expected {expected_hash}, calculated {actual_hash}.",
            code="DOCUMENT_INTEGRITY_TAMPERED",
            status_code=500,
        )
        self.document_id = document_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


class DocumentDeliveryException(BillingDocumentException):
    """Raised when an email delivery provider fails all retry attempts."""

    def __init__(self, delivery_id: uuid.UUID, recipient: str, reason: str) -> None:
        super().__init__(
            message=f"Email delivery '{delivery_id}' to '{recipient}' failed: {reason}",
            code="DELIVERY_FAILED",
            status_code=502,
        )
        self.delivery_id = delivery_id
        self.recipient = recipient
        self.reason = reason


class DocumentPermissionDeniedException(BillingDocumentException):
    """Raised when an authenticated caller attempts cross-tenant document access."""

    def __init__(self, document_id: uuid.UUID, caller_society_id: uuid.UUID | None) -> None:
        super().__init__(
            message=f"Access denied to billing document '{document_id}' for tenant '{caller_society_id}'.",
            code="CROSS_TENANT_ACCESS_DENIED",
            status_code=403,
        )
        self.document_id = document_id
        self.caller_society_id = caller_society_id
