"""Phase 21E.4A — Indian GST Tax Engine Domain Exceptions.

Provides specialized domain exceptions for GST calculation, place-of-supply resolution,
GSTIN validation, and tax snapshot integrity.
"""

from typing import Any
from uuid import UUID

from fastapi import status

from apps.api.src.core.exceptions import AppException


class TaxDomainException(AppException):
    """Base domain exception for GST tax engine operations."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class InvalidPlaceOfSupplyException(TaxDomainException):
    """Raised when the place of supply cannot be legally or unambiguously determined."""

    def __init__(
        self,
        reason: str,
        supplier_state: str | None = None,
        customer_state: str | None = None,
        customer_gstin: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = details or {}
        merged["reason"] = reason
        if supplier_state:
            merged["supplier_state"] = supplier_state
        if customer_state:
            merged["customer_state"] = customer_state
        if customer_gstin:
            merged["customer_gstin"] = customer_gstin
        super().__init__(
            code="INVALID_PLACE_OF_SUPPLY",
            message=f"Place of supply could not be determined: {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=merged,
        )


class InvalidGSTINException(TaxDomainException):
    """Raised when a GSTIN fails syntactic, structural, or checksum validation."""

    def __init__(
        self,
        gstin: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = details or {}
        merged["gstin"] = gstin
        merged["reason"] = reason
        super().__init__(
            code="INVALID_GSTIN_FORMAT",
            message=f"Invalid GSTIN '{gstin}': {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=merged,
        )


class TaxConfigurationNotFoundException(TaxDomainException):
    """Raised when no active tax rule configuration exists for an SAC code and date."""

    def __init__(
        self,
        sac_code: str,
        transaction_date: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = details or {}
        merged["sac_code"] = sac_code
        if transaction_date:
            merged["transaction_date"] = transaction_date
        super().__init__(
            code="TAX_CONFIG_NOT_FOUND",
            message=f"No active GST tax configuration found for SAC '{sac_code}'.",
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged,
        )


class TaxCalculationException(TaxDomainException):
    """Raised when arithmetic or domain constraint fails during GST tax calculation."""

    def __init__(
        self,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="TAX_CALCULATION_ERROR",
            message=f"GST calculation failed: {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class TaxSnapshotTamperedException(TaxDomainException):
    """Raised when a historical tax snapshot's cryptographic integrity hash fails verification."""

    def __init__(
        self,
        snapshot_id: UUID | str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = details or {}
        merged["snapshot_id"] = str(snapshot_id)
        super().__init__(
            code="TAX_SNAPSHOT_TAMPERED",
            message=f"Cryptographic integrity verification failed for tax snapshot {snapshot_id}.",
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class IncompatibleCreditNoteTaxException(TaxDomainException):
    """Raised when a credit note tax calculation conflicts with the original invoice tax snapshot."""

    def __init__(
        self,
        invoice_id: UUID | str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = details or {}
        merged["invoice_id"] = str(invoice_id)
        merged["reason"] = reason
        super().__init__(
            code="INCOMPATIBLE_CREDIT_NOTE_TAX",
            message=f"Credit note tax calculation is incompatible with invoice {invoice_id}: {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=merged,
        )
