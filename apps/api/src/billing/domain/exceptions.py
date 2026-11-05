"""Domain-Specific Exceptions for Maintenance Billing."""

from typing import Any

from apps.api.src.core.exceptions import AppException, ConflictException, NotFoundException


class BillingConfigNotFoundException(NotFoundException):
    def __init__(self, society_id: Any) -> None:
        super().__init__(
            message=f"Billing configuration not found for society '{society_id}'.",
            details={"code": "BILLING_CONFIG_NOT_FOUND", "society_id": str(society_id)},
        )


class BillingPeriodNotFoundException(NotFoundException):
    def __init__(self, period_id: Any) -> None:
        super().__init__(
            message=f"Billing period '{period_id}' not found.",
            details={"code": "BILLING_PERIOD_NOT_FOUND", "period_id": str(period_id)},
        )


class BillingPeriodClosedException(AppException):
    def __init__(self, period_code: str) -> None:
        super().__init__(
            code="BILLING_PERIOD_CLOSED",
            message=f"Billing period '{period_code}' is closed or cancelled. Operations are rejected.",
            status_code=400,
            details={"period_code": period_code},
        )


class BillingPeriodOverlapException(ConflictException):
    def __init__(self, period_code: str) -> None:
        super().__init__(
            message=f"A billing period with code '{period_code}' already exists.",
            details={"code": "BILLING_PERIOD_OVERLAP", "period_code": period_code},
        )


class DuplicateInvoiceException(ConflictException):
    def __init__(self, unit_number: str, period_code: str) -> None:
        super().__init__(
            message=f"Invoice for unit '{unit_number}' in period '{period_code}' already exists.",
            details={"code": "DUPLICATE_INVOICE", "unit": unit_number, "period": period_code},
        )


class InvoiceNotFoundException(NotFoundException):
    def __init__(self, invoice_id: Any) -> None:
        super().__init__(
            message=f"Invoice '{invoice_id}' not found.",
            details={"code": "INVOICE_NOT_FOUND", "invoice_id": str(invoice_id)},
        )


class InvoiceImmutableException(AppException):
    def __init__(self, invoice_number: str, status: str) -> None:
        super().__init__(
            code="INVOICE_IMMUTABLE",
            message=f"Invoice '{invoice_number}' is {status} and cannot be modified directly.",
            status_code=400,
            details={"invoice_number": invoice_number, "status": status},
        )


class UndeterminedResponsiblePartyException(AppException):
    def __init__(self, unit_id: Any, reason: str) -> None:
        super().__init__(
            code="UNDETERMINED_RESPONSIBLE_PARTY",
            message=f"Cannot determine financially responsible party for unit '{unit_id}': {reason}",
            status_code=400,
            details={"unit_id": str(unit_id), "reason": reason},
        )


class InvalidChargeRuleException(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="INVALID_CHARGE_RULE",
            message=message,
            status_code=400,
        )


class PaymentNotFoundException(NotFoundException):
    def __init__(self, payment_id: Any) -> None:
        super().__init__(
            message=f"Payment '{payment_id}' not found.",
            details={"code": "PAYMENT_NOT_FOUND", "payment_id": str(payment_id)},
        )


class PaymentOverAllocationException(AppException):
    def __init__(self, requested: str, available: str) -> None:
        super().__init__(
            code="PAYMENT_OVER_ALLOCATION",
            message=f"Cannot allocate {requested}; only {available} unallocated funds remain.",
            status_code=400,
            details={"requested": requested, "available": available},
        )


class CrossTenantBillingException(AppException):
    def __init__(self, message: str = "Cross-tenant billing operation rejected.") -> None:
        super().__init__(
            code="CROSS_TENANT_BILLING_ACCESS",
            message=message,
            status_code=403,
        )


class BillingAccountingIntegrationException(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="BILLING_ACCOUNTING_ERROR",
            message=message,
            status_code=400,
            details=details,
        )


class InvalidAdjustmentException(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="INVALID_ADJUSTMENT",
            message=message,
            status_code=400,
        )


class DuplicateNoteException(ConflictException):
    def __init__(self, note_number: str) -> None:
        super().__init__(
            message=f"Credit/Debit note '{note_number}' already exists.",
            details={"code": "DUPLICATE_NOTE", "note_number": note_number},
        )


class ReconciliationNotFoundException(NotFoundException):
    def __init__(self, session_id: Any) -> None:
        super().__init__(
            message=f"Reconciliation session '{session_id}' not found.",
            details={"code": "RECONCILIATION_NOT_FOUND", "session_id": str(session_id)},
        )


class ReconciliationClosedException(AppException):
    def __init__(self, session_number: str) -> None:
        super().__init__(
            code="RECONCILIATION_CLOSED",
            message=f"Reconciliation session '{session_number}' is closed. Modifications are rejected.",
            status_code=400,
            details={"session_number": session_number},
        )


class ReceiptNotFoundException(NotFoundException):
    def __init__(self, receipt_id: Any) -> None:
        super().__init__(
            message=f"Receipt '{receipt_id}' not found.",
            details={"code": "RECEIPT_NOT_FOUND", "receipt_id": str(receipt_id)},
        )


class ReceiptImmutableException(AppException):
    def __init__(self, receipt_number: str, status: str) -> None:
        super().__init__(
            code="RECEIPT_IMMUTABLE",
            message=f"Receipt '{receipt_number}' is {status} and cannot be modified or re-cancelled.",
            status_code=400,
            details={"receipt_number": receipt_number, "status": status},
        )


class PaymentImmutableException(AppException):
    def __init__(self, payment_id: Any, status: str) -> None:
        super().__init__(
            code="PAYMENT_IMMUTABLE",
            message=f"Payment '{payment_id}' has status '{status}' and cannot be reversed/refunded.",
            status_code=400,
            details={"payment_id": str(payment_id), "status": status},
        )
