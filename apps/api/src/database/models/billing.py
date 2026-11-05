"""Maintenance Billing and Resident Financial Obligation Models."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.finance import Account, FinancialPeriod, JournalEntry
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society, Unit


class SocietyBillingConfig(Base, TimestampMixin, TenantScopedMixin):
    """
    Society-level billing configuration and defaults.
    Controls billing cycle frequency, due days, late fee rules, and account mappings.
    """

    __tablename__ = "society_billing_configs"
    __table_args__ = (UniqueConstraint("society_id", name="uq_billing_config_society"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    billing_frequency: Mapped[str] = mapped_column(
        String(20), default="MONTHLY", nullable=False
    )  # 'MONTHLY', 'QUARTERLY', 'BIANNUAL', 'ANNUAL'
    billing_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    default_due_days: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    late_fee_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    late_fee_type: Mapped[str] = mapped_column(
        String(30), default="PERCENTAGE", nullable=False
    )  # 'FIXED_AMOUNT', 'PERCENTAGE', 'PER_DAY_PERCENTAGE'
    late_fee_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    grace_period_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_late_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    interest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_generate_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_responsibility: Mapped[str] = mapped_column(
        String(30), default="OWNER", nullable=False
    )  # 'OWNER', 'TENANT', 'RESPONSIBLE_PARTY'

    # Accounting Integration Accounts
    receivable_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    income_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    late_fee_income_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="billing_config")
    receivable_account: Mapped["Account"] = relationship("Account", foreign_keys=[receivable_account_id])
    income_account: Mapped["Account"] = relationship("Account", foreign_keys=[income_account_id])
    bank_account: Mapped["Account | None"] = relationship("Account", foreign_keys=[bank_account_id])
    late_fee_income_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[late_fee_income_account_id]
    )


class MaintenanceChargeRule(Base, TimestampMixin, TenantScopedMixin):
    """
    Configurable maintenance charge calculation rule.
    Supports fixed per unit, per square foot, and unit type based formulas.
    """

    __tablename__ = "billing_rules"
    __table_args__ = (
        UniqueConstraint("society_id", "code", name="uq_billing_rules_society_code"),
        Index("ix_billing_rules_society_active", "society_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    calculation_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # 'FIXED_PER_UNIT', 'PER_SQFT', 'UNIT_TYPE', 'BLOCK', 'FLOOR'
    rate_or_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    unit_type_rates: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    income_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="charge_rules")
    income_account: Mapped["Account"] = relationship("Account")


class BillingPeriod(Base, TimestampMixin, TenantScopedMixin):
    """
    Discrete operational billing cycle (e.g., April 2026).
    Links to Phase 4 FinancialPeriod for accounting control.
    """

    __tablename__ = "billing_periods"
    __table_args__ = (
        UniqueConstraint("society_id", "period_code", name="uq_billing_periods_society_code"),
        CheckConstraint("end_date >= start_date", name="ck_billing_periods_date_range"),
        Index("ix_billing_periods_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    financial_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_periods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    period_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", nullable=False
    )  # 'DRAFT', 'GENERATED', 'REVIEW', 'APPROVED', 'PUBLISHED', 'CLOSED', 'CANCELLED'

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="billing_periods")
    financial_period: Mapped["FinancialPeriod"] = relationship("FinancialPeriod")
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="billing_period")


class Invoice(Base, TimestampMixin, TenantScopedMixin):
    """
    Individual maintenance invoice issued to a resident/unit for a billing period.
    Idempotent by (society_id, billing_period_id, unit_id).
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("society_id", "billing_period_id", "unit_id", name="uq_invoices_period_unit"),
        UniqueConstraint("society_id", "invoice_number", name="uq_invoices_society_number"),
        Index("ix_invoices_society_status", "society_id", "status"),
        Index("ix_invoices_society_unit", "society_id", "unit_id"),
        Index("ix_invoices_society_user", "society_id", "responsible_user_id"),
        Index("ix_invoices_due_date", "society_id", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    billing_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    responsible_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    adjustment_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    late_fee_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", nullable=False
    )  # 'DRAFT', 'REVIEW', 'APPROVED', 'PUBLISHED', 'PAID', 'PARTIALLY_PAID', 'OVERDUE', 'CANCELLED'
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    # Accounting Reference
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    accounting_status: Mapped[str] = mapped_column(
        String(20), default="NOT_POSTED", nullable=False
    )  # 'NOT_POSTED', 'POSTED', 'FAILED', 'PENDING'
    accounting_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="invoices")
    billing_period: Mapped["BillingPeriod"] = relationship("BillingPeriod", back_populates="invoices")
    unit: Mapped["Unit"] = relationship("Unit", backref="invoices")
    responsible_user: Mapped["User"] = relationship("User", foreign_keys=[responsible_user_id])
    journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")
    lines: Mapped[list["InvoiceLine"]] = relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLine.line_number",
        lazy="selectin",
    )
    adjustments: Mapped[list["BillingAdjustment"]] = relationship(
        "BillingAdjustment",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        "PaymentAllocation",
        back_populates="invoice",
        lazy="selectin",
    )


class InvoiceLine(Base, TenantScopedMixin):
    """
    Detailed breakdown line item within an invoice.
    Freezes calculation rate and rule snapshot for historical integrity.
    """

    __tablename__ = "invoice_lines"
    __table_args__ = (
        Index("ix_invoice_lines_invoice_id", "invoice_id"),
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_lines_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    charge_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    charge_rule_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1.0000"), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    accounting_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")
    charge_rule: Mapped["MaintenanceChargeRule | None"] = relationship("MaintenanceChargeRule")
    account: Mapped["Account"] = relationship("Account")


class BillingAdjustment(Base, TenantScopedMixin):
    """
    Controlled adjustment (waiver, discount, correction, surcharge) on an invoice.
    """

    __tablename__ = "billing_adjustments"
    __table_args__ = (Index("ix_billing_adjustments_invoice", "invoice_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    adjustment_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # 'DISCOUNT', 'WAIVER', 'SURCHARGE', 'CORRECTION'
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc if hasattr(datetime, "timezone") else None),  # type: ignore
        nullable=False,
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="adjustments")


class CreditDebitNote(Base, TimestampMixin, TenantScopedMixin):
    """
    Credit Note or Debit Note referencing an original invoice.
    Creates corresponding accounting impact without modifying original invoice history.
    """

    __tablename__ = "credit_debit_notes"
    __table_args__ = (
        UniqueConstraint("society_id", "note_number", name="uq_notes_society_number"),
        Index("ix_notes_society_invoice", "society_id", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    note_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'CREDIT_NOTE', 'DEBIT_NOTE'
    note_number: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="APPLIED", nullable=False
    )  # 'APPLIED', 'CANCELLED'
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice")
    journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")


class Payment(Base, TimestampMixin, TenantScopedMixin):
    """
    Resident payment recorded against maintenance dues.
    Serves as payment allocation foundation without third-party gateway coupling.
    """

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_society_payer", "society_id", "payer_user_id"),
        Index("ix_payments_society_date", "society_id", "payment_date"),
        Index("ix_payments_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    payer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(30), default="BANK_TRANSFER", nullable=False
    )  # 'BANK_TRANSFER', 'CHEQUE', 'CASH', 'UPI_MANUAL', 'OTHER'
    reference_number: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="RECORDED", nullable=False
    )  # 'RECORDED', 'ALLOCATED', 'PARTIALLY_ALLOCATED', 'BOUNCED', 'CANCELLED'

    allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    unallocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )

    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="payments")
    payer_user: Mapped["User"] = relationship("User", foreign_keys=[payer_user_id])
    unit: Mapped["Unit | None"] = relationship("Unit")
    bank_account: Mapped["Account | None"] = relationship("Account", foreign_keys=[bank_account_id])
    journal_entry: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry", foreign_keys=[journal_entry_id]
    )
    reversal_journal_entry: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry", foreign_keys=[reversal_journal_entry_id]
    )
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        "PaymentAllocation",
        back_populates="payment",
        cascade="all, delete-orphan",
    )
    receipt: Mapped["Receipt | None"] = relationship("Receipt", back_populates="payment", uselist=False)


class PaymentAllocation(Base, TenantScopedMixin):
    """
    Deterministic allocation of a recorded payment against a specific invoice.
    Tracks precise amount applied to outstanding invoice balance.
    """

    __tablename__ = "payment_allocations"
    __table_args__ = (
        Index("ix_payment_allocations_payment", "payment_id"),
        Index("ix_payment_allocations_invoice", "invoice_id"),
        Index("ix_payment_allocations_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc if hasattr(datetime, "timezone") else None),  # type: ignore
        nullable=False,
    )
    allocated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)  # 'ACTIVE', 'REVERSED'
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reversal_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    payment: Mapped["Payment"] = relationship("Payment", back_populates="allocations")
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="allocations")


class Receipt(Base, TimestampMixin, TenantScopedMixin):
    """
    Payment receipt issued upon payment allocation.
    Per-society unique sequential receipt number.
    """

    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("society_id", "receipt_number", name="uq_receipts_society_number"),
        Index("ix_receipts_society_payer", "society_id", "payer_user_id"),
        Index("ix_receipts_society_payment", "society_id", "payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    receipt_number: Mapped[str] = mapped_column(String(50), nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    payer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="ISSUED", nullable=False)  # 'ISSUED', 'CANCELLED'
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="receipts")
    payment: Mapped["Payment"] = relationship("Payment", back_populates="receipt")
    payer_user: Mapped["User"] = relationship("User", foreign_keys=[payer_user_id])
    unit: Mapped["Unit | None"] = relationship("Unit")
