"""Phase 21E.4C — SaaS Credit Note Domain Exceptions.

Provides explicit, domain-specific exception types for all failure modes in the
Credit Note lifecycle, eligibility checks, tax snapshot verifications, and balance adjustments.
Inherits from the core SocietySphere AppException hierarchy.
"""

from typing import Any
from uuid import UUID

from apps.api.src.core.exceptions import AppException


class CreditNoteDomainException(AppException):
    """Base exception for all SaaS credit note domain and lifecycle errors."""

    def __init__(
        self,
        message: str,
        code: str = "CREDIT_NOTE_DOMAIN_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class CreditNoteNotFoundException(CreditNoteDomainException):
    """Raised when querying a credit note ID that does not exist in the tenant scope."""

    def __init__(self, credit_note_id: UUID) -> None:
        super().__init__(
            code="CREDIT_NOTE_NOT_FOUND",
            message=f"Credit note {credit_note_id} not found in current tenant scope.",
            status_code=404,
            details={"credit_note_id": str(credit_note_id)},
        )
        self.credit_note_id = credit_note_id


class InvalidCreditNoteStateException(CreditNoteDomainException):
    """Raised when an operation is prohibited for the credit note's current status."""

    def __init__(self, current_status: str, target_status: str, reason: str) -> None:
        super().__init__(
            code="INVALID_CREDIT_NOTE_STATE",
            message=(
                f"Invalid credit note transition from '{current_status}' to '{target_status}'. "
                f"Reason: {reason}"
            ),
            status_code=400,
            details={
                "current_status": current_status,
                "target_status": target_status,
                "reason": reason,
            },
        )
        self.current_status = current_status
        self.target_status = target_status
        self.reason = reason


class CreditNoteInvoiceNotEligibleException(CreditNoteDomainException):
    """Raised when attempting to issue a credit note against an ineligible invoice (e.g. DRAFT or VOID)."""

    def __init__(self, invoice_id: UUID, invoice_status: str, reason: str) -> None:
        super().__init__(
            code="INVOICE_NOT_ELIGIBLE",
            message=(
                f"Invoice {invoice_id} with status '{invoice_status}' is not eligible "
                f"for credit note issuance. Reason: {reason}"
            ),
            status_code=400,
            details={
                "invoice_id": str(invoice_id),
                "invoice_status": invoice_status,
                "reason": reason,
            },
        )
        self.invoice_id = invoice_id
        self.invoice_status = invoice_status


class CreditNoteExceedsEligibleBalanceException(CreditNoteDomainException):
    """Raised when the requested credit amount exceeds the remaining eligible invoice balance."""

    def __init__(self, invoice_id: UUID, requested_amount: str, eligible_balance: str) -> None:
        super().__init__(
            code="EXCEEDS_ELIGIBLE_BALANCE",
            message=(
                f"Credit note amount ₹{requested_amount} exceeds eligible remaining invoice balance "
                f"₹{eligible_balance} on invoice {invoice_id}."
            ),
            status_code=422,
            details={
                "invoice_id": str(invoice_id),
                "requested_amount": requested_amount,
                "eligible_balance": eligible_balance,
            },
        )
        self.invoice_id = invoice_id
        self.requested_amount = requested_amount
        self.eligible_balance = eligible_balance


class CreditNoteItemExceedsLineEligibilityException(CreditNoteDomainException):
    """Raised when a partial credit note item exceeds the eligible value of the target invoice item."""

    def __init__(
        self,
        invoice_item_id: UUID,
        requested_amount: str,
        eligible_amount: str,
    ) -> None:
        super().__init__(
            code="ITEM_EXCEEDS_LINE_ELIGIBILITY",
            message=(
                f"Line credit amount ₹{requested_amount} exceeds line eligible amount ₹{eligible_amount} "
                f"on invoice item {invoice_item_id}."
            ),
            status_code=422,
            details={
                "invoice_item_id": str(invoice_item_id),
                "requested_amount": requested_amount,
                "eligible_amount": eligible_amount,
            },
        )
        self.invoice_item_id = invoice_item_id
        self.requested_amount = requested_amount
        self.eligible_amount = eligible_amount


class CreditNoteValidationException(CreditNoteDomainException):
    """Raised when credit note payload fails domain validation rules."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            code="CREDIT_NOTE_VALIDATION_ERROR",
            message=f"Credit note validation failed: {reason}",
            status_code=422,
            details={"reason": reason},
        )


class CreditNotePermissionDeniedException(CreditNoteDomainException):
    """Raised when tenant context or role authorization is violated."""

    def __init__(self, reason: str = "Access to credit note denied for tenant/role context.") -> None:
        super().__init__(
            code="CREDIT_NOTE_PERMISSION_DENIED",
            message=reason,
            status_code=403,
            details={"reason": reason},
        )


class CreditNoteTaxSnapshotNotFoundException(CreditNoteDomainException):
    """Raised when the historical tax snapshot for the credit note or original invoice cannot be located."""

    def __init__(self, entity_id: UUID, entity_type: str = "INVOICE") -> None:
        super().__init__(
            code="TAX_SNAPSHOT_NOT_FOUND",
            message=(
                f"Immutable tax snapshot for {entity_type} {entity_id} not found in audit logs. "
                "Credit note calculations require a valid historical snapshot."
            ),
            status_code=404,
            details={"entity_id": str(entity_id), "entity_type": entity_type},
        )
        self.entity_id = entity_id
        self.entity_type = entity_type


class CreditNoteTaxSnapshotTamperedException(CreditNoteDomainException):
    """Raised when cryptographic SHA-256 digest verification fails on a retrieved tax snapshot."""

    def __init__(self, snapshot_id: UUID, stored_hash: str, computed_hash: str) -> None:
        super().__init__(
            code="TAX_SNAPSHOT_TAMPERED",
            message=(
                f"Tax snapshot {snapshot_id} integrity verification failed! "
                f"Stored hash '{stored_hash}' does not match computed hash '{computed_hash}'. "
                "Issuance rejected to prevent statutory and accounting corruption."
            ),
            status_code=409,
            details={
                "snapshot_id": str(snapshot_id),
                "stored_hash": stored_hash,
                "computed_hash": computed_hash,
            },
        )
        self.snapshot_id = snapshot_id
        self.stored_hash = stored_hash
        self.computed_hash = computed_hash


class CreditNoteSequenceExhaustedException(CreditNoteDomainException):
    """Raised if the 5-digit credit note sequence overflows for a financial year."""

    def __init__(self, fiscal_year: str, reason: str = "Sequence limit exceeded (> 99999).") -> None:
        super().__init__(
            code="SEQUENCE_EXHAUSTED",
            message=f"Credit note sequence counter for fiscal year '{fiscal_year}' failed: {reason}",
            status_code=500,
            details={"fiscal_year": fiscal_year, "reason": reason},
        )
        self.fiscal_year = fiscal_year
