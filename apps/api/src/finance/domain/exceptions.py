"""Financial Domain Exceptions."""

from typing import Any

from apps.api.src.core.exceptions import AppException


class FinanceDomainException(AppException):
    """Base domain exception for financial core violations."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class UnbalancedJournalException(FinanceDomainException):
    def __init__(self, debit_total: str, credit_total: str, difference: str) -> None:
        super().__init__(
            code="UNBALANCED_JOURNAL_ENTRY",
            message=f"Double-entry validation failed: Total Debits ({debit_total}) must equal Total Credits ({credit_total}). Discrepancy: {difference}",
            status_code=400,
            details={"debit_total": debit_total, "credit_total": credit_total, "difference": difference},
        )


class ClosedPeriodPostingException(FinanceDomainException):
    def __init__(self, period_name: str, period_id: str) -> None:
        super().__init__(
            code="CLOSED_PERIOD_POSTING_REJECTED",
            message=f"Financial postings are strictly prohibited into closed financial period '{period_name}'.",
            status_code=400,
            details={"period_id": period_id, "period_name": period_name},
        )


class InvalidFinancialPeriodDateException(FinanceDomainException):
    def __init__(self, entry_date: str, start_date: str, end_date: str) -> None:
        super().__init__(
            code="JOURNAL_DATE_OUTSIDE_PERIOD",
            message=f"Transaction entry date {entry_date} falls outside the active financial period bounds ({start_date} to {end_date}).",
            status_code=400,
            details={"entry_date": entry_date, "start_date": start_date, "end_date": end_date},
        )


class InactiveAccountPostingException(FinanceDomainException):
    def __init__(self, account_code: str, account_name: str) -> None:
        super().__init__(
            code="INACTIVE_ACCOUNT_POSTING_REJECTED",
            message=f"Account '{account_code} - {account_name}' is inactive and cannot receive new financial postings.",
            status_code=400,
            details={"account_code": account_code, "account_name": account_name},
        )


class CrossTenantFinancialException(FinanceDomainException):
    def __init__(
        self, message: str = "Cross-tenant financial entity referencing is strictly forbidden."
    ) -> None:
        super().__init__(
            code="CROSS_TENANT_FINANCIAL_VIOLATION",
            message=message,
            status_code=403,
        )


class ImmutableRecordException(FinanceDomainException):
    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(
            code="IMMUTABLE_FINANCIAL_RECORD",
            message=f"Posted financial records are immutable. Direct editing or deletion of {entity_type} '{entity_id}' is forbidden. Use a reversal entry.",
            status_code=400,
            details={"entity_type": entity_type, "entity_id": entity_id},
        )


class DuplicateReversalException(FinanceDomainException):
    def __init__(self, journal_number: str) -> None:
        super().__init__(
            code="ALREADY_REVERSED",
            message=f"Journal entry '{journal_number}' has already been reversed. Multiple reversals are prevented.",
            status_code=400,
            details={"journal_number": journal_number},
        )


class InvalidJournalLinesException(FinanceDomainException):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="INVALID_JOURNAL_LINES",
            message=message,
            status_code=400,
        )


class ProviderNotConfiguredException(FinanceDomainException):
    def __init__(self, provider_name: str) -> None:
        super().__init__(
            code="PROVIDER_NOT_CONFIGURED",
            message=f"Accounting provider '{provider_name}' is not configured or transport is not enabled.",
            status_code=501,
            details={"provider": provider_name},
        )
