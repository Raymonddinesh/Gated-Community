"""Pydantic schemas for the Finance & Accounting module."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Financial Period Schemas ---
class PeriodCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    start_date: date
    end_date: date
    fiscal_year: str = Field(..., min_length=4, max_length=20)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, v: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be strictly after start_date")
        return v


class PeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    name: str
    start_date: date
    end_date: date
    fiscal_year: str
    status: str
    currency: str
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class PeriodCloseRequest(BaseModel):
    reason: str | None = None


class PeriodReopenRequest(BaseModel):
    reason: str = Field(..., min_length=5, description="Audited justification for reopening period")


# --- Account / Chart of Accounts Schemas ---
class AccountCreateRequest(BaseModel):
    account_code: str = Field(..., min_length=2, max_length=50)
    account_name: str = Field(..., min_length=2, max_length=150)
    account_type: str = Field(..., pattern="^(ASSET|LIABILITY|EQUITY|INCOME|EXPENSE)$")
    normal_balance: str = Field(..., pattern="^(DEBIT|CREDIT)$")
    parent_account_id: UUID | None = None
    sub_type: str | None = Field(None, max_length=50)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    is_system_account: bool = False


class AccountUpdateRequest(BaseModel):
    account_name: str | None = Field(None, min_length=2, max_length=150)
    is_active: bool | None = None
    sub_type: str | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    account_code: str
    account_name: str
    account_type: str
    normal_balance: str
    parent_account_id: UUID | None = None
    is_active: bool
    is_system_account: bool = False
    sub_type: str | None = None
    currency: str
    created_at: datetime
    updated_at: datetime


# --- Journal Entry Schemas ---
class JournalLineCreateRequest(BaseModel):
    account_id: UUID
    debit_amount: Decimal = Field(default=Decimal("0.0000"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0.0000"), ge=0)
    description: str | None = None

    @field_validator("credit_amount")
    @classmethod
    def validate_one_sided_line(cls, v: Decimal, info: Any) -> Decimal:
        deb = info.data.get("debit_amount", Decimal("0.0000"))
        if deb > 0 and v > 0:
            raise ValueError("A single line cannot have both positive debit and credit amounts.")
        if deb == 0 and v == 0:
            raise ValueError("A line must have either debit > 0 or credit > 0.")
        return v


class JournalEntryCreateRequest(BaseModel):
    financial_period_id: UUID
    entry_date: date
    description: str = Field(..., min_length=3, max_length=500)
    lines: list[JournalLineCreateRequest] = Field(..., min_length=2)
    source_type: str = Field(default="MANUAL", max_length=50)
    source_record_id: str | None = None
    reference_number: str | None = None
    currency: str = Field(default="INR", min_length=3, max_length=3)
    idempotency_key: str | None = None

    @field_validator("lines")
    @classmethod
    def validate_balanced_entry(cls, lines: list[JournalLineCreateRequest]) -> list[JournalLineCreateRequest]:
        total_deb = sum(line.debit_amount for line in lines)
        total_crd = sum(line.credit_amount for line in lines)
        if total_deb != total_crd:
            raise ValueError(
                f"Journal entry must balance: total debit {total_deb} != total credit {total_crd}"
            )
        return lines


class JournalLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    journal_entry_id: UUID
    account_id: UUID
    account_code: str | None = None
    account_name: str | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None = None


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    financial_period_id: UUID
    journal_number: str
    entry_date: date
    description: str
    status: str
    source_type: str
    source_record_id: str | None = None
    reference_number: str | None = None
    total_debit: Decimal
    total_credit: Decimal
    currency: str
    posted_at: datetime | None = None
    posted_by: UUID | None = None
    reversed_entry_id: UUID | None = None
    reversal_reason: str | None = None
    idempotency_key: str | None = None
    lines: list[JournalLineResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class JournalReverseRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


# --- Expense Schemas ---
class ExpenseCreateRequest(BaseModel):
    financial_period_id: UUID
    category_account_id: UUID
    paid_from_account_id: UUID
    amount: Decimal = Field(..., gt=0)
    expense_date: date
    description: str = Field(..., min_length=3, max_length=500)
    vendor_name: str | None = Field(None, max_length=200)
    reference_number: str | None = Field(None, max_length=100)
    currency: str = Field(default="INR", min_length=3, max_length=3)


class ExpenseApproveRequest(BaseModel):
    notes: str | None = None


class ExpenseRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    financial_period_id: UUID
    category_account_id: UUID
    paid_from_account_id: UUID
    expense_number: str
    amount: Decimal
    currency: str
    expense_date: date
    vendor_name: str | None = None
    reference_number: str | None = None
    description: str
    status: str
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    journal_entry_id: UUID | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


# --- Financial Reports Schemas ---
class ReportGenerateRequest(BaseModel):
    report_type: str = Field(
        ...,
        pattern="^(TRIAL_BALANCE|GENERAL_LEDGER|INCOME_EXPENDITURE|BALANCE_SHEET|RECEIPTS_PAYMENTS)$",
    )
    financial_period_id: UUID
    name: str | None = None
    publish_immediately: bool = False


class FinancialReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    financial_period_id: UUID
    report_type: str
    name: str
    version: int
    status: str
    report_data: dict[str, Any]
    generated_at: datetime
    generated_by: UUID | None = None
    published_at: datetime | None = None


# --- Accounting Config Schemas ---
class AccountingConfigUpdateRequest(BaseModel):
    accounting_mode: str | None = Field(None, pattern="^(NATIVE|TALLY|HYBRID|IMPORT_EXPORT)$")
    authoritative_source: str | None = Field(None, pattern="^(INTERNAL|TALLY)$")
    tally_company_name: str | None = None
    tally_guid: str | None = None


class AccountingConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    accounting_mode: str
    authoritative_source: str
    default_currency: str = "INR"
    allow_backdated_postings: bool = False
    tally_company_name: str | None = None
    tally_guid: str | None = None
    sync_metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# --- Import / Export Schemas ---
class ExternalJournalLineDTO(BaseModel):
    account_code: str
    debit_amount: Decimal = Field(default=Decimal("0.0000"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0.0000"), ge=0)
    description: str | None = None


class ExternalJournalEntryDTO(BaseModel):
    journal_number: str | None = None
    entry_date: date
    description: str
    lines: list[ExternalJournalLineDTO] = Field(..., min_length=2)
    source_type: str = "IMPORT"
    reference_number: str | None = None
    currency: str = "INR"
    idempotency_key: str | None = None


class JournalImportRequest(BaseModel):
    entries: list[ExternalJournalEntryDTO]
    dry_run: bool = True


class ProviderResultResponse(BaseModel):
    success: bool
    message: str
    record_id: str | None = None
    journal_number: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
