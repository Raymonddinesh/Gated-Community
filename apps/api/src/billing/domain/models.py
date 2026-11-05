"""Billing Domain Enums, Interfaces, and Calculation Structures."""

from enum import StrEnum


class BillingFrequency(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    BIANNUAL = "BIANNUAL"
    ANNUAL = "ANNUAL"


class ChargeCalculationType(StrEnum):
    FIXED_PER_UNIT = "FIXED_PER_UNIT"
    PER_SQFT = "PER_SQFT"
    UNIT_TYPE = "UNIT_TYPE"
    BLOCK = "BLOCK"
    FLOOR = "FLOOR"


class BillingPeriodStatus(StrEnum):
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class AccountingStatus(StrEnum):
    NOT_POSTED = "NOT_POSTED"
    POSTED = "POSTED"
    FAILED = "FAILED"
    PENDING = "PENDING"


class ResponsiblePartyType(StrEnum):
    OWNER = "OWNER"
    TENANT = "TENANT"
    RESPONSIBLE_PARTY = "RESPONSIBLE_PARTY"


class AdjustmentType(StrEnum):
    DISCOUNT = "DISCOUNT"
    WAIVER = "WAIVER"
    SURCHARGE = "SURCHARGE"
    CORRECTION = "CORRECTION"


class NoteType(StrEnum):
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"


class NoteStatus(StrEnum):
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"


class LateFeeType(StrEnum):
    FIXED_AMOUNT = "FIXED_AMOUNT"
    PERCENTAGE = "PERCENTAGE"
    PER_DAY_PERCENTAGE = "PER_DAY_PERCENTAGE"


class PaymentSource(StrEnum):
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    BANK = "BANK"
    GATEWAY = "GATEWAY"


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    CASH = "CASH"
    UPI = "UPI"
    UPI_MANUAL = "UPI_MANUAL"
    DD = "DD"
    CARD = "CARD"
    OTHER = "OTHER"


class PaymentStatus(StrEnum):
    RECORDED = "RECORDED"
    CLEARED = "CLEARED"
    ALLOCATED = "ALLOCATED"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    BOUNCED = "BOUNCED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"
    REFUNDED = "REFUNDED"


class ReceiptStatus(StrEnum):
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"


class ReconciliationSessionStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RECONCILED = "RECONCILED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class MatchStatus(StrEnum):
    UNMATCHED = "UNMATCHED"
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    EXCLUDED = "EXCLUDED"


class AllocationStrategy(StrEnum):
    OLDEST_FIRST = "OLDEST_FIRST"
    EXPLICIT = "EXPLICIT"
