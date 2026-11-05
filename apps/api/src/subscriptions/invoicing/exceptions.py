"""Phase 21E.4B — SaaS Invoice Domain Exceptions."""

from typing import Any
from uuid import UUID

from fastapi import status

from apps.api.src.core.exceptions import AppException


class InvoicingDomainException(AppException):
    """Base domain exception for Phase 21E.4B commercial SaaS invoicing operations."""

    def __init__(
        self,
        message: str,
        code: str = "INVOICING_DOMAIN_ERROR",
        http_status: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=http_status,
            details=details,
        )
        self.http_status = http_status


class InvoiceNotFoundException(InvoicingDomainException):
    """Raised when an invoice is not found in the database or tenant context."""

    def __init__(self, invoice_id: UUID) -> None:
        super().__init__(
            message=f"Platform invoice '{invoice_id}' was not found.",
            code="INVOICE_NOT_FOUND",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"invoice_id": str(invoice_id)},
        )


class InvalidInvoiceStateException(InvoicingDomainException):
    """Raised when an invoice lifecycle state transition is prohibited."""

    def __init__(
        self,
        invoice_id: UUID,
        current_status: str,
        attempted_action: str,
        reason: str | None = None,
    ) -> None:
        msg = f"Cannot {attempted_action} invoice '{invoice_id}' in '{current_status}' status."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(
            message=msg,
            code="INVALID_INVOICE_STATE",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={
                "invoice_id": str(invoice_id),
                "current_status": current_status,
                "attempted_action": attempted_action,
                "reason": reason,
            },
        )


class InvoiceFinalizationException(InvoicingDomainException):
    """Raised when validation fails during DRAFT -> ISSUED invoice finalization."""

    def __init__(self, reason: str, invoice_id: UUID | None = None, details: dict[str, Any] | None = None) -> None:
        det = details or {}
        if invoice_id:
            det["invoice_id"] = str(invoice_id)
        super().__init__(
            message=f"Invoice finalization failed: {reason}",
            code="INVOICE_FINALIZATION_FAILED",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=det,
        )


class InvoicePermissionDeniedException(InvoicingDomainException):
    """Raised when an actor lacks permission to manage or view an invoice."""

    def __init__(self, reason: str = "Insufficient permissions to perform invoice action.") -> None:
        super().__init__(
            message=reason,
            code="INVOICE_PERMISSION_DENIED",
            http_status=status.HTTP_403_FORBIDDEN,
        )


class InvoiceSequenceExhaustedException(InvoicingDomainException):
    """Raised if sequential numbering encounters an irrecoverable sequence error."""

    def __init__(self, fiscal_year: str, reason: str) -> None:
        super().__init__(
            message=f"Invoice sequence allocation error for FY {fiscal_year}: {reason}",
            code="INVOICE_SEQUENCE_ERROR",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"fiscal_year": fiscal_year, "reason": reason},
        )


class InvoiceTaxSnapshotNotFoundException(InvoicingDomainException):
    """Raised when an immutable tax snapshot for an invoice cannot be retrieved."""

    def __init__(self, invoice_id: UUID) -> None:
        super().__init__(
            message=f"Immutable tax snapshot for invoice '{invoice_id}' was not found.",
            code="INVOICE_TAX_SNAPSHOT_NOT_FOUND",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"invoice_id": str(invoice_id)},
        )


class InvoiceTaxSnapshotTamperedException(InvoicingDomainException):
    """Raised when an invoice tax snapshot fails SHA-256 integrity verification."""

    def __init__(self, invoice_id: UUID, reason: str = "Cryptographic integrity hash mismatch.") -> None:
        super().__init__(
            message=f"Tax snapshot for invoice '{invoice_id}' is corrupted or tampered: {reason}",
            code="INVOICE_TAX_SNAPSHOT_TAMPERED",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"invoice_id": str(invoice_id), "reason": reason},
        )
