"""Financial Domain Enums, Monetary Quantization, and Double-Entry Rules."""

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class NormalBalance(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class PeriodStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class JournalStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class JournalSourceType(StrEnum):
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    EXPENSE = "EXPENSE"
    BILLING = "BILLING"
    PAYMENT = "PAYMENT"
    SYSTEM = "SYSTEM"
    TALLY = "TALLY"


class ExpenseStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class ReportType(StrEnum):
    TRIAL_BALANCE = "TRIAL_BALANCE"
    GENERAL_LEDGER = "GENERAL_LEDGER"
    INCOME_EXPENDITURE = "INCOME_EXPENDITURE"
    BALANCE_SHEET = "BALANCE_SHEET"
    RECEIPTS_PAYMENTS = "RECEIPTS_PAYMENTS"
    EXPENSE_SUMMARY = "EXPENSE_SUMMARY"


class ReportStatus(StrEnum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"


class AccountingMode(StrEnum):
    NATIVE = "NATIVE"
    TALLY = "TALLY"
    HYBRID = "HYBRID"
    IMPORT_EXPORT = "IMPORT_EXPORT"


class AuthoritativeSource(StrEnum):
    INTERNAL = "INTERNAL"
    TALLY = "TALLY"
    HYBRID = "HYBRID"


# Deterministic Monetary Calculation Helpers
FOUR_PLACES = Decimal("0.0001")
TWO_PLACES = Decimal("0.01")
ZERO_AMOUNT = Decimal("0.0000")


def quantize_amount(amount: Decimal | str | int | float, places: int = 4) -> Decimal:
    """
    Deterministically quantize monetary amounts to exact decimal precision.
    Floating-point inputs are converted via string to avoid IEEE 754 precision artifacts.
    """
    if isinstance(amount, float):
        d = Decimal(str(amount))
    elif isinstance(amount, Decimal):
        d = amount
    else:
        d = Decimal(str(amount))

    quantum = FOUR_PLACES if places == 4 else TWO_PLACES
    return d.quantize(quantum, rounding=ROUND_HALF_UP)


def default_normal_balance(account_type: AccountType) -> NormalBalance:
    """
    Standard accounting normal balances:
    - ASSETS and EXPENSES naturally have DEBIT normal balances.
    - LIABILITIES, EQUITY, and INCOME naturally have CREDIT normal balances.
    """
    if account_type in (AccountType.ASSET, AccountType.EXPENSE):
        return NormalBalance.DEBIT
    return NormalBalance.CREDIT
