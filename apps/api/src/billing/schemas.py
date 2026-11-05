"""Pydantic Schemas for Maintenance Billing Request and Response Payloads."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Billing Config ---
class BillingConfigCreateUpdateRequest(BaseModel):
    receivable_account_id: UUID
    income_account_id: UUID
    currency: str = Field(default="INR", min_length=3, max_length=3)
    billing_frequency: str = Field(default="MONTHLY")
    billing_day: int = Field(default=1, ge=1, le=28)
    default_due_days: int = Field(default=15, ge=1, le=90)
    late_fee_enabled: bool = False
    late_fee_type: str = Field(default="PERCENTAGE")
    late_fee_rate: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0.0000"))
    grace_period_days: int = Field(default=0, ge=0)
    max_late_fee: Decimal | None = None
    interest_enabled: bool = False
    auto_generate_enabled: bool = False
    approval_required: bool = True
    default_responsibility: str = Field(default="OWNER")
    bank_account_id: UUID | None = None
    late_fee_income_account_id: UUID | None = None


class BillingConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    currency: str
    billing_frequency: str
    billing_day: int
    default_due_days: int
    late_fee_enabled: bool
    late_fee_type: str
    late_fee_rate: Decimal
    grace_period_days: int
    max_late_fee: Decimal | None = None
    interest_enabled: bool
    auto_generate_enabled: bool
    approval_required: bool
    default_responsibility: str
    receivable_account_id: UUID
    income_account_id: UUID
    bank_account_id: UUID | None = None
    late_fee_income_account_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


# --- Charge Rules ---
class ChargeRuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    calculation_type: str = Field(..., min_length=2, max_length=30)
    rate_or_amount: Decimal = Field(..., ge=Decimal("0.0000"))
    income_account_id: UUID
    effective_from: date
    effective_to: date | None = None
    unit_type_rates: dict[str, Any] | None = None
    description: str | None = None


class ChargeRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    name: str
    code: str
    calculation_type: str
    rate_or_amount: Decimal
    unit_type_rates: dict[str, Any] | None = None
    effective_from: date
    effective_to: date | None = None
    income_account_id: UUID
    is_active: bool
    description: str | None = None
    created_at: datetime


# --- Billing Periods ---
class BillingPeriodCreateRequest(BaseModel):
    financial_period_id: UUID
    period_code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)
    start_date: date
    end_date: date
    billing_date: date
    due_date: date


class BillingPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    financial_period_id: UUID
    period_code: str
    name: str
    start_date: date
    end_date: date
    billing_date: date
    due_date: date
    status: str
    generated_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime


# --- Invoices ---
class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit_rate: Decimal
    amount: Decimal
    accounting_account_id: UUID
    charge_rule_id: UUID | None = None
    charge_rule_snapshot: dict[str, Any] | None = None


class InvoiceAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    adjustment_type: str
    amount: Decimal
    reason: str
    created_at: datetime


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    billing_period_id: UUID
    unit_id: UUID
    unit_number: str | None = None
    responsible_user_id: UUID
    invoice_number: str
    invoice_date: date
    due_date: date
    subtotal: Decimal
    adjustment_total: Decimal
    late_fee_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    status: str
    currency: str
    journal_entry_id: UUID | None = None
    accounting_status: str
    accounting_error: str | None = None
    published_at: datetime | None = None
    lines: list[InvoiceLineResponse] = Field(default_factory=list)
    adjustments: list[InvoiceAdjustmentResponse] = Field(default_factory=list)
    created_at: datetime


class InvoiceAdjustmentRequest(BaseModel):
    adjustment_type: str = Field(..., description="DISCOUNT, WAIVER, SURCHARGE, CORRECTION")
    amount: Decimal = Field(..., gt=Decimal("0.0000"))
    reason: str = Field(..., min_length=3, max_length=500)


class CreditDebitNoteCreateRequest(BaseModel):
    note_type: str = Field(..., description="CREDIT_NOTE or DEBIT_NOTE")
    amount: Decimal = Field(..., gt=Decimal("0.0000"))
    reason: str = Field(..., min_length=3, max_length=500)


class CreditDebitNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    invoice_id: UUID
    note_type: str
    note_number: str
    amount: Decimal
    reason: str
    journal_entry_id: UUID | None = None
    status: str
    created_at: datetime


# --- Payments & Allocations ---
class PaymentCreateRequest(BaseModel):
    payer_user_id: UUID
    amount: Decimal = Field(..., gt=Decimal("0.0000"))
    payment_date: date
    reference_number: str = Field(..., min_length=2, max_length=100)
    payment_method: str = Field(default="BANK_TRANSFER")
    unit_id: UUID | None = None
    bank_account_id: UUID | None = None
    notes: str | None = None
    currency: str = Field(default="INR", min_length=3, max_length=3)
    idempotency_key: str | None = None
    auto_allocate: bool = True
    auto_clear: bool | None = None


class PaymentAllocationRequest(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(..., gt=Decimal("0.0000"))


class PaymentAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    invoice_id: UUID
    amount: Decimal
    allocated_at: datetime
    status: str = "ACTIVE"
    reversed_at: datetime | None = None
    reversal_reason: str | None = None
    reversal_reference: str | None = None


class PaymentReverseRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class PaymentClearRequest(BaseModel):
    cleared_date: date | None = None


class PaymentBounceRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class PaymentRefundRequest(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0.0000"))
    reason: str = Field(..., min_length=3, max_length=500)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    payer_user_id: UUID
    unit_id: UUID | None = None
    bank_account_id: UUID | None = None
    amount: Decimal
    currency: str
    payment_date: date
    payment_method: str
    reference_number: str
    notes: str | None = None
    status: str
    allocated_amount: Decimal
    unallocated_amount: Decimal
    idempotency_key: str | None = None
    journal_entry_id: UUID | None = None
    reversal_journal_entry_id: UUID | None = None
    reversal_reason: str | None = None
    reversed_at: datetime | None = None
    allocations: list[PaymentAllocationResponse] = Field(default_factory=list)
    created_at: datetime


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    payment_id: UUID
    receipt_number: str
    receipt_date: date
    amount: Decimal
    payer_user_id: UUID
    unit_id: UUID | None = None
    status: str
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    created_at: datetime


class ReceiptCancelRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


# --- Reconciliation Schemas ---
class ReconciliationSessionCreateRequest(BaseModel):
    account_id: UUID
    statement_reference: str = Field(..., min_length=2, max_length=100)
    statement_start_date: date
    statement_end_date: date
    opening_balance: Decimal = Field(default=Decimal("0.0000"))
    closing_balance: Decimal
    notes: str | None = None


class ReconciliationItemCreateRequest(BaseModel):
    transaction_date: date
    reference_number: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=255)
    statement_amount: Decimal
    payment_id: UUID | None = None
    notes: str | None = None


class ReconciliationMatchRequest(BaseModel):
    payment_id: UUID


class ReconciliationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    payment_id: UUID | None = None
    transaction_date: date
    reference_number: str
    description: str
    statement_amount: Decimal
    recorded_amount: Decimal | None = None
    discrepancy_amount: Decimal
    match_status: str
    notes: str | None = None
    matched_at: datetime | None = None


class ReconciliationSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    session_number: str
    account_id: UUID
    statement_reference: str
    statement_start_date: date
    statement_end_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    reconciled_amount: Decimal
    unreconciled_amount: Decimal
    status: str
    notes: str | None = None
    closed_at: datetime | None = None
    items: list[ReconciliationItemResponse] = Field(default_factory=list)
    created_at: datetime


# --- Reports ---
class CollectionSummaryResponse(BaseModel):
    total_subtotal: str
    total_adjustments: str
    total_late_fees: str
    total_billed: str
    total_paid_against_invoices: str
    total_outstanding: str
    total_invoices_count: int
    total_payments_recorded: str
    total_payments_allocated: str
    total_payments_unallocated: str
    total_payments_count: int


class UnitOutstandingResponse(BaseModel):
    unit_id: str
    unit_number: str
    outstanding_amount: str
    unpaid_invoices_count: int


class ResidentOutstandingResponse(BaseModel):
    user_id: str
    display_name: str
    email: str | None = None
    outstanding_amount: str
    unpaid_invoices_count: int


class AgingReportResponse(BaseModel):
    as_of_date: str
    total_outstanding: str
    aging_buckets: dict[str, str]
    invoices_analyzed: int
