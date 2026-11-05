"""Accounting & Financial Core Domain Database Models.

Deterministic, double-entry, multi-tenant accounting models.
Monetary values strictly use exact Decimal/Numeric representations; zero floating-point.
Tenant isolation strictly enforced through TenantScopedMixin and PostgreSQL RLS.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
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

from apps.api.src.database.base import ArchiveMixin, Base, TenantScopedMixin, TimestampMixin


class FinancialPeriod(Base, TimestampMixin, TenantScopedMixin):
    """
    Financial Reporting Period for an Apartment Society (e.g., Fiscal Year or Quarter).
    Control gate for journal entry postings.
    """

    __tablename__ = "financial_periods"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_financial_periods_date_range"),
        UniqueConstraint("society_id", "name", name="uq_financial_period_society_name"),
        Index("ix_financial_periods_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    fiscal_year: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="OPEN",
        nullable=False,
    )  # 'OPEN', 'CLOSED'
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society = relationship("Society", backref="financial_periods")
    journals = relationship("JournalEntry", back_populates="period")


class Account(Base, TimestampMixin, ArchiveMixin, TenantScopedMixin):
    """
    Chart of Accounts (COA) entity.
    Hierarchical structure with parent accounts, account classifications, and normal balances.
    Unique account_code per society tenant.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("society_id", "account_code", name="uq_accounts_society_code"),
        Index("ix_accounts_society_type", "society_id", "account_type"),
        Index("ix_accounts_society_active", "society_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_code: Mapped[str] = mapped_column(String(50), nullable=False)
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'ASSET', 'LIABILITY', 'EQUITY', 'INCOME', 'EXPENSE'
    sub_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'BANK', 'CASH', 'ACCOUNTS_RECEIVABLE', 'ACCOUNTS_PAYABLE', etc.
    parent_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    normal_balance: Mapped[str] = mapped_column(String(10), nullable=False)  # 'DEBIT' or 'CREDIT'
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    society = relationship("Society", backref="accounts")
    parent_account = relationship("Account", remote_side=[id], backref="child_accounts")
    journal_lines = relationship("JournalEntryLine", back_populates="account")


class JournalEntry(Base, TimestampMixin, TenantScopedMixin):
    """
    Financial Journal Entry Header.
    Double-entry immutable ledger entry once POSTED.
    TOTAL DEBITS must strictly equal TOTAL CREDITS before posting.
    """

    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("society_id", "journal_number", name="uq_journal_society_number"),
        Index("ix_journal_entries_society_date", "society_id", "entry_date"),
        Index("ix_journal_entries_society_status", "society_id", "status"),
        Index(
            "ix_journal_entries_idempotency",
            "society_id",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
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
    journal_number: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", nullable=False
    )  # 'DRAFT', 'POSTED', 'REVERSED'
    source_type: Mapped[str] = mapped_column(
        String(50), default="MANUAL", nullable=False
    )  # 'MANUAL', 'IMPORT', 'EXPENSE', 'BILLING', 'PAYMENT', 'SYSTEM', 'TALLY'
    source_record_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    total_debit: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reversed_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    period = relationship("FinancialPeriod", back_populates="journals")
    lines: Mapped[list["JournalEntryLine"]] = relationship(
        "JournalEntryLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.line_number",
    )
    reversed_entry = relationship("JournalEntry", remote_side=[id], foreign_keys=[reversed_entry_id])


class JournalEntryLine(Base, TenantScopedMixin):
    """
    Individual debit or credit line in a Journal Entry.
    Every line must be strictly debit OR credit; never both, never neither.
    """

    __tablename__ = "journal_entry_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="ck_journal_entry_lines_debit_or_credit",
        ),
        CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="ck_journal_lines_non_negative"),
        UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_lines_entry_line_number"),
        Index("ix_journal_entry_lines_account", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")


class Expense(Base, TimestampMixin, TenantScopedMixin):
    """
    Operational Society Expense.
    Draft expenses are approved and then posted through the double-entry accounting engine.
    """

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        UniqueConstraint("society_id", "expense_number", name="uq_expenses_society_number"),
        Index("ix_expenses_society_status", "society_id", "status"),
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
    expense_number: Mapped[str] = mapped_column(String(50), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    paid_from_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", nullable=False
    )  # 'DRAFT', 'APPROVED', 'POSTED', 'CANCELLED'
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    category_account = relationship("Account", foreign_keys=[category_account_id])
    paid_from_account = relationship("Account", foreign_keys=[paid_from_account_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])


class FinancialReport(Base, TimestampMixin, TenantScopedMixin):
    """
    Generated, versioned financial statements.
    Calculated exclusively from POSTED double-entry records.
    Published reports are immutable and versioned.
    """

    __tablename__ = "financial_reports"
    __table_args__ = (
        UniqueConstraint(
            "society_id", "report_type", "financial_period_id", "version", name="uq_reports_version"
        ),
        Index("ix_financial_reports_society_type", "society_id", "report_type"),
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
    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'TRIAL_BALANCE', 'GENERAL_LEDGER', 'INCOME_EXPENDITURE', 'BALANCE_SHEET', 'RECEIPTS_PAYMENTS', 'EXPENSE_SUMMARY'
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="GENERATED", nullable=False
    )  # 'DRAFT', 'GENERATED', 'REVIEW', 'APPROVED', 'PUBLISHED'
    report_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
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


class SocietyAccountingConfig(Base, TimestampMixin, TenantScopedMixin):
    """
    Per-society accounting mode, provider authority, and external synchronization configuration.
    Defines whether SocietySphere internal financial engine or external Tally is authoritative.
    """

    __tablename__ = "society_accounting_configs"
    __table_args__ = (UniqueConstraint("society_id", name="uq_accounting_config_society"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    accounting_mode: Mapped[str] = mapped_column(
        String(30), default="NATIVE", nullable=False
    )  # 'NATIVE', 'TALLY', 'HYBRID', 'IMPORT_EXPORT'
    authoritative_source: Mapped[str] = mapped_column(
        String(30), default="INTERNAL", nullable=False
    )  # 'INTERNAL', 'TALLY', 'HYBRID'
    default_currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    allow_backdated_postings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tally_company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tally_guid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sync_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
